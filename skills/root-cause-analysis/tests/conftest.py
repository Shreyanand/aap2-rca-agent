import sys
from pathlib import Path

import pytest

# Add root-cause-analysis to path for all tests in this directory
rca_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(rca_root))

from scripts.config import Config, SplunkConfig  # noqa: E402


@pytest.fixture
def mock_config():
    """Shared mock configuration fixture."""
    splunk_config = SplunkConfig(
        host="https://splunk.example.com",
        username="user",
        password="password",
        index="main",
        token=None,
        ocp_app_index="ocp_apps",
        verify_ssl=True,
    )
    return Config(splunk=splunk_config, analysis_dir=Path("."), job_logs_dir=None)
