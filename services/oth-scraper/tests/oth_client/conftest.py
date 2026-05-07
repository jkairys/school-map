from pathlib import Path

import pytest

FIXTURES_ROOT = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture(scope="session")
def fixtures_root() -> Path:
    return FIXTURES_ROOT


@pytest.fixture(scope="session")
def oth_fixtures_dir(fixtures_root: Path) -> Path:
    return fixtures_root / "oth"


@pytest.fixture(scope="session")
def expected_payloads_dir(fixtures_root: Path) -> Path:
    return fixtures_root / "expected_payloads"
