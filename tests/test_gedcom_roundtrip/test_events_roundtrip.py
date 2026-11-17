"""Events: Properties 7 and 17 and the examples of Requirements 1.8 to 1.14, 8.

Round trips go through ``GEDCOMExporter`` and ``ImportService.run`` into a real
empty project. Persons are labelled ``P<n>`` before the export (the importer
creates new ids), and events are compared in label terms.

``Event.extra_origins`` holds one RecordOrigin for each further INDI record of
an event that the importer built from several INDI records (task 6.2). The
re-import tests check that a second import creates nothing, in the same
session and after save and reopen.
"""

from __future__ import annotations

import copy
import tempfile
from collections import Counter
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.gedcom.importer import ImportResult
from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef
from slaktbusken.model.family import Family, FamilyPartner
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.persistence.serialization import serialize
from slaktbusken.services.import_service import ImportService
from slaktbusken.services.project_service import ProjectService
from slaktbusken.services.report_service import ReportService
from slaktbusken.services.validation_service import ValidationService
from tests.test_gedcom_roundtrip import synthetic as syn
from tests.test_gedcom_roundtrip.strategies import event_projects
from tests.test_gedcom_roundtrip.test_families_roundtrip import (
    FAMILY_TYPES,
    _children,
    export_text,
    fam_records,
    import_text,
    indi_records,
    label_by_xref,
    label_of,
    label_persons,
)
import pytest

pytestmark = pytest.mark.mandatory_integrity

_FILE_HEAD = "0 HEAD\n1 GEDC\n2 VERS 5.5.1\n2 FORM LINEAGE-LINKED\n1 CHAR UTF-8\n"


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


class World:
    """A real project on disk that several files are imported into."""

    def __init__(self, root: Path) -> None:
        self.ps = ProjectService()
        self.ps.create_project("Mål", root / "proj")
        self.folder = self.ps.project_path.parent
        self.service = ImportService(ValidationService(), ReportService())
        self._n = 0

    @property
    def data(self) -> ProjectData:
        return self.ps.data

    def run(self, text: str) -> ImportResult:
        self._n += 1
        path = self.folder / f"import_{self._n}.ged"
        path.write_text(text, encoding="utf-8")
        return self.service.run(self.ps.data, path, self.folder, self.ps)

    def save_and_reopen(self) -> None:
        self.ps.save_project()
        path = self.ps.project_path
        self.ps = ProjectService()
        self.ps.open_project(path)


def event_view(data: ProjectData, event: Event) -> tuple:
    """An event in label terms: type, custom name, sorted (label, role) pairs."""
    labels = {p.id: label_of(p) for p in data.persons}
    parts = tuple(sorted((labels[p.person_id], p.role) for p in event.participants))
    return (event.type, event.custom_type_name or None, parts)


def event_counter(data: ProjectData, types: tuple[str, ...] = ()) -> Counter:
    return Counter(event_view(data, e) for e in data.events
                   if not types or e.type in types)


def fallback_events(data: ProjectData, text: str) -> list[Event]:
    """Events written as Individual_Fallback in ``text`` (token on an INDI)."""
    tokens = set()
    for indi in indi_records(text):
        for node in indi.children:
            if node.tag == "EVEN" and _children(node, "_SLK_EVTYPE"):
                tokens.update(c.value for c in _children(node, "_SLK_EID"))
    return [e for e in data.events if e.id in tokens and e.type in FAMILY_TYPES]


def origin_count(data: ProjectData) -> int:
    return sum((e.origin is not None) + len(e.extra_origins) for e in data.events)


def no_change(world: World, text: str) -> None:
    """A second import of ``text`` creates nothing and changes nothing."""
    before = serialize(world.data)
    events, persons, origins = (len(world.data.events), len(world.data.persons),
                                origin_count(world.data))
    participants = sum(len(e.participants) for e in world.data.events)
    result = world.run(text)
    assert result.events_added == 0
    assert len(world.data.events) == events
    assert len(world.data.persons) == persons
    assert sum(len(e.participants) for e in world.data.events) == participants
    assert origin_count(world.data) == origins
    assert serialize(world.data) == before


# ---------------------------------------------------------------------------
# Property 7
# ---------------------------------------------------------------------------


# Feature: gedcom-roundtrip-0-3-0, Property 7: Events round-trip with roles, types and participants
# **Validates: Requirements 1.4, 8.1, 8.3, 8.4, 8.5, 8.6**
@given(event_projects())
def test_events_roundtrip_with_roles_types_and_participants(data: ProjectData) -> None:
    data = label_persons(data)
    text, _export = export_text(data)
    imported, _result = import_text(text)
    assert event_counter(imported) == event_counter(data)
    # Custom types keep their names.
    assert (Counter(e.custom_type_name for e in imported.events if e.custom_type_name)
            == Counter(e.custom_type_name for e in data.events if e.custom_type_name))


def test_event_without_own_tag_keeps_type_and_role() -> None:
    persons = [Person(id=f"person_{i}", sex="U", names=[Name("birth", f"P{i}", "X")])
               for i in (1, 2)]
    events = [
        Event(id="event_1", type=t,
              participants=[Participant("person_1", "subject"),
                            Participant("person_2", "witness")])
        for t in ("gender_correction", "name_change")
    ]
    events[1].id = "event_2"
    data = ProjectData(persons=persons, events=events)
    text, _ = export_text(data)
    assert "2 _SLK_EVTYPE gender_correction" in text
    imported, result = import_text(text)
    assert event_counter(imported) == event_counter(data)
    assert not [w for w in result.warnings if "_SLK_EVTYPE" in str(w)]


def test_unknown_evtype_becomes_custom_with_a_warning() -> None:
    text = (
        _FILE_HEAD + "0 @I1@ INDI\n1 NAME Ada /X/\n"
        "1 EVEN\n2 TYPE Något\n2 _SLK_EVTYPE ingen_typ\n"
        "0 TRLR\n"
    )
    imported, result = import_text(text)
    assert [e.type for e in imported.events] == ["custom_individual_event"]
    assert any("_SLK_EVTYPE" in str(w) or "ingen_typ" in str(w)
               for w in result.warnings)


def test_listed_family_event_keeps_participants_and_roles() -> None:
    data = label_persons(syn.build_synthetic_project())
    text, _ = export_text(data)
    imported, _ = import_text(text)
    types = FAMILY_TYPES
    assert event_counter(imported, types) == event_counter(data, types)


# ---------------------------------------------------------------------------
# Property 17 and the fallback examples
# ---------------------------------------------------------------------------


def fallback_project(shared_date: str = "1900-06-15",
                     couples: int = 2) -> ProjectData:
    """Couples without a family and with equal date and place."""
    persons, events = [], []
    for c in range(couples):
        a, b = 2 * c + 1, 2 * c + 2
        persons += [Person(id=f"person_{i}", sex=s,
                           names=[Name("birth", f"P{i}", "X")])
                    for i, s in ((a, "M"), (b, "F"))]
        events.append(Event(
            id=f"event_{c + 1}", type="marriage",
            participants=[Participant(f"person_{a}", "spouse"),
                          Participant(f"person_{b}", "spouse")],
            date=DateValue(value=shared_date, precision="day"),
            place=PlaceRef(syn.PLACE_LJUSDAL)))
    return ProjectData(persons=persons, events=events, places=syn.build_places())


def marriage_views(data: ProjectData) -> list[frozenset[str]]:
    labels = {p.id: label_of(p) for p in data.persons}
    return sorted(
        (frozenset(labels[p.person_id] for p in e.participants)
         for e in data.events if e.type == "marriage"), key=sorted)


# Feature: gedcom-roundtrip-0-3-0, Property 17: Event tokens join and nothing else joins
# **Validates: Requirements 1.8, 1.9, 1.10, 1.12, 1.13, 8.9**
@given(event_projects())
def test_event_tokens_join_and_nothing_else_joins(data: ProjectData) -> None:
    data = label_persons(data)
    text, _export = export_text(data)
    fallback = fallback_events(data, text)
    with tempfile.TemporaryDirectory() as folder:
        world = World(Path(folder))
        world.run(text)
        imported = world.data
        # One Event per token with the participants of that token.
        assert event_counter(imported, FAMILY_TYPES) == event_counter(data, FAMILY_TYPES)
        for event in fallback:
            expected = event_view(data, event)
            assert event_counter(imported)[expected] >= 1
        # A merged event has one further origin for each further INDI record.
        merged = {e.id: e for e in imported.events if e.extra_origins}
        for original in fallback:
            if len(original.participants) > 1:
                match = [e for e in imported.events
                         if event_view(imported, e) == event_view(data, original)]
                assert any(len(e.extra_origins) == len(original.participants) - 1
                           for e in match), original.id
        for event in merged.values():
            assert len({(o.owner_kind, o.owner_id) for o in
                        [event.origin, *event.extra_origins]}) == 1 + len(event.extra_origins)
        # Idempotent: the same file again, in the same session and after reopen.
        no_change(world, text)
        world.save_and_reopen()
        no_change(world, text)


def test_orphan_with_several_matching_families_is_one_shared_event() -> None:
    data = label_persons(syn.build_synthetic_project())
    sara_nils = next(f for f in data.families
                     if {p.person_id for p in f.partners} == {"person_12", "person_13"})
    data.families.append(
        Family(id="family_dup", partners=list(sara_nils.partners), children=[]))
    text, export = export_text(data)
    assert any("hör inte till någon enskild familj" in w and "7 JUL 1901" in w
               for w in export.warnings)
    imported, _ = import_text(text)
    labels = {p.id: label_of(p) for p in imported.persons}
    want = frozenset({label_of(next(p for p in data.persons if p.id == "person_12")),
                      label_of(next(p for p in data.persons if p.id == "person_13"))})
    found = [e for e in imported.events if e.type == "marriage"
             and frozenset(labels[p.person_id] for p in e.participants) == want
             and e.date and e.date.value == "1901-07-07"]
    assert len(found) == 1
    assert [p.role for p in found[0].participants] == ["spouse", "spouse"]
    assert len(found[0].extra_origins) == 1


def test_separate_marriages_with_equal_date_and_place_are_never_merged() -> None:
    data = fallback_project(couples=3)
    text, export = export_text(data)
    assert len([w for w in export.warnings if "hör inte till någon" in w]) == 3
    tokens = [c.value for i in indi_records(text) for n in i.children
              for c in _children(n, "_SLK_EID")]
    assert len(tokens) == 6 and len(set(tokens)) == 3
    imported, _ = import_text(text)
    assert marriage_views(imported) == marriage_views(data)
    assert len([e for e in imported.events if e.type == "marriage"]) == 3
    assert all(len(e.participants) == 2 for e in imported.events)


def test_same_token_in_a_different_event_type_still_joins_by_token_only() -> None:
    # Equal date, place, type and participants, but different tokens: two events.
    data = fallback_project(couples=1)
    twin = copy.deepcopy(data.events[0])
    twin.id = "event_9"
    data.events.append(twin)
    text, _ = export_text(data)
    imported, _ = import_text(text)
    assert len([e for e in imported.events if e.type == "marriage"]) == 2


def test_fallback_reimport_is_idempotent_also_after_reopen(tmp_path: Path) -> None:
    data = fallback_project(couples=2)
    text, _ = export_text(data)
    world = World(tmp_path)
    first = world.run(text)
    assert first.events_added == 2
    merged = [e for e in world.data.events if e.type == "marriage"]
    assert all(len(e.extra_origins) == 1 for e in merged)
    # Extra origins are one Origin_Group: same owner kind, different owner ids.
    for event in merged:
        assert event.origin is not None
        assert event.extra_origins[0].owner_id != event.origin.owner_id
    no_change(world, text)
    world.save_and_reopen()
    reopened = [e for e in world.data.events if e.type == "marriage"]
    assert all(len(e.extra_origins) == 1 for e in reopened)
    no_change(world, text)
    no_change(world, text)


def test_participant_arriving_in_a_later_run_does_not_duplicate(tmp_path: Path) -> None:
    data = fallback_project(couples=1)
    text, _ = export_text(data)
    world = World(tmp_path)
    world.run(text)
    world.run(text)
    assert len([e for e in world.data.events if e.type == "marriage"]) == 1


# ---------------------------------------------------------------------------
# Tokens: duplicate, empty, single
# ---------------------------------------------------------------------------


def _even(token: str | None, type_: str = "marriage", role: str | None = None,
          date: str = "1 JAN 1900") -> str:
    lines = ["1 EVEN", "2 TYPE Vigsel", f"2 _SLK_EVTYPE {type_}", f"2 DATE {date}"]
    if token is not None:
        lines.append(f"2 _SLK_EID {token}")
    if role:
        lines.append(f"2 _SLK_ROLE {role}")
    return "\n".join(lines) + "\n"


def _indi(xref: str, given: str, *events: str) -> str:
    return f"0 {xref} INDI\n1 NAME {given} /X/\n" + "".join(events)


def test_duplicate_token_on_one_indi_uses_the_first_and_warns() -> None:
    text = (_FILE_HEAD
            + _indi("@I1@", "Ada", _even("e1", date="1 JAN 1900"),
                    _even("e1", date="2 FEB 1901"))
            + _indi("@I2@", "Bo", _even("e1", date="1 JAN 1900"))
            + "0 TRLR\n")
    imported, result = import_text(text)
    marriages = [e for e in imported.events if e.type == "marriage"]
    assert len(marriages) == 1
    assert marriages[0].date.value == "1900-01-01"
    assert len(marriages[0].participants) == 2
    assert sum("_SLK_EID" in str(w) for w in result.warnings) == 1


def test_empty_token_gives_a_single_participant_event_without_warning() -> None:
    text = (_FILE_HEAD
            + _indi("@I1@", "Ada", _even(""))
            + _indi("@I2@", "Bo", _even(""))
            + "0 TRLR\n")
    imported, result = import_text(text)
    assert all(len(e.participants) == 1 for e in imported.events)
    assert not [w for w in result.warnings if "_SLK_EID" in str(w)]


def test_single_indi_token_gives_a_single_participant_event_without_warning() -> None:
    text = (_FILE_HEAD + _indi("@I1@", "Ada", _even("solo")) + "0 TRLR\n")
    imported, result = import_text(text)
    marriages = [e for e in imported.events if e.type == "marriage"]
    assert len(marriages) == 1 and len(marriages[0].participants) == 1
    assert marriages[0].extra_origins == []
    assert not result.warnings or not any("_SLK_EID" in str(w) for w in result.warnings)


def test_equal_date_without_token_does_not_join() -> None:
    text = (_FILE_HEAD
            + _indi("@I1@", "Ada", _even(None)) + _indi("@I2@", "Bo", _even(None))
            + "0 TRLR\n")
    imported, _ = import_text(text)
    assert len([e for e in imported.events if e.type == "marriage"]) == 2


def test_same_token_in_two_files_is_not_joined_across_files(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.run(_FILE_HEAD + _indi("@I1@", "Ada", _even("e1")) + "0 TRLR\n")
    world.run(_FILE_HEAD + _indi("@I2@", "Bo", _even("e1")) + "0 TRLR\n")
    assert len(world.data.persons) == 2
    assert len([e for e in world.data.events if e.type == "marriage"]) == 2


# ---------------------------------------------------------------------------
# One test per registry tag of the event module
# ---------------------------------------------------------------------------


def _event_nodes(text: str):
    for indi in indi_records(text):
        for node in indi.children:
            if node.tag in ("EVEN", "BIRT", "DEAT", "BURI", "CENS", "BAPM"):
                yield indi, node


def test_slk_tag_eid() -> None:
    data = fallback_project(couples=2)
    data.events.append(Event(
        id="event_7", type="birth", participants=[Participant("person_1", "subject")]))
    text, _ = export_text(data)
    tokens = Counter(c.value for _i, n in _event_nodes(text)
                     for c in _children(n, "_SLK_EID"))
    assert tokens == Counter({"event_1": 2, "event_2": 2, "event_7": 1})
    imported, _ = import_text(text)
    assert len([e for e in imported.events if e.type == "birth"]) == 1


def test_slk_tag_eid_on_listed_family_event() -> None:
    data = syn.build_synthetic_project()
    text, _ = export_text(data)
    family_tokens = [c.value for r in fam_records(text) for n in r.children
                     for c in _children(n, "_SLK_EID")]
    family = next(f for f in data.families if f.event_ids)
    assert set(family.event_ids) <= set(family_tokens)


def test_slk_tag_evtype() -> None:
    data = fallback_project(couples=1)
    text, _ = export_text(data)
    for _indi_rec, node in _event_nodes(text):
        assert [c.value for c in _children(node, "_SLK_EVTYPE")] == ["marriage"]
        assert node.tag == "EVEN"
    imported, _ = import_text(text)
    assert [e.type for e in imported.events] == ["marriage"]


def test_slk_tag_role() -> None:
    persons = [Person(id=f"person_{i}", sex="U", names=[Name("birth", f"P{i}", "X")])
               for i in (1, 2)]
    event = Event(id="event_1", type="baptism", participants=[
        Participant("person_1", "subject"), Participant("person_2", "godfather")])
    data = ProjectData(persons=persons, events=[event])
    text, _ = export_text(data)
    roles = {label_by_xref(text)[i.xref_id]: [c.value for n in _event_nodes_of(i)
                                               for c in _children(n, "_SLK_ROLE")]
             for i in indi_records(text)}
    assert roles == {"P1": [], "P2": ["godfather"]}
    imported, _ = import_text(text)
    assert event_view(label_persons(data), event)[2] == (("P1", "subject"),
                                                          ("P2", "godfather"))
    assert event_counter(imported) == event_counter(label_persons(data))


def _event_nodes_of(indi):
    return [n for n in indi.children if n.tag in ("EVEN", "BAPM")]


def test_no_slk_role_for_placement_events() -> None:
    data = syn.build_synthetic_project()
    text, _ = export_text(data)
    for indi in indi_records(text):
        for node in indi.children:
            is_placement = node.tag == "ADOP" or any(
                c.tag == "TYPE" and c.value == "Fosterhem" for c in node.children)
            if is_placement:
                assert not _children(node, "_SLK_ROLE")


def test_slk_tag_fromplac() -> None:
    data = ProjectData(
        persons=[Person(id="person_1", sex="U", names=[Name("birth", "P1", "X")])],
        events=[Event(id="event_1", type="flytt",
                      participants=[Participant("person_1", "subject")],
                      date=DateValue(value="1860-05-01", precision="day"),
                      place=PlaceRef(syn.PLACE_GAVLE),
                      from_place=PlaceRef(syn.PLACE_LJUSDAL))],
        places=syn.build_places())
    text, _ = export_text(data)
    node = next(n for _i, n in _event_nodes(text))
    values = [c.value for c in _children(node, "_SLK_FROMPLAC")]
    assert len(values) == 1 and values[0].startswith("Ljusdal")
    imported, _ = import_text(text)
    flytt = next(e for e in imported.events if e.type == "flytt")
    assert flytt.from_place is not None
    places = {p.id: p for p in imported.places}
    chain, pid = [], flytt.from_place.place_id
    while pid:
        chain.append(places[pid].name)
        pid = places[pid].parent_place_id
    assert chain[0] == "Ljusdal"


# ---------------------------------------------------------------------------
# K56: the cause is written as CAUS
# ---------------------------------------------------------------------------
# Feature: gedcom-roundtrip-0-3-0, K56: Event.cause_of_death round-trips through CAUS
# **Validates: Requirements 8.10, 8.11**
@given(event_projects())
def test_event_cause_roundtrips_through_caus(data: ProjectData) -> None:
    data = label_persons(data)
    text, _export = export_text(data)
    imported, _result = import_text(text)
    assert Counter(e.cause_of_death for e in imported.events if e.cause_of_death) == \
        Counter(e.cause_of_death for e in data.events if e.cause_of_death)


def test_cause_is_written_as_caus_for_death_and_other_events() -> None:
    persons = [Person(id="person_1", sex="U", names=[Name("birth", "P1", "X")])]
    events = [
        Event(id=f"event_{n}", type=t, participants=[Participant("person_1", "subject")],
              cause_of_death=cause)
        for n, (t, cause) in enumerate(
            (("death", "Lunginflammation"), ("burial", "Olycka")), 1)]
    text, _ = export_text(label_persons(ProjectData(persons=persons, events=events)))
    assert [n.value for _i, n in _event_nodes(text)
            for c in _children(n, "CAUS") for n in (c,)] == ["Lunginflammation", "Olycka"]
    imported, _ = import_text(text)
    assert {e.type: e.cause_of_death for e in imported.events} == {
        "death": "Lunginflammation", "burial": "Olycka"}


def test_reimport_does_not_overwrite_a_user_edited_cause(tmp_path: Path) -> None:
    persons = [Person(id="person_1", sex="U", names=[Name("birth", "P1", "X")])]
    event = Event(id="event_1", type="death",
                  participants=[Participant("person_1", "subject")],
                  cause_of_death="Ålderdom")
    text, _ = export_text(label_persons(ProjectData(persons=persons, events=[event])))
    world = World(tmp_path)
    world.run(text)
    (death,) = [e for e in world.data.events if e.type == "death"]
    death.cause_of_death = "Redigerad av användaren"
    world.run(text)
    deaths = [e for e in world.data.events if e.type == "death"]
    assert [e.cause_of_death for e in deaths] == ["Redigerad av användaren"]
