"""Configuration management for splunk-log-analysis."""

import os
from dataclasses import dataclass
from pathlib import Path

from common.config import load_database_config


def _none_if_empty(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value if value else None


@dataclass
class SplunkConfig:
    host: str
    username: str
    password: str
    index: str | None = None
    verify_ssl: bool = True
    # Legacy token-based auth (optional, username/password preferred)
    token: str | None = None
    # Additional indices for OCP logs
    ocp_app_index: str | None = None
    ocp_infra_index: str | None = None

    @property
    def auth_method(self) -> str:
        """Return the authentication method being used."""
        if self.username and self.password:
            return "basic"
        elif self.token:
            return "token"
        return "none"


@dataclass
class Config:
    splunk: SplunkConfig
    analysis_dir: Path
    job_logs_dir: Path | None = None
    github_token: str | None = None
    remote_host: str = ""
    remote_log_dir: str = ""
    jumpbox_uri: str = ""
    # Database configuration for per-job bastion lookup
    source_db_host: str = ""
    source_db_port: int = 5432
    source_db_name: str = ""
    source_db_user: str = ""
    source_db_password: str = ""
    source_db_table: str = ""
    source_db_bastion_table: str = ""
    # SSH configuration
    ssh_jumpbox_alias: str = ""
    bastion_ssh_user: str = ""

    @classmethod
    def from_env(cls, base_dir: Path | None = None) -> "Config":
        """Load configuration from the shared project environment."""
        if base_dir is None:
            base_dir = Path(__file__).parent.parent

        db_config = load_database_config(
            defaults={
                # Bastion lookup is opt-in; do not treat an omitted host as localhost.
                "host": "",
                "source_table": "aap2_events",
                "bastion_table": "aap2_user_url",
            }
        )

        splunk = SplunkConfig(
            host=os.environ.get("SPLUNK_HOST", ""),
            username=os.environ.get("SPLUNK_USERNAME", ""),
            password=os.environ.get("SPLUNK_PASSWORD", ""),
            index=_none_if_empty(os.environ.get("SPLUNK_INDEX")),
            verify_ssl=os.environ.get("SPLUNK_VERIFY_SSL", "false").lower() == "true",
            token=os.environ.get("SPLUNK_TOKEN"),
            ocp_app_index=_none_if_empty(os.environ.get("SPLUNK_OCP_APP_INDEX")),
            ocp_infra_index=_none_if_empty(os.environ.get("SPLUNK_OCP_INFRA_INDEX")),
        )

        job_logs_dir_str = os.environ.get("JOB_LOGS_DIR", "")
        job_logs_dir = Path(job_logs_dir_str) if job_logs_dir_str else None

        return cls(
            splunk=splunk,
            analysis_dir=base_dir / ".analysis",
            job_logs_dir=job_logs_dir,
            github_token=os.environ.get("GITHUB_TOKEN"),
            remote_host=os.environ.get("REMOTE_HOST", ""),
            remote_log_dir=os.environ.get("REMOTE_DIR", ""),
            jumpbox_uri=os.environ.get("JUMPBOX_URI", ""),
            source_db_host=db_config["host"],
            source_db_port=db_config["port"],
            source_db_name=db_config["name"],
            source_db_user=db_config["user"],
            source_db_password=db_config["password"],
            source_db_table=db_config["source_table"],
            source_db_bastion_table=db_config["bastion_table"],
            ssh_jumpbox_alias=os.environ.get("SSH_JUMPBOX_ALIAS", "rca-jumpbox"),
            bastion_ssh_user=os.environ.get("BASTION_SSH_USER", ""),
        )

    def find_job_log(self, job_id: str) -> Path | None:
        """Find a job log file by job ID in the configured directory."""
        if not self.job_logs_dir or not self.job_logs_dir.exists():
            return None

        # Search for files matching job_<id>.*
        patterns = [
            f"job_{job_id}.json",
            f"job_{job_id}.json.gz",
            f"job_{job_id}.json.gz.transform-processed",
            f"job_{job_id}.json.transform-processed",
        ]

        for pattern in patterns:
            path = self.job_logs_dir / pattern
            if path.exists():
                return path

        # Fallback: glob search for any file starting with job_<id>
        matches = list(self.job_logs_dir.glob(f"job_{job_id}.*"))
        if matches:
            return matches[0]

        return None

    def validate_splunk(self) -> list[str]:
        """Validate Splunk configuration, return list of errors."""
        errors = []
        if not self.splunk.host:
            errors.append("SPLUNK_HOST is required")
        if self.splunk.auth_method == "none":
            errors.append("SPLUNK_USERNAME/SPLUNK_PASSWORD or SPLUNK_TOKEN is required")
        return errors

    def validate_github(self) -> list[str]:
        """Validate GitHub configuration, return list of errors."""
        errors = []
        if not self.github_token or self.github_token == "your-github-token":
            errors.append("GITHUB_TOKEN is required")
        return errors

    def has_source_db(self) -> bool:
        """Check if source database is configured."""
        return bool(
            self.source_db_host
            and self.source_db_name
            and self.source_db_user
            and self.source_db_password
        )
