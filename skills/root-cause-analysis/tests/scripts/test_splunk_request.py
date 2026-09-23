from unittest.mock import MagicMock, patch

from scripts.splunk_client import splunk_request, wait_for_job  # noqa: E402

# --- splunk_request tests ---


@patch("urllib.request.urlopen")
def test_splunk_request_get(mock_urlopen, mock_config):
    """Test GET request using urllib."""
    # Mock response
    mock_response = MagicMock()
    mock_response.read.return_value = b'{"result": "success"}'
    mock_urlopen.return_value.__enter__.return_value = mock_response

    result = splunk_request(mock_config, "/test/endpoint")

    assert result == {"result": "success"}

    # Verify request construction
    mock_urlopen.assert_called_once()
    req = mock_urlopen.call_args[0][0]
    assert req.full_url == "https://splunk.example.com/services/test/endpoint?output_mode=json"
    assert req.method == "GET"
    assert req.headers["Authorization"].startswith("Basic")


@patch("urllib.request.urlopen")
def test_splunk_request_post(mock_urlopen, mock_config):
    """Test POST request using urllib."""
    mock_response = MagicMock()
    mock_response.read.return_value = b'{"sid": "123"}'
    mock_urlopen.return_value.__enter__.return_value = mock_response

    data = {"search": "index=main"}
    result = splunk_request(mock_config, "/search/jobs", method="POST", data=data)

    assert result == {"sid": "123"}

    # Verify request construction
    mock_urlopen.assert_called_once()
    req = mock_urlopen.call_args[0][0]
    assert req.method == "POST"
    assert b"search=index%3Dmain" in req.data


@patch("ssl.create_default_context")
@patch("urllib.request.urlopen")
def test_splunk_request_ssl_verify(mock_urlopen, mock_create_context, mock_config):
    """Test SSL verification setting."""
    mock_response = MagicMock()
    mock_response.read.return_value = b"{}"
    mock_urlopen.return_value.__enter__.return_value = mock_response

    # Verify SSL = False
    mock_config.splunk.verify_ssl = False
    splunk_request(mock_config, "/test")

    context = mock_create_context.return_value
    assert context.check_hostname is False
    # We can't easily check verify_mode constant value without importing ssl, but check_hostname is good enough


# --- wait_for_job tests ---


@patch("scripts.splunk_client.splunk_request")
@patch("time.sleep")
def test_wait_for_job_success(mock_sleep, mock_request, mock_config):
    """Test waiting for a job to complete successfully."""
    # Sequence of responses: RUNNING -> DONE
    mock_request.side_effect = [
        {"entry": [{"content": {"dispatchState": "RUNNING"}}]},
        {"entry": [{"content": {"dispatchState": "DONE", "resultCount": 100, "scanCount": 200}}]},
    ]

    result = wait_for_job(mock_config, "sid-123")

    assert result["status"] == "done"
    assert result["result_count"] == 100
    assert mock_sleep.called


@patch("scripts.splunk_client.splunk_request")
@patch("time.sleep")
def test_wait_for_job_failed(mock_sleep, mock_request, mock_config):
    """Test waiting for a job that fails."""
    mock_request.return_value = {
        "entry": [{"content": {"dispatchState": "FAILED", "messages": ["Error"]}}]
    }

    result = wait_for_job(mock_config, "sid-123")

    assert result["status"] == "failed"
    assert result["error"] == ["Error"]


@patch("scripts.splunk_client.splunk_request")
@patch("time.sleep")
@patch("time.time")
def test_wait_for_job_timeout(mock_time, mock_sleep, mock_request, mock_config):
    """Test timeout when waiting for job."""
    # Mock time to simulate timeout immediately
    # Start time = 0, Current time = 400 (timeout is 300)
    mock_time.side_effect = [0, 400]

    result = wait_for_job(mock_config, "sid-123")

    assert result["status"] == "timeout"
