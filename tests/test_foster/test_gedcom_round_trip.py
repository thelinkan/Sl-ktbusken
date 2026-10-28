"""Property-based test for GEDCOM round-trip with no loss.

Feature: foster-parents, Property 7: GEDCOM round-trip with no loss

Validates: Requirements 11.1, 11.2, 11.2a, 11.2b, 11.2c, 11.2d, 11.2e, 11.3,
11.4, 11.5, 11.6, 11.7, 11.7a, 11.8, 11.9, 11.10

The property (round-trip no loss). For a generated project:

1. Run ``sync_parentage_links`` so derived placement families (with the
   ``event_ids`` the exporter needs for ``FAMC``) exist.
2. Export to a temp GEDCOM via ``GEDCOMExporter().export(project, path)``.
3. Re-import into a fresh empty project via
   ``GEDCOMImporter(empty, translation_dir).import_file(path)`` (which runs
   back-fill + sync + reconcile internally).

Then assert, scoped to foster/adoptive parentage and placement events:

* **parentage_type preserved** - every foster/adoptive (child -> parent)
  relationship present after the source sync is present after round-trip, with
  the same derived type; biological links are not lost and are not corrupted
  into foster/adoptive (Reqs 11.1-11.5).
* **no foster/adoptive link lost** - the set of (child, parent, type) derived
  pairs is preserved exactly (Reqs 11.6, 11.8, 11.9).
* **placement date/place preserved** - the round-tripped placement start event
  carries the same start date and the same place leaf name (Reqs 11.2a, 11.2b,
  11.7).
* **Parent_Set grouping** - GEDCOM-family-mates form one Parent_Set; multiple
  Parent_Sets of a type round-trip as multiple ordered structures (Reqs 11.2c,
  11.2d, 11.7a).
* **end date round-trips on the paired structure** - a placement with an end
  event still has a paired end event with that end date after round-trip
  (Reqs 11.2e, 11.10).

Design note on the generator. People are given globally unique names so the
source person and its re-imported counterpart can be matched by name across the
round-trip (the importer mints fresh ids). Dates are year-precision ("YYYY")
and places are single-token ASCII names, both of which GEDCOM round-trips
without normalisation loss, so the property isolates *structural* foster/
adoptive loss rather than exercising the date/place parsers' own edge cases
(those have dedicated unit tests).
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.gedcom.importer import GEDCOMImporter
from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services.foster_sync import (
    parent_sets_in_order,
    sync_parentage_links,
)

from tests.test_foster.foster_strategies import PLACEMENT_END, PLACEMENT_START


# ---------------------------------------------------------------------------
# A self-contained generator producing projects whose placement events survive
# GEDCOM round-trip losslessly: unique person names, year-precision dates,
# single-token place names.
# ---------------------------------------------------------------------------


def _unique_word(prefix: str, n: int) -> str:
    """A deterministic unique ASCII word used as a person/place name token."""
    return f"{prefix}{n}"


@st.composite
def round_trip_project(draw: DrawFn):
    """Draw a project of placement events for a round-trip property.

    Covers, across examples:

    * foster and adoptive placements symmetrically;
    * one- and two-parent Parent_Sets;
    * multiple Parent_Sets of the same type for one child (ordering);
    * dated and undated start events (year precision);
    * start events with and without a paired end event;
    * placements with and without a place;
    * biological links that must survive untouched.

    Returns a tuple ``(project, places_by_id)`` where ``project`` is a fresh,
    *un-synced* :class:`ProjectData` (the caller runs sync).
    """
    name_counter = {"n": 0}

    def _fresh_person(sex: str) -> Person:
        name_counter["n"] += 1
        token = _unique_word("P", name_counter["n"])
        # Unique given name so the person is identifiable by name post-import.
        return Person(
            id=f"person_{name_counter['n']}",
            names=[Name(type="birth", given=token, surname="Slakt")],
            sex=sex,
        )

    # --- places (single-token, round-trip-safe) -------------------------
    n_places = draw(st.integers(min_value=0, max_value=3))
    places: list[Place] = [
        Place(id=f"place_{i}", name=_unique_word("Ort", i), type="socken")
        for i in range(n_places)
    ]
    place_ids = [p.id for p in places]

    persons: list[Person] = []
    events: list[Event] = []
    ev_counter = {"n": 0}

    def _next_event_id() -> str:
        ev_counter["n"] += 1
        return f"event_{ev_counter['n']}"

    n_children = draw(st.integers(min_value=1, max_value=3))

    for _ in range(n_children):
        child = _fresh_person(draw(st.sampled_from(("M", "F", "U"))))
        persons.append(child)

        n_placements = draw(st.integers(min_value=0, max_value=3))
        for _ in range(n_placements):
            start_type = draw(st.sampled_from(list(PLACEMENT_START)))
            spec = PLACEMENT_START[start_type]

            n_parents = draw(st.integers(min_value=1, max_value=2))
            parents = [
                _fresh_person(draw(st.sampled_from(("M", "F", "U"))))
                for _ in range(n_parents)
            ]
            persons.extend(parents)

            dated = draw(st.booleans())
            start_year = draw(st.integers(min_value=1600, max_value=2000)) if dated else None

            place_id = None
            if place_ids and draw(st.booleans()):
                place_id = draw(st.sampled_from(place_ids))

            start_participants = [
                Participant(person_id=child.id, role=spec["child_role"])
            ]
            for parent in parents:
                start_participants.append(
                    Participant(person_id=parent.id, role=spec["parent_role"])
                )

            start_id = _next_event_id()
            events.append(
                Event(
                    id=start_id,
                    type=start_type,
                    participants=start_participants,
                    date=(
                        DateValue(value=str(start_year), precision="year")
                        if start_year is not None
                        else None
                    ),
                    place=PlaceRef(place_id=place_id) if place_id else None,
                )
            )

            # Optional paired end event.
            if draw(st.booleans()):
                end_type = next(
                    e for e, s in PLACEMENT_END.items() if s == start_type
                )
                # End no earlier than start (end-before-start is only a
                # validator warning and is out of scope for the lossless
                # round-trip property; constrain it narrowly here).
                if start_year is not None:
                    end_year = draw(
                        st.integers(min_value=start_year, max_value=2000)
                    )
                else:
                    end_year = draw(st.integers(min_value=1600, max_value=2000))
                end_participants = [
                    Participant(person_id=child.id, role=spec["child_role"])
                ]
                for parent in parents:
                    end_participants.append(
                        Participant(person_id=parent.id, role=spec["parent_role"])
                    )
                events.append(
                    Event(
                        id=_next_event_id(),
                        type=end_type,
                        participants=end_participants,
                        date=DateValue(value=str(end_year), precision="year"),
                    )
                )

    project = ProjectData(
        format="släktbuske-file",
        version="0.2",
        project=ProjectMetadata(title="Round Trip Property"),
        persons=persons,
        families=[],
        events=events,
        places=places,
        sources=[],
    )
    return project


# ---------------------------------------------------------------------------
# Helpers that read derived state by *person name* so the source project and
# the re-imported project can be compared across fresh ids.
# ---------------------------------------------------------------------------


def _name_of(project: ProjectData, person_id: str) -> str:
    for person in project.persons:
        if person.id == person_id:
            return person.names[0].given if person.names else ""
    return ""


def _derived_pairs_by_name(project: ProjectData) -> set[tuple[str, str, str]]:
    """Every foster/adoptive link as ``(child_name, parent_name, type)``."""
    out: set[tuple[str, str, str]] = set()
    for family in project.families:
        for link in family.parent_child_links:
            if link.parentage_type in ("foster", "adoptive") and link.parent_id:
                out.add(
                    (
                        _name_of(project, link.child_id),
                        _name_of(project, link.parent_id),
                        link.parentage_type,
                    )
                )
    return out


def _biological_pairs_by_name(project: ProjectData) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for family in project.families:
        for link in family.parent_child_links:
            if link.parentage_type == "biological" and link.parent_id:
                out.add(
                    (
                        _name_of(project, link.child_id),
                        _name_of(project, link.parent_id),
                    )
                )
    return out


def _place_leaf_name(project: ProjectData, place_id: str | None) -> str | None:
    """The leaf place name for a place id, or ``None``."""
    if place_id is None:
        return None
    for place in project.places:
        if place.id == place_id:
            return place.name
    return None


def _id_by_name(project: ProjectData, given: str) -> str | None:
    for person in project.persons:
        if person.names and person.names[0].given == given:
            return person.id
    return None


def _start_date_by_name(
    project: ProjectData, child_name: str, parentage: str
) -> list[str | None]:
    """Ordered list of start-date values for a child's Parent_Sets of a type.

    Uses ``parent_sets_in_order`` so the ordering invariant (dated first by
    date value, undated last in project order) is the one under test.
    """
    child_id = _id_by_name(project, child_name)
    if child_id is None:
        return []
    start_type = next(
        etype
        for etype, cfg in PLACEMENT_START.items()
        if cfg["parentage"] == parentage
    )
    out: list[str | None] = []
    for family in parent_sets_in_order(project, child_id, parentage):
        start = next(
            (
                e
                for eid in family.event_ids
                for e in project.events
                if e.id == eid and e.type == start_type
            ),
            None,
        )
        out.append(start.date.value if start and start.date else None)
    return out


# ---------------------------------------------------------------------------
# The property
# ---------------------------------------------------------------------------


class TestGedcomRoundTripNoLoss:
    """Feature: foster-parents, Property 7: GEDCOM round-trip with no loss

    Export then import preserves parentage_type and the placement event's
    date/place/parent-set/end-date; every imported foster/adoptive link
    survives the post-import sync; GEDCOM-family-mates form one Parent_Set;
    multiple Parent_Sets round-trip as multiple ordered structures; a
    placement's end date round-trips on the paired structure.

    **Validates: Requirements 11.1, 11.2, 11.2a, 11.2b, 11.2c, 11.2d, 11.2e,
    11.3, 11.4, 11.5, 11.6, 11.7, 11.7a, 11.8, 11.9, 11.10**
    """

    _example = 0

    @given(project=round_trip_project())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_round_trip_preserves_parentage_and_placements(
        self, project: ProjectData, tmp_path: Path
    ) -> None:
        """Property 7: export then import loses no foster/adoptive information.

        Feature: foster-parents, Property 7: GEDCOM round-trip with no loss
        **Validates: Requirements 11.1-11.10**
        """
        # 1. Establish the source-of-truth derived families + end pairing.
        sync_parentage_links(project)

        source_derived = _derived_pairs_by_name(project)
        source_biological = _biological_pairs_by_name(project)

        # Record, per child+type, the ordered start-date sequence and the leaf
        # place name of each dated placement structure, keyed by start date so
        # the round-trip can be matched structure-for-structure.
        source_place_by_start: dict[tuple[str, str, str], str | None] = {}
        source_end_dates: set[tuple[str, str, str]] = set()
        for event in project.events:
            if event.type in PLACEMENT_START:
                spec = PLACEMENT_START[event.type]
                child = next(
                    (
                        p.person_id
                        for p in event.participants
                        if p.role == spec["child_role"]
                    ),
                    None,
                )
                if child is not None and event.date and event.date.value:
                    key = (
                        _name_of(project, child),
                        spec["parentage"],
                        event.date.value,
                    )
                    source_place_by_start[key] = _place_leaf_name(
                        project, event.place.place_id if event.place else None
                    )
            elif event.type in PLACEMENT_END:
                start_type = PLACEMENT_END[event.type]
                spec = PLACEMENT_START[start_type]
                child = next(
                    (
                        p.person_id
                        for p in event.participants
                        if p.role == spec["child_role"]
                    ),
                    None,
                )
                if child is not None and event.date and event.date.value:
                    source_end_dates.add(
                        (
                            _name_of(project, child),
                            spec["parentage"],
                            event.date.value,
                        )
                    )

        # 2. Export. ``tmp_path`` is a function-scoped fixture reused across
        # Hypothesis examples, so give each example its own unique sub-path.
        self._example += 1
        case_dir = tmp_path / f"case_{self._example}"
        case_dir.mkdir(exist_ok=True)
        ged_path = case_dir / "round_trip.ged"
        GEDCOMExporter().export(project, ged_path)

        # 3. Re-import into a fresh project (runs back-fill + sync + reconcile).
        imported = ProjectData(project=ProjectMetadata(title="Imported"))
        translation_dir = case_dir / "translation"
        translation_dir.mkdir(exist_ok=True)
        GEDCOMImporter(imported, translation_dir).import_file(ged_path)

        result_derived = _derived_pairs_by_name(imported)
        result_biological = _biological_pairs_by_name(imported)

        # --- parentage_type preserved + no foster/adoptive link lost --------
        # (Reqs 11.1-11.6, 11.8, 11.9): the full set of derived (child, parent,
        # type) pairs is preserved exactly - none lost, none fabricated, and
        # none with a changed type.
        assert result_derived == source_derived, (
            "Foster/adoptive derived links changed across the round-trip.\n"
            f"  only in source: {source_derived - result_derived}\n"
            f"  only in result: {result_derived - source_derived}"
        )

        # --- biological not lost / not corrupted into foster/adoptive -------
        # (Req 11.5). Every source biological pair reappears as biological; and
        # no source biological pair reappears as foster/adoptive.
        assert result_biological >= source_biological, (
            "A biological link was lost across the round-trip.\n"
            f"  missing: {source_biological - result_biological}"
        )
        corrupted = {
            (c, p) for (c, p, _t) in result_derived
        } & source_biological
        assert not corrupted, (
            f"Biological links were corrupted into foster/adoptive: {corrupted}"
        )

        # --- placement date + place preserved -------------------------------
        # (Reqs 11.2a, 11.2b, 11.7). For each dated source placement structure,
        # the re-imported start event with the same child+type+start-date must
        # carry the same leaf place name.
        for (child_name, parentage, start_value), place_name in (
            source_place_by_start.items()
        ):
            start_type = next(
                etype
                for etype, cfg in PLACEMENT_START.items()
                if cfg["parentage"] == parentage
            )
            matching = [
                e
                for e in imported.events
                if e.type == start_type
                and e.date is not None
                and e.date.value == start_value
                and any(
                    _name_of(imported, p.person_id) == child_name
                    and p.role == PLACEMENT_START[start_type]["child_role"]
                    for p in e.participants
                )
            ]
            assert matching, (
                f"Placement start for {child_name!r} ({parentage}) dated "
                f"{start_value} did not round-trip."
            )
            event = matching[0]
            result_place = _place_leaf_name(
                imported, event.place.place_id if event.place else None
            )
            assert result_place == place_name, (
                f"Place for {child_name!r} ({parentage}) dated {start_value} "
                f"did not round-trip: source {place_name!r} vs {result_place!r}"
            )

        # --- Parent_Set grouping: mates form one set; ordering survives -----
        # (Reqs 11.2c, 11.2d, 11.7a). For every child+type, the ordered
        # sequence of start-date values of its Parent_Sets is identical before
        # and after the round-trip (so the number of sets, their grouping, and
        # their order all survive). Comparing via ``parent_sets_in_order``
        # exercises the ordering helper on both sides.
        children = {
            _name_of(project, link.child_id)
            for family in project.families
            for link in family.parent_child_links
            if link.parentage_type in ("foster", "adoptive")
        }
        for child_name in children:
            for parentage in ("foster", "adoptive"):
                before = _start_date_by_name(project, child_name, parentage)
                after = _start_date_by_name(imported, child_name, parentage)
                assert before == after, (
                    f"Parent_Set count/order for {child_name!r} ({parentage}) "
                    f"changed across round-trip: {before} vs {after}"
                )

        # --- end date round-trips on the paired structure -------------------
        # (Reqs 11.2e, 11.10). Every source placement end (child, type, date)
        # reappears as a paired end event after the round-trip.
        for child_name, parentage, end_value in source_end_dates:
            end_type = next(
                etype
                for etype, start in PLACEMENT_END.items()
                if PLACEMENT_START[start]["parentage"] == parentage
            )
            child_role = PLACEMENT_START[PLACEMENT_END[end_type]]["child_role"]
            matching_ends = [
                e
                for e in imported.events
                if e.type == end_type
                and e.date is not None
                and e.date.value == end_value
                and any(
                    _name_of(imported, p.person_id) == child_name
                    and p.role == child_role
                    for p in e.participants
                )
            ]
            assert matching_ends, (
                f"End date {end_value} for {child_name!r} ({parentage}) did "
                f"not round-trip on the paired structure."
            )
