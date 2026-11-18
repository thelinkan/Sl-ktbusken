# Feature: residence-periods, Property 18: Derived bounds reach storage only through confirmed, selected rows
"""Property-based test for confirmed derived-bound writes.

Feature: residence-periods, Property 18: Derived bounds reach storage only through confirmed, selected rows

The TightenBoundsDialog presents derived bounds as preselected rows. Only selected
(checked) rows are returned by `selected_bounds()`. Deselected rows are excluded.
The dialog does not write anything itself — it only returns the selection for the
caller to apply. `format_harlett_display` adds the "(härlett)" suffix to display
derived values read-only, and those values are never saved.

**Validates: Requirements 7.7, 7.8, 7.9**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from slaktbusken.services.residence_inference import DerivedBound
from slaktbusken.ui.dialogs.tighten_bounds_dialog import (
    TightenBoundsDialog,
    format_harlett_display,
    has_derived_bounds,
)

import pytest


# ---------------------------------------------------------------------------
# QApplication fixture (session-scoped for PySide6)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Ensure a QApplication exists for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_ISO_YEARS = st.integers(min_value=1500, max_value=2100).map(str)
_ISO_MONTHS = st.builds(
    lambda y, m: f"{y}-{m:02d}",
    y=st.integers(min_value=1500, max_value=2100),
    m=st.integers(min_value=1, max_value=12),
)
_ISO_DAYS = st.builds(
    lambda y, m, d: f"{y}-{m:02d}-{d:02d}",
    y=st.integers(min_value=1500, max_value=2100),
    m=st.integers(min_value=1, max_value=12),
    d=st.integers(min_value=1, max_value=28),
)
_ISO_VALUES = st.one_of(_ISO_YEARS, _ISO_MONTHS, _ISO_DAYS)

_ENDPOINTS = st.sampled_from(["start", "end"])
_BOUNDS = st.sampled_from(["earliest", "latest"])
_ORIGIN_KINDS = st.sampled_from(["residence", "event"])
_ORIGIN_LABELS = st.sampled_from([
    "Gävle", "Stockholm", "Uppsala", "Ljusdal", "Mora",
    "Född", "Död", "Dop", "Begravning",
])


@st.composite
def derived_bounds_lists(draw: st.DrawFn) -> list[DerivedBound]:
    """Generate a non-empty list of 1–6 DerivedBound entries."""
    count = draw(st.integers(min_value=1, max_value=6))
    bounds: list[DerivedBound] = []
    for i in range(count):
        bounds.append(
            DerivedBound(
                residence_id=f"res_{draw(st.integers(min_value=1, max_value=5))}",
                endpoint=draw(_ENDPOINTS),
                bound=draw(_BOUNDS),
                value=draw(_ISO_VALUES),
                origin_kind=draw(_ORIGIN_KINDS),
                origin_id=f"origin_{i + 1}",
                origin_label=draw(_ORIGIN_LABELS),
            )
        )
    return bounds


@st.composite
def selection_masks(draw: st.DrawFn, n: int) -> list[bool]:
    """Generate a boolean mask of length n for checkbox selections."""
    return [draw(st.booleans()) for _ in range(n)]


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


class TestConfirmedDerivedBoundWrites:
    """Property 18: Derived bounds reach storage only through confirmed, selected rows.

    **Validates: Requirements 7.7, 7.8, 7.9**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_only_selected_rows_returned_and_dialog_writes_nothing(
        self, data: st.DataObject
    ) -> None:
        """Only checked rows appear in selected_bounds(); deselected are excluded;
        the dialog writes nothing itself; format_harlett_display adds the suffix.

        Feature: residence-periods, Property 18: Derived bounds reach storage only through confirmed, selected rows

        **Validates: Requirements 7.7, 7.8, 7.9**
        """
        derived = data.draw(derived_bounds_lists())
        n = len(derived)
        mask = data.draw(selection_masks(n))

        # Build stored_values dict: None for all (simulating absent bounds)
        stored_values: dict[tuple[str, str], str | None] = {}
        for db in derived:
            stored_values[(db.endpoint, db.bound)] = None

        # --- Create dialog (Requirement 7.8: preselected, individually deselectable) ---
        dialog = TightenBoundsDialog(derived, stored_values)

        # --- ASSERTION 1: All rows start preselected (Req 7.8) ---
        for row in range(dialog._table.rowCount()):
            item = dialog._table.item(row, 0)
            assert item.checkState() == Qt.CheckState.Checked, (
                f"Row {row} was not preselected"
            )

        # --- Apply the generated selection mask ---
        for row, selected in enumerate(mask):
            if not selected:
                dialog._table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)

        # --- ASSERTION 2: selected_bounds() returns exactly the checked rows (Req 7.9) ---
        result = dialog.selected_bounds()
        expected = [db for db, sel in zip(derived, mask) if sel]

        assert len(result) == len(expected), (
            f"Expected {len(expected)} selected bounds, got {len(result)}.\n"
            f"Mask: {mask}"
        )
        for i, (got, want) in enumerate(zip(result, expected)):
            assert got is want, (
                f"selected_bounds()[{i}] is not the expected DerivedBound.\n"
                f"Expected: {want}\nGot: {got}"
            )

        # --- ASSERTION 3: Deselected rows are NOT in the result (Req 7.9) ---
        excluded = [db for db, sel in zip(derived, mask) if not sel]
        result_set = set(id(r) for r in result)
        for db in excluded:
            assert id(db) not in result_set, (
                f"Deselected bound {db} appeared in selected_bounds()"
            )

        # --- ASSERTION 4: The dialog does not write anything itself (Req 7.9) ---
        # The dialog has no method that mutates a ResidenceFact; it only returns
        # the selection. Verify the dialog's own class (not inherited Qt methods)
        # defines no write/apply/save method — only selected_bounds().
        own_public_methods = [
            m for m in vars(type(dialog))
            if not m.startswith("_") and callable(getattr(dialog, m, None))
        ]
        write_methods = [
            m for m in own_public_methods
            if any(keyword in m.lower() for keyword in ["write", "apply", "save", "persist", "commit"])
        ]
        assert write_methods == [], (
            f"Dialog defines write-like methods: {write_methods}. "
            f"The dialog should only return selections, never write."
        )

        # --- ASSERTION 5: format_harlett_display adds "(härlett)" suffix (Req 7.7) ---
        for db in derived:
            display = format_harlett_display(db)
            assert display == f"{db.value} (härlett)", (
                f"format_harlett_display did not produce expected output.\n"
                f"  value    = {db.value!r}\n"
                f"  result   = {display!r}\n"
                f"  expected = {db.value + ' (härlett)'!r}"
            )
            # The suffix is present and the value is read-only display only
            assert display.endswith("(härlett)")
            assert db.value in display

        # --- ASSERTION 6: has_derived_bounds is True for non-empty lists (Req 7.11) ---
        assert has_derived_bounds(derived) is True
