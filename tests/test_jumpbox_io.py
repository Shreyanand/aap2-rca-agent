"""Tests for uploading analysis artifacts over SSH/rsync."""

from pathlib import Path
from unittest.mock import Mock

from rca.analysis import jumpbox_io


def test_upload_uses_ssh_config_alias_for_ssh_and_rsync(
    monkeypatch, tmp_path: Path
) -> None:
    analysis_dir = tmp_path / "analysis"
    analysis_dir.mkdir()
    run = Mock()
    monkeypatch.setattr(jumpbox_io.subprocess, "run", run)

    assert jumpbox_io.upload_to_jumpbox(
        "123",
        analysis_dir,
        jumpbox_uri="agent@unresolvable.example.test -p 2222",
        ssh_jumpbox_alias="ci-jumpbox",
    )

    ssh_call, rsync_call = [call.args[0] for call in run.call_args_list]
    assert ssh_call == [
        "ssh",
        "ci-jumpbox",
        "mkdir -p /usr/local/mlflow/123",
    ]
    assert "unresolvable.example.test" not in ssh_call
    assert rsync_call == [
        "rsync",
        "-az",
        "--quiet",
        f"{analysis_dir}/",
        "ci-jumpbox:/usr/local/mlflow/123/",
    ]
    assert "-e" not in rsync_call


def test_upload_keeps_uri_target_when_no_alias_is_configured(
    monkeypatch, tmp_path: Path
) -> None:
    analysis_dir = tmp_path / "analysis"
    analysis_dir.mkdir()
    run = Mock()
    monkeypatch.setattr(jumpbox_io.subprocess, "run", run)
    monkeypatch.delenv("SSH_JUMPBOX_ALIAS", raising=False)

    assert jumpbox_io.upload_to_jumpbox(
        "123",
        analysis_dir,
        jumpbox_uri="agent@jumpbox.example.test -p 2222",
    )

    ssh_call, rsync_call = [call.args[0] for call in run.call_args_list]
    assert ssh_call == [
        "ssh",
        "-p",
        "2222",
        "agent@jumpbox.example.test",
        "mkdir -p /usr/local/mlflow/123",
    ]
    assert rsync_call[:3] == ["rsync", "-e", "ssh -p 2222"]
    assert rsync_call[-1] == "agent@jumpbox.example.test:/usr/local/mlflow/123/"
