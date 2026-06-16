"""Place editor widget.

Provides a split-panel editor for Place records: a filterable place list
on the left and a detail form on the right with type, name, parent place,
coordinates, and notes. Enforces the place-type hierarchy and warns before
deleting places referenced by events. All UI text is in Swedish.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem, QMessageBox, QWidget

from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData
from slaktbusken.ui.generated.ui_place_editor import Ui_PlaceEditor

logger = logging.getLogger(__name__)

# Mapping from Swedish UI labels to internal type strings
_TYPE_LABEL_TO_INTERNAL: dict[str, str] = {
    "Land": "country",
    "Län": "county",
    "Socken": "parish",
    "Kyrka": "church",
    "Kyrkogård": "cemetery",
}

_TYPE_INTERNAL_TO_LABEL: dict[str, str] = {v: k for k, v in _TYPE_LABEL_TO_INTERNAL.items()}

# Valid parent types for each place type
_VALID_PARENT_TYPES: dict[str, Optional[str]] = {
    "country": None,
    "county": "country",
    "parish": "county",
    "church": "parish",
    "cemetery": "parish",
}


class PlaceEditor(QWidget):
    """Editor widget for Place records with list/detail split layout.

    Displays a filterable list of all places on the left and an edit form
    on the right. Supports creating new places, editing existing ones,
    and deleting with referential integrity warnings.

    Args:
        project_data: The current project data containing all entities.
        place: Optional existing Place to select initially for editing.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        project_data: ProjectData,
        place: Optional[Place] = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the place editor.

        Args:
            project_data: The current project data containing all entities.
            place: Optional existing Place to select initially for editing.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._project_data = project_data
        self._place = place
        self._saved_place: Optional[Place] = None
        self._editing_place: Optional[Place] = None

        # Set up UI from generated form
        self._ui = Ui_PlaceEditor()
        self._ui.setupUi(self)

        self._connect_signals()
        self._refresh_place_list()

        # If a place was provided, select it in the list
        if self._place is not None:
            self._select_place_in_list(self._place.id)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def saved_place(self) -> Optional[Place]:
        """The saved Place result, or None if not yet saved."""
        return self._saved_place

    def get_place(self) -> Optional[Place]:
        """Return the saved place, or None if save was not performed.

        Returns:
            The Place object if save was successful, None otherwise.
        """
        return self._saved_place

    # ------------------------------------------------------------------
    # Private: setup
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        """Wire up UI signals to handler slots."""
        # Filter
        self._ui.filter_input.textChanged.connect(self._on_filter_changed)

        # List selection
        self._ui.place_list.currentItemChanged.connect(self._on_place_selected)

        # Add / Delete buttons
        self._ui.add_button.clicked.connect(self._on_add_place)
        self._ui.delete_button.clicked.connect(self._on_delete_place)

        # Coordinates checkbox
        self._ui.coordinates_check.toggled.connect(self._on_coordinates_toggled)

        # Type change updates parent combo
        self._ui.type_combo.currentIndexChanged.connect(self._on_type_changed)

        # Save / Cancel
        self._ui.save_button.clicked.connect(self._on_save)
        self._ui.cancel_button.clicked.connect(self._on_cancel)

    # ------------------------------------------------------------------
    # Private: place list management
    # ------------------------------------------------------------------

    def _refresh_place_list(self) -> None:
        """Rebuild the place list from project_data, applying the current filter."""
        filter_text = self._ui.filter_input.text().strip().lower()
        self._ui.place_list.blockSignals(True)
        self._ui.place_list.clear()

        for place in self._project_data.places:
            display = self._format_place_display(place)
            if filter_text and filter_text not in display.lower():
                continue
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, place.id)
            self._ui.place_list.addItem(item)

        self._ui.place_list.blockSignals(False)

    def _format_place_display(self, place: Place) -> str:
        """Format a place for display in the list with hierarchy context.

        Args:
            place: The Place to format.

        Returns:
            Display string with name and parent context.
        """
        type_label = _TYPE_INTERNAL_TO_LABEL.get(place.type, place.type)
        display = f"{place.name} ({type_label})"

        # Show parent name for context
        if place.parent_place_id:
            parent = self._find_place_by_id(place.parent_place_id)
            if parent:
                display += f" — {parent.name}"

        return display

    def _find_place_by_id(self, place_id: str) -> Optional[Place]:
        """Find a place by its ID in the project data.

        Args:
            place_id: The place ID to search for.

        Returns:
            The Place if found, None otherwise.
        """
        for p in self._project_data.places:
            if p.id == place_id:
                return p
        return None

    def _select_place_in_list(self, place_id: str) -> None:
        """Select a place in the list by its ID.

        Args:
            place_id: The ID of the place to select.
        """
        for i in range(self._ui.place_list.count()):
            item = self._ui.place_list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == place_id:
                self._ui.place_list.setCurrentItem(item)
                return

    def _on_filter_changed(self, text: str) -> None:
        """Handle filter text changes by refreshing the place list.

        Args:
            text: The new filter text.
        """
        self._refresh_place_list()

    # ------------------------------------------------------------------
    # Private: place selection and form population
    # ------------------------------------------------------------------

    def _on_place_selected(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]) -> None:
        """Handle place list selection change.

        Args:
            current: The newly selected item.
            previous: The previously selected item.
        """
        if current is None:
            self._clear_form()
            self._editing_place = None
            return

        place_id = current.data(Qt.ItemDataRole.UserRole)
        place = self._find_place_by_id(place_id)
        if place is None:
            self._clear_form()
            self._editing_place = None
            return

        self._editing_place = place
        self._load_place_to_form(place)

    def _load_place_to_form(self, place: Place) -> None:
        """Populate the edit form with data from a Place.

        Args:
            place: The Place to load into the form.
        """
        # Type
        type_label = _TYPE_INTERNAL_TO_LABEL.get(place.type, "Land")
        type_index = self._ui.type_combo.findText(type_label)
        if type_index >= 0:
            self._ui.type_combo.setCurrentIndex(type_index)

        # Name
        self._ui.name_input.setText(place.name)

        # Parent - populate combo first based on type
        self._populate_parent_combo(place.type)
        if place.parent_place_id:
            parent = self._find_place_by_id(place.parent_place_id)
            if parent:
                parent_index = self._ui.parent_combo.findData(parent.id)
                if parent_index >= 0:
                    self._ui.parent_combo.setCurrentIndex(parent_index)

        # Coordinates
        has_coords = place.latitude is not None and place.longitude is not None
        self._ui.coordinates_check.setChecked(has_coords)
        self._ui.latitude_spin.setEnabled(has_coords)
        self._ui.longitude_spin.setEnabled(has_coords)
        if has_coords:
            self._ui.latitude_spin.setValue(place.latitude)  # type: ignore[arg-type]
            self._ui.longitude_spin.setValue(place.longitude)  # type: ignore[arg-type]
        else:
            self._ui.latitude_spin.setValue(0.0)
            self._ui.longitude_spin.setValue(0.0)

        # Notes
        self._ui.notes_input.setPlainText(place.notes)

        self._clear_status()

    def _clear_form(self) -> None:
        """Reset all form fields to their default empty state."""
        self._ui.type_combo.setCurrentIndex(0)
        self._ui.name_input.clear()
        self._ui.parent_combo.clear()
        self._ui.coordinates_check.setChecked(False)
        self._ui.latitude_spin.setValue(0.0)
        self._ui.longitude_spin.setValue(0.0)
        self._ui.latitude_spin.setEnabled(False)
        self._ui.longitude_spin.setEnabled(False)
        self._ui.notes_input.clear()
        self._clear_status()

    # ------------------------------------------------------------------
    # Private: parent combo population with hierarchy enforcement
    # ------------------------------------------------------------------

    def _populate_parent_combo(self, place_type: str) -> None:
        """Populate parent combo with valid parent places based on type hierarchy.

        Args:
            place_type: The internal type string of the current place.
        """
        self._ui.parent_combo.clear()
        self._ui.parent_combo.addItem("(Ingen)", "")

        required_parent_type = _VALID_PARENT_TYPES.get(place_type)
        if required_parent_type is None:
            # country has no parent
            return

        for p in self._project_data.places:
            if p.type == required_parent_type:
                # Don't allow a place to be its own parent
                if self._editing_place and p.id == self._editing_place.id:
                    continue
                display = p.name
                self._ui.parent_combo.addItem(display, p.id)

    def _on_type_changed(self, index: int) -> None:
        """Handle type combo change to update parent combo options.

        Args:
            index: The new index in the type combo.
        """
        type_label = self._ui.type_combo.currentText()
        internal_type = _TYPE_LABEL_TO_INTERNAL.get(type_label, "country")
        self._populate_parent_combo(internal_type)

    # ------------------------------------------------------------------
    # Private: coordinates toggle
    # ------------------------------------------------------------------

    def _on_coordinates_toggled(self, checked: bool) -> None:
        """Enable or disable coordinate spin boxes.

        Args:
            checked: Whether coordinates should be enabled.
        """
        self._ui.latitude_spin.setEnabled(checked)
        self._ui.longitude_spin.setEnabled(checked)

    # ------------------------------------------------------------------
    # Private: add / delete
    # ------------------------------------------------------------------

    def _on_add_place(self) -> None:
        """Prepare the form for creating a new place."""
        self._ui.place_list.clearSelection()
        self._editing_place = None
        self._clear_form()
        self._ui.name_input.setFocus()

    def _on_delete_place(self) -> None:
        """Delete the currently selected place with referential integrity check."""
        current = self._ui.place_list.currentItem()
        if current is None:
            self._update_status("Välj en plats att ta bort.")
            return

        place_id = current.data(Qt.ItemDataRole.UserRole)
        place = self._find_place_by_id(place_id)
        if place is None:
            return

        # Check for referencing events
        referencing_events = self._find_referencing_events(place_id)
        if referencing_events:
            event_lines: list[str] = []
            for e in referencing_events:
                parts = [e.type]
                if e.date:
                    parts.append(e.date.value)
                if e.participants:
                    participant_names = ", ".join(
                        p.person_id for p in e.participants
                    )
                    parts.append(participant_names)
                event_lines.append(f"  • {' — '.join(parts)}")
            event_list = "\n".join(event_lines)
            reply = QMessageBox.warning(
                self,
                "Varning",
                f"Denna plats refereras av följande händelser:\n\n"
                f"{event_list}\n\n"
                "Vill du verkligen ta bort platsen?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Remove from project data
        self._project_data.places = [
            p for p in self._project_data.places if p.id != place_id
        ]

        self._editing_place = None
        self._clear_form()
        self._refresh_place_list()
        self._clear_status()
        logger.info("Plats borttagen: %s", place_id)

    def _find_referencing_events(self, place_id: str) -> list:
        """Find all events that reference a given place.

        Args:
            place_id: The place ID to search for.

        Returns:
            List of Event objects referencing this place.
        """
        referencing = []
        for event in self._project_data.events:
            if event.place and event.place.place_id == place_id:
                referencing.append(event)
        return referencing

    # ------------------------------------------------------------------
    # Private: save / cancel
    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        """Validate and save the place data.

        Validates that name is 1-200 chars, type is set, and hierarchy is valid.
        On success, stores the result in saved_place.
        """
        # Get type
        type_label = self._ui.type_combo.currentText()
        internal_type = _TYPE_LABEL_TO_INTERNAL.get(type_label, "country")

        # Validate name
        name = self._ui.name_input.text().strip()
        if not name:
            self._update_status("Namn krävs (1–200 tecken).")
            return
        if len(name) > 200:
            self._update_status("Namn får vara högst 200 tecken.")
            return

        # Parent place
        parent_place_id: Optional[str] = None
        parent_data = self._ui.parent_combo.currentData()
        if parent_data:
            parent_place_id = parent_data

        # Validate hierarchy
        required_parent_type = _VALID_PARENT_TYPES.get(internal_type)
        if required_parent_type is not None and not parent_place_id:
            parent_type_label = _TYPE_INTERNAL_TO_LABEL.get(required_parent_type, required_parent_type)
            self._update_status(
                f"En plats av typen \"{type_label}\" kräver en överordnad plats av typen \"{parent_type_label}\"."
            )
            return

        if parent_place_id and required_parent_type is not None:
            parent_place = self._find_place_by_id(parent_place_id)
            if parent_place and parent_place.type != required_parent_type:
                parent_type_label = _TYPE_INTERNAL_TO_LABEL.get(required_parent_type, required_parent_type)
                self._update_status(
                    f"Överordnad plats måste vara av typen \"{parent_type_label}\"."
                )
                return

        # Coordinates
        latitude: Optional[float] = None
        longitude: Optional[float] = None
        if self._ui.coordinates_check.isChecked():
            latitude = self._ui.latitude_spin.value()
            longitude = self._ui.longitude_spin.value()

        # Notes
        notes = self._ui.notes_input.toPlainText()

        # Determine place ID
        place_id = self._editing_place.id if self._editing_place else str(uuid.uuid4())

        self._saved_place = Place(
            id=place_id,
            type=internal_type,
            name=name,
            parent_place_id=parent_place_id,
            latitude=latitude,
            longitude=longitude,
            notes=notes,
        )

        self._clear_status()
        logger.info("Plats sparad: %s (%s)", name, place_id)
        self.close()

    def _on_cancel(self) -> None:
        """Close the editor without saving."""
        self._saved_place = None
        self.close()

    # ------------------------------------------------------------------
    # Private: helpers
    # ------------------------------------------------------------------

    def _update_status(self, message: str) -> None:
        """Update the status label text with an error/info message.

        Args:
            message: The status message to display.
        """
        self._ui.status_label.setText(message)

    def _clear_status(self) -> None:
        """Clear the status label."""
        self._ui.status_label.setText("")
