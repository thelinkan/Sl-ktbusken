"""Source translation editor widget.

Provides a searchable list of GEDCOM→App_JSON source mappings with
add/edit/remove/save functionality. Validates that target App_JSON
source records exist before persisting changes. All UI text is in Swedish.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QTableWidgetItem, QWidget

from slaktbusken.model.project import ProjectData
from slaktbusken.persistence.translation_io import SourceMapping, TranslationData
from slaktbusken.services.translation_service import (
    TranslationService,
    TranslationServiceError,
)
from slaktbusken.ui.generated.ui_source_translation_editor import (
    Ui_SourceTranslationEditor,
)

logger = logging.getLogger(__name__)


class SourceTranslationEditor(QWidget):
    """Editor widget for GEDCOM source → App_JSON source translation mappings.

    Displays a searchable table of existing source mappings and provides
    controls to add, edit, and remove entries. Validates that the target
    App_JSON source exists in the project before saving.

    Args:
        translation_service: Service for loading/saving translation files.
        project_data: The current project data containing available sources.
        project_path: Path to the project file or directory.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        translation_service: TranslationService,
        project_data: ProjectData,
        project_path: Path,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the source translation editor.

        Args:
            translation_service: Service for loading/saving translation files.
            project_data: The current project data containing available sources.
            project_path: Path to the project file or directory.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._translation_service = translation_service
        self._project_data = project_data
        self._project_path = project_path

        self._translation_data: TranslationData | None = None
        self._dirty: bool = False
        self._editing_row: int | None = None

        # Set up UI from generated form
        self._ui = Ui_SourceTranslationEditor()
        self._ui.setupUi(self)

        self._setup_table()
        self._populate_source_combo()
        self._connect_signals()

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

    def _populate_source_combo(self) -> None:
        """Fill the App_JSON source combo box with available project sources."""
        combo = self._ui.app_source_combo
        combo.clear()
        combo.addItem("", "")  # Empty default entry
        for source in self._project_data.sources:
            display = f"{source.id} — {source.title}" if source.title else source.id
            combo.addItem(display, source.id)

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
        self._ui.app_source_combo.currentIndexChanged.connect(
            self._update_validation_indicator
        )

    # ------------------------------------------------------------------
    # Private: table management
    # ------------------------------------------------------------------

    def _refresh_table(self) -> None:
        """Rebuild the table contents from current translation data."""
        table = self._ui.mapping_table
        table.setRowCount(0)

        if self._translation_data is None:
            return

        for mapping in self._translation_data.sources:
            self._add_table_row(mapping)

    def _add_table_row(self, mapping: SourceMapping) -> None:
        """Append a single mapping row to the table.

        Args:
            mapping: The source mapping to display.
        """
        table = self._ui.mapping_table
        row = table.rowCount()
        table.insertRow(row)

        gedcom_item = QTableWidgetItem(mapping.gedcom_id)
        gedcom_item.setFlags(
            Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        )

        title_display = mapping.title if mapping.title else mapping.app_id
        title_item = QTableWidgetItem(title_display)
        title_item.setFlags(
            Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        )

        table.setItem(row, 0, gedcom_item)
        table.setItem(row, 1, title_item)

    # ------------------------------------------------------------------
    # Private: search / filter
    # ------------------------------------------------------------------

    def _on_search_changed(self, text: str) -> None:
        """Filter visible table rows based on search text.

        Case-insensitive substring match on GEDCOM ID or title.

        Args:
            text: The current search string.
        """
        search = text.lower()
        table = self._ui.mapping_table

        for row in range(table.rowCount()):
            gedcom_text = (table.item(row, 0).text() or "").lower()
            title_text = (table.item(row, 1).text() or "").lower()
            visible = search in gedcom_text or search in title_text
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

        if 0 <= row < len(self._translation_data.sources):
            mapping = self._translation_data.sources[row]
            self._ui.gedcom_id_input.setText(mapping.gedcom_id)

            # Select matching combo entry
            combo = self._ui.app_source_combo
            for i in range(combo.count()):
                if combo.itemData(i) == mapping.app_id:
                    combo.setCurrentIndex(i)
                    break

    def _on_add(self) -> None:
        """Add a new source mapping from the edit fields."""
        gedcom_id = self._ui.gedcom_id_input.text().strip()
        app_id = self._ui.app_source_combo.currentData()

        if not gedcom_id:
            self._update_status("Ange ett GEDCOM-ID.")
            return

        if not app_id:
            self._update_status("Välj en App_JSON-källa.")
            return

        if not self._validate_target(app_id):
            return

        # Find title for display
        title = self._get_source_title(app_id)

        new_mapping = SourceMapping(
            gedcom_id=gedcom_id, app_id=app_id, title=title
        )

        if self._translation_data is None:
            self._translation_data = TranslationData()

        # Check for duplicate GEDCOM ID
        for i, existing in enumerate(self._translation_data.sources):
            if existing.gedcom_id == gedcom_id:
                self._update_status(
                    f"GEDCOM-ID '{gedcom_id}' finns redan. "
                    "Använd Redigera för att ändra."
                )
                return

        self._translation_data.sources.append(new_mapping)
        self._add_table_row(new_mapping)
        self._mark_dirty()
        self._clear_edit_fields()
        self._update_status(f"Mappning tillagd: {gedcom_id} → {app_id}")

    def _on_edit(self) -> None:
        """Update the currently selected mapping with edited values."""
        selected = self._ui.mapping_table.selectedItems()
        if not selected:
            self._update_status("Välj en rad att redigera.")
            return

        row = selected[0].row()
        if self._translation_data is None or row >= len(
            self._translation_data.sources
        ):
            return

        gedcom_id = self._ui.gedcom_id_input.text().strip()
        app_id = self._ui.app_source_combo.currentData()

        if not gedcom_id:
            self._update_status("Ange ett GEDCOM-ID.")
            return

        if not app_id:
            self._update_status("Välj en App_JSON-källa.")
            return

        if not self._validate_target(app_id):
            return

        title = self._get_source_title(app_id)

        # Update the mapping
        self._translation_data.sources[row] = SourceMapping(
            gedcom_id=gedcom_id, app_id=app_id, title=title
        )

        # Update table display
        self._ui.mapping_table.item(row, 0).setText(gedcom_id)
        self._ui.mapping_table.item(row, 1).setText(title or app_id)

        self._mark_dirty()
        self._update_status(f"Mappning uppdaterad: {gedcom_id} → {app_id}")

    def _on_remove(self) -> None:
        """Remove the currently selected mapping."""
        selected = self._ui.mapping_table.selectedItems()
        if not selected:
            self._update_status("Välj en rad att ta bort.")
            return

        row = selected[0].row()
        if self._translation_data is None or row >= len(
            self._translation_data.sources
        ):
            return

        removed = self._translation_data.sources.pop(row)
        self._ui.mapping_table.removeRow(row)
        self._mark_dirty()
        self._update_status(f"Mappning borttagen: {removed.gedcom_id}")

    def _on_save(self) -> None:
        """Persist all mappings to disk.

        Validates all mappings before saving. On file system errors,
        displays a Swedish-language error message and retains unsaved
        changes in the editor.
        """
        if self._translation_data is None:
            self._update_status("Inga data att spara.")
            return

        # Validate all mappings before saving
        invalid = self._find_invalid_mappings()
        if invalid:
            ids = ", ".join(invalid)
            self._update_status(
                f"Ogiltiga mappningar (mål saknas): {ids}. Åtgärda innan du sparar."
            )
            return

        try:
            self._translation_service.save_translations(
                self._translation_data, self._project_path
            )
            self._dirty = False
            self._update_status("Översättningar sparade.")
            logger.info("Källöversättningar sparade till disk.")
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
            logger.error("Kunde inte spara källöversättningar: %s", exc)
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
            logger.error("Filsystemfel vid sparning av källöversättningar: %s", exc)

    # ------------------------------------------------------------------
    # Private: validation
    # ------------------------------------------------------------------

    def _validate_target(self, app_id: str) -> bool:
        """Check that the target App_JSON source ID exists in project data.

        Args:
            app_id: The App_JSON source ID to validate.

        Returns:
            True if the source exists, False otherwise (with UI feedback).
        """
        if any(s.id == app_id for s in self._project_data.sources):
            self._ui.validation_indicator.setText("✓ Giltig källa")
            self._ui.validation_indicator.setStyleSheet("color: green;")
            return True

        self._ui.validation_indicator.setText("✗ Källa saknas i projektet")
        self._ui.validation_indicator.setStyleSheet("color: red;")
        self._update_status(
            f"App_JSON-källa '{app_id}' finns inte i projektets källregister."
        )
        return False

    def _update_validation_indicator(self) -> None:
        """Update the validation indicator when the combo selection changes."""
        app_id = self._ui.app_source_combo.currentData()
        if not app_id:
            self._ui.validation_indicator.setText("")
            self._ui.validation_indicator.setStyleSheet("")
            return

        if any(s.id == app_id for s in self._project_data.sources):
            self._ui.validation_indicator.setText("✓ Giltig källa")
            self._ui.validation_indicator.setStyleSheet("color: green;")
        else:
            self._ui.validation_indicator.setText("✗ Källa saknas i projektet")
            self._ui.validation_indicator.setStyleSheet("color: red;")

    def _find_invalid_mappings(self) -> list[str]:
        """Find mappings whose target App_JSON source doesn't exist.

        Returns:
            List of GEDCOM IDs with invalid targets.
        """
        if self._translation_data is None:
            return []

        valid_ids = {s.id for s in self._project_data.sources}
        return [
            m.gedcom_id
            for m in self._translation_data.sources
            if m.app_id not in valid_ids
        ]

    # ------------------------------------------------------------------
    # Private: helpers
    # ------------------------------------------------------------------

    def _get_source_title(self, app_id: str) -> str:
        """Look up the human-readable title for an App_JSON source ID.

        Args:
            app_id: The App_JSON source ID.

        Returns:
            The source title, or empty string if not found.
        """
        for source in self._project_data.sources:
            if source.id == app_id:
                return source.title
        return ""

    def _mark_dirty(self) -> None:
        """Mark the editor as having unsaved changes."""
        self._dirty = True

    def _clear_edit_fields(self) -> None:
        """Reset the edit input fields to empty state."""
        self._ui.gedcom_id_input.clear()
        self._ui.app_source_combo.setCurrentIndex(0)
        self._ui.validation_indicator.setText("")
        self._ui.validation_indicator.setStyleSheet("")

    def _update_status(self, message: str) -> None:
        """Update the status label text.

        Args:
            message: The status message to display.
        """
        self._ui.status_label.setText(message)
