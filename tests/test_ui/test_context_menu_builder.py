"""Unit tests for the ContextMenuBuilder class.

Verifies that context menus are built with the correct actions
in the correct order, and that edge cases are handled properly.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from slaktbusken.ui.context_menu_builder import ContextMenuBuilder


# Ensure QApplication instance exists for widget tests
@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def builder() -> ContextMenuBuilder:
    """Create a ContextMenuBuilder instance."""
    return ContextMenuBuilder()


@pytest.fixture
def parent_widget() -> QWidget:
    """Create a parent widget for the menu."""
    return QWidget()


class TestContextMenuBuilder:
    """Tests for the ContextMenuBuilder.build_person_menu method."""

    def test_menu_has_seven_actions(
        self, builder: ContextMenuBuilder, parent_widget: QWidget
    ) -> None:
        """The menu should contain exactly 9 entries (7 actions + separator + delete)."""
        menu = builder.build_person_menu("person_1", "main_1", parent_widget)
        actions = menu.actions()
        assert len(actions) == 9

    def test_action_order(
        self, builder: ContextMenuBuilder, parent_widget: QWidget
    ) -> None:
        """Actions must appear in the specified order per requirement 7.1."""
        menu = builder.build_person_menu("person_1", "main_1", parent_widget)
        actions = menu.actions()

        expected_labels = [
            "Gör aktuell",
            "Redigera person",
            "Ny partner",
            "Ny pappa",
            "Ny mamma",
            "Nytt barn",
            "Visa släktskap med huvudpersonen",
            "",  # separator
            "Ta bort person",
        ]
        actual_labels = [action.text() for action in actions]
        assert actual_labels == expected_labels

    def test_actions_have_data_with_person_id(
        self, builder: ContextMenuBuilder, parent_widget: QWidget
    ) -> None:
        """Each non-separator action should carry data containing the person_id."""
        person_id = "person_42"
        menu = builder.build_person_menu(person_id, "main_1", parent_widget)
        actions = menu.actions()

        for action in actions:
            if action.isSeparator():
                continue
            data = action.data()
            assert data is not None
            assert data[1] == person_id

    def test_action_data_types(
        self, builder: ContextMenuBuilder, parent_widget: QWidget
    ) -> None:
        """Each non-separator action should carry a tuple of (action_type, person_id)."""
        menu = builder.build_person_menu("person_1", "main_1", parent_widget)
        actions = menu.actions()

        expected_types = [
            "make_active",
            "edit_person",
            "new_partner",
            "new_father",
            "new_mother",
            "new_child",
            "show_relationship",
            "delete_person",
        ]
        actual_types = [action.data()[0] for action in actions if not action.isSeparator()]
        assert actual_types == expected_types

    def test_menu_parent_is_correct(
        self, builder: ContextMenuBuilder, parent_widget: QWidget
    ) -> None:
        """The menu should be parented to the provided widget."""
        menu = builder.build_person_menu("person_1", "main_1", parent_widget)
        assert menu.parent() == parent_widget

    def test_menu_with_none_main_person_id(
        self, builder: ContextMenuBuilder, parent_widget: QWidget
    ) -> None:
        """Menu should build correctly even when main_person_id is None."""
        menu = builder.build_person_menu("person_1", None, parent_widget)
        actions = menu.actions()
        assert len(actions) == 9

    @patch("slaktbusken.ui.context_menu_builder.QMessageBox.information")
    def test_show_relationship_same_as_main_shows_message(
        self,
        mock_info,
        builder: ContextMenuBuilder,
        parent_widget: QWidget,
    ) -> None:
        """When clicked person is main person, show info message (req 7.10)."""
        person_id = "person_main"
        menu = builder.build_person_menu(person_id, person_id, parent_widget)

        # Trigger the "Visa släktskap" action
        actions = menu.actions()
        relationship_action = actions[6]  # Last action
        relationship_action.trigger()

        mock_info.assert_called_once_with(
            parent_widget,
            "Släktskap",
            "Vald person är redan huvudpersonen.",
        )

    @patch("slaktbusken.ui.context_menu_builder.QMessageBox.information")
    def test_show_relationship_different_person_no_message(
        self,
        mock_info,
        builder: ContextMenuBuilder,
        parent_widget: QWidget,
    ) -> None:
        """When clicked person is not main person, no info message shown."""
        menu = builder.build_person_menu("person_2", "person_main", parent_widget)

        # Trigger the "Visa släktskap" action
        actions = menu.actions()
        relationship_action = actions[6]
        relationship_action.trigger()

        mock_info.assert_not_called()

    @patch("slaktbusken.ui.context_menu_builder.QMessageBox.information")
    def test_show_relationship_none_main_person_no_message(
        self,
        mock_info,
        builder: ContextMenuBuilder,
        parent_widget: QWidget,
    ) -> None:
        """When main_person_id is None, no info message shown."""
        menu = builder.build_person_menu("person_1", None, parent_widget)

        actions = menu.actions()
        relationship_action = actions[6]
        relationship_action.trigger()

        mock_info.assert_not_called()
