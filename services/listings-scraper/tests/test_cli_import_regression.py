"""Regression tests: CLI must load without errors at import time.

These tests require no DB and no running API — they run ``scraper --help``
(and each subcommand's ``--help``) as a subprocess and assert exit code 0.
A ValidationError on a module-level Pydantic instantiation (e.g. constructing
a ``ResolvedSuburb`` with missing required fields at module load) would surface
here before any test fixtures are even created.

Regression for: dev_commands.py had a module-level
``_PADDINGTON = ResolvedSuburb(name=..., postcode=..., state=...)`` that
raised a Pydantic ValidationError because the updated ``ResolvedSuburb`` model
(post PR-1) requires ``id: int`` and ``resolved_at: datetime``. This broke
``uv run scraper --help`` and every subcommand.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_scraper(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "scraper", *args],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(_REPO_ROOT),
    )


def test_scraper_help_exits_zero():
    """``scraper --help`` must exit 0 without a traceback."""
    result = _run_scraper("--help")
    assert result.returncode == 0, (
        f"'scraper --help' exited {result.returncode}.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "Usage:" in result.stdout or "usage:" in result.stdout.lower(), (
        f"Expected usage text in output, got: {result.stdout[:200]}"
    )


@pytest.mark.parametrize("subcommand", ["suburb", "list", "jobs", "listings", "dev"])
def test_scraper_subcommand_help_exits_zero(subcommand: str) -> None:
    """Each subcommand ``--help`` must also exit 0.

    This catches any lazy imports in subcommand modules that fail at import
    time when the module is loaded for the first time via the CLI entrypoint.
    """
    result = _run_scraper(subcommand, "--help")
    assert result.returncode == 0, (
        f"'scraper {subcommand} --help' exited {result.returncode}.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
