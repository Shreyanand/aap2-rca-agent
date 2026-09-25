# aap2-rca-agent

The root-cause-analysis skill and batch automation share one Python dependency
set and the source modules in `common/`. The skill remains discoverable through
`skills/root-cause-analysis/SKILL.md`; its scripts and schemas stay in that
skill-shaped directory.

## Development setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

The root pytest configuration runs the skill unit tests, shared-module tests,
and the batch PostgreSQL integration tests. PostgreSQL tests skip if the test
database is not running. To start the provided test database and run those
tests:

```bash
deploy/batch-rca-automation/tests/run_integration_tests.sh
```

Configuration can be supplied through environment variables or a repository-
root `.env` file. Do not commit credentials.
