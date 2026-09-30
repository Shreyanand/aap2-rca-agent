"""Tests for shared project configuration and SSH parsing."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from rca import database
from rca.config import load_database_config
from rca.ssh import (
    append_ssh_host_block,
    ensure_bastion_host,
    ensure_jumpbox_alias,
    parse_jumpbox_uri,
    ssh_host_exists,
)


def test_load_database_config_shares_environment_mapping() -> None:
    config = load_database_config(
        defaults={"host": "", "source_table": "aap2_events", "bastion_table": "aap2_user_url"},
        env={
            "SOURCE_DB_HOST": "db.internal",
            "SOURCE_DB_PORT": "15432",
            "SOURCE_DB_NAME": "rca",
            "SOURCE_DB_USER": "agent",
            "SOURCE_DB_PASSWORD": "secret",
            "SOURCE_DB_TABLE": "job_events",
        },
    )

    assert config == {
        "host": "db.internal",
        "port": 15432,
        "name": "rca",
        "user": "agent",
        "password": "secret",
        "source_table": "job_events",
        "results_table": "",
        "bastion_table": "aap2_user_url",
    }


def test_load_database_config_validates_required_environment() -> None:
    with pytest.raises(SystemExit):
        load_database_config(required=("name",), env={})


def test_lookup_job_bastion_row_uses_shared_connection_and_closes_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = {
        "host": "db.internal",
        "port": 5432,
        "name": "rca",
        "user": "agent",
        "password": "secret",
        "source_table": "job_events",
        "bastion_table": "cluster_bastions",
    }
    connection = MagicMock()
    cursor_context = MagicMock()
    cursor = cursor_context.__enter__.return_value
    row = {"job_id": 123, "cluster_name": "cluster-a"}
    cursor.fetchone.return_value = row
    connection.cursor.return_value = cursor_context
    connect = MagicMock(return_value=connection)
    monkeypatch.setattr(database, "connect_db", connect)

    result = database.lookup_job_bastion_row(config, "123")

    assert result == row
    connect.assert_called_once_with(config, use_dict_cursor=True)
    cursor.execute.assert_called_once()
    assert cursor.execute.call_args.args[1] == ("123",)
    connection.close.assert_called_once_with()


def test_parse_jumpbox_uri() -> None:
    assert parse_jumpbox_uri("rca@jumpbox.example.com -p 2222") == (
        "rca",
        "jumpbox.example.com",
        "2222",
    )
    assert parse_jumpbox_uri("rca@jumpbox.example.com") == (
        "rca",
        "jumpbox.example.com",
        None,
    )


@pytest.mark.parametrize("value", ["", "jumpbox.example.com", "@jumpbox", "rca@"])
def test_parse_jumpbox_uri_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        parse_jumpbox_uri(value)


def test_ssh_helpers_append_aliases_once(tmp_path: Path) -> None:
    config_path = tmp_path / ".ssh" / "config"
    append_ssh_host_block(config_path, "existing", ["HostName existing.example"])
    ensure_jumpbox_alias(
        "jumpbox",
        "rca@jumpbox.example.com -p 2222",
        identity_file="/tmp/key",
        config_path=config_path,
    )
    ensure_bastion_host(
        "bastion-cluster-a",
        "bastion.example.com",
        2200,
        "rca",
        "jumpbox",
        identity_file="/tmp/key",
        config_path=config_path,
    )
    ensure_jumpbox_alias(
        "jumpbox",
        "rca@another.example.com",
        identity_file="/tmp/key",
        config_path=config_path,
    )

    content = config_path.read_text()
    assert content.count("Host jumpbox\n") == 1
    assert "HostName jumpbox.example.com" in content
    assert "Port 2222" in content
    assert "ProxyJump jumpbox" in content
    assert ssh_host_exists("bastion-cluster-a", config_path)
    assert config_path.stat().st_mode & 0o777 == 0o600
