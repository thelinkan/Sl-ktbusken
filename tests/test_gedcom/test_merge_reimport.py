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


@settings(max_examples=30, deadline=None)
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
