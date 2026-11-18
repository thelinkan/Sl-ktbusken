"""Integration tests for ImportService orchestration.

Tests the full import pipeline using real GEDCOM content written to temp files.
Validates: Requirements 4.1, 4.2, 4.3, 5.1, 5.6, 5.7
"""

from __future__ import annotations

from pathlib import Path

import pytest

from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services.import_service import ImportError, ImportService
from slaktbusken.services.project_service import ProjectService
from slaktbusken.services.report_service import ReportService
from slaktbusken.services.validation_service import ValidationService

# ---------------------------------------------------------------------------
# Shared GEDCOM content fixtures
# ---------------------------------------------------------------------------

MINIMAL_GEDCOM = """\
0 HEAD
1 SOUR TestProg
1 GEDC
2 VERS 5.5.1
2 FORM LINEAGE-LINKED
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Erik /Svensson/
1 SEX M
0 TRLR
"""

FULL_GEDCOM = """\
0 HEAD
1 SOUR TestProg
1 GEDC
2 VERS 5.5.1
2 FORM LINEAGE-LINKED
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Erik /Svensson/
1 SEX M
1 BIRT
2 DATE 1 JAN 1850
2 PLAC Ljusdal, Gävleborgs län, Sverige
0 @I2@ INDI
1 NAME Anna /Johansson/
1 SEX F
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 MARR
2 DATE 15 MAY 1875
0 @S1@ SOUR
1 TITL Husförhörslängd AI:1
0 TRLR
"""


def _write_gedcom(tmp_path: Path, content: str, filename: str = "test.ged") -> Path:
    """Write GEDCOM content to a temp file and return its path."""
    gedcom_path = tmp_path / filename
    gedcom_path.write_text(content, encoding="utf-8")
    return gedcom_path


def _make_service() -> ImportService:
    """Create an ImportService with real dependencies."""
    validation_service = ValidationService()
    report_service = ReportService()
    return ImportService(validation_service, report_service)


def _ps(project_data: ProjectData) -> ProjectService:
    """Project service holding *project_data* (no files)."""
    ps = ProjectService()
    ps._project_data = project_data
    return ps


def _make_project_data() -> ProjectData:
    """Create an empty ProjectData for testing."""
    return ProjectData(project=ProjectMetadata(title="Test"))


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestImportServiceIntegration:
    """Integration tests for ImportService using real GEDCOM files."""

    def test_import_valid_gedcom_creates_entities(self, tmp_path: Path) -> None:
        """Importing a valid GEDCOM creates persons, families, events, sources, places."""
        service = _make_service()
        project_data = _make_project_data()
        gedcom_path = _write_gedcom(tmp_path, FULL_GEDCOM)
        project_path = tmp_path / "project"
        project_path.mkdir()

        result = service.run(project_data, gedcom_path, project_path, _ps(project_data))

        # Persons created
        assert result.persons_added == 2
        assert len(project_data.persons) == 2

        # Family created
        assert result.families_added == 1
        assert len(project_data.families) == 1

        # Events created (at least birth + marriage)
        assert result.events_added >= 2
        assert len(project_data.events) >= 2

        # Source created
        assert result.sources_added == 1
        assert len(project_data.sources) == 1
        assert project_data.sources[0].title == "Husförhörslängd AI:1"

        # Place created (from birth place string)
        assert result.places_added >= 1
        assert len(project_data.places) >= 1

    def test_import_nonexistent_file_raises_file_not_found(self, tmp_path: Path) -> None:
        """Importing a non-existent file raises FileNotFoundError."""
        service = _make_service()
        project_data = _make_project_data()
        missing_path = tmp_path / "does_not_exist.ged"
        project_path = tmp_path / "project"
        project_path.mkdir()

        with pytest.raises(FileNotFoundError):
            service.run(project_data, missing_path, project_path, _ps(project_data))

    def test_import_non_gedcom_file_raises_import_error(self, tmp_path: Path) -> None:
        """Importing a file that isn't valid GEDCOM raises ImportError with Swedish message."""
        service = _make_service()
        project_data = _make_project_data()
        bad_file = tmp_path / "not_gedcom.txt"
        bad_file.write_text("This is not a GEDCOM file at all.", encoding="utf-8")
        project_path = tmp_path / "project"
        project_path.mkdir()

        with pytest.raises(ImportError) as exc_info:
            service.run(project_data, bad_file, project_path, _ps(project_data))

        # Error message should be in Swedish
        assert "Kunde inte tolka GEDCOM-filen" in exc_info.value.message

    def test_reimport_same_file_updates_not_duplicates(self, tmp_path: Path) -> None:
        """Re-importing the same GEDCOM updates records rather than duplicating."""
        service = _make_service()
        project_data = _make_project_data()
        gedcom_path = _write_gedcom(tmp_path, FULL_GEDCOM)
        project_path = tmp_path / "project"
        project_path.mkdir()

        # First import
        ps = _ps(project_data)
        result1 = service.run(project_data, gedcom_path, project_path, ps)
        persons_after_first = len(project_data.persons)
        families_after_first = len(project_data.families)
        sources_after_first = len(project_data.sources)

        # Second import (re-import)
        result2 = service.run(project_data, gedcom_path, project_path, ps)

        # Should not have duplicated entities
        assert len(project_data.persons) == persons_after_first
        assert len(project_data.families) == families_after_first
        assert len(project_data.sources) == sources_after_first

        # Second import should show updates, not additions
        assert result2.persons_added == 0
        assert result2.persons_updated == 2

    def test_post_import_validation_warnings_appended(self, tmp_path: Path) -> None:
        """Post-import validation warnings are appended to result.warnings."""
        service = _make_service()
        project_data = _make_project_data()
        gedcom_path = _write_gedcom(tmp_path, FULL_GEDCOM)
        project_path = tmp_path / "project"
        project_path.mkdir()

        result = service.run(project_data, gedcom_path, project_path, _ps(project_data))

        # A clean import introduces no finding, so no validation warning.
        assert isinstance(result.warnings, list)
        assert not any("Valideringsvarning" in w for w in result.warnings)

    def test_import_minimal_gedcom(self, tmp_path: Path) -> None:
        """Importing a minimal GEDCOM (HEAD + one person + TRLR) works."""
        service = _make_service()
        project_data = _make_project_data()
        gedcom_path = _write_gedcom(tmp_path, MINIMAL_GEDCOM)
        project_path = tmp_path / "project"
        project_path.mkdir()

        result = service.run(project_data, gedcom_path, project_path, _ps(project_data))

        assert result.persons_added == 1
        assert len(project_data.persons) == 1

        person = project_data.persons[0]
        assert person.sex == "M"
        assert person.names[0].given == "Erik"
        assert person.names[0].surname == "Svensson"


# ---------------------------------------------------------------------------
# Atomic import (task 11.2)
# ---------------------------------------------------------------------------


def _tree(folder: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(folder)): p.read_bytes()
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


class TestAtomicImport:
    """The import stages translation data and adopts it with one change mark."""

    def test_import_writes_no_translation_file_and_marks_changed_once(
        self, tmp_path: Path
    ) -> None:
        service = _make_service()
        project_data = _make_project_data()
        ps = _ps(project_data)
        gedcom_path = _write_gedcom(tmp_path, FULL_GEDCOM)
        project_path = tmp_path / "project"
        (project_path / "translation").mkdir(parents=True)
        before = _tree(project_path)
        revisions: list[int] = []
        ps.add_merge_listener(lambda: revisions.append(ps.content_revision))

        service.run(project_data, gedcom_path, project_path, ps)

        assert _tree(project_path) == before
        assert ps.is_dirty
        assert revisions == [1]
        pending = ps.pending_translation
        assert pending is not None and pending.data.persons
        assert set(pending.base) == {
            "translation/persons.json",
            "translation/places.json",
            "translation/sources.json",
        }
        assert set(pending.base.values()) == {"absent"}
        assert not ps.import_in_progress

    def test_reimport_changing_nothing_adopts_nothing(self, tmp_path: Path) -> None:
        service = _make_service()
        project_data = _make_project_data()
        ps = _ps(project_data)
        gedcom_path = _write_gedcom(tmp_path, FULL_GEDCOM)
        project_path = tmp_path / "project"
        project_path.mkdir()
        service.run(project_data, gedcom_path, project_path, ps)
        first = ps.pending_translation
        revision = ps.content_revision

        service.run(project_data, gedcom_path, project_path, ps)

        assert ps.content_revision == revision
        assert ps.pending_translation is first

    def test_translation_file_changed_during_import_aborts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from slaktbusken.gedcom import importer as importer_module

        service = _make_service()
        project_data = _make_project_data()
        ps = _ps(project_data)
        gedcom_path = _write_gedcom(tmp_path, FULL_GEDCOM)
        project_path = tmp_path / "project"
        (project_path / "translation").mkdir(parents=True)
        original = importer_module.GEDCOMImporter.import_file

        def touching(self, path):  # type: ignore[no-untyped-def]
            result = original(self, path)
            (project_path / "translation" / "places.json").write_text("{}", encoding="utf-8")
            return result

        monkeypatch.setattr(importer_module.GEDCOMImporter, "import_file", touching)

        with pytest.raises(ImportError) as exc_info:
            service.run(project_data, gedcom_path, project_path, ps)

        assert exc_info.value.message == (
            "Översättningsfilerna ändrades under importen. Ingenting har ändrats."
        )
        assert project_data.persons == []
        assert not ps.is_dirty
        assert ps.pending_translation is None
        assert not ps.import_in_progress

    def test_import_refused_during_edit_session(self, tmp_path: Path) -> None:
        service = _make_service()
        project_data = _make_project_data()
        ps = _ps(project_data)
        ps.begin_edit_session("Personredigerare: Anna (person_1)")
        gedcom_path = _write_gedcom(tmp_path, MINIMAL_GEDCOM)

        with pytest.raises(ImportError) as exc_info:
            service.run(project_data, gedcom_path, tmp_path, ps)

        assert "Personredigerare: Anna (person_1)" in exc_info.value.message
        assert project_data.persons == []

    def test_import_failure_keeps_pending_translation(self, tmp_path: Path) -> None:
        service = _make_service()
        project_data = _make_project_data()
        ps = _ps(project_data)
        good = _write_gedcom(tmp_path, FULL_GEDCOM)
        service.run(project_data, good, tmp_path, ps)
        pending = ps.pending_translation
        bad = tmp_path / "bad.txt"
        bad.write_text("not gedcom", encoding="utf-8")

        with pytest.raises(ImportError):
            service.run(project_data, bad, tmp_path, ps)

        assert ps.pending_translation is pending


# ---------------------------------------------------------------------------
# Validation aborts the import when it introduces findings (task 16.1)
# ---------------------------------------------------------------------------


class _FakeValidation(ValidationService):
    """Validator whose findings are chosen by a function of the project data."""

    def __init__(self, findings) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self._findings = findings

    def validate_project(self, project_data):  # type: ignore[no-untyped-def]
        return self._findings(project_data)


def _run_with_validator(tmp_path: Path, validator: ValidationService):  # type: ignore[no-untyped-def]
    from slaktbusken.services.report_service import ReportService as _R

    service = ImportService(validator, _R())
    project_data = _make_project_data()
    ps = _ps(project_data)
    gedcom_path = _write_gedcom(tmp_path, FULL_GEDCOM)
    project_path = tmp_path / "project"
    (project_path / "translation").mkdir(parents=True)
    before = _tree(project_path)
    return service, project_data, ps, gedcom_path, project_path, before


class TestValidationAbort:
    def test_new_finding_aborts_and_changes_nothing(self, tmp_path: Path) -> None:
        from slaktbusken.gedcom.errors import ImportAborted
        from slaktbusken.services.validation_service import ValidationError

        def findings(data):  # type: ignore[no-untyped-def]
            return [
                ValidationError("Person", p.id, f"fel {i}")
                for i, p in enumerate(data.persons)
            ] + [ValidationError("Family", f.id, "fel") for f in data.families] * 3

        service, data, ps, ged, proj, before = _run_with_validator(
            tmp_path, _FakeValidation(findings)
        )

        with pytest.raises(ImportAborted) as exc_info:
            service.run(data, ged, proj, ps)

        exc = exc_info.value
        assert exc.phase == "validation"
        assert exc.message_sv.startswith(
            "Importen avbröts och ingenting har ändrats. "
            "Importen skulle ha gett ogiltiga data: 5 fel, t.ex. "
        )
        assert "Person" in exc.message_sv
        assert "Family" in exc.traceback_text
        assert data.persons == [] and data.families == [] and data.events == []
        assert not ps.is_dirty
        assert ps.pending_translation is None
        assert ps.content_revision == 0
        assert _tree(proj) == before
        assert not ps.import_in_progress

    def test_at_most_five_findings_are_named(self, tmp_path: Path) -> None:
        from slaktbusken.gedcom.errors import ImportAborted
        from slaktbusken.services.validation_service import ValidationError

        def findings(data):  # type: ignore[no-untyped-def]
            return [ValidationError("Event", e.id, "fel") for e in data.events]

        service, data, ps, ged, proj, _ = _run_with_validator(
            tmp_path, _FakeValidation(findings)
        )
        with pytest.raises(ImportAborted) as exc_info:
            service.run(data, ged, proj, ps)

        message = exc_info.value.message_sv
        assert message.count("Event ") <= 5
        assert len(exc_info.value.traceback_text.splitlines()) > 1

    def test_pre_existing_finding_only_warns(self, tmp_path: Path) -> None:
        from slaktbusken.services.validation_service import ValidationError

        def findings(data):  # type: ignore[no-untyped-def]
            return [ValidationError("Place", "place_old", "gammalt fel")]

        service, data, ps, ged, proj, _ = _run_with_validator(
            tmp_path, _FakeValidation(findings)
        )

        result = service.run(data, ged, proj, ps)

        assert "Valideringsvarning (Place place_old): gammalt fel" in result.warnings
        assert len(data.persons) == 2
        assert ps.is_dirty

    def test_validator_exception_aborts_with_cause(self, tmp_path: Path) -> None:
        from slaktbusken.gedcom.errors import ImportAborted

        def findings(data):  # type: ignore[no-untyped-def]
            raise RuntimeError("valideringen kraschade")

        service, data, ps, ged, proj, before = _run_with_validator(
            tmp_path, _FakeValidation(findings)
        )

        with pytest.raises(ImportAborted) as exc_info:
            service.run(data, ged, proj, ps)

        assert isinstance(exc_info.value.__cause__, RuntimeError)
        assert exc_info.value.phase == "validation"
        assert data.persons == []
        assert not ps.is_dirty
        assert _tree(proj) == before

    def test_residence_without_place_and_orphan_place_only_warn(
        self, tmp_path: Path
    ) -> None:
        """The two findings the importer produces on purpose do not abort."""
        text = MINIMAL_GEDCOM.replace(
            "1 SEX M\n",
            "1 SEX M\n1 RESI\n2 DATE 1870\n1 BIRT\n2 PLAC Bergsjö\n",
        )
        service = _make_service()
        data = _make_project_data()
        ps = _ps(data)

        result = service.run(data, _write_gedcom(tmp_path, text), tmp_path, ps)

        assert len(data.residences) == 1 and data.residences[0].place_id == ""
        assert any(
            "Boendet måste ange både person och plats." in w for w in result.warnings
        )
        assert any("överordnad plats" in w for w in result.warnings)
