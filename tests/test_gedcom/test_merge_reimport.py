"""Identity aliases in persons.json after a merge (mandatory group f).

Property 42: Identity aliases.
**Validates: Requirements 30.1, 30.2, 30.3, 30.10**
"""
from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from slaktbusken.persistence import translation_io
from slaktbusken.persistence.translation_io import (
    FamilyMapping,
    IdentityAlias,
    PersonMapping,
    TranslationData,
)
from slaktbusken.services.merge_engine import MergeEngine
from slaktbusken.services.merge_planner import IdentityOps

pytestmark = pytest.mark.mandatory_integrity


class _Plan:
    """Minimal stand-in carrying only the identity operations the engine reads."""

    def __init__(self, ops: IdentityOps) -> None:
        self.identity_ops = ops


def _persist(td: TranslationData, directory: Path) -> Path:
    path = directory / "persons.json"
    path.write_bytes(
        translation_io.dumps_persons(td.persons, td.families, td.person_aliases)
    )
    return path


def _merge(td: TranslationData, retired: str, survivor: str, merge_id: str) -> TranslationData:
    """Apply the merge's translation step the way the planner prescribes it."""
    moved = [m for m in td.persons if m.app_id == retired]
    old_aliases = [a for a in td.person_aliases if a.person_id == retired]
    ops = IdentityOps(
        mappings_moved=tuple(m.gedcom_id for m in moved),
        aliases_rewritten=tuple(a.gedcom_id for a in old_aliases),
        new_aliases=tuple(
            IdentityAlias(m.gedcom_id, m.fingerprint, survivor, merge_id) for m in moved
        ),
        rewritten_aliases=tuple(
            IdentityAlias(a.gedcom_id, a.fingerprint, survivor, a.merge_id)
            for a in old_aliases
        ),
    )
    return MergeEngine._merged_translation(_Plan(ops), td, retired, survivor)  # type: ignore[arg-type]


def _base() -> TranslationData:
    return TranslationData(
        persons=[
            PersonMapping("@I1@", "person_1", "fp1"),
            PersonMapping("@I2@", "person_2", "fp2"),
            PersonMapping("@I3@", "person_3", "fp3"),
        ],
        families=[FamilyMapping("@F1@", "family_1")],
    )


# Feature: person-comparison-and-merge, Property 42:
def test_property_42_identity_aliases(tmp_path: Path) -> None:
    # Read-then-write equality, with aliases present.
    td = _merge(_base(), "person_2", "person_1", "merge_1")
    path = _persist(td, tmp_path)
    original = path.read_bytes()
    reread = translation_io.read_all(tmp_path)
    assert reread.person_aliases == td.person_aliases
    assert translation_io.dumps_persons(
        reread.persons, reread.families, reread.person_aliases
    ) == original

    # A file without aliases has no identity_aliases key and round-trips.
    plain = tmp_path / "plain"
    plain.mkdir()
    base = _base()
    plain_path = _persist(base, plain)
    assert b"identity_aliases" not in plain_path.read_bytes()
    reread_plain = translation_io.read_all(plain)
    assert reread_plain.person_aliases == []
    assert translation_io.dumps_persons(
        reread_plain.persons, reread_plain.families, reread_plain.person_aliases
    ) == plain_path.read_bytes()

    # The merge moves every mapping of the retired person into an alias with
    # unchanged gedcom_id and fingerprint, pointing at the survivor.
    assert [m.app_id for m in td.persons] == ["person_1", "person_3"]
    assert td.person_aliases == [IdentityAlias("@I2@", "fp2", "person_1", "merge_1")]

    # Merging an earlier survivor into a third person rewrites its aliases.
    td2 = _merge(td, "person_1", "person_3", "merge_2")
    assert {a.person_id for a in td2.person_aliases} == {"person_3"}
    by_xref = {a.gedcom_id: a for a in td2.person_aliases}
    assert by_xref["@I2@"] == IdentityAlias("@I2@", "fp2", "person_3", "merge_1")
    assert by_xref["@I1@"] == IdentityAlias("@I1@", "fp1", "person_3", "merge_2")
    assert [m.app_id for m in td2.persons] == ["person_3"]
    path2 = _persist(td2, tmp_path)
    assert translation_io.read_all(tmp_path).person_aliases == td2.person_aliases
    assert path2.read_bytes() == translation_io.dumps_persons(
        td2.persons, td2.families, td2.person_aliases
    )


@settings(max_examples=100, deadline=None)
@given(
    xrefs=st.lists(st.integers(1, 50), min_size=2, max_size=6, unique=True),
    fps=st.lists(st.one_of(st.none(), st.text("abcdef0123", min_size=1, max_size=8)),
                 min_size=6, max_size=6),
)
def test_aliases_preserve_gedcom_id_and_fingerprint(xrefs, fps) -> None:
    mappings = [
        PersonMapping(f"@I{x}@", f"person_{i}", fps[i]) for i, x in enumerate(xrefs)
    ]
    td = TranslationData(persons=mappings)
    merged = _merge(td, "person_1", "person_0", "merge_x")
    alias = next(a for a in merged.person_aliases)
    assert (alias.gedcom_id, alias.fingerprint) == (mappings[1].gedcom_id, mappings[1].fingerprint)
    assert alias.person_id == "person_0"
    assert all(m.app_id != "person_1" for m in merged.persons)
    data = translation_io.dumps_persons(merged.persons, merged.families, merged.person_aliases)
    assert data.endswith(b"\n")


# ---------------------------------------------------------------------------
# Re-import after a real merge (Property 43, requirements 30.4 to 30.8, 30.11)
#
# These tests import into a real ProjectService project, merge through the
# real planner and MergeEngine, and then import again.  Family events are
# deleted and recreated by an update import, so event IDS change while the
# COUNTS stay equal: only counts are asserted.
# ---------------------------------------------------------------------------
import tempfile  # noqa: E402

from slaktbusken.gedcom.importer import GEDCOMImporter  # noqa: E402
from slaktbusken.services.merge_planner import MergeDecisions, build_plan  # noqa: E402
from slaktbusken.services.project_service import ProjectService  # noqa: E402

_FIXTURE = """\
0 HEAD
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Johan /Andersson/
1 SEX M
1 OCCU Bonde
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
0 @I4@ INDI
1 NAME Karin /Olsson/
1 SEX F
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I3@
1 MARR
2 DATE 1 JAN 1875
0 @F2@ FAM
1 HUSB @I2@
1 WIFE @I4@
1 MARR
2 DATE 1 JAN 1880
0 TRLR
"""


class _World:
    """A real project, a GEDCOM path and the merged pair."""

    def __init__(self, root: Path, text: str = _FIXTURE) -> None:
        self.root = root
        self.svc = ProjectService()
        self.svc.create_project("T", root)
        self.tdir = self.svc.project_path.parent / "translation"
        self.tdir.mkdir(exist_ok=True)
        self.ged = root / "t.ged"
        self.ged.write_text(text, encoding="utf-8")
        self.importer().import_file(self.ged)
        self.svc._dirty = True
        self.svc.save_project()
        by_xref = {m.gedcom_id: m for m in translation_io.read_all(self.tdir).persons}
        self.survivor = by_xref["@I1@"].app_id
        self.retired = by_xref["@I2@"].app_id

    def importer(self) -> GEDCOMImporter:
        return GEDCOMImporter(self.svc.data, self.tdir)

    def merge(self) -> None:
        translation = translation_io.read_all(self.tdir)
        decisions = MergeDecisions(
            self.survivor, self.retired,
            survivor_id=self.survivor, survivor_confirmed=True,
        )
        plan = build_plan(self.svc.data, translation, decisions, self.svc.content_revision)
        assert plan.can_execute, [c.message for c in plan.blocking]
        outcome = MergeEngine(self.svc, None).execute(plan)
        assert outcome.success, outcome.message

    def counts(self) -> tuple[int, int, int]:
        d = self.svc.data
        return len(d.persons), len(d.events), len(d.families)

    def untouched(self) -> tuple:
        d = self.svc.data
        return (
            [(h.id, h.surviving_person_id, h.merged_person_id) for h in d.merge_history],
            len(d.merge_candidates),
            len(d.research_cases),
        )


def _survivor_fields(w: _World) -> tuple:
    p = next(p for p in w.svc.data.persons if p.id == w.survivor)
    return (p.occupation, p.title, [(n.given, n.surname) for n in p.names], p.notes)


def test_reimport_identical_file_does_not_recreate_retired_person(tmp_path: Path) -> None:
    w = _World(tmp_path)
    w.merge()
    survivor_before = _survivor_fields(w)

    result = w.importer().import_file(w.ged)

    ids = {p.id for p in w.svc.data.persons}
    assert w.retired not in ids
    assert w.survivor in ids
    assert result.persons_added == 0
    matches = [m for m in result.merged_identity_matches if m.xref == "@I2@"]
    assert len(matches) == 1 and matches[0].person_id == w.survivor
    assert matches[0].matched_by == "xref"
    # The merge carried the occupation over to the survivor, so nothing differs.
    assert matches[0].differing_fields == []
    assert result.ambiguous_records == []
    assert _survivor_fields(w) == survivor_before
    # Persisted mapping state never points at the retired id again.
    tr = translation_io.read_all(w.tdir)
    assert all(m.app_id != w.retired for m in tr.persons)


def test_reimport_edited_variant_matches_by_fingerprint(tmp_path: Path) -> None:
    w = _World(tmp_path)
    w.merge()
    survivor_before = _survivor_fields(w)
    before = w.counts()

    # Renumbered xrefs; the identity data (name, birth) is unchanged so the
    # fingerprint still matches, and the occupation is edited.
    variant = (
        _FIXTURE.replace("@I2@", "@I9@").replace("1 OCCU Bonde\n1 BIRT\n2 DATE 15 MAR 1850\n0 @I3@", "1 OCCU Torpare\n1 BIRT\n2 DATE 15 MAR 1850\n0 @I3@")
    )
    w.ged.write_text(variant, encoding="utf-8")
    result = w.importer().import_file(w.ged)

    assert w.retired not in {p.id for p in w.svc.data.persons}
    assert w.counts() == before
    assert result.persons_added == 0
    match = [m for m in result.merged_identity_matches if m.xref == "@I9@"]
    assert len(match) == 1
    assert match[0].matched_by == "fingerprint"
    assert match[0].person_id == w.survivor
    assert match[0].differing_fields == ["occupation"]
    assert _survivor_fields(w) == survivor_before


def test_reimport_counts_unchanged(tmp_path: Path) -> None:
    w = _World(tmp_path)
    w.merge()
    before, kept = w.counts(), w.untouched()

    w.importer().import_file(w.ged)
    assert w.counts() == before
    w.importer().import_file(w.ged)
    assert w.counts() == before
    assert w.untouched() == kept


def test_both_partners_same_person_gives_warning(tmp_path: Path) -> None:
    w = _World(tmp_path)
    w.merge()
    # Variant: @I2@ (merged into @I1@'s person) is husband and wife of F1.
    variant = _FIXTURE.replace("1 WIFE @I3@", "1 WIFE @I2@")
    w.ged.write_text(variant, encoding="utf-8")

    result = w.importer().import_file(w.ged)

    assert any(
        "Båda partnerna i familjen @F1@ pekar på samma person." in x
        for x in result.warnings
    )
    families = [f for f in w.svc.data.families if any(
        p.person_id == w.survivor for p in f.partners)]
    assert families
    for f in families:
        ids = [p.person_id for p in f.partners]
        assert len(ids) == len(set(ids))
    assert w.retired not in {p.id for p in w.svc.data.persons}


def test_negative_without_alias_recreates_person(tmp_path: Path) -> None:
    """Proves the tests detect the defect: without the alias, a duplicate returns."""
    # The two records differ in birth date, so only the alias can tie @I2@ to
    # the survivor; without it the record is a new person again.
    text = _FIXTURE.replace("2 DATE 15 MAR 1850\n0 @I3@", "2 DATE 16 MAR 1850\n0 @I3@")
    assert text != _FIXTURE
    w = _World(tmp_path, text)
    w.merge()
    tr = translation_io.read_all(w.tdir)
    assert tr.person_aliases, "the merge must have written an alias"
    translation_io.write_persons(tr.persons, tr.families, w.tdir / "persons.json")
    assert translation_io.read_all(w.tdir).person_aliases == []
    before = len(w.svc.data.persons)

    result = w.importer().import_file(w.ged)

    assert len(w.svc.data.persons) == before + 1
    assert result.persons_added == 1
    assert result.merged_identity_matches == []


# -- Property 43 -------------------------------------------------------------

_GIVEN_M = ["Johan", "Erik", "Lars", "Per", "Olof", "Nils"]
_GIVEN_F = ["Anna", "Karin", "Brita", "Stina", "Lisa", "Maria"]
_SURN = ["Andersson", "Persson", "Olsson", "Nilsson", "Berg", "Lund"]


@st.composite
def _gedcoms(draw):
    gm = draw(st.sampled_from(_GIVEN_M))
    sm = draw(st.sampled_from(_SURN))
    w1, w2 = draw(st.lists(st.sampled_from(_GIVEN_F), min_size=2, max_size=2, unique=True))
    sw = draw(st.sampled_from(_SURN))
    year = draw(st.integers(1700, 1900))
    occ = draw(st.sampled_from(["Bonde", "Smed", "Skräddare"]))
    return gm, sm, w1, w2, sw, year, occ


def _write(gm, sm, w1, w2, sw, year, occ, dup_x="@I2@", dup_occ_value=None) -> str:
    """Two records for one man (@I1@ and the duplicate), one family each."""
    base_occ = f"1 OCCU {occ}\n"
    dup_occ = f"1 OCCU {dup_occ_value or occ}\n"
    return (
        "0 HEAD\n1 CHAR UTF-8\n"
        f"0 @I1@ INDI\n1 NAME {gm} /{sm}/\n1 SEX M\n{base_occ}1 BIRT\n2 DATE 1 JAN {year}\n"
        f"0 {dup_x} INDI\n1 NAME {gm} /{sm}/\n1 SEX M\n{dup_occ}1 BIRT\n2 DATE 1 JAN {year}\n"
        f"0 @I3@ INDI\n1 NAME {w1} /{sw}/\n1 SEX F\n"
        f"0 @I4@ INDI\n1 NAME {w2} /{sw}/\n1 SEX F\n"
        "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I3@\n1 MARR\n2 DATE 1 JAN 1875\n"
        f"0 @F2@ FAM\n1 HUSB {dup_x}\n1 WIFE @I4@\n1 MARR\n2 DATE 1 JAN 1880\n"
        "0 TRLR\n"
    )


# Feature: person-comparison-and-merge, Property 43:
@settings(max_examples=100, deadline=None)
@given(spec=_gedcoms(), renumber=st.booleans())
def test_property_43_reimport_after_merge(spec, renumber) -> None:
    """**Validates: Requirements 30.4, 30.5, 30.6, 30.7, 30.8**"""
    with tempfile.TemporaryDirectory() as tmp:
        w = _World(Path(tmp), _write(*spec))
        w.merge()
        before, kept = w.counts(), w.untouched()
        survivor_before = _survivor_fields(w)

        # Step 3: identical file.  Step 4: edited variant with a renumbered xref.
        variants = [(_write(*spec), "xref")]
        if renumber:
            gm, sm, w1, w2, sw, year, occ = spec
            other = "Torpare" if occ != "Torpare" else "Bonde"
            variants.append(
                (
                    _write(gm, sm, w1, w2, sw, year, occ, dup_x="@I9@", dup_occ_value=other),
                    "fingerprint",
                )
            )
        for text, how in variants:
            w.ged.write_text(text, encoding="utf-8")
            result = w.importer().import_file(w.ged)

            assert w.retired not in {p.id for p in w.svc.data.persons}
            assert result.persons_added == 0
            assert w.counts() == before
            assert w.untouched() == kept
            assert _survivor_fields(w) == survivor_before
            assert result.ambiguous_records == []
            matches = result.merged_identity_matches
            assert len(matches) == 1
            assert matches[0].person_id == w.survivor
            assert matches[0].matched_by == how
            assert matches[0].differing_fields == (
                ["occupation"] if how == "fingerprint" else []
            )
