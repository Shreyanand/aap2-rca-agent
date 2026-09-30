"""The package batch entry point preserves the current shell runner contract."""

import sys
from pathlib import Path
from unittest.mock import Mock

from rca.batch import orchestrator


def test_batch_entrypoint_delegates_args_to_configured_runner(
    monkeypatch, tmp_path: Path
) -> None:
    script = tmp_path / "batch_rca_headless.sh"
    script.write_text("#!/bin/bash\n", encoding="utf-8")
    run = Mock(return_value=Mock(returncode=7))
    monkeypatch.setenv("RCA_LEGACY_BATCH_SCRIPT", str(script))
    monkeypatch.setattr(sys, "argv", ["rca-batch", "--limit", "5", "--no-pre-filter"])
    monkeypatch.setattr(orchestrator.subprocess, "run", run)

    assert orchestrator.main() == 7
    run.assert_called_once_with(
        ["bash", str(script), "--limit", "5", "--no-pre-filter"],
        check=False,
    )
