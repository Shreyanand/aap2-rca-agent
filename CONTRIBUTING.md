# Contributing

Thanks for your interest in improving the AAP RCA agent. The root-cause-analysis
skill and batch automation share runtime dependencies and Python helpers:

- [`skills/root-cause-analysis/`](skills/root-cause-analysis/README.md) — the
  Claude Code skill that analyzes a single failed job.
- [`deploy/batch-rca-automation/`](deploy/batch-rca-automation/README.md) —
  the scripts and CronJob that run the skill across many jobs in production.

## Setting up a dev environment

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

## Running tests

```bash
.venv/bin/python -m pytest
```

The root pytest configuration runs skill unit tests, shared-module tests, and
batch PostgreSQL integration tests. Database-dependent tests skip when the
test database is unavailable. To start the provided database and run those
tests:

```bash
deploy/batch-rca-automation/tests/run_integration_tests.sh
```

## Making changes

- Keep changes scoped to the relevant skill or batch automation area where
  possible. Shared dependencies live in the root `requirements.txt`, and
  reusable Python helpers live in `common/`.
- Add runtime dependencies to the root `requirements.txt` and development/test
  dependencies to `requirements-dev.txt`.
- If you change the shape of any `.analysis/<job-id>/stepN_*.json` output,
  update the corresponding JSON schema in `skills/root-cause-analysis/schemas/`
  and both READMEs that document the file table.
- If you change Helm values or CronJob behavior, update
  `deploy/helm/values.example.yaml` and call out the new/changed keys in your
  PR description.

## Reporting issues

Open a GitHub issue with:
- What you expected to happen vs. what happened.
- The command you ran (`cli.py analyze ...`, Helm install, etc.).
- Relevant logs — redact any GUIDs, hostnames, or credentials first.

## Secrets

Never commit `.claude/settings.local.json`, `.claude/mcp.json`, `.env` files,
or anything under `.analysis/` — these can contain tokens, SSH details, or
job data. They're excluded via `.gitignore`; double-check `git status` before
committing if you've been debugging locally.
