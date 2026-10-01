#!/usr/bin/env python3
"""Compatibility shim to the installed package CLI for the on-disk skill."""

from rca.analysis.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
