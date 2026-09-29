# Batch RCA Automation

Automated root cause analysis system for Red Hat Demo Platform (RHDP) infrastructure failures, deployed as an OpenShift CronJob.

## Overview

This system automatically:
- Fetches failed job logs every 30 minutes from remote bastion
- Spawns parallel Claude Code agents for analysis (up to 15 jobs simultaneously)
- Generates aggregated batch reports with root cause breakdowns
- Tracks analyzed jobs to prevent duplicate processing
- Persists analysis results to PVC for long-term storage

See the [root README](../../README.md#architecture) for the architecture
diagram and full flowchart.

## How It Works

The orchestration script (`batch_rca_headless.sh`):
1. Loads environment variables from Claude settings
2. Fetches recent failed job logs via SSH
3. Filters out already-analyzed jobs
4. Spawns parallel Claude Code agents in background mode run rca skill for each of the jobs in parallel.
5. Generates aggregated batch reports
6. Updates state tracking to prevent re-processing

## Python dependencies and tests

Runtime dependencies for both the skill and this batch app are declared in the
repository-root `requirements.txt`. The Docker image installs that shared file;
there is no batch-specific Python environment or dependency manifest. From the
repository root, install development/test dependencies and run the unified test
suite with:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

The batch PostgreSQL integration tests can also be run with
`deploy/batch-rca-automation/tests/run_integration_tests.sh`.

See the [root README](../../README.md#performance) for performance metrics
and the batch/per-job output format.
