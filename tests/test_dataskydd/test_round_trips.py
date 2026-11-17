"""Cross-component round trips: save and reopen, GEDCOM export and import.

One project carries every new field of data-integrity-0-3-0: event citations,
place and from_place citations, every date qualifier, a Julian date, an
unparsed date with original text, event origins, residences with and without
origins and a flytt link between two residences. The project is saved and
reopened, exported to GEDCOM and imported into a new project, and the exported
file is imported a second time.

Documented limits of the GEDCOM format that the tests assert instead of
hiding (design findings F28 to F30, Requirement 18.15 of the earlier spec):

* ``from_place`` of a flytt event leaves the file only as ``2 NOTE Från: ...``
  with an export log entry; the importer does not read it back.
* Links between residences and flytt events (``Endpoint.event_id``) are never
  written to a GEDCOM file.
* The citation context (event, date, place) and the quality of a citation are
  not part of GEDCOM; every exported citation returns as an event-level
  citation, so citations are compared as multisets of source titles per event.
* The earliest start and latest end of a residence travel as labelled notes
  that the importer does not read.

**Validates: Requirements 11.9, 12.7, 14.11, 16.6, 20.22, 21.7, 22.33**
"""

from __future__ import annotations

import copy
import dataclasses
from collections import Counter
from pathlib import Path

import pytest

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.gedcom.importer import ImportResult
from slaktbusken.model.date_semantics import validate_date_value
from slaktbusken.model.event import (
    DateValue,
    Event,
    Participant,
    PlaceRef,
    SourceRef,
)
from slaktbusken.model.event_citations import CitationContext, event_citations
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData
from slaktbusken.model.record_origin import RecordOrigin, origin_key
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.model.source import Source
from slaktbusken.persistence.serialization import serialize
from slaktbusken.services.import_service import ImportService
from slaktbusken.services.project_service import ProjectService
from slaktbusken.services.report_service import ReportService
from slaktbusken.services.validation_service import ValidationService

pytestmark = pytest.mark.mandatory_integrity

PERSON = "person_1"
HASH_A = "a" * 64
HASH_B = "b" * 64


# ---------------------------------------------------------------------------
# The project with every new field
# ---------------------------------------------------------------------------


def _dv(value: str, qualifier: str = "exact", **kw) -> DateValue:
    if "precision" not in kw:
        if qualifier == "exact":
            kw["precision"] = {4: "year", 7: "month", 10: "day"}[len(value)]
        else:
            kw["precision"] = "approximate"
    return DateValue(value=value, qualifier=qualifier, **kw)


def _ref(source_id: str, **kw) -> SourceRef:
    return SourceRef(source_id=source_id, quality=kw.pop("quality", "secondary"), **kw)


def _event(event_id: str, type_: str, date: DateValue | None, **kw) -> Event:
    return Event(
        id=event_id,
        type=type_,
        participants=[Participant(person_id=PERSON, role="subject")],
        date=date,
        **kw,
    )


def _origin(tag_key: str, index: int = 0, instance: int = 0, uid=None, hash_=HASH_A):
    return RecordOrigin(
        owner_kind="INDI",
        owner_id=PERSON,
        owner_xref="@I1@",
        tag_key=tag_key,
        index=index,
        record_hash=hash_,
        uid=uid,
        instance=instance,
    )


def build_data(data: ProjectData) -> None:
    """Fill *data* (a created project) with every new field."""
    data.persons = [
        Person(id=PERSON, sex="M", names=[Name(type="birth", given="Johan", surname="Andersson")])
    ]
    data.places = [
        Place(id="place_1", type="county", name="Gävleborgs län"),
        Place(id="place_2", type="parish", name="Ljusdal", parent_place_id="place_1"),
        Place(id="place_3", type="parish", name="Gävle", parent_place_id="place_1"),
        Place(id="place_4", type="parish", name="Bollnäs", parent_place_id="place_1"),
    ]
    data.sources = [
        Source(id="source_1", provider="", source_type="other", title="Husförhörslängd A"),
        Source(id="source_2", provider="", source_type="other", title="Husförhörslängd B"),
        Source(id="source_3", provider="", source_type="other", title="Dopbok C"),
    ]
    events = [
        # Event, date, place and from_place citations on one event.
        _event(
            "event_1", "birth",
            _dv("1850-03-04", original_text="1850-03-04",
                source_refs=[_ref("source_2", note="s. 4", aspects=["date"])]),
            place=PlaceRef("place_2", [_ref("source_3", quality="primary")]),
            source_refs=[_ref("source_1", quality="primary", note="födelsepost")],
            origin=_origin("BIRT", uid="UID-BIRT"),
        ),
        _event(
            "event_2", "death",
            DateValue(value="", precision="approximate", qualifier="unparsed",
                      original_text="vid midsommar 1920"),
            place=PlaceRef("place_4"),
            origin=_origin("DEAT", hash_=HASH_B),
        ),
        # Julian date.
        _event("event_3", "burial", _dv("1700-02-29", calendar="julian"),
               source_refs=[_ref("source_1"), _ref("source_1")]),
        _event("event_4", "baptism", _dv("1850", precision="year"),
               place=PlaceRef("place_2"), origin=_origin("BAPM", instance=1)),
        # One census event per remaining qualifier.
        _event("event_5", "census", _dv("1851", "about"),
               source_refs=[_ref("source_1"), _ref("source_2")]),
        _event("event_6", "census", _dv("1852-05", "estimated"),
               place=PlaceRef("place_3", [_ref("source_2")])),
        _event("event_7", "census", _dv("1853", "calculated")),
        _event("event_8", "census", _dv("1854", "before", source_refs=[_ref("source_3")])),
        _event("event_9", "census", _dv("1855-06-01", "after")),
        _event("event_10", "census", _dv("1856", "between", value_to="1858")),
        _event("event_11", "census", _dv("1859-01", "from_to", value_to="1860-02-03")),
        _event("event_12", "census", _dv("1861", "from")),
        _event("event_13", "census", _dv("1862-07", "to")),
        _event("event_14", "census", _dv("1863", "interpreted",
                                         original_text="INT 1863 (cirka)")),
        _event("event_15", "census", _dv("1864", "between", value_to="1866",
                                         calendar="julian")),
        # Flytt with from_place, its citations and an event-level citation.
        _event(
            "event_16", "flytt", _dv("1860-05-01"),
            place=PlaceRef("place_3", [_ref("source_2")]),
            from_place=PlaceRef("place_2", [_ref("source_1")]),
            source_refs=[_ref("source_3")],
            origin=_origin("EVEN:flytt", hash_=HASH_B),
        ),
    ]
    data.events = events
    data.residences = [
        # With origins and a flytt link at the end.
        ResidenceFact(
            id="residence_1", person_id=PERSON, place_id="place_2",
            start=Endpoint(earliest="1850", latest="1850-06", precision="year"),
            end=Endpoint(earliest="1860-04", latest="1860-05-01", precision="month",
                         event_id="event_16"),
            role_in_household="Dräng",
            observations=[Observation(_ref("source_1"), "1855", "1858", "s. 12")],
            notes="Egen anteckning",
            origins=[_origin("RESI", instance=0), _origin("RESI", instance=1, uid="UID-R")],
        ),
        # Without origin; start linked to the same flytt event.
        ResidenceFact(
            id="residence_2", person_id=PERSON, place_id="place_3",
            start=Endpoint(earliest="1860-04", latest="1860-05-01", precision="month",
                           event_id="event_16"),
            end=Endpoint(earliest="1870", latest="1871", precision="year"),
            observations=[Observation(_ref("source_2"), "1865", "1868")],
        ),
        # Origin only.
        ResidenceFact(
            id="residence_3", person_id=PERSON, place_id="place_4",
            start=Endpoint(earliest="1872", latest="1872", precision="year"),
            end=Endpoint(),
            origins=[_origin("RESI", index=1, hash_=HASH_B)],
        ),
    ]
    data.id_high_water_marks = {}


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


class Session:
    """A real project on disk and an import service bound to it."""

    def __init__(self, ps: ProjectService) -> None:
        self.ps = ps
        self.service = ImportService(ValidationService(), ReportService())
        self._n = 0

    @classmethod
    def create(cls, root: Path, name: str = "Projekt") -> "Session":
        ps = ProjectService()
        ps.create_project(name, root)
        return cls(ps)

    @property
    def data(self) -> ProjectData:
        return self.ps.data

    @property
    def folder(self) -> Path:
        return self.ps.project_path.parent

    def save_and_reopen(self) -> None:
        self.ps.save_project()
        path = self.ps.project_path
        ps = ProjectService()
        ps.open_project(path)
        self.ps = ps

    def export(self, name: str = "export.ged"):
        path = self.folder / name
        result = GEDCOMExporter().export(self.data, path)
        return path, result

    def import_file(self, path: Path) -> ImportResult:
        return self.service.run(self.ps.data, path, self.folder, self.ps)


@pytest.fixture
def source_project(tmp_path: Path) -> Session:
    session = Session.create(tmp_path / "a")
    build_data(session.data)
    session.ps.mark_changed("test")
    return session


def _place_chain(data: ProjectData, place_id: str | None) -> list[str]:
    places = {p.id: p for p in data.places}
    chain: list[str] = []
    while place_id:
        chain.append(places[place_id].name)
        place_id = places[place_id].parent_place_id
    # The importer adds country and continent above the stored chain.
    return chain[:2]


def _titles(data: ProjectData, refs) -> Counter:
    titles = {s.id: s.title for s in data.sources}
    return Counter(titles[r.source_id] for r in refs)


def _event_title_multiset(data: ProjectData, event: Event, skip_from_place: bool) -> Counter:
    refs = [
        c.ref for c in event_citations(event)
        if not (skip_from_place and c.context == CitationContext.FROM_PLACE)
    ]
    return _titles(data, refs)


def _citations_per_context(data: ProjectData, event: Event) -> dict:
    titles = {s.id: s.title for s in data.sources}
    result: dict[str, list[tuple]] = {}
    for c in event_citations(event):
        result.setdefault(c.context.value, []).append(
            (titles[c.ref.source_id], c.ref.quality, c.ref.note, tuple(c.ref.aspects))
        )
    return result


def _key(event: Event) -> tuple:
    d = event.date
    return (event.type, (d.value or d.original_text) if d else None)


def _dates_equal_ignoring_refs(a: DateValue | None, b: DateValue | None) -> bool:
    if a is None or b is None:
        return a is b
    return dataclasses.replace(a, source_refs=[]) == dataclasses.replace(b, source_refs=[])


# ---------------------------------------------------------------------------
# Save and reopen (14.11, 16.6, 21.7, 22.33, 12.7)
# ---------------------------------------------------------------------------


def test_source_project_dates_are_valid(source_project: Session) -> None:
    """Guard for the fixture: every date of the project passes the validator."""
    for event in source_project.data.events:
        if event.date is not None:
            assert validate_date_value(event.date) == [], event.id


def test_save_and_reopen_keeps_every_field(source_project: Session) -> None:
    before = copy.deepcopy(source_project.data)
    canonical = serialize(before)
    source_project.save_and_reopen()
    after = source_project.data

    assert after.events == before.events
    assert after.residences == before.residences
    assert after.places == before.places
    assert after.sources == before.sources
    assert serialize(after) == canonical

    # Spot checks that name the new fields.
    by_id = {e.id: e for e in after.events}
    assert by_id["event_1"].source_refs[0].source_id == "source_1"
    assert by_id["event_1"].date.source_refs[0].source_id == "source_2"
    assert by_id["event_1"].place.source_refs[0].source_id == "source_3"
    assert by_id["event_16"].from_place.place_id == "place_2"
    assert by_id["event_16"].from_place.source_refs[0].source_id == "source_1"
    assert by_id["event_2"].date.qualifier == "unparsed"
    assert by_id["event_2"].date.original_text == "vid midsommar 1920"
    assert by_id["event_3"].date.calendar == "julian"
    assert by_id["event_14"].date.original_text == "INT 1863 (cirka)"
    assert by_id["event_1"].date.original_text == "1850-03-04"
    assert Counter(e.date.qualifier for e in after.events if e.date) == Counter(
        e.date.qualifier for e in before.events if e.date
    )


def test_save_and_reopen_keeps_origins_and_flytt_links(source_project: Session) -> None:
    keys_before = {
        "events": {e.id: origin_key(e.origin) for e in source_project.data.events if e.origin},
        "residences": {
            r.id: [origin_key(o) for o in r.origins] for r in source_project.data.residences
        },
    }
    source_project.save_and_reopen()
    keys_after = {
        "events": {e.id: origin_key(e.origin) for e in source_project.data.events if e.origin},
        "residences": {
            r.id: [origin_key(o) for o in r.origins] for r in source_project.data.residences
        },
    }
    assert keys_after == keys_before
    residences = {r.id: r for r in source_project.data.residences}
    assert residences["residence_1"].end.event_id == "event_16"
    assert residences["residence_2"].start.event_id == "event_16"
    assert residences["residence_2"].origins == []
    assert [o.instance for o in residences["residence_1"].origins] == [0, 1]


def test_export_is_identical_before_and_after_reopen(source_project: Session) -> None:
    before_path, _ = source_project.export("before.ged")
    source_project.save_and_reopen()
    after_path, _ = source_project.export("after.ged")
    assert after_path.read_text(encoding="utf-8") == before_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Export and import into a new project (11.9, 12.7, 14.11, 16.6)
# ---------------------------------------------------------------------------


def _import_into_new(source: Session, tmp_path: Path) -> tuple[Session, Path, object]:
    path, export = source.export()
    target = Session.create(tmp_path / "b", "Mål")
    target.import_file(path)
    return target, path, export


def test_export_import_keeps_dates_citations_and_texts(
    source_project: Session, tmp_path: Path
) -> None:
    target, path, export = _import_into_new(source_project, tmp_path)
    exported = [e for e in source_project.data.events]
    imported = {_key(e): e for e in target.data.events}
    assert len(imported) == len(target.data.events) == len(exported)

    for original in exported:
        got = imported[_key(original)]
        assert got.type == original.type
        # Dates: qualifier, both endpoints, calendar, precision and original text.
        assert _dates_equal_ignoring_refs(got.date, original.date), original.id
        # Citations per context (event, date, place, from_place), with source title,
        # quality, note and aspects (Requirement 6).
        assert _citations_per_context(target.data, got) == _citations_per_context(
            source_project.data, original
        ), original.id
        # Place.
        original_chain = _place_chain(source_project.data, original.place.place_id) if original.place else []
        got_chain = _place_chain(target.data, got.place.place_id) if got.place else []
        # The importer may add country and continent above the stored chain.
        assert got_chain[: len(original_chain)] == original_chain, original.id
        # Every imported event has a fresh origin.
        assert got.origin is not None

    # The every qualifier of the project is present after the import.
    assert {e.date.qualifier for e in target.data.events if e.date} == {
        e.date.qualifier for e in source_project.data.events if e.date
    }
    assert any(e.date.calendar == "julian" for e in target.data.events if e.date)
    unparsed = imported[("death", "vid midsommar 1920")]
    assert unparsed.date.qualifier == "unparsed"
    assert unparsed.date.original_text == "vid midsommar 1920"
    assert unparsed.date.value == ""
    assert imported[("census", "1863")].date.original_text == "INT 1863 (cirka)"
    assert imported[("birth", "1850-03-04")].date.original_text == "1850-03-04"


def test_export_import_flytt_documented_limits(
    source_project: Session, tmp_path: Path
) -> None:
    """from_place and residence links do not travel in GEDCOM (F29, F30, 18.15)."""
    target, path, export = _import_into_new(source_project, tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "2 NOTE Från: Ljusdal, Gävleborgs län" in text
    assert not any("ursprungsplats" in w for w in export.warnings)
    flytt = [e for e in target.data.events if e.type == "flytt"]
    assert len(flytt) == 1
    original = next(e for e in source_project.data.events if e.type == "flytt")
    assert _place_chain(target.data, flytt[0].from_place.place_id) == _place_chain(
        source_project.data, original.from_place.place_id
    )
    assert _place_chain(target.data, flytt[0].place.place_id) == ["Gävle", "Gävleborgs län"]
    assert _dates_equal_ignoring_refs(flytt[0].date, _dv("1860-05-01"))
    # Endpoint links travel as _SLK_EREF: the link equals the original event
    # after mapping (the imported event has the same type and date).
    def _linked(data, fact):
        def one(event_id):
            event = next((e for e in data.events if e.id == event_id), None)
            return None if event is None else _key(event)
        return (one(fact.start.event_id), one(fact.end.event_id))

    got_links = Counter(_linked(target.data, f) for f in target.data.residences)
    want_links = Counter(_linked(source_project.data, f) for f in source_project.data.residences)
    assert got_links == want_links
    assert got_links[(None, _key(original))] == 1


def test_export_import_keeps_residences(source_project: Session, tmp_path: Path) -> None:
    target, _path, _export = _import_into_new(source_project, tmp_path)
    original = source_project.data
    assert len(target.data.residences) == len(original.residences)
    got = Counter(
        (
            tuple(_place_chain(target.data, r.place_id)),
            r.start.latest or None,
            r.end.earliest or None,
            tuple(sorted(_titles(target.data, [o.source_ref for o in r.observations]).items())),
        )
        for r in target.data.residences
    )
    want = Counter(
        (
            tuple(_place_chain(original, r.place_id)),
            r.start.latest or None,
            r.end.earliest or None,
            tuple(sorted(_titles(original, [o.source_ref for o in r.observations]).items())),
        )
        for r in original.residences
    )
    assert got == want
    assert all(len(r.origins) == 1 for r in target.data.residences)


def test_second_import_of_exported_file_creates_nothing(
    source_project: Session, tmp_path: Path
) -> None:
    target, path, _export = _import_into_new(source_project, tmp_path)
    events_before = copy.deepcopy(target.data.events)
    residences_before = copy.deepcopy(target.data.residences)
    canonical = serialize(target.data)
    result = target.import_file(path)
    assert result.events_added == 0
    assert result.residences_added == 0
    assert target.data.events == events_before
    assert target.data.residences == residences_before
    assert serialize(target.data) == canonical


# ---------------------------------------------------------------------------
# Imported project, pending translation, save, reopen, re-import (20.22, 22.33)
# ---------------------------------------------------------------------------


def test_imported_project_saved_reopened_and_reimported_creates_nothing(
    source_project: Session, tmp_path: Path
) -> None:
    target, path, _export = _import_into_new(source_project, tmp_path)
    assert target.ps.pending_translation is not None  # translation is staged, not written
    events_before = copy.deepcopy(target.data.events)
    residences_before = copy.deepcopy(target.data.residences)
    event_keys = {e.id: origin_key(e.origin) for e in events_before}
    residence_keys = {r.id: [origin_key(o) for o in r.origins] for r in residences_before}

    target.save_and_reopen()

    assert target.ps.pending_translation is None
    assert target.data.events == events_before
    assert target.data.residences == residences_before
    assert {e.id: origin_key(e.origin) for e in target.data.events} == event_keys
    assert {
        r.id: [origin_key(o) for o in r.origins] for r in target.data.residences
    } == residence_keys

    result = target.import_file(path)
    assert result.events_added == 0
    assert result.residences_added == 0
    assert target.data.events == events_before
    assert target.data.residences == residences_before
    assert len(target.data.persons) == 1
