"""Fixture round trip, Property 16 and the catalog completeness test.

``MergeTest.json`` is exported and imported into a real empty project. The two
Stable_Views are compared with ``comparison.compare`` (Requirement 14): every
difference must be in the difference catalog, and no difference with status
``fixed`` may remain. The explicit counts below state the most important
results in plain numbers.
"""

from __future__ import annotations

import tempfile
from collections import Counter
from pathlib import Path

import pytest
from hypothesis import given

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.gedcom.parser import parse_gedcom
from slaktbusken.gedcom.slk_tags import SLK_TAG_REGISTRY
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.model.source import Repository
from tests.test_gedcom_roundtrip.comparison import (
    Difference,
    UncatalogedDifference,
    blocking,
    compare,
    reportable,
)
from tests.test_gedcom_roundtrip.difference_catalog import (
    APP_ONLY,
    CATALOG,
    DEFERRED,
    DIFFERENCE_CLASSES,
    FIXED,
    STATUSES,
)
from tests.test_gedcom_roundtrip.fixtures import load_mergetest
from tests.test_gedcom_roundtrip.stable_view import stable_view
from tests.test_gedcom_roundtrip.strategies import projects
from tests.test_gedcom_roundtrip.test_events_roundtrip import World
from tests.test_gedcom_roundtrip.test_families_roundtrip import (
    export_text,
    import_text,
    label_persons,
)

pytestmark = pytest.mark.mandatory_integrity

SALVAGED_FIELDS = (
    ("persons", "notes"),
    ("persons", "title"),
    ("persons", "names"),
    ("persons", "occupation"),
    ("persons", "name_event_links"),
    ("families", "partners"),
    ("families", "parentage"),
    ("events", "citations"),
    ("events", "participants"),
    ("residences", "start"),
    ("residences", "end"),
    ("residences", "start_event"),
    ("residences", "end_event"),
    ("residences", "observations"),
    ("residences", "role"),
    ("residences", "notes"),
    ("repositories", "phone"),
    ("repositories", "notes"),
)


def _type_counts(data: ProjectData) -> Counter:
    return Counter(e.type for e in data.events)


def _roundtrip_mergetest() -> tuple[ProjectData, ProjectData, str]:
    original = load_mergetest()
    text, _export = export_text(original)
    imported, _result = import_text(text)
    return original, imported, text


# ---------------------------------------------------------------------------
# The fixture round trip (Requirement 14.1, 14.2, 14.3)
# ---------------------------------------------------------------------------


def test_mergetest_counts_survive_the_round_trip() -> None:
    original, imported, _ = _roundtrip_mergetest()
    assert len(imported.persons) == len(original.persons) == 63
    assert len(imported.families) == len(original.families) == 30
    assert len(imported.events) == len(original.events) == 88
    assert _type_counts(imported) == _type_counts(original)


def test_all_six_marriages_survive_including_the_one_outside_event_ids() -> None:
    original, imported, text = _roundtrip_mergetest()
    assert _type_counts(original)["marriage"] == 6
    assert _type_counts(imported)["marriage"] == 6
    listed = {eid for f in original.families for eid in f.event_ids}
    outside = [e for e in original.events if e.type == "marriage" and e.id not in listed]
    assert len(outside) == 1 and outside[0].date.value == "1977-11-22"

    names = {p.id: p.names[0].given for p in imported.persons}
    siv_arne = [
        e for e in imported.events
        if e.type == "marriage" and e.date and e.date.value == "1977-11-22"
    ]
    assert len(siv_arne) == 1
    assert {names[p.person_id] for p in siv_arne[0].participants} == {"Siv", "Arne"}
    assert text.count("22 NOV 1977") == 1


def test_mergetest_has_no_blocking_difference_and_every_difference_is_catalogued() -> None:
    original, imported, _ = _roundtrip_mergetest()
    differences = compare(original, imported)  # raises when one has no catalog entry
    assert blocking(differences) == [], [d.describe() for d in blocking(differences)]
    assert all(d.code in CATALOG for d in differences)


def test_mergetest_content_fields_have_no_difference() -> None:
    """Notes, titles, name types, partner roles and order, citations, residences
    and repositories come back unchanged (Requirements 2, 3, 4, 6, 7, 9)."""
    original, imported, _ = _roundtrip_mergetest()
    differences = compare(original, imported)
    found = {(d.section, d.field) for d in differences}
    assert not found & set(SALVAGED_FIELDS), found & set(SALVAGED_FIELDS)


def test_mergetest_residences_and_repositories_counts() -> None:
    original, imported, _ = _roundtrip_mergetest()
    assert len(imported.residences) == len(original.residences)
    assert len(imported.repositories) == len(original.repositories)
    before, after = stable_view(original), stable_view(imported)
    assert before.items("residences") and len(before.items("residences")) == len(
        after.items("residences"))
    assert [i.key for i in before.items("repositories")] == [
        i.key for i in after.items("repositories")]


def test_mergetest_event_links_round_trip() -> None:
    original, imported, _ = _roundtrip_mergetest()
    before, after = stable_view(original), stable_view(imported)
    for section, field in (("persons", "name_event_links"),
                           ("residences", "start_event"),
                           ("residences", "end_event")):
        def values(view):
            return sorted((repr(i.identity), repr(i.fields.get(field)))
                          for i in view.items(section))
        assert values(before) == values(after), (section, field)


def test_unreferenced_repository_is_exported_and_imported() -> None:
    data = load_mergetest()
    used = {r.repository_id for s in data.sources for r in s.repository_refs}
    data.repositories.append(Repository(id="repo_unused", name="Oanvänt arkiv", type="archive"))
    assert "repo_unused" not in used
    text, _ = export_text(data)
    assert "Oanvänt arkiv" in text
    imported, _ = import_text(text)
    assert "Oanvänt arkiv" in {r.name for r in imported.repositories}
    assert not blocking(compare(data, imported))


def test_a_second_import_of_the_fixture_creates_nothing(tmp_path: Path) -> None:
    original = load_mergetest()
    text, _ = export_text(original)
    world = World(tmp_path)
    first = world.run(text)
    assert first.persons_added == len(original.persons)
    assert first.families_added == len(world.data.families) == len(original.families)
    view = stable_view(world.data)
    counts = {
        name: len(getattr(world.data, name))
        for name in ("persons", "families", "events", "sources", "places",
                     "repositories", "residences")
    }

    second = world.run(text)
    assert second.persons_added == 0
    assert second.families_added == 0
    assert second.events_added == 0
    assert second.sources_added == 0
    assert second.places_added == 0
    assert second.residences_added == 0
    assert counts == {name: len(getattr(world.data, name)) for name in counts}
    assert not compare(view, stable_view(world.data))


# ---------------------------------------------------------------------------
# Property 16
# ---------------------------------------------------------------------------


# Feature: gedcom-roundtrip-0-3-0, Property 16: A round trip leaves no unclassified difference
# **Validates: Requirements 14.1, 14.2, 14.4, 14.6**
@given(projects())
def test_round_trip_leaves_no_unclassified_difference(data: ProjectData) -> None:
    data = label_persons(data)
    text, _export = export_text(data)
    imported, _result = import_text(text)
    differences = compare(data, imported)  # UncatalogedDifference when unclassified
    assert blocking(differences) == [], [d.describe() for d in blocking(differences)]


def test_an_uncatalogued_difference_makes_the_comparison_fail() -> None:
    data = load_mergetest()
    changed = load_mergetest()
    changed.persons.append(Person(id="person_new", sex="U", names=[Name("birth", "Ny", "Person")]))
    with pytest.raises(UncatalogedDifference):
        compare(data, changed)


# ---------------------------------------------------------------------------
# Catalog completeness (Requirement 14.5, 14.8)
# ---------------------------------------------------------------------------


def test_every_catalog_entry_has_class_status_description_and_requirement() -> None:
    assert CATALOG
    for code, entry in CATALOG.items():
        assert entry.code == code
        assert entry.classes and all(c in DIFFERENCE_CLASSES for c in entry.classes), code
        assert entry.root_class in DIFFERENCE_CLASSES
        assert entry.status in STATUSES, code
        assert entry.description.strip(), code
        assert entry.requirement.strip(), code
        assert entry.difference_class == "/".join(entry.classes)
        if entry.status == APP_ONLY:
            assert entry.root_class == "D", code


def test_documented_limitations_are_in_the_catalog() -> None:
    texts = {code: e.description.lower() for code, e in CATALOG.items()}

    def has(*words: str) -> bool:
        return any(all(w in t for w in words) for t in texts.values())

    assert has("legacy residence", "endpoint")
    assert has("foster-only", "derived")
    assert has("partial", "parent-child links")
    assert has("place type")
    assert has("media")
    assert has("husb/wife placeholder")
    assert has("3 text")
    assert has("swedish", "note")
    assert CATALOG["K57"].status == DEFERRED and CATALOG["K57"].root_class == "B"
    assert has("hash-based xrefs", "duplicates")
    for code, e in CATALOG.items():
        if any(w in e.description.lower() for w in ("legacy residence", "foster-only",
                                                    "partial or missing")):
            assert e.status == DEFERRED


def test_mergetest_report_entries_are_deferred_or_app_only() -> None:
    original, imported, _ = _roundtrip_mergetest()
    shown: list[Difference] = reportable(compare(original, imported))
    assert shown
    assert all(d.status in (DEFERRED, APP_ONLY) for d in shown)
    assert all(d.difference_class for d in shown)


# ---------------------------------------------------------------------------
# _SLK_VERS
# ---------------------------------------------------------------------------


def test_slk_tag_vers_is_written_once_in_head_and_registered() -> None:
    row = SLK_TAG_REGISTRY["_SLK_VERS"]
    assert row.parents == ("HEAD",)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "out.ged"
        GEDCOMExporter().export(load_mergetest(), path)
        text = path.read_text(encoding="utf-8")
    assert text.count("_SLK_VERS") == 1
    head = next(r for r in parse_gedcom(text).records if r.tag == "HEAD")
    assert [c.value for c in head.children if c.tag == "_SLK_VERS"] == ["1"]
