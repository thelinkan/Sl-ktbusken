"""Unit tests for the residents query of the Residence_Query_Service.

Covers Requirements 8.1 (one entry per fact, no merging, ordering), 8.2–8.4
(labelling), 8.5 (entry fields), 8.6 (descendant walk, chains, cycles), 8.9
(both-sides-unbounded spans) and 15.9 (no lifespan clamping), plus the worked
examples of Requirements 14.8 and 15.5–15.6.
"""

from copy import deepcopy

from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import Endpoint, ResidenceFact
from slaktbusken.services.residence_query import (
    LABEL_CERTAIN,
    LABEL_POSSIBLE,
    MAX_DESCENDANT_LEVELS,
    ResidentEntry,
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
