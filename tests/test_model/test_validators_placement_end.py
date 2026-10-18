"""Unit tests for placement end-event pairing validation.

A Placement_End_Event (``foster_home_ended`` closes ``foster_home``;
``adoption_ended`` closes ``adoption``) names the same child and the same
parents as its paired Placement_Start_Event (symmetric participants), and is
paired to exactly one start by Parent_Set. Covers Requirements 1.10, 2A.1,
2A.3, 2A.4, 2A.6 and 2A.7.
"""

from __future__ import annotations

from typing import Optional

import pytest

from slaktbusken.model.event import DateValue, Event, Participant
from slaktbusken.model.validators import (
    _MSG_PLACEMENT_DUPLICATE_END_ADOPTION,
    _MSG_PLACEMENT_DUPLICATE_END_FOSTER,
    _MSG_PLACEMENT_END_BEFORE_START,
    _MSG_PLACEMENT_ORPHAN_END_ADOPTION,
    _MSG_PLACEMENT_ORPHAN_END_FOSTER,
    placement_end_findings,
    validate_placement_end_events,
)


# Per-type role strings, end types, and expected messages, so each test runs
# symmetrically over the foster and adoptive variants.
FOSTER = {
    "start_type": "foster_home",
    "end_type": "foster_home_ended",
    "child_role": "fosterbarn",
    "parent_role": "fosterförälder",
    "orphan": _MSG_PLACEMENT_ORPHAN_END_FOSTER,
    "duplicate": _MSG_PLACEMENT_DUPLICATE_END_FOSTER,
}
ADOPTION = {
    "start_type": "adoption",
    "end_type": "adoption_ended",
    "child_role": "adopterad",
    "parent_role": "adoptivförälder",
    "orphan": _MSG_PLACEMENT_ORPHAN_END_ADOPTION,
    "duplicate": _MSG_PLACEMENT_DUPLICATE_END_ADOPTION,
}

BOTH = [pytest.param(FOSTER, id="foster"), pytest.param(ADOPTION, id="adoptive")]

_COUNTER = {"n": 0}


def _next_id() -> str:
    _COUNTER["n"] += 1
    return f"event_{_COUNTER['n']}"


def make_start(
    spec: dict,
    child: str,
    parents: list[str],
    *,
    date: Optional[str] = None,
    event_id: Optional[str] = None,
) -> Event:
    """A placement START event naming *child* and *parents* in the type's roles."""
    participants = [Participant(person_id=child, role=spec["child_role"])]
    participants.extend(
        Participant(person_id=p, role=spec["parent_role"]) for p in parents
    )
    return Event(
        id=event_id or _next_id(),
        type=spec["start_type"],
        participants=participants,
        date=DateValue(value=date, precision="day") if date else None,
    )


def make_end(
    spec: dict,
    child: str,
    parents: list[str],
    *,
    date: Optional[str] = None,
    event_id: Optional[str] = None,
) -> Event:
    """A placement END event naming *child* and *parents* in the type's roles."""
    participants = [Participant(person_id=child, role=spec["child_role"])]
    participants.extend(
        Participant(person_id=p, role=spec["parent_role"]) for p in parents
    )
    return Event(
        id=event_id or _next_id(),
        type=spec["end_type"],
        participants=participants,
        date=DateValue(value=date, precision="day") if date else None,
    )


class TestValidPairing:
    """Req 2A.1 — an end paired to a matching start is error-free."""

    @pytest.mark.parametrize("spec", BOTH)
    def test_end_matching_start_one_parent(self, spec: dict) -> None:
        """**Validates: Requirements 2A.1**"""
        start = make_start(spec, "child_a", ["parent_1"])
        end = make_end(spec, "child_a", ["parent_1"])
        assert validate_placement_end_events([start, end]) == []

    @pytest.mark.parametrize("spec", BOTH)
    def test_end_matching_start_two_parents_order_independent(self, spec: dict) -> None:
        """Parent_Set is a set: parent order does not affect matching.

        **Validates: Requirements 2A.1, 1.10**
        """
        start = make_start(spec, "child_a", ["parent_1", "parent_2"])
        end = make_end(spec, "child_a", ["parent_2", "parent_1"])
        assert validate_placement_end_events([start, end]) == []


class TestOrphanEnd:
    """Req 2A.4 — an end with no matching start yields the orphan message once."""

    @pytest.mark.parametrize("spec", BOTH)
    def test_no_start_at_all(self, spec: dict) -> None:
        """**Validates: Requirements 2A.4**"""
        end = make_end(spec, "child_a", ["parent_1"])
        errors = validate_placement_end_events([end])
        assert errors.count(spec["orphan"]) == 1
        assert errors == [spec["orphan"]]

    @pytest.mark.parametrize("spec", BOTH)
    def test_no_start_for_that_child(self, spec: dict) -> None:
        """A start exists but for a different child → orphan.

        **Validates: Requirements 2A.4**
        """
        start = make_start(spec, "child_a", ["parent_1"])
        end = make_end(spec, "child_b", ["parent_1"])
        errors = validate_placement_end_events([start, end])
        assert errors.count(spec["orphan"]) == 1

    @pytest.mark.parametrize("spec", BOTH)
    def test_parents_do_not_match_any_parent_set(self, spec: dict) -> None:
        """Same child, but no start's Parent_Set matches → orphan (Req 2A.7).

        **Validates: Requirements 2A.4, 2A.7**
        """
        start = make_start(spec, "child_a", ["parent_1"])
        end = make_end(spec, "child_a", ["parent_9"])
        errors = validate_placement_end_events([start, end])
        assert errors.count(spec["orphan"]) == 1

    @pytest.mark.parametrize("spec", BOTH)
    def test_subset_of_parents_does_not_match(self, spec: dict) -> None:
        """A two-parent start is not matched by a one-parent end.

        **Validates: Requirements 2A.4, 2A.7**
        """
        start = make_start(spec, "child_a", ["parent_1", "parent_2"])
        end = make_end(spec, "child_a", ["parent_1"])
        errors = validate_placement_end_events([start, end])
        assert errors.count(spec["orphan"]) == 1


class TestPairingAmongMultipleStarts:
    """Req 2A.7 — the end resolves to the start whose Parent_Set it names."""

    @pytest.mark.parametrize("spec", BOTH)
    def test_end_picks_matching_parent_set(self, spec: dict) -> None:
        """Two starts for one child; the end matches exactly one by Parent_Set.

        **Validates: Requirements 2A.7**
        """
        start_1 = make_start(spec, "child_a", ["parent_1"])
        start_2 = make_start(spec, "child_a", ["parent_2"])
        end = make_end(spec, "child_a", ["parent_2"])
        assert validate_placement_end_events([start_1, start_2, end]) == []

    @pytest.mark.parametrize("spec", BOTH)
    def test_two_ends_for_two_different_starts_both_ok(self, spec: dict) -> None:
        """Each start may have its own single end.

        **Validates: Requirements 2A.3, 2A.7**
        """
        start_1 = make_start(spec, "child_a", ["parent_1"])
        start_2 = make_start(spec, "child_a", ["parent_2"])
        end_1 = make_end(spec, "child_a", ["parent_1"])
        end_2 = make_end(spec, "child_a", ["parent_2"])
        assert validate_placement_end_events([start_1, start_2, end_1, end_2]) == []


class TestAtMostOneEndPerStart:
    """Req 2A.3 — a second end on the same start yields the duplicate message."""

    @pytest.mark.parametrize("spec", BOTH)
    def test_two_ends_for_same_start(self, spec: dict) -> None:
        """**Validates: Requirements 2A.3**"""
        start = make_start(spec, "child_a", ["parent_1"])
        end_1 = make_end(spec, "child_a", ["parent_1"])
        end_2 = make_end(spec, "child_a", ["parent_1"])
        errors = validate_placement_end_events([start, end_1, end_2])
        assert errors.count(spec["duplicate"]) == 1
        assert spec["orphan"] not in errors

    @pytest.mark.parametrize("spec", BOTH)
    def test_three_ends_for_same_start_two_duplicates(self, spec: dict) -> None:
        """The first end keeps the slot; each later end is a duplicate.

        **Validates: Requirements 2A.3**
        """
        start = make_start(spec, "child_a", ["parent_1"])
        ends = [make_end(spec, "child_a", ["parent_1"]) for _ in range(3)]
        errors = validate_placement_end_events([start, *ends])
        assert errors.count(spec["duplicate"]) == 2


class TestEndBeforeStartWarning:
    """Req 2A.6 — end earlier than its start is a WARNING, never a hard error."""

    @pytest.mark.parametrize("spec", BOTH)
    def test_end_before_start_is_a_warning(self, spec: dict) -> None:
        """**Validates: Requirements 2A.6**"""
        start = make_start(spec, "child_a", ["parent_1"], date="1850-06-01")
        end = make_end(spec, "child_a", ["parent_1"], date="1849-01-01")
        findings = placement_end_findings([start, end])
        assert len(findings) == 1
        assert findings[0].message == _MSG_PLACEMENT_END_BEFORE_START
        assert findings[0].severity == "warning"
        assert findings[0].event_id == end.id

    @pytest.mark.parametrize("spec", BOTH)
    def test_end_before_start_is_not_a_hard_error(self, spec: dict) -> None:
        """The chronology problem must not surface as a hard error.

        **Validates: Requirements 2A.6**
        """
        start = make_start(spec, "child_a", ["parent_1"], date="1850-06-01")
        end = make_end(spec, "child_a", ["parent_1"], date="1849-01-01")
        assert validate_placement_end_events([start, end]) == []

    @pytest.mark.parametrize("spec", BOTH)
    def test_end_after_start_has_no_finding(self, spec: dict) -> None:
        """**Validates: Requirements 2A.6**"""
        start = make_start(spec, "child_a", ["parent_1"], date="1850-06-01")
        end = make_end(spec, "child_a", ["parent_1"], date="1860-01-01")
        assert placement_end_findings([start, end]) == []

    @pytest.mark.parametrize("spec", BOTH)
    def test_undated_events_have_no_finding(self, spec: dict) -> None:
        """No finding when either side is undated.

        **Validates: Requirements 2A.6**
        """
        start = make_start(spec, "child_a", ["parent_1"])
        end = make_end(spec, "child_a", ["parent_1"], date="1849-01-01")
        assert placement_end_findings([start, end]) == []

    @pytest.mark.parametrize("spec", BOTH)
    def test_orphan_end_has_no_finding(self, spec: dict) -> None:
        """An unpaired end has no start to compare against.

        **Validates: Requirements 2A.6**
        """
        end = make_end(spec, "child_a", ["parent_1"], date="1849-01-01")
        assert placement_end_findings([end]) == []


class TestSymmetricParticipants:
    """Req 1.10 — an end mirrors its start's one-child / one-or-two-parent shape."""

    @pytest.mark.parametrize("spec", BOTH)
    def test_single_parent_end_pairs(self, spec: dict) -> None:
        """**Validates: Requirements 1.10**"""
        start = make_start(spec, "child_a", ["parent_1"])
        end = make_end(spec, "child_a", ["parent_1"])
        assert validate_placement_end_events([start, end]) == []

    @pytest.mark.parametrize("spec", BOTH)
    def test_two_parent_end_pairs(self, spec: dict) -> None:
        """**Validates: Requirements 1.10**"""
        start = make_start(spec, "child_a", ["parent_1", "parent_2"])
        end = make_end(spec, "child_a", ["parent_1", "parent_2"])
        assert validate_placement_end_events([start, end]) == []


class TestTypesAreIndependent:
    """A foster end never pairs to an adoption start or vice versa."""

    def test_foster_end_does_not_pair_to_adoption_start(self) -> None:
        """**Validates: Requirements 2A.1, 2A.4**"""
        start = make_start(ADOPTION, "child_a", ["parent_1"])
        end = make_end(FOSTER, "child_a", ["parent_1"])
        errors = validate_placement_end_events([start, end])
        assert errors == [_MSG_PLACEMENT_ORPHAN_END_FOSTER]

    def test_mixed_project_each_type_pairs_independently(self) -> None:
        """Foster and adoptive placements for the same child coexist.

        **Validates: Requirements 2A.1, 2A.7**
        """
        f_start = make_start(FOSTER, "child_a", ["parent_1"])
        f_end = make_end(FOSTER, "child_a", ["parent_1"])
        a_start = make_start(ADOPTION, "child_a", ["parent_2"])
        a_end = make_end(ADOPTION, "child_a", ["parent_2"])
        assert validate_placement_end_events([f_start, f_end, a_start, a_end]) == []


class TestEmptyAndStartOnly:
    """No end events means nothing to validate."""

    def test_empty_event_list(self) -> None:
        assert validate_placement_end_events([]) == []
        assert placement_end_findings([]) == []

    @pytest.mark.parametrize("spec", BOTH)
    def test_start_only_no_errors(self, spec: dict) -> None:
        start = make_start(spec, "child_a", ["parent_1"], date="1850-06-01")
        assert validate_placement_end_events([start]) == []
        assert placement_end_findings([start]) == []
