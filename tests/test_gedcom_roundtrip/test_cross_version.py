"""Cross-version identity and backward compatibility: Property 13 and
Requirements 12.4 to 12.8, 13.1, 13.2 and 14.7.

Old-format files are made in two ways:

* ``old_form(text)`` turns a new export into the file the exporter wrote
  before this spec: it drops the SLK_Marker and every ``_SLK_`` structure, and
  under every citation ``SOUR`` line the ``QUAY``, ``PAGE``, ``DATA`` and
  ``OBJE`` children and each ``NOTE`` that does not start with
  ``Observation:``. Requirement 12.8 keeps every older line byte for byte, so
  the rest (``3 TEXT``, the Swedish residence prose ``Tidigast början:``,
  ``Senast slut:``, ``Roll:`` and ``3 NOTE Observation:``) stays. The result
  has no marker, so it is read with Hash_Profile ``legacy`` and its residence
  prose with the exact legacy parse (decision 9).
* ``exporttest.ged`` is a frozen output of the old exporter.

The old exporter numbered records whose id has no numeric suffix with
``abs(hash(app_id)) % 99999`` (``@X41703@``), which changes with Python's hash
seed; the new exporter numbers them deterministically (Requirement 13.5). Two
families of ``MergeTest.json`` have such ids. A FAM record whose xref differs
between two files is a different record to the importer, so its family events
are new to the other file. This is the known limitation cataloged as K57
(Requirement 12.10, deferred, class B): importing such an old file creates
duplicates (2 families, 2 marriages for MergeTest) and no matcher is added. The ``exporttest.ged`` examples therefore allow
creations only for records that the other file does not contain.
"""

from __future__ import annotations

import re
import tempfile
from collections import Counter
from pathlib import Path

import pytest
from hypothesis import given

from slaktbusken.gedcom.importer import GEDCOMImporter, ImportResult
from slaktbusken.gedcom.parser import parse_gedcom
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.persistence.serialization import deserialize, serialize
from tests.test_gedcom_roundtrip import fixtures
from tests.test_gedcom_roundtrip import synthetic as syn
from tests.test_gedcom_roundtrip.comparison import compare
from tests.test_gedcom_roundtrip.difference_catalog import CATALOG
from tests.test_gedcom_roundtrip.strategies import projects
from tests.test_gedcom_roundtrip.test_events_roundtrip import World
from tests.test_gedcom_roundtrip.test_families_roundtrip import (
    export_text,
    import_text,
    label_persons,
)

pytestmark = pytest.mark.mandatory_integrity

GEDCOM_FIXTURES = sorted(
    (Path(__file__).resolve().parents[1] / "fixtures" / "gedcom").glob("*.ged"))

_LINE_RE = re.compile(r"^(\d+) (?:(@[^@]+@) )?(\S+)(?: (.*))?$")
_CITATION_DROP = frozenset({"QUAY", "PAGE", "DATA", "OBJE"})

#: Collections whose ids show whether an import created something.
_KINDS = ("persons", "families", "events", "residences", "sources", "places",
          "repositories")


# ---------------------------------------------------------------------------
# Old-format generator
# ---------------------------------------------------------------------------


def old_form(text: str) -> str:
    """The file that the exporter before this spec wrote for the same data."""
    out: list[str] = []
    tags: list[str] = []
    skip_below: int | None = None
    for line in text.splitlines():
        match = _LINE_RE.match(line)
        assert match, line
        level, tag, value = int(match.group(1)), match.group(3), match.group(4) or ""
        if skip_below is not None:
            if level > skip_below:
                continue
            skip_below = None
        tags = tags[:level] + [tag]
        under_citation = level >= 2 and tags[level - 1] == "SOUR"
        # The old exporter never wrote CAUS (K56).
        drop = tag.startswith("_SLK_") or tag == "CAUS" or (under_citation and (
            tag in _CITATION_DROP
            or (tag == "NOTE" and not value.strip().startswith("Observation:"))))
        if drop:
            skip_below = level
            continue
        out.append(line)
    return "\n".join(out) + "\n"


def test_old_form_drops_exactly_the_new_nodes() -> None:
    new, _ = export_text(label_persons(syn.build_synthetic_project()))
    old = old_form(new)
    assert "1 _SLK_VERS 1" in new
    assert "_SLK_" not in old
    assert re.search(r"^2 CAUS ", new, re.M)
    assert not re.search(r"^\d+ CAUS ", old, re.M)
    assert re.search(r"^\d+ QUAY ", new, re.M)

    def citation_children(node, inside_record: bool) -> list[str]:
        found = []
        for child in node.children:
            if inside_record and node.tag == "SOUR":
                found.append(child.tag)
            found.extend(citation_children(child, True))
        return found

    for record in parse_gedcom(old).records:
        tags = citation_children(record, False)
        assert not set(tags) & _CITATION_DROP, tags
    kept = set(old.splitlines())
    for line in new.splitlines():
        if re.match(r"^\d+ (TEXT|NOTE (Tidigast början|Senast slut|Roll|Observation):)",
                    line):
            assert line in kept, line


def test_hash_profile_follows_the_marker_only(tmp_path: Path) -> None:
    new, _ = export_text(label_persons(syn.build_synthetic_project()))
    for text, profile in ((new, "slk1"), (old_form(new), "legacy"),
                          (fixtures.exporttest_ged_path().read_text(encoding="utf-8"),
                           "legacy")):
        path = tmp_path / f"{profile}.ged"
        path.write_text(text, encoding="utf-8")
        tdir = tmp_path / f"t_{profile}"
        tdir.mkdir(exist_ok=True)
        importer = GEDCOMImporter(ProjectData(project=ProjectMetadata(title="T")), tdir)
        importer.import_file(path)
        assert importer._hash_profile == profile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def ids(data: ProjectData) -> dict[str, set[str]]:
    return {kind: {item.id for item in getattr(data, kind)} for kind in _KINDS}


def origin_hashes(data: ProjectData) -> Counter:
    """(owner xref, tag key, record hash) of every event and residence origin."""
    found: Counter = Counter()
    for event in data.events:
        for origin in [event.origin, *event.extra_origins]:
            if origin is not None:
                found[(origin.owner_xref, origin.tag_key, origin.record_hash)] += 1
    for fact in data.residences:
        for origin in fact.origins:
            found[(origin.owner_xref, origin.tag_key, origin.record_hash)] += 1
    return found


def created(before: dict[str, set[str]], data: ProjectData) -> dict[str, set[str]]:
    after = ids(data)
    return {kind: after[kind] - before[kind] for kind in _KINDS if after[kind] - before[kind]}


def _created_text(new_ids: dict[str, set[str]], data: ProjectData) -> str:
    events = {e.id: e for e in data.events}
    lines = [f"{kind}: {sorted(v)}" for kind, v in new_ids.items()]
    for eid in sorted(new_ids.get("events", ())):
        e = events[eid]
        lines.append(f"  {e.type} {e.date and e.date.value} {e.origin}")
    return "\n".join(lines)


def assert_creates_nothing(world: World, text: str) -> ImportResult:
    before = ids(world.data)
    result = world.run(text)
    new_ids = created(before, world.data)
    assert not new_ids, _created_text(new_ids, world.data)
    assert result.events_added == 0 and result.residences_added == 0
    assert result.persons_added == 0
    return result


def check_cross_version(data: ProjectData, root: Path) -> None:
    """Property 13 for one project and its new and old export."""
    new, _ = export_text(data)
    old = old_form(new)

    # Old import first, then the new export: the old file contains every
    # event and residence, so nothing is created (Requirement 12.4).
    world = World(root / "a")
    world.run(old)
    hashes_old = origin_hashes(world.data)
    assert_creates_nothing(world, new)

    # New import first, then the old export creates nothing (12.5); the new
    # export again creates and changes nothing (12.6), origins included.
    world = World(root / "b")
    world.run(new)
    snapshot = serialize(world.data)
    # slk1 hashes of the new records equal the legacy hashes of the old ones.
    assert set(origin_hashes(world.data)) == set(hashes_old)
    assert_creates_nothing(world, new)
    assert serialize(world.data) == snapshot
    assert_creates_nothing(world, old)


# ---------------------------------------------------------------------------
# Property 13
# ---------------------------------------------------------------------------


# Feature: gedcom-roundtrip-0-3-0, Property 13: Re-imports across versions create no duplicates
# **Validates: Requirements 7.10, 12.4, 12.5, 12.6, 12.7**
@given(projects())
def test_reimports_across_versions_create_no_duplicates(data: ProjectData) -> None:
    with tempfile.TemporaryDirectory() as folder:
        check_cross_version(label_persons(data), Path(folder))


@pytest.mark.parametrize("name", ["synthetic", "mergetest"])
def test_cross_version_examples(name: str, tmp_path: Path) -> None:
    data = (syn.build_synthetic_project() if name == "synthetic"
            else fixtures.load_mergetest())
    check_cross_version(label_persons(data), tmp_path)


# ---------------------------------------------------------------------------
# exporttest.ged (frozen old export) against the new export of MergeTest.json
# ---------------------------------------------------------------------------


def _record_keys(text: str) -> set[str]:
    return set(re.findall(r"^0 (@[^@]+@) ", text, re.M))


def _assert_only_records_missing_from(world: World, text: str, first: ProjectData,
                                      first_text: str) -> None:
    """Import ``text``; each created event comes from a record that the first
    file does not contain (other xref, or no record with that hash)."""
    before = ids(world.data)
    stored = set(origin_hashes(first))
    first_xrefs = _record_keys(first_text)
    result = world.run(text)
    new_ids = created(before, world.data)
    assert result.residences_added == 0
    assert result.persons_added == 0
    # Repositories: the old exporter wrote no REPO record (K31).
    assert set(new_ids) <= {"events", "families", "repositories"}, \
        _created_text(new_ids, world.data)
    if "repositories" in new_ids:
        assert "REPO" not in {line.split(" ")[-1] for line in first_text.splitlines()
                              if line.startswith("0 @")}
    # A family is created only for a FAM record whose xref the first file lacks.
    fam_xrefs = {x for x in re.findall(r"^0 (@[^@]+@) FAM", text, re.M)}
    assert len(new_ids.get("families", ())) <= len(fam_xrefs - first_xrefs)
    events = {e.id: e for e in world.data.events}
    for eid in new_ids.get("events", ()):
        origin = events[eid].origin
        assert origin is not None
        assert (origin.owner_xref not in first_xrefs
                or (origin.owner_xref, origin.tag_key, origin.record_hash) not in stored), \
            _created_text(new_ids, world.data)


def test_exporttest_then_new_export(tmp_path: Path) -> None:
    old = fixtures.exporttest_ged_path().read_text(encoding="utf-8")
    new, _ = export_text(fixtures.load_mergetest())
    world = World(tmp_path)
    world.run(old)
    _assert_only_records_missing_from(world, new, world.data, old)


def test_new_export_then_exporttest(tmp_path: Path) -> None:
    old = fixtures.exporttest_ged_path().read_text(encoding="utf-8")
    new, _ = export_text(fixtures.load_mergetest())
    world = World(tmp_path)
    world.run(new)
    _assert_only_records_missing_from(world, old, world.data, new)


def test_exporttest_reexport_into_same_project_creates_no_residence(tmp_path: Path) -> None:
    old = fixtures.exporttest_ged_path().read_text(encoding="utf-8")
    world = World(tmp_path)
    world.run(old)
    new, _ = export_text(world.data)
    _assert_only_records_missing_from(world, new, world.data, old)


# ---------------------------------------------------------------------------
# Backward compatibility (Requirements 13.1, 13.2, 14.7)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path", [*GEDCOM_FIXTURES, fixtures.exporttest_ged_path()], ids=lambda p: p.name)
def test_fixture_imports_without_abort(path: Path, tmp_path: Path) -> None:
    raw = path.read_bytes()
    assert b"_SLK_VERS" not in raw
    world = World(tmp_path)
    target = world.folder / path.name
    target.write_bytes(raw)  # the file as it is, in its own encoding
    result = world.service.run(world.data, target, world.folder, world.ps)
    assert isinstance(result, ImportResult)
    assert world.data.persons
    assert result.persons_added == len(world.data.persons)


#: Requirements whose behaviour may change the import of an old file (13.1).
_IMPROVEMENT_REQUIREMENTS = {str(n) for n in range(2, 10)}


def test_exporttest_import_equals_exporttest_json_apart_from_catalog() -> None:
    text = fixtures.exporttest_ged_path().read_text(encoding="utf-8")
    imported, _ = import_text(text)
    baseline = deserialize(fixtures.exporttest_json_path().read_text(encoding="utf-8"))
    differences = compare(baseline, imported)  # raises on an uncatalogued one
    # Only field changes, no person, family, event or residence appears or
    # disappears (13.1), and each change is behaviour of Requirements 2 to 9.
    assert all(d.field is not None for d in differences), [
        d.describe() for d in differences if d.field is None]
    assert {CATALOG[d.code].requirement for d in differences} <= \
        _IMPROVEMENT_REQUIREMENTS, [d.describe() for d in differences]
    assert len(imported.persons) == len(baseline.persons)
    assert len(imported.families) == len(baseline.families)
    assert len(imported.events) == len(baseline.events)
    assert len(imported.residences) == len(baseline.residences)
