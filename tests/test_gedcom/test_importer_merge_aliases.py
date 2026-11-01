"""Importer behaviour after a person merge (alias resolution, retired ids).

Validates: Requirements 30.4, 30.5, 30.6, 30.7, 30.8
"""

from __future__ import annotations

from pathlib import Path

import pytest

from slaktbusken.gedcom.importer import GEDCOMImporter
from slaktbusken.gedcom.translation import TranslationManager
from slaktbusken.model.merge_candidate import MergeHistoryEntry
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.persistence.translation_io import IdentityAlias

_GEDCOM = """\
0 HEAD
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Johan /Andersson/
1 SEX M
1 BIRT
2 DATE 15 MAR 1850
0 @I2@ INDI
1 NAME Johan /Andersson/
1 SEX M
1 OCCU Bonde
1 BIRT
2 DATE 15 MAR 1850
0 @I3@ INDI
1 NAME Anna /Persson/
1 SEX F
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 MARR
2 DATE 1 JAN 1875
0 @F2@ FAM
1 HUSB @I2@
1 WIFE @I3@
1 MARR
2 DATE 1 JAN 1876
0 TRLR
"""


@pytest.fixture
def setup(tmp_path: Path):
    """Import once, then merge the person of @I2@ into the person of @I1@."""
    tdir = tmp_path / "translation"
    tdir.mkdir()
    gedcom = tmp_path / "t.ged"
    gedcom.write_text(_GEDCOM, encoding="utf-8")
    data = ProjectData(project=ProjectMetadata(title="T"))
    GEDCOMImporter(data, tdir).import_file(gedcom)

    mgr = TranslationManager(tdir)
    td = mgr.load_translations()
    by_xref = {m.gedcom_id: m for m in td.persons}
    survivor, retired = by_xref["@I1@"].app_id, by_xref["@I2@"].app_id
    td.person_aliases.append(
        IdentityAlias("@I2@", by_xref["@I2@"].fingerprint, survivor, "merge_1")
    )
    td.persons = [m for m in td.persons if m.app_id != retired]
    mgr.save_translations(td)
    data.persons = [p for p in data.persons if p.id != retired]
    data.merge_history.append(
        MergeHistoryEntry(
            id="merge_1", surviving_person_id=survivor, merged_person_id=retired,
            merged_person_name="Johan Andersson", merged_person_lifespan="",
            merge_date="2024-01-01",
        )
    )
    return data, tdir, gedcom, survivor, retired


def _counts(data: ProjectData) -> tuple[int, int, int]:
    # Person events only: sync_parentage_links currently strips marriage ids
    # from Family.event_ids, so family events are duplicated by any re-import
    # (pre-existing, unrelated to merging).
    person_events = sum(1 for e in data.events if e.type == "birth")
    return len(data.persons), person_events, len(data.families)


def test_reimport_does_not_recreate_retired_person(setup) -> None:
    data, tdir, gedcom, survivor, retired = setup
    before = _counts(data)

    result = GEDCOMImporter(data, tdir).import_file(gedcom)

    assert retired not in {p.id for p in data.persons}
    assert _counts(data) == before
    assert result.persons_added == 0
    assert [m.xref for m in result.merged_identity_matches] == ["@I2@"]
    match = result.merged_identity_matches[0]
    assert match.person_id == survivor
    assert match.matched_by == "xref"
    assert match.differing_fields == ["occupation"]
    assert result.ambiguous_records == []


def test_survivor_unchanged_by_matched_record(setup) -> None:
    data, tdir, gedcom, survivor, _ = setup
    person = next(p for p in data.persons if p.id == survivor)
    person.occupation = "Smed"

    GEDCOMImporter(data, tdir).import_file(gedcom)

    # @I1@ itself is an ordinary update; @I2@ (the alias) must not touch it.
    assert person.occupation != "Bonde"


def test_match_by_fingerprint_when_xref_renumbered(setup) -> None:
    data, tdir, gedcom, survivor, retired = setup
    gedcom.write_text(
        _GEDCOM.replace("@I2@", "@I9@"), encoding="utf-8"
    )
    before = _counts(data)

    result = GEDCOMImporter(data, tdir).import_file(gedcom)

    assert retired not in {p.id for p in data.persons}
    assert _counts(data)[0] == before[0]
    match = [m for m in result.merged_identity_matches if m.xref == "@I9@"]
    assert match and match[0].matched_by == "fingerprint"


def test_record_resolving_to_two_active_persons_is_ambiguous(setup) -> None:
    data, tdir, gedcom, survivor, _ = setup
    mgr = TranslationManager(tdir)
    td = mgr.load_translations()
    # An active mapping (other person) also claims the alias xref.
    other = next(m for m in td.persons if m.gedcom_id == "@I3@")
    other.gedcom_id = "@I2@"
    mgr.save_translations(td)
    persons_before = len(data.persons)

    result = GEDCOMImporter(data, tdir).import_file(gedcom)

    assert [r.xref for r in result.ambiguous_records] == ["@I2@"]
    assert set(result.ambiguous_records[0].candidate_person_ids) == {survivor, other.app_id}
    assert result.merged_identity_matches == []
    assert len(data.persons) == persons_before


def test_family_with_both_partners_same_person_drops_second(setup) -> None:
    data, tdir, gedcom, survivor, _ = setup

    result = GEDCOMImporter(data, tdir).import_file(gedcom)

    family = next(f for f in data.families if f.partners and survivor in
                  {p.person_id for p in f.partners} and len(f.partners) == 1)
    assert [p.person_id for p in family.partners] == [survivor]
    assert any(
        "Båda partnerna i familjen @F1@ pekar på samma person." in w
        for w in result.warnings
    )


def test_mapping_to_retired_id_creates_nothing(setup) -> None:
    data, tdir, gedcom, survivor, retired = setup
    mgr = TranslationManager(tdir)
    td = mgr.load_translations()
    # Simulate a mapping that was not moved (older backup).
    stale = next(m for m in td.persons if m.gedcom_id == "@I3@")
    stale.app_id = retired
    mgr.save_translations(td)

    result = GEDCOMImporter(data, tdir).import_file(gedcom)

    assert retired not in {p.id for p in data.persons}
    assert any("slagits samman" in w for w in result.warnings)
