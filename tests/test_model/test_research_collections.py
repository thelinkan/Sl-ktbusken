"""Tests for the research collections and the research id mechanism.

Covers collection order, id uniqueness, and the guarantee that a deleted research
id is never issued again, including after the project is saved and reopened.

**Validates: Requirements 1.2, 1.3, 2.1, 2.3, 2.4, 2.5, 4.2, 4.3, 5.3, 6.2, 6.3**
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.research_case import (
    HypothesisComment,
    ResearchAction,
    ResearchCase,
    ResearchHypothesis,
)
from slaktbusken.persistence.serialization import deserialize, serialize
from slaktbusken.services.research_service import (
    RESEARCH_ID_ENTITY_TYPES,
    ResearchIdGenerator,
    live_research_ids,
    reconcile_id_high_water_marks,
    research_id_prefix,
)


def _project() -> ProjectData:
    return ProjectData(project=ProjectMetadata(title="Test"))


def _reopen(data: ProjectData) -> ProjectData:
    """Save and reload the project, as closing and reopening it would."""
    return deserialize(serialize(data))


class TestNewProject:
    def test_a_new_project_has_empty_research_collections(self) -> None:
        """**Validates: Requirements 1.2, 4.2, 6.2**"""
        data = _project()
        assert data.research_cases == []
        assert data.research_hypotheses == []
        assert data.research_actions == []
        assert data.id_high_water_marks == {}

    def test_collections_are_not_shared_between_projects(self) -> None:
        first, second = _project(), _project()
        first.research_cases.append(ResearchCase(id="case_1"))
        first.id_high_water_marks["case_"] = 1
        assert second.research_cases == []
        assert second.id_high_water_marks == {}


class TestOrder:
    def test_cases_keep_the_order_they_were_added_in(self) -> None:
        """**Validates: Requirements 1.2**"""
        data = _project()
        generator = ResearchIdGenerator(data)
        for _ in range(5):
            data.research_cases.append(ResearchCase(id=generator.generate("research_case")))
        assert [c.id for c in data.research_cases] == [f"case_{n}" for n in range(1, 6)]

    def test_order_survives_save_and_reopen(self) -> None:
        data = _project()
        data.research_cases = [ResearchCase(id=i) for i in ("case_3", "case_1", "case_2")]
        data.research_hypotheses = [
            ResearchHypothesis(id=i, research_case_id="case_1") for i in ("hypothesis_2", "hypothesis_1")
        ]
        data.research_actions = [
            ResearchAction(id=i, research_case_id="case_1") for i in ("action_9", "action_4", "action_7")
        ]
        reopened = _reopen(data)
        assert [c.id for c in reopened.research_cases] == ["case_3", "case_1", "case_2"]
        assert [h.id for h in reopened.research_hypotheses] == ["hypothesis_2", "hypothesis_1"]
        assert [a.id for a in reopened.research_actions] == ["action_9", "action_4", "action_7"]

    def test_deleting_one_keeps_the_others_in_place(self) -> None:
        data = _project()
        data.research_cases = [ResearchCase(id=f"case_{n}") for n in range(1, 5)]
        data.research_cases = [c for c in data.research_cases if c.id != "case_2"]
        assert [c.id for c in data.research_cases] == ["case_1", "case_3", "case_4"]


class TestUniqueIds:
    @pytest.mark.parametrize(
        ("entity_type", "first"),
        [
            ("research_case", "case_1"),
            ("research_hypothesis", "hypothesis_1"),
            ("research_action", "action_1"),
            ("hypothesis_comment", "hypcomment_1"),
        ],
    )
    def test_the_first_id_of_each_type_starts_at_one(self, entity_type: str, first: str) -> None:
        """**Validates: Requirements 1.3, 4.3, 5.3, 6.3**"""
        assert ResearchIdGenerator(_project()).generate(entity_type) == first

    def test_ids_increase_even_before_the_entity_is_added(self) -> None:
        """An editor may issue several ids before anything is committed."""
        generator = ResearchIdGenerator(_project())
        assert [generator.generate("research_action") for _ in range(3)] == [
            "action_1", "action_2", "action_3"
        ]

    def test_each_type_counts_independently(self) -> None:
        generator = ResearchIdGenerator(_project())
        assert generator.generate("research_case") == "case_1"
        assert generator.generate("research_case") == "case_2"
        assert generator.generate("research_action") == "action_1"
        assert generator.generate("hypothesis_comment") == "hypcomment_1"

    def test_a_new_id_is_above_every_live_id(self) -> None:
        data = _project()
        data.research_cases = [ResearchCase(id="case_4"), ResearchCase(id="case_9")]
        assert ResearchIdGenerator(data).generate("research_case") == "case_10"

    def test_comment_ids_inside_hypotheses_count_as_live(self) -> None:
        data = _project()
        data.research_hypotheses = [
            ResearchHypothesis(
                id="hypothesis_1",
                research_case_id="case_1",
                comments=[HypothesisComment(id="hypcomment_6"), HypothesisComment(id="hypcomment_2")],
            )
        ]
        assert ResearchIdGenerator(data).generate("hypothesis_comment") == "hypcomment_7"

    @pytest.mark.parametrize("entity_type", ["person", "residence", "nonsense", ""])
    def test_only_research_types_are_accepted(self, entity_type: str) -> None:
        with pytest.raises(ValueError):
            ResearchIdGenerator(_project()).generate(entity_type)
        with pytest.raises(ValueError):
            research_id_prefix(entity_type)

    def test_ids_of_other_entities_are_untouched(self) -> None:
        """A research id never collides with a person or event id."""
        generator = ResearchIdGenerator(_project())
        ids = {generator.generate(t) for t in RESEARCH_ID_ENTITY_TYPES}
        assert not any(i.startswith(("person_", "event_", "note_")) for i in ids)


class TestNonReuse:
    """A deleted id is never handed out again."""

    def test_a_freed_id_is_not_reused_within_a_session(self) -> None:
        """**Validates: Requirements 2.5**"""
        data = _project()
        generator = ResearchIdGenerator(data)
        data.research_cases.append(ResearchCase(id=generator.generate("research_case")))
        data.research_cases.append(ResearchCase(id=generator.generate("research_case")))
        data.research_cases.pop()  # delete case_2, the highest
        assert ResearchIdGenerator(data).generate("research_case") == "case_3"

    def test_the_highest_id_is_not_reused_after_save_and_reopen(self) -> None:
        """The case the existing IDGenerator gets wrong. **Validates: Requirements 2.1, 2.3**"""
        data = _project()
        generator = ResearchIdGenerator(data)
        for _ in range(7):
            data.research_cases.append(ResearchCase(id=generator.generate("research_case")))
        data.research_cases = [c for c in data.research_cases if c.id != "case_7"]

        reopened = _reopen(data)
        assert "case_7" not in {c.id for c in reopened.research_cases}
        assert ResearchIdGenerator(reopened).generate("research_case") == "case_8"

    def test_every_research_type_is_protected(self) -> None:
        data = _project()
        generator = ResearchIdGenerator(data)
        issued = {t: generator.generate(t) for t in RESEARCH_ID_ENTITY_TYPES}
        # Nothing was added to the project, so nothing is live: only the marks
        # remember the ids.
        reopened = _reopen(data)
        for entity_type in RESEARCH_ID_ENTITY_TYPES:
            assert ResearchIdGenerator(reopened).generate(entity_type) != issued[entity_type]

    def test_deleting_everything_does_not_reset_the_counters(self) -> None:
        data = _project()
        generator = ResearchIdGenerator(data)
        data.research_cases = [ResearchCase(id=generator.generate("research_case")) for _ in range(3)]
        data.research_cases = []
        assert ResearchIdGenerator(_reopen(data)).generate("research_case") == "case_4"

    def test_the_marks_round_trip(self) -> None:
        """**Validates: Requirements 2.4**"""
        data = _project()
        data.id_high_water_marks = {"case_": 7, "action_": 3}
        assert _reopen(data).id_high_water_marks == {"case_": 7, "action_": 3}

    def test_a_project_without_marks_has_none_written(self) -> None:
        assert "id_high_water_marks" not in serialize(_project())

    def test_a_cancelled_editor_still_advances_the_mark(self) -> None:
        """Ids issued to a working copy that is thrown away are not reissued."""
        data = _project()
        ResearchIdGenerator(data).generate("research_case")  # issued, never added
        assert ResearchIdGenerator(data).generate("research_case") == "case_2"

    @given(
        operations=st.lists(
            st.tuples(st.sampled_from(["add", "delete", "reopen"]), st.integers(min_value=0, max_value=50)),
            max_size=40,
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_no_id_is_ever_issued_twice(self, operations: list[tuple[str, int]]) -> None:
        """Feature: research-cases, Property: research ids are never reused

        Across any mix of adding, deleting and saving-and-reopening, an id issued
        once is never issued again.

        **Validates: Requirements 2.1, 2.3, 2.5**
        """
        data = _project()
        issued: set[str] = set()
        for operation, index in operations:
            if operation == "add":
                new_id = ResearchIdGenerator(data).generate("research_case")
                assert new_id not in issued, f"{new_id} was issued twice"
                issued.add(new_id)
                data.research_cases.append(ResearchCase(id=new_id))
            elif operation == "delete" and data.research_cases:
                del data.research_cases[index % len(data.research_cases)]
            elif operation == "reopen":
                data = _reopen(data)


class TestReconcile:
    def test_a_project_with_research_but_no_marks_gets_them(self) -> None:
        """A file written before the marks existed. **Validates: Requirements 2.4**"""
        data = _project()
        data.research_cases = [ResearchCase(id="case_5")]
        data.research_actions = [ResearchAction(id="action_2", research_case_id="case_5")]
        data.research_hypotheses = [
            ResearchHypothesis(
                id="hypothesis_3", research_case_id="case_5",
                comments=[HypothesisComment(id="hypcomment_8")],
            )
        ]
        reconcile_id_high_water_marks(data)
        assert data.id_high_water_marks == {
            "case_": 5, "hypothesis_": 3, "action_": 2, "hypcomment_": 8
        }

    def test_loading_such_a_file_reconciles_it(self) -> None:
        data = _project()
        data.research_cases = [ResearchCase(id="case_5")]
        assert "id_high_water_marks" not in serialize(data)
        assert _reopen(data).id_high_water_marks == {"case_": 5}

    def test_a_mark_is_never_lowered(self) -> None:
        data = _project()
        data.research_cases = [ResearchCase(id="case_2")]
        data.id_high_water_marks = {"case_": 9}
        reconcile_id_high_water_marks(data)
        assert data.id_high_water_marks == {"case_": 9}

    def test_a_live_id_above_the_mark_raises_it(self) -> None:
        data = _project()
        data.research_cases = [ResearchCase(id="case_12")]
        data.id_high_water_marks = {"case_": 3}
        reconcile_id_high_water_marks(data)
        assert data.id_high_water_marks == {"case_": 12}

    def test_a_project_without_research_keeps_an_empty_map(self) -> None:
        """A pre-feature project is left exactly as it was."""
        data = _project()
        reconcile_id_high_water_marks(data)
        assert data.id_high_water_marks == {}

    def test_ids_that_do_not_follow_the_pattern_are_ignored(self) -> None:
        data = _project()
        data.research_cases = [ResearchCase(id="legacy"), ResearchCase(id="case_x"), ResearchCase(id="case_3")]
        reconcile_id_high_water_marks(data)
        assert data.id_high_water_marks == {"case_": 3}

    def test_reconciling_twice_changes_nothing(self) -> None:
        data = _project()
        data.research_cases = [ResearchCase(id="case_4")]
        reconcile_id_high_water_marks(data)
        once = dict(data.id_high_water_marks)
        reconcile_id_high_water_marks(data)
        assert data.id_high_water_marks == once

    def test_live_research_ids_are_grouped_by_prefix(self) -> None:
        data = _project()
        data.research_cases = [ResearchCase(id="case_1")]
        data.research_actions = [ResearchAction(id="action_1", research_case_id="case_1")]
        live = live_research_ids(data)
        assert live["case_"] == {"case_1"}
        assert live["action_"] == {"action_1"}
        assert live["hypothesis_"] == set()
        assert live["hypcomment_"] == set()
