"""Place translation editor widget.

Provides a searchable list of GEDCOM→App_JSON place mappings with
add/edit/remove/save functionality and place hierarchy visualization.
Validates that target App_JSON place records exist before persisting
changes. Supports creating new App_JSON Place records directly from
unmapped GEDCOM place strings. All UI text is in Swedish.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.id_generator import IDGenerator
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData
from slaktbusken.persistence.translation_io import PlaceMapping, TranslationData
from slaktbusken.services.translation_service import (
    TranslationService,
    TranslationServiceError,
)
from slaktbusken.ui.generated.ui_place_translation_editor import (
    Ui_PlaceTranslationEditor,
)

logger = logging.getLogger(__name__)

# Valid place types in hierarchy order (most specific → least specific)
_PLACE_TYPES = ["church", "cemetery", "parish", "county", "country"]
_PLACE_TYPE_LABELS = {
    "country": "Land",
    "county": "Län",
    "parish": "Församling",
    "church": "Kyrka",
    "cemetery": "Kyrkogård",
}


class CreatePlaceDialog(QDialog):
    """Dialog for creating new App_JSON Place records from a GEDCOM place string.

    Parses the comma-separated GEDCOM place string and intelligently
    matches each part against existing places. Shows the full hierarchy
    and lets the user create all missing intermediate levels in one step.

    For example, "Mora, Kopparbergs län, Sverige" would show:
      - Mora (Församling) — NY
      - Kopparbergs län (Län) — NY
      - Sverige (Land) — ✓ finns redan

    The user can adjust types and names before confirming. All missing
    places are created with correct parent links.

    Args:
        gedcom_place_string: The GEDCOM place string to parse.
        existing_places: List of existing places for matching.
        place_by_id: Lookup dict for hierarchy resolution.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        gedcom_place_string: str,
        existing_places: list[Place],
        place_by_id: dict[str, Place],
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the create place dialog.

        Args:
            gedcom_place_string: The GEDCOM place string (comma-separated).
            existing_places: All existing places for matching.
            place_by_id: Dict for hierarchy resolution.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("Skapa platser från GEDCOM-sträng")
        self.setMinimumWidth(600)

        self._place_by_id = place_by_id
        self._existing_places = existing_places
        self._created_places: list[Place] = []

        # Parse GEDCOM string: parts go from most specific to least specific
        self._parts = [p.strip() for p in gedcom_place_string.split(",") if p.strip()]

        # Guess types based on position (most specific → least specific)
        self._guessed_types = self._guess_types(self._parts)

        # Try to match each part to an existing place
        self._matches: list[Place | None] = [
            self._find_matching_place(part) for part in self._parts
        ]

        layout = QVBoxLayout(self)

        # Info
        info = QLabel(
            f"GEDCOM-platssträng: \"{gedcom_place_string}\"\n\n"
            "Följande platshierarki tolkas. Markerade platser (NY) "
            "kommer att skapas. Befintliga platser återanvänds."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # Build the hierarchy table
        from PySide6.QtWidgets import QGridLayout, QGroupBox

        group = QGroupBox("Platshierarki (mest specifik → minst specifik)")
        grid = QGridLayout(group)

        # Column headers
        grid.addWidget(QLabel("<b>Namn</b>"), 0, 0)
        grid.addWidget(QLabel("<b>Typ</b>"), 0, 1)
        grid.addWidget(QLabel("<b>Status</b>"), 0, 2)

        self._name_inputs: list[QLineEdit] = []
        self._type_combos: list[QComboBox] = []
        self._status_labels: list[QLabel] = []

        for i, part in enumerate(self._parts):
            row = i + 1
            match = self._matches[i]

            # Name input
            name_input = QLineEdit(part)
            name_input.setMaxLength(200)
            if match:
                name_input.setReadOnly(True)
                name_input.setStyleSheet("background-color: #f0f0f0;")
            self._name_inputs.append(name_input)
            grid.addWidget(name_input, row, 0)

            # Type combo
            type_combo = QComboBox()
            for type_key in _PLACE_TYPES:
                type_combo.addItem(_PLACE_TYPE_LABELS[type_key], type_key)
            guessed = self._guessed_types[i]
            if guessed in _PLACE_TYPES:
                type_combo.setCurrentIndex(_PLACE_TYPES.index(guessed))
            if match:
                # Lock the type for existing places
                idx = _PLACE_TYPES.index(match.type) if match.type in _PLACE_TYPES else 0
                type_combo.setCurrentIndex(idx)
                type_combo.setEnabled(False)
            self._type_combos.append(type_combo)
            grid.addWidget(type_combo, row, 1)

            # Status label
            if match:
                status = QLabel(f"✓ Finns ({match.id})")
                status.setStyleSheet("color: green;")
            else:
                status = QLabel("⊕ NY")
                status.setStyleSheet("color: #cc6600; font-weight: bold;")
            self._status_labels.append(status)
            grid.addWidget(status, row, 2)

        layout.addWidget(group)

        # Preview
        self._preview_label = QLabel("")
        self._preview_label.setStyleSheet("color: #555; font-style: italic;")
        self._preview_label.setWordWrap(True)
        layout.addWidget(self._preview_label)
        self._update_preview()

        # Connect name changes to preview update
        for name_input in self._name_inputs:
            name_input.textChanged.connect(self._update_preview)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Skapa platser")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Avbryt")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def created_places(self) -> list[Place]:
        """The new Place records created by this dialog (empty if cancelled).

        Places are ordered from least specific (e.g. country) to most
        specific (e.g. church) so the caller can add them in order and
        parent references resolve correctly.
        """
        return self._created_places

    @property
    def leaf_place(self) -> Place | None:
        """The most specific place (first in the GEDCOM string).

        This is the place that should be used as the mapping target.
        Could be a newly created place or an existing one.
        """
        if self._created_places:
            # Most specific is last in reversed list (we return least→most)
            return self._created_places[-1]
        # If no new places were created, the first part matched an existing one
        return self._matches[0] if self._matches else None

    def _guess_types(self, parts: list[str]) -> list[str]:
        """Guess place types from position and Swedish naming conventions.

        In Swedish GEDCOM, the order is typically:
        church/parish, parish/county, county, country

        Args:
            parts: The comma-separated parts (most specific first).

        Returns:
            List of guessed type strings, same length as parts.
        """
        n = len(parts)
        if n == 0:
            return []

        types: list[str] = []
        for i, part in enumerate(parts):
            lower = part.lower()
            # Try to detect by name patterns
            if any(kw in lower for kw in ("kyrka", "kirke", "church")):
                types.append("church")
            elif any(kw in lower for kw in ("kyrkogård", "cemetery", "begravningsplats")):
                types.append("cemetery")
            elif any(kw in lower for kw in ("län",)):
                types.append("county")
            elif any(kw in lower for kw in ("sverige", "norway", "finland", "denmark")):
                types.append("country")
            else:
                # Positional heuristic
                if i == n - 1:
                    types.append("country")
                elif i == n - 2:
                    types.append("county")
                else:
                    types.append("parish")

        return types

    def _find_matching_place(self, name: str) -> Place | None:
        """Find an existing place by exact name match (case-insensitive).

        Args:
            name: The place name to search for.

        Returns:
            The matching Place, or None if not found.
        """
        lower = name.lower()
        for place in self._existing_places:
            if place.name.lower() == lower:
                return place
        return None

    def _update_preview(self) -> None:
        """Update the hierarchy preview text."""
        names = [inp.text().strip() or "?" for inp in self._name_inputs]
        # Show as hierarchy: most specific → least specific
        self._preview_label.setText(
            "Resulterande hierarki: " + " → ".join(names)
        )

    def _on_accept(self) -> None:
        """Validate inputs and build the list of new Place objects.

        New places are returned in order from least specific to most
        specific. For new→new parent chains, ``parent_place_id`` is set
        to a sentinel string ``"__new:<name>"`` that the caller resolves
        after assigning real IDs.
        """
        # Validate: all names must be non-empty
        for i, name_input in enumerate(self._name_inputs):
            if not name_input.text().strip():
                QMessageBox.warning(
                    self, "Fel", f"Rad {i + 1}: Ange ett platsnamn."
                )
                return

        # Build places from least specific (end of list) to most specific (start).
        new_places: list[Place] = []

        for i in range(len(self._parts) - 1, -1, -1):
            if self._matches[i] is not None:
                # Already exists, skip
                continue

            name = self._name_inputs[i].text().strip()
            place_type = self._type_combos[i].currentData()

            # Determine parent_place_id
            parent_id: str | None = None
            if i + 1 < len(self._parts):
                if self._matches[i + 1]:
                    # Parent exists in the project
                    parent_id = self._matches[i + 1].id
                else:
                    # Parent is also new — use sentinel for caller to resolve
                    parent_name = self._name_inputs[i + 1].text().strip()
                    parent_id = f"__new:{parent_name}"

            new_place = Place(
                id="",  # Caller assigns real ID
                type=place_type,
                name=name,
                parent_place_id=parent_id,
            )
            new_places.append(new_place)

        self._created_places = new_places
        self.accept()


class PlaceTranslationEditor(QWidget):
    """Editor widget for GEDCOM place → App_JSON place translation mappings.

    Displays a searchable table of existing place mappings with hierarchy
    context and provides controls to add, edit, and remove entries.
    Validates that the target App_JSON place exists in the project before
    saving.

    Also shows unmapped GEDCOM place strings (those without an App_JSON
    target) and lets the user create new Place records directly to map
    them.

    Signals:
        place_created: Emitted when a new Place is created from this
            editor. The signal carries the new Place instance so the
            caller can persist it to the project.

    Args:
        translation_service: Service for loading/saving translation files.
        project_data: The current project data containing available places.
        project_path: Path to the project file or directory.
        parent: Optional parent widget.
    """

    place_created = Signal(object)  # Emits the new Place instance

    def __init__(
        self,
        translation_service: TranslationService,
        project_data: ProjectData,
        project_path: Path,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the place translation editor.

        Args:
            translation_service: Service for loading/saving translation files.
            project_data: The current project data containing available places.
            project_path: Path to the project file or directory.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._translation_service = translation_service
        self._project_data = project_data
        self._project_path = project_path

        self._translation_data: TranslationData | None = None
        self._dirty: bool = False

        # Build a lookup dict for fast place resolution
        self._place_by_id: dict[str, Place] = {
            p.id: p for p in self._project_data.places
        }

        # ID generator for creating new places
        existing_ids = {p.id for p in self._project_data.places}
        self._id_generator = IDGenerator(existing_ids)

        # Set up UI from generated form
        self._ui = Ui_PlaceTranslationEditor()
        self._ui.setupUi(self)

        self._setup_table()
        self._populate_place_combo()
        self._connect_signals()
        self._add_create_button()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_dirty(self) -> bool:
        """Whether the editor has unsaved changes."""
        return self._dirty

    def load_data(self) -> None:
        """Load translation data from disk and populate the mapping table.

        Raises:
            TranslationServiceError: If the translation files cannot be read.
        """
        self._translation_data = self._translation_service.load_translations(
            self._project_path
        )
        self._refresh_table()
        self._dirty = False
        self._update_status("")

    # ------------------------------------------------------------------
    # Private: setup
    # ------------------------------------------------------------------

    def _setup_table(self) -> None:
        """Configure the mapping table appearance."""
        table = self._ui.mapping_table
        table.setColumnCount(2)
        table.horizontalHeader().setStretchLastSection(True)
        table.setEditTriggers(table.EditTrigger.NoEditTriggers)

    def _populate_place_combo(self) -> None:
        """Fill the App_JSON place combo box with available project places.

        Each entry shows the place name with its full hierarchy path for
        context (e.g. "Ljusdals kyrka (Ljusdals kyrka → Ljusdal → Sverige)").
        """
        combo = self._ui.app_place_combo
        combo.clear()
        combo.addItem("", "")  # Empty default entry
        for place in self._project_data.places:
            hierarchy = self._build_hierarchy_string(place.id)
            display = f"{place.name} ({hierarchy})" if hierarchy != place.name else place.name
            combo.addItem(display, place.id)

    def _connect_signals(self) -> None:
        """Wire up UI signals to handler slots."""
        self._ui.search_input.textChanged.connect(self._on_search_changed)
        self._ui.add_button.clicked.connect(self._on_add)
        self._ui.edit_button.clicked.connect(self._on_edit)
        self._ui.remove_button.clicked.connect(self._on_remove)
        self._ui.save_button.clicked.connect(self._on_save)
        self._ui.mapping_table.itemSelectionChanged.connect(
            self._on_selection_changed
        )
        self._ui.app_place_combo.currentIndexChanged.connect(
            self._on_combo_changed
        )

    def _add_create_button(self) -> None:
        """Add a 'Skapa ny plats' button next to the existing buttons.

        Inserts the button after the 'Lägg till' button in the button
        layout so the user can create a new App_JSON Place directly from
        an unmapped GEDCOM place string.
        """
        from PySide6.QtWidgets import QPushButton

        self._create_place_button = QPushButton("Skapa ny plats...")
        self._create_place_button.setToolTip(
            "Skapa en ny App_JSON-plats från den valda GEDCOM-platssträngen"
        )
        # Insert after the add_button (index 1)
        self._ui.button_layout.insertWidget(1, self._create_place_button)
        self._create_place_button.clicked.connect(self._on_create_place)

    # ------------------------------------------------------------------
    # Private: hierarchy helpers
    # ------------------------------------------------------------------

    def _build_hierarchy_string(self, place_id: str) -> str:
        """Build a full hierarchy path string for a place.

        Walks up the parent_place_id chain and joins names with " → ".
        Example: "Ljusdals kyrka → Ljusdal → Gävleborgs län → Sverige"

        Args:
            place_id: The starting place ID to build hierarchy for.

        Returns:
            A string showing the full hierarchy path, or empty string if
            the place ID is not found.
        """
        parts: list[str] = []
        visited: set[str] = set()
        current_id: str | None = place_id

        while current_id and current_id not in visited:
            visited.add(current_id)
            place = self._place_by_id.get(current_id)
            if place is None:
                break
            parts.append(place.name)
            current_id = place.parent_place_id

        return " \u2192 ".join(parts) if parts else ""

    def _get_hierarchy_for_combo_selection(self) -> str:
        """Get the hierarchy string for the currently selected combo place.

        Returns:
            The full hierarchy string, or empty string if nothing selected.
        """
        app_id = self._ui.app_place_combo.currentData()
        if not app_id:
            return ""
        return self._build_hierarchy_string(app_id)

    # ------------------------------------------------------------------
    # Private: table management
    # ------------------------------------------------------------------

    def _refresh_table(self) -> None:
        """Rebuild the table contents from current translation data.

        Unmapped entries (those with empty app_id or a target that doesn't
        exist in the project) are shown with a "⚠ Ej mappad" indicator in
        the second column and highlighted with a yellow background.
        """
        table = self._ui.mapping_table
        table.setRowCount(0)

        if self._translation_data is None:
            return

        for mapping in self._translation_data.places:
            self._add_table_row(mapping)

    def _add_table_row(self, mapping: PlaceMapping) -> None:
        """Append a single mapping row to the table.

        The second column shows the place name with its hierarchy context.
        Unmapped entries (empty app_id or target not in project) are shown
        with a warning indicator and yellow background.

        Args:
            mapping: The place mapping to display.
        """
        table = self._ui.mapping_table
        row = table.rowCount()
        table.insertRow(row)

        gedcom_item = QTableWidgetItem(mapping.gedcom_place)
        gedcom_item.setFlags(
            Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        )

        # Determine if this is an unmapped entry
        is_unmapped = not mapping.app_id or mapping.app_id not in self._place_by_id

        if is_unmapped:
            display = "\u26a0 Ej mappad"
            place_item = QTableWidgetItem(display)
            place_item.setFlags(
                Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
            )
            # Yellow background for unmapped entries
            from PySide6.QtGui import QColor
            gedcom_item.setBackground(QColor(255, 255, 200))
            place_item.setBackground(QColor(255, 255, 200))
        else:
            # Show hierarchy in the table for context
            hierarchy = self._build_hierarchy_string(mapping.app_id)
            display = hierarchy if hierarchy else (mapping.name or mapping.app_id)
            place_item = QTableWidgetItem(display)
            place_item.setFlags(
                Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
            )

        table.setItem(row, 0, gedcom_item)
        table.setItem(row, 1, place_item)

    # ------------------------------------------------------------------
    # Private: search / filter
    # ------------------------------------------------------------------

    def _on_search_changed(self, text: str) -> None:
        """Filter visible table rows based on search text.

        Case-insensitive substring match on GEDCOM place string or
        App_JSON place display.

        Args:
            text: The current search string.
        """
        search = text.lower()
        table = self._ui.mapping_table

        for row in range(table.rowCount()):
            gedcom_text = (table.item(row, 0).text() or "").lower()
            place_text = (table.item(row, 1).text() or "").lower()
            visible = search in gedcom_text or search in place_text
            table.setRowHidden(row, not visible)

    # ------------------------------------------------------------------
    # Private: action handlers
    # ------------------------------------------------------------------

    def _on_selection_changed(self) -> None:
        """Update edit fields when a table row is selected."""
        selected = self._ui.mapping_table.selectedItems()
        if not selected:
            return

        row = selected[0].row()
        if self._translation_data is None:
            return

        if 0 <= row < len(self._translation_data.places):
            mapping = self._translation_data.places[row]
            self._ui.gedcom_place_input.setText(mapping.gedcom_place)

            # Select matching combo entry
            combo = self._ui.app_place_combo
            for i in range(combo.count()):
                if combo.itemData(i) == mapping.app_id:
                    combo.setCurrentIndex(i)
                    break

    def _on_combo_changed(self) -> None:
        """Update hierarchy label and validation when combo selection changes."""
        app_id = self._ui.app_place_combo.currentData()
        if not app_id:
            self._ui.hierarchy_label.setText("")
            self._ui.validation_indicator.setText("")
            self._ui.validation_indicator.setStyleSheet("")
            return

        # Update hierarchy display
        hierarchy = self._build_hierarchy_string(app_id)
        self._ui.hierarchy_label.setText(hierarchy)

        # Update validation indicator
        if app_id in self._place_by_id:
            self._ui.validation_indicator.setText("\u2713 Giltig plats")
            self._ui.validation_indicator.setStyleSheet("color: green;")
        else:
            self._ui.validation_indicator.setText("\u2717 Plats saknas i projektet")
            self._ui.validation_indicator.setStyleSheet("color: red;")

    def _on_add(self) -> None:
        """Add a new place mapping from the edit fields."""
        gedcom_place = self._ui.gedcom_place_input.text().strip()
        app_id = self._ui.app_place_combo.currentData()

        if not gedcom_place:
            self._update_status("Ange en GEDCOM-platssträng.")
            return

        if not app_id:
            self._update_status("Välj en App_JSON-plats.")
            return

        if not self._validate_target(app_id):
            return

        # Get display name for the place
        name = self._get_place_name(app_id)

        new_mapping = PlaceMapping(
            gedcom_place=gedcom_place, app_id=app_id, name=name
        )

        if self._translation_data is None:
            self._translation_data = TranslationData()

        # Check for duplicate GEDCOM place string
        for existing in self._translation_data.places:
            if existing.gedcom_place == gedcom_place:
                self._update_status(
                    f"GEDCOM-platssträng '{gedcom_place}' finns redan. "
                    "Använd Redigera för att ändra."
                )
                return

        self._translation_data.places.append(new_mapping)
        self._add_table_row(new_mapping)
        self._mark_dirty()
        self._clear_edit_fields()
        self._update_status(f"Mappning tillagd: {gedcom_place} → {app_id}")

    def _on_create_place(self) -> None:
        """Open a dialog to create new App_JSON Places from the current GEDCOM string.

        Parses the GEDCOM place string, matches existing places, and
        creates any missing intermediate levels in one step. After
        creation, the combo is refreshed and the leaf place is auto-
        selected so the user can click 'Lägg till' to complete the mapping.
        """
        gedcom_place = self._ui.gedcom_place_input.text().strip()

        if not gedcom_place:
            # If no text in the input, try the selected row
            selected = self._ui.mapping_table.selectedItems()
            if selected:
                gedcom_place = selected[0].text()

        if not gedcom_place:
            self._update_status(
                "Ange eller välj en GEDCOM-platssträng att skapa plats för."
            )
            return

        dialog = CreatePlaceDialog(
            gedcom_place_string=gedcom_place,
            existing_places=self._project_data.places,
            place_by_id=self._place_by_id,
            parent=self,
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_places = dialog.created_places
        if not new_places:
            self._update_status("Inga nya platser att skapa (alla finns redan).")
            return

        # Assign real IDs. Places come in order: least specific → most specific.
        # Build a name→ID map to resolve __new: sentinel parent references.
        name_to_id: dict[str, str] = {}

        for place in new_places:
            place.id = self._id_generator.generate("place")
            name_to_id[place.name] = place.id

        # Resolve __new:<name> parent references now that IDs are assigned
        for place in new_places:
            if place.parent_place_id and place.parent_place_id.startswith("__new:"):
                parent_name = place.parent_place_id[6:]  # Strip "__new:" prefix
                place.parent_place_id = name_to_id.get(parent_name)

        # Add all new places to the project
        for place in new_places:
            self._project_data.places.append(place)
            self._place_by_id[place.id] = place
            self.place_created.emit(place)

        # Refresh the combo to include all new places
        self._populate_place_combo()

        # The leaf place is the most specific (last in the list)
        leaf = new_places[-1]

        # Select the leaf place in the combo
        combo = self._ui.app_place_combo
        for i in range(combo.count()):
            if combo.itemData(i) == leaf.id:
                combo.setCurrentIndex(i)
                break

        # Set the GEDCOM string in the input
        self._ui.gedcom_place_input.setText(gedcom_place)

        names = ", ".join(p.name for p in new_places)
        self._update_status(
            f"{len(new_places)} plats(er) skapade: {names}. "
            "Klicka 'Lägg till' för att skapa mappningen."
        )
        logger.info(
            "Skapade %d platser från redigeraren: %s",
            len(new_places),
            names,
        )

    def _on_edit(self) -> None:
        """Update the currently selected mapping with edited values."""
        selected = self._ui.mapping_table.selectedItems()
        if not selected:
            self._update_status("Välj en rad att redigera.")
            return

        row = selected[0].row()
        if self._translation_data is None or row >= len(
            self._translation_data.places
        ):
            return

        gedcom_place = self._ui.gedcom_place_input.text().strip()
        app_id = self._ui.app_place_combo.currentData()

        if not gedcom_place:
            self._update_status("Ange en GEDCOM-platssträng.")
            return

        if not app_id:
            self._update_status("Välj en App_JSON-plats.")
            return

        if not self._validate_target(app_id):
            return

        name = self._get_place_name(app_id)

        # Update the mapping
        self._translation_data.places[row] = PlaceMapping(
            gedcom_place=gedcom_place, app_id=app_id, name=name
        )

        # Update table display
        self._ui.mapping_table.item(row, 0).setText(gedcom_place)
        hierarchy = self._build_hierarchy_string(app_id)
        self._ui.mapping_table.item(row, 1).setText(
            hierarchy if hierarchy else (name or app_id)
        )

        self._mark_dirty()
        self._update_status(f"Mappning uppdaterad: {gedcom_place} → {app_id}")

    def _on_remove(self) -> None:
        """Remove the currently selected mapping."""
        selected = self._ui.mapping_table.selectedItems()
        if not selected:
            self._update_status("Välj en rad att ta bort.")
            return

        row = selected[0].row()
        if self._translation_data is None or row >= len(
            self._translation_data.places
        ):
            return

        removed = self._translation_data.places.pop(row)
        self._ui.mapping_table.removeRow(row)
        self._mark_dirty()
        self._update_status(f"Mappning borttagen: {removed.gedcom_place}")

    def _on_save(self) -> None:
        """Persist all mappings to disk.

        Validates all mappings before saving. On file system errors,
        displays a Swedish-language error message and retains unsaved
        changes in the editor (requirement 6.6).
        """
        if self._translation_data is None:
            self._update_status("Inga data att spara.")
            return

        # Validate all mappings before saving
        invalid = self._find_invalid_mappings()
        if invalid:
            places_str = ", ".join(invalid)
            self._update_status(
                f"Ogiltiga mappningar (mål saknas): {places_str}. "
                "Åtgärda innan du sparar."
            )
            return

        try:
            self._translation_service.save_translations(
                self._translation_data, self._project_path
            )
            self._dirty = False
            self._update_status("Översättningar sparade.")
            logger.info("Platsöversättningar sparade till disk.")
        except TranslationServiceError as exc:
            # Requirement 6.6: Swedish error message, retain unsaved changes
            error_msg = (
                f"Kunde inte spara översättningsfilen: {exc.message}\n\n"
                "Ändringarna finns kvar i redigeraren."
            )
            self._update_status(f"Fel: {exc.message}")
            QMessageBox.warning(
                self,
                "Sparfel",
                error_msg,
            )
            logger.error("Kunde inte spara platsöversättningar: %s", exc)
        except OSError as exc:
            error_msg = (
                f"Filsystemfel vid sparning: {exc}\n\n"
                "Ändringarna finns kvar i redigeraren."
            )
            self._update_status(f"Fel: {exc}")
            QMessageBox.warning(
                self,
                "Sparfel",
                error_msg,
            )
            logger.error(
                "Filsystemfel vid sparning av platsöversättningar: %s", exc
            )

    # ------------------------------------------------------------------
    # Private: validation
    # ------------------------------------------------------------------

    def _validate_target(self, app_id: str) -> bool:
        """Check that the target App_JSON place ID exists in project data.

        Args:
            app_id: The App_JSON place ID to validate.

        Returns:
            True if the place exists, False otherwise (with UI feedback).
        """
        if app_id in self._place_by_id:
            self._ui.validation_indicator.setText("\u2713 Giltig plats")
            self._ui.validation_indicator.setStyleSheet("color: green;")
            return True

        self._ui.validation_indicator.setText("\u2717 Plats saknas i projektet")
        self._ui.validation_indicator.setStyleSheet("color: red;")
        self._update_status(
            f"App_JSON-plats '{app_id}' finns inte i projektets platsregister."
        )
        return False

    def _find_invalid_mappings(self) -> list[str]:
        """Find mappings whose target App_JSON place doesn't exist.

        Entries with an empty app_id are considered "unmapped" rather
        than "invalid" — they are allowed but will be skipped during
        export. Only entries with a non-empty app_id that doesn't match
        a project place are reported as invalid.

        Returns:
            List of GEDCOM place strings with invalid (non-empty but
            non-existent) targets.
        """
        if self._translation_data is None:
            return []

        return [
            m.gedcom_place
            for m in self._translation_data.places
            if m.app_id and m.app_id not in self._place_by_id
        ]

    # ------------------------------------------------------------------
    # Private: helpers
    # ------------------------------------------------------------------

    def _get_place_name(self, app_id: str) -> str:
        """Look up the name for an App_JSON place ID.

        Args:
            app_id: The App_JSON place ID.

        Returns:
            The place name, or empty string if not found.
        """
        place = self._place_by_id.get(app_id)
        return place.name if place else ""

    def _mark_dirty(self) -> None:
        """Mark the editor as having unsaved changes."""
        self._dirty = True

    def _clear_edit_fields(self) -> None:
        """Reset the edit input fields to empty state."""
        self._ui.gedcom_place_input.clear()
        self._ui.app_place_combo.setCurrentIndex(0)
        self._ui.hierarchy_label.setText("")
        self._ui.validation_indicator.setText("")
        self._ui.validation_indicator.setStyleSheet("")

    def _update_status(self, message: str) -> None:
        """Update the status label text.

        Args:
            message: The status message to display.
        """
        self._ui.status_label.setText(message)
