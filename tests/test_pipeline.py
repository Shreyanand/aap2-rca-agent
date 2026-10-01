"""Tests for the deterministic analysis pipeline entry conditions."""

import pytest

from rca.analysis.pipeline import AnalysisPipelineError, run_analysis
from rca.config import Config


def test_fetch_with_job_log_requires_job_id(tmp_path) -> None:
    job_log = tmp_path / "job.json"
    job_log.write_text("{}", encoding="utf-8")
    config = Config.from_env(environment={"RCA_STATE_DIR": str(tmp_path)})

    with pytest.raises(AnalysisPipelineError, match="--fetch requires --job-id"):
        run_analysis(config=config, job_log=job_log, fetch=True)
