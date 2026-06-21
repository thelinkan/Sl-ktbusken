"""Unit tests for diagram panel infrastructure.

Tests the DiagramPanel, ZoomableGraphicsView, PersonBoxItem,
PlaceholderBoxItem, and ConnectionLineItem classes.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtWidgets import QApplication

from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.ui.diagram_panel import DiagramPanel, ZoomableGraphicsView, _MAX_ZOOM, _MIN_ZOOM
from slaktbusken.ui.main_window import ViewType
from slaktbusken.ui.widgets.connection_line import ConnectionLineItem, ConnectionType
from slaktbusken.ui.widgets.person_box import PersonBoxItem
from slaktbusken.ui.widgets.placeholder_box import PlaceholderBoxItem, PlaceholderRole


# Ensure QApplication instance exists for widget tests
@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# DiagramPanel tests
# ---------------------------------------------------------------------------


class TestDiagramPanel:
    """Tests for the DiagramPanel widget."""

    def test_creation(self) -> None:
        """DiagramPanel can be instantiated."""
        panel = DiagramPanel()
        assert panel.scene is not None
        assert panel.view is not None
        assert panel.active_person_id is None
        assert panel.current_view is None

    def test_set_active_person(self) -> None:
        """set_active_person updates the active_person_id."""
        panel = DiagramPanel()
        panel.set_active_person("person_42")
        assert panel.active_person_id == "person_42"

    def test_set_active_person_none(self) -> None:
        """set_active_person with None clears the active person."""
        panel = DiagramPanel()
        panel.set_active_person("person_1")
        panel.set_active_person(None)
        assert panel.active_person_id is None

    def test_switch_view(self) -> None:
        """switch_view updates the current_view."""
        panel = DiagramPanel()
        panel.switch_view(ViewType.FAMILY)
        assert panel.current_view == ViewType.FAMILY

        panel.switch_view(ViewType.ANCESTRY)
        assert panel.current_view == ViewType.ANCESTRY

        panel.switch_view(ViewType.DESCENDANTS)
        assert panel.current_view == ViewType.DESCENDANTS


# ---------------------------------------------------------------------------
# ZoomableGraphicsView tests
# ---------------------------------------------------------------------------


class TestZoomableGraphicsView:
    """Tests for the ZoomableGraphicsView widget."""

    def test_initial_zoom(self) -> None:
        """Initial zoom factor is 1.0 (100%)."""
        panel = DiagramPanel()
        assert panel.view.zoom_factor == 1.0

    def test_set_zoom_clamps_minimum(self) -> None:
        """set_zoom clamps to 25% minimum."""
        panel = DiagramPanel()
        panel.view.set_zoom(0.1)
        assert panel.view.zoom_factor == pytest.approx(_MIN_ZOOM)

    def test_set_zoom_clamps_maximum(self) -> None:
        """set_zoom clamps to 400% maximum."""
        panel = DiagramPanel()
        panel.view.set_zoom(10.0)
        assert panel.view.zoom_factor == pytest.approx(_MAX_ZOOM)

    def test_set_zoom_within_range(self) -> None:
        """set_zoom accepts values within range."""
        panel = DiagramPanel()
        panel.view.set_zoom(2.0)
        assert panel.view.zoom_factor == pytest.approx(2.0)

    def test_reset_zoom(self) -> None:
        """reset_zoom returns to 100%."""
        panel = DiagramPanel()
        panel.view.set_zoom(3.0)
        panel.view.reset_zoom()
        assert panel.view.zoom_factor == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# PersonBoxItem tests
# ---------------------------------------------------------------------------


class TestPersonBoxItem:
    """Tests for the PersonBoxItem graphics item."""

    def test_creation(self) -> None:
        """PersonBoxItem can be created with basic data."""
        config = PersonBoxConfig()
        data = {"name": "Erik Svensson", "birth_date": "1850-03-15", "death_date": "1920-11-02"}
        item = PersonBoxItem("person_1", data, config)
        assert item.person_id == "person_1"

    def test_bounding_rect_is_valid(self) -> None:
        """boundingRect returns a non-empty rectangle."""
        config = PersonBoxConfig()
        data = {"name": "Anna Karlsson"}
        item = PersonBoxItem("person_2", data, config)
        rect = item.boundingRect()
        assert rect.width() > 0
        assert rect.height() > 0

    def test_omits_empty_fields(self) -> None:
        """Fields with no data are omitted (Req 20.4)."""
        config = PersonBoxConfig(
            name=True,
            birth_date=True,
            birth_place=True,
            death_date=True,
        )
        data = {"name": "Erik Svensson", "birth_date": "1850", "birth_place": None, "death_date": ""}
        item = PersonBoxItem("person_3", data, config)
        # Only name and birth_date should produce lines
        assert len(item._lines) == 2
        assert item._lines[0] == "Erik Svensson"
        assert "1850" in item._lines[1]

    def test_omits_disabled_fields(self) -> None:
        """Disabled config fields are not shown even with data."""
        config = PersonBoxConfig(
            name=True,
            birth_date=False,
            death_date=False,
        )
        data = {"name": "Test Person", "birth_date": "1900", "death_date": "1980"}
        item = PersonBoxItem("person_4", data, config)
        assert len(item._lines) == 1
        assert item._lines[0] == "Test Person"

    def test_selection_state(self) -> None:
        """set_selected toggles the selection state."""
        config = PersonBoxConfig()
        data = {"name": "Test"}
        item = PersonBoxItem("person_5", data, config)
        assert not item.is_selected
        item.set_selected(True)
        assert item.is_selected
        item.set_selected(False)
        assert not item.is_selected

    def test_all_fields_shown_when_enabled_and_present(self) -> None:
        """All configured and non-empty fields appear in lines."""
        config = PersonBoxConfig(
            name=True,
            birth_date=True,
            birth_place=True,
            death_date=True,
            death_place=True,
            marriage_date=True,
            marriage_place=True,
            occupation=True,
            dna_info=True,
            notes=True,
        )
        data = {
            "name": "Erik Svensson",
            "birth_date": "1850-03-15",
            "birth_place": "Ljusdal",
            "death_date": "1920-11-02",
            "death_place": "Stockholm",
            "marriage_date": "1875-06-12",
            "marriage_place": "Ljusdals kyrka",
            "occupation": "Bonde",
            "dna_info": "Cluster A",
            "notes": "Forskning pågår",
        }
        item = PersonBoxItem("person_6", data, config)
        # Date+place combined on same line: 7 lines total
        # name, birth+place, death+place, marriage+place, occupation, dna, notes
        assert len(item._lines) == 7


# ---------------------------------------------------------------------------
# PlaceholderBoxItem tests
# ---------------------------------------------------------------------------


class TestPlaceholderBoxItem:
    """Tests for the PlaceholderBoxItem graphics item."""

    def test_creation_mother(self) -> None:
        """PlaceholderBoxItem can be created with MOTHER role."""
        item = PlaceholderBoxItem(PlaceholderRole.MOTHER)
        assert item.role == PlaceholderRole.MOTHER
        assert item.family_id is None

    def test_creation_father(self) -> None:
        """PlaceholderBoxItem can be created with FATHER role."""
        item = PlaceholderBoxItem(PlaceholderRole.FATHER)
        assert item.role == PlaceholderRole.FATHER

    def test_creation_child_with_family_id(self) -> None:
        """PlaceholderBoxItem for CHILD stores family_id."""
        item = PlaceholderBoxItem(PlaceholderRole.CHILD, family_id="family_7")
        assert item.role == PlaceholderRole.CHILD
        assert item.family_id == "family_7"

    def test_bounding_rect_is_valid(self) -> None:
        """boundingRect returns a non-empty rectangle."""
        item = PlaceholderBoxItem(PlaceholderRole.MOTHER)
        rect = item.boundingRect()
        assert rect.width() > 0
        assert rect.height() > 0


# ---------------------------------------------------------------------------
# ConnectionLineItem tests
# ---------------------------------------------------------------------------


class TestConnectionLineItem:
    """Tests for the ConnectionLineItem graphics item."""

    def test_parent_child_creation(self) -> None:
        """ConnectionLineItem can be created for parent-child."""
        start = QPointF(100, 50)
        end = QPointF(100, 150)
        item = ConnectionLineItem(start, end, ConnectionType.PARENT_CHILD)
        assert item.connection_type == ConnectionType.PARENT_CHILD
        assert item.start_point == start
        assert item.end_point == end

    def test_partner_creation(self) -> None:
        """ConnectionLineItem can be created for partner connections."""
        start = QPointF(50, 100)
        end = QPointF(250, 100)
        item = ConnectionLineItem(start, end, ConnectionType.PARTNER)
        assert item.connection_type == ConnectionType.PARTNER

    def test_bounding_rect_is_valid(self) -> None:
        """boundingRect returns a non-empty rectangle."""
        start = QPointF(0, 0)
        end = QPointF(100, 200)
        item = ConnectionLineItem(start, end)
        rect = item.boundingRect()
        assert rect.width() > 0
        assert rect.height() > 0

    def test_set_points_updates(self) -> None:
        """set_points updates the start and end positions."""
        start = QPointF(0, 0)
        end = QPointF(50, 50)
        item = ConnectionLineItem(start, end)

        new_start = QPointF(10, 10)
        new_end = QPointF(200, 200)
        item.set_points(new_start, new_end)

        assert item.start_point == new_start
        assert item.end_point == new_end

    def test_default_connection_type(self) -> None:
        """Default connection type is PARENT_CHILD."""
        item = ConnectionLineItem(QPointF(0, 0), QPointF(100, 100))
        assert item.connection_type == ConnectionType.PARENT_CHILD
