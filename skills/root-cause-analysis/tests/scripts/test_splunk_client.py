import base64
from unittest.mock import patch

import pytest

from scripts.splunk_client import (
    SplunkClient,
    create_search_job,
    get_auth_header,
)

# --- get_auth_header tests ---


def test_get_auth_header_basic(mock_config):
    """Test Basic auth header generation."""
    # Ensure token is None to trigger basic auth logic
    mock_config.splunk.token = None
    mock_config.splunk.username = "user"
    mock_config.splunk.password = "password"

    header = get_auth_header(mock_config)
    expected_creds = base64.b64encode(b"user:password").decode()
    assert header == {"Authorization": f"Basic {expected_creds}"}


def test_get_auth_header_token(mock_config):
    """Test Bearer token auth header generation."""
    # Ensure username/password are cleared so token auth takes precedence
    mock_config.splunk.username = ""
    mock_config.splunk.password = ""
    mock_config.splunk.token = "my-token"

    header = get_auth_header(mock_config)
    assert header == {"Authorization": "Bearer my-token"}


def test_get_auth_header_none(mock_config):
    """Test error when no auth configured."""
    # Clear all auth fields
    mock_config.splunk.username = ""
    mock_config.splunk.password = ""
    mock_config.splunk.token = None

    with pytest.raises(ValueError, match="No authentication configured"):
        get_auth_header(mock_config)


# --- create_search_job tests ---


@patch("scripts.splunk_client.splunk_request")
def test_create_search_job_prepends_search(mock_request, mock_config):
    """Test 'search' is prepended to query if missing."""
    mock_request.return_value = {"sid": "123"}

    sid = create_search_job(mock_config, 'index=main "error"')

    assert sid == "123"
    mock_request.assert_called_once()
    args, kwargs = mock_request.call_args
    assert kwargs["data"]["search"] == 'search index=main "error"'


@patch("scripts.splunk_client.splunk_request")
def test_create_search_job_no_prepend_if_present(mock_request, mock_config):
    """Test 'search' is NOT prepended if already present."""
    mock_request.return_value = {"sid": "123"}

    create_search_job(mock_config, 'search index=main "error"')

    args, kwargs = mock_request.call_args
    assert kwargs["data"]["search"] == 'search index=main "error"'


@patch("scripts.splunk_client.splunk_request")
def test_create_search_job_no_prepend_pipe(mock_request, mock_config):
    """Test 'search' is NOT prepended if query starts with pipe."""
    mock_request.return_value = {"sid": "123"}

    create_search_job(mock_config, "| tstats count")

    args, kwargs = mock_request.call_args
    assert kwargs["data"]["search"] == "| tstats count"


@patch("scripts.splunk_client.splunk_request")
def test_create_search_job_post_body(mock_request, mock_config):
    """Test correct POST body fields."""
    mock_request.return_value = {"sid": "123"}

    create_search_job(mock_config, "query", earliest="-1h", latest="now")

    args, kwargs = mock_request.call_args
    data = kwargs["data"]
    assert data["earliest_time"] == "-1h"
    assert data["latest_time"] == "now"


# --- SplunkClient tests ---


@patch("scripts.splunk_client.SplunkClient.query")
def test_query_ocp_namespace_basic(mock_query, mock_config):
    """Test OCP namespace query construction."""
    client = SplunkClient(mock_config)
    client.query_ocp_namespace("test-ns")

    mock_query.assert_called_once()
    query_arg = mock_query.call_args[0][0]
    assert "index=ocp_apps" in query_arg
    assert 'kubernetes.namespace_name="test-ns"' in query_arg


@patch("scripts.splunk_client.SplunkClient.query")
def test_query_ocp_namespace_errors_only(mock_query, mock_config):
    """Test OCP namespace query with error filtering."""
    client = SplunkClient(mock_config)
    client.query_ocp_namespace("test-ns", errors_only=True)

    mock_query.assert_called_once()
    query_arg = mock_query.call_args[0][0]
    assert "(error OR failed OR fatal OR exception OR FAILED OR ERROR)" in query_arg


@patch("scripts.splunk_client.SplunkClient.query")
def test_query_by_guid_default_index(mock_query, mock_config):
    """Test GUID query with default index."""
    client = SplunkClient(mock_config)
    client.query_by_guid("guid-123")

    mock_query.assert_called_once()
    query_arg = mock_query.call_args[0][0]
    assert "index=ocp_apps" in query_arg
    assert '"guid-123"' in query_arg


@patch("scripts.splunk_client.SplunkClient.query")
def test_query_by_guid_custom_index(mock_query, mock_config):
    """Test GUID query with custom index."""
    client = SplunkClient(mock_config)
    client.query_by_guid("guid-123", index="custom_idx")

    mock_query.assert_called_once()
    query_arg = mock_query.call_args[0][0]
    assert "index=custom_idx" in query_arg
    assert '"guid-123"' in query_arg
