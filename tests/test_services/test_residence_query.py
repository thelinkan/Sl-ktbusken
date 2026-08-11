"""Unit tests for the residents query of the Residence_Query_Service.

Covers Requirements 8.1 (one entry per fact, no merging, ordering), 8.2–8.4
(labelling), 8.5 (entry fields), 8.6 (descendant walk, chains, cycles), 8.7
(residence timeline ordering), 8.8 (no household entity), 8.9
(both-sides-unbounded spans), 8.10 (role grouping) and 15.9 (no lifespan
clamping), plus the worked examples of Requirements 14.8 and 15.5–15.6.
"""

from copy import deepcopy

from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import Endpoint, ResidenceFact
from slaktbusken.services.residence_query import (
    LABEL_CERTAIN,
    LABEL_POSSIBLE,
    LABEL_ROLE_MISSING,
    MAX_DESCENDANT_LEVELS,
    ResidentEntry,
    residence_timeline,
    residents_grouped_by_role,
    residents_of_place,
    swedish_sort_key,
)


def _person(person_id, given="Anders", surname="Andersson"):
    return Person(
        id=person_id,
        sex="M",
        names=[Name(type="birth", given=given, surname=surname)],
    )


def _place(place_id, name, parent_place_id=None):
    return Place(id=place_id, type="farm", name=name, parent_place_id=parent_place_id)


def _fact(
    fact_id,
    person_id="person_1",
    place_id="place_1",
    start=None,
    end=None,
    role="",
):
    return ResidenceFact(
        id=fact_id,
        person_id=person_id,
        place_id=place_id,
        start=start or Endpoint(),
        end=end or Endpoint(),
        role_in_household=role,
    )


def _project(persons=None, places=None, residences=None):
    return ProjectData(
        persons=list(persons or []),
        places=list(places or []),
        residences=list(residences or []),
    )


# --- entry fields (Requirement 8.5) ---


def test_entry_carries_every_required_field():
    data = _project(
        persons=[_person("person_1", "Brita", "Persdotter")],
        places=[_place("place_1", "Norrgården")],
        residences=[
            _fact(
                "residence_1",
                start=Endpoint(earliest="1840", latest="1840"),
                end=Endpoint(earliest="1846", latest="1846"),
                role="piga",
            )
        ],
    )

    entries = residents_of_place(data, "place_1", 1843)

    assert entries == [
        ResidentEntry(
            person_id="person_1",
            person_display="Brita Persdotter",
            residence_id="residence_1",
            place_id="place_1",
            place_display="Norrgården",
            interval_display="1840\u20131846",
            label=LABEL_CERTAIN,
            role_in_household="piga",
            undated=False,
            place_chain=["Norrgården"],
        )
    ]


def test_empty_role_is_an_empty_value_rather_than_omitted():
    data = _project(
        persons=[_person("person_1")],
        places=[_place("place_1", "Åby")],
        residences=[
            _fact(
                "residence_1",
                start=Endpoint(latest="1840"),
                end=Endpoint(earliest="1846"),
            )
        ],
    )

    entry = residents_of_place(data, "place_1", 1843)[0]

    assert entry.role_in_household == ""


def test_the_project_is_left_unchanged():
    data = _project(
        persons=[_person("person_1")],
        places=[_place("place_1", "Åby")],
        residences=[
            _fact(
                "residence_1",
                start=Endpoint(latest="1840"),
                end=Endpoint(earliest="1846"),
            )
        ],
    )
    before = deepcopy(data)

    residents_of_place(data, "place_1", 1843)

    assert data == before


# --- labelling (Requirements 8.2, 8.3, 8.4) ---


def test_year_overlapping_the_certain_core_is_certain():
    data = _project(
        persons=[_person("person_1")],
        places=[_place("place_1", "Åby")],
        residences=[
            _fact(
                "residence_1",
                start=Endpoint(earliest="1838", latest="1840"),
                end=Endpoint(earliest="1846", latest="1848"),
            )
        ],
    )

    for year in (1840, 1843, 1846):
        assert residents_of_place(data, "place_1", year)[0].label == LABEL_CERTAIN


def test_year_inside_the_possible_span_only_is_possible():
    data = _project(
        persons=[_person("person_1")],
        places=[_place("place_1", "Åby")],
        residences=[
            _fact(
                "residence_1",
                start=Endpoint(earliest="1838", latest="1840"),
                end=Endpoint(earliest="1846", latest="1848"),
            )
        ],
    )

    for year in (1838, 1839, 1847, 1848):
        assert residents_of_place(data, "place_1", year)[0].label == LABEL_POSSIBLE


def test_empty_core_is_always_possible():
    # start.latest 1846 falls after end.earliest 1840 → the core is empty.
    data = _project(
        persons=[_person("person_1")],
        places=[_place("place_1", "Åby")],
        residences=[
            _fact(
                "residence_1",
                start=Endpoint(earliest="1838", latest="1846"),
                end=Endpoint(earliest="1840", latest="1848"),
            )
        ],
    )

    for year in (1838, 1842, 1848):
        assert residents_of_place(data, "place_1", year)[0].label == LABEL_POSSIBLE


def test_year_outside_the_possible_span_yields_no_entry():
    # Requirement 14.8: Place B ends 1846, so 1850 returns zero persons.
    data = _project(
        persons=[_person("person_1")],
        places=[_place("place_1", "Åby")],
        residences=[
            _fact(
                "residence_1",
                start=Endpoint(earliest="1840", latest="1840"),
                end=Endpoint(earliest="1846", latest="1846"),
            )
        ],
    )

    assert residents_of_place(data, "place_1", 1850) == []


# --- both endpoints open (Requirements 8.9, 15.5, 15.6, 15.9) ---


def test_both_sides_unbounded_span_matches_every_year_without_clamping():
    data = _project(
        persons=[_person("person_1", "Brita", "Persdotter")],
        places=[_place("place_1", "Åby")],
        residences=[
            _fact(
                "residence_1",
                start=Endpoint(latest="1840"),
                end=Endpoint(earliest="1846"),
            )
        ],
    )

    for year in (1750, 1850, 1980):
        entries = residents_of_place(data, "place_1", year)
        assert len(entries) == 1
        assert entries[0].label == LABEL_POSSIBLE
        assert entries[0].undated is True
        assert entries[0].interval_display == "senast 1840\u2013tidigast 1846"

    for year in (1840, 1843, 1846):
        assert residents_of_place(data, "place_1", year)[0].label == LABEL_CERTAIN


def test_undated_entries_sort_after_every_bounded_entry():
    data = _project(
        persons=[
            _person("person_1", "Anders", "Andersson"),
            _person("person_2", "Brita", "Persdotter"),
        ],
        places=[_place("place_1", "Åby")],
        residences=[
            # Unbounded in both directions → undated, sorts last.
            _fact("residence_1", person_id="person_1"),
            # Bounded möjlig entry.
            _fact(
                "residence_2",
                person_id="person_2",
                start=Endpoint(earliest="1840"),
                end=Endpoint(latest="1860"),
            ),
        ],
    )

    entries = residents_of_place(data, "place_1", 1850)

    assert [entry.residence_id for entry in entries] == ["residence_2", "residence_1"]
    assert [entry.undated for entry in entries] == [False, True]


# --- no merging and ordering (Requirement 8.1) ---


def test_two_facts_of_the_same_person_yield_two_entries():
    data = _project(
        persons=[_person("person_1")],
        places=[_place("place_1", "Åby")],
        residences=[
            _fact(
                "residence_1",
                start=Endpoint(earliest="1840", latest="1840"),
                end=Endpoint(earliest="1846", latest="1846"),
            ),
            _fact(
                "residence_2",
                start=Endpoint(earliest="1842", latest="1842"),
                end=Endpoint(earliest="1848", latest="1848"),
            ),
        ],
    )

    entries = residents_of_place(data, "place_1", 1843)

    assert [entry.residence_id for entry in entries] == ["residence_1", "residence_2"]
    assert {entry.person_id for entry in entries} == {"person_1"}


def test_entries_are_ordered_by_label_then_place_then_person_then_id():
    certain = dict(
        start=Endpoint(earliest="1840", latest="1840"),
        end=Endpoint(earliest="1860", latest="1860"),
    )
    possible = dict(start=Endpoint(earliest="1840"), end=Endpoint(latest="1860"))
    data = _project(
        persons=[
            _person("person_1", "Anders", "Andersson"),
            _person("person_2", "Örjan", "Öberg"),
        ],
        places=[
            _place("place_1", "Ed"),
            _place("place_2", "Åby", parent_place_id="place_1"),
            _place("place_3", "Ösjö", parent_place_id="place_1"),
        ],
        residences=[
            _fact("residence_5", person_id="person_2", place_id="place_3", **possible),
            _fact("residence_4", person_id="person_1", place_id="place_2", **possible),
            _fact("residence_3", person_id="person_2", place_id="place_2", **certain),
            _fact("residence_2", person_id="person_1", place_id="place_2", **certain),
            _fact("residence_1", person_id="person_1", place_id="place_1", **certain),
        ],
    )

    entries = residents_of_place(data, "place_1", 1850)

    assert [(entry.label, entry.place_display, entry.person_display, entry.residence_id)
            for entry in entries] == [
        (LABEL_CERTAIN, "Ed", "Anders Andersson", "residence_1"),
        (LABEL_CERTAIN, "Åby", "Anders Andersson", "residence_2"),
        (LABEL_CERTAIN, "Åby", "Örjan Öberg", "residence_3"),
        (LABEL_POSSIBLE, "Åby", "Anders Andersson", "residence_4"),
        (LABEL_POSSIBLE, "Ösjö", "Örjan Öberg", "residence_5"),
    ]


def test_swedish_sort_key_orders_a_ring_letters_after_z():
    names = sorted(["Östansjö", "Åby", "Ängen", "Zäta", "Ed"], key=swedish_sort_key)
    assert names == ["Ed", "Zäta", "Åby", "Ängen", "Östansjö"]


# --- descendant places (Requirement 8.6) ---


def test_descendants_are_included_with_their_place_chain():
    data = _project(
        persons=[_person("person_1")],
        places=[
            _place("place_1", "Ljusdal"),
            _place("place_2", "Åby", parent_place_id="place_1"),
            _place("place_3", "Norrgården", parent_place_id="place_2"),
        ],
        residences=[
            _fact(
                "residence_1",
                place_id="place_3",
                start=Endpoint(earliest="1840", latest="1840"),
                end=Endpoint(earliest="1846", latest="1846"),
            )
        ],
    )

    entries = residents_of_place(data, "place_1", 1843)

    assert len(entries) == 1
    assert entries[0].place_id == "place_3"
    assert entries[0].place_display == "Norrgården"
    assert entries[0].place_chain == ["Ljusdal", "Åby", "Norrgården"]


def test_descendants_beyond_ten_levels_are_excluded():
    places = [_place("place_0", "Nivå 0")]
    for level in range(1, MAX_DESCENDANT_LEVELS + 2):
        places.append(
            _place(f"place_{level}", f"Nivå {level}", parent_place_id=f"place_{level - 1}")
        )
    residences = [
        _fact(
            f"residence_{level}",
            place_id=f"place_{level}",
            start=Endpoint(earliest="1840", latest="1840"),
            end=Endpoint(earliest="1846", latest="1846"),
        )
        for level in range(MAX_DESCENDANT_LEVELS + 2)
    ]
    data = _project(persons=[_person("person_1")], places=places, residences=residences)

    entries = residents_of_place(data, "place_0", 1843)

    assert {entry.place_id for entry in entries} == {
        f"place_{level}" for level in range(MAX_DESCENDANT_LEVELS + 1)
    }
    deepest = next(
        entry
        for entry in entries
        if entry.place_id == f"place_{MAX_DESCENDANT_LEVELS}"
    )
    assert len(deepest.place_chain) == MAX_DESCENDANT_LEVELS + 1


def test_circular_parent_chain_terminates():
    data = _project(
        persons=[_person("person_1")],
        places=[
            _place("place_1", "Åby", parent_place_id="place_2"),
            _place("place_2", "Ed", parent_place_id="place_1"),
        ],
        residences=[
            _fact(
                "residence_1",
                place_id="place_2",
                start=Endpoint(earliest="1840", latest="1840"),
                end=Endpoint(earliest="1846", latest="1846"),
            )
        ],
    )

    entries = residents_of_place(data, "place_1", 1843)

    assert [entry.place_chain for entry in entries] == [["Åby", "Ed"]]


def test_unresolved_references_are_reported_with_their_stored_identifiers():
    data = _project(
        residences=[
            _fact(
                "residence_1",
                person_id="person_9",
                place_id="place_9",
                start=Endpoint(earliest="1840", latest="1840"),
                end=Endpoint(earliest="1846", latest="1846"),
            )
        ]
    )

    entries = residents_of_place(data, "place_9", 1843)

    assert len(entries) == 1
    assert entries[0].person_display == "person_9"
    assert entries[0].place_display == "place_9"


def test_place_without_residences_yields_no_entries():
    data = _project(persons=[_person("person_1")], places=[_place("place_1", "Åby")])

    assert residents_of_place(data, "place_1", 1843) == []


# ===========================================================================
# residence_timeline (Requirement 8.7)
# ===========================================================================


def test_timeline_sorts_by_start_earliest_ascending():
    data = _project(
        persons=[_person("person_1")],
        places=[_place("place_1", "Åby")],
        residences=[
            _fact("r2", start=Endpoint(earliest="1850"), end=Endpoint(latest="1860")),
            _fact("r1", start=Endpoint(earliest="1840"), end=Endpoint(latest="1860")),
        ],
    )

    result = residence_timeline(data, "person_1")

    assert [f.id for f in result] == ["r1", "r2"]


def test_timeline_absent_sorts_before_any_present_value():
    data = _project(
        persons=[_person("person_1")],
        places=[_place("place_1", "Åby")],
        residences=[
            _fact("r2", start=Endpoint(earliest="1840"), end=Endpoint(latest="1860")),
            _fact("r1", start=Endpoint(), end=Endpoint(latest="1860")),
        ],
    )

    result = residence_timeline(data, "person_1")

    assert [f.id for f in result] == ["r1", "r2"]


def test_timeline_breaks_ties_on_start_latest():
    data = _project(
        persons=[_person("person_1")],
        places=[_place("place_1", "Åby")],
        residences=[
            _fact("r2", start=Endpoint(earliest="1840", latest="1845")),
            _fact("r1", start=Endpoint(earliest="1840", latest="1842")),
        ],
    )

    result = residence_timeline(data, "person_1")

    assert [f.id for f in result] == ["r1", "r2"]


def test_timeline_breaks_ties_on_end_earliest_then_end_latest():
    data = _project(
        persons=[_person("person_1")],
        places=[_place("place_1", "Åby")],
        residences=[
            _fact(
                "r2",
                start=Endpoint(earliest="1840", latest="1840"),
                end=Endpoint(earliest="1850", latest="1860"),
            ),
            _fact(
                "r1",
                start=Endpoint(earliest="1840", latest="1840"),
                end=Endpoint(earliest="1848", latest="1860"),
            ),
        ],
    )

    result = residence_timeline(data, "person_1")

    assert [f.id for f in result] == ["r1", "r2"]


def test_timeline_breaks_ties_on_place_name_swedish_order():
    data = _project(
        persons=[_person("person_1")],
        places=[
            _place("place_1", "Åby"),
            _place("place_2", "Ed"),
        ],
        residences=[
            _fact(
                "r1",
                place_id="place_1",
                start=Endpoint(earliest="1840"),
                end=Endpoint(latest="1860"),
            ),
            _fact(
                "r2",
                place_id="place_2",
                start=Endpoint(earliest="1840"),
                end=Endpoint(latest="1860"),
            ),
        ],
    )

    result = residence_timeline(data, "person_1")

    # "Ed" < "Åby" in Swedish alphabetical order (å comes after z).
    assert [f.id for f in result] == ["r2", "r1"]


def test_timeline_final_tiebreak_is_ascending_id():
    data = _project(
        persons=[_person("person_1")],
        places=[_place("place_1", "Åby")],
        residences=[
            _fact("r3", start=Endpoint(earliest="1840"), end=Endpoint(latest="1860")),
            _fact("r1", start=Endpoint(earliest="1840"), end=Endpoint(latest="1860")),
            _fact("r2", start=Endpoint(earliest="1840"), end=Endpoint(latest="1860")),
        ],
    )

    result = residence_timeline(data, "person_1")

    assert [f.id for f in result] == ["r1", "r2", "r3"]


def test_timeline_returns_only_facts_of_the_given_person():
    data = _project(
        persons=[_person("person_1"), _person("person_2", "Brita", "Persdotter")],
        places=[_place("place_1", "Åby")],
        residences=[
            _fact("r1", person_id="person_1", start=Endpoint(earliest="1840")),
            _fact("r2", person_id="person_2", start=Endpoint(earliest="1830")),
        ],
    )

    result = residence_timeline(data, "person_1")

    assert [f.id for f in result] == ["r1"]


def test_timeline_is_stable_across_runs():
    data = _project(
        persons=[_person("person_1")],
        places=[_place("place_1", "Åby")],
        residences=[
            _fact("r3", start=Endpoint(earliest="1840")),
            _fact("r1", start=Endpoint(earliest="1840")),
            _fact("r2", start=Endpoint(earliest="1850")),
        ],
    )

    first_run = residence_timeline(data, "person_1")
    second_run = residence_timeline(data, "person_1")

    assert [f.id for f in first_run] == [f.id for f in second_run]


def test_timeline_leaves_project_unchanged():
    data = _project(
        persons=[_person("person_1")],
        places=[_place("place_1", "Åby")],
        residences=[
            _fact("r1", start=Endpoint(earliest="1850")),
            _fact("r2", start=Endpoint(earliest="1840")),
        ],
    )
    before = deepcopy(data)

    residence_timeline(data, "person_1")

    assert data == before


def test_timeline_empty_for_unknown_person():
    data = _project(
        persons=[_person("person_1")],
        places=[_place("place_1", "Åby")],
        residences=[_fact("r1")],
    )

    assert residence_timeline(data, "person_99") == []


# ===========================================================================
# residents_grouped_by_role (Requirement 8.10)
# ===========================================================================


def _entry(residence_id="r1", role="", person_id="person_1"):
    """A minimal ResidentEntry for role grouping tests."""
    return ResidentEntry(
        person_id=person_id,
        person_display="Test",
        residence_id=residence_id,
        place_id="place_1",
        place_display="Åby",
        interval_display="1840\u20131860",
        label=LABEL_CERTAIN,
        role_in_household=role,
    )


def test_role_grouping_groups_by_exact_text():
    entries = [
        _entry("r1", role="husbonde"),
        _entry("r2", role="piga"),
        _entry("r3", role="husbonde"),
    ]

    result = residents_grouped_by_role(entries)

    assert [(role, [e.residence_id for e in members]) for role, members in result] == [
        ("husbonde", ["r1", "r3"]),
        ("piga", ["r2"]),
    ]


def test_role_grouping_empty_roles_in_final_group():
    entries = [
        _entry("r1", role=""),
        _entry("r2", role="piga"),
        _entry("r3", role=""),
    ]

    result = residents_grouped_by_role(entries)

    assert [(role, [e.residence_id for e in members]) for role, members in result] == [
        ("piga", ["r2"]),
        (LABEL_ROLE_MISSING, ["r1", "r3"]),
    ]


def test_role_grouping_case_sensitive():
    entries = [
        _entry("r1", role="Piga"),
        _entry("r2", role="piga"),
    ]

    result = residents_grouped_by_role(entries)

    assert [(role, [e.residence_id for e in members]) for role, members in result] == [
        ("Piga", ["r1"]),
        ("piga", ["r2"]),
    ]


def test_role_grouping_whitespace_sensitive():
    entries = [
        _entry("r1", role="dräng på gården"),
        _entry("r2", role="dräng  på gården"),
    ]

    result = residents_grouped_by_role(entries)

    assert len(result) == 2
    assert result[0][0] == "dräng på gården"
    assert result[1][0] == "dräng  på gården"


def test_role_grouping_preserves_first_occurrence_order():
    entries = [
        _entry("r1", role="inhyses"),
        _entry("r2", role="piga"),
        _entry("r3", role="husbonde"),
        _entry("r4", role="piga"),
    ]

    result = residents_grouped_by_role(entries)

    assert [role for role, _ in result] == ["inhyses", "piga", "husbonde"]


def test_role_grouping_all_empty_yields_one_final_group():
    entries = [_entry("r1"), _entry("r2"), _entry("r3")]

    result = residents_grouped_by_role(entries)

    assert len(result) == 1
    assert result[0][0] == LABEL_ROLE_MISSING
    assert len(result[0][1]) == 3


def test_role_grouping_no_entries_yields_empty_list():
    assert residents_grouped_by_role([]) == []


def test_role_grouping_no_empty_roles_means_no_final_group():
    entries = [_entry("r1", role="husbonde"), _entry("r2", role="piga")]

    result = residents_grouped_by_role(entries)

    assert all(role != LABEL_ROLE_MISSING for role, _ in result)
    assert [role for role, _ in result] == ["husbonde", "piga"]
