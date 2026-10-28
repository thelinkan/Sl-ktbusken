"""Unit tests for PersonDetailPanel foster/adoptive parent labelling (task 11.3).

Covers the pure, Qt-free helpers that drive the "Föräldrar och syskon" section
of the person detail panel:

* ``_parentage_type_for`` reads the parentage type from a family's
  ``parent_child_links`` (biological when no explicit link exists);
* ``_format_parent_entry`` annotates foster and adoptive parents distinctly
  from biological parents using the shared Swedish parentage labels
  (Requirement 12.3), mirroring the Ansedel report convention.

These are tested directly to avoid a Qt event loop.
"""

from __future__ import annotations

from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.ui.person_detail_panel import (
    _format_parent_entry,
    _parentage_type_for,
)


def _family_with_link(child_id: str, parent_id: str, parentage_type: str) -> Family:
    return Family(
        id="F1",
        partners=[FamilyPartner(person_id=parent_id, role="mother")],
        children=[child_id],
        parent_child_links=[
            ParentChildLink(
                child_id=child_id,
                parent_id=parent_id,
                parentage_type=parentage_type,
            )
        ],
    )


# ---------------------------------------------------------------------------
# _parentage_type_for
# ---------------------------------------------------------------------------


def test_parentage_type_for_reads_foster_link() -> None:
    family = _family_with_link("C1", "P1", "foster")
    assert _parentage_type_for(family, "C1", "P1") == "foster"


def test_parentage_type_for_reads_adoptive_link() -> None:
    family = _family_with_link("C1", "P1", "adoptive")
    assert _parentage_type_for(family, "C1", "P1") == "adoptive"


def test_parentage_type_for_defaults_to_biological_when_no_link() -> None:
    family = Family(
        id="F1",
        partners=[FamilyPartner(person_id="P1", role="mother")],
        children=["C1"],
        parent_child_links=[],
    )
    assert _parentage_type_for(family, "C1", "P1") == "biological"


def test_parentage_type_for_ignores_other_pairs() -> None:
    family = Family(
        id="F1",
        partners=[
            FamilyPartner(person_id="P1", role="father"),
            FamilyPartner(person_id="P2", role="mother"),
        ],
        children=["C1"],
        parent_child_links=[
            ParentChildLink(child_id="C1", parent_id="P1", parentage_type="foster"),
            ParentChildLink(child_id="C1", parent_id="P2", parentage_type="biological"),
        ],
    )
    assert _parentage_type_for(family, "C1", "P1") == "foster"
    assert _parentage_type_for(family, "C1", "P2") == "biological"


# ---------------------------------------------------------------------------
# _format_parent_entry
# ---------------------------------------------------------------------------


def test_format_parent_entry_foster_shows_foster_label() -> None:
    entry = _format_parent_entry("Mor", "Anna Persdotter", "foster")
    assert entry == "Mor: Anna Persdotter (Foster)"


def test_format_parent_entry_adoptive_shows_adoptive_label() -> None:
    entry = _format_parent_entry("Far", "Erik Svensson", "adoptive")
    assert entry == "Far: Erik Svensson (Adoptiv)"


def test_format_parent_entry_biological_has_no_label() -> None:
    entry = _format_parent_entry("Far", "Erik Svensson", "biological")
    assert entry == "Far: Erik Svensson"


def test_format_parent_entry_foster_and_adoptive_are_distinct() -> None:
    foster = _format_parent_entry("Förälder", "Kim", "foster")
    adoptive = _format_parent_entry("Förälder", "Kim", "adoptive")
    assert foster != adoptive
    assert "Foster" in foster
    assert "Adoptiv" in adoptive
