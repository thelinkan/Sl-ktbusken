"""Property-based tests for the foster-parents backward-compatibility guarantee.

Feature: foster-parents, Property 8: Backward compatibility

Loading a pre-feature project loses no foster/adoptive link, preserves
descriptive adoption events, and defaults Connection_Overrides to empty when the
key is absent.

**Validates: Requirements 13.1, 13.3, 13.4, 13.5**

The "load" path under test is the on-load migration + sync in
``slaktbusken/services/foster_sync.py:migrate_orphan_links(project)`` (back-fill
orphan placement events, then ``sync_parentage_links``), together with the
serializer round-trip in ``slaktbusken/persistence/serialization.py`` which must
default ``connection_overrides`` to empty when absent.

``foster_project()`` (from ``tests.test_foster.foster_strategies``) builds a
raw, pre-sync project that stands in for a pre-feature project: it generates
orphan foster/adoptive links with no backing event (``orphan_link_family_ids``),
pre-feature purely-descriptive adoption events (an ``adoption`` start naming a
child but no adoptive-parent participant), and ``connection_overrides`` entries.

These are production-behaviour tests (expected to PASS), NOT bugfix exploration
tests.
"""

from __future__ import annotations

import copy
import json

from hypothesis import given, settings

from slaktbusken.model.event import Event
from slaktbusken.model.validators import _VALID_PARENTAGE_TYPES
from slaktbusken.persistence.serialization import deserialize, serialize
from slaktbusken.services.foster_sync import migrate_orphan_links

from tests.test_foster.foster_strategies import (
    DERIVED_PARENTAGE,
    PLACEMENT_START,
    foster_project,
)


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------


def _derived_link_set(project) -> set[tuple[str, str, str]]:
    """Every foster/adoptive link as ``(parentage_type, child_id, parent_id)``.

    Captures a child/parent/type link regardless of which family holds it, so
    two snapshots compare equal across the family reorganisation the migration
    performs.
    """
    out: set[tuple[str, str, str]] = set()
    for family in project.families:
        for link in family.parent_child_links:
            if (
                link.parentage_type in DERIVED_PARENTAGE
                and link.parent_id is not None
            ):
                out.add((link.parentage_type, link.child_id, link.parent_id))
    return out


def _descriptive_adoption_events(project) -> list[Event]:
    """Pre-feature descriptive adoption events in a project.

    A descriptive adoption event is an ``adoption`` start that names a child in
    the ``adopterad`` role but has NO participant in the adoptive-parent role
    (``adoptivförälder``). Such an event derives no link (Req 1.9 / 13.5).
    """
    child_role = PLACEMENT_START["adoption"]["child_role"]
    parent_role = PLACEMENT_START["adoption"]["parent_role"]
    descriptive: list[Event] = []
    for event in project.events:
        if event.type != "adoption":
            continue
        has_child = any(p.role == child_role for p in event.participants)
        has_parent = any(p.role == parent_role for p in event.participants)
        if has_child and not has_parent:
            descriptive.append(event)
    return descriptive


def _event_signature(event: Event) -> tuple:
    """An identity-independent signature of an event's observable content."""
    date_value = None if event.date is None else (event.date.value, event.date.precision)
    participants = tuple(
        sorted((p.role, p.person_id) for p in event.participants)
    )
    return (event.id, event.type, date_value, participants)


# ---------------------------------------------------------------------------
# Property 8: Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """Feature: foster-parents, Property 8: Backward compatibility

    Loading a pre-feature project loses no foster/adoptive link; descriptive
    adoption events are preserved and still derive no link; Connection_Overrides
    default to empty when absent; and the validator still accepts the
    ``"foster"`` and ``"adoptive"`` parentage types.

    **Validates: Requirements 13.1, 13.3, 13.4, 13.5**
    """

    @given(fp=foster_project())
    @settings(max_examples=100, deadline=None)
    def test_no_foster_adoptive_link_lost_on_load(self, fp) -> None:
        """No foster/adoptive link is lost across the load path (Req 13.3).

        Every foster/adoptive ``(child_id, parent_id, parentage_type)`` link
        present BEFORE ``migrate_orphan_links`` is still present AFTER it.

        Feature: foster-parents, Property 8
        **Validates: Requirement 13.3**
        """
        project = copy.deepcopy(fp.project)
        before = _derived_link_set(project)

        migrate_orphan_links(project)

        after = _derived_link_set(project)
        missing = before - after
        assert not missing, (
            f"the load path dropped foster/adoptive links: {missing}"
        )

    @given(fp=foster_project())
    @settings(max_examples=100, deadline=None)
    def test_descriptive_adoption_events_preserved(self, fp) -> None:
        """Descriptive adoption events survive the load path unchanged (Req 13.5).

        Every pre-existing ``adoption`` event that names a child but NO
        adoptive-parent participant is still present and unchanged after the
        load path, and still derives no link.

        Feature: foster-parents, Property 8
        **Validates: Requirement 13.5**
        """
        project = copy.deepcopy(fp.project)

        before = _descriptive_adoption_events(project)
        before_signatures = {ev.id: _event_signature(ev) for ev in before}
        before_links = _derived_link_set(project)

        migrate_orphan_links(project)

        after_by_id = {ev.id: ev for ev in project.events}
        for event_id, signature in before_signatures.items():
            assert event_id in after_by_id, (
                f"descriptive adoption event {event_id} was dropped by the load path"
            )
            assert _event_signature(after_by_id[event_id]) == signature, (
                f"descriptive adoption event {event_id} was altered by the load path"
            )

        # A descriptive event names no parent, so it can derive no new link:
        # the set of (child) ids that gained an adoptive link must not come from
        # a purely-descriptive event. Concretely, every descriptive event's
        # child must not have acquired a link whose parent is itself.
        after_links = _derived_link_set(project)
        for event in before:
            child_ids = {
                p.person_id
                for p in event.participants
                if p.role == PLACEMENT_START["adoption"]["child_role"]
            }
            for child_id in child_ids:
                # The descriptive event introduced no parent, so it cannot be
                # the origin of any new adoptive link for its child. Any adoptive
                # link for that child must already have existed (via a real
                # parent-bearing set), never conjured from the descriptive event.
                new_links_for_child = {
                    link
                    for link in (after_links - before_links)
                    if link[1] == child_id and link[0] == "adoptive"
                }
                # Each such new link must trace to a parent-bearing event, i.e.
                # a backing adoption start event naming that (child, parent).
                for _, lc, lp in new_links_for_child:
                    backed = any(
                        ev.type == "adoption"
                        and any(
                            p.role == "adopterad" and p.person_id == lc
                            for p in ev.participants
                        )
                        and any(
                            p.role == "adoptivförälder" and p.person_id == lp
                            for p in ev.participants
                        )
                        for ev in project.events
                    )
                    assert backed, (
                        "an adoptive link appeared with no parent-bearing adoption "
                        f"event to back it: child={lc} parent={lp}"
                    )

    @given(fp=foster_project())
    @settings(max_examples=100, deadline=None)
    def test_overrides_default_empty_when_key_absent(self, fp) -> None:
        """A payload without ``connection_overrides`` deserializes to ``{}`` (Req 13.1/13.4).

        Serialize a Hypothesis-generated project, strip the
        ``connection_overrides`` key from the JSON payload to model a pre-feature
        file, deserialize, and assert the overrides default to an empty dict.

        Feature: foster-parents, Property 8
        **Validates: Requirements 13.1, 13.4**
        """
        project = copy.deepcopy(fp.project)

        payload = json.loads(serialize(project))
        # Model a pre-feature file: the key simply does not exist.
        payload.pop("connection_overrides", None)
        assert "connection_overrides" not in payload

        restored = deserialize(json.dumps(payload, ensure_ascii=False))

        assert restored.connection_overrides == {}, (
            "a project payload lacking connection_overrides must load with an "
            "empty overrides dict"
        )

    @given(fp=foster_project())
    @settings(max_examples=100, deadline=None)
    def test_empty_overrides_omitted_then_reload_empty(self, fp) -> None:
        """A project with no overrides omits the key and reloads empty (Req 13.1).

        When a project carries no Connection_Overrides, the serializer omits the
        key entirely, and deserializing that payload yields an empty overrides
        dict.

        Feature: foster-parents, Property 8
        **Validates: Requirements 13.1**
        """
        project = copy.deepcopy(fp.project)
        project.connection_overrides = {}

        serialized = serialize(project)
        payload = json.loads(serialized)
        assert "connection_overrides" not in payload, (
            "an empty overrides map must be omitted from the written file"
        )

        restored = deserialize(serialized)
        assert restored.connection_overrides == {}


class TestValidParentageTypesAccepted:
    """Feature: foster-parents, Property 8: valid parentage types still accepted

    The load path must not reject the non-biological parentage types, so the
    validator's ``_VALID_PARENTAGE_TYPES`` set keeps accepting ``"foster"`` and
    ``"adoptive"`` (Req 13.4).

    **Validates: Requirement 13.4**
    """

    def test_foster_and_adoptive_are_valid_parentage_types(self) -> None:
        """``_VALID_PARENTAGE_TYPES`` contains foster and adoptive (Req 13.4).

        Feature: foster-parents, Property 8
        **Validates: Requirement 13.4**
        """
        assert "foster" in _VALID_PARENTAGE_TYPES
        assert "adoptive" in _VALID_PARENTAGE_TYPES
