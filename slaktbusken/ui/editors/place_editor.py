"""Place editor widget.

Provides a split-panel editor for Place records: a filterable place list
on the left and a detail form on the right with type, name, parent place,
coordinates, and notes. Enforces the place-type hierarchy and warns before
deleting places referenced by events. All UI text is in Swedish.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from slaktbusken.services.photo_service import PhotoService

from slaktbusken.data.country_presets import available_presets, get_preset
from slaktbusken.model.place import (
    CustomFieldDef,
    ExternalId,
    Place,
    RegionLevel,
    add_alternative_name,
    add_external_id,
    edit_external_id,
    needs_red_dot,
    remove_alternative_name,
    remove_external_id,
)
from slaktbusken.model.project import ProjectData
from slaktbusken.ui.generated.ui_place_editor import Ui_PlaceEditor
from slaktbusken.ui.icons.icon_registry import icon_registry
from slaktbusken.ui.widgets.coordinate_spin_box import CoordinateSpinBox

logger = logging.getLogger(__name__)

# Mapping from Swedish UI labels to internal type strings (static types)
_TYPE_LABEL_TO_INTERNAL: dict[str, str] = {
    "Kontinent": "continent",
    "Land": "country",
    "Kyrka": "church",
    "Kyrkogård": "cemetery",
    "Gård": "farm",
    "Skola": "school",
    "Ort": "ort",
}

_TYPE_INTERNAL_TO_LABEL: dict[str, str] = {v: k for k, v in _TYPE_LABEL_TO_INTERNAL.items()}

# Valid parent types for each place type (legacy — kept for backward compat)
_VALID_PARENT_TYPES: dict[str, Optional[str]] = {
    "continent": None,
    "country": "continent",
    "church": None,
    "cemetery": None,
    "farm": None,
    "school": None,
    "ort": None,
}


def build_type_options(project_data: ProjectData) -> list[str]:
    """Build the list of available place type labels for the Type_Dropdown.

    Always includes:
    - "Kontinent" (first)
    - "Land"
    - Universal types: "Kyrka", "Kyrkogård", "Gård", "Skola", "Ort"

    Additionally includes all unique region level labels from countries
    in the project (from their region_levels field, or from presets if
    no region_levels are set on the country).

    Args:
        project_data: The current project data containing all entities.

    Returns:
        Ordered list of type labels for the dropdown.
    """
    from slaktbusken.data.country_presets import available_presets, get_preset

    # Fixed types always present
    fixed_labels = ["Kontinent", "Land"]
    universal_labels = ["Kyrka", "Kyrkogård", "Gård", "Skola", "Ort"]

    # Collect unique region level labels from all countries in the project
    region_labels: set[str] = set()
    for place in project_data.places:
        if place.type == "country":
            if place.region_levels:
                for rl in place.region_levels:
                    region_labels.add(rl.label)
            else:
                # Country has no region_levels set — check presets
                preset_name = _get_preset_name_for_country(place.name)
                if preset_name:
                    for rl in get_preset(preset_name):
                        region_labels.add(rl.label)

    # Build final list: Kontinent first, then Land, then region labels sorted,
    # then universal types
    sorted_region_labels = sorted(region_labels)
    return fixed_labels + sorted_region_labels + universal_labels


def _get_preset_name_for_country(country_name: str) -> Optional[str]:
    """Get the preset name for a country by its display name.

    Checks both the country_presets available list and common name variations.
    """
    from slaktbusken.data.country_presets import available_presets

    # Direct match
    if country_name in available_presets():
        return country_name

    # Try common name mappings
    _NAME_TO_PRESET = {
        "sverige": "Sverige",
        "norway": "Norge",
        "norge": "Norge",
        "finland": "Finland",
        "danmark": "Danmark",
        "denmark": "Danmark",
        "tyskland": "Tyskland",
        "germany": "Tyskland",
        "england": "England",
        "usa": "USA",
        "united states": "USA",
        "kanada": "USA",
        "canada": "USA",
    }
    return _NAME_TO_PRESET.get(country_name.lower())


def _resolve_type_label_to_internal(label: str, project_data: ProjectData) -> str:
    """Resolve a type dropdown label to its internal type string.

    Checks static types first, then looks up region level labels in project
    countries (both from their region_levels and from presets).

    Args:
        label: The Swedish UI label to resolve.
        project_data: The project data for looking up dynamic region level labels.

    Returns:
        The internal type string corresponding to the label.
    """
    from slaktbusken.data.country_presets import get_preset

    if label in _TYPE_LABEL_TO_INTERNAL:
        return _TYPE_LABEL_TO_INTERNAL[label]
    # Try to find among region level labels on countries
    for place in project_data.places:
        if place.type == "country":
            if place.region_levels:
                for rl in place.region_levels:
                    if rl.label == label:
                        return rl.key
            else:
                # Check preset for this country
                preset_name = _get_preset_name_for_country(place.name)
                if preset_name:
                    for rl in get_preset(preset_name):
                        if rl.label == label:
                            return rl.key
    return label.lower()  # Fallback


def _migrate_legacy_place_types(project_data: ProjectData) -> None:
    """Migrate legacy place types (county/parish/village) to region-level keys.

    Old GEDCOM imports used fixed types like "county" and "parish". The new
    system uses country-specific region-level keys (e.g., "lan", "socken" for
    Sverige). This function:
    1. Ensures all countries have their region_levels preset applied
    2. Converts legacy types to the correct region-level keys based on the
       country ancestor of each place
    """
    from slaktbusken.data.country_presets import get_preset

    # Step 1: Ensure countries have presets applied
    for place in project_data.places:
        if place.type == "country" and not place.region_levels:
            preset_name = _get_preset_name_for_country(place.name)
            if preset_name:
                place.region_levels = get_preset(preset_name)

    # Step 2: Build a map of place_id -> place for parent lookups
    place_map = {p.id: p for p in project_data.places}

    # Legacy type mappings per preset
    _LEGACY_TYPE_MAP: dict[str, dict[str, str]] = {
        "Sverige": {"county": "lan", "parish": "socken", "village": "socken"},
        "Norge": {"county": "fylke", "parish": "kommune"},
        "Finland": {"county": "landskap", "parish": "kommun"},
        "Danmark": {"county": "region", "parish": "kommune"},
        "Tyskland": {"county": "forbundsland", "parish": "kreis"},
        "England": {"county": "county", "parish": "parish"},
        "USA": {"county": "delstat", "parish": "county"},
    }

    # Step 3: Convert legacy types by walking up to find the country
    for place in project_data.places:
        if place.type not in ("county", "parish", "village"):
            continue

        # Walk up the parent chain to find the country
        country_name: Optional[str] = None
        current = place
        visited: set[str] = {place.id}
        while current.parent_place_id and current.parent_place_id not in visited:
            visited.add(current.parent_place_id)
            parent = place_map.get(current.parent_place_id)
            if parent is None:
                break
            if parent.type == "country":
                country_name = parent.name
                break
            current = parent

        if country_name:
            preset_name = _get_preset_name_for_country(country_name)
            if preset_name and preset_name in _LEGACY_TYPE_MAP:
                type_map = _LEGACY_TYPE_MAP[preset_name]
                if place.type in type_map:
                    place.type = type_map[place.type]


class PlaceListItemDelegate(QStyledItemDelegate):
    """Custom delegate that renders a red dot next to non-country places without a parent.

    The red dot (≤8px solid circle) appears 4px after the item text, vertically
    centred within the row. It indicates that the place needs a parent assignment.

    Args:
        project_data: The project data used to look up Place objects by ID.
        parent: Optional parent object.
    """

    _DOT_DIAMETER = 8
    _DOT_SPACING = 4

    def __init__(self, project_data: ProjectData, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project_data = project_data

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index,
    ) -> None:
        """Paint the item, adding a red dot indicator when appropriate."""
        # Let the base class render the text and selection state
        super().paint(painter, option, index)

        # Look up the place by ID stored in UserRole
        place_id = index.data(Qt.ItemDataRole.UserRole)
        if place_id is None:
            return

        place = self._find_place(place_id)
        if place is None:
            return

        if not needs_red_dot(place):
            return

        # Calculate text width to position the dot after it
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        font_metrics = option.fontMetrics
        text_width = font_metrics.horizontalAdvance(text)

        # Position: left edge of item + text offset + text width + spacing
        style = option.widget.style() if option.widget else None
        text_margin = style.pixelMetric(
            style.PixelMetric.PM_FocusFrameHMargin, option, option.widget
        ) + 1 if style else 4

        dot_x = option.rect.left() + text_margin + text_width + self._DOT_SPACING
        dot_y = option.rect.top() + (option.rect.height() - self._DOT_DIAMETER) // 2

        # Draw the solid red circle
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QBrush(QColor(255, 0, 0)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRect(dot_x, dot_y, self._DOT_DIAMETER, self._DOT_DIAMETER))
        painter.restore()

    def _find_place(self, place_id: str) -> Optional[Place]:
        """Find a place by its ID in the project data."""
        for p in self._project_data.places:
            if p.id == place_id:
                return p
        return None


class PlaceEditor(QWidget):
    """Editor widget for Place records with list/detail split layout.

    Displays a filterable list of all places on the left and an edit form
    on the right. Supports creating new places, editing existing ones,
    and deleting with referential integrity warnings.

    Signals:
        save_requested: Emitted when the user saves successfully.
        cancel_requested: Emitted when the user cancels editing.

    Args:
        project_data: The current project data containing all entities.
        place: Optional existing Place to select initially for editing.
        parent: Optional parent widget.
    """

    save_requested = Signal()
    cancel_requested = Signal()
    person_open_requested = Signal(str)  # Emits person_id

    def __init__(
        self,
        project_data: ProjectData,
        place: Optional[Place] = None,
        parent: QWidget | None = None,
        photo_service: "Optional[PhotoService]" = None,
    ) -> None:
        """Initialise the place editor.

        Args:
            project_data: The current project data containing all entities.
            place: Optional existing Place to select initially for editing.
            parent: Optional parent widget.
            photo_service: Optional PhotoService for photo management operations.
        """
        super().__init__(parent)

        self._project_data = project_data
        self._place = place
        self._photo_service = photo_service
        self._saved_place: Optional[Place] = None
        self._editing_place: Optional[Place] = None

        # Migrate legacy place types and ensure country presets are applied
        _migrate_legacy_place_types(project_data)

        # Set up UI from generated form
        self._ui = Ui_PlaceEditor()
        self._ui.setupUi(self)

        # Replace latitude/longitude spin boxes with CoordinateSpinBox (paste support)
        self._replace_spin_with_coordinate_spin("latitude_spin")
        self._replace_spin_with_coordinate_spin("longitude_spin")

        # Add "Visa på karta" button beside the coordinates checkbox
        self._btn_show_on_map = QPushButton("Visa på karta")
        self._btn_show_on_map.setEnabled(self._ui.coordinates_check.isChecked())
        # Replace the checkbox cell in the form layout with an HBox containing both
        coords_row_layout = QHBoxLayout()
        coords_row_layout.setContentsMargins(0, 0, 0, 0)
        # Remove the checkbox from form row 3 and re-add in a horizontal layout
        self._ui.form_layout.removeWidget(self._ui.coordinates_check)
        coords_row_layout.addWidget(self._ui.coordinates_check)
        coords_row_layout.addWidget(self._btn_show_on_map)
        coords_row_layout.addStretch()
        self._ui.form_layout.setLayout(
            3, QFormLayout.ItemRole.FieldRole, coords_row_layout
        )

        # Wrap the right panel in a QScrollArea so all content is accessible
        self._right_scroll = QScrollArea()
        self._right_scroll.setWidgetResizable(True)
        self._right_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        # Replace right_panel in the splitter with the scroll area containing it
        self._ui.splitter.replaceWidget(
            self._ui.splitter.indexOf(self._ui.right_panel),
            self._right_scroll,
        )
        self._right_scroll.setWidget(self._ui.right_panel)
        # Add type filter combo box to left panel between filter_input and place_list
        self._type_filter_label = QLabel("Typ:", self._ui.left_panel)
        self._type_filter_combo = QComboBox(self._ui.left_panel)
        type_options = build_type_options(project_data)
        self._type_filter_combo.addItems(["Alla"] + type_options)
        self._type_filter_combo.setCurrentIndex(0)
        # Insert at index 2 (after filter_input at index 1, before place_list)
        self._ui.left_layout.insertWidget(2, self._type_filter_label)
        self._ui.left_layout.insertWidget(3, self._type_filter_combo)

        self._setup_child_places_list()
        self._setup_preset_section()
        self._setup_custom_fields_section()
        self._setup_photo_section()
        self._connect_signals()

        # Set up custom delegate for red dot indicator on places missing a parent
        self._place_list_delegate = PlaceListItemDelegate(project_data, self._ui.place_list)
        self._ui.place_list.setItemDelegate(self._place_list_delegate)

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

    def _replace_spin_with_coordinate_spin(self, attr_name: str) -> None:
        """Replace a QDoubleSpinBox in the form with a CoordinateSpinBox.

        Copies the original widget's range, decimals, enabled state, and value,
        then swaps it in the form layout at the same position.

        Args:
            attr_name: The attribute name on self._ui (e.g. "latitude_spin").
        """
        original = getattr(self._ui, attr_name)
        new_spin = CoordinateSpinBox(self._ui.right_panel)
        new_spin.setObjectName(original.objectName())
        new_spin.setMinimum(original.minimum())
        new_spin.setMaximum(original.maximum())
        new_spin.setDecimals(original.decimals())
        new_spin.setEnabled(original.isEnabled())
        new_spin.setValue(original.value())

        # Find the widget in the form layout and replace it
        layout = self._ui.form_layout
        for row in range(layout.rowCount()):
            item = layout.itemAt(row, QFormLayout.ItemRole.FieldRole)
            if item and item.widget() is original:
                original.setParent(None)
                layout.setWidget(row, QFormLayout.ItemRole.FieldRole, new_spin)
                break

        # Update the reference on the UI object so existing code keeps working
        setattr(self._ui, attr_name, new_spin)

    def _setup_child_places_list(self) -> None:
        """Add a child places group box to the right panel.

        Shows all places that have this place as their parent, allowing
        the user to see the hierarchy below the selected place.
        """
        # Populate the type combo dynamically using build_type_options
        existing_labels = [
            self._ui.type_combo.itemText(i)
            for i in range(self._ui.type_combo.count())
        ]
        for label in build_type_options(self._project_data):
            if label not in existing_labels:
                self._ui.type_combo.addItem(label)

        # Create group box with list
        self._child_group = QGroupBox("Underordnade platser", self._ui.right_panel)
        child_layout = QVBoxLayout(self._child_group)
        self._child_list = QListWidget(self._child_group)
        self._child_list.setMaximumHeight(150)
        child_layout.addWidget(self._child_list)

        # Insert before the status label and buttons (at index -2 from end)
        # The right_layout has: form_layout, notes, status_label, buttons_layout
        # Insert before status_label
        right_layout = self._ui.right_layout
        status_index = right_layout.indexOf(self._ui.status_label)
        if status_index >= 0:
            right_layout.insertWidget(status_index, self._child_group)
        else:
            right_layout.addWidget(self._child_group)

        # Create linked persons group box
        self._persons_group = QGroupBox("Kopplade personer", self._ui.right_panel)
        persons_layout = QVBoxLayout(self._persons_group)
        self._persons_list = QListWidget(self._persons_group)
        self._persons_list.setMaximumHeight(150)
        persons_layout.addWidget(self._persons_list)

        # Insert after child group (before status label)
        right_layout = self._ui.right_layout
        status_index = right_layout.indexOf(self._ui.status_label)
        if status_index >= 0:
            right_layout.insertWidget(status_index, self._persons_group)
        else:
            right_layout.addWidget(self._persons_group)

        # Create External IDs group box
        self._ext_id_group = QGroupBox("Externa ID:n", self._ui.right_panel)
        ext_id_layout = QVBoxLayout(self._ext_id_group)
        self._ext_id_list = QListWidget(self._ext_id_group)
        self._ext_id_list.setMaximumHeight(120)
        ext_id_layout.addWidget(self._ext_id_list)

        # Buttons: Lägg till, Redigera, Ta bort
        ext_id_btn_layout = QHBoxLayout()
        self._ext_id_add_btn = QPushButton("Lägg till", self._ext_id_group)
        self._ext_id_edit_btn = QPushButton("Redigera", self._ext_id_group)
        self._ext_id_remove_btn = QPushButton("Ta bort", self._ext_id_group)
        ext_id_btn_layout.addWidget(self._ext_id_add_btn)
        ext_id_btn_layout.addWidget(self._ext_id_edit_btn)
        ext_id_btn_layout.addWidget(self._ext_id_remove_btn)
        ext_id_layout.addLayout(ext_id_btn_layout)

        # Insert before status label
        status_index = right_layout.indexOf(self._ui.status_label)
        if status_index >= 0:
            right_layout.insertWidget(status_index, self._ext_id_group)
        else:
            right_layout.addWidget(self._ext_id_group)

        # Create Alternative Names group box
        self._alt_names_group = QGroupBox("Alternativnamn:", self._ui.right_panel)
        alt_names_layout = QVBoxLayout(self._alt_names_group)
        self._alt_names_list = QListWidget(self._alt_names_group)
        self._alt_names_list.setMaximumHeight(120)
        alt_names_layout.addWidget(self._alt_names_list)

        # Buttons: Lägg till, Ta bort
        alt_names_btn_layout = QHBoxLayout()
        self._alt_name_add_btn = QPushButton("Lägg till", self._alt_names_group)
        self._alt_name_remove_btn = QPushButton("Ta bort", self._alt_names_group)
        alt_names_btn_layout.addWidget(self._alt_name_add_btn)
        alt_names_btn_layout.addWidget(self._alt_name_remove_btn)
        alt_names_layout.addLayout(alt_names_btn_layout)

        # Insert before status label
        status_index = right_layout.indexOf(self._ui.status_label)
        if status_index >= 0:
            right_layout.insertWidget(status_index, self._alt_names_group)
        else:
            right_layout.addWidget(self._alt_names_group)

    def _setup_preset_section(self) -> None:
        """Create the preset selection UI, shown only for country places.

        Adds a group box with a combo listing available presets, an apply button,
        and a list widget showing the current region levels.
        """
        self._preset_group = QGroupBox("Förinställning regionnivåer", self._ui.right_panel)
        preset_layout = QVBoxLayout(self._preset_group)

        # Preset combo + apply button row
        preset_row = QHBoxLayout()
        self._preset_combo = QComboBox(self._preset_group)
        self._preset_combo.addItem("(Välj förinställning)")
        for preset_name in available_presets():
            self._preset_combo.addItem(preset_name)
        preset_row.addWidget(self._preset_combo)

        self._preset_apply_btn = QPushButton("Använd", self._preset_group)
        preset_row.addWidget(self._preset_apply_btn)
        preset_layout.addLayout(preset_row)

        # Region levels display list
        self._region_levels_list = QListWidget(self._preset_group)
        self._region_levels_list.setMaximumHeight(120)
        preset_layout.addWidget(self._region_levels_list)

        # Insert before status label in the right layout
        right_layout = self._ui.right_layout
        status_index = right_layout.indexOf(self._ui.status_label)
        if status_index >= 0:
            right_layout.insertWidget(status_index, self._preset_group)
        else:
            right_layout.addWidget(self._preset_group)

        # Hidden by default; shown only when editing a country place
        self._preset_group.setVisible(False)

    def _setup_custom_fields_section(self) -> None:
        """Create the custom fields UI, shown when place type matches a region level with custom fields.

        Adds a group box with dynamically created QLineEdit inputs for each custom field.
        """
        self._custom_fields_group = QGroupBox("Anpassade fält", self._ui.right_panel)
        self._custom_fields_layout = QFormLayout(self._custom_fields_group)
        self._custom_field_inputs: dict[str, QLineEdit] = {}

        # Insert before status label in the right layout
        right_layout = self._ui.right_layout
        status_index = right_layout.indexOf(self._ui.status_label)
        if status_index >= 0:
            right_layout.insertWidget(status_index, self._custom_fields_group)
        else:
            right_layout.addWidget(self._custom_fields_group)

        # Hidden by default; shown only when place type has custom fields
        self._custom_fields_group.setVisible(False)

    def _setup_photo_section(self) -> None:
        """Create the photo section using PhotoSectionWidget.

        Adds a "Foton" group box with the reusable PhotoSectionWidget
        configured for place mode (buttons: Visa foto, Redigera foto, Lägg till foto).
        The section is hidden until a place is selected.
        """
        from slaktbusken.ui.widgets.photo_section_widget import PhotoSectionWidget

        self._photo_group = QGroupBox("Foton", self._ui.right_panel)
        photo_layout = QVBoxLayout(self._photo_group)

        # Create a placeholder PhotoSectionWidget (will be replaced on place selection)
        self._photo_section: Optional[PhotoSectionWidget] = None
        self._photo_section_layout = photo_layout

        # Insert before status label in the right layout
        right_layout = self._ui.right_layout
        status_index = right_layout.indexOf(self._ui.status_label)
        if status_index >= 0:
            right_layout.insertWidget(status_index, self._photo_group)
        else:
            right_layout.addWidget(self._photo_group)

        # Hidden until a place is selected
        self._photo_group.setVisible(False)

    def _connect_signals(self) -> None:
        """Wire up UI signals to handler slots."""
        # Filter
        self._ui.filter_input.textChanged.connect(self._on_filter_changed)
        self._type_filter_combo.currentIndexChanged.connect(self._on_type_filter_changed)

        # List selection
        self._ui.place_list.currentItemChanged.connect(self._on_place_selected)

        # Add / Delete buttons
        self._ui.add_button.clicked.connect(self._on_add_place)
        self._ui.delete_button.clicked.connect(self._on_delete_place)

        # Coordinates checkbox
        self._ui.coordinates_check.toggled.connect(self._on_coordinates_toggled)
        self._ui.coordinates_check.toggled.connect(self._btn_show_on_map.setEnabled)
        self._btn_show_on_map.clicked.connect(self._on_show_place_on_map)

        # Type change updates parent combo
        self._ui.type_combo.currentIndexChanged.connect(self._on_type_changed)

        # External IDs
        self._ext_id_add_btn.clicked.connect(self._on_ext_id_add)
        self._ext_id_edit_btn.clicked.connect(self._on_ext_id_edit)
        self._ext_id_remove_btn.clicked.connect(self._on_ext_id_remove)

        # Alternative Names
        self._alt_name_add_btn.clicked.connect(self._on_alt_name_add)
        self._alt_name_remove_btn.clicked.connect(self._on_alt_name_remove)

        # Preset apply
        self._preset_apply_btn.clicked.connect(self._on_preset_apply)

        # Linked persons double-click
        self._persons_list.itemDoubleClicked.connect(self._on_person_double_clicked)

        # Save / Cancel
        self._ui.save_button.clicked.connect(self._on_save)
        self._ui.cancel_button.clicked.connect(self._on_cancel)

    # ------------------------------------------------------------------
    # Private: place list management
    # ------------------------------------------------------------------

    def _refresh_place_list(self) -> None:
        """Rebuild the place list from project_data, applying text and type filters."""
        filter_text = self._ui.filter_input.text().strip().lower()
        type_filter_label = self._type_filter_combo.currentText()
        if type_filter_label == "Alla":
            type_filter = "all"
        else:
            type_filter = _resolve_type_label_to_internal(
                type_filter_label, self._project_data
            )

        self._ui.place_list.blockSignals(True)
        self._ui.place_list.clear()

        # Collect and sort alphabetically
        entries: list[tuple[str, str]] = []
        for place in self._project_data.places:
            if not self._matches_filters(place, filter_text, type_filter):
                continue
            display = self._format_place_display(place)
            entries.append((display, place.id))

        entries.sort(key=lambda x: x[0].lower())

        for display, place_id in entries:
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, place_id)
            # Show map icon for places with coordinates
            place = self._find_place_by_id(place_id)
            if place and place.latitude is not None and place.longitude is not None:
                item.setIcon(QIcon(icon_registry.get_map_icon()))
            self._ui.place_list.addItem(item)

        self._ui.place_list.blockSignals(False)

    @staticmethod
    def _matches_filters(place: Place, text_filter: str, type_filter: str) -> bool:
        """Return True if the place passes both text and type filters.

        Args:
            place: The Place to check.
            text_filter: Lowercase text to match against display name (empty = no filter).
            type_filter: Internal type string to match, or "all" for no type filtering.

        Returns:
            True if the place matches all active filters.
        """
        if type_filter != "all" and place.type != type_filter:
            return False
        if text_filter:
            # Build a simple display string for text matching
            type_label = _TYPE_INTERNAL_TO_LABEL.get(place.type, place.type)
            display = f"{place.name} ({type_label})"
            if text_filter not in display.lower():
                return False
        return True

    def _format_place_display(self, place: Place) -> str:
        """Format a place for display in the list with hierarchy context.

        Args:
            place: The Place to format.

        Returns:
            Display string with name and parent context.
        """
        type_label = _TYPE_INTERNAL_TO_LABEL.get(place.type, place.type)
        # For dynamic region level types, look up the label from country definitions or presets
        if place.type not in _TYPE_INTERNAL_TO_LABEL:
            for p in self._project_data.places:
                if p.type == "country":
                    for rl in self._get_region_levels_for_country(p):
                        if rl.key == place.type:
                            type_label = rl.label.lower()
                            break
                    else:
                        continue
                    break
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

    def _on_type_filter_changed(self, index: int) -> None:
        """Handle type filter combo changes by refreshing the place list.

        Args:
            index: The new index in the type filter combo.
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
        from slaktbusken.data.country_presets import get_preset

        # Type
        type_label = _TYPE_INTERNAL_TO_LABEL.get(place.type, None)
        # If not in static mapping, check dynamic region level labels
        if type_label is None:
            for p in self._project_data.places:
                if p.type == "country":
                    # Check region_levels on the country
                    if p.region_levels:
                        for rl in p.region_levels:
                            if rl.key == place.type:
                                type_label = rl.label
                                break
                    else:
                        # Check preset for this country
                        preset_name = _get_preset_name_for_country(p.name)
                        if preset_name:
                            for rl in get_preset(preset_name):
                                if rl.key == place.type:
                                    type_label = rl.label
                                    break
                    if type_label:
                        break
        if type_label is None:
            type_label = place.type.capitalize()  # Better fallback than "Land"
        type_index = self._ui.type_combo.findText(type_label)
        if type_index >= 0:
            self._ui.type_combo.setCurrentIndex(type_index)
        else:
            # Type not in combo — add it dynamically
            self._ui.type_combo.addItem(type_label)
            self._ui.type_combo.setCurrentIndex(self._ui.type_combo.count() - 1)

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

        # Child places
        self._refresh_child_places(place)

        # Linked persons
        self._refresh_linked_persons(place)

        # External IDs
        self._refresh_external_ids(place)

        # Alternative Names
        self._refresh_alternative_names(place)

        # Preset section (visible only for country places)
        is_country = place.type == "country"
        self._preset_group.setVisible(is_country)
        if is_country:
            self._refresh_region_levels_list(place)

        # Custom fields (visible if type matches a region level with custom fields)
        self._update_custom_fields_visibility(place.type)

        # Photo section
        self._refresh_photo_section(place)

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
        self._child_list.clear()
        self._persons_list.clear()
        self._ext_id_list.clear()
        self._alt_names_list.clear()
        self._region_levels_list.clear()
        self._preset_combo.setCurrentIndex(0)
        self._preset_group.setVisible(False)
        self._custom_fields_group.setVisible(False)
        while self._custom_fields_layout.rowCount() > 0:
            self._custom_fields_layout.removeRow(0)
        self._custom_field_inputs.clear()
        self._photo_group.setVisible(False)
        self._clear_status()

    def _refresh_child_places(self, place: Place) -> None:
        """Populate the child places list with places that have this place as parent.

        Args:
            place: The parent place to find children for.
        """
        self._child_list.clear()

        children = [
            p for p in self._project_data.places
            if p.parent_place_id == place.id
        ]
        # Sort by type then name
        children.sort(key=lambda p: (p.type, p.name.lower()))

        if not children:
            self._child_group.setTitle("Underordnade platser (inga)")
            return

        self._child_group.setTitle(f"Underordnade platser ({len(children)})")
        for child in children:
            type_label = _TYPE_INTERNAL_TO_LABEL.get(child.type, child.type)
            # For dynamic region level types, look up the label from country definitions
            if child.type not in _TYPE_INTERNAL_TO_LABEL:
                for p in self._project_data.places:
                    if p.type == "country":
                        for rl in p.region_levels:
                            if rl.key == child.type:
                                type_label = rl.label
                                break
                        else:
                            continue
                        break
            display = f"{child.name} ({type_label})"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, child.id)
            self._child_list.addItem(item)

    def _refresh_linked_persons(self, place: Place) -> None:
        """Populate the linked persons list with people who have events at this place.

        Also includes sub-places (children of this place) to show all persons
        connected to this location in the hierarchy.

        Args:
            place: The place to find linked persons for.
        """
        self._persons_list.clear()

        # Collect place IDs: this place + all its children
        place_ids: set[str] = {place.id}
        for p in self._project_data.places:
            if p.parent_place_id == place.id:
                place_ids.add(p.id)

        # Find all persons with events at these places
        person_ids: set[str] = set()
        for event in self._project_data.events:
            if event.place and event.place.place_id in place_ids:
                for participant in event.participants:
                    person_ids.add(participant.person_id)

        if not person_ids:
            self._persons_group.setTitle("Kopplade personer (inga)")
            return

        self._persons_group.setTitle(f"Kopplade personer ({len(person_ids)})")

        # Build display entries sorted alphabetically
        entries: list[tuple[str, str]] = []
        for person in self._project_data.persons:
            if person.id in person_ids:
                if person.names:
                    name = person.names[0]
                    parts = []
                    if name.surname:
                        parts.append(name.surname)
                    if name.given:
                        parts.append(name.given)
                    display = ", ".join(parts) if parts else person.id
                else:
                    display = person.id
                entries.append((display, person.id))

        entries.sort(key=lambda x: x[0].lower())

        for display, person_id in entries:
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, person_id)
            self._persons_list.addItem(item)

    def _on_person_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle double-click on a person in the linked persons list.

        Emits person_open_requested signal with the person ID.

        Args:
            item: The double-clicked list item.
        """
        person_id = item.data(Qt.ItemDataRole.UserRole)
        if person_id:
            self.person_open_requested.emit(person_id)

    def _on_ext_id_add(self) -> None:
        """Handle click on the Add button in the External IDs section.

        Shows a dialog with key/value input fields. Validates and adds the
        entry to the current place on confirm.
        """
        if self._editing_place is None:
            self._update_status("Välj en plats först.")
            return

        while True:
            dialog = QDialog(self)
            dialog.setWindowTitle("Lägg till externt ID")
            layout = QVBoxLayout(dialog)

            form_layout = QFormLayout()
            key_input = QLineEdit(dialog)
            key_input.setMaxLength(100)
            key_input.setPlaceholderText("T.ex. _PARISH_AID")
            value_input = QLineEdit(dialog)
            value_input.setMaxLength(200)
            value_input.setPlaceholderText("Identifierare")

            form_layout.addRow("Nyckel:", key_input)
            form_layout.addRow("Värde:", value_input)
            layout.addLayout(form_layout)

            error_label = QLabel("", dialog)
            error_label.setStyleSheet("color: red;")
            error_label.setWordWrap(True)
            layout.addWidget(error_label)

            button_box = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
                dialog,
            )
            layout.addWidget(button_box)

            button_box.accepted.connect(dialog.accept)
            button_box.rejected.connect(dialog.reject)

            result = dialog.exec()
            if result != QDialog.DialogCode.Accepted:
                return

            key = key_input.text()
            value = value_input.text()

            ext_id = ExternalId(key=key, value=value)
            errors = add_external_id(self._editing_place, ext_id)

            if errors:
                self._update_status(" ".join(errors))
                # Loop to re-show dialog so user can correct input
                continue

            # Success: refresh display and clear status
            self._refresh_external_ids(self._editing_place)
            self._clear_status()
            return

    def _on_ext_id_edit(self) -> None:
        """Handle click on the Edit button in the External IDs section.

        Shows a dialog pre-populated with the selected entry's key and value.
        Validates and updates the entry on confirm.
        """
        if self._editing_place is None:
            self._update_status("Välj en plats först.")
            return

        current = self._ext_id_list.currentItem()
        if current is None:
            self._update_status("Välj ett externt ID att redigera.")
            return

        old_key = current.data(Qt.ItemDataRole.UserRole)

        # Find the existing entry to pre-populate the dialog
        existing_entry = None
        for eid in self._editing_place.external_ids:
            if eid.key == old_key:
                existing_entry = eid
                break

        if existing_entry is None:
            return

        while True:
            dialog = QDialog(self)
            dialog.setWindowTitle("Redigera externt ID")
            layout = QVBoxLayout(dialog)

            form_layout = QFormLayout()
            key_input = QLineEdit(dialog)
            key_input.setMaxLength(100)
            key_input.setText(existing_entry.key)
            value_input = QLineEdit(dialog)
            value_input.setMaxLength(200)
            value_input.setText(existing_entry.value)

            form_layout.addRow("Nyckel:", key_input)
            form_layout.addRow("Värde:", value_input)
            layout.addLayout(form_layout)

            error_label = QLabel("", dialog)
            error_label.setStyleSheet("color: red;")
            error_label.setWordWrap(True)
            layout.addWidget(error_label)

            button_box = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
                dialog,
            )
            layout.addWidget(button_box)

            button_box.accepted.connect(dialog.accept)
            button_box.rejected.connect(dialog.reject)

            result = dialog.exec()
            if result != QDialog.DialogCode.Accepted:
                return

            new_key = key_input.text()
            new_value = value_input.text()

            new_ext_id = ExternalId(key=new_key, value=new_value)
            errors = edit_external_id(self._editing_place, old_key, new_ext_id)

            if errors:
                self._update_status(" ".join(errors))
                # Loop to re-show dialog so user can correct input
                continue

            # Success: refresh display and clear status
            self._refresh_external_ids(self._editing_place)
            self._clear_status()
            return

    def _on_ext_id_remove(self) -> None:
        """Handle click on the Remove button in the External IDs section.

        Removes the currently selected External ID entry from the place.
        """
        if self._editing_place is None:
            self._update_status("Välj en plats först.")
            return

        current = self._ext_id_list.currentItem()
        if current is None:
            self._update_status("Välj ett externt ID att ta bort.")
            return

        key = current.data(Qt.ItemDataRole.UserRole)
        remove_external_id(self._editing_place, key)

        # Refresh display and clear status
        self._refresh_external_ids(self._editing_place)
        self._clear_status()

    def _refresh_external_ids(self, place: Place) -> None:
        """Populate the external IDs list with the place's external ID entries.

        Args:
            place: The place whose external IDs should be displayed.
        """
        self._ext_id_list.clear()

        ext_ids = getattr(place, "external_ids", [])
        if not ext_ids:
            return

        for ext_id in ext_ids:
            display = f"{ext_id.key}: {ext_id.value}"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, ext_id.key)
            self._ext_id_list.addItem(item)

    # ------------------------------------------------------------------
    # Private: alternative names
    # ------------------------------------------------------------------

    def _on_alt_name_add(self) -> None:
        """Handle click on the Add button in the Alternative Names section."""
        if self._editing_place is None:
            self._update_status("Välj en plats först.")
            return

        while True:
            dialog = QDialog(self)
            dialog.setWindowTitle("Lägg till alternativnamn")
            layout = QVBoxLayout(dialog)

            form_layout = QFormLayout()
            name_input = QLineEdit(dialog)
            name_input.setMaxLength(200)
            name_input.setPlaceholderText("Alternativt namn")
            form_layout.addRow("Namn:", name_input)
            layout.addLayout(form_layout)

            error_label = QLabel("", dialog)
            error_label.setStyleSheet("color: red;")
            error_label.setWordWrap(True)
            layout.addWidget(error_label)

            button_box = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
                dialog,
            )
            layout.addWidget(button_box)

            button_box.accepted.connect(dialog.accept)
            button_box.rejected.connect(dialog.reject)

            result = dialog.exec()
            if result != QDialog.DialogCode.Accepted:
                return

            name = name_input.text()
            errors = add_alternative_name(self._editing_place, name)

            if errors:
                self._update_status(" ".join(errors))
                continue

            # Success: refresh display and clear status
            self._refresh_alternative_names(self._editing_place)
            self._clear_status()
            return

    def _on_alt_name_remove(self) -> None:
        """Handle click on the Remove button in the Alternative Names section."""
        if self._editing_place is None:
            self._update_status("Välj en plats först.")
            return

        current = self._alt_names_list.currentItem()
        if current is None:
            self._update_status("Välj ett alternativnamn att ta bort.")
            return

        row = self._alt_names_list.currentRow()
        remove_alternative_name(self._editing_place, row)
        self._refresh_alternative_names(self._editing_place)
        self._clear_status()

    def _refresh_alternative_names(self, place: Place) -> None:
        """Refresh the alternative names list display from the place model."""
        self._alt_names_list.clear()
        for name in place.alternative_names:
            self._alt_names_list.addItem(name)

    # ------------------------------------------------------------------
    # Private: parent combo population with hierarchy enforcement
    # ------------------------------------------------------------------

    def _populate_parent_combo(self, place_type: str) -> None:
        """Populate parent combo with valid parent places based on type hierarchy.

        For static types:
        - continent: no parent allowed
        - country: parent must be continent
        - church/cemetery/farm/school: parent can be any region-level type or ort
        - ort: parent can be any region-level type

        For dynamic region-level types:
        - order=1: parent must be country
        - order>1: parent must be preceding region level

        Args:
            place_type: The internal type string of the current place.
        """
        self._ui.parent_combo.clear()
        self._ui.parent_combo.addItem("(Ingen)", "")

        # Continent has no parent
        if place_type == "continent":
            return

        # Determine which types are valid parents
        valid_parent_types: set[str] = set()

        if place_type == "country":
            valid_parent_types = {"continent"}
        elif place_type in ("church", "cemetery", "farm", "school"):
            # Universal types can be children of any region level or ort
            valid_parent_types = {"ort"}
            # Add all region-level keys from countries in project
            for p in self._project_data.places:
                if p.type == "country":
                    valid_parent_types.update(self._get_region_keys_for_country(p))
        elif place_type == "ort":
            # Locality can be child of any region level
            for p in self._project_data.places:
                if p.type == "country":
                    valid_parent_types.update(self._get_region_keys_for_country(p))
        else:
            # Dynamic region-level type — find which country defines it
            for p in self._project_data.places:
                if p.type == "country":
                    region_levels = self._get_region_levels_for_country(p)
                    for rl in region_levels:
                        if rl.key == place_type:
                            if rl.order == 1:
                                valid_parent_types = {"country"}
                            else:
                                # Find preceding region level
                                for rl2 in region_levels:
                                    if rl2.order == rl.order - 1:
                                        valid_parent_types = {rl2.key}
                                        break
                            break
                    if valid_parent_types:
                        break
            # If we couldn't determine valid parent types, allow any place as parent
            if not valid_parent_types:
                valid_parent_types = {"country", "continent"}
                for p in self._project_data.places:
                    if p.type == "country":
                        valid_parent_types.update(self._get_region_keys_for_country(p))

        # Collect valid parent places with display text
        parent_entries: list[tuple[str, str]] = []
        for p in self._project_data.places:
            if p.type in valid_parent_types:
                # Don't allow a place to be its own parent
                if self._editing_place and p.id == self._editing_place.id:
                    continue
                # Show parent context to distinguish same-named places
                display = p.name
                if p.parent_place_id:
                    grandparent = self._find_place_by_id(p.parent_place_id)
                    if grandparent:
                        display = f"{p.name}, {grandparent.name}"
                parent_entries.append((display, p.id))

        # Sort alphabetically
        parent_entries.sort(key=lambda x: x[0].lower())
        for display, place_id in parent_entries:
            # Show map icon for places with coordinates
            p = self._find_place_by_id(place_id)
            if p and p.latitude is not None and p.longitude is not None:
                self._ui.parent_combo.addItem(QIcon(icon_registry.get_map_icon()), display, place_id)
            else:
                self._ui.parent_combo.addItem(display, place_id)

    def _get_region_levels_for_country(self, country_place: Place) -> list:
        """Get region levels for a country, checking presets if not set."""
        from slaktbusken.data.country_presets import get_preset

        if country_place.region_levels:
            return country_place.region_levels
        preset_name = _get_preset_name_for_country(country_place.name)
        if preset_name:
            return get_preset(preset_name)
        return []

    def _get_region_keys_for_country(self, country_place: Place) -> set[str]:
        """Get all region level keys for a country, checking presets if not set."""
        return {rl.key for rl in self._get_region_levels_for_country(country_place)}

    def _on_type_changed(self, index: int) -> None:
        """Handle type combo change to update parent combo options.

        Also updates preset section visibility and custom fields visibility.

        Args:
            index: The new index in the type combo.
        """
        type_label = self._ui.type_combo.currentText()
        internal_type = _resolve_type_label_to_internal(type_label, self._project_data)
        self._populate_parent_combo(internal_type)

        # Show preset section only for country type
        self._preset_group.setVisible(internal_type == "country")

        # Update custom fields visibility based on new type
        self._update_custom_fields_visibility(internal_type)

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
    # Private: preset and custom fields
    # ------------------------------------------------------------------

    def _on_preset_apply(self) -> None:
        """Handle preset apply button click.

        Populates the editing place's region_levels from the selected preset.
        The user can still modify them before saving.
        """
        if self._editing_place is None:
            self._update_status("Välj en plats först.")
            return

        preset_name = self._preset_combo.currentText()
        if preset_name == "(Välj förinställning)":
            self._update_status("Välj en förinställning att använda.")
            return

        levels = get_preset(preset_name)
        if not levels:
            self._update_status(f"Ingen förinställning hittades för '{preset_name}'.")
            return

        # Populate the editing place's region_levels
        self._editing_place.region_levels = levels
        self._refresh_region_levels_list(self._editing_place)
        self._clear_status()

    def _refresh_region_levels_list(self, place: Place) -> None:
        """Refresh the region levels list widget from the place's region_levels.

        Args:
            place: The place whose region levels should be displayed.
        """
        self._region_levels_list.clear()
        for rl in place.region_levels:
            custom_info = ""
            if rl.custom_fields:
                field_labels = ", ".join(cf.label for cf in rl.custom_fields)
                custom_info = f" [{field_labels}]"
            display = f"{rl.order}. {rl.label} (nyckel: {rl.key}){custom_info}"
            self._region_levels_list.addItem(display)

    def _update_custom_fields_visibility(self, internal_type: str) -> None:
        """Show or hide custom fields section based on place type.

        If the type matches a region level that has custom_fields defined,
        shows the custom fields group with appropriate input fields.

        Args:
            internal_type: The internal type string of the current place.
        """
        # Clear existing custom field inputs
        while self._custom_fields_layout.rowCount() > 0:
            self._custom_fields_layout.removeRow(0)
        self._custom_field_inputs.clear()

        # Find if any country defines this type as a region level with custom fields
        custom_fields_found: list[CustomFieldDef] = []
        for p in self._project_data.places:
            if p.type == "country":
                for rl in p.region_levels:
                    if rl.key == internal_type and rl.custom_fields:
                        custom_fields_found = rl.custom_fields
                        break
                if custom_fields_found:
                    break

        if not custom_fields_found:
            self._custom_fields_group.setVisible(False)
            return

        # Create input fields for each custom field definition
        for cf_def in custom_fields_found:
            line_edit = QLineEdit(self._custom_fields_group)
            line_edit.setMaxLength(20)
            line_edit.setPlaceholderText(f"Max 20 tecken")
            self._custom_fields_layout.addRow(f"{cf_def.label}:", line_edit)
            self._custom_field_inputs[cf_def.key] = line_edit

            # Pre-populate from editing place if available
            if self._editing_place and cf_def.key in self._editing_place.custom_field_values:
                line_edit.setText(self._editing_place.custom_field_values[cf_def.key])

        self._custom_fields_group.setVisible(True)

    def _on_show_place_on_map(self) -> None:
        """Open a map dialog showing the current place's coordinates."""
        from slaktbusken.services.map_data_service import MapMarker
        from slaktbusken.ui.dialogs.map_dialog import MapDialog

        lat = self._ui.latitude_spin.value()
        lng = self._ui.longitude_spin.value()
        name = self._ui.name_input.text() or "(namnlös plats)"

        marker = MapMarker(
            place_id="preview",
            place_name=name,
            latitude=lat,
            longitude=lng,
            events=[],
        )
        dialog = MapDialog([marker], f"Karta — {name}", parent=self)
        dialog.exec()

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
        internal_type = _resolve_type_label_to_internal(type_label, self._project_data)

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

        # External IDs (collected from in-memory edits on the editing place)
        external_ids = self._editing_place.external_ids if self._editing_place else []

        # Alternative Names (collected from in-memory edits on the editing place)
        alternative_names = self._editing_place.alternative_names if self._editing_place else []

        # Region levels (from in-memory edits on the editing place, only for countries)
        region_levels = []
        if internal_type == "country" and self._editing_place:
            region_levels = self._editing_place.region_levels

        # Custom field values (collected from UI inputs)
        custom_field_values: dict[str, str] = {}
        if self._custom_fields_group.isVisible():
            for key, line_edit in self._custom_field_inputs.items():
                value = line_edit.text().strip()
                if value:
                    custom_field_values[key] = value

        self._saved_place = Place(
            id=place_id,
            type=internal_type,
            name=name,
            parent_place_id=parent_place_id,
            latitude=latitude,
            longitude=longitude,
            notes=notes,
            external_ids=external_ids,
            alternative_names=alternative_names,
            region_levels=region_levels,
            custom_field_values=custom_field_values,
        )

        self._clear_status()
        logger.info("Plats sparad: %s (%s)", name, place_id)

        # Update the in-memory editing place reference
        self._editing_place = self._saved_place

        # Update the project data in-place
        for i, p in enumerate(self._project_data.places):
            if p.id == place_id:
                self._project_data.places[i] = self._saved_place
                break
        else:
            # New place — add to project
            self._project_data.places.append(self._saved_place)

        # Refresh place list so red dot indicator reflects updated parent assignment
        self._refresh_place_list()

        # Re-select the saved place in the list
        self._select_place_in_list(place_id)

        # Show confirmation in the status label instead of closing
        self._update_status("✔ Platsen sparad.")
        self._ui.status_label.setStyleSheet("color: green;")

        self.save_requested.emit()

    def _on_cancel(self) -> None:
        """Close the editor without saving."""
        self._saved_place = None
        self.cancel_requested.emit()
        self.close()

    # ------------------------------------------------------------------
    # Private: photo section
    # ------------------------------------------------------------------

    def _refresh_photo_section(self, place: Place) -> None:
        """Rebuild the PhotoSectionWidget for the given place.

        Creates or replaces the PhotoSectionWidget inside the photo group box,
        connecting its buttons to appropriate handlers.

        Args:
            place: The place whose photos should be displayed.
        """
        from slaktbusken.ui.widgets.photo_section_widget import PhotoSectionWidget

        # Remove existing photo section widget if present
        if self._photo_section is not None:
            self._photo_section_layout.removeWidget(self._photo_section)
            self._photo_section.setParent(None)
            self._photo_section.deleteLater()
            self._photo_section = None

        if self._photo_service is None:
            self._photo_group.setVisible(False)
            return

        # Create new PhotoSectionWidget for this place
        self._photo_section = PhotoSectionWidget(
            project_data=self._project_data,
            photo_service=self._photo_service,
            entity_type="place",
            entity_id=place.id,
            parent=self._photo_group,
        )
        self._photo_section_layout.addWidget(self._photo_section)

        # Connect button signals
        self._photo_section.add_button.clicked.connect(self._on_photo_add)
        if self._photo_section.view_button:
            self._photo_section.view_button.clicked.connect(self._on_photo_view)
        self._photo_section.photo_edited.connect(self._on_photo_edit)

        self._photo_group.setVisible(True)

    def _on_photo_add(self) -> None:
        """Handle 'Lägg till foto' button click in the photo section.

        Opens a file dialog filtered to image formats. On file selection,
        creates a new MediaItem with type 'photo' and a LinkedEntity
        linking it to the current place.
        """
        if self._editing_place is None or self._photo_service is None:
            return

        file_filter = "Bildfiler (*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.tif)"
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Välj bild",
            "",
            file_filter,
        )

        if not file_path:
            # User cancelled — do nothing (Requirement 9.7)
            return

        from slaktbusken.model.media import LinkedEntity, MediaItem

        # Create the new MediaItem
        new_media = MediaItem(
            id=str(uuid.uuid4()),
            type="photo",
            file=file_path,
            title=Path(file_path).stem,
            linked_entities=[
                LinkedEntity(entity_type="place", entity_id=self._editing_place.id)
            ],
        )

        # Add to project data
        self._project_data.media.append(new_media)

        # Refresh the photo section and emit signal
        if self._photo_section is not None:
            self._photo_section.refresh()
            self._photo_section.emit_photo_added(new_media.id)

    def _on_photo_view(self) -> None:
        """Handle 'Visa foto' button click.

        Opens a modal dialog showing the selected photo's image file.
        """
        if self._photo_section is None or self._photo_service is None:
            return

        photo_id = self._photo_section.get_selected_photo_id()
        if photo_id is None:
            return

        # Find the MediaItem
        media_item = self._find_media_item_by_id(photo_id)
        if media_item is None:
            return

        # Resolve the file path
        file_path = Path(media_item.file)
        if not file_path.is_absolute():
            file_path = self._photo_service._foto_mapp / file_path

        if not file_path.exists():
            QMessageBox.warning(
                self,
                "Fil saknas",
                f"Bildfilen kunde inte hittas:\n{file_path}",
            )
            return

        # Open a modal image viewer dialog
        from PySide6.QtGui import QPixmap

        dialog = QDialog(self)
        dialog.setWindowTitle(media_item.title)
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)

        pixmap = QPixmap(str(file_path))
        if pixmap.isNull():
            QMessageBox.warning(
                self,
                "Kan inte visa",
                f"Bildfilen kunde inte läsas:\n{file_path}",
            )
            return

        # Scale to reasonable size while keeping aspect ratio
        scaled = pixmap.scaled(800, 600, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        image_label = QLabel()
        image_label.setPixmap(scaled)
        layout.addWidget(image_label)

        close_btn = QPushButton("Stäng")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)

        dialog.exec()

    def _on_photo_edit(self, media_item_id: str) -> None:
        """Handle 'Redigera foto' button click.

        Opens EditPhotoDialog with the selected MediaItem.

        Args:
            media_item_id: The ID of the MediaItem to edit.
        """
        if self._photo_service is None:
            return

        media_item = self._find_media_item_by_id(media_item_id)
        if media_item is None:
            return

        from slaktbusken.ui.dialogs.edit_photo_dialog import EditPhotoDialog

        dialog = EditPhotoDialog(
            media_item=media_item,
            project_data=self._project_data,
            photo_service=self._photo_service,
            parent=self,
        )
        dialog.exec()

        # Refresh photo section after dialog closes (changes may have been saved)
        if self._photo_section is not None:
            self._photo_section.refresh()

    def _find_media_item_by_id(self, media_id: str) -> "Optional[MediaItem]":
        """Find a MediaItem by its ID in the project data.

        Args:
            media_id: The MediaItem ID to search for.

        Returns:
            The MediaItem if found, None otherwise.
        """
        from slaktbusken.model.media import MediaItem

        for item in self._project_data.media:
            if item.id == media_id:
                return item
        return None

    # ------------------------------------------------------------------
    # Private: helpers
    # ------------------------------------------------------------------

    def _update_status(self, message: str) -> None:
        """Update the status label text with an error/info message.

        Args:
            message: The status message to display.
        """
        self._ui.status_label.setStyleSheet("color: red;")
        self._ui.status_label.setText(message)

    def _clear_status(self) -> None:
        """Clear the status label."""
        self._ui.status_label.setText("")
        self._ui.status_label.setStyleSheet("")
