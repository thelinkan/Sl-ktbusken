"""Report menu builder for the Rapporter top-level menu.

Builds the "Rapporter" menu with five category submenus and all report items.
Three reports are implemented (Ansedel, Geografisk konsistens, Mediakonsistens);
the rest are disabled placeholders with a Swedish tooltip.

When no project is open, all items (including implemented ones) are disabled,
but implemented items do NOT show the placeholder tooltip.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QMenuBar

if TYPE_CHECKING:
    from slaktbusken.app import Application

logger = logging.getLogger(__name__)

# Swedish tooltip shown on placeholder (not-yet-implemented) items
_PLACEHOLDER_TOOLTIP = "Rapporten är inte implementerad ännu"


class ReportMenuBuilder:
    """Builds the Rapporter menu and manages item enabled states.

    After calling :meth:`build`, the builder stores references to:
    - The three implemented report actions (ansedel, geographic, media)
    - All placeholder actions (always disabled regardless of project state)

    Call :meth:`update_project_state` when a project is opened or closed
    to toggle enabled/disabled state on implemented items.
    """

    def __init__(self) -> None:
        # Implemented report actions (enabled when project is open)
        self.action_ansedel: QAction | None = None
        self.action_geographic: QAction | None = None
        self.action_media: QAction | None = None

        # All placeholder actions (always disabled)
        self._placeholder_actions: list[QAction] = []

        # The top-level menu reference
        self.menu: QMenu | None = None

    def build(self, menu_bar: QMenuBar, app: "Application") -> QMenu:
        """Build and return the Rapporter top-level menu.

        Creates five category submenus with all report items. Implemented
        items have their ``triggered`` signal available for external
        connection. Placeholder items are disabled with a tooltip.

        Args:
            menu_bar: The application's menu bar to add the menu to.
            app: The Application instance (used to determine initial state).

        Returns:
            The created "Rapporter" QMenu.
        """
        self.menu = menu_bar.addMenu("&Rapporter")

        # --- Standardrapporter ---
        menu_standard = self.menu.addMenu("Standardrapporter")
        self.action_ansedel = menu_standard.addAction("Ansedel")
        self._add_placeholder(menu_standard, "Antavla")
        self._add_placeholder(menu_standard, "Ättlingarapport")

        # --- DNA-rapporter ---
        menu_dna = self.menu.addMenu("DNA-rapporter")
        self._add_placeholder(menu_dna, "DNA-matchlista")
        self._add_placeholder(menu_dna, "Klusterrapport")
        self._add_placeholder(menu_dna, "Trianguleringsrapport")

        # --- Konsistensrapporter ---
        menu_consistency = self.menu.addMenu("Konsistensrapporter")
        self.action_geographic = menu_consistency.addAction(
            "Geografisk konsistens"
        )
        self._add_placeholder(menu_consistency, "Personkonsistens")
        self._add_placeholder(menu_consistency, "Familjekonsistens")
        self.action_media = menu_consistency.addAction("Mediakonsistens")
        self._add_placeholder(menu_consistency, "Källkonsistens")

        # --- Forskningsrapporter ---
        menu_research = self.menu.addMenu("Forskningsrapporter")
        self._add_placeholder(menu_research, "Öppna forskningsfrågor")
        self._add_placeholder(menu_research, "Personer med saknade källor")

        # --- Exportkontroller ---
        menu_export = self.menu.addMenu("Exportkontroller")
        self._add_placeholder(menu_export, "ArkivDigital-export")
        self._add_placeholder(menu_export, "GEDCOM-export")

        # Set initial state based on whether a project is open
        project_open = app.project_service.project_path is not None
        self.update_project_state(project_open)

        return self.menu

    def update_project_state(self, project_open: bool) -> None:
        """Update enabled/disabled state of menu items based on project state.

        When a project is open, implemented items are enabled and
        placeholders remain disabled with their tooltip.

        When no project is open, ALL items are disabled. Implemented
        items do NOT get the placeholder tooltip.

        Args:
            project_open: True if a project is currently open.
        """
        # Implemented actions: enabled only when project is open
        for action in (
            self.action_ansedel,
            self.action_geographic,
            self.action_media,
        ):
            if action is not None:
                action.setEnabled(project_open)
                # Implemented items never show the placeholder tooltip
                # (Requirement 1.11)
                action.setToolTip("")

        # Placeholder actions: always disabled, tooltip only when project
        # is open (so we don't confuse "not implemented" with "no project")
        # Actually per Requirement 1.9: placeholder tooltip is always shown
        # on placeholders. Requirement 1.11 only applies to implemented items.
        # Placeholders are always disabled regardless of project state.
        for action in self._placeholder_actions:
            action.setEnabled(False)
            action.setToolTip(_PLACEHOLDER_TOOLTIP)

    def _add_placeholder(self, menu: QMenu, label: str) -> QAction:
        """Add a disabled placeholder report item to a submenu.

        Args:
            menu: The submenu to add the item to.
            label: The Swedish-language label for the item.

        Returns:
            The created disabled QAction.
        """
        action = menu.addAction(label)
        action.setEnabled(False)
        action.setToolTip(_PLACEHOLDER_TOOLTIP)
        self._placeholder_actions.append(action)
        return action
