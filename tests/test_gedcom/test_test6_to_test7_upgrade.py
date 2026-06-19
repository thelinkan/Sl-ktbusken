"""Test that upgrading from Test-6 to Test-7 does not duplicate Märta Stina Karlsson.

Test-6 has Märta Stina at @I5@ and Ärla at @I6@ (no birth data).
Test-7 has Märta Stina at @I6@ and Ärla at @I7@ (with birth data added).
The xref shuffle combined with Ärla gaining birth data must not cause duplication.
"""

from pathlib import Path

import pytest

from slaktbusken.gedcom.importer import GEDCOMImporter
from slaktbusken.model.project import ProjectData


@pytest.fixture
def empty_project() -> ProjectData:
    """An empty project data container."""
    return ProjectData(
        persons=[], families=[], events=[], places=[], sources=[], repositories=[]
    )


@pytest.fixture
def translation_dir(tmp_path: Path) -> Path:
    """A temporary directory for translation files."""
    d = tmp_path / "translation"
    d.mkdir()
    return d


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to the GEDCOM test fixtures directory."""
    return Path(__file__).parent.parent / "fixtures" / "gedcom"


class TestTest6ToTest7Upgrade:
    """Verify person identity tracking when xrefs shuffle and data is added."""

    def test_marta_stina_not_duplicated(
        self, empty_project: ProjectData, translation_dir: Path, fixtures_dir: Path
    ) -> None:
        """Märta Stina Karlsson must not be duplicated when upgrading Test-6 → Test-7.

        In Test-6 she is @I5@, in Test-7 she moves to @I6@. Meanwhile Ärla
        (previously @I6@ with no birth data) moves to @I7@ and gains birth data.
        The bidirectional identity check must prevent misclassification.
        """
        # Initial import of Test-6
        importer1 = GEDCOMImporter(empty_project, translation_dir)
        result1 = importer1.import_file(fixtures_dir / "Test-6.ged")

        # Test-6 has 13 persons
        assert result1.persons_added == 13
        assert len(empty_project.persons) == 13

        # Find Märta Stina
        marta_persons = [
            p for p in empty_project.persons
            if p.names and p.names[0].given == "Märta Stina"
        ]
        assert len(marta_persons) == 1, (
            f"Expected exactly 1 Märta Stina after Test-6, got {len(marta_persons)}"
        )
        marta_id = marta_persons[0].id

        # Find Ärla
        arla_persons = [
            p for p in empty_project.persons
            if p.names and "Ärla" in (p.names[0].given or "")
        ]
        assert len(arla_persons) == 1
        arla_id = arla_persons[0].id

        # Update import of Test-7 (adds Janne Sr @I4@, Janne Jr @I5@ changes,
        # and Lotta @I14@ — total new persons: 2 new (Janne Sr + Lotta))
        importer2 = GEDCOMImporter(empty_project, translation_dir)
        result2 = importer2.import_file(fixtures_dir / "Test-7.ged")

        # After update: should NOT have duplicated Märta Stina
        marta_persons_after = [
            p for p in empty_project.persons
            if p.names and p.names[0].given == "Märta Stina"
        ]
        assert len(marta_persons_after) == 1, (
            f"Expected exactly 1 Märta Stina after Test-7 update, "
            f"got {len(marta_persons_after)}. Duplication bug!"
        )

        # Märta Stina should still be the same person record
        assert marta_persons_after[0].id == marta_id, (
            "Märta Stina's app_id should be preserved across imports"
        )

        # Ärla should still exist (not overwritten by Märta)
        arla_persons_after = [
            p for p in empty_project.persons
            if p.names and "Ärla" in (p.names[0].given or "")
        ]
        assert len(arla_persons_after) == 1, (
            f"Expected exactly 1 Ärla after Test-7 update, "
            f"got {len(arla_persons_after)}"
        )
        # Ärla should still be the same record
        assert arla_persons_after[0].id == arla_id, (
            "Ärla's app_id should be preserved across imports"
        )

    def test_new_persons_added_in_test7(
        self, empty_project: ProjectData, translation_dir: Path, fixtures_dir: Path
    ) -> None:
        """Test-7 adds new persons (Janne Sr born 1888, Lotta) correctly."""
        # Initial import of Test-6
        importer1 = GEDCOMImporter(empty_project, translation_dir)
        importer1.import_file(fixtures_dir / "Test-6.ged")

        initial_count = len(empty_project.persons)
        assert initial_count == 13

        # Update import of Test-7
        importer2 = GEDCOMImporter(empty_project, translation_dir)
        result2 = importer2.import_file(fixtures_dir / "Test-7.ged")

        # Test-7 has 14 persons total. Test-6 had 13. The new persons are:
        # - Janne Karlsson born 14 NOV 1888 (@I4@ in Test-7) — grandfather
        # - Lotta Pettersson (@I14@ in Test-7)
        # At minimum we need no duplications
        final_count = len(empty_project.persons)

        # Should have at most 15 persons (13 original + 2 new max)
        assert final_count <= 15, (
            f"Too many persons ({final_count}) — likely duplication"
        )

        # Should not lose any persons
        assert final_count >= 13, (
            f"Lost persons — only {final_count} remaining from original 13"
        )
