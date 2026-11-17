"""Export log and output hygiene: Requirement 10 and Property 15.

Covers the Swedish warnings (media, place types, Individual_Fallback, one
placeholder warning per conflict family plus the closing line), the omission
counts, the absence of DNA and research data in the output, the removed stale
log lines, and Property 15: every ``_`` tag of the output is registered in
``SLK_TAG_REGISTRY`` (checked dynamically, with its parent tag), two exports of
the same project are byte-identical and the output parses without warnings.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Iterator

from hypothesis import given
from hypothesis import strategies as st

from slaktbusken.gedcom.exporter import ExportResult, GEDCOMExporter
from slaktbusken.gedcom.parser import GedcomLine, parse_gedcom
from slaktbusken.gedcom.slk_tags import SLK_TAG_REGISTRY
from slaktbusken.model.event import Event, Participant
from slaktbusken.model.media import MediaItem
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData
from tests.test_gedcom_roundtrip.fixtures import load_mergetest
from tests.test_gedcom_roundtrip.strategies import projects, residence_projects
from tests.test_gedcom_roundtrip.test_families_roundtrip import (
    CLOSING_LINE,
    PLACEHOLDER_WARNING,
    couple,
    export_text,
)
import pytest

pytestmark = pytest.mark.mandatory_integrity

STALE_LINES = (
    "Observationernas delperioder exporteras som anteckningar.",
    "Flyttens ursprungsplats exporteras som anteckning",
)

# Level-0 records that the exporter may write.
ALLOWED_RECORDS = {"HEAD", "INDI", "FAM", "SOUR", "REPO", "TRLR"}

# ProjectData attribute -> label of ExportResult.omitted_elements.
OMISSION_LABELS = {
    "dna_companies": "DNA-företag",
    "dna_profiles": "DNA-profiler",
    "dna_matches": "DNA-matchningar",
    "dna_segments": "DNA-segment",
    "dna_clusters": "DNA-kluster",
    "dna_triangulations": "DNA-trianguleringar",
    "research_notes": "Forskningsanteckningar",
    "research_cases": "Forskningsärenden",
    "research_hypotheses": "Hypoteser",
    "research_actions": "Forskningsåtgärder",
    "media": "Medieobjekt",
    "merge_candidates": "Sammanslagningskandidater",
    "merge_history": "Sammanslagningshistorik",
    "connection_overrides": "Anslutningsöverstyrningar",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def export_bytes(data: ProjectData) -> tuple[bytes, ExportResult]:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "out.ged"
        result = GEDCOMExporter().export(data, path)
        return path.read_bytes(), result


def _person(index: int, sex: str = "U") -> Person:
    return Person(id=f"person_{index}", sex=sex,
                  names=[Name("birth", f"P{index}", "X")])


def _media(count: int) -> list[MediaItem]:
    return [MediaItem(id=f"media_{i}", type="image", file=f"bild{i}.jpg",
                      title=f"Bild {i}") for i in range(1, count + 1)]


def _walk(node: GedcomLine, parent: GedcomLine | None
          ) -> Iterator[tuple[GedcomLine, GedcomLine | None]]:
    yield node, parent
    for child in node.children:
        yield from _walk(child, node)


def _event_tags() -> frozenset[str]:
    """Tags that stand for ``<event>`` in the registry (read from the exporter)."""
    from slaktbusken.gedcom import exporter

    return frozenset(exporter._EVENT_TYPE_TO_TAG.values()) | frozenset(
        exporter._FAMILY_EVENT_TYPE_TO_TAG.values()) | {"EVEN"}


def _family_event_tags() -> frozenset[str]:
    from slaktbusken.gedcom import exporter

    return frozenset(exporter._FAMILY_EVENT_TYPE_TO_TAG.values()) | {"EVEN"}


def _parent_allowed(slk_tag: str, parent: GedcomLine) -> bool:
    """Whether *parent* is one of the parents the registry names for *slk_tag*."""
    allowed = SLK_TAG_REGISTRY[slk_tag].parents
    if parent.tag in allowed:
        return True
    if parent.level == 0 and f"<{parent.tag} record>" in allowed:
        return True
    if "<event>" in allowed and parent.tag in _event_tags():
        return True
    return "<family event>" in allowed and parent.tag in _family_event_tags()


def check_output(text: str) -> None:
    """The structural half of Property 15 on one exported text."""
    parsed = parse_gedcom(text)
    assert parsed.warnings == []

    slk_lines = 0
    for record in parsed.records:
        assert record.tag in ALLOWED_RECORDS
        for node, parent in _walk(record, None):
            if not node.tag.startswith("_"):
                continue
            slk_lines += 1
            assert node.tag in SLK_TAG_REGISTRY, node.tag
            assert parent is not None, node.tag
            assert _parent_allowed(node.tag, parent), (node.tag, parent.tag)

    head = next(r for r in parsed.records if r.tag == "HEAD")
    marker = [c for c in head.children if c.tag == "_SLK_VERS"]
    if slk_lines:
        assert [c.value for c in marker] == ["1"]


# ---------------------------------------------------------------------------
# Warning texts (Requirement 10 criteria 2, 3, 5; Requirement 4 criteria 14, 15)
# ---------------------------------------------------------------------------


def test_media_warning_and_omission_count() -> None:
    data = ProjectData(persons=[_person(1)], media=_media(3))
    _text, result = export_text(data)
    assert result.omitted_elements["Medieobjekt"] == 3
    assert result.warnings == [
        "Media exporteras inte: 3 medieobjekt"
        " (filer och länkar) ingår inte i GEDCOM-filen."
    ]


def test_place_types_warning_only_when_a_place_has_a_type() -> None:
    typed = ProjectData(persons=[_person(1)],
                        places=[Place(id="place_1", type="parish", name="Ed")])
    untyped = ProjectData(persons=[_person(1)],
                          places=[Place(id="place_1", type="", name="Ed")])
    _t, with_type = export_text(typed)
    _t, without_type = export_text(untyped)
    assert with_type.warnings == [
        "Platstyper exporteras inte (skjuts upp till en senare version)."
    ]
    assert without_type.warnings == []


def test_no_media_or_place_type_warning_for_a_plain_project() -> None:
    _text, result = export_text(ProjectData(persons=[_person(1)]))
    assert result.warnings == []
    assert result.omitted_elements == {}


def test_individual_fallback_warning_names_event_and_participants() -> None:
    data = ProjectData(
        persons=[_person(1, "M"), _person(2, "F")],
        events=[Event(id="event_1", type="marriage", participants=[
            Participant("person_1", "spouse"), Participant("person_2", "spouse")])],
    )
    text, result = export_text(data)
    assert len(result.warnings) == 1
    warning = result.warnings[0]
    assert warning.startswith("Händelsen ")
    assert "utan datum" in warning
    assert "P1 X" in warning and "P2 X" in warning
    assert "hör inte till någon enskild familj" in warning
    assert warning.endswith("Ingen familj skapades.")
    assert "0 @F" not in text  # no family record was created


def test_placeholder_warning_per_conflict_family_and_one_closing_line() -> None:
    persons = [_person(1, "F"), _person(2, "F"), _person(3, "X"), _person(4, "U"),
               _person(5, "M"), _person(6, "F")]
    from slaktbusken.model.family import Family, FamilyPartner

    def fam(index: int, a: str, b: str, role: str) -> Family:
        return Family(id=f"family_{index}", children=[],
                      partners=[FamilyPartner(a, role), FamilyPartner(b, role)])

    data = ProjectData(persons=persons, families=[
        fam(1, "person_1", "person_2", "wife"),     # conflict
        fam(2, "person_3", "person_4", "partner"),  # conflict (X)
        fam(3, "person_5", "person_6", "partner"),  # no conflict
    ])
    _text, result = export_text(data)
    family_warnings = [w for w in result.warnings if PLACEHOLDER_WARNING in w]
    assert len(family_warnings) == 2
    assert family_warnings[0].startswith("Familj F1 (P1 X, P2 X)")
    assert family_warnings[1].startswith("Familj F2 (P3 X, P4 X)")
    for warning in family_warnings:
        assert "HUSB/WIFE är en teknisk platshållare" in warning
        assert "_SLK_PARTNER" in warning
    closing = [w for w in result.warnings if w.startswith(CLOSING_LINE)]
    assert closing == [
        "Program som inte läser _SLK_PARTNER visar platshållarna HUSB"
        " och WIFE som make och maka."
    ]
    assert result.warnings.index(closing[0]) > result.warnings.index(
        family_warnings[-1])


def test_no_placeholder_lines_without_conflict() -> None:
    _text, result = export_text(couple(["M", "F"], ["husband", "wife"]))
    assert result.warnings == []


def test_removed_log_lines_are_absent_for_the_mergetest_project() -> None:
    _text, result = export_text(load_mergetest())
    for stale in STALE_LINES:
        assert not any(stale in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Omissions and data that is not exported (Requirement 10 criterion 1)
# ---------------------------------------------------------------------------


def test_omission_counts_match_the_project() -> None:
    data = load_mergetest()
    _text, result = export_text(data)
    expected = {label: len(getattr(data, attr))
                for attr, label in OMISSION_LABELS.items() if getattr(data, attr)}
    assert expected, "MergeTest.json must contain data without a GEDCOM form"
    assert result.omitted_elements == expected


def test_omitted_data_is_not_in_the_output() -> None:
    data = load_mergetest()
    text, _result = export_text(data)
    parsed = parse_gedcom(text)
    assert {r.tag for r in parsed.records} <= ALLOWED_RECORDS
    needles: list[str] = []
    for attr in ("dna_companies", "dna_profiles", "dna_matches", "dna_clusters",
                 "dna_triangulations", "research_cases", "research_notes",
                 "research_hypotheses", "research_actions", "merge_candidates",
                 "merge_history"):
        needles += [item.id for item in getattr(data, attr)]
    needles += [case.title for case in data.research_cases]
    needles += [p.kit_name for p in data.dna_profiles if p.kit_name]
    needles += [c.name for c in data.dna_companies]
    assert needles
    for needle in needles:
        assert needle not in text, needle
    for key in data.connection_overrides:
        assert key not in text, key


def test_media_items_are_not_written() -> None:
    data = ProjectData(persons=[_person(1)], media=_media(2))
    text, _result = export_text(data)
    assert "OBJE" not in text and "bild1.jpg" not in text


# ---------------------------------------------------------------------------
# Stale log lines (removed) on generated projects
# ---------------------------------------------------------------------------


@given(residence_projects())
def test_stale_log_lines_are_never_written(data: ProjectData) -> None:
    _text, result = export_text(data)
    for stale in STALE_LINES:
        assert not any(stale in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Property 15
# ---------------------------------------------------------------------------


# Feature: gedcom-roundtrip-0-3-0, Property 15: Export output is registered,
# deterministic and valid
# **Validates: Requirements 10.4, 11.1, 13.4, 13.5**
@given(projects())
def test_property_15_output_is_registered_deterministic_and_valid(
    data: ProjectData,
) -> None:
    first, first_result = export_bytes(data)
    second, second_result = export_bytes(data)
    assert first == second
    assert first_result.warnings == second_result.warnings
    assert first_result.omitted_elements == second_result.omitted_elements
    check_output(first.decode("utf-8"))


# **Validates: Requirements 10.4, 11.1, 13.4, 13.5**
@given(st.sampled_from(["mergetest", "synthetic"]))
def test_property_15_holds_for_the_fixture_projects(which: str) -> None:
    if which == "mergetest":
        data = load_mergetest()
    else:
        from tests.test_gedcom_roundtrip import synthetic as syn

        data = syn.build_synthetic_project()
    first, _ = export_bytes(data)
    assert first == export_bytes(data)[0]
    check_output(first.decode("utf-8"))


def test_one_exporter_instance_gives_identical_files_twice() -> None:
    data = load_mergetest()
    exporter = GEDCOMExporter()
    with tempfile.TemporaryDirectory() as folder:
        a, b = Path(folder) / "a.ged", Path(folder) / "b.ged"
        exporter.export(data, a)
        exporter.export(data, b)
        assert a.read_bytes() == b.read_bytes()


def test_marker_is_in_head_when_an_slk_tag_is_written() -> None:
    text, _ = export_text(couple(["F", "F"], ["wife", "wife"]))
    assert "_SLK_PARTNER" in text
    head = parse_gedcom(text).records[0]
    assert [c.value for c in head.children if c.tag == "_SLK_VERS"] == ["1"]
