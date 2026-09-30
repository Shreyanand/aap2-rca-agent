"""Shared unit-test fixtures for the installed RCA package."""

import pytest

from rca.config import Config


@pytest.fixture
def mock_config() -> Config:
    """Configuration fixture isolated from local environment and settings files."""
    return Config.from_env(
        environment={
            "SPLUNK_HOST": "https://splunk.example.com",
            "SPLUNK_USERNAME": "user",
            "SPLUNK_PASSWORD": "password",
            "SPLUNK_INDEX": "main",
            "SPLUNK_OCP_APP_INDEX": "ocp_apps",
            "SPLUNK_VERIFY_SSL": "true",
            "RCA_STATE_DIR": ".",
        }
    )
