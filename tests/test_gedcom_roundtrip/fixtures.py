"""Loader for the GEDCOM round-trip fixtures (fictive persons only)."""

from __future__ import annotations

from pathlib import Path

from slaktbusken.model.project import ProjectData
from slaktbusken.persistence.serialization import deserialize

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "gedcom_roundtrip"

MERGETEST_JSON = "MergeTest.json"
EXPORTTEST_GED = "exporttest.ged"
EXPORTTEST_JSON = "exporttest.json"

REQUIRED_FIXTURES: tuple[str, ...] = (MERGETEST_JSON, EXPORTTEST_GED, EXPORTTEST_JSON)


def missing_fixtures() -> list[Path]:
    """Return the paths of required fixture files that do not exist."""
    return [FIXTURE_DIR / n for n in REQUIRED_FIXTURES if not (FIXTURE_DIR / n).is_file()]


def mergetest_path() -> Path:
    return FIXTURE_DIR / MERGETEST_JSON


def exporttest_ged_path() -> Path:
    return FIXTURE_DIR / EXPORTTEST_GED


def exporttest_json_path() -> Path:
    return FIXTURE_DIR / EXPORTTEST_JSON


def load_mergetest() -> ProjectData:
    """Load MergeTest.json (uncompressed project JSON, format 0.5)."""
    return deserialize(mergetest_path().read_text(encoding="utf-8"))
