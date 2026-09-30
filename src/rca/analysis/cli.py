#!/usr/bin/env python3
"""Manual root-cause analysis and debugging commands."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

from rca.analysis.jumpbox_io import upload_to_jumpbox
from rca.analysis.pipeline import AnalysisPipelineError, get_step_name, run_analysis
from rca.analysis.setup import print_checks, run_checks
from rca.analysis.splunk_client import SplunkClient
from rca.config import Config

logger = logging.getLogger("rca.analysis")


def _write_json(data: Any, output: str | None = None) -> None:
    rendered = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    if output:
        Path(output).write_text(rendered + "\n", encoding="utf-8")
        print(f"Output written to: {output}")
    else:
        print(rendered)


def cmd_analyze(args: argparse.Namespace, config: Config) -> int:
    try:
        artifacts = run_analysis(
            config=config,
            job_id=args.job_id,
            job_log=args.job_log,
            fetch=args.fetch,
        )
    except AnalysisPipelineError as exc:
        logger.error("[ERROR] %s", exc)
        return 1

    job = artifacts.job_context
    correlation = artifacts.correlation.get("correlation", {})
    print("=" * 60)
    print("Analysis Complete")
    print("=" * 60)
    print(f"Job ID: {artifacts.job_id}")
    print(f"Status: {job.get('status', '')}")
    print(f"GUID: {job.get('guid', '')}")
    print(f"Namespace: {job.get('namespace', '')}")
    print(f"Correlation confidence: {correlation.get('confidence', 'none')}")
    print(f"Analysis directory: {artifacts.analysis_dir}")
    for step in range(1, 5):
        print(f"  - step{step}_{get_step_name(step)}.json")
    return 0


def cmd_parse(args: argparse.Namespace) -> int:
    from rca.analysis.job_parser import parse_job_log

    path = Path(args.job_log).expanduser()
    if not path.is_file():
        logger.error("Job log file not found: %s", path)
        return 1
    try:
        _write_json(parse_job_log(path), args.output)
    except Exception as exc:
        logger.error("Could not parse %s: %s", path, exc)
        return 1
    return 0


def cmd_query(args: argparse.Namespace, config: Config) -> int:
    errors = config.validate_splunk()
    if errors:
        logger.error("%s", "; ".join(errors))
        return 1
    try:
        results = SplunkClient(config).query(
            args.query,
            earliest=args.earliest,
            latest=args.latest,
            max_results=args.max_results,
        )
    except Exception as exc:
        logger.error("Splunk query failed: %s", exc)
        return 1
    if args.output:
        _write_json(results, args.output)
    else:
        print(f"Found {len(results)} results")
        for row in results[:10]:
            print(f"{row.get('_time', '')}: {str(row.get('_raw', ''))[:200]}")
    return 0


def cmd_setup(config: Config, as_json: bool) -> int:
    base_dir = Path(__file__).resolve().parent
    with patch.dict(os.environ, config.environment):
        results = run_checks(base_dir, Path.cwd())
    if as_json:
        print(json.dumps(results, indent=2))
    else:
        issues = print_checks(results)
        return 0 if issues == 0 else 1
    return 0 if all(item["status"] == "ok" for item in results) else 1


def cmd_status(args: argparse.Namespace, config: Config) -> int:
    analysis_dir = config.analysis_dir / args.job_id
    if not analysis_dir.is_dir():
        logger.error("No analysis found for job %s", args.job_id)
        return 1
    print(f"Analysis directory: {analysis_dir}")
    for step in range(1, 6):
        path = analysis_dir / f"step{step}_{get_step_name(step)}.json"
        marker = "x" if path.is_file() else " "
        suffix = f" ({path.stat().st_size} bytes)" if path.is_file() else ""
        print(f"  [{marker}] Step {step}: {path.name}{suffix}")
    return 0


def cmd_upload(args: argparse.Namespace, config: Config) -> int:
    success = upload_to_jumpbox(
        args.job_id,
        config.analysis_dir / args.job_id,
        config.jumpbox_uri,
        config.environment.get("CLAUDE_SESSION_ID", "unknown"),
    )
    return 0 if success else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rca-analyze",
        description="Run the deterministic RCA preparation steps or a debugging command",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser("analyze", help="Run deterministic analysis steps 1–4")
    analyze.add_argument("--job-log", help="Path to a job log file (.json or .json.gz)")
    analyze.add_argument("--job-id", help="Job ID (searches JOB_LOGS_DIR)")
    analyze.add_argument("--fetch", action="store_true", help="Fetch a missing job log over SSH")

    parse = subparsers.add_parser("parse", help="Parse a job log only")
    parse.add_argument("--job-log", required=True, help="Path to a job log file")
    parse.add_argument("--output", "-o", help="Write JSON to this file instead of stdout")

    query = subparsers.add_parser("query", help="Run an ad-hoc Splunk query")
    query.add_argument("query", help="Splunk search query")
    query.add_argument("--earliest", default="-24h")
    query.add_argument("--latest", default="now")
    query.add_argument("--max-results", type=int, default=100)
    query.add_argument("--output", "-o")

    setup = subparsers.add_parser("setup", help="Check prerequisites")
    setup.add_argument("--json", action="store_true", help="Output checks as JSON")

    status = subparsers.add_parser("status", help="Show saved analysis artifacts")
    status.add_argument("job_id")

    upload = subparsers.add_parser("upload", help="Upload analysis files to the jumpbox")
    upload.add_argument("--job-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = build_parser().parse_args(argv)
    try:
        config = Config.from_env()
    except (OSError, ValueError, SystemExit) as exc:
        logger.error("Could not load RCA configuration: %s", exc)
        return 1

    if args.command == "analyze":
        return cmd_analyze(args, config)
    if args.command == "parse":
        return cmd_parse(args)
    if args.command == "query":
        return cmd_query(args, config)
    if args.command == "setup":
        return cmd_setup(config, args.json)
    if args.command == "status":
        return cmd_status(args, config)
    if args.command == "upload":
        return cmd_upload(args, config)
    return 2


if __name__ == "__main__":
    sys.exit(main())
