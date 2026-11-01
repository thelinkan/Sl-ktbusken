"""Context menu builder for person-related actions.

Provides a reusable builder that creates a standard QMenu with
person actions for use in DiagramPanel and PersonListPanel.
"""

from __future__ import annotations

import logging
from typing import Optional, Sequence

from PySide6.QtWidgets import QMenu, QMessageBox, QWidget

from slaktbusken.services.comparison_session import menu_state

logger = logging.getLogger(__name__)

COMPARE_ACTION = "compare_persons"
MARK_CANDIDATES_ACTION = "mark_candidates"


def merge_action_ids(action) -> Optional[tuple[str, list[str]]]:
    """Return ``(kind, ids)`` for a merge menu action, else None."""
    data = action.data() if action is not None else None
    if (
        isinstance(data, tuple)
        and len(data) == 2
        and data[0] in (COMPARE_ACTION, MARK_CANDIDATES_ACTION)
    ):
        return data[0], list(data[1])
    return None


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
        selected_ids: Optional[Sequence[str]] = None,
        project_open: bool = True,
    ) -> QMenu:
        """Create a QMenu with standard person actions.

        ``selected_ids`` are the selected person ids in person-list order
        (default None: the merge entries are not added). They decide the enablement of the
        "Jämför personer..." and "Markera som sammanslagningskandidater"
        entries; both are disabled while no project is open.

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

        # Action: Filtrera på DNA-träffar
        action_dna_filter = menu.addAction("Filtrera på DNA-träffar")
        action_dna_filter.setData(("filter_dna_matches", person_id))

        # Action: Visa på karta
        action_show_map = menu.addAction("Visa på karta")
        action_show_map.setData(("show_on_map", person_id))

        # Per-connection parentage override actions (Requirement 5.4).
        #
        # The design calls for a context action "on a child's parent
        # connection" to set/clear ProjectData.connection_overrides[child_id].
        # Hit-testing the thin ConnectionLineItem is unreliable and the panel's
        # right-click path is built around PersonBoxItem, so the robust,
        # codebase-consistent realization is to attach the four override actions
        # to the PERSON menu: the right-clicked person is treated as the child
        # whose parent connection is being overridden. The actions live in a
        # dedicated submenu to avoid cluttering the top-level menu.
        override_menu = menu.addMenu("Visa föräldratyp")

        action_override_bio = override_menu.addAction("Visa biologiska föräldrar")
        action_override_bio.setData(("override_biological", person_id))

        action_override_foster = override_menu.addAction("Visa fosterföräldrar")
        action_override_foster.setData(("override_foster", person_id))

        action_override_adoptive = override_menu.addAction("Visa adoptivföräldrar")
        action_override_adoptive.setData(("override_adoptive", person_id))

        action_override_clear = override_menu.addAction("Återställ till standard")
        action_override_clear.setData(("override_clear", person_id))

        # Merge entry points (Req 8.4 to 8.7). These only open the
        # comparison or the candidate editor; they never start a merge.
        if selected_ids is not None:
            ids = list(selected_ids)
            state = menu_state(len(ids))
            menu.addSeparator()
            action_compare = menu.addAction("Jämför personer...")
            action_compare.setData((COMPARE_ACTION, tuple(ids)))
            action_compare.setEnabled(project_open and state.compare_enabled)
            action_mark = menu.addAction("Markera som sammanslagningskandidater")
            action_mark.setData((MARK_CANDIDATES_ACTION, tuple(ids)))
            action_mark.setEnabled(
                project_open and state.mark_candidates_enabled
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
