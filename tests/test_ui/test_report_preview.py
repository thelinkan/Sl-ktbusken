"""Unit tests for the Report Preview dialog.

Tests paper size selection, default paper size, fallback behaviour,
and pagination updates.

Validates: Requirements 5.1, 5.2, 5.3, 5.6
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.persistence.settings_io import ProjectSettings
from slaktbusken.reports.content import ParagraphBlock, ReportContent
from slaktbusken.ui.dialogs.report_preview import ReportPreviewDialog


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_content() -> ReportContent:
    """Create a simple ReportContent with enough text to span multiple pages."""
    blocks = [ParagraphBlock(text="Test text " * 50) for _ in range(20)]
    return ReportContent(title="Test Report", blocks=blocks)


class TestPaperSizeComboOptions:
    """Requirement 5.1: Paper_Size selection control offering A4, A3, A5 formats."""

    def test_combo_contains_a4_a3_a5(self) -> None:
        """The paper size combo box must offer exactly A4, A3, A5."""
        settings = ProjectSettings()
        content = _make_content()
        dialog = ReportPreviewDialog(content, settings)

        combo = dialog._paper_size_combo
        items = [combo.itemText(i) for i in range(combo.count())]
        assert "A4" in items
        assert "A3" in items
        assert "A5" in items

    def test_combo_has_three_items(self) -> None:
        """The combo box has exactly three paper size options."""
        settings = ProjectSettings()
        content = _make_content()
        dialog = ReportPreviewDialog(content, settings)

        assert dialog._paper_size_combo.count() == 3


class TestDefaultPaperSize:
    """Requirement 5.2: Default Paper_Size is A4 when generating a report."""

    def test_default_paper_size_is_a4(self) -> None:
        """A new ProjectSettings should cause the dialog to show A4 as default."""
        settings = ProjectSettings()
        content = _make_content()
        dialog = ReportPreviewDialog(content, settings)

        assert dialog._paper_size_combo.currentText() == "A4"

    def test_settings_default_report_paper_size_is_a4(self) -> None:
        """ProjectSettings default value for report_paper_size is A4."""
        settings = ProjectSettings()
        assert settings.report_paper_size == "A4"


class TestUnrecognizedPaperSizeFallback:
    """Requirement 5.2 / 5.3: Unrecognized paper size falls back to A4."""

    def test_invalid_paper_size_falls_back_to_a4(self) -> None:
        """Setting an invalid paper size (e.g. 'Letter') should show A4 in the dialog."""
        settings = ProjectSettings()
        settings.report_paper_size = "Letter"
        content = _make_content()
        dialog = ReportPreviewDialog(content, settings)

        assert dialog._paper_size_combo.currentText() == "A4"

    def test_empty_paper_size_falls_back_to_a4(self) -> None:
        """An empty string paper size should fall back to A4."""
        settings = ProjectSettings()
        settings.report_paper_size = ""
        content = _make_content()
        dialog = ReportPreviewDialog(content, settings)

        assert dialog._paper_size_combo.currentText() == "A4"


class TestPaperSizeChangePagination:
    """Requirement 5.3: Re-paginate report content on paper size change."""

    def test_paper_size_change_updates_page_count(self) -> None:
        """Changing paper size from A4 to A5 should increase page count (smaller pages)."""
        settings = ProjectSettings()
        content = _make_content()
        dialog = ReportPreviewDialog(content, settings)

        # Initial pagination with A4
        pages_a4 = len(dialog._pages)

        # Change to A5 (smaller paper = more pages)
        dialog._paper_size_combo.setCurrentText("A5")
        pages_a5 = len(dialog._pages)

        assert pages_a5 > pages_a4

    def test_paper_size_change_to_a3_reduces_pages(self) -> None:
        """Changing paper size from A4 to A3 should reduce page count (larger pages)."""
        settings = ProjectSettings()
        content = _make_content()
        dialog = ReportPreviewDialog(content, settings)

        pages_a4 = len(dialog._pages)

        # Change to A3 (larger paper = fewer pages)
        dialog._paper_size_combo.setCurrentText("A3")
        pages_a3 = len(dialog._pages)

        assert pages_a3 <= pages_a4


class TestPaperSizePersistence:
    """Requirement 5.6: Persist most recently selected Paper_Size in project settings."""

    def test_paper_size_change_persists_to_settings(self) -> None:
        """Changing the combo box to A5 should update settings.report_paper_size."""
        settings = ProjectSettings()
        content = _make_content()
        dialog = ReportPreviewDialog(content, settings)

        dialog._paper_size_combo.setCurrentText("A5")
        assert settings.report_paper_size == "A5"

    def test_paper_size_change_to_a3_persists(self) -> None:
        """Changing the combo box to A3 should update settings.report_paper_size."""
        settings = ProjectSettings()
        content = _make_content()
        dialog = ReportPreviewDialog(content, settings)

        dialog._paper_size_combo.setCurrentText("A3")
        assert settings.report_paper_size == "A3"
