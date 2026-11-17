"""Print the classified GEDCOM round-trip difference report as Markdown.

Usage::

    python scripts/gedcom_roundtrip_report.py

The script exports ``tests/fixtures/gedcom_roundtrip/MergeTest.json`` to
GEDCOM, imports the file into a new empty project and compares the two
Stable_Views (``tests/test_gedcom_roundtrip/comparison.py``). The report lists
every catalog entry per Difference_Class (A missing from the GEDCOM output,
B lost or changed by the importer, C not representable in GEDCOM 5.5.1 without
extensions, D Släktbusken-only data), with its catalog id, description, status
and the number of differences that the MergeTest round trip produced.
Differences with status ``fixed`` must be zero; the script exits with 1 when
one remains or when a difference has no catalog entry.
"""

from __future__ import annotations

import os
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from slaktbusken.gedcom.exporter import GEDCOMExporter  # noqa: E402
from slaktbusken.services.import_service import ImportService  # noqa: E402
from slaktbusken.services.project_service import ProjectService  # noqa: E402
from slaktbusken.services.report_service import ReportService  # noqa: E402
from slaktbusken.services.validation_service import ValidationService  # noqa: E402
from tests.test_gedcom_roundtrip.comparison import (  # noqa: E402
    UncatalogedDifference,
    blocking,
    compare_sections,
)
from tests.test_gedcom_roundtrip.difference_catalog import (  # noqa: E402
    CATALOG,
    DIFFERENCE_CLASSES,
    code_number,
)
from tests.test_gedcom_roundtrip.fixtures import load_mergetest  # noqa: E402
from tests.test_gedcom_roundtrip.stable_view import stable_view  # noqa: E402

CLASS_TITLES = {
    "A": "A. Missing from the GEDCOM output",
    "B": "B. Lost or changed by the importer",
    "C": "C. Not representable in GEDCOM 5.5.1 without extensions",
    "D": "D. Släktbusken-only data that is not exported",
}


def round_trip_differences():
    """Return ``(original, imported, differences)`` for the MergeTest fixture."""
    original = load_mergetest()
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        gedcom = root / "MergeTest.ged"
        GEDCOMExporter().export(original, gedcom)
        service = ProjectService()
        service.create_project("Rundresa", root / "project")
        ImportService(ValidationService(), ReportService()).run(
            service.data, gedcom, service.project_path.parent, service
        )
        imported = service.data
        differences = compare_sections(stable_view(original), stable_view(imported))
    return original, imported, differences


def render(original, imported, differences) -> str:
    counts = Counter(d.code for d in differences)
    lines: list[str] = ["# GEDCOM round-trip difference report", ""]
    lines.append(
        f"Fixture: `MergeTest.json` ({len(original.persons)} persons, "
        f"{len(original.families)} families, {len(original.events)} events). "
        f"After export and import: {len(imported.persons)} persons, "
        f"{len(imported.families)} families, {len(imported.events)} events."
    )
    lines.append("")
    unclassified = [d for d in differences if d.code not in CATALOG]
    remaining = blocking(differences)
    lines.append(
        f"Differences found: {len(differences)}. Without catalog entry: "
        f"{len(unclassified)}. With status `fixed` (must be 0): {len(remaining)}."
    )
    lines.append("")
    for letter in DIFFERENCE_CLASSES:
        entries = sorted(
            (e for e in CATALOG.values() if e.root_class == letter),
            key=lambda e: code_number(e.code),
        )
        found = sum(counts[e.code] for e in entries)
        lines.append(f"## {CLASS_TITLES[letter]}")
        lines.append("")
        lines.append(f"{len(entries)} catalog entries, {found} differences in this round trip.")
        lines.append("")
        lines.append("| Id | Class | Status | Requirement | Found | Description |")
        lines.append("|---|---|---|---|---|---|")
        for e in entries:
            description = e.description.replace("|", "\\|")
            lines.append(
                f"| {e.code} | {e.difference_class} | {e.status} | {e.requirement} "
                f"| {counts[e.code]} | {description} |"
            )
        lines.append("")
    if unclassified:
        lines.append("## Differences without catalog entry")
        lines.append("")
        lines.extend(f"- {d.describe()}" for d in unclassified)
        lines.append("")
    if remaining:
        lines.append("## Differences with status `fixed`")
        lines.append("")
        lines.extend(f"- {d.describe()}" for d in remaining)
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    original, imported, differences = round_trip_differences()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(render(original, imported, differences))
    if any(d.code not in CATALOG for d in differences) or blocking(differences):
        return 1
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except UncatalogedDifference as error:  # pragma: no cover - defensive
        print(error)
        code = 1
    sys.stdout.flush()
    os._exit(code)  # skip the Qt shutdown, which can crash on exit
