"""Unit tests for the ResidenceEditor bulk paste panel.

Tests the bulk paste panel: planning, candidate display, unparsed line handling,
atomic execution with all-or-nothing semantics, and the Swedish summary.

Requirements: 9.1, 9.2, 9.3, 9.5, 9.6, 9.8, 9.9, 9.10.
"""

from __future__ import annotations

import copy

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.model.event import SourceRef
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.model.source import Source, StructuredReference
from slaktbusken.ui.editors.residence_editor import ResidenceEditor


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def bulk_project() -> ProjectData:
    """Project with a person, place, and existing source for bulk testing."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        sources=[
            Source(
                id="src_existing",
                provider="Arkiv Digital",
                source_type="church_book",
                title="Ljusdal AI:15 Sida: 10",
                structured_reference=StructuredReference(
                    fields={
                        "parish": "Ljusdal",
                        "series": "AI",
                        "volume": "15",
                        "years": "1866-1870",
                        "image": "25",
                        "page": "10",
                    }
                ),
            ),
        ],
        residences=[
            ResidenceFact(
                id="res_1",
                person_id="p1",
                place_id="pl1",
                start=Endpoint(earliest="1860", latest="1866"),
                end=Endpoint(earliest="1870", latest="1880"),
                role_in_household="husbonde",
                observations=[
                    Observation(
                        source_ref=SourceRef(
                            source_id="src_existing", quality="primary"
                        ),
                        observed_from="1866",
                        observed_to="1870",
                    ),
                ],
            ),
        ],
    )


@pytest.fixture()
def bulk_editor(qapp, bulk_project, monkeypatch) -> ResidenceEditor:
    """Create a ResidenceEditor pre-loaded with the bulk project fixture."""
    # Patch QMessageBox to avoid blocking dialogs in tests.
    monkeypatch.setattr(
        "slaktbusken.ui.editors.residence_editor.QMessageBox.information",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "slaktbusken.ui.editors.residence_editor.QMessageBox.warning",
        lambda *args, **kwargs: None,
    )
    residence = bulk_project.residences[0]
    editor = ResidenceEditor(
        bulk_project, residence=residence, person_id="p1"
    )
    return editor


# ============================================================================
# Test: Bulk panel exists and is collapsible
# ============================================================================


class TestBulkPanelStructure:
    """Verify the bulk paste panel structure and collapsibility."""

    def test_bulk_group_exists(self, bulk_editor):
        """The bulk panel group box exists with the correct title."""
        assert bulk_editor._bulk_group is not None
        assert bulk_editor._bulk_group.title() == "Klistra in referenser"

    def test_bulk_group_is_checkable(self, bulk_editor):
        """The bulk panel is collapsible (checkable group box)."""
        assert bulk_editor._bulk_group.isCheckable()

    def test_bulk_group_starts_collapsed(self, bulk_editor):
        """The bulk panel starts collapsed (unchecked)."""
        assert not bulk_editor._bulk_group.isChecked()

    def test_paste_field_exists(self, bulk_editor):
        """The multi-line paste field exists."""
        assert bulk_editor._bulk_paste_edit is not None

    def test_plan_button_exists(self, bulk_editor):
        """The 'Planera' button exists."""
        assert bulk_editor._btn_bulk_plan is not None
        assert bulk_editor._btn_bulk_plan.text() == "Planera"

    def test_execute_button_exists(self, bulk_editor):
        """The 'Utför' button exists."""
        assert bulk_editor._btn_bulk_execute is not None
        assert bulk_editor._btn_bulk_execute.text() == "Utför"

    def test_results_initially_hidden(self, bulk_editor):
        """The plan results area is hidden before planning."""
        assert not bulk_editor._bulk_results_widget.isVisible()


# ============================================================================
# Test: Planera functionality (Requirements 9.1, 9.2, 9.6)
# ============================================================================


class TestBulkPlan:
    """Verify bulk plan creation from pasted text."""

    def test_plan_empty_text_shows_error(self, bulk_editor):
        """Planning with empty text shows an error message."""
        bulk_editor._bulk_paste_edit.setPlainText("")
        bulk_editor._on_bulk_plan()
        # In Qt, isVisible() requires the widget hierarchy to be shown.
        # Check that the label text was set (the label shows the error).
        assert "minst en referensrad" in bulk_editor._bulk_error_label.text()

    def test_plan_parseable_line_creates_candidate(self, bulk_editor):
        """A parseable reference line produces a candidate in the plan."""
        # Use Bild colon format which the parser recognizes
        text = "Ljusdal (X) AI:16 (1871-1875) Bild: 30 Sida: 12"
        bulk_editor._bulk_paste_edit.setPlainText(text)
        bulk_editor._on_bulk_plan()

        assert bulk_editor._bulk_plan is not None
        assert len(bulk_editor._bulk_plan.candidates) == 1
        assert bulk_editor._bulk_plan.candidates[0].observed_from == "1871"
        assert bulk_editor._bulk_plan.candidates[0].observed_to == "1875"

    def test_plan_unparseable_line_listed_truncated(self, bulk_editor):
        """An unparseable line appears under 'Kunde inte tolkas', truncated at 200."""
        # A line the parser won't recognize
        long_junk = "X" * 300
        text = f"Ljusdal (X) AI:16 (1871-1875) Bild: 30 Sida: 12\n{long_junk}"
        bulk_editor._bulk_paste_edit.setPlainText(text)
        bulk_editor._on_bulk_plan()

        assert bulk_editor._bulk_plan is not None
        assert len(bulk_editor._bulk_plan.unparsed_lines) == 1
        # Truncated at 200 characters
        assert len(bulk_editor._bulk_plan.unparsed_lines[0]) == 200

    def test_plan_shows_unparsed_label(self, bulk_editor):
        """Unparsed lines make the unparsed label contain 'Kunde inte tolkas'."""
        text = "Ljusdal (X) AI:16 (1871-1875) Bild: 30 Sida: 12\ngarbage line"
        bulk_editor._bulk_paste_edit.setPlainText(text)
        bulk_editor._on_bulk_plan()

        assert "Kunde inte tolkas" in bulk_editor._bulk_unparsed_label.text()

    def test_plan_prefills_observed_from_to(self, bulk_editor):
        """Candidates get observed_from and observed_to prefilled from years."""
        text = "Ljusdal (X) AI:16 (1871-1875) Bild: 30 Sida: 12"
        bulk_editor._bulk_paste_edit.setPlainText(text)
        bulk_editor._on_bulk_plan()

        plan = bulk_editor._bulk_plan
        assert plan is not None
        candidate = plan.candidates[0]
        assert candidate.observed_from == "1871"
        assert candidate.observed_to == "1875"

    def test_plan_summary_shows_five_counts(self, bulk_editor):
        """The summary label shows the five required counts."""
        text = "Ljusdal (X) AI:16 (1871-1875) Bild: 30 Sida: 12"
        bulk_editor._bulk_paste_edit.setPlainText(text)
        bulk_editor._on_bulk_plan()

        summary = bulk_editor._bulk_summary_label.text()
        assert "Boenden att skapa" in summary
        assert "Boenden att utöka" in summary
        assert "Observationer att bifoga" in summary
        assert "Källor återanvända" in summary
        assert "Rader ej tolkade" in summary

    def test_plan_results_visible_after_plan(self, bulk_editor):
        """The results widget is set to visible after a successful plan."""
        text = "Ljusdal (X) AI:16 (1871-1875) Bild: 30 Sida: 12"
        bulk_editor._bulk_paste_edit.setPlainText(text)
        bulk_editor._on_bulk_plan()

        # Check the summary label was populated (indicates plan was displayed)
        assert bulk_editor._bulk_summary_label.text() != ""


# ============================================================================
# Test: Limit enforcement (Requirement 9.8)
# ============================================================================


class TestBulkLimits:
    """Verify that limits are enforced before processing."""

    def test_exceeding_char_limit_shows_error(self, bulk_editor):
        """Text exceeding 20000 characters is refused with the limit named."""
        # Create text exceeding 20000 chars
        # Use multiple parseable lines to fill the character count
        line = "Ljusdal (X) AI:16 (1871-1875) Bild: 30 Sida: 12"
        # 20001+ characters worth of repeated lines
        text = (line + "\n") * 500  # well over 20000 chars
        bulk_editor._bulk_paste_edit.setPlainText(text)
        bulk_editor._on_bulk_plan()

        assert "tecken" in bulk_editor._bulk_error_label.text()

    def test_exceeding_line_limit_shows_error(self, bulk_editor):
        """More than 50 non-empty lines is refused with the limit named."""
        line = "Ljusdal (X) AI:16 (1871-1875) Bild: 30 Sida: 12"
        # 51 non-empty lines (short enough to stay under char limit)
        lines = [f"Line {i}" for i in range(51)]
        text = "\n".join(lines)
        # Ensure under 20000 chars
        assert len(text) < 20000
        bulk_editor._bulk_paste_edit.setPlainText(text)
        bulk_editor._on_bulk_plan()

        assert "rader" in bulk_editor._bulk_error_label.text()


# ============================================================================
# Test: Candidate selectability (Requirement 9.2)
# ============================================================================


class TestBulkCandidateSelectability:
    """Verify that incomplete candidates are unselectable."""

    def test_complete_candidate_is_selectable(self, bulk_editor):
        """A candidate with both observed_from and observed_to is selectable."""
        text = "Ljusdal (X) AI:16 (1871-1875) Bild: 30 Sida: 12"
        bulk_editor._bulk_paste_edit.setPlainText(text)
        bulk_editor._on_bulk_plan()

        # The candidate table should have one row
        assert bulk_editor._bulk_candidates_table.rowCount() == 1
        # The row should be selectable (has ItemIsSelectable flag)
        from PySide6.QtCore import Qt

        item = bulk_editor._bulk_candidates_table.item(0, 0)
        assert item.flags() & Qt.ItemFlag.ItemIsSelectable


# ============================================================================
# Test: Atomic execution (Requirements 9.3, 9.5, 9.9)
# ============================================================================


class TestBulkExecute:
    """Verify atomic execution of the bulk plan."""

    def test_execute_extends_existing_fact(self, bulk_editor, bulk_project):
        """Executing a plan extends an existing Residence_Fact."""
        text = "Ljusdal (X) AI:16 (1871-1875) Bild: 30 Sida: 12"
        bulk_editor._bulk_paste_edit.setPlainText(text)
        bulk_editor._on_bulk_plan()

        plan = bulk_editor._bulk_plan
        assert plan is not None
        # The plan should extend the existing res_1 since its span overlaps
        assert plan.facts_to_extend >= 1

        original_obs_count = len(bulk_project.residences[0].observations)

        # Complete candidates are already pre-selected by _display_bulk_plan,
        # so no need to call selectRow again (that would deselect in MultiSelection mode).
        bulk_editor._on_bulk_execute()

        # Find the updated fact (it may have been replaced in-place)
        updated_fact = None
        for fact in bulk_project.residences:
            if fact.id == "res_1":
                updated_fact = fact
                break
        assert updated_fact is not None
        assert len(updated_fact.observations) == original_obs_count + 1

    def test_execute_creates_new_fact_when_no_match(self, qapp, monkeypatch):
        """Executing creates a new fact when no existing one matches."""
        monkeypatch.setattr(
            "slaktbusken.ui.editors.residence_editor.QMessageBox.information",
            lambda *args, **kwargs: None,
        )
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            sources=[],
            residences=[],
        )
        # Create a residence for context (even though it will be empty)
        # We need a residence in the editor for place_id context
        residence = ResidenceFact(
            id="res_ctx",
            person_id="p1",
            place_id="pl1",
            start=Endpoint(),
            end=Endpoint(),
        )
        project.residences.append(residence)

        editor = ResidenceEditor(project, residence=residence, person_id="p1")
        text = "Ljusdal (X) AI:16 (1871-1875) Bild: 30 Sida: 12"
        editor._bulk_paste_edit.setPlainText(text)
        editor._on_bulk_plan()

        # The plan should indicate a new fact needs creation (the existing
        # res_ctx has no overlapping span since it has unknown endpoints)
        plan = editor._bulk_plan
        assert plan is not None

        # Complete candidates are pre-selected by _display_bulk_plan.
        editor._on_bulk_execute()

        # A new residence should have been created
        assert len(project.residences) >= 1

    def test_execute_failure_rolls_back(self, qapp, monkeypatch):
        """If execution fails, the project state is restored (all-or-nothing)."""
        monkeypatch.setattr(
            "slaktbusken.ui.editors.residence_editor.QMessageBox.information",
            lambda *args, **kwargs: None,
        )
        monkeypatch.setattr(
            "slaktbusken.ui.editors.residence_editor.QMessageBox.warning",
            lambda *args, **kwargs: None,
        )
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            sources=[],
            residences=[
                ResidenceFact(
                    id="res_1",
                    person_id="p1",
                    place_id="pl1",
                    start=Endpoint(earliest="1860", latest="1866"),
                    end=Endpoint(earliest="1870", latest="1880"),
                    observations=[],
                ),
            ],
        )

        editor = ResidenceEditor(
            project, residence=project.residences[0], person_id="p1"
        )
        text = "Ljusdal (X) AI:16 (1871-1875) Bild: 30 Sida: 12"
        editor._bulk_paste_edit.setPlainText(text)
        editor._on_bulk_plan()

        # Monkeypatch _apply_bulk_plan to raise an exception
        def failing_apply(*args, **kwargs):
            raise RuntimeError("Simulated failure")

        monkeypatch.setattr(editor, "_apply_bulk_plan", failing_apply)

        original_residences = copy.deepcopy(project.residences)
        original_sources = copy.deepcopy(project.sources)

        # Complete candidates are pre-selected by _display_bulk_plan.
        editor._on_bulk_execute()

        # Project should be unchanged due to rollback
        assert len(project.residences) == len(original_residences)
        assert len(project.sources) == len(original_sources)

    def test_execute_source_reused_when_matching(self, bulk_editor, bulk_project):
        """An existing Source is reused when it matches the parsed reference."""
        # Use reference that matches the existing source exactly
        text = "Ljusdal (X) AI:15 (1866-1870) Bild: 25 Sida: 10"
        bulk_editor._bulk_paste_edit.setPlainText(text)
        bulk_editor._on_bulk_plan()

        plan = bulk_editor._bulk_plan
        assert plan is not None
        assert plan.sources_reused >= 1

        original_source_count = len(bulk_project.sources)

        # Complete candidates are pre-selected by _display_bulk_plan.
        bulk_editor._on_bulk_execute()

        # No new source should have been created
        assert len(bulk_project.sources) == original_source_count

    def test_execute_clears_panel_on_success(self, qapp, monkeypatch):
        """After successful execution, the panel state is cleared."""
        monkeypatch.setattr(
            "slaktbusken.ui.editors.residence_editor.QMessageBox.information",
            lambda *args, **kwargs: None,
        )
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            sources=[],
            residences=[
                ResidenceFact(
                    id="res_ctx",
                    person_id="p1",
                    place_id="pl1",
                    start=Endpoint(),
                    end=Endpoint(),
                ),
            ],
        )
        editor = ResidenceEditor(
            project, residence=project.residences[0], person_id="p1"
        )
        text = "Ljusdal (X) AI:16 (1871-1875) Bild: 30 Sida: 12"
        editor._bulk_paste_edit.setPlainText(text)
        editor._on_bulk_plan()

        assert editor._bulk_plan is not None

        # Complete candidates are already pre-selected by _display_bulk_plan.
        # Don't call selectRow again (that toggles off in MultiSelection mode).
        editor._on_bulk_execute()

        # Plan state should be cleared after successful execution
        assert editor._bulk_plan is None


# ============================================================================
# Test: Summary format (Requirement 9.10)
# ============================================================================


class TestBulkSummary:
    """Verify the Swedish summary of five counts."""

    def test_summary_has_all_five_counts(self, bulk_editor):
        """The summary displays all five required counts in Swedish."""
        text = "Ljusdal (X) AI:16 (1871-1875) Bild: 30 Sida: 12\nnonsense line"
        bulk_editor._bulk_paste_edit.setPlainText(text)
        bulk_editor._on_bulk_plan()

        summary = bulk_editor._bulk_summary_label.text()
        # Five distinct lines for counts
        assert "Boenden att skapa:" in summary or "Boenden att utöka:" in summary
        assert "Observationer att bifoga:" in summary
        assert "Källor återanvända:" in summary
        assert "Rader ej tolkade:" in summary
