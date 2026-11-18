"""GEDCOM interaction with research data (task 12.4).

Research cases, hypotheses and actions have no GEDCOM representation. Import
must leave them alone and export must report them as omitted.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.gedcom.importer import GEDCOMImporter
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.research_case import (
    HypothesisComment,
    ResearchAction,
    ResearchCase,
    ResearchEntityLink,
    ResearchHypothesis,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "gedcom"


@pytest.fixture
def translation_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "translation"
    directory.mkdir()
    return directory


def _research_for(person_id: str) -> tuple[list, list, list]:
    cases = [
        ResearchCase(
            id="case_1",
            title="Vem var fadern?",
            primary_entity_ref=ResearchEntityLink("person", person_id),
        )
    ]
    hypotheses = [
        ResearchHypothesis(
            id="hypothesis_1",
            research_case_id="case_1",
            statement="Samma person",
            linked_entities=[ResearchEntityLink("person", person_id)],
            comments=[HypothesisComment(id="hypcomment_1", date="2026-01-01", text="t")],
        )
    ]
    actions = [ResearchAction(id="action_1", research_case_id="case_1", title="Sök")]
    return cases, hypotheses, actions


def _import(data: ProjectData, name: str, translation_dir: Path) -> None:
    GEDCOMImporter(data, translation_dir).import_file(FIXTURES / name)


def _snapshot(data: ProjectData):
    return (
        copy.deepcopy(data.research_cases),
        copy.deepcopy(data.research_hypotheses),
        copy.deepcopy(data.research_actions),
    )


class TestImport:
    def test_reimport_preserves_research_and_creates_no_duplicates(
        self, translation_dir: Path
    ) -> None:
        data = ProjectData(project=ProjectMetadata(title="T"))
        _import(data, "Test-1.ged", translation_dir)
        person_id = data.persons[0].id
        data.research_cases, data.research_hypotheses, data.research_actions = _research_for(
            person_id
        )
        before = _snapshot(data)

        _import(data, "Test-1.ged", translation_dir)

        assert _snapshot(data) == before
        assert len(data.research_cases) == 1
        assert len(data.research_hypotheses) == 1
        assert len(data.research_actions) == 1

    def test_person_missing_from_a_later_gedcom_keeps_its_research(
        self, translation_dir: Path
    ) -> None:
        data = ProjectData(project=ProjectMetadata(title="T"))
        _import(data, "Test-1.ged", translation_dir)
        person_id = data.persons[0].id
        data.research_cases, data.research_hypotheses, data.research_actions = _research_for(
            person_id
        )
        before = _snapshot(data)

        # A different file that does not mention the person again.
        _import(data, "Test-2.ged", translation_dir)

        assert _snapshot(data) == before
        assert any(p.id == person_id for p in data.persons)

    def test_import_into_project_without_research_stays_empty(
        self, translation_dir: Path
    ) -> None:
        data = ProjectData(project=ProjectMetadata(title="T"))
        _import(data, "Test-1.ged", translation_dir)
        assert data.research_cases == []
        assert data.research_hypotheses == []
        assert data.research_actions == []
        assert data.id_high_water_marks == {}


class TestExport:
    def test_export_reports_research_omissions(self, tmp_path: Path, translation_dir: Path) -> None:
        data = ProjectData(project=ProjectMetadata(title="T"))
        _import(data, "Test-1.ged", translation_dir)
        data.research_cases, data.research_hypotheses, data.research_actions = _research_for(
            data.persons[0].id
        )
        data.research_cases.append(ResearchCase(id="case_2", title="Två"))

        result = GEDCOMExporter().export(data, tmp_path / "out.ged")

        assert result.omitted_elements["Forskningsärenden"] == 2
        assert result.omitted_elements["Hypoteser"] == 1
        assert result.omitted_elements["Forskningsåtgärder"] == 1

    def test_export_without_research_reports_no_research_omission(
        self, tmp_path: Path, translation_dir: Path
    ) -> None:
        data = ProjectData(project=ProjectMetadata(title="T"))
        _import(data, "Test-1.ged", translation_dir)
        result = GEDCOMExporter().export(data, tmp_path / "out.ged")
        for key in ("Forskningsärenden", "Hypoteser", "Forskningsåtgärder"):
            assert key not in result.omitted_elements

    def test_export_does_not_change_research(self, tmp_path: Path, translation_dir: Path) -> None:
        data = ProjectData(project=ProjectMetadata(title="T"))
        _import(data, "Test-1.ged", translation_dir)
        data.research_cases, data.research_hypotheses, data.research_actions = _research_for(
            data.persons[0].id
        )
        before = _snapshot(data)
        GEDCOMExporter().export(data, tmp_path / "out.ged")
        assert _snapshot(data) == before
