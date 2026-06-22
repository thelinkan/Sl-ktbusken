"""Context menu builder for person-related actions.

Provides a reusable builder that creates a standard QMenu with
person actions for use in DiagramPanel and PersonListPanel.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtWidgets import QMenu, QMessageBox, QWidget

logger = logging.getLogger(__name__)


class ContextMenuBuilder:
    """Builds the standard person context menu.

    Creates a QMenu with the following actions in order:
    Gör aktuell, Redigera person, Ny partner, Ny pappa,
    Ny mamma, Nytt barn, Visa släktskap med huvudpersonen.
    """

    def build_person_menu(
        self,
        person_id: str,
        main_person_id: Optional[str],
        parent_widget: QWidget,
    ) -> QMenu:
        """Create a QMenu with standard person actions.

        Actions are added in the order specified by requirement 7.1:
        Gör aktuell, Redigera person, Ny partner, Ny pappa,
        Ny mamma, Nytt barn, Visa släktskap med huvudpersonen.

        The "Visa släktskap med huvudpersonen" action handles the edge
        case where the clicked person is the main person by showing
        an info message instead of invoking the relationship calculator.

        Args:
            person_id: The ID of the right-clicked person.
            main_person_id: The ID of the current main person, or None.
            parent_widget: The parent widget for the menu (used for
                positioning and as parent for any dialogs).

        Returns:
            A QMenu ready to be shown via exec().
        """
        menu = QMenu(parent_widget)

        # Action: Gör aktuell
        action_make_active = menu.addAction("Gör aktuell")
        action_make_active.setData(("make_active", person_id))

        # Action: Redigera person
        action_edit = menu.addAction("Redigera person")
        action_edit.setData(("edit_person", person_id))

        # Action: Ny partner
        action_new_partner = menu.addAction("Ny partner")
        action_new_partner.setData(("new_partner", person_id))

        # Action: Ny pappa
        action_new_father = menu.addAction("Ny pappa")
        action_new_father.setData(("new_father", person_id))

        # Action: Ny mamma
        action_new_mother = menu.addAction("Ny mamma")
        action_new_mother.setData(("new_mother", person_id))

        # Action: Nytt barn
        action_new_child = menu.addAction("Nytt barn")
        action_new_child.setData(("new_child", person_id))

        # Action: Visa släktskap med huvudpersonen
        action_show_relationship = menu.addAction(
            "Visa släktskap med huvudpersonen"
        )
        action_show_relationship.setData(("show_relationship", person_id))

        # Connect the relationship action to handle the edge case
        # where the clicked person is the main person (requirement 7.10)
        action_show_relationship.triggered.connect(
            lambda: self._handle_show_relationship(
                person_id, main_person_id, parent_widget
            )
        )

        # Separator before destructive action
        menu.addSeparator()

        # Action: Ta bort person
        action_delete = menu.addAction("Ta bort person")
        action_delete.setData(("delete_person", person_id))

        return menu

    def _handle_show_relationship(
        self,
        person_id: str,
        main_person_id: Optional[str],
        parent_widget: QWidget,
    ) -> None:
        """Handle the 'Visa släktskap med huvudpersonen' action.

        If the clicked person is the main person, shows an info message.
        Otherwise the action data can be handled by the caller.

        Args:
            person_id: The ID of the right-clicked person.
            main_person_id: The ID of the current main person.
            parent_widget: Parent widget for the message box.
        """
        if person_id == main_person_id:
            QMessageBox.information(
                parent_widget,
                "Släktskap",
                "Vald person är redan huvudpersonen.",
            )
