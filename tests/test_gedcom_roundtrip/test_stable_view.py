"""Unit tests for Stable_View, the difference catalog and the comparator (task 1.2)."""

from __future__ import annotations

import copy
import random

import pytest

from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef, SourceRef
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import Endpoint, ResidenceFact
from slaktbusken.model.source import Source
from tests.test_gedcom_roundtrip import fixtures
from tests.test_gedcom_roundtrip.comparison import (
    UncatalogedDifference,
    blocking,
    compare,
    reportable,
)
from tests.test_gedcom_roundtrip.difference_catalog import (
    APP_ONLY,
    CATALOG,
    DEFERRED,
    FIXED,
    UNCOVERED_SOURCE_FIELDS,
)
from tests.test_gedcom_roundtrip.stable_view import person_key, person_ref, stable_view

pytestmark = pytest.mark.mandatory_integrity


def _project() -> ProjectData:
    data = ProjectData()
    data.places = [
        Place(id="p1", type="country", name="Sverige"),
        Place(id="p2", type="parish", name="Orsa", parent_place_id="p1"),
    ]
    data.sources = [Source(id="s1", provider="", source_type="church_book", title="Orsa C:1")]
    data.persons = [
        Person(id="a", sex="M", names=[Name("birth", "Anders", "Persson")], notes="n"),
        Person(
            id="b",
            sex="F",
            names=[Name("birth", "Brita", "Olsdotter"), Name("married", "Brita", "Persson")],
        ),
        Person(id="c", sex="F", names=[Name("birth", "Cajsa", "Persson")]),
    ]
    data.events = [
        Event(
            id="e1",
            type="birth",
            participants=[Participant("a", "subject")],
            date=DateValue("1800-01-02", "day"),
            place=PlaceRef("p2", [SourceRef("s1", "primary", "n", ["x"])]),
        ),
        Event(
            id="e2",
            type="marriage",
            participants=[Participant("a", "groom"), Participant("b", "bride")],
            date=DateValue("1825", "year"),
        ),
    ]
    data.families = [
        Family(
            id="f1",
            partners=[FamilyPartner("a", "husband"), FamilyPartner("b", "wife")],
            children=["c"],
            parent_child_links=[
                ParentChildLink("c", "a", "biological"),
                ParentChildLink("c", "b", "step"),
            ],
            event_ids=["e2"],
        )
    ]
    data.residences = [
        ResidenceFact(
            id="r1",
            person_id="a",
            place_id="p2",
            start=Endpoint(earliest="1820", latest="1821"),
            role_in_household="dräng",
        )
    ]
    return data


def _codes(a: ProjectData, b: ProjectData) -> list[str]:
    return [d.code for d in compare(a, b)]


# ---- keys ---------------------------------------------------------------


def test_person_key_sorts_names_and_includes_sex_and_birth() -> None:
    p = Person(
        id="x",
        sex="F",
        names=[Name("married", "Brita", "Persson"), Name("birth", "Brita", "Olsdotter")],
    )
    key = person_key(p, "1800")
    assert key == (
        (("birth", "Brita", "Olsdotter"), ("married", "Brita", "Persson")),
        "F",
        "1800",
    )
    p.names.reverse()
    assert person_key(p, "1800") == key


def test_person_key_ignores_id_and_changes_with_sex_or_birth() -> None:
    p1 = Person(id="x", sex="M", names=[Name("birth", "A", "B")])
    p2 = Person(id="y", sex="M", names=[Name("birth", "A", "B")])
    assert person_key(p1) == person_key(p2)
    p2.sex = "U"
    assert person_key(p1) != person_key(p2)
    assert person_key(p1, "1800") != person_key(p1, "1801")
    assert person_ref(p1) == person_ref(p2)  # reference ignores sex and name type


def test_event_key_has_no_ids_and_ignores_participant_order_and_roles() -> None:
    view = stable_view(_project())
    marriage = [i for i in view.items("events") if i.identity[0] == "marriage"][0]
    assert marriage.identity[2] == ("1825", "", "year", "exact", "gregorian")
    assert len(marriage.identity[4]) == 2

    data = _project()
    data.events[1].participants.reverse()
    data.events[1].participants[0].role = "other"
    again = [i for i in stable_view(data).items("events") if i.identity[0] == "marriage"][0]
    assert again.identity == marriage.identity
    assert again.fields != marriage.fields  # the roles are a field


def test_event_key_contains_place_chain_root_first() -> None:
    view = stable_view(_project())
    birth = [i for i in view.items("events") if i.identity[0] == "birth"][0]
    assert birth.identity[3] == ("Sverige", "Orsa")


def test_equal_identities_get_distinct_ordinals() -> None:
    data = _project()
    data.events.append(copy.deepcopy(data.events[1]))
    data.events[-1].id = "e9"
    marriages = [i for i in stable_view(data).items("events") if i.identity[0] == "marriage"]
    assert sorted(i.ordinal for i in marriages) == [0, 1]
    assert len({i.key for i in marriages}) == 2


# ---- stable ordering ----------------------------------------------------


def test_view_is_independent_of_ids_and_list_order() -> None:
    original = _project()
    shuffled = copy.deepcopy(original)
    rename = {"a": "z9", "b": "y8", "c": "x7", "e1": "ev_b", "e2": "ev_a", "f1": "fam", "s1": "src"}
    for person in shuffled.persons:
        person.id = rename[person.id]
    for event in shuffled.events:
        event.id = rename[event.id]
        for participant in event.participants:
            participant.person_id = rename[participant.person_id]
        for ref in (event.place.source_refs if event.place else []):
            ref.source_id = rename[ref.source_id]
    family = shuffled.families[0]
    family.id = rename[family.id]
    for partner in family.partners:
        partner.person_id = rename[partner.person_id]
    family.children = [rename[c] for c in family.children]
    for link in family.parent_child_links:
        link.child_id = rename[link.child_id]
        link.parent_id = rename[link.parent_id]
    family.event_ids = [rename[e] for e in family.event_ids]
    shuffled.sources[0].id = rename["s1"]
    shuffled.residences[0].person_id = rename["a"]
    rng = random.Random(7)
    for items in (shuffled.persons, shuffled.events, shuffled.families):
        rng.shuffle(items)
    shuffled.persons[0].names.reverse()

    assert stable_view(shuffled) == stable_view(original)
    assert compare(original, shuffled) == []


def test_view_does_not_modify_input() -> None:
    data = _project()
    before = copy.deepcopy(data)
    stable_view(data)
    assert data == before


def test_counts_cover_persons_families_and_event_types() -> None:
    counts = stable_view(_project()).counts
    assert counts["persons"] == 3
    assert counts["families"] == 1
    assert counts["events_per_type"] == {"birth": 1, "marriage": 1}


# ---- catalog ------------------------------------------------------------


def test_catalog_has_k1_to_k43_and_the_source_fields() -> None:
    for n in range(1, 44):
        assert f"K{n}" in CATALOG
    for code in UNCOVERED_SOURCE_FIELDS.values():
        assert CATALOG[code].status in (DEFERRED, APP_ONLY)
    assert set(UNCOVERED_SOURCE_FIELDS) == {
        "provider_ref",
        "short_note",
        "free_note",
        "arkivreferens",
        "arkivreferenser",
        "media_ids",
    }


def test_catalog_statuses_and_classes_follow_the_design() -> None:
    assert {c for c, e in CATALOG.items() if e.status == DEFERRED} >= {
        "K19", "K30", "K35", "K36", "K40", "K43",
    }
    assert {c for c, e in CATALOG.items() if e.status == APP_ONLY} == {"K37", "K38", "K39"}
    assert CATALOG["K13"].classes == ("A", "C")
    assert CATALOG["K13"].difference_class == "A/C"
    assert CATALOG["K37"].root_class == "D"
    assert CATALOG["K29"].status == FIXED
    for entry in CATALOG.values():
        assert entry.classes and set(entry.classes) <= set("ABCD")


# ---- comparator ---------------------------------------------------------


def test_identical_projects_have_no_differences() -> None:
    assert compare(_project(), _project()) == []


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda d: setattr(d.persons[0], "notes", ""), "K3"),
        (lambda d: setattr(d.persons[0], "title", "Dr"), "K4"),
        (lambda d: setattr(d.persons[0], "occupation", "Dräng"), "K42"),
        (lambda d: setattr(d.persons[2], "sex", "X"), "K13"),
        (lambda d: setattr(d.persons[1].names[1], "type", "aka"), "K7"),
        (lambda d: setattr(d.families[0].partners[0], "role", "partner"), "K11"),
        (lambda d: setattr(d.families[0].parent_child_links[1], "parentage_type", "biological"), "K14"),
        (lambda d: setattr(d.families[0].parent_child_links[0], "parentage_type", "foster"), "K15"),
        (lambda d: setattr(d.residences[0], "role_in_household", ""), "K26"),
        (lambda d: setattr(d.residences[0].start, "latest", None), "K24"),
        (lambda d: setattr(d.sources[0], "source_type", "other"), "K33"),
        (lambda d: setattr(d.sources[0], "provider_ref", "x"), "K44"),
    ],
)
def test_field_differences_get_catalog_codes(mutate, code) -> None:
    changed = _project()
    mutate(changed)
    assert _codes(_project(), changed) == [code]


def test_missing_family_event_is_k1_and_other_event_is_k27() -> None:
    changed = _project()
    changed.events = [e for e in changed.events if e.type != "marriage"]
    changed.families[0].event_ids = []
    assert set(_codes(_project(), changed)) == {"K1"}

    original = _project()
    original.events.append(
        Event("e3", "confirmation", [Participant("a", "subject")], DateValue("1815", "year"))
    )
    assert _codes(original, _project()) == ["K27"]


def test_participant_role_and_participant_set_changes() -> None:
    changed = _project()
    changed.events[1].participants[0].role = "subject"
    assert _codes(_project(), changed) == ["K28"]

    original = _project()
    original.events.append(
        Event(
            "e3",
            "emigration",
            [Participant("a", "subject"), Participant("c", "subject")],
            DateValue("1850", "year"),
        )
    )
    split = copy.deepcopy(original)
    split.events[-1].participants = [Participant("a", "subject")]
    assert _codes(original, split) == ["K29"]


def test_citation_differences_are_split_by_context_quality_and_note() -> None:
    def with_ref(ref_context: str, quality="primary", note="n", aspects=("x",)):
        d = _project()
        ev = d.events[0]
        ref = SourceRef("s1", quality, note, list(aspects))
        ev.place = PlaceRef("p2", [ref] if ref_context == "place" else [])
        ev.date = DateValue("1800-01-02", "day", [ref] if ref_context == "date" else [])
        ev.source_refs = [ref] if ref_context == "event" else []
        return d

    assert _codes(with_ref("date"), with_ref("event")) == ["K16"]
    assert _codes(with_ref("event"), with_ref("event", quality="secondary")) == ["K17"]
    assert _codes(with_ref("event"), with_ref("event", note="")) == ["K18"]
    assert _codes(with_ref("event"), with_ref("event", aspects=())) == ["K18"]


def test_uncatalogued_difference_fails_with_all_differences() -> None:
    changed = _project()
    changed.families[0].children = []  # no catalog code
    changed.persons[0].notes = ""  # K3, still reported
    with pytest.raises(UncatalogedDifference) as info:
        compare(_project(), changed)
    assert {d.code for d in info.value.differences} == {"UNCLASSIFIED", "K3"}


def test_blocking_and_reportable_split_by_status() -> None:
    changed = _project()
    changed.persons[0].notes = ""
    changed.persons[0].profile_media_id = "m1"
    diffs = compare(_project(), changed)
    assert {d.code for d in blocking(diffs)} == {"K3"}
    assert {d.code for d in reportable(diffs)} == {"K40"}
    assert [d.difference_class for d in reportable(diffs)] == ["A/C"]


# ---- fixtures -----------------------------------------------------------


def test_view_of_mergetest_is_stable_and_self_equal() -> None:
    data = fixtures.load_mergetest()
    view = stable_view(data)
    assert view.counts["persons"] == len(data.persons)
    assert stable_view(fixtures.load_mergetest()) == view
    assert compare(data, fixtures.load_mergetest()) == []
    assert not any(isinstance(k, str) and k.startswith("person_") for item in view.items("persons") for k in item.identity)
