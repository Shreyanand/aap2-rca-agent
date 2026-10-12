"""Callable deterministic job-analysis pipeline (steps 1–4)."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

import jsonschema

from rca.config import Config

from .bastion_resolver import (
    prepare_bastion_for_fetch,
    resolve_bastion_for_job,
    resolve_remote_log_dir,
)
from .correlator import build_correlation_timeline, fetch_correlated_logs
from .github_fetcher import GitHubAnalyzer, GitHubAuthenticationError, GitHubClient
from .job_parser import parse_job_log
from .log_fetcher import fetch_job_log

logger = logging.getLogger(__name__)

_SUMMARY_SCHEMA: dict[str, Any] = json.loads(
    files("rca")
    .joinpath("schemas")
    .joinpath("summary.schema.json")
    .read_text(encoding="utf-8")
)

_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "secrets",
        (
            "authentication failed",
            "credential",
            "permission denied",
            "secret",
            "token",
            "unauthorized",
        ),
    ),
    (
        "resource",
        (
            "capacity",
            "evicted",
            "out of memory",
            "quota",
            "resource exhausted",
            "too many open files",
        ),
    ),
    (
        "network",
        (
            "connection refused",
            "connection reset",
            "dns",
            "name resolution",
            "network",
            "nodename nor servname",
            "timed out",
            "timeout",
            "unreachable",
        ),
    ),
    (
        "cloud_api",
        (
            "api error",
            "aws",
            "azure",
            "gcp",
            "rate limit",
            "throttl",
        ),
    ),
    (
        "dependency",
        (
            "collection",
            "dependency",
            "image pull",
            "module not found",
            "package",
            "requirements",
        ),
    ),
    (
        "configuration",
        (
            "configuration",
            "invalid data passed to 'loop'",
            "lookup",
            "missing variable",
            "syntax error",
            "template",
            "undefined variable",
            "wantlist",
        ),
    ),
    (
        "infrastructure",
        (
            "crashloop",
            "node",
            "pod",
            "openshift",
            "cluster",
        ),
    ),
    (
        "application_bug",
        (
            "command failed",
            "failed",
            "non-zero",
            "task failed",
        ),
    ),
)


class AnalysisPipelineError(RuntimeError):
    """A deterministic analysis step could not complete."""


@dataclass(frozen=True)
class AnalysisArtifacts:
    job_id: str
    analysis_dir: Path
    job_context: dict[str, Any]
    splunk_logs: dict[str, Any]
    correlation: dict[str, Any]
    github_fetch_history: dict[str, Any]


def get_step_name(step: int) -> str:
    return {
        1: "job_context",
        2: "splunk_logs",
        3: "correlation",
        4: "github_fetch_history",
        5: "analysis_summary",
    }.get(step, f"step{step}")


def save_step(analysis_dir: Path, step: int, data: dict[str, Any]) -> Path:
    """Write one analysis artifact as JSON."""
    analysis_dir.mkdir(parents=True, exist_ok=True)
    output_path = analysis_dir / f"step{step}_{get_step_name(step)}.json"
    temporary_path = output_path.with_name(f".{output_path.name}.tmp")
    try:
        with temporary_path.open("w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False, default=str)
        temporary_path.replace(output_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return output_path


def load_step(analysis_dir: Path, step: int) -> dict[str, Any] | None:
    path = analysis_dir / f"step{step}_{get_step_name(step)}.json"
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any, limit: int | None = None) -> str:
    result = value if isinstance(value, str) else str(value or "")
    result = " ".join(result.split())
    return result[:limit] if limit is not None else result


def _root_cause_category(error_message: str) -> str:
    normalized = error_message.lower()
    for category, patterns in _CATEGORY_RULES:
        if any(pattern in normalized for pattern in patterns):
            return category
    return "unknown"


def _root_cause_confidence(
    *,
    has_failed_task: bool,
    splunk_error_count: int,
    correlation: dict[str, Any],
) -> str:
    correlation_details = _mapping(correlation.get("correlation"))
    overlap = _mapping(correlation_details.get("time_overlap")).get("overlap_confirmed")
    if has_failed_task and splunk_error_count and overlap is True:
        return "high"
    if has_failed_task:
        return "medium"
    return "low"


def _summary_correlation(
    job_context: dict[str, Any], correlation: dict[str, Any]
) -> dict[str, Any]:
    details = _mapping(correlation.get("correlation"))
    identifiers = _mapping(details.get("identifiers"))
    overlap = _mapping(details.get("time_overlap"))
    matching_pods = details.get("matching_pods")
    pod_name = ""
    if isinstance(matching_pods, list) and matching_pods:
        pod_name = _text(matching_pods[0])

    normalized_identifiers = {
        key: _text(identifiers.get(key))
        for key in ("guid", "namespace", "pod_name")
        if _text(identifiers.get(key))
    }
    if pod_name:
        normalized_identifiers["pod_name"] = pod_name

    time_window = _mapping(job_context.get("time_window"))
    normalized_overlap = {
        "aap_job_start": _text(time_window.get("started")),
        "aap_job_end": _text(time_window.get("finished")),
        "splunk_first_error": _text(overlap.get("splunk_first_log")),
        "splunk_last_error": _text(overlap.get("splunk_last_log")),
        "overlap_confirmed": overlap.get("overlap_confirmed") is True,
    }
    normalized_overlap = {
        key: value for key, value in normalized_overlap.items() if value != ""
    }

    return {
        "method": _text(details.get("method")) or "none",
        "identifiers": normalized_identifiers,
        "time_overlap": normalized_overlap,
    }


def _github_evidence(github_fetch_history: dict[str, Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    github_fetches = github_fetch_history.get("github_fetches")
    if isinstance(github_fetches, list):
        for item in github_fetches:
            fetch = _mapping(item)
            location = _mapping(_mapping(fetch.get("location")).get("parsed"))
            fetched_workload = _mapping(fetch.get("fetched_workload"))
            failed_task_code = _mapping(fetched_workload.get("failed_task_code"))
            owner = _text(location.get("owner"))
            repo = _text(location.get("repo"))
            file_path = _text(location.get("file_path"))
            line_number = location.get("line_number")
            if not all((owner, repo, file_path, failed_task_code.get("content"))):
                continue
            evidence.append(
                {
                    "source": "agnosticd_code",
                    "timestamp": "",
                    "message": "Workload code for the failed task was fetched.",
                    "github_path": f"{owner}/{repo}:{file_path}:{line_number}",
                }
            )

    config_sources = [_mapping(github_fetch_history.get("fetched_configs"))]
    if isinstance(github_fetches, list):
        config_sources.extend(
            _mapping(_mapping(item).get("fetched_configs"))
            for item in github_fetches
            if isinstance(item, dict)
        )
    seen_config_paths: set[str] = set()
    for configs in config_sources:
        for result in configs.values():
            fetched = _mapping(result)
            path = _text(fetched.get("path"))
            if not path or not fetched.get("content") or path in seen_config_paths:
                continue
            seen_config_paths.add(path)
            evidence.append(
                {
                    "source": "agnosticv_config",
                    "timestamp": "",
                    "message": "Configuration context for the job was fetched.",
                    "github_path": f"rhpds/agnosticv:{path}",
                }
            )
    return evidence


def _summary_evidence(
    job_context: dict[str, Any], correlation: dict[str, Any]
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    failed_tasks = job_context.get("failed_tasks")
    if isinstance(failed_tasks, list) and failed_tasks:
        for task_value in failed_tasks:
            task = _mapping(task_value)
            message = _text(task.get("error_message"), 500)
            if not message:
                message = f"Task '{_text(task.get('task'))}' failed."
            evidence.append(
                {
                    "source": "aap_job",
                    "timestamp": _text(task.get("timestamp")),
                    "message": message,
                }
            )
    else:
        evidence.append(
            {
                "source": "aap_job",
                "timestamp": _text(_mapping(job_context.get("time_window")).get("finished")),
                "message": (
                    f"Job status was '{_text(job_context.get('status')) or 'unknown'}'; "
                    "no failed-task details were recorded."
                ),
            }
        )

    timeline_events = correlation.get("timeline_events")
    if isinstance(timeline_events, list):
        for event_value in timeline_events:
            event = _mapping(event_value)
            if event.get("source") != "splunk_ocp":
                continue
            details = _mapping(event.get("details"))
            message = _text(details.get("message") or event.get("summary"), 500)
            if not message:
                continue
            evidence.append(
                {
                    "source": "splunk_ocp",
                    "timestamp": _text(event.get("timestamp")),
                    "message": message,
                }
            )
    return evidence


def _recommendation(category: str, summary: str, github_path: str | None) -> dict[str, Any]:
    actions = {
        "application_bug": "Correct the failing workload task and add a regression test.",
        "infrastructure": "Investigate the affected platform component and retry after recovery.",
        "configuration": "Correct the task input or configuration value that produced the failure.",
        "dependency": "Verify and restore the required dependency or collection.",
        "network": "Verify connectivity, DNS resolution, and required network paths.",
        "resource": "Increase or free the required resource capacity before retrying.",
        "cloud_api": "Verify cloud provider health, authentication, and API quotas.",
        "secrets": "Verify the referenced credential and its secret configuration.",
        "unknown": "Reproduce the failure with verbose logging and inspect the failed task.",
    }
    recommendation: dict[str, Any] = {
        "priority": "medium",
        "action": actions[category],
        "details": summary,
    }
    if github_path:
        recommendation["github_path"] = github_path
        recommendation["file"] = github_path.split(":", 1)[1].rsplit(":", 1)[0]
    return recommendation


def build_analysis_summary(
    artifacts: AnalysisArtifacts, *, agent_review: str | None = None
) -> dict[str, Any]:
    """Build a schema-valid Step 5 summary from deterministic Step 1–4 data."""
    job_context = artifacts.job_context
    splunk_logs = artifacts.splunk_logs
    correlation = artifacts.correlation
    github_fetch_history = artifacts.github_fetch_history

    failed_tasks = job_context.get("failed_tasks")
    failed_tasks = failed_tasks if isinstance(failed_tasks, list) else []
    primary_task = _mapping(failed_tasks[0]) if failed_tasks else {}
    error_message = _text(primary_task.get("error_message"), 500)
    category = _root_cause_category(error_message)
    task_name = _text(primary_task.get("task"))
    if task_name:
        summary = f"Task '{task_name}' failed: {error_message or 'no error message was recorded'}"
    else:
        summary = f"Job failed with status '{_text(job_context.get('status')) or 'unknown'}'."

    error_logs = splunk_logs.get("error_logs")
    confidence = _root_cause_confidence(
        has_failed_task=bool(failed_tasks),
        splunk_error_count=len(error_logs) if isinstance(error_logs, list) else 0,
        correlation=correlation,
    )
    evidence = _summary_evidence(job_context, correlation)
    github_evidence = _github_evidence(github_fetch_history)
    evidence.extend(github_evidence)
    github_path = github_evidence[0].get("github_path") if github_evidence else None

    contributing_factors: list[str] = []
    if splunk_logs.get("skipped") or splunk_logs.get("errors"):
        reason = _text(
            splunk_logs.get("reason")
            or "; ".join(str(error) for error in splunk_logs.get("errors", [])),
            300,
        )
        contributing_factors.append(f"Splunk evidence was unavailable: {reason or 'query failed'}")
    if github_fetch_history.get("skipped"):
        contributing_factors.append(
            f"GitHub context was unavailable: {_text(github_fetch_history.get('reason'), 300)}"
        )
    correlation_details = _mapping(correlation.get("correlation"))
    if _text(correlation_details.get("confidence")) == "low":
        contributing_factors.append("AAP and Splunk evidence were not strongly correlated.")

    summary_document: dict[str, Any] = {
        "job_id": artifacts.job_id,
        "root_cause": {
            "summary": summary,
            "category": category,
            "confidence": confidence,
        },
        "correlation": _summary_correlation(job_context, correlation),
        "evidence": evidence,
        "recommendations": [_recommendation(category, summary, github_path)],
    }
    analyzed_at = _text(correlation.get("generated_at")) or _text(
        _mapping(job_context.get("time_window")).get("finished")
    )
    if analyzed_at:
        summary_document["analyzed_at"] = analyzed_at
    if contributing_factors:
        summary_document["contributing_factors"] = contributing_factors
    review = _text(agent_review, 4000)
    if review:
        summary_document["agent_review"] = review

    jsonschema.validate(summary_document, _SUMMARY_SCHEMA)
    return summary_document


def write_analysis_summary(
    artifacts: AnalysisArtifacts, *, agent_review: str | None = None
) -> dict[str, Any]:
    """Deterministically build and persist the Step 5 summary artifact."""
    summary = build_analysis_summary(artifacts, agent_review=agent_review)
    save_step(artifacts.analysis_dir, 5, summary)
    return summary


def _resolve_job_log(
    *,
    config: Config,
    job_id: str | None,
    job_log: str | Path | None,
    fetch: bool,
    db_pool: Any | None = None,
) -> tuple[Path, str | None]:
    if fetch and not job_id:
        raise AnalysisPipelineError("--fetch requires --job-id (it has no effect with --job-log)")

    if job_log is not None:
        path = Path(job_log).expanduser()
        if not path.is_file():
            raise AnalysisPipelineError(f"Job log file not found: {path}")
        return path, job_id

    if not job_id:
        raise AnalysisPipelineError("Either --job-log or --job-id is required")

    path = config.find_job_log(job_id)
    if path:
        return path, job_id
    if not fetch:
        if config.job_logs_dir:
            raise AnalysisPipelineError(
                f"No log file found for job {job_id} in {config.job_logs_dir}; use --fetch to retrieve it"
            )
        raise AnalysisPipelineError("JOB_LOGS_DIR is not configured; use --job-log or set JOB_LOGS_DIR")
    if not config.job_logs_dir:
        raise AnalysisPipelineError("--fetch requires JOB_LOGS_DIR to be configured")

    logger.info("[Fetch] Resolving bastion and retrieving log for job_id=%s", job_id)
    try:
        if db_pool is None:
            target = resolve_bastion_for_job(config, job_id)
        else:
            target = resolve_bastion_for_job(config, job_id, db_pool=db_pool)
        prepare_bastion_for_fetch(config, target)
        remote_dir = resolve_remote_log_dir(target, config)
        fetched_files = fetch_job_log(job_id, config.job_logs_dir, target.remote_host, remote_dir)
    except (
        FileNotFoundError,
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        ValueError,
    ) as exc:
        raise AnalysisPipelineError(f"Failed to fetch job log: {exc}") from exc

    path = config.find_job_log(job_id)
    if path is None:
        raise AnalysisPipelineError(
            f"Log fetch returned {len(fetched_files)} file(s), but no job_{job_id} log exists in "
            f"{config.job_logs_dir}"
        )
    return path, job_id


def run_analysis(
    *,
    config: Config,
    job_id: str | None = None,
    job_log: str | Path | None = None,
    fetch: bool = False,
    db_pool: Any | None = None,
) -> AnalysisArtifacts:
    """Run steps 1–4 and return their artifacts for the caller."""
    job_log_path, requested_job_id = _resolve_job_log(
        config=config,
        job_id=job_id,
        job_log=job_log,
        fetch=fetch,
        db_pool=db_pool,
    )
    try:
        job_context = parse_job_log(job_log_path)
    except Exception as exc:
        raise AnalysisPipelineError(f"Could not parse job log {job_log_path}: {exc}") from exc

    parsed_job_id = str(requested_job_id or job_context.get("job_id") or "unknown")
    analysis_dir = config.analysis_dir / parsed_job_id
    save_step(analysis_dir, 1, job_context)

    splunk_errors = config.validate_splunk()
    if splunk_errors:
        splunk_logs: dict[str, Any] = {
            "job_id": parsed_job_id,
            "ocp_logs": [],
            "error_logs": [],
            "pods_found": [],
            "skipped": True,
            "reason": "; ".join(splunk_errors),
        }
    else:
        try:
            splunk_logs = fetch_correlated_logs(config, job_context)
        except Exception as exc:
            logger.warning("[Step 2] Splunk query failed for job_id=%s: %s", parsed_job_id, exc)
            splunk_logs = {
                "job_id": parsed_job_id,
                "ocp_logs": [],
                "error_logs": [],
                "pods_found": [],
                "errors": [str(exc)],
            }
    save_step(analysis_dir, 2, splunk_logs)

    correlation = build_correlation_timeline(job_context, splunk_logs)
    save_step(analysis_dir, 3, correlation)

    if not config.github_token or config.github_token == "your-github-token":
        github_fetch_history: dict[str, Any] = {
            "job_id": parsed_job_id,
            "skipped": True,
            "reason": "GITHUB_TOKEN is not configured",
            "github_fetches": [],
            "fetched_configs": {},
        }
    else:
        try:
            github_fetch_history = GitHubAnalyzer(
                parsed_job_id,
                analysis_dir,
                GitHubClient(config.github_token),
            ).run()
        except GitHubAuthenticationError as exc:
            logger.warning("[Step 4] GitHub authentication failed for job_id=%s: %s", parsed_job_id, exc)
            github_fetch_history = {
                "job_id": parsed_job_id,
                "skipped": True,
                "reason": f"GitHub API authentication failed: {exc}",
                "github_fetches": [],
                "fetched_configs": {},
            }
        except Exception as exc:
            raise AnalysisPipelineError(f"Error fetching GitHub files: {exc}") from exc
    save_step(analysis_dir, 4, github_fetch_history)

    return AnalysisArtifacts(
        job_id=parsed_job_id,
        analysis_dir=analysis_dir,
        job_context=job_context,
        splunk_logs=splunk_logs,
        correlation=correlation,
        github_fetch_history=github_fetch_history,
    )
