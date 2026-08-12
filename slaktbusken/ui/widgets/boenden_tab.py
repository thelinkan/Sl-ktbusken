"""Boenden tab for PersonEditor.

Displays a list of Residence_Facts linked to a person, allows creation
of a new Residence_Fact for the active person, and provides an entry
point to the ResidentsDialog. Follows the FotoTab insertion pattern —
the widget is instantiated programmatically inside the Person editor.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.person import Person
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import Endpoint, ResidenceFact
from slaktbusken.services.residence_query import residence_timeline
from slaktbusken.ui.swedish_locale import format_residence_line


class BoendenTab(QWidget):
    """Residence management tab displaying Boenden linked to a person.

    Shows a list of the person's Residence_Facts rendered with place,
    interval and role, or an empty state message when no residences exist.
    Provides buttons to create a new Residence_Fact and to open the
    ResidentsDialog.

    Signals:
        create_requested: Emitted when the user wants to create a new
            Residence_Fact for this person.
        edit_requested(str): Emitted with the residence id when the user
            wants to edit an existing Residence_Fact.
        residents_dialog_requested: Emitted when the user clicks the
            residents dialog entry point.

    Args:
        project_data: The project data containing all entities.
        person: The person whose residences are displayed.
        parent: Optional parent widget.
    """

    create_requested = Signal()
    edit_requested = Signal(str)
    residents_dialog_requested = Signal()

    def __init__(
        self,
        project_data: ProjectData,
        person: Person,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._project_data = project_data
        self._person = person

        self._setup_ui()
        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Rebuild the residence list from current project data."""
        self._list.clear()
        facts = residence_timeline(self._project_data, self._person.id)

        if not facts:
            self._stack.setCurrentWidget(self._empty_label)
        else:
            self._stack.setCurrentWidget(self._list)
            places_by_id = {p.id: p for p in self._project_data.places}
            for fact in facts:
                place = places_by_id.get(fact.place_id)
                place_display = place.name if place else fact.place_id
                line = format_residence_line(
                    place_display, fact.start, fact.end, fact.role_in_household
                )
                item = QListWidgetItem(line)
                item.setData(Qt.ItemDataRole.UserRole, fact.id)
                self._list.addItem(item)

        self._update_button_states()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Build the tab layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Stack: empty label or the list widget
        self._stack_widget = QWidget()
        self._stack = QStackedLayout(self._stack_widget)

        self._empty_label = QLabel("Inga boenden registrerade.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stack.addWidget(self._empty_label)

        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._stack.addWidget(self._list)

        layout.addWidget(self._stack_widget)

        # Buttons row
        buttons_layout = QHBoxLayout()

        self._add_button = QPushButton("Nytt boende")
        self._add_button.setToolTip(
            "Skapa ett nytt boende för den aktiva personen"
        )
        buttons_layout.addWidget(self._add_button)

        self._edit_button = QPushButton("Redigera boende")
        self._edit_button.setToolTip("Redigera valt boende")
        self._edit_button.setEnabled(False)
        buttons_layout.addWidget(self._edit_button)

        self._residents_button = QPushButton("Boende på plats\u2026")
        self._residents_button.setToolTip(
            "Visa vilka som bodde på en plats ett visst år"
        )
        buttons_layout.addWidget(self._residents_button)

        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)

        # Connect internal signals
        self._add_button.clicked.connect(self._on_create)
        self._edit_button.clicked.connect(self._on_edit)
        self._residents_button.clicked.connect(self._on_residents_dialog)
        self._list.itemSelectionChanged.connect(self._update_button_states)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)

    def _update_button_states(self) -> None:
        """Enable/disable edit button based on selection."""
        has_selection = len(self._list.selectedItems()) > 0
        self._edit_button.setEnabled(has_selection)

    def _on_create(self) -> None:
        """Handle the 'Nytt boende' button click."""
        self.create_requested.emit()

    def _on_edit(self) -> None:
        """Handle the 'Redigera boende' button click."""
        items = self._list.selectedItems()
        if items:
            residence_id = items[0].data(Qt.ItemDataRole.UserRole)
            self.edit_requested.emit(residence_id)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle double-click on a list item to edit."""
        residence_id = item.data(Qt.ItemDataRole.UserRole)
        if residence_id:
            self.edit_requested.emit(residence_id)

    def _on_residents_dialog(self) -> None:
        """Handle the 'Boende på plats' button click."""
        self.residents_dialog_requested.emit()

    # ------------------------------------------------------------------
    # Test helpers
    # ------------------------------------------------------------------

    @property
    def add_button(self) -> QPushButton:
        """The 'Nytt boende' button."""
        return self._add_button

    @property
    def edit_button(self) -> QPushButton:
        """The 'Redigera boende' button."""
        return self._edit_button

    @property
    def residents_button(self) -> QPushButton:
        """The 'Boende på plats' button."""
        return self._residents_button

    @property
    def residence_list(self) -> QListWidget:
        """The list widget showing residences."""
        return self._list

    @property
    def empty_label(self) -> QLabel:
        """The empty state label."""
        return self._empty_label

    @property
    def stack_layout(self) -> QStackedLayout:
        """The stacked layout switching between empty and list."""
        return self._stack
