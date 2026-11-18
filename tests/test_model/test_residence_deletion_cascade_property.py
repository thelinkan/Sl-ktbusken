# Feature: residence-periods, Property 7: Deletion cascades, clears and blocks as specified
"""Property-based test for deletion cascade, clearing and blocking.

Feature: residence-periods, Property 7: Deletion cascades, clears and blocks
as specified

For any Project, deleting a person removes exactly that person's
Residence_Facts together with their Observations and leaves every other
Residence_Fact unchanged; deleting an Event sets `event_id` to absent on every
referencing Endpoint while leaving `earliest`, `latest` and `precision`
unchanged and deleting no fact; requesting deletion of a place referenced by one
or more Residence_Facts, or by a Flytt_Event `from_place`, is refused with one
blocking dependency entry per referencing entity and leaves the place and the
`residences` collection unchanged.

**Validates: Requirements 1.8, 1.9, 3.11, 18.17**
"""

from __future__ import annotations

import copy
from typing import Optional

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.event import Event, Participant, PlaceRef, DateValue
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.services.delete_service import (
    clear_event_from_residence_endpoints,
    execute_person_deletion,
    find_place_event_dependencies,
    find_residence_dependencies,
    ResidenceDependency,
)
from tests.test_model.residence_strategies import consistent_projects


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


@st.composite
def _projects_with_flytt_from_place(draw: DrawFn) -> ProjectData:
    """Generate a consistent project that may include flytt events with from_place set.

    This extends `consistent_projects` by optionally adding `from_place` to flytt
    events so that the place-blocking via `from_place` path can be exercised.
    """
    project = draw(
        consistent_projects(
            min_persons=2,
            max_persons=4,
            min_places=2,
            max_places=4,
            max_events=5,
            min_residences=1,
            max_residences=6,
        )
    )

    place_ids = [p.id for p in project.places]

    # Optionally set from_place on flytt events.
    for event in project.events:
        if event.type == "flytt" and draw(st.booleans()):
            event.from_place = PlaceRef(
                place_id=draw(st.sampled_from(place_ids))
            )

    return project


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestDeletionCascadeClearingAndBlocking:
    """Property 7: Deletion cascades, clears and blocks as specified.

    **Validates: Requirements 1.8, 1.9, 3.11, 18.17**
    """

    @given(data=st.data(), project=_projects_with_flytt_from_place())
    @settings(max_examples=100, deadline=None)
    def test_deletion_cascades_clears_and_blocks(
        self,
        data: st.DataObject,
        project: ProjectData,
    ) -> None:
        """Person deletion removes residences; event deletion clears event_id;
        place blocking reports one entry per referencing fact.

        Feature: residence-periods, Property 7: Deletion cascades, clears and blocks as specified

        **Validates: Requirements 1.8, 1.9, 3.11, 18.17**
        """
        # --- Sub-property A: Person deletion ---
        # Pick a person to delete and snapshot the residences before.
        person_id = data.draw(
            st.sampled_from([p.id for p in project.persons]),
            label="person_to_delete",
        )

        # Deep-copy so we can test the before/after state.
        project_for_person_deletion = copy.deepcopy(project)

        person_residences_before = [
            r for r in project_for_person_deletion.residences
            if r.person_id == person_id
        ]
        other_residences_before = [
            copy.deepcopy(r)
            for r in project_for_person_deletion.residences
            if r.person_id != person_id
        ]

        execute_person_deletion(person_id, project_for_person_deletion)

        # Requirement 1.8: every Residence_Fact of the deleted person is gone.
        remaining_ids = {r.id for r in project_for_person_deletion.residences}
        for r in person_residences_before:
            assert r.id not in remaining_ids, (
                f"Residence {r.id!r} of deleted person {person_id!r} "
                f"still present after deletion"
            )

        # Requirement 1.8: every other Residence_Fact is unchanged.
        for expected in other_residences_before:
            matches = [
                r for r in project_for_person_deletion.residences
                if r.id == expected.id
            ]
            assert len(matches) == 1, (
                f"Residence {expected.id!r} of another person should survive "
                f"person deletion"
            )
            actual = matches[0]
            assert actual.person_id == expected.person_id
            assert actual.place_id == expected.place_id
            assert actual.start.earliest == expected.start.earliest
            assert actual.start.latest == expected.start.latest
            assert actual.end.earliest == expected.end.earliest
            assert actual.end.latest == expected.end.latest
            assert len(actual.observations) == len(expected.observations)

        # --- Sub-property B: Event deletion clears event_id ---
        project_for_event_clear = copy.deepcopy(project)

        # Ensure at least one residence has an event_id set so we exercise clearing.
        if project_for_event_clear.events and project_for_event_clear.residences:
            # Pick an event and link some endpoints to it.
            event_to_clear = data.draw(
                st.sampled_from(project_for_event_clear.events),
                label="event_to_clear",
            )
            # Link a random subset of residence endpoints to this event.
            for residence in project_for_event_clear.residences:
                if data.draw(st.booleans(), label="link_start"):
                    residence.start.event_id = event_to_clear.id
                if data.draw(st.booleans(), label="link_end"):
                    residence.end.event_id = event_to_clear.id

            # Snapshot endpoints before clearing.
            endpoint_snapshots: list[
                tuple[str, str, Optional[str], Optional[str], Optional[str], Optional[str]]
            ] = []
            for r in project_for_event_clear.residences:
                endpoint_snapshots.append((
                    r.id,
                    "start",
                    r.start.event_id,
                    r.start.earliest,
                    r.start.latest,
                    r.start.precision,
                ))
                endpoint_snapshots.append((
                    r.id,
                    "end",
                    r.end.event_id,
                    r.end.earliest,
                    r.end.latest,
                    r.end.precision,
                ))

            residence_count_before = len(project_for_event_clear.residences)

            # Clear the event from all endpoints.
            clear_event_from_residence_endpoints(
                {event_to_clear.id}, project_for_event_clear
            )

            # Requirement 3.11: no Residence_Fact is deleted.
            assert len(project_for_event_clear.residences) == residence_count_before, (
                "Event clearing must not delete any Residence_Fact"
            )

            # Requirement 3.11: event_id is cleared, but earliest/latest/precision unchanged.
            for r in project_for_event_clear.residences:
                for side, ep in [("start", r.start), ("end", r.end)]:
                    # Find the snapshot for this endpoint.
                    snap = next(
                        s for s in endpoint_snapshots
                        if s[0] == r.id and s[1] == side
                    )
                    _, _, old_event_id, old_earliest, old_latest, old_precision = snap

                    if old_event_id == event_to_clear.id:
                        # The event_id must now be None.
                        assert ep.event_id is None, (
                            f"Endpoint {r.id}.{side} should have event_id "
                            f"cleared after event deletion"
                        )
                    else:
                        # Unrelated event_id must be unchanged.
                        assert ep.event_id == old_event_id

                    # Requirement 3.11: bounds and precision always unchanged.
                    assert ep.earliest == old_earliest, (
                        f"earliest on {r.id}.{side} should not change"
                    )
                    assert ep.latest == old_latest, (
                        f"latest on {r.id}.{side} should not change"
                    )
                    assert ep.precision == old_precision, (
                        f"precision on {r.id}.{side} should not change"
                    )

        # --- Sub-property C: Place blocking via residences ---
        if project.places and project.residences:
            place_to_check = data.draw(
                st.sampled_from([p.id for p in project.places]),
                label="place_to_block",
            )

            # Snapshot the collection before the check.
            residences_before_block = copy.deepcopy(project.residences)
            places_before_block = copy.deepcopy(project.places)

            deps = find_residence_dependencies(place_to_check, project)

            # Requirement 1.9: one entry per referencing Residence_Fact.
            referencing_facts = [
                r for r in project.residences if r.place_id == place_to_check
            ]
            assert len(deps) == len(referencing_facts), (
                f"Expected {len(referencing_facts)} blocking entries for place "
                f"{place_to_check!r}, got {len(deps)}"
            )

            # Each entry references the correct residence.
            dep_residence_ids = {d.residence_id for d in deps}
            for r in referencing_facts:
                assert r.id in dep_residence_ids, (
                    f"Residence {r.id!r} references place but is not in deps"
                )

            # The place and residences collection are unchanged (read-only check).
            assert project.residences == residences_before_block
            assert project.places == places_before_block

        # --- Sub-property D: Place blocking via Flytt from_place ---
        if project.places and project.events:
            place_for_flytt = data.draw(
                st.sampled_from([p.id for p in project.places]),
                label="place_for_flytt_block",
            )

            events_before_block = copy.deepcopy(project.events)

            event_deps = find_place_event_dependencies(place_for_flytt, project)

            # Requirement 18.17: events referencing place via `place` or `from_place`.
            expected_events = [
                e for e in project.events
                if (e.place and e.place.place_id == place_for_flytt)
                or (e.from_place and e.from_place.place_id == place_for_flytt)
            ]
            assert len(event_deps) == len(expected_events), (
                f"Expected {len(expected_events)} event blocking entries for "
                f"place {place_for_flytt!r}, got {len(event_deps)}"
            )

            # The events collection is unchanged.
            assert project.events == events_before_block
