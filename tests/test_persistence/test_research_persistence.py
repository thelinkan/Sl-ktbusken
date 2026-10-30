"""Tests for saving, loading and migrating research data.

Covers the round trip of cases, hypotheses, comments and actions; tolerant loading
of projects that predate the feature; corrupt research sections; the 0.2 to 0.3
migration; and the guard against files from a newer version.

**Validates: Requirements 29.1, 29.2, 29.3, 29.4, 29.5, 29.6, 29.7, 29.8**
"""

from __future__ import annotations

import copy
import gzip
import json
from pathlib import Path

import pytest
from hypothesis import given, settings

from slaktbusken.model.event import SourceRef
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.research_case import (
    HypothesisComment,
    ResearchAction,
    ResearchCase,
    ResearchEntityLink,
    ResearchHypothesis,
)
from slaktbusken.model.source import Source
from slaktbusken.persistence.file_io import (
    CURRENT_VERSION,
    CorruptedFileError,
    FilePersistence,
    UnsupportedVersionError,
)
from slaktbusken.persistence.migration import MigrationManager
from slaktbusken.persistence.serialization import deserialize, serialize
from slaktbusken.services.project_service import ProjectService
from tests.test_model.research_strategies import consistent_projects


def _project() -> ProjectData:
    return ProjectData(project=ProjectMetadata(title="Test"))


def _roundtrip(data: ProjectData) -> ProjectData:
    return deserialize(serialize(data))


def _write_raw(raw: dict, path: Path) -> None:
    path.write_bytes(gzip.compress(json.dumps(raw, ensure_ascii=False).encode("utf-8")))


def _full_project() -> ProjectData:
    """A project exercising every research field."""
    data = _project()
    data.persons = [Person(id="person_1", sex="F", names=[Name("birth", "Anna", "Andersdotter")])]
    data.sources = [Source(id="source_1", provider="Arkiv Digital", source_type="church_book", title="Ljusdal AI:17")]
    data.research_cases = [
        ResearchCase(
            id="case_1",
            title="Vem var Anna Andersdotters far?",
            description="Fadern anges inte i födelseboken.",
            status="in_progress",
            priority="high",
            conclusion="Ej klarlagt",
            primary_entity_ref=ResearchEntityLink("person", "person_1"),
            linked_entities=[
                ResearchEntityLink("person", "person_789", "candidate"),
                ResearchEntityLink("event", "event_456", "research_context"),
            ],
        ),
        ResearchCase(id="case_2"),
    ]
    data.research_hypotheses = [
        ResearchHypothesis(
            id="hypothesis_1",
            research_case_id="case_1",
            statement="Per Persson är Annas biologiska far.",
            assessment="possible",
            reasoning="DNA-matchning stöder.",
            linked_entities=[ResearchEntityLink("person", "person_789", "candidate")],
            comments=[
                HypothesisComment("hypcomment_1", "2026-10-30", "En ny DNA-matchning stärker hypotesen."),
                HypothesisComment("hypcomment_2", "", ""),
                HypothesisComment("hypcomment_3", "2026-10", "Ytterligare belägg behövs."),
            ],
        ),
        ResearchHypothesis(id="hypothesis_2", research_case_id="case_1", assessment="rejected"),
    ]
    data.research_actions = [
        ResearchAction(
            id="action_1", research_case_id="case_1", title="Kontrollera Ljusdal AI:17",
            text="Personen återfanns inte.", completed_date="2026-10-30", sort_order=2,
            source_refs=[
                SourceRef("source_1", "primary", "Sid 12", ["examined", "result"]),
                SourceRef("source_9", "questionable"),
            ],
        ),
        ResearchAction(id="action_2", research_case_id="case_1", title="Granska kyrkoböcker", sort_order=0),
        ResearchAction(id="action_3", research_case_id="case_1", completed_date="2026-05"),
    ]
    return data


class TestRoundTrip:
    def test_a_full_project_round_trips_field_by_field(self) -> None:
        """**Validates: Requirements 29.1, 29.2**"""
        data = _full_project()
        loaded = _roundtrip(data)
        assert loaded.research_cases == data.research_cases
        assert loaded.research_hypotheses == data.research_hypotheses
        assert loaded.research_actions == data.research_actions

    @given(project=consistent_projects(include_over_limit=False))
    @settings(max_examples=100, deadline=None)
    def test_generated_projects_round_trip(self, project: ProjectData) -> None:
        """Feature: research-cases, Property: research data survives save and load

        **Validates: Requirements 29.2**
        """
        loaded = _roundtrip(project)
        assert loaded.research_cases == project.research_cases
        assert loaded.research_hypotheses == project.research_hypotheses
        assert loaded.research_actions == project.research_actions

    def test_the_collections_are_written_in_the_file(self) -> None:
        raw = json.loads(serialize(_full_project()))
        assert [c["id"] for c in raw["research_cases"]] == ["case_1", "case_2"]
        assert [h["id"] for h in raw["research_hypotheses"]] == ["hypothesis_1", "hypothesis_2"]
        assert [a["id"] for a in raw["research_actions"]] == ["action_1", "action_2", "action_3"]

    def test_comments_are_nested_inside_their_hypothesis(self) -> None:
        raw = json.loads(serialize(_full_project()))
        assert [c["id"] for c in raw["research_hypotheses"][0]["comments"]] == [
            "hypcomment_1", "hypcomment_2", "hypcomment_3"
        ]
        assert "research_comments" not in raw

    def test_the_file_is_stamped_with_the_current_version(self) -> None:
        raw = json.loads(serialize(_project()))
        assert raw["version"] == CURRENT_VERSION == "0.3"

    def test_comments_and_source_references_keep_their_order(self) -> None:
        loaded = _roundtrip(_full_project())
        assert [c.id for c in loaded.research_hypotheses[0].comments] == [
            "hypcomment_1", "hypcomment_2", "hypcomment_3"
        ]
        assert [r.source_id for r in loaded.research_actions[0].source_refs] == ["source_1", "source_9"]
        assert [l.entity_id for l in loaded.research_cases[0].linked_entities] == ["person_789", "event_456"]


class TestOptionalAndEmptyValues:
    def test_a_pending_action_has_no_completion_date_in_the_file(self) -> None:
        """**Validates: Requirements 29.2**"""
        raw = json.loads(serialize(_full_project()))
        pending = next(a for a in raw["research_actions"] if a["id"] == "action_2")
        assert "completed_date" not in pending

    def test_an_absent_completion_date_stays_absent_not_empty(self) -> None:
        loaded = _roundtrip(_full_project())
        pending = next(a for a in loaded.research_actions if a.id == "action_2")
        assert pending.completed_date is None

    def test_a_blank_completion_date_in_a_file_loads_as_pending(self) -> None:
        raw = json.loads(serialize(_full_project()))
        raw["research_actions"][1]["completed_date"] = ""
        raw["research_actions"][0]["completed_date"] = "   "
        loaded = deserialize(json.dumps(raw))
        assert loaded.research_actions[0].completed_date is None
        assert loaded.research_actions[1].completed_date is None

    def test_a_completion_date_of_any_precision_round_trips(self) -> None:
        loaded = _roundtrip(_full_project())
        assert [a.completed_date for a in loaded.research_actions] == ["2026-10-30", None, "2026-05"]

    def test_empty_text_fields_come_back_as_empty_strings_not_none(self) -> None:
        loaded = _roundtrip(_full_project())
        empty = loaded.research_cases[1]
        assert (empty.title, empty.description, empty.conclusion) == ("", "", "")
        assert empty.primary_entity_ref is None
        assert empty.linked_entities == []
        comment = loaded.research_hypotheses[0].comments[1]
        assert (comment.date, comment.text) == ("", "")

    def test_sort_order_round_trips_as_an_integer_including_zero(self) -> None:
        loaded = _roundtrip(_full_project())
        orders = {a.id: a.sort_order for a in loaded.research_actions}
        assert orders == {"action_1": 2, "action_2": 0, "action_3": 0}
        assert all(isinstance(v, int) for v in orders.values())

    def test_a_case_with_no_hypotheses_and_no_actions_round_trips(self) -> None:
        data = _project()
        data.research_cases = [ResearchCase(id="case_1", title="Ensam")]
        loaded = _roundtrip(data)
        assert loaded.research_cases == data.research_cases
        assert loaded.research_hypotheses == [] and loaded.research_actions == []

    def test_a_hypothesis_with_no_comments_round_trips(self) -> None:
        data = _project()
        data.research_hypotheses = [ResearchHypothesis(id="hypothesis_1", research_case_id="case_1")]
        assert _roundtrip(data).research_hypotheses[0].comments == []

    def test_source_reference_details_are_preserved(self) -> None:
        loaded = _roundtrip(_full_project())
        ref = loaded.research_actions[0].source_refs[0]
        assert (ref.quality, ref.note, ref.aspects) == ("primary", "Sid 12", ["examined", "result"])

    def test_link_roles_are_preserved(self) -> None:
        loaded = _roundtrip(_full_project())
        assert [l.role for l in loaded.research_cases[0].linked_entities] == ["candidate", "research_context"]

    def test_swedish_text_survives_a_save_to_disk(self, tmp_path: Path) -> None:
        """**Validates: Requirements 29.8**"""
        text = "Fadern anges inte i födelseboken – åäö ÅÄÖ é"
        data = _project()
        data.research_cases = [ResearchCase(id="case_1", title=text, description=text, conclusion=text)]
        data.research_hypotheses = [
            ResearchHypothesis(
                id="hypothesis_1", research_case_id="case_1", statement=text, reasoning=text,
                comments=[HypothesisComment("hypcomment_1", "2026", text)],
            )
        ]
        data.research_actions = [ResearchAction(id="action_1", research_case_id="case_1", title=text, text=text)]
        path = tmp_path / "p.json.gz"
        FilePersistence.save(data, path)

        # the text is in the file as readable UTF-8, not escaped
        assert text.encode("utf-8") in gzip.decompress(path.read_bytes())

        loaded = FilePersistence.load(path)
        assert loaded.research_cases[0].title == text
        assert loaded.research_hypotheses[0].comments[0].text == text
        assert loaded.research_actions[0].text == text

    def test_very_long_text_round_trips(self) -> None:
        long_text = "å" * 10000
        data = _project()
        data.research_cases = [ResearchCase(id="case_1", description=long_text, conclusion=long_text)]
        assert _roundtrip(data).research_cases[0].description == long_text


class TestProjectsWithoutResearch:
    def _old_raw(self, version: str = "0.2") -> dict:
        return {
            "format": "släktbuske-file",
            "version": version,
            "format_version": version,
            "project": {"title": "Gammalt projekt"},
            "persons": [{"id": "person_1", "sex": "F", "names": [{"type": "birth", "given": "Anna", "surname": "A"}]}],
        }

    def test_missing_sections_load_as_empty(self) -> None:
        """**Validates: Requirements 29.3**"""
        loaded = deserialize(json.dumps(self._old_raw()))
        assert loaded.research_cases == []
        assert loaded.research_hypotheses == []
        assert loaded.research_actions == []
        assert loaded.id_high_water_marks == {}
        assert loaded.persons[0].id == "person_1"

    def test_null_sections_load_as_empty(self) -> None:
        raw = self._old_raw("0.3")
        raw.update(research_cases=None, research_hypotheses=None, research_actions=None)
        loaded = deserialize(json.dumps(raw))
        assert loaded.research_cases == [] and loaded.research_hypotheses == [] and loaded.research_actions == []

    def test_empty_sections_load_as_empty(self) -> None:
        raw = self._old_raw("0.3")
        raw.update(research_cases=[], research_hypotheses=[], research_actions=[])
        assert deserialize(json.dumps(raw)).research_cases == []

    def test_loading_reports_no_errors(self) -> None:
        log: list[str] = []
        deserialize(json.dumps(self._old_raw()), log=log)
        assert log == []

    def test_a_0_2_file_loads_through_the_file_layer_and_is_migrated(self, tmp_path: Path) -> None:
        path = tmp_path / "old.json.gz"
        _write_raw(self._old_raw("0.2"), path)
        loaded = FilePersistence.load(path)
        assert loaded.version == CURRENT_VERSION
        assert loaded.research_cases == []
        assert (tmp_path / "old_v0.2.json.gz").exists()  # a backup was made first

    def test_a_pre_feature_project_saves_with_nothing_added(self) -> None:
        """Saving an old project writes no research noise except empty sections."""
        loaded = deserialize(json.dumps(self._old_raw()))
        raw = json.loads(serialize(loaded))
        assert raw["research_cases"] == []
        assert "id_high_water_marks" not in raw
        assert raw["persons"][0]["id"] == "person_1"


class TestCorruptSections:
    @pytest.mark.parametrize(
        ("key", "name"),
        [
            ("research_cases", "forskningsärenden"),
            ("research_hypotheses", "hypoteser"),
            ("research_actions", "forskningsåtgärder"),
        ],
    )
    @pytest.mark.parametrize("bad", [{"a": 1}, "text", 5, True])
    def test_a_section_that_is_not_a_list_aborts_the_load_naming_it(
        self, key: str, name: str, bad: object
    ) -> None:
        """**Validates: Requirements 29.6**"""
        raw = {"format": "släktbuske-file", "version": "0.3", "project": {"title": "T"}, key: bad}
        with pytest.raises(CorruptedFileError) as excinfo:
            deserialize(json.dumps(raw))
        assert name in str(excinfo.value)
        assert "ogiltigt format" in str(excinfo.value)

    def test_the_open_project_is_left_untouched_by_a_failed_open(self, tmp_path: Path) -> None:
        good = tmp_path / "good.json.gz"
        FilePersistence.save(_full_project(), good)
        bad = tmp_path / "bad.json.gz"
        _write_raw({"format": "släktbuske-file", "version": "0.3", "format_version": "0.3",
                    "project": {"title": "Trasig"}, "research_actions": "oops"}, bad)

        service = ProjectService()
        opened = service.open_project(good)
        with pytest.raises(CorruptedFileError):
            service.open_project(bad)

        assert service.data is opened
        assert service.project_path == good
        assert [c.id for c in service.data.research_cases] == ["case_1", "case_2"]

    def test_a_non_list_marks_value_does_not_fail_the_load(self) -> None:
        raw = {"format": "f", "version": "0.3", "project": {"title": "T"}, "id_high_water_marks": [1, 2]}
        assert deserialize(json.dumps(raw)).id_high_water_marks == {}

    def test_non_integer_marks_are_ignored(self) -> None:
        raw = {"format": "f", "version": "0.3", "project": {"title": "T"},
               "id_high_water_marks": {"case_": 4, "action_": "x", "hypothesis_": 2.5, "hypcomment_": True}}
        assert deserialize(json.dumps(raw)).id_high_water_marks == {"case_": 4}


class TestTolerantLoading:
    def test_unknown_fields_are_ignored_and_logged_with_the_entity_id(self) -> None:
        """**Validates: Requirements 29.7**"""
        raw = json.loads(serialize(_full_project()))
        raw["research_cases"][0]["from_the_future"] = 1
        raw["research_actions"][1]["another"] = "x"
        log: list[str] = []
        loaded = deserialize(json.dumps(raw), log=log)
        assert any("from_the_future" in line and "case_1" in line for line in log)
        assert any("another" in line and "action_2" in line for line in log)
        assert loaded.research_cases[0].title == "Vem var Anna Andersdotters far?"

    def test_unresolved_references_are_kept_and_logged(self) -> None:
        data = _full_project()  # event_456, person_789 and source_9 do not exist
        log: list[str] = []
        loaded = deserialize(serialize(data), log=log)
        assert any("person_789" in line for line in log)
        assert any("event_456" in line for line in log)
        assert any("source_9" in line and "action_1" in line for line in log)
        # nothing was dropped
        assert loaded.research_cases == data.research_cases
        assert loaded.research_actions == data.research_actions

    def test_a_hypothesis_or_action_with_a_missing_case_is_kept_and_logged(self) -> None:
        data = _project()
        data.research_hypotheses = [ResearchHypothesis(id="hypothesis_1", research_case_id="case_404")]
        data.research_actions = [ResearchAction(id="action_1", research_case_id="case_404")]
        log: list[str] = []
        loaded = deserialize(serialize(data), log=log)
        assert len(loaded.research_hypotheses) == 1 and len(loaded.research_actions) == 1
        assert any("hypothesis_1" in line and "case_404" in line for line in log)
        assert any("action_1" in line and "case_404" in line for line in log)

    def test_resolved_references_are_not_logged(self) -> None:
        data = _project()
        data.persons = [Person(id="person_1", sex="F", names=[Name("birth", "A", "B")])]
        data.research_cases = [ResearchCase(id="case_1", primary_entity_ref=ResearchEntityLink("person", "person_1"))]
        log: list[str] = []
        deserialize(serialize(data), log=log)
        assert log == []

    def test_unresolved_references_do_not_abort_the_load(self) -> None:
        deserialize(serialize(_full_project()))  # no log, no error


class TestMigration:
    def _raw(self, **extra: object) -> dict:
        raw = {
            "format": "släktbuske-file", "version": "0.2", "format_version": "0.2",
            "project": {"title": "T"}, "persons": [{"id": "person_1"}], "residences": [{"id": "residence_1"}],
        }
        raw.update(extra)
        return raw

    def _migrate(self, raw: dict) -> dict:
        return MigrationManager.migrate(raw, "0.2")

    def test_the_three_empty_collections_are_added(self) -> None:
        """**Validates: Requirements 29.4**"""
        result = self._migrate(self._raw())
        assert result["research_cases"] == []
        assert result["research_hypotheses"] == []
        assert result["research_actions"] == []

    def test_both_version_fields_are_bumped(self) -> None:
        result = self._migrate(self._raw())
        assert result["version"] == "0.3"
        assert result["format_version"] == "0.3"

    def test_nothing_else_is_changed(self) -> None:
        raw = self._raw()
        before = copy.deepcopy(raw)
        result = self._migrate(raw)
        for key in ("format", "project", "persons", "residences"):
            assert result[key] == before[key]

    def test_existing_research_data_is_left_alone(self) -> None:
        existing = [{"id": "case_1", "title": "Kvar"}]
        result = self._migrate(self._raw(research_cases=existing))
        assert result["research_cases"] == existing
        assert result["research_hypotheses"] == []

    def test_applying_it_twice_changes_nothing(self) -> None:
        once = self._migrate(self._raw())
        snapshot = copy.deepcopy(once)
        again = MigrationManager.migrate(once, "0.3")
        assert again == snapshot

    def test_running_the_step_again_on_migrated_data_is_a_no_op(self) -> None:
        from slaktbusken.persistence.migration import _migrate_0_2_to_0_3

        once = _migrate_0_2_to_0_3(self._raw())
        snapshot = copy.deepcopy(once)
        assert _migrate_0_2_to_0_3(once) == snapshot

    def test_a_0_1_file_is_carried_all_the_way(self) -> None:
        raw = self._raw()
        raw.update(version="0.1", format_version="0.1")
        raw.pop("residences")
        result = MigrationManager.migrate(raw, "0.1")
        assert result["residences"] == []
        assert result["research_cases"] == []
        assert result["version"] == CURRENT_VERSION

    def test_a_0_2_file_needs_migration_and_a_0_3_file_does_not(self) -> None:
        assert MigrationManager.needs_migration("0.2") is True
        assert MigrationManager.needs_migration("0.3") is False

    def test_the_two_version_constants_agree(self) -> None:
        assert MigrationManager.CURRENT_VERSION == CURRENT_VERSION == ProjectData().version == "0.3"

    def test_a_loaded_0_2_project_keeps_all_its_data(self, tmp_path: Path) -> None:
        raw = self._raw()
        raw["persons"] = [
            {"id": "person_1", "sex": "F", "names": [{"type": "birth", "given": "Anna", "surname": "Andersdotter"}]}
        ]
        raw["residences"] = []
        path = tmp_path / "p.json.gz"
        _write_raw(raw, path)
        loaded = FilePersistence.load(path)
        assert loaded.persons[0].id == "person_1"
        assert loaded.persons[0].names[0].surname == "Andersdotter"
        assert loaded.project.title == "T"
        assert loaded.version == "0.3"
        assert loaded.research_cases == []


class TestNewerVersionIsRefused:
    def test_a_newer_file_is_refused_and_left_unchanged(self, tmp_path: Path) -> None:
        """An older program must never write over research data it cannot represent.

        **Validates: Requirements 29.5**
        """
        path = tmp_path / "future.json.gz"
        _write_raw(
            {"format": "släktbuske-file", "version": "0.4", "format_version": "0.4",
             "project": {"title": "T"}, "research_cases": [{"id": "case_1"}]},
            path,
        )
        before = path.read_bytes()
        with pytest.raises(UnsupportedVersionError) as excinfo:
            FilePersistence.load(path)
        assert "nyare version" in str(excinfo.value)
        assert path.read_bytes() == before
        assert list(tmp_path.iterdir()) == [path]  # no backup or stray file either


class TestSaveFailureKeepsTheOldFile:
    def test_a_failed_save_leaves_the_previous_file_intact(self, tmp_path: Path, monkeypatch) -> None:
        """**Validates: Requirements 29.8**"""
        path = tmp_path / "p.json.gz"
        FilePersistence.save(_full_project(), path)
        before = path.read_bytes()

        import os

        def boom(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(os, "replace", boom)
        changed = _full_project()
        changed.research_cases[0].title = "Ändrad rubrik"
        with pytest.raises(OSError):
            FilePersistence.save(changed, path)

        assert path.read_bytes() == before
        assert not [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]
