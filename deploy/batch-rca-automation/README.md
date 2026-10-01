# Batch RCA Automation

The OpenShift CronJob continues to run
[`batch_rca_headless.sh`](batch_rca_headless.sh). The script retains the
existing Claude Code orchestration and uses the installed `rca.batch` package
modules for source-job queries, filtering, known issues, and report storage.

The image installs runtime dependencies from the repository `pyproject.toml`.
Batch helper modules are imported from the installed package rather than
copied as a second Python source tree. The on-disk Skill is still installed by
the init container for the current Claude CLI flow.

## Development and tests

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest
```

PostgreSQL integration tests are under `tests/integration/` and can be run
with `tests/run_integration_tests.sh`.

See the [root README](../../README.md#performance) for the existing performance
baseline and [output format](../../README.md#output).
