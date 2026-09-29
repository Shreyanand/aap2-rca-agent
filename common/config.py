"""Shared project and source-database configuration loading."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATABASE_ENV_KEYS = {
    "host": ("SOURCE_DB_HOST", "localhost"),
    "port": ("SOURCE_DB_PORT", "5432"),
    "name": ("SOURCE_DB_NAME", ""),
    "user": ("SOURCE_DB_USER", ""),
    "password": ("SOURCE_DB_PASSWORD", ""),
    "source_table": ("SOURCE_DB_TABLE", ""),
    "results_table": ("SOURCE_DB_RESULT_TABLE", ""),
    "bastion_table": ("SOURCE_DB_BASTION_TABLE", ""),
}


def load_project_env(env_file: str | Path | None = None) -> None:
    """Load the repository's .env file, if present, without overriding the process env."""
    path = Path(env_file) if env_file is not None else PROJECT_ROOT / ".env"
    if path.is_file():
        load_dotenv(path)


def load_database_config(
    required: tuple[str, ...] = (),
    *,
    defaults: Mapping[str, Any] | None = None,
    env_file: str | Path | None = None,
) -> dict[str, Any]:
    """Read shared SOURCE_DB_* settings and optionally validate required fields.

    ``defaults`` allows a component to preserve its historical table/host defaults
    while keeping the environment-variable mapping in one place.
    """
    load_project_env(env_file)
    effective_defaults = {key: value for key, (_, value) in DATABASE_ENV_KEYS.items()}
    if defaults:
        unknown_keys = defaults.keys() - DATABASE_ENV_KEYS.keys()
        if unknown_keys:
            raise KeyError(f"Unknown database configuration key(s): {', '.join(sorted(unknown_keys))}")
        effective_defaults.update(defaults)

    config: dict[str, Any] = {}
    for key, (env_var, _) in DATABASE_ENV_KEYS.items():
        value = os.environ.get(env_var, effective_defaults[key])
        config[key] = int(value) if key == "port" else value

    unknown_required = set(required) - DATABASE_ENV_KEYS.keys()
    if unknown_required:
        raise KeyError(
            f"Unknown required database configuration key(s): {', '.join(sorted(unknown_required))}"
        )
    errors = [f"{DATABASE_ENV_KEYS[key][0]} is required" for key in required if not config[key]]
    if errors:
        print("\n".join(errors), file=sys.stderr)
        raise SystemExit(1)

    return config
