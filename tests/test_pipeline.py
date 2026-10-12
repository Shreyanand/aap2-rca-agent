"""Tests for the deterministic analysis pipeline entry conditions."""

import json

import pytest

from rca.analysis.github_fetcher import GitHubAuthenticationError
from rca.analysis.pipeline import (
    AnalysisArtifacts,
    AnalysisPipelineError,
    run_analysis,
    write_analysis_summary,
)
from rca.config import Config


def test_fetch_with_job_log_requires_job_id(tmp_path) -> None:
    job_log = tmp_path / "job.json"
    job_log.write_text("{}", encoding="utf-8")
    config = Config.from_env(environment={"RCA_STATE_DIR": str(tmp_path)})

    with pytest.raises(AnalysisPipelineError, match="--fetch requires --job-id"):
        run_analysis(config=config, job_log=job_log, fetch=True)


def test_github_authentication_failure_skips_step_four(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_log = tmp_path / "job.json"
    job_log.write_text("{}", encoding="utf-8")
    config = Config.from_env(
        environment={
            "RCA_STATE_DIR": str(tmp_path),
            "GITHUB_TOKEN": "invalid-token",
        }
    )

    class FailingAnalyzer:
        def __init__(self, *_args, **_kwargs):
            pass

        def run(self):
            raise GitHubAuthenticationError("GitHub API authentication failed")

    monkeypatch.setattr("rca.analysis.pipeline.GitHubAnalyzer", FailingAnalyzer)

    artifacts = run_analysis(config=config, job_log=job_log)

    assert artifacts.github_fetch_history["skipped"] is True
    assert "authentication failed" in artifacts.github_fetch_history["reason"]


def test_step5_summary_is_deterministic_and_replaces_stale_output(tmp_path) -> None:
    artifacts = AnalysisArtifacts(
        job_id="101",
        analysis_dir=tmp_path,
        job_context={
            "job_id": "101",
            "status": "failed",
            "time_window": {"finished": "2026-10-09T17:09:51Z"},
            "failed_tasks": [
                {
                    "task": "Deploy workloads",
                    "timestamp": "2026-10-09T17:09:51Z",
                    "error_message": "Invalid data passed to 'loop'",
                }
            ],
        },
        splunk_logs={"error_logs": []},
        correlation={
            "generated_at": "2026-10-09T17:38:54Z",
            "correlation": {
                "method": "identifier_match",
                "confidence": "low",
                "identifiers": {"guid": "abc12", "namespace": None},
                "time_overlap": {"overlap_confirmed": False},
            },
            "timeline_events": [],
        },
        github_fetch_history={
            "github_fetches": [
                {
                    "location": {
                        "parsed": {
                            "owner": "example",
                            "repo": "workloads",
                            "file_path": "roles/example/tasks/main.yml",
                            "line_number": 42,
                        }
                    },
                    "fetched_workload": {
                        "failed_task_code": {"content": "- include_tasks: workloads.yml"}
                    },
                }
            ]
        },
    )
    summary_path = tmp_path / "step5_analysis_summary.json"
    summary_path.write_text('{"root_cause": {"summary": "stale"}}', encoding="utf-8")

    first = write_analysis_summary(artifacts)
    first_json = summary_path.read_text(encoding="utf-8")
    second = write_analysis_summary(artifacts)

    assert first == second
    assert first_json == summary_path.read_text(encoding="utf-8")
    assert first["root_cause"]["category"] == "configuration"
    assert first["root_cause"]["summary"] == "Task 'Deploy workloads' failed: Invalid data passed to 'loop'"
    assert first["evidence"][0]["source"] == "aap_job"
    assert first["evidence"][-1]["github_path"] == "example/workloads:roles/example/tasks/main.yml:42"
    assert json.loads(first_json) == first
