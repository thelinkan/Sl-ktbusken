"""Unit tests for the Report Menu structure.

Verifies category submenus, item placement, placeholder/implemented states,
tooltip behaviour, and project-open/closed toggling.

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 1.9, 1.10, 1.11
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMenuBar

from slaktbusken.ui.report_menu import ReportMenuBuilder, _PLACEHOLDER_TOOLTIP


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# Fake application stubs
# ---------------------------------------------------------------------------


class _FakeProjectService:
    def __init__(self, project_open: bool = False):
        self.project_path = Path("/fake") if project_open else None


class _FakeApp:
    def __init__(self, project_open: bool = False):
        self.project_service = _FakeProjectService(project_open)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PLACEHOLDER_LABELS = {
    "Antavla",
    "Ättlingarapport",
    "DNA-matchlista",
    "Klusterrapport",
    "Trianguleringsrapport",
    "Personkonsistens",
    "Familjekonsistens",
    "Källkonsistens",
    "Öppna forskningsfrågor",
    "Personer med saknade källor",
    "ArkivDigital-export",
    "GEDCOM-export",
}

_IMPLEMENTED_LABELS = {
    "Ansedel",
    "Geografisk konsistens",
    "Mediakonsistens",
}


@pytest.fixture()
def menu_project_open():
    """Build menu with project open; keep all Qt objects alive."""
    builder = ReportMenuBuilder()
    menu_bar = QMenuBar()
    app = _FakeApp(project_open=True)
    menu = builder.build(menu_bar, app)
    return builder, menu, menu_bar


@pytest.fixture()
def menu_project_closed():
    """Build menu with no project open; keep all Qt objects alive."""
    builder = ReportMenuBuilder()
    menu_bar = QMenuBar()
    app = _FakeApp(project_open=False)
    menu = builder.build(menu_bar, app)
    return builder, menu, menu_bar


def _collect_all_actions(menu):
    """Collect all submenu actions as list of (submenu_title, action) tuples.

    We iterate submenus immediately and collect action data (text, enabled,
    tooltip) to avoid lifetime issues with Qt C++ objects.
    """
    results = []
    for top_action in menu.actions():
        sub = top_action.menu()
        if sub is not None:
            title = sub.title()
            for action in sub.actions():
                results.append({
                    "submenu": title,
                    "text": action.text(),
                    "enabled": action.isEnabled(),
                    "tooltip": action.toolTip(),
                })
    return results


def _get_submenu_items(menu):
    """Return dict of submenu title -> list of item labels."""
    result: dict[str, list[str]] = {}
    for top_action in menu.actions():
        sub = top_action.menu()
        if sub is not None:
            result[sub.title()] = [a.text() for a in sub.actions()]
    return result


# ---------------------------------------------------------------------------
# Test: Top-level menu label
# ---------------------------------------------------------------------------


class TestMenuLabel:
    """Requirement 1.1: Top-level menu is labeled 'Rapporter'."""

    def test_top_level_menu_labeled_rapporter(self, menu_project_open) -> None:
        _, menu, _bar = menu_project_open
        assert menu.title().replace("&", "") == "Rapporter"


# ---------------------------------------------------------------------------
# Test: Five category submenus exist with correct labels
# ---------------------------------------------------------------------------


class TestCategorySubmenus:
    """Requirement 1.1: Five category submenus with correct labels."""

    def test_has_five_submenus(self, menu_project_open) -> None:
        _, menu, _bar = menu_project_open
        submenus = _get_submenu_items(menu)
        assert len(submenus) == 5

    def test_submenu_labels(self, menu_project_open) -> None:
        _, menu, _bar = menu_project_open
        submenus = _get_submenu_items(menu)
        expected = {
            "Standardrapporter",
            "DNA-rapporter",
            "Konsistensrapporter",
            "Forskningsrapporter",
            "Exportkontroller",
        }
        assert set(submenus.keys()) == expected


# ---------------------------------------------------------------------------
# Test: Items in correct submenus with correct labels
# ---------------------------------------------------------------------------


class TestSubmenuItems:
    """Requirements 1.2–1.6: Correct items in each category."""

    def test_standardrapporter_items(self, menu_project_open) -> None:
        _, menu, _bar = menu_project_open
        submenus = _get_submenu_items(menu)
        assert submenus["Standardrapporter"] == [
            "Ansedel",
            "Källrapport",
            "Antavla",
            "Ättlingarapport",
        ]

    def test_dna_rapporter_items(self, menu_project_open) -> None:
        _, menu, _bar = menu_project_open
        submenus = _get_submenu_items(menu)
        assert submenus["DNA-rapporter"] == [
            "DNA-matchlista",
            "Klusterrapport",
            "Trianguleringsrapport",
        ]

    def test_konsistensrapporter_items(self, menu_project_open) -> None:
        _, menu, _bar = menu_project_open
        submenus = _get_submenu_items(menu)
        assert submenus["Konsistensrapporter"] == [
            "Geografisk konsistens",
            "Personkonsistens",
            "Familjekonsistens",
            "Mediakonsistens",
            "Källkonsistens",
        ]

    def test_forskningsrapporter_items(self, menu_project_open) -> None:
        _, menu, _bar = menu_project_open
        submenus = _get_submenu_items(menu)
        assert submenus["Forskningsrapporter"] == [
            "Öppna forskningsfrågor",
            "Personer med saknade källor",
        ]

    def test_exportkontroller_items(self, menu_project_open) -> None:
        _, menu, _bar = menu_project_open
        submenus = _get_submenu_items(menu)
        assert submenus["Exportkontroller"] == [
            "ArkivDigital-export",
            "GEDCOM-export",
        ]


# ---------------------------------------------------------------------------
# Test: Placeholder items disabled with tooltip
# ---------------------------------------------------------------------------


class TestPlaceholderState:
    """Requirements 1.8, 1.9: Placeholders disabled with tooltip."""

    def test_placeholder_items_disabled(self, menu_project_open) -> None:
        _, menu, _bar = menu_project_open
        all_actions = _collect_all_actions(menu)
        placeholders = [a for a in all_actions if a["text"] in _PLACEHOLDER_LABELS]
        assert len(placeholders) == len(_PLACEHOLDER_LABELS)
        for item in placeholders:
            assert not item["enabled"], (
                f"Placeholder '{item['text']}' should be disabled"
            )

    def test_placeholder_items_have_tooltip(self, menu_project_open) -> None:
        _, menu, _bar = menu_project_open
        all_actions = _collect_all_actions(menu)
        placeholders = [a for a in all_actions if a["text"] in _PLACEHOLDER_LABELS]
        for item in placeholders:
            assert item["tooltip"] == _PLACEHOLDER_TOOLTIP, (
                f"Placeholder '{item['text']}' should have tooltip"
            )


# ---------------------------------------------------------------------------
# Test: Implemented items enabled when project is open
# ---------------------------------------------------------------------------


class TestImplementedItemsProjectOpen:
    """Requirement 1.7 (implied): Implemented items enabled with open project."""

    def test_implemented_items_enabled(self, menu_project_open) -> None:
        _, menu, _bar = menu_project_open
        all_actions = _collect_all_actions(menu)
        implemented = [a for a in all_actions if a["text"] in _IMPLEMENTED_LABELS]
        assert len(implemented) == len(_IMPLEMENTED_LABELS)
        for item in implemented:
            assert item["enabled"], (
                f"Implemented '{item['text']}' should be enabled"
            )

    def test_implemented_items_no_placeholder_tooltip(self, menu_project_open) -> None:
        _, menu, _bar = menu_project_open
        all_actions = _collect_all_actions(menu)
        implemented = [a for a in all_actions if a["text"] in _IMPLEMENTED_LABELS]
        for item in implemented:
            assert item["tooltip"] != _PLACEHOLDER_TOOLTIP, (
                f"Implemented '{item['text']}' should NOT have placeholder tooltip"
            )


# ---------------------------------------------------------------------------
# Test: All items disabled when no project is open
# ---------------------------------------------------------------------------


class TestNoProjectOpen:
    """Requirement 1.10: All items disabled when no project open."""

    def test_all_items_disabled(self, menu_project_closed) -> None:
        _, menu, _bar = menu_project_closed
        all_actions = _collect_all_actions(menu)
        for item in all_actions:
            assert not item["enabled"], (
                f"'{item['text']}' should be disabled when no project open"
            )

    def test_implemented_items_no_placeholder_tooltip_when_no_project(
        self, menu_project_closed
    ) -> None:
        """Requirement 1.11: Implemented items do NOT have placeholder tooltip."""
        _, menu, _bar = menu_project_closed
        all_actions = _collect_all_actions(menu)
        implemented = [a for a in all_actions if a["text"] in _IMPLEMENTED_LABELS]
        for item in implemented:
            assert item["tooltip"] != _PLACEHOLDER_TOOLTIP, (
                f"Implemented '{item['text']}' should NOT have placeholder tooltip when no project"
            )


# ---------------------------------------------------------------------------
# Test: update_project_state toggles correctly
# ---------------------------------------------------------------------------


class TestUpdateProjectState:
    """Verify update_project_state toggles enabled/disabled correctly."""

    def test_open_then_close(self, menu_project_open) -> None:
        builder, _menu, _bar = menu_project_open

        # Initially open: implemented should be enabled
        assert builder.action_ansedel.isEnabled()
        assert builder.action_geographic.isEnabled()
        assert builder.action_media.isEnabled()

        # Close project
        builder.update_project_state(False)
        assert not builder.action_ansedel.isEnabled()
        assert not builder.action_geographic.isEnabled()
        assert not builder.action_media.isEnabled()

    def test_close_then_open(self, menu_project_closed) -> None:
        builder, _menu, _bar = menu_project_closed

        # Initially closed: implemented should be disabled
        assert not builder.action_ansedel.isEnabled()
        assert not builder.action_geographic.isEnabled()
        assert not builder.action_media.isEnabled()

        # Open project
        builder.update_project_state(True)
        assert builder.action_ansedel.isEnabled()
        assert builder.action_geographic.isEnabled()
        assert builder.action_media.isEnabled()

    def test_placeholders_stay_disabled_after_state_change(
        self, menu_project_closed
    ) -> None:
        builder, menu, _bar = menu_project_closed
        builder.update_project_state(True)

        # Placeholders must remain disabled
        all_actions = _collect_all_actions(menu)
        placeholders = [a for a in all_actions if a["text"] in _PLACEHOLDER_LABELS]
        for item in placeholders:
            assert not item["enabled"], (
                f"Placeholder '{item['text']}' should stay disabled after project opens"
            )
