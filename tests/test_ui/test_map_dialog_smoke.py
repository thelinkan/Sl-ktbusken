"""Smoke test for MapDialog instantiation (Checkpoint 4).

Verifies that MapDialog can be instantiated without errors and has
the expected window title, minimum size, and modality.
"""

import sys

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.services.map_data_service import MapMarker
from slaktbusken.ui.dialogs.map_dialog import MapDialog


@pytest.fixture(scope="session")
def qapp():
    """Provide a QApplication instance for the test session."""
    app = QApplication.instance() or QApplication(sys.argv)
    return app


def test_map_dialog_instantiation(qapp):
    """MapDialog can be instantiated with test markers without crashing."""
    markers = [
        MapMarker(
            place_id="p1",
            place_name="Stockholm",
            latitude=59.33,
            longitude=18.07,
            events=[],
        ),
        MapMarker(
            place_id="p2",
            place_name="Göteborg",
            latitude=57.70,
            longitude=11.97,
            events=[],
        ),
    ]
    dialog = MapDialog(markers, "Karta — Test")

    assert dialog.windowTitle() == "Karta — Test"
    assert dialog.minimumWidth() == 900
    assert dialog.minimumHeight() == 700
    assert dialog.isModal()


def test_map_dialog_with_empty_markers(qapp):
    """MapDialog can be instantiated with an empty marker list."""
    dialog = MapDialog([], "Karta — Tom")

    assert dialog.windowTitle() == "Karta — Tom"
    assert dialog.minimumWidth() == 900
    assert dialog.minimumHeight() == 700
    assert dialog.isModal()
