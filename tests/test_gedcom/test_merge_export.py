"""Export test for merged projects.

The GEDCOM export contains every active person and not the
Merged_Away_Person, and reports merge data in the omission counts.

Validates: Requirements 30.12
"""

from __future__ import annotations

from pathlib import Path

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.model.merge_candidate import MergeCandidate, MergeHistoryEntry
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata


def _person(pid: str, given: str, surname: str) -> Person:
    return Person(id=pid, sex="M", names=[Name(type="birth", given=given, surname=surname)])


def _merged_project() -> ProjectData:
    """Project after merging person_3 into person_1 (person_3 is retired)."""
    data = ProjectData(
        format="släktbuske-file",
        version="0.1",
        project=ProjectMetadata(title="Test"),
        persons=[
            _person("person_1", "Survivor", "Alpha"),
            _person("person_2", "Bystander", "Beta"),
        ],
        families=[],
        events=[],
        places=[],
        sources=[],
    )
    data.merge_candidates = [
        MergeCandidate(id="mergecand_1", person_1_id="person_1", person_2_id="person_2"),
    ]
    data.merge_history = [
        MergeHistoryEntry(
            id="merge_1",
            surviving_person_id="person_1",
            merged_person_id="person_3",
            merged_person_name="Retiredname Gamma",
            merged_person_lifespan="",
            merge_date="2024-01-01",
        ),
    ]
    return data


def test_export_contains_all_active_persons_and_not_merged_away(tmp_path: Path) -> None:
    data = _merged_project()
    output = tmp_path / "merged.ged"

    result = GEDCOMExporter().export(data, output)
    text = output.read_text(encoding="utf-8")

    assert result.persons_exported == len(data.persons) == 2
    assert text.count(" INDI\n") == 2
    for name in ("Survivor", "Bystander"):
        assert name in text
    assert "Retiredname" not in text
    assert "Gamma" not in text


def test_export_reports_merge_omission_counts(tmp_path: Path) -> None:
    result = GEDCOMExporter().export(_merged_project(), tmp_path / "merged.ged")

    assert result.omitted_elements["Sammanslagningskandidater"] == 1
    assert result.omitted_elements["Sammanslagningshistorik"] == 1
