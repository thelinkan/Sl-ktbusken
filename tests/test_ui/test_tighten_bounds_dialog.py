"""Unit tests for the TightenBoundsDialog.

Tests the dialog structure, row population, checkbox behaviour,
the härlett display helper, and the zero-derived-bounds path.

Validates: Requirements 7.7, 7.8, 7.9, 7.11
"""

from __future__ import annotations

import pytest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from slaktbusken.services.residence_inference import DerivedBound
from slaktbusken.ui.dialogs.tighten_bounds_dialog import (
    NO_DERIVED_BOUNDS_MESSAGE,
    TightenBoundsDialog,
    format_harlett_display,
    has_derived_bounds,
)


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def sample_derived_bounds() -> list[DerivedBound]:
    """Two sample derived bounds for testing."""
    return [
        DerivedBound(
            residence_id="res_1",
            endpoint="start",
            bound="earliest",
            value="1840",
            origin_kind="residence",
            origin_id="res_2",
            origin_label="Gävle",
        ),
        DerivedBound(
            residence_id="res_1",
            endpoint="end",
            bound="latest",
            value="1885",
            origin_kind="event",
            origin_id="evt_1",
            origin_label="Död",
        ),
    ]


@pytest.fixture()
def sample_stored_values() -> dict[tuple[str, str], str | None]:
    """Stored values corresponding to the sample derived bounds."""
    return {
        ("start", "earliest"): None,
        ("start", "latest"): "1845",
        ("end", "earliest"): "1880",
        ("end", "latest"): None,
    }


class TestHasDerivedBounds:
    """Tests for the has_derived_bounds helper (Requirement 7.11)."""

    def test_returns_false_for_empty_list(self):
        assert has_derived_bounds([]) is False

    def test_returns_true_for_non_empty_list(self, sample_derived_bounds):
        assert has_derived_bounds(sample_derived_bounds) is True

    def test_no_derived_bounds_message_is_correct(self):
        assert NO_DERIVED_BOUNDS_MESSAGE == "Inga härledda värden att föreslå."


class TestFormatHarlettDisplay:
    """Tests for the härlett display formatting (Requirement 7.7)."""

    def test_formats_with_harlett_suffix(self):
        db = DerivedBound(
            residence_id="res_1",
            endpoint="start",
            bound="earliest",
            value="1840",
            origin_kind="residence",
            origin_id="res_2",
            origin_label="Gävle",
        )
        result = format_harlett_display(db)
        assert result == "1840 (härlett)"

    def test_formats_month_precision_value(self):
        db = DerivedBound(
            residence_id="res_1",
            endpoint="end",
            bound="latest",
            value="1885-06",
            origin_kind="event",
            origin_id="evt_1",
            origin_label="Död",
        )
        result = format_harlett_display(db)
        assert result == "1885-06 (härlett)"

    def test_formats_day_precision_value(self):
        db = DerivedBound(
            residence_id="res_1",
            endpoint="start",
            bound="earliest",
            value="1840-03-15",
            origin_kind="residence",
            origin_id="res_2",
            origin_label="Stockholm",
        )
        result = format_harlett_display(db)
        assert result == "1840-03-15 (härlett)"


class TestTightenBoundsDialogStructure:
    """Tests for the dialog UI structure (Requirement 7.8)."""

    def test_dialog_has_title(self, qapp, sample_derived_bounds, sample_stored_values):
        dialog = TightenBoundsDialog(sample_derived_bounds, sample_stored_values)
        assert dialog.windowTitle() == "Snäva in från grannar"

    def test_dialog_has_minimum_width(
        self, qapp, sample_derived_bounds, sample_stored_values
    ):
        dialog = TightenBoundsDialog(sample_derived_bounds, sample_stored_values)
        assert dialog.minimumWidth() >= 600

    def test_table_has_correct_column_count(
        self, qapp, sample_derived_bounds, sample_stored_values
    ):
        dialog = TightenBoundsDialog(sample_derived_bounds, sample_stored_values)
        assert dialog._table.columnCount() == 6

    def test_table_has_correct_row_count(
        self, qapp, sample_derived_bounds, sample_stored_values
    ):
        dialog = TightenBoundsDialog(sample_derived_bounds, sample_stored_values)
        assert dialog._table.rowCount() == 2

    def test_table_headers(
        self, qapp, sample_derived_bounds, sample_stored_values
    ):
        dialog = TightenBoundsDialog(sample_derived_bounds, sample_stored_values)
        headers = [
            dialog._table.horizontalHeaderItem(col).text()
            for col in range(dialog._table.columnCount())
        ]
        assert headers == [
            "",
            "Endpunkt",
            "Gräns",
            "Nuvarande värde",
            "Föreslaget värde",
            "Källa",
        ]


class TestTightenBoundsDialogRows:
    """Tests for row content (Requirement 7.8)."""

    def test_first_row_shows_start_earliest(
        self, qapp, sample_derived_bounds, sample_stored_values
    ):
        dialog = TightenBoundsDialog(sample_derived_bounds, sample_stored_values)
        # Endpoint column
        assert dialog._table.item(0, 1).text() == "Början"
        # Bound column
        assert dialog._table.item(0, 2).text() == "Tidigast"

    def test_second_row_shows_end_latest(
        self, qapp, sample_derived_bounds, sample_stored_values
    ):
        dialog = TightenBoundsDialog(sample_derived_bounds, sample_stored_values)
        assert dialog._table.item(1, 1).text() == "Slut"
        assert dialog._table.item(1, 2).text() == "Senast"

    def test_absent_stored_value_shows_okant(
        self, qapp, sample_derived_bounds, sample_stored_values
    ):
        dialog = TightenBoundsDialog(sample_derived_bounds, sample_stored_values)
        # start.earliest is None → "okänt"
        assert dialog._table.item(0, 3).text() == "okänt"

    def test_present_stored_value_shows_value(self, qapp):
        """When a stored bound has a value, show it instead of 'okänt'."""
        derived = [
            DerivedBound(
                residence_id="res_1",
                endpoint="start",
                bound="latest",
                value="1842",
                origin_kind="residence",
                origin_id="res_3",
                origin_label="Uppsala",
            ),
        ]
        stored = {("start", "latest"): "1845"}
        dialog = TightenBoundsDialog(derived, stored)
        assert dialog._table.item(0, 3).text() == "1845"

    def test_proposed_value_column(
        self, qapp, sample_derived_bounds, sample_stored_values
    ):
        dialog = TightenBoundsDialog(sample_derived_bounds, sample_stored_values)
        assert dialog._table.item(0, 4).text() == "1840"
        assert dialog._table.item(1, 4).text() == "1885"

    def test_origin_column(
        self, qapp, sample_derived_bounds, sample_stored_values
    ):
        dialog = TightenBoundsDialog(sample_derived_bounds, sample_stored_values)
        assert dialog._table.item(0, 5).text() == "Gävle"
        assert dialog._table.item(1, 5).text() == "Död"


class TestTightenBoundsDialogCheckboxes:
    """Tests for checkbox preselection and deselection (Requirements 7.8, 7.9)."""

    def test_all_rows_preselected(
        self, qapp, sample_derived_bounds, sample_stored_values
    ):
        dialog = TightenBoundsDialog(sample_derived_bounds, sample_stored_values)
        for row in range(dialog._table.rowCount()):
            item = dialog._table.item(row, 0)
            assert item.checkState() == Qt.CheckState.Checked

    def test_selected_bounds_returns_all_when_all_checked(
        self, qapp, sample_derived_bounds, sample_stored_values
    ):
        dialog = TightenBoundsDialog(sample_derived_bounds, sample_stored_values)
        selected = dialog.selected_bounds()
        assert len(selected) == 2
        assert selected[0] is sample_derived_bounds[0]
        assert selected[1] is sample_derived_bounds[1]

    def test_deselecting_row_excludes_from_result(
        self, qapp, sample_derived_bounds, sample_stored_values
    ):
        dialog = TightenBoundsDialog(sample_derived_bounds, sample_stored_values)
        # Deselect first row
        dialog._table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
        selected = dialog.selected_bounds()
        assert len(selected) == 1
        assert selected[0] is sample_derived_bounds[1]

    def test_deselecting_all_rows_returns_empty(
        self, qapp, sample_derived_bounds, sample_stored_values
    ):
        dialog = TightenBoundsDialog(sample_derived_bounds, sample_stored_values)
        for row in range(dialog._table.rowCount()):
            dialog._table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)
        selected = dialog.selected_bounds()
        assert selected == []


class TestTightenBoundsDialogReadOnly:
    """Tests that data columns are read-only (Requirement 7.8)."""

    def test_data_columns_not_editable(
        self, qapp, sample_derived_bounds, sample_stored_values
    ):
        dialog = TightenBoundsDialog(sample_derived_bounds, sample_stored_values)
        # Columns 1-5 should not have ItemIsEditable flag
        for row in range(dialog._table.rowCount()):
            for col in range(1, 6):
                item = dialog._table.item(row, col)
                assert not (item.flags() & Qt.ItemFlag.ItemIsEditable)

    def test_checkbox_column_is_checkable(
        self, qapp, sample_derived_bounds, sample_stored_values
    ):
        dialog = TightenBoundsDialog(sample_derived_bounds, sample_stored_values)
        for row in range(dialog._table.rowCount()):
            item = dialog._table.item(row, 0)
            assert item.flags() & Qt.ItemFlag.ItemIsUserCheckable


class TestTightenBoundsDialogEmpty:
    """Tests for the zero derived bounds case (Requirement 7.11)."""

    def test_has_derived_bounds_false_for_empty(self):
        assert has_derived_bounds([]) is False

    def test_dialog_can_be_created_with_empty_list(self, qapp):
        """Even with an empty list, the dialog can be instantiated.

        In practice, the caller checks has_derived_bounds first and
        shows the NO_DERIVED_BOUNDS_MESSAGE instead.
        """
        dialog = TightenBoundsDialog([], {})
        assert dialog._table.rowCount() == 0
