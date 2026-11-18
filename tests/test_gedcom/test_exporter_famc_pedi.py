"""Unit tests for FAMC/FAMS and PEDI export in the GEDCOM exporter.

Tests verify that _write_person emits:
- ``1 FAMC @Fxx@`` for each family where the person is a child, with
  ``2 PEDI foster`` / ``2 PEDI adopted`` for foster/adoptive links and no
  ``PEDI`` for biological links.
- ``1 FAMS @Fxx@`` for each family where the person is a partner.

Validates: Requirements 11.1, 11.2
"""

from __future__ import annotations

from pathlib import Path

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _project(persons: list[Person], families: list[Family]) -> ProjectData:
    """Build a minimal ProjectData with the given persons and families."""
    return ProjectData(
        format="släktbuske-file",
        version="0.2",
        project=ProjectMetadata(title="Test"),
        persons=persons,
        families=families,
        events=[],
        places=[],
        sources=[],
    )


def _export_lines(data: ProjectData, tmp_path: Path) -> list[str]:
    """Export and return all GEDCOM lines."""
    exporter = GEDCOMExporter()
    exporter.export(data, tmp_path / "test.ged")
    return (tmp_path / "test.ged").read_text(encoding="utf-8").splitlines()


def _child(child_id: str) -> Person:
    return Person(
        id=child_id,
        names=[Name(type="birth", given="Barn", surname="Testsson")],
        sex="M",
    )


def _family_with_child(
    family_id: str, child_id: str, parentage_type: str
) -> Family:
    """A family containing one child via a link of the given parentage type."""
    return Family(
        id=family_id,
        partners=[
            FamilyPartner(person_id="person_10", role="husband"),
            FamilyPartner(person_id="person_11", role="wife"),
        ],
        children=[child_id],
        parent_child_links=[
            ParentChildLink(
                child_id=child_id,
                parent_id="person_10",
                parentage_type=parentage_type,
            ),
            ParentChildLink(
                child_id=child_id,
                parent_id="person_11",
                parentage_type=parentage_type,
            ),
        ],
    )


def _indi_block(lines: list[str], gedcom_id: str) -> list[str]:
    """Return the lines of the INDI record for gedcom_id (e.g. '@I1@')."""
    result: list[str] = []
    collecting = False
    for line in lines:
        if line.startswith("0 ") and line.endswith(" INDI"):
            collecting = line == f"0 {gedcom_id} INDI"
            if collecting:
                result.append(line)
            continue
        if line.startswith("0 "):
            collecting = False
            continue
        if collecting:
            result.append(line)
    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFamcPediExport:
    """FAMC/FAMS + PEDI emission in _write_person."""

    def test_biological_famc_has_no_pedi(self, tmp_path: Path) -> None:
        """A child in a biological family gets FAMC with no following PEDI."""
        child = _child("person_1")
        family = _family_with_child("family_1", "person_1", "biological")
        lines = _export_lines(_project([child], [family]), tmp_path)

        block = _indi_block(lines, "@I1@")
        assert "1 FAMC @F1@" in block
        famc_idx = block.index("1 FAMC @F1@")
        # No PEDI line should follow the FAMC.
        assert not any(l.startswith("2 PEDI") for l in block[famc_idx + 1:])

    def test_foster_famc_has_pedi_foster(self, tmp_path: Path) -> None:
        """A foster child's FAMC is immediately followed by '2 PEDI foster'."""
        child = _child("person_1")
        family = _family_with_child("family_1", "person_1", "foster")
        lines = _export_lines(_project([child], [family]), tmp_path)

        block = _indi_block(lines, "@I1@")
        assert "1 FAMC @F1@" in block
        famc_idx = block.index("1 FAMC @F1@")
        assert block[famc_idx + 1] == "2 PEDI foster"

    def test_adoptive_famc_has_pedi_adopted(self, tmp_path: Path) -> None:
        """An adoptive child's FAMC is followed by '2 PEDI adopted' (not adoptive)."""
        child = _child("person_1")
        family = _family_with_child("family_1", "person_1", "adoptive")
        lines = _export_lines(_project([child], [family]), tmp_path)

        block = _indi_block(lines, "@I1@")
        assert "1 FAMC @F1@" in block
        famc_idx = block.index("1 FAMC @F1@")
        assert block[famc_idx + 1] == "2 PEDI adopted"
        assert "2 PEDI adoptive" not in block

    def test_partner_gets_fams(self, tmp_path: Path) -> None:
        """A partner in a family gets '1 FAMS @Fxx@' for that family."""
        husband = Person(
            id="person_10",
            names=[Name(type="birth", given="Far", surname="Testsson")],
            sex="M",
        )
        child = _child("person_1")
        family = _family_with_child("family_1", "person_1", "biological")
        lines = _export_lines(_project([husband, child], [family]), tmp_path)

        block = _indi_block(lines, "@I10@")
        assert "1 FAMS @F1@" in block
        # The partner is not a child, so no FAMC for this family.
        assert "1 FAMC @F1@" not in block

    def test_mixed_links_prefer_foster(self, tmp_path: Path) -> None:
        """When a family mixes foster and adoptive links for one child, foster wins."""
        child = _child("person_1")
        family = Family(
            id="family_1",
            partners=[
                FamilyPartner(person_id="person_10", role="husband"),
                FamilyPartner(person_id="person_11", role="wife"),
            ],
            children=["person_1"],
            parent_child_links=[
                ParentChildLink(
                    child_id="person_1",
                    parent_id="person_10",
                    parentage_type="foster",
                ),
                ParentChildLink(
                    child_id="person_1",
                    parent_id="person_11",
                    parentage_type="adoptive",
                ),
            ],
        )
        lines = _export_lines(_project([child], [family]), tmp_path)

        block = _indi_block(lines, "@I1@")
        famc_idx = block.index("1 FAMC @F1@")
        assert block[famc_idx + 1] == "2 PEDI foster"
        assert "2 PEDI adopted" not in block
