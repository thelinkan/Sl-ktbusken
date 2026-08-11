# Feature: residence-periods, Property 19: The residents query returns, labels and orders entries correctly
"""Property-based test for the residents query.

Feature: residence-periods, Property 19: The residents query returns, labels and orders entries correctly

For any consistent Project and any queried place and year, `residents_of_place`
returns one entry per matching Residence_Fact whose Possible_Span shares at
least one day with the queried year (no merging); labels each entry "säker" when
the queried year overlaps the Certain_Core by at least one day, "möjlig" when it
overlaps only the Possible_Span or the core is empty; marks a both-sides-
unbounded Possible_Span as "möjlig" with `undated=True` matching every year and
sorting last; and orders entries by label ("säker" first), then place display
name in Swedish alphabetical order, then person display name, then ascending
Residence_Fact `id`.

**Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.9, 8.10**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.date_span import overlaps, year_span
from slaktbusken.model.residence import certain_core, possible_span
from slaktbusken.services.residence_query import (
    LABEL_CERTAIN,
    LABEL_POSSIBLE,
    ResidentEntry,
    residents_of_place,
    swedish_sort_key,
)
from tests.test_model.residence_strategies import consistent_projects


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _place_subtree_ids(place_id: str, data) -> set[str]:
    """Collect place_id and all descendant place_ids breadth-first to 10 levels."""
    from slaktbusken.services.residence_query import MAX_DESCENDANT_LEVELS

    children_by_parent: dict[str, list[str]] = {}
    for place in data.places:
        parent = place.parent_place_id
        if parent:
            children_by_parent.setdefault(parent, []).append(place.id)

    visited: set[str] = {place_id}
    level: list[str] = [place_id]
    for depth in range(MAX_DESCENDANT_LEVELS):
        next_level: list[str] = []
        for pid in level:
            for child_id in children_by_parent.get(pid, ()):
                if child_id not in visited:
                    visited.add(child_id)
                    next_level.append(child_id)
        if not next_level:
            break
        level = next_level

    return visited


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


class TestResidentsQuery:
    """Property 19: The residents query returns, labels and orders entries correctly.

    One entry per matching fact (no merging), "säker" when year overlaps core,
    "möjlig" otherwise, unbounded spans match every year as "möjlig" + undated,
    ordering by label then place then person then id.

    **Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.9, 8.10**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_residents_query_property(self, data: st.DataObject) -> None:
        """The residents query returns, labels and orders entries correctly.

        Feature: residence-periods, Property 19: The residents query returns, labels and orders entries correctly

        **Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.9, 8.10**
        """
        project = data.draw(
            consistent_projects(
                min_persons=1,
                max_persons=4,
                min_places=1,
                max_places=4,
                max_sources=2,
                max_events=2,
                min_residences=1,
                max_residences=6,
                include_many_observations=False,
            )
        )

        if not project.places:
            return

        # Pick a place to query
        queried_place = data.draw(st.sampled_from(project.places))
        # Pick a year in the plausible range
        year = data.draw(st.integers(min_value=1500, max_value=2100))

        # --- Run the query ---
        entries = residents_of_place(project, queried_place.id, year)

        # --- Compute expected matching facts independently ---
        subtree_ids = _place_subtree_ids(queried_place.id, project)
        queried_year = year_span(year)

        expected_matches: list[tuple[str, str]] = []  # (residence_id, expected_label)
        for fact in project.residences:
            if fact.place_id not in subtree_ids:
                continue
            span = possible_span(fact)
            if not span.overlaps_year(year):
                continue
            # Determine the label
            core = certain_core(fact)
            if core is not None and overlaps(core, queried_year):
                expected_matches.append((fact.id, LABEL_CERTAIN))
            else:
                expected_matches.append((fact.id, LABEL_POSSIBLE))

        # --- ASSERTION 1: One entry per matching fact, no merging (Req 8.1) ---
        entry_ids = [entry.residence_id for entry in entries]
        expected_ids = [rid for rid, _ in expected_matches]
        assert sorted(entry_ids) == sorted(expected_ids), (
            f"Entry ids {sorted(entry_ids)} != expected {sorted(expected_ids)}"
        )

        # --- ASSERTION 2: Labels are correct (Req 8.2, 8.3, 8.4) ---
        expected_labels = {rid: label for rid, label in expected_matches}
        for entry in entries:
            assert entry.label == expected_labels[entry.residence_id], (
                f"Entry {entry.residence_id}: label={entry.label!r}, "
                f"expected={expected_labels[entry.residence_id]!r}"
            )

        # --- ASSERTION 3: Undated marking (Req 8.9) ---
        # An entry is undated iff its Possible_Span is unbounded in both directions.
        facts_by_id = {fact.id: fact for fact in project.residences}
        for entry in entries:
            fact = facts_by_id[entry.residence_id]
            span = possible_span(fact)
            expected_undated = span.is_unbounded_both()
            assert entry.undated == expected_undated, (
                f"Entry {entry.residence_id}: undated={entry.undated}, "
                f"expected={expected_undated}"
            )
            # Undated entries are always "möjlig" (unless core matches, which can't
            # happen with both bounds unbounded producing an always-None core)
            if expected_undated:
                assert entry.label == LABEL_POSSIBLE

        # --- ASSERTION 4: Ordering (Req 8.1, 8.9) ---
        # label (säker=0, möjlig=1), undated last, place Swedish, person Swedish, id
        for i in range(len(entries) - 1):
            a, b = entries[i], entries[i + 1]
            key_a = (
                0 if a.label == LABEL_CERTAIN else 1,
                1 if a.undated else 0,
                swedish_sort_key(a.place_display),
                swedish_sort_key(a.person_display),
                a.residence_id,
            )
            key_b = (
                0 if b.label == LABEL_CERTAIN else 1,
                1 if b.undated else 0,
                swedish_sort_key(b.place_display),
                swedish_sort_key(b.person_display),
                b.residence_id,
            )
            assert key_a <= key_b, (
                f"Ordering violated at positions {i},{i+1}: "
                f"{key_a} > {key_b}"
            )

        # --- ASSERTION 5: Entry fields are populated (Req 8.5) ---
        persons_by_id = {p.id: p for p in project.persons}
        places_by_id = {p.id: p for p in project.places}
        for entry in entries:
            fact = facts_by_id[entry.residence_id]
            # person_id matches
            assert entry.person_id == fact.person_id
            # place_id matches
            assert entry.place_id == fact.place_id
            # role_in_household is the stored value (never omitted)
            assert entry.role_in_household == fact.role_in_household
            # place_display is the place name (or id if unresolved)
            place = places_by_id.get(fact.place_id)
            if place is not None:
                assert entry.place_display == place.name
            # person_display is derivable from the person
            person = persons_by_id.get(fact.person_id)
            if person is not None and person.names:
                name = person.names[0]
                expected_display = f"{name.given} {name.surname}".strip()
                if expected_display:
                    assert entry.person_display == expected_display
            # place_chain is non-empty and starts with the queried place name
            assert len(entry.place_chain) >= 1
            expected_root_name = (
                queried_place.name
                if queried_place.id in {p.id for p in project.places}
                else queried_place.id
            )
            assert entry.place_chain[0] == expected_root_name
            # place_chain ends with the entry's place display
            assert entry.place_chain[-1] == entry.place_display

        # --- ASSERTION 6: Both-sides-unbounded spans match every year (Req 8.9) ---
        # Verified implicitly: if a fact has an unbounded span and place is in
        # the subtree, it must appear in the results regardless of year.
        for fact in project.residences:
            if fact.place_id not in subtree_ids:
                continue
            span = possible_span(fact)
            if span.is_unbounded_both():
                assert fact.id in entry_ids, (
                    f"Unbounded fact {fact.id} not in results for year {year}"
                )
