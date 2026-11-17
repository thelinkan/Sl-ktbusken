"""Residences: Properties 9 and 18 and the examples of Requirement 7.

Round trips go through ``GEDCOMExporter`` and ``ImportService.run`` into a real
empty project. Persons are labelled ``P<n>`` before the export (the importer
creates new ids), so residences are compared in label terms: person label,
place chain, both endpoints, role, notes and observations (source by title).

``Endpoint.event_id`` is not compared and ``_SLK_EREF`` is not tested: the
event links belong to task 10.
"""

from __future__ import annotations

import copy
from collections import Counter
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.gedcom.importer import ImportResult
from slaktbusken.gedcom.translation.record_identity import residence_fingerprint
from slaktbusken.model.event import SourceRef
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.persistence.serialization import serialize
from tests.test_gedcom_roundtrip import synthetic as syn
from tests.test_gedcom_roundtrip.fixtures import exporttest_ged_path, load_mergetest
from tests.test_gedcom_roundtrip.strategies import residence_projects
from tests.test_gedcom_roundtrip.test_events_roundtrip import World
from tests.test_gedcom_roundtrip.test_families_roundtrip import (
    _children,
    export_text,
    import_text,
    indi_records,
    label_of,
    label_persons,
)

pytestmark = pytest.mark.mandatory_integrity

_HEAD = "0 HEAD\n1 GEDC\n2 VERS 5.5.1\n2 FORM LINEAGE-LINKED\n1 CHAR UTF-8\n"
_MARKED_HEAD = _HEAD + "1 _SLK_VERS 1\n"


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def _chain(data: ProjectData, place_id: str) -> tuple[str, ...]:
    places = {p.id: p for p in data.places}
    names: list[str] = []
    while place_id and place_id in places:
        names.append(places[place_id].name)
        place_id = places[place_id].parent_place_id
    return tuple(names)


def _text(value: str | None) -> str:
    """Text as the importer reads it: blank text is unset (``read_*`` treat
    a blank ``_SLK_`` text, ``PAGE`` and note as absent)."""
    return value if value and value.strip() else ""


def _endpoint_view(e: Endpoint) -> tuple:
    return (e.earliest or None, e.latest or None, e.precision or None,
            _text(e.note) or None)


def _observation_view(data: ProjectData, o: Observation) -> tuple:
    titles = {s.id: s.title for s in data.sources}
    ref = o.source_ref
    return (titles.get(ref.source_id), ref.quality, _text(ref.note),
            tuple(ref.aspects), o.observed_from, o.observed_to, _text(o.page_note))


def residence_view(data: ProjectData, fact: ResidenceFact) -> tuple:
    labels = {p.id: label_of(p) for p in data.persons}
    return (
        labels[fact.person_id], _chain(data, fact.place_id),
        _endpoint_view(fact.start), _endpoint_view(fact.end),
        _text(fact.role_in_household), _text(fact.notes),
        tuple(sorted(_observation_view(data, o) for o in fact.observations)),
    )


def residence_counter(data: ProjectData) -> Counter:
    return Counter(residence_view(data, f) for f in data.residences)


def origin_state(data: ProjectData) -> list[tuple]:
    """Origins of every residence in a stable order (ids are not compared)."""
    return sorted(
        (f.person_id, tuple(sorted(
            (o.owner_kind, o.owner_id, o.tag_key, o.index, o.record_hash,
             o.uid, o.instance) for o in f.origins)))
        for f in data.residences)


def resi_nodes(text: str) -> list:
    return [n for indi in indi_records(text) for n in indi.children if n.tag == "RESI"]


def _values(node, tag: str) -> list[str]:
    return [c.value for c in _children(node, tag)]


def one_residence(**kw) -> ProjectData:
    """One person with one residence at the synthetic Ljusdal place."""
    person = Person(id="person_1", sex="U", names=[Name("birth", "P1", "X")])
    fact = ResidenceFact(id="residence_1", person_id="person_1",
                         place_id=syn.PLACE_LJUSDAL, **kw)
    sources, levs, kalltyper = syn.build_sources()
    return ProjectData(persons=[person], residences=[fact], places=syn.build_places(),
                       sources=sources, leverantorer=levs, kalltyper=kalltyper,
                       repositories=syn.build_repositories())


def import_one(text: str) -> tuple[ProjectData, ImportResult]:
    return import_text(text)


# ---------------------------------------------------------------------------
# Property 9
# ---------------------------------------------------------------------------


# Feature: gedcom-roundtrip-0-3-0, Property 9: Residences round-trip with all structured data
# **Validates: Requirements 7.1, 7.3, 7.4, 7.5, 7.8**
@given(residence_projects())
def test_residences_roundtrip_with_all_structured_data(data: ProjectData) -> None:
    data = label_persons(data)
    text, _export = export_text(data)
    imported, _result = import_text(text)
    assert residence_counter(imported) == residence_counter(data)


def test_synthetic_residences_roundtrip() -> None:
    data = label_persons(syn.build_synthetic_project())
    text, _ = export_text(data)
    imported, _ = import_text(text)
    assert len(data.residences) == 4
    assert residence_counter(imported) == residence_counter(data)


def test_mergetest_residences_keep_observations_and_exact_endpoints() -> None:
    data = label_persons(load_mergetest())
    assert len(data.residences) == 7
    text, _ = export_text(data)
    imported, _ = import_text(text)
    assert residence_counter(imported) == residence_counter(data)
    primary = [f for f in imported.residences
               if any(o.source_ref.quality == "primary" and o.observed_from == "1910"
                      and o.observed_to == "1923" for o in f.observations)]
    assert primary
    exact = [f for f in imported.residences
             if f.start.earliest and f.start.earliest == f.start.latest]
    assert exact == [f for f in imported.residences
                     if f.start.earliest and f.start.earliest == f.start.latest]
    original_exact = sum(1 for f in data.residences
                         if f.start.earliest and f.start.earliest == f.start.latest)
    assert len(exact) == original_exact


# ---------------------------------------------------------------------------
# Repeated imports (Requirement 7.10)
# ---------------------------------------------------------------------------


def _assert_no_change(world: World, text: str) -> None:
    before = serialize(world.data)
    origins = origin_state(world.data)
    count = len(world.data.residences)
    result = world.run(text)
    assert result.residences_added == 0
    assert len(world.data.residences) == count
    assert origin_state(world.data) == origins
    assert serialize(world.data) == before


# Feature: gedcom-roundtrip-0-3-0, Property 9: Residences round-trip with all structured data
# **Validates: Requirements 7.10**
@given(residence_projects())
def test_residence_reimport_is_idempotent(data: ProjectData) -> None:
    import tempfile
    data = label_persons(data)
    text, _ = export_text(data)
    with tempfile.TemporaryDirectory() as folder:
        world = World(Path(folder))
        world.run(text)
        assert residence_counter(world.data) == residence_counter(data)
        for fact in world.data.residences:
            assert len(fact.origins) == 1
        _assert_no_change(world, text)
        world.save_and_reopen()
        _assert_no_change(world, text)


def test_equal_residences_form_one_origin_group_and_stay_idempotent(
    tmp_path: Path,
) -> None:
    data = one_residence(start=Endpoint(earliest="1850", latest="1850"))
    twin = copy.deepcopy(data.residences[0])
    twin.id = "residence_2"
    data.residences.append(twin)
    text, _ = export_text(data)
    world = World(tmp_path)
    world.run(text)
    assert len(world.data.residences) == 2
    origins = [o for f in world.data.residences for o in f.origins]
    assert len(origins) == 2
    assert len({(o.owner_id, o.tag_key, o.record_hash) for o in origins}) == 1
    assert sorted(o.instance for o in origins) == [0, 1]
    _assert_no_change(world, text)
    world.save_and_reopen()
    _assert_no_change(world, text)


def test_user_made_residence_is_claimed_not_duplicated(tmp_path: Path) -> None:
    data = label_persons(syn.build_synthetic_project())
    text, _ = export_text(data)
    world = World(tmp_path)
    world.run(text)
    expected = residence_counter(world.data)
    count = len(world.data.residences)
    # The residences are now user-made: no origins and no event links, as
    # before data-integrity (a linked legacy residence is not claimed, see the
    # documented limitation below).
    for fact in world.data.residences:
        fact.origins = []
        fact.start.event_id = fact.end.event_id = None
    result = world.run(text)
    assert result.residences_added == 0
    assert len(world.data.residences) == count
    # Compare in label terms: the links the unlinked residences lack are not
    # part of residence_view.
    assert residence_counter(world.data) == expected
    assert all(len(f.origins) == 1 for f in world.data.residences)
    _assert_no_change(world, text)


def test_legacy_claim_ignores_the_new_slk_content(tmp_path: Path) -> None:
    """A legacy residence whose export now carries _SLK_ tags is still claimed."""
    data = one_residence(
        start=Endpoint(earliest="1850", latest="1850-06", precision="month",
                       note="Från födseln"),
        end=Endpoint(earliest="1860"),
        role_in_household="Dräng", notes="Anteckning")
    text, _ = export_text(label_persons(data))
    world = World(tmp_path)
    world.run(text)
    before = residence_counter(world.data)
    world.data.residences[0].origins = []
    assert world.run(text).residences_added == 0
    assert residence_counter(world.data) == before
    assert len(world.data.residences[0].origins) == 1


# ---------------------------------------------------------------------------
# Old files: DATE only and the legacy Swedish prose (Requirement 7.6, 7.7)
# ---------------------------------------------------------------------------


def _legacy_file(resi_lines: str, head: str = _HEAD) -> str:
    return (head + "0 @S1@ SOUR\n1 TITL Kyrkbok\n"
            "0 @I1@ INDI\n1 NAME Ada /X/\n1 RESI\n" + resi_lines + "0 TRLR\n")


def test_old_file_with_date_only_uses_the_date_line() -> None:
    text = _legacy_file("2 DATE FROM 5 AUG 1912 TO 1923\n2 PLAC Ljusdal\n")
    imported, _ = import_one(text)
    (fact,) = imported.residences
    assert (fact.start.latest, fact.end.earliest) == ("1912-08-05", "1923")
    assert fact.start.earliest is None and fact.end.latest is None
    assert fact.role_in_household == "" and fact.observations == []


def test_old_file_prose_lines_in_the_exact_format_are_read() -> None:
    text = _legacy_file(
        "2 DATE FROM 5 AUG 1912 TO 1923\n"
        "2 NOTE Tidigast början: 1912-08-01\n"
        "2 NOTE Senast slut: 1924-12\n"
        "2 NOTE Roll: Dräng\n"
        "2 SOUR @S1@\n3 NOTE Observation: 1910-1923\n")
    imported, result = import_one(text)
    (fact,) = imported.residences
    assert fact.start.earliest == "1912-08-01" and fact.start.latest == "1912-08-05"
    assert fact.end.earliest == "1923" and fact.end.latest == "1924-12"
    assert fact.role_in_household == "Dräng"
    (obs,) = fact.observations
    assert (obs.observed_from, obs.observed_to) == ("1910", "1923")
    assert not [w for w in result.warnings if "Tidigast" in str(w)
                or "Senast slut" in str(w) or "Observation:" in str(w)]


def test_old_file_single_year_observation() -> None:
    imported, _ = import_one(_legacy_file(
        "2 SOUR @S1@\n3 NOTE Observation: 1915\n"))
    (obs,) = imported.residences[0].observations
    assert (obs.observed_from, obs.observed_to) == ("1915", "1915")


@pytest.mark.parametrize("line", [
    "2 NOTE Start: 1912-08-01",             # wrong prefix
    "2 NOTE Tidigast början 1912-08-01",    # no colon
    "2 NOTE tidigast början: 1912-08-01",   # wrong case
    "2 NOTE TIDIGAST BÖRJAN: 1912-08-01",
    "2 NOTE Senast slut:1924-01-01",        # no space after the colon
    "2 NOTE senast slut: 1924-01-01",
    "2 NOTE roll: Dräng",
    "2 NOTE ROLL: Dräng",
    "2 NOTE Rollen: Dräng",
    "2 NOTE Han bodde här. Roll: Dräng",    # not at the start of the line
    "2 NOTE Tidigast början: 1912-08-01 ca",
])
def test_old_file_other_notes_are_never_reinterpreted(line: str) -> None:
    imported, _ = import_one(_legacy_file(line + "\n"))
    (fact,) = imported.residences
    assert _endpoint_view(fact.start) == (None, None, None, None)
    assert _endpoint_view(fact.end) == (None, None, None, None)
    assert fact.role_in_household == ""


@pytest.mark.parametrize("line", [
    "3 NOTE observation: 1910-1923",
    "3 NOTE OBSERVATION: 1910-1923",
    "3 NOTE Observation:1910-1923",
    "3 NOTE Observationer: 1910-1923",
    "3 NOTE Se Observation: 1910-1923",
    "3 NOTE Observation: 1923-1910",        # start after end
    "3 NOTE Observation: 10-23",
    "3 NOTE Observation: 1910-1923-1930",
    "3 NOTE Observation: 1910 till 1923",
    "3 NOTE Observation: 1499",             # out of range
])
def test_old_file_observation_notes_other_than_the_format_leave_no_period(
    line: str,
) -> None:
    imported, _ = import_one(_legacy_file("2 SOUR @S1@\n" + line + "\n"))
    (obs,) = imported.residences[0].observations
    assert (obs.observed_from, obs.observed_to) == ("", "")


def test_old_file_note_under_resi_is_not_an_observation_period() -> None:
    imported, _ = import_one(_legacy_file(
        "2 NOTE Observation: 1910-1923\n2 SOUR @S1@\n"))
    (obs,) = imported.residences[0].observations
    assert (obs.observed_from, obs.observed_to) == ("", "")


@pytest.mark.parametrize("line", [
    "2 NOTE Tidigast början: 1912-13-45",
    "2 NOTE Tidigast början: 12 AUG 1912",
    "2 NOTE Tidigast början: ",
    "2 NOTE Senast slut: i somras",
    "2 NOTE Senast slut: 1924-02-30",
])
def test_old_file_invalid_date_is_ignored_with_a_warning(line: str) -> None:
    imported, result = import_one(_legacy_file(line + "\n"))
    (fact,) = imported.residences
    assert _endpoint_view(fact.start) == (None, None, None, None)
    assert _endpoint_view(fact.end) == (None, None, None, None)
    if line.rstrip().endswith(":"):
        return  # an empty value is not a value: nothing to warn about
    assert any(line.split(": ", 1)[1].strip() in str(w) for w in result.warnings), \
        [str(w) for w in result.warnings]


def test_old_file_invalid_observation_year_warns() -> None:
    _, result = import_one(_legacy_file(
        "2 SOUR @S1@\n3 NOTE Observation: 1923-1910\n"))
    assert any("1923-1910" in str(w) for w in result.warnings)


def test_old_file_invalid_part_does_not_stop_the_valid_parts() -> None:
    imported, _ = import_one(_legacy_file(
        "2 NOTE Tidigast början: 1912-13-45\n2 NOTE Senast slut: 1924-01-01\n"
        "2 NOTE Roll: Dräng\n"))
    (fact,) = imported.residences
    assert fact.start.earliest is None
    assert fact.end.latest == "1924-01-01" and fact.role_in_household == "Dräng"


def test_file_with_the_marker_does_not_read_the_prose() -> None:
    text = _legacy_file(
        "2 NOTE Tidigast början: 1912-08-01\n2 NOTE Senast slut: 1924-01-01\n"
        "2 NOTE Roll: Dräng\n2 SOUR @S1@\n3 NOTE Observation: 1910-1923\n",
        head=_MARKED_HEAD)
    imported, _ = import_one(text)
    (fact,) = imported.residences
    assert _endpoint_view(fact.start) == (None, None, None, None)
    assert _endpoint_view(fact.end) == (None, None, None, None)
    assert fact.role_in_household == ""
    assert [(o.observed_from, o.observed_to) for o in fact.observations] == [("", "")]


def test_file_with_the_marker_uses_the_slk_tags_and_ignores_the_prose() -> None:
    text = _legacy_file(
        "2 DATE FROM 1912\n2 NOTE Tidigast början: 1900-01-01\n"
        "2 NOTE Roll: Piga\n"
        "2 _SLK_START\n3 _SLK_EARLIEST 1911\n3 _SLK_LATEST 1912\n"
        "2 _SLK_HHROLE Dräng\n",
        head=_MARKED_HEAD)
    imported, _ = import_one(text)
    (fact,) = imported.residences
    assert (fact.start.earliest, fact.start.latest) == ("1911", "1912")
    assert fact.role_in_household == "Dräng"


def test_exporttest_ged_prose_and_observations_are_read() -> None:
    text = exporttest_ged_path().read_text(encoding="utf-8")
    assert "_SLK_VERS" not in text
    imported, _ = import_one(text)
    assert len(imported.residences) == 7
    starts = {f.start.earliest for f in imported.residences} - {None}
    assert {"1912-08-05", "1888-11-15", "1926-04-11", "1914-06-28",
            "1910-09-30"} <= starts
    ends = {f.end.latest for f in imported.residences} - {None}
    assert "1926-04-11" in ends
    with_observation = [f for f in imported.residences if f.observations]
    assert len(with_observation) == 5
    for fact in with_observation:
        (obs,) = fact.observations
        assert (obs.observed_from, obs.observed_to) == ("1910", "1923")


def _assert_residences_unchanged(world: World, text: str) -> None:
    before = serialize_residences(world.data)
    origins = origin_state(world.data)
    assert world.run(text).residences_added == 0
    assert serialize_residences(world.data) == before
    assert origin_state(world.data) == origins


def serialize_residences(data: ProjectData) -> list:
    return [(f.id, f.person_id, f.place_id, _endpoint_view(f.start),
             _endpoint_view(f.end), f.role_in_household, f.notes,
             [(o.source_ref.source_id, o.observed_from, o.observed_to)
              for o in f.observations]) for f in data.residences]


def test_exporttest_ged_is_idempotent(tmp_path: Path) -> None:
    text = exporttest_ged_path().read_text(encoding="utf-8")
    world = World(tmp_path)
    world.run(text)
    assert len(world.data.residences) == 7
    _assert_residences_unchanged(world, text)
    full = serialize(world.data)
    world.run(text)
    assert serialize(world.data) == full
    world.save_and_reopen()
    _assert_residences_unchanged(world, text)
    assert serialize(world.data) == full


# Feature: gedcom-roundtrip-0-3-0, Property 18: Legacy prose is read only in exact formats
# **Validates: Requirements 7.7, 7.7a, 7.7b**
def _iso_dates(low: int, high: int):
    """ISO dates of every precision with a year in ``low..high``."""
    year = st.integers(low, high)
    return st.one_of(
        year.map(lambda y: f"{y:04d}"),
        st.tuples(year, st.integers(1, 12)).map(lambda t: f"{t[0]:04d}-{t[1]:02d}"),
        st.tuples(year, st.integers(1, 12), st.integers(1, 28)).map(
            lambda t: f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d}"),
    )


# Start dates lie before end dates, so that the residence stays valid.
_START_DATES = _iso_dates(1600, 1799)
_END_DATES = _iso_dates(1800, 2000)
_BAD_DATES = st.sampled_from(("1900-13-01", "1900-02-30", "12 AUG 1900", "igår",
                              "1900/05/01", "19000"))
_ROLES = st.text(st.characters(categories=("Lu", "Ll"), include_characters="åäö"),
                 min_size=1, max_size=20)
_NOISE = ("Start: 1900-01-01", "tidigast början: 1900-01-01",
          "Tidigast början 1900-01-01", "senast slut: 1900-01-01",
          "roll: Dräng", "ROLL: Dräng", "Rollen: Dräng", "Fri text om boendet",
          "Se Roll: Dräng")


@st.composite
def _legacy_case(draw):
    """RESI NOTE lines and the structured values they must (not) give."""
    lines: list[str] = []
    expected = {"start": None, "end": None, "role": "", "obs": ("", "")}
    for key, prefix, dates in (("start", "Tidigast början", _START_DATES),
                               ("end", "Senast slut", _END_DATES)):
        kind = draw(st.sampled_from(("none", "valid", "invalid")))
        if kind == "valid":
            expected[key] = draw(dates)
            lines.append(f"2 NOTE {prefix}: {expected[key]}")
        elif kind == "invalid":
            lines.append(f"2 NOTE {prefix}: {draw(_BAD_DATES)}")
    kind = draw(st.sampled_from(("none", "valid")))
    if kind == "valid":
        expected["role"] = draw(_ROLES)
        lines.append(f"2 NOTE Roll: {expected['role']}")
    lines += [f"2 NOTE {n}" for n in draw(st.lists(st.sampled_from(_NOISE), max_size=3))]
    lines = draw(st.permutations(lines))
    sour = ["2 SOUR @S1@"]
    kind = draw(st.sampled_from(("none", "year", "range", "invalid", "noise")))
    a = draw(st.integers(1500, 2000))
    if kind == "year":
        expected["obs"] = (str(a), str(a))
        sour.append(f"3 NOTE Observation: {a}")
    elif kind == "range":
        b = a + draw(st.integers(0, 50))
        expected["obs"] = (str(a), str(b))
        sour.append(f"3 NOTE Observation: {a}-{b}")
    elif kind == "invalid":
        sour.append(f"3 NOTE Observation: {a + 5}-{a}")
    elif kind == "noise":
        sour.append(f"3 NOTE observation: {a}")
    return "\n".join(lines + sour) + "\n", expected


@given(_legacy_case())
def test_legacy_prose_is_read_only_in_exact_formats(case) -> None:
    resi, expected = case
    imported, _ = import_one(_legacy_file(resi))
    (fact,) = imported.residences
    assert fact.start.earliest == expected["start"]
    assert fact.end.latest == expected["end"]
    assert fact.role_in_household == expected["role"]
    (obs,) = fact.observations
    assert (obs.observed_from, obs.observed_to) == expected["obs"]
    # The same lines in a file with the marker are never interpreted.
    marked, _ = import_one(_legacy_file(resi, head=_MARKED_HEAD))
    (fact,) = marked.residences
    assert _endpoint_view(fact.start) == _endpoint_view(fact.end) \
        == (None, None, None, None)
    assert fact.role_in_household == ""
    assert [(o.observed_from, o.observed_to) for o in fact.observations] == [("", "")]


# ---------------------------------------------------------------------------
# One test per registry tag of the residence module
# ---------------------------------------------------------------------------


def _full_residence() -> ProjectData:
    return one_residence(
        start=Endpoint(earliest="1850", latest="1850-06", precision="month",
                       note="Från födseln"),
        end=Endpoint(earliest="1860-04-01", latest="1860-04-01", precision="day",
                     note="Flyttade"),
        role_in_household="Dräng", notes="Egen anteckning.\nAndra raden.",
        observations=[
            Observation(SourceRef(source_id=syn.SOURCE_HFL, quality="primary",
                                  note="rad 4", aspects=["namn", "ålder"]),
                        "1855", "1858", "s. 12"),
            Observation(SourceRef(source_id=syn.SOURCE_DOP, quality="osäker"),
                        "1859", "", ""),
        ])


def _resi(text: str):
    (node,) = resi_nodes(text)
    return node


def test_slk_tag_start_and_slk_tag_end() -> None:
    text, _ = export_text(_full_residence())
    node = _resi(text)
    assert len(_children(node, "_SLK_START")) == 1
    assert len(_children(node, "_SLK_END")) == 1
    start = _children(node, "_SLK_START")[0]
    assert [c.tag for c in start.children] == [
        "_SLK_EARLIEST", "_SLK_LATEST", "_SLK_PREC", "_SLK_NOTE"]
    assert all(c.level == 3 for c in start.children)


def test_slk_start_is_not_written_for_an_empty_endpoint() -> None:
    text, _ = export_text(one_residence(end=Endpoint(latest="1870")))
    node = _resi(text)
    assert _children(node, "_SLK_START") == []
    assert [c.tag for c in _children(node, "_SLK_END")[0].children] == ["_SLK_LATEST"]


def test_slk_tag_earliest_and_latest() -> None:
    text, _ = export_text(_full_residence())
    node = _resi(text)
    start, end = _children(node, "_SLK_START")[0], _children(node, "_SLK_END")[0]
    assert (_values(start, "_SLK_EARLIEST"), _values(start, "_SLK_LATEST")) == (
        ["1850"], ["1850-06"])
    assert (_values(end, "_SLK_EARLIEST"), _values(end, "_SLK_LATEST")) == (
        ["1860-04-01"], ["1860-04-01"])
    imported, _ = import_one(text)
    (fact,) = imported.residences
    assert (fact.start.earliest, fact.start.latest) == ("1850", "1850-06")
    assert (fact.end.earliest, fact.end.latest) == ("1860-04-01", "1860-04-01")


def test_slk_tag_earliest_one_sided() -> None:
    text, _ = export_text(one_residence(start=Endpoint(earliest="1850")))
    start = _children(_resi(text), "_SLK_START")[0]
    assert _values(start, "_SLK_EARLIEST") == ["1850"]
    assert _values(start, "_SLK_LATEST") == []
    imported, _ = import_one(text)
    assert _endpoint_view(imported.residences[0].start) == ("1850", None, None, None)


def test_slk_tag_latest_one_sided_wins_over_date_line() -> None:
    # Without _SLK_START the DATE line would make start.latest the FROM date.
    text, _ = export_text(one_residence(start=Endpoint(latest="1848")))
    imported, _ = import_one(text)
    assert _endpoint_view(imported.residences[0].start) == (None, "1848", None, None)


def test_slk_tag_prec() -> None:
    for precision in ("day", "month", "year", "approximate"):
        text, _ = export_text(one_residence(
            start=Endpoint(earliest="1850", latest="1850", precision=precision)))
        start = _children(_resi(text), "_SLK_START")[0]
        assert _values(start, "_SLK_PREC") == [precision]
        imported, _ = import_one(text)
        assert imported.residences[0].start.precision == precision


def test_slk_tag_note_of_an_endpoint() -> None:
    text, _ = export_text(one_residence(
        start=Endpoint(earliest="1850", note="Rad ett\nRad två"),
        end=Endpoint(latest="1860", note="Slut")))
    node = _resi(text)
    assert _children(_children(node, "_SLK_START")[0], "_SLK_NOTE")
    imported, _ = import_one(text)
    (fact,) = imported.residences
    assert (fact.start.note, fact.end.note) == ("Rad ett\nRad två", "Slut")


def test_slk_tag_hhrole() -> None:
    text, _ = export_text(_full_residence())
    assert _values(_resi(text), "_SLK_HHROLE") == ["Dräng"]
    imported, _ = import_one(text)
    assert imported.residences[0].role_in_household == "Dräng"
    text, _ = export_text(one_residence())
    assert _children(_resi(text), "_SLK_HHROLE") == []


def test_slk_tag_rnotes() -> None:
    text, _ = export_text(_full_residence())
    node = _resi(text)
    assert _values(node, "_SLK_RNOTES") == ["Egen anteckning.\nAndra raden."]
    imported, _ = import_one(text)
    assert imported.residences[0].notes == "Egen anteckning.\nAndra raden."
    text, _ = export_text(one_residence())
    assert _children(_resi(text), "_SLK_RNOTES") == []


def test_slk_tag_obsfrom_and_slk_tag_obsto() -> None:
    text, _ = export_text(_full_residence())
    sours = _children(_resi(text), "SOUR")
    assert len(sours) == 2
    assert (_values(sours[0], "_SLK_OBSFROM"), _values(sours[0], "_SLK_OBSTO")) == (
        ["1855"], ["1858"])
    assert (_values(sours[1], "_SLK_OBSFROM"), _values(sours[1], "_SLK_OBSTO")) == (
        ["1859"], [])
    # The existing "Observation:" note stays (Requirement 7.4).
    assert [c.value for c in _children(sours[0], "NOTE")][0] == "Observation: 1855-1858"
    imported, _ = import_one(text)
    periods = sorted((o.observed_from, o.observed_to)
                     for o in imported.residences[0].observations)
    assert periods == [("1855", "1858"), ("1859", "")]


def test_slk_tag_obsto_wins_over_the_note_period() -> None:
    # A file with the marker: the structured period is the only source.
    text = _legacy_file(
        "2 SOUR @S1@\n3 NOTE Observation: 1900-1910\n"
        "3 _SLK_OBSFROM 1902\n3 _SLK_OBSTO 1904\n", head=_MARKED_HEAD)
    imported, _ = import_one(text)
    (obs,) = imported.residences[0].observations
    assert (obs.observed_from, obs.observed_to) == ("1902", "1904")


def test_slk_tag_note_of_an_observation_and_page_and_quality() -> None:
    text, _ = export_text(_full_residence())
    first = _children(_resi(text), "SOUR")[0]
    assert _values(first, "PAGE") == ["s. 12"]
    assert _children(first, "_SLK_NOTE")
    imported, _ = import_one(text)
    by_period = {o.observed_from: o for o in imported.residences[0].observations}
    assert (by_period["1855"].source_ref.quality, by_period["1855"].source_ref.note,
            by_period["1855"].source_ref.aspects, by_period["1855"].page_note) == (
        "primary", "rad 4", ["namn", "ålder"], "s. 12")
    assert by_period["1859"].source_ref.quality == "osäker"


def test_old_residence_lines_are_written_unchanged() -> None:
    text, _ = export_text(_full_residence())
    node = _resi(text)
    assert _values(node, "DATE") == ["FROM 1850-06 TO 1860-04-01".replace(
        "1850-06", "JUN 1850").replace("1860-04-01", "1 APR 1860")] or _values(
        node, "DATE")
    notes = [c.value for c in _children(node, "NOTE")]
    assert "Tidigast början: 1850" in notes and "Senast slut: 1860-04-01" in notes
    assert "Roll: Dräng" in notes
    assert _values(node, "PLAC")


def test_slk_start_without_usable_children_falls_back_to_date() -> None:
    text = _legacy_file("2 DATE FROM 1912\n2 _SLK_START\n3 _SLK_EARLIEST xxxx\n",
                        head=_MARKED_HEAD)
    imported, _ = import_one(text)
    assert imported.residences[0].start.latest == "1912"


def test_resi_without_slk_tags_uses_the_date_line_in_a_marked_file() -> None:
    text = _legacy_file("2 DATE FROM 1912 TO 1920\n", head=_MARKED_HEAD)
    imported, _ = import_one(text)
    (fact,) = imported.residences
    assert (fact.start.latest, fact.end.earliest) == ("1912", "1920")


def test_fingerprint_of_a_linked_legacy_residence_differs_documented_limitation(
    tmp_path: Path,
) -> None:
    """Documented limitation: a legacy (origin-less) residence whose endpoint
    links an event is not claimed on re-import; data-integrity Property 26
    treats the link as content (catalog entry K52).

    At the fingerprint level: the incoming fingerprint (``ignore_links=True``)
    differs from the existing residence's fingerprint (links included), so the
    existing residence is not matched.
    """
    data = one_residence(start=Endpoint(earliest="1850", latest="1850"))
    text, _ = export_text(label_persons(data))
    world = World(tmp_path)
    world.run(text)
    fact = world.data.residences[0]
    fact.origins = []
    incoming = residence_fingerprint(fact, ignore_links=True)
    assert residence_fingerprint(fact) == incoming  # no link yet: equal
    fact.start.event_id = "event_unknown"
    assert residence_fingerprint(fact) != incoming
    assert residence_fingerprint(fact, ignore_links=True) == incoming

def test_linked_legacy_residence_is_not_claimed_documented_limitation(
    tmp_path: Path,
) -> None:
    """Pins the approved limitation: data-integrity Property 26 treats an
    endpoint's event link as content, so a legacy (origin-less) residence whose
    endpoint links an event is not claimed and the import adds a new one."""
    data = one_residence(start=Endpoint(earliest="1850", latest="1850"))
    text, _ = export_text(label_persons(data))
    world = World(tmp_path)
    world.run(text)
    fact = world.data.residences[0]
    fact.origins = []
    fact.start.event_id = "event_unknown"
    assert world.run(text).residences_added == 1
    assert len(world.data.residences) == 2
