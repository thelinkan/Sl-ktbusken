"""Event links: Property 10 and the examples of Requirements 3.8, 3.9, 7.9, 16.

``Name.event_id`` and ``Endpoint.event_id`` travel as ``_SLK_EREF`` (level 2
under ``1 NAME``, level 3 under ``2 _SLK_START`` / ``2 _SLK_END``). All code
for them is in ``slaktbusken.gedcom.event_links``; this is the only test module
for it (design, Event_Link_Module).

Persons are labelled ``P<n>`` before the export (the importer creates new ids),
so a link is compared by the label view of the event it points at.
"""

from __future__ import annotations

import re
from collections import Counter

import pytest
from hypothesis import given
from hypothesis import strategies as st

from slaktbusken.gedcom import event_links
from slaktbusken.gedcom import exporter as exporter_module
from slaktbusken.gedcom.parser import GedcomLine
from slaktbusken.model.project import ProjectData
from tests.test_gedcom_roundtrip import synthetic as syn
from tests.test_gedcom_roundtrip.strategies import projects
from tests.test_gedcom_roundtrip.test_events_roundtrip import (
    event_counter,
    event_view,
)
from tests.test_gedcom_roundtrip.test_families_roundtrip import (
    _children,
    export_text,
    import_text,
    indi_records,
    label_of,
    label_persons,
)
from tests.test_gedcom_roundtrip.test_residences_roundtrip import (
    _endpoint_view,
    residence_view,
)

pytestmark = pytest.mark.mandatory_integrity

_HEAD = "0 HEAD\n1 GEDC\n2 VERS 5.5.1\n2 FORM LINEAGE-LINKED\n1 CHAR UTF-8\n"
_MARKED_HEAD = _HEAD + "1 _SLK_VERS 1\n"


# ---------------------------------------------------------------------------
# Views: a link is the label view of its event
# ---------------------------------------------------------------------------


def _link_view(data: ProjectData, event_id: str | None):
    if not event_id:
        return None
    event = next((e for e in data.events if e.id == event_id), None)
    return event_view(data, event) if event is not None else None


def name_link_counter(data: ProjectData) -> Counter:
    return Counter(
        (label_of(p), n.type, _link_view(data, n.event_id))
        for p in data.persons for n in p.names
    )


def endpoint_link_counter(data: ProjectData) -> Counter:
    return Counter(
        (residence_view(data, f), _link_view(data, f.start.event_id),
         _link_view(data, f.end.event_id))
        for f in data.residences
    )


def link_counts(data: ProjectData) -> tuple[int, int]:
    names = sum(1 for p in data.persons for n in p.names if n.event_id)
    ends = sum((f.start.event_id is not None) + (f.end.event_id is not None)
               for f in data.residences)
    return names, ends


@st.composite
def linked_projects(draw) -> ProjectData:
    """A whole project in which names and endpoints link to its events."""
    data = draw(projects())
    event_ids = [e.id for e in data.events]
    if event_ids:
        for person in data.persons:
            for name in person.names:
                if draw(st.booleans()):
                    name.event_id = draw(st.sampled_from(event_ids))
        for fact in data.residences:
            for endpoint in (fact.start, fact.end):
                endpoint.event_id = (draw(st.sampled_from(event_ids))
                                     if draw(st.booleans()) else None)
    return data


# ---------------------------------------------------------------------------
# Property 10
# ---------------------------------------------------------------------------


# Feature: gedcom-roundtrip-0-3-0, Property 10: Event links resolve to the matching event
# **Validates: Requirements 3.8, 3.9, 7.9**
@given(linked_projects())
def test_name_and_endpoint_event_links_survive_export_and_import(
    data: ProjectData,
) -> None:
    data = label_persons(data)
    text, _export = export_text(data)
    imported, result = import_text(text)
    assert name_link_counter(imported) == name_link_counter(data)
    assert endpoint_link_counter(imported) == endpoint_link_counter(data)
    assert link_counts(imported) == link_counts(data)
    assert not [w for w in result.warnings if "_SLK_EREF" in str(w)]


def test_synthetic_links_survive_export_and_import() -> None:
    data = label_persons(syn.build_synthetic_project())
    assert link_counts(data) == (1, 3)
    imported, result = import_text(export_text(data)[0])
    assert name_link_counter(imported) == name_link_counter(data)
    assert endpoint_link_counter(imported) == endpoint_link_counter(data)
    assert link_counts(imported) == (1, 3)
    assert not [w for w in result.warnings if "_SLK_EREF" in str(w)]


def test_link_to_a_missing_event_is_not_written() -> None:
    data = label_persons(syn.build_synthetic_project())
    for person in data.persons:
        for name in person.names:
            name.event_id = "event_missing"
    text, _ = export_text(data)
    assert not [l for l in text.splitlines() if l.startswith("2 _SLK_EREF")]
    assert text.count("3 _SLK_EREF") == 3


# ---------------------------------------------------------------------------
# Unresolved token (Requirement 3.9)
# ---------------------------------------------------------------------------


def test_unresolved_eref_warns_in_swedish_and_leaves_the_target_unchanged() -> None:
    text = (
        _MARKED_HEAD
        + "0 @I1@ INDI\n1 NAME Ada /X/\n2 TYPE birth\n2 _SLK_EREF x\n"
        + "1 RESI\n2 _SLK_START\n3 _SLK_EARLIEST 1850\n3 _SLK_EREF x\n"
        + "0 TRLR\n"
    )
    imported, result = import_text(text)
    (person,) = imported.persons
    assert person.names[0].event_id is None
    (fact,) = imported.residences
    assert fact.start.event_id is None and fact.end.event_id is None
    assert fact.start.earliest == "1850"
    warnings = [str(w) for w in result.warnings if "_SLK_EREF" in str(w)]
    assert len(warnings) == 2
    with_line = re.compile(
        r"_SLK_EREF 'x' pekar på en händelse som inte finns i filen "
        r"\(rad \d+\)\. Länken till händelsen ignorerades\.")
    without_line = ("_SLK_EREF 'x' pekar på en händelse som inte finns i filen. "
                    "Länken till händelsen ignorerades.")
    assert any(with_line.search(w) for w in warnings), warnings
    assert all(with_line.search(w) or without_line in w for w in warnings), warnings


# ---------------------------------------------------------------------------
# test_slk_tag_eref (Requirement 3.8, 16.1)
# ---------------------------------------------------------------------------


def _eref_lines(node) -> list[GedcomLine]:
    return _children(node, "_SLK_EREF")


def test_slk_tag_eref() -> None:
    data = label_persons(syn.build_synthetic_project())
    text, _ = export_text(data)
    name_links = endpoint_links = 0
    for indi in indi_records(text):
        for node in indi.children:
            if node.tag == "NAME":
                for eref in _eref_lines(node):
                    assert eref.level == 2
                    assert eref.value and not re.search(r"\s", eref.value)
                    name_links += 1
            if node.tag == "RESI":
                assert _eref_lines(node) == []
                for container in _children(node, "_SLK_START") + _children(
                        node, "_SLK_END"):
                    for eref in _eref_lines(container):
                        assert eref.level == 3
                        endpoint_links += 1
    assert (name_links, endpoint_links) == (1, 3)
    # No other place holds the tag.
    assert text.count("_SLK_EREF") == 4


def _node(*children: GedcomLine) -> GedcomLine:
    return GedcomLine(1, "NAME", "Ada /X/", None, 1, list(children))


def _eref(value, line: int = 2) -> GedcomLine:
    return GedcomLine(2, "_SLK_EREF", value, None, line)


@pytest.mark.parametrize("value", [None, "", "   ", "a b", " a b ", "\t"])
def test_read_eref_is_total_for_empty_and_whitespace_values(value) -> None:
    assert event_links.read_eref(_node(_eref(value))) is None


def test_read_eref_reads_one_token_and_the_first_repeat_counts() -> None:
    assert event_links.read_eref(_node(_eref("  event_7 "))) == "event_7"
    assert event_links.read_eref(_node(_eref("first"), _eref("second"))) == "first"
    # An unusable first value is the first: the repeat does not replace it.
    assert event_links.read_eref(_node(_eref(""), _eref("second"))) is None
    assert event_links.read_eref(_node()) is None
    assert event_links.read_eref(None) is None


@given(st.lists(st.one_of(st.none(), st.text(max_size=12)), max_size=4))
def test_read_eref_never_raises(values) -> None:
    result = event_links.read_eref(_node(*[_eref(v) for v in values]))
    assert result is None or (result and not re.search(r"\s", result))


def test_importer_ignores_unusable_eref_values_without_a_warning() -> None:
    text = (
        _MARKED_HEAD
        + "0 @I1@ INDI\n1 NAME Ada /X/\n2 _SLK_EREF\n2 _SLK_EREF a b\n"
        + "1 RESI\n2 _SLK_START\n3 _SLK_EARLIEST 1850\n3 _SLK_EREF\n"
        + "2 _SLK_END\n3 _SLK_LATEST 1860\n3 _SLK_EREF   \n"
        + "0 TRLR\n"
    )
    imported, result = import_text(text)
    assert link_counts(imported) == (0, 0)
    assert not [w for w in result.warnings if "_SLK_EREF" in str(w)]


# ---------------------------------------------------------------------------
# Module bypassed (Requirement 16)
# ---------------------------------------------------------------------------


def _bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exporter_module, "export_name_link", lambda *a, **k: [])
    monkeypatch.setattr(exporter_module, "export_endpoint_link", lambda *a, **k: [])
    monkeypatch.setattr(event_links, "collect_name_links", lambda *a, **k: None)
    monkeypatch.setattr(event_links, "collect_endpoint_links", lambda *a, **k: None)
    monkeypatch.setattr(event_links, "resolve_event_links", lambda *a, **k: 0)


def test_core_export_and_import_work_without_the_event_link_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = label_persons(syn.build_synthetic_project())
    assert link_counts(data) == (1, 3)
    _bypass(monkeypatch)
    text, _ = export_text(data)
    assert "_SLK_EREF" not in text
    imported, result = import_text(text)
    assert link_counts(imported) == (0, 0)
    assert event_counter(imported) == event_counter(data)
    assert Counter(
        (label_of(p), n.type, n.given, n.surname)
        for p in imported.persons for n in p.names
    ) == Counter(
        (label_of(p), n.type, n.given, n.surname)
        for p in data.persons for n in p.names
    )
    assert Counter(
        (residence_view(imported, f)) for f in imported.residences
    ) == Counter(residence_view(data, f) for f in data.residences)
    assert Counter(_endpoint_view(f.end) for f in imported.residences) == Counter(
        _endpoint_view(f.end) for f in data.residences)
    assert not [w for w in result.warnings if "_SLK_EREF" in str(w)]


def test_core_import_skips_a_file_with_erefs_when_the_module_is_bypassed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = label_persons(syn.build_synthetic_project())
    text, _ = export_text(data)
    assert "_SLK_EREF" in text
    _bypass(monkeypatch)
    imported, result = import_text(text)
    assert link_counts(imported) == (0, 0)
    assert event_counter(imported) == event_counter(data)
    assert not [w for w in result.warnings if "_SLK_EREF" in str(w)]
