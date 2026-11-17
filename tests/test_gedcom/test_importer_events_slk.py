"""Importer side of events: _SLK_ROLE, _SLK_EVTYPE, _SLK_EID, _SLK_FROMPLAC (task 6.2).

Focused tests; the full event test suite is task 6.3.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.model.event import Event
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.persistence.serialization import deserialize, serialize
from slaktbusken.services.import_service import ImportService
from slaktbusken.services.project_service import ProjectService
from slaktbusken.services.report_service import ReportService
from slaktbusken.services.validation_service import ValidationService
from tests.test_gedcom_roundtrip import fixtures
from tests.test_gedcom_roundtrip.synthetic import build_synthetic_project

HEAD = (
    "0 HEAD\n1 SOUR T\n1 GEDC\n2 VERS 5.5.1\n2 FORM LINEAGE-LINKED\n"
    "1 CHAR UTF-8\n1 _SLK_VERS 1\n"
)

_SERVICES: dict[Path, ProjectService] = {}


def _import(text: str, tmp_path: Path, data: ProjectData | None = None):
    data = data or ProjectData(project=ProjectMetadata(title="T"))
    ps = _SERVICES.get(tmp_path)
    if ps is None:
        ps = _SERVICES[tmp_path] = ProjectService()
    ps._project_data = data
    ged = tmp_path / "in.ged"
    ged.write_text(text, encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    service = ImportService(ValidationService(), ReportService())
    result = service.run(data, ged, project, ps)
    return data, result


def _indi(xref: str, given: str, *event_blocks: str) -> str:
    return f"0 {xref} INDI\n1 NAME {given} /X/\n" + "".join(event_blocks)


def _fallback(token: str | None, role: str = "spouse", date: str = "1900",
              place: str = "Ljusdal", evtype: str = "marriage") -> str:
    lines = ["1 EVEN", "2 TYPE Vigsel", f"2 _SLK_EVTYPE {evtype}"]
    if token is not None:
        lines.append(f"2 _SLK_EID {token}")
    if role:
        lines.append(f"2 _SLK_ROLE {role}")
    lines.append(f"2 DATE {date}")
    lines.append(f"2 PLAC {place}")
    return "\n".join(lines) + "\n"


def _marriages(data: ProjectData) -> list[Event]:
    return [e for e in data.events if e.type == "marriage"]


def _names(data: ProjectData, event: Event) -> list[tuple[str, str]]:
    by_id = {p.id: p.names[0].given for p in data.persons}
    return sorted((by_id[p.person_id], p.role) for p in event.participants)


def _snapshot(data: ProjectData) -> str:
    """Events, persons and residences (family.event_ids of foster events is not
    part of this task: a re-import appends the end event to the family)."""
    raw = json.loads(serialize(copy.deepcopy(data)))
    return json.dumps(
        {k: raw.get(k) for k in ("persons", "events", "residences")}, sort_keys=True
    )


# ---------------------------------------------------------------------------
# Individual_Fallback: join by token only
# ---------------------------------------------------------------------------


def test_same_token_on_two_indi_gives_one_event_with_both_participants(tmp_path):
    text = HEAD + _indi("@I1@", "Anna", _fallback("event_7")) + _indi(
        "@I2@", "Bo", _fallback("event_7")) + "0 TRLR\n"
    data, _ = _import(text, tmp_path)
    (event,) = _marriages(data)
    assert _names(data, event) == [("Anna", "spouse"), ("Bo", "spouse")]
    assert event.custom_type_name is None


def test_separate_marriages_with_equal_date_and_place_stay_separate(tmp_path):
    text = (
        HEAD
        + _indi("@I1@", "Anna", _fallback("event_1"))
        + _indi("@I2@", "Bo", _fallback("event_1"))
        + _indi("@I3@", "Cia", _fallback("event_2"))
        + _indi("@I4@", "Dan", _fallback("event_2"))
        + "0 TRLR\n"
    )
    data, _ = _import(text, tmp_path)
    events = _marriages(data)
    assert len(events) == 2
    assert sorted(tuple(n for n, _r in _names(data, e)) for e in events) == [
        ("Anna", "Bo"), ("Cia", "Dan")]


def test_equal_date_place_without_token_never_join(tmp_path):
    text = (
        HEAD + _indi("@I1@", "Anna", _fallback(None))
        + _indi("@I2@", "Bo", _fallback(None)) + "0 TRLR\n"
    )
    data, result = _import(text, tmp_path)
    assert len(_marriages(data)) == 2
    assert all(len(e.participants) == 1 for e in _marriages(data))


def test_single_indi_token_and_empty_token_make_single_events_without_warning(tmp_path):
    text = (
        HEAD + _indi("@I1@", "Anna", _fallback("event_9"))
        + _indi("@I2@", "Bo", _fallback("")) + "0 TRLR\n"
    )
    data, result = _import(text, tmp_path)
    assert len(_marriages(data)) == 2
    assert not [w for w in result.warnings if "_SLK_EID" in str(w)]


def test_duplicate_token_on_one_indi_uses_first_and_warns(tmp_path):
    text = (
        HEAD
        + _indi("@I1@", "Anna", _fallback("event_1", date="1900"),
                _fallback("event_1", date="1950"))
        + "0 TRLR\n"
    )
    data, result = _import(text, tmp_path)
    (event,) = _marriages(data)
    assert event.date.value == "1900"
    assert any("_SLK_EID" in str(w) for w in result.warnings)


def test_fallback_roles_come_from_slk_role(tmp_path):
    text = (
        HEAD + _indi("@I1@", "Anna", _fallback("event_1", role="godfather"))
        + _indi("@I2@", "Bo", _fallback("event_1", role="")) + "0 TRLR\n"
    )
    data, _ = _import(text, tmp_path)
    (event,) = _marriages(data)
    assert _names(data, event) == [("Anna", "godfather"), ("Bo", "subject")]


def test_origins_one_per_indi_record_and_second_import_creates_nothing(tmp_path):
    text = (
        HEAD + _indi("@I1@", "Anna", _fallback("event_1"))
        + _indi("@I2@", "Bo", _fallback("event_1"))
        + _indi("@I3@", "Cia", _fallback("event_2")) + "0 TRLR\n"
    )
    data, _ = _import(text, tmp_path)
    merged = next(e for e in _marriages(data) if len(e.participants) == 2)
    origins = [merged.origin, *merged.extra_origins]
    assert len(origins) == 2
    assert {o.owner_xref for o in origins} == {"@I1@", "@I2@"}
    assert {o.owner_id for o in origins} == {p.person_id for p in merged.participants}
    assert all(o.record_hash for o in origins)
    assert len({o.record_hash for o in origins}) == 1  # same structure text

    before = _snapshot(data)
    data2, result = _import(text, tmp_path, data)
    assert _snapshot(data2) == before
    assert result.events_added == 0


def test_reimport_with_added_participant_joins_existing_event(tmp_path):
    first = (
        HEAD + _indi("@I1@", "Anna", _fallback("event_1"))
        + _indi("@I2@", "Bo", _fallback("event_1")) + "0 TRLR\n"
    )
    data, _ = _import(first, tmp_path)
    (event,) = _marriages(data)
    second = (
        HEAD + _indi("@I1@", "Anna", _fallback("event_1"))
        + _indi("@I2@", "Bo", _fallback("event_1"))
        + _indi("@I3@", "Cia", _fallback("event_1", role="vittne")) + "0 TRLR\n"
    )
    data2, _ = _import(second, tmp_path, data)
    (event2,) = _marriages(data2)
    assert event2.id == event.id
    assert _names(data2, event2) == [
        ("Anna", "spouse"), ("Bo", "spouse"), ("Cia", "vittne")]
    assert len([event2.origin, *event2.extra_origins]) == 3


def test_new_participant_listed_before_matched_ones_folds_into_existing_event(tmp_path):
    first = (
        HEAD + _indi("@I1@", "Anna", _fallback("event_1"))
        + _indi("@I2@", "Bo", _fallback("event_1")) + "0 TRLR\n"
    )
    data, _ = _import(first, tmp_path)
    (event,) = _marriages(data)
    second = (
        HEAD + _indi("@I3@", "Cia", _fallback("event_1", role="vittne"))
        + _indi("@I1@", "Anna", _fallback("event_1"))
        + _indi("@I2@", "Bo", _fallback("event_1")) + "0 TRLR\n"
    )
    data2, _ = _import(second, tmp_path, data)
    (event2,) = _marriages(data2)
    assert event2.id == event.id
    assert len(event2.participants) == 3
    assert len([event2.origin, *event2.extra_origins]) == 3
    third_data, _ = _import(second, tmp_path, data2)
    assert len(_marriages(third_data)) == 1


def test_merged_event_survives_save_and_reopen(tmp_path):
    text = (
        HEAD + _indi("@I1@", "Anna", _fallback("event_1"))
        + _indi("@I2@", "Bo", _fallback("event_1")) + "0 TRLR\n"
    )
    data, _ = _import(text, tmp_path)
    reopened = deserialize(serialize(data))
    (event,) = _marriages(reopened)
    assert len(event.extra_origins) == 1
    data2, _ = _import(text, tmp_path, reopened)
    assert len(_marriages(data2)) == 1


# ---------------------------------------------------------------------------
# _SLK_ROLE, _SLK_EVTYPE
# ---------------------------------------------------------------------------


def test_slk_role_on_known_tag_event(tmp_path):
    text = (
        HEAD + _indi("@I1@", "Anna", "1 BAPM\n2 DATE 1850\n2 _SLK_EID e1\n")
        + _indi("@I2@", "Bo", "1 BAPM\n2 DATE 1850\n2 _SLK_EID e1\n2 _SLK_ROLE godfather\n")
        + "0 TRLR\n"
    )
    data, _ = _import(text, tmp_path)
    (event,) = [e for e in data.events if e.type == "baptism"]
    assert _names(data, event) == [("Anna", "subject"), ("Bo", "godfather")]


def test_known_slk_evtype_creates_that_type(tmp_path):
    text = (
        HEAD
        + _indi("@I1@", "Anna", "1 EVEN\n2 TYPE name_change\n2 _SLK_EVTYPE name_change\n")
        + "0 TRLR\n"
    )
    data, result = _import(text, tmp_path)
    (event,) = data.events
    assert event.type == "name_change"
    assert event.custom_type_name is None
    assert not [w for w in result.warnings if "_SLK_EVTYPE" in str(w)]


def test_custom_family_event_keeps_its_name(tmp_path):
    text = (
        HEAD
        + _indi("@I1@", "Anna", "1 EVEN\n2 TYPE Samboavtal\n"
                "2 _SLK_EVTYPE custom_family_event\n2 _SLK_EID e1\n")
        + _indi("@I2@", "Bo", "1 EVEN\n2 TYPE Samboavtal\n"
                "2 _SLK_EVTYPE custom_family_event\n2 _SLK_EID e1\n")
        + "0 TRLR\n"
    )
    data, _ = _import(text, tmp_path)
    (event,) = data.events
    assert event.type == "custom_family_event"
    assert event.custom_type_name == "Samboavtal"
    assert len(event.participants) == 2


def test_unknown_slk_evtype_becomes_custom_individual_event_with_warning(tmp_path):
    text = (
        HEAD
        + _indi("@I1@", "Anna", "1 EVEN\n2 TYPE Mystisk\n2 _SLK_EVTYPE zorb\n2 DATE 1900\n")
        + "0 TRLR\n"
    )
    data, result = _import(text, tmp_path)
    (event,) = data.events
    assert event.type == "custom_individual_event"
    assert event.custom_type_name == "Mystisk"
    assert any("zorb" in str(w) for w in result.warnings)


def test_placement_event_ignores_slk_role(tmp_path):
    text = (
        HEAD + _indi("@I1@", "Anna", "1 EVEN\n2 TYPE Fosterhem\n2 _SLK_ROLE godfather\n")
        + "0 TRLR\n"
    )
    data, _ = _import(text, tmp_path)
    (event,) = [e for e in data.events if e.type == "foster_home"]
    assert "godfather" not in {p.role for p in event.participants}


# ---------------------------------------------------------------------------
# _SLK_FROMPLAC
# ---------------------------------------------------------------------------


def test_slk_fromplac_sets_from_place_with_plac_resolution(tmp_path):
    text = (
        HEAD
        + _indi("@I1@", "Anna", "1 EVEN\n2 TYPE Flytt\n2 DATE 1860\n"
                "2 PLAC Gävle\n2 NOTE Från: Ljusdal\n2 _SLK_FROMPLAC Ljusdal\n")
        + "0 TRLR\n"
    )
    data, _ = _import(text, tmp_path)
    (event,) = data.events
    assert event.type == "flytt"
    assert event.from_place is not None
    assert event.place is not None and event.place.place_id != event.from_place.place_id
    names = {p.id: p.name for p in data.places}
    assert names[event.from_place.place_id] == "Ljusdal"


def test_flytt_without_fromplac_has_no_from_place(tmp_path):
    text = HEAD + _indi("@I1@", "Anna", "1 EVEN\n2 TYPE Flytt\n2 PLAC Gävle\n") + "0 TRLR\n"
    data, _ = _import(text, tmp_path)
    assert data.events[0].from_place is None


# ---------------------------------------------------------------------------
# Whole-project round trips
# ---------------------------------------------------------------------------


def _roundtrip(source: ProjectData, tmp_path: Path):
    ged = tmp_path / "out.ged"
    GEDCOMExporter().export(source, ged)
    return ged.read_text(encoding="utf-8")


def _marriage_keys(data: ProjectData) -> list:
    by_id = {p.id: p.names[0].given for p in data.persons}
    return sorted(
        (e.date.value if e.date else "", tuple(sorted(by_id[p.person_id] for p in e.participants)))
        for e in data.events if e.type == "marriage"
    )


def test_synthetic_orphan_marriages_stay_two_and_reimport_is_idempotent(tmp_path):
    source = build_synthetic_project()
    text = _roundtrip(source, tmp_path)
    data, _ = _import(text, tmp_path)

    fallback = [
        e for e in data.events
        if e.type == "marriage" and e.date and e.date.value == "1900-06-15"
    ]
    assert len(fallback) == 2
    assert sorted(tuple(sorted(n for n, _r in _names(data, e))) for e in fallback) == [
        ("Axel", "Britta"), ("Carl", "Disa")]
    assert all(len(e.participants) == 2 for e in fallback)

    before = _snapshot(data)
    data2, result = _import(text, tmp_path, data)
    assert _snapshot(data2) == before
    assert result.events_added == 0


def test_synthetic_flytt_from_place_and_godfather_role_roundtrip(tmp_path):
    source = build_synthetic_project()
    data, _ = _import(_roundtrip(source, tmp_path), tmp_path)

    places = {p.id: p.name for p in data.places}
    flytt = sorted(
        (e.date.value, places[e.from_place.place_id], places[e.place.place_id])
        for e in data.events if e.type == "flytt"
    )
    assert flytt == [("1860-05-01", "Ljusdal", "Gävle"), ("1872-10", "Gävle", "Ljusdal")]

    (baptism,) = [
        e for e in data.events
        if e.type == "baptism" and e.date and e.date.value == "1850-03-10"
    ]
    assert _names(data, baptism) == [("Erik", "godfather"), ("Karl", "subject")]


def test_mergetest_marriages_roundtrip_and_reimport_creates_nothing(tmp_path):
    source = fixtures.load_mergetest()
    text = _roundtrip(source, tmp_path)
    data, _ = _import(text, tmp_path)
    assert _marriage_keys(data) == _marriage_keys(source)

    before = _snapshot(data)
    data2, result = _import(text, tmp_path, data)
    assert _snapshot(data2) == before
    assert result.events_added == 0
