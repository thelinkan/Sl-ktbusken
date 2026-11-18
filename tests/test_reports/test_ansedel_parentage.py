"""Unit tests for parentage-type annotation in the Ansedel report's parents section.

Tests that the "Föräldrar" section annotates non-biological parents with their
Swedish parentage label (foster, adoptive) distinctly, while biological parents
are listed without annotation.

Requirements: 10.1, 10.2, 10.3
"""

from __future__ import annotations

from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.reports.ansedel import generate_ansedel
from slaktbusken.reports.content import HeadingBlock, ListBlock
from slaktbusken.ui.swedish_locale import get_parentage_type_label


def _person(pid: str, given: str, surname: str) -> Person:
    """Create a minimal person."""
    return Person(id=pid, sex="U", names=[Name(type="birth", given=given, surname=surname)])


def _find_section(report, heading_text: str):
    """Find the block immediately after a heading with the given text."""
    blocks = report.blocks
    for i, block in enumerate(blocks):
        if isinstance(block, HeadingBlock) and block.text == heading_text:
            if i + 1 < len(blocks):
                return blocks[i + 1]
    return None


def _entry_for(items: list[str], name: str) -> str | None:
    """Return the single list entry that starts with the given name, else None."""
    for item in items:
        if item.startswith(name):
            return item
    return None


class TestAnsedelParentageAnnotation:
    """The Ansedel parents section annotates non-biological parents (Req 10)."""

    def test_mixed_parent_types_annotated_distinctly(self):
        """A child with biological, foster, and adoptive parents annotates each distinctly.

        - the biological parent appears with NO annotation,
        - the foster parent appears annotated with the foster label,
        - the adoptive parent appears annotated with the adoptive label,
        all three labels distinct from each other.
        """
        child = _person("c1", "Erik", "Svensson")
        bio = _person("b1", "Bio", "Far")
        foster = _person("f1", "Foster", "Mor")
        adoptive = _person("a1", "Adoptiv", "Far")

        # Biological family (older-style: still has an explicit link)
        bio_family = Family(
            id="fam_bio",
            partners=[FamilyPartner(person_id="b1", role="father")],
            children=["c1"],
            parent_child_links=[
                ParentChildLink(child_id="c1", parent_id="b1", parentage_type="biological"),
            ],
        )
        # Derived foster family
        foster_family = Family(
            id="fam_foster",
            partners=[FamilyPartner(person_id="f1", role="mother")],
            children=["c1"],
            parent_child_links=[
                ParentChildLink(child_id="c1", parent_id="f1", parentage_type="foster"),
            ],
        )
        # Derived adoptive family
        adoptive_family = Family(
            id="fam_adopt",
            partners=[FamilyPartner(person_id="a1", role="father")],
            children=["c1"],
            parent_child_links=[
                ParentChildLink(child_id="c1", parent_id="a1", parentage_type="adoptive"),
            ],
        )

        data = ProjectData(
            persons=[child, bio, foster, adoptive],
            families=[bio_family, foster_family, adoptive_family],
        )

        report = generate_ansedel(data, "c1", project_folder=None)
        section = _find_section(report, "Föräldrar")
        assert isinstance(section, ListBlock)

        foster_label = get_parentage_type_label("foster")
        adoptive_label = get_parentage_type_label("adoptive")
        # Labels must be distinct from each other
        assert foster_label != adoptive_label

        bio_entry = _entry_for(section.items, "Bio Far")
        foster_entry = _entry_for(section.items, "Foster Mor")
        adoptive_entry = _entry_for(section.items, "Adoptiv Far")

        assert bio_entry is not None
        assert foster_entry is not None
        assert adoptive_entry is not None

        # Biological: no parentage annotation (plain name)
        assert bio_entry == "Bio Far"
        assert "(" not in bio_entry

        # Foster: annotated with the foster label, distinct
        assert foster_entry == f"Foster Mor ({foster_label})"
        assert adoptive_label not in foster_entry

        # Adoptive: annotated with the adoptive label, distinct
        assert adoptive_entry == f"Adoptiv Far ({adoptive_label})"
        assert foster_label not in adoptive_entry

    def test_biological_parent_unannotated(self):
        """A biological parent is listed without any parentage-type annotation (Req 10.2)."""
        child = _person("c1", "Erik", "Svensson")
        bio = _person("b1", "Anna", "Nilsson")
        family = Family(
            id="fam_bio",
            partners=[FamilyPartner(person_id="b1", role="mother")],
            children=["c1"],
            parent_child_links=[
                ParentChildLink(child_id="c1", parent_id="b1", parentage_type="biological"),
            ],
        )
        data = ProjectData(persons=[child, bio], families=[family])

        report = generate_ansedel(data, "c1", project_folder=None)
        section = _find_section(report, "Föräldrar")
        assert isinstance(section, ListBlock)
        assert section.items == ["Anna Nilsson"]

    def test_missing_explicit_link_treated_as_biological(self):
        """A family with no explicit parent_child_link is treated as biological (unannotated)."""
        child = _person("c1", "Erik", "Svensson")
        bio = _person("b1", "Olle", "Persson")
        family = Family(
            id="fam_bio",
            partners=[FamilyPartner(person_id="b1", role="father")],
            children=["c1"],
            parent_child_links=[],
        )
        data = ProjectData(persons=[child, bio], families=[family])

        report = generate_ansedel(data, "c1", project_folder=None)
        section = _find_section(report, "Föräldrar")
        assert isinstance(section, ListBlock)
        assert section.items == ["Olle Persson"]
