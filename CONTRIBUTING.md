# Contributing

Thanks for your interest in improving the AAP RCA agent. This repo has two
independent pieces of code, each with its own dependencies and tests:

- [`skills/root-cause-analysis/`](skills/root-cause-analysis/README.md) — the
  Claude Code skill that analyzes a single failed job.
- [`deploy/batch-rca-automation/`](deploy/batch-rca-automation/README.md) —
  the scripts and CronJob that run the skill across many jobs in production.

## Setting up a dev environment

Each component manages its own virtual environment:

```bash
# Skill
cd skills/root-cause-analysis
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Batch automation
cd deploy/batch-rca-automation
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Running tests

```bash
# Skill unit tests
cd skills/root-cause-analysis
.venv/bin/pip install -r requirements-dev.txt  # if present
.venv/bin/python -m pytest tests/

# Batch automation tests (includes integration tests against a test DB)
cd deploy/batch-rca-automation
.venv/bin/pip install -r tests/requirements-dev.txt
.venv/bin/python -m pytest tests/
# or, for the Postgres-backed integration suite:
tests/run_integration_tests.sh
```

## Making changes

- Keep changes to `skills/root-cause-analysis/` and
  `deploy/batch-rca-automation/` scoped to one component per PR where
  possible — they have separate dependency lists and test suites.
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
