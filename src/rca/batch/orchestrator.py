"""Compatibility entry point for the legacy shell batch runner.

The Python batch orchestrator is introduced separately; keep this console
script available while the existing headless shell flow uses the package's
installed database and analysis modules.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the installed legacy batch RCA coordinator"
    )
    parser.add_argument("--since", help="Only include events after this timestamp")
    parser.add_argument("--limit", type=int, help="Maximum number of jobs to query")
    parser.add_argument(
        "--no-pre-filter", action="store_true", help="Skip known-issue filtering"
    )
    parser.parse_known_args()

    script = os.environ.get("RCA_LEGACY_BATCH_SCRIPT") or shutil.which("batch_rca_headless.sh")
    if not script:
        candidate = Path.cwd() / "batch_rca_headless.sh"
        script = str(candidate) if candidate.is_file() else None
    if not script or not Path(script).is_file():
        print(
            "Legacy batch runner not found. Set RCA_LEGACY_BATCH_SCRIPT to "
            "batch_rca_headless.sh.",
            file=sys.stderr,
        )
        return 1
    return subprocess.run(["bash", script, *sys.argv[1:]], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
