"""Dedicated photo management tab for PersonEditor.

Displays a list of photos linked to a person, showing each photo's
Foto_Typ label and title separately. Shows an empty state message
when no photos are linked. Provides functionality to add new photos,
edit photo metadata (title, Foto_Typ), and manage persons in the photo.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedLayout,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.person import Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.photo_service import PhotoService
from slaktbusken.ui.widgets.person_list_widget import PersonListWidget


class FotoTab(QWidget):
    """Photo management tab displaying photos linked to a person.

    Shows a table with Foto_Typ and Title columns, or an empty state
    message when no photos are linked. Allows adding new photos via
    a file dialog with validation and conflict resolution. When a photo
    is selected, displays editable metadata fields and a person list
    management section ("Personer i bilden").

    Args:
        project_data: The project data containing all media items.
        person: The person whose photos are displayed.
        photo_service: Service for retrieving and parsing photo data.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        project_data: ProjectData,
        person: Person,
        photo_service: PhotoService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._project_data = project_data
        self._person = person
        self._photo_service = photo_service

        # Track currently selected media item
        self._selected_media_item: MediaItem | None = None

        self._setup_ui()
        self._connect_signals()
        self.refresh()

    def _connect_signals(self) -> None:
        """Connect internal widget signals."""
        self._table.itemSelectionChanged.connect(self._on_photo_selected)
        self._person_list_widget.persons_changed.connect(
            self._on_persons_changed
        )
        self._delete_button.clicked.connect(self._on_delete_photo)

    def _setup_ui(self) -> None:
        """Create the UI layout with button, table, empty state, editing panel, and person list."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Button row at top
        btn_layout = QHBoxLayout()
        self._add_button = QPushButton("Lägg till foto")
        self._add_button.clicked.connect(self._on_add_photo)
        btn_layout.addWidget(self._add_button)

        self._delete_button = QPushButton("Ta bort foto")
        self._delete_button.setEnabled(False)
        btn_layout.addWidget(self._delete_button)

        layout.addLayout(btn_layout)

        # Stacked layout to switch between table and empty state
        self._stack_widget = QWidget()
        self._stack_layout = QStackedLayout(self._stack_widget)

        # Photo table
        self._table = QTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["Fototyp", "Titel", "Fil"])
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._table.verticalHeader().setVisible(False)

        header = self._table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)

        self._stack_layout.addWidget(self._table)

        # Empty state message
        self._empty_label = QLabel(
            "Inga foton är kopplade till denna person.\n"
            "Lägg till ett foto med knappen ovan."
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._stack_layout.addWidget(self._empty_label)

        layout.addWidget(self._stack_widget)

        # Preview window (separate non-modal popup)
        self._preview_window: QWidget | None = None
        self._preview_image_label: QLabel | None = None

        # --- Metadata editing panel ---
        self._edit_group = QGroupBox("Redigera foto")
        edit_layout = QFormLayout(self._edit_group)

        self._edit_title_input = QLineEdit()
        self._edit_title_input.setMaxLength(200)
        self._edit_title_input.setPlaceholderText("Titel (1–200 tecken)")
        edit_layout.addRow("Titel:", self._edit_title_input)

        self._edit_typ_combo = QComboBox()
        self._edit_typ_combo.addItems(PhotoService.FOTO_TYPES)
        edit_layout.addRow("Fototyp:", self._edit_typ_combo)

        # Save button
        save_layout = QHBoxLayout()
        save_layout.addStretch()
        self._save_edit_button = QPushButton("Spara ändringar")
        self._save_edit_button.clicked.connect(self._on_save_metadata)
        save_layout.addWidget(self._save_edit_button)
        edit_layout.addRow(save_layout)

        # Status label for validation messages
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: red;")
        self._status_label.setWordWrap(True)
        edit_layout.addRow(self._status_label)

        self._edit_group.setVisible(False)
        layout.addWidget(self._edit_group)

        # --- Person list section (Personer i bilden) ---
        self._person_list_group = QGroupBox("Personer i bilden")
        person_group_layout = QVBoxLayout(self._person_list_group)

        self._person_list_widget = PersonListWidget(
            self._project_data, parent=self
        )
        person_group_layout.addWidget(self._person_list_widget)

        # Save persons button
        self._save_persons_btn = QPushButton("Spara personlista")
        self._save_persons_btn.clicked.connect(self._on_save_persons)
        self._save_persons_btn.setEnabled(False)
        person_group_layout.addWidget(self._save_persons_btn)

        self._person_list_group.setVisible(False)
        layout.addWidget(self._person_list_group)

    def _on_photo_selected(self) -> None:
        """Handle photo selection in the table.

        Loads the selected photo's metadata into editing fields and
        person list into the PersonListWidget, and shows both sections.
        Shows a preview of the selected image.
        """
        self._clear_status()
        selected_items = self._table.selectedItems()
        if not selected_items:
            self._edit_group.setVisible(False)
            self._person_list_group.setVisible(False)
            self._close_preview_window()
            self._selected_media_item = None
            self._person_list_widget.clear()
            self._delete_button.setEnabled(False)
            return

        # Get media_item id from the first column's UserRole data
        row = self._table.currentRow()
        typ_item = self._table.item(row, 0)
        if typ_item is None:
            return

        media_id = typ_item.data(Qt.ItemDataRole.UserRole)
        if not media_id:
            return

        # Find the MediaItem
        media_item = self._find_media_item(media_id)
        if media_item is None:
            return

        self._selected_media_item = media_item

        # Show image preview
        self._show_preview(media_item)

        # Populate metadata editing fields
        foto_typ, title = self._photo_service.parse_title(media_item.title)
        self._edit_title_input.setText(title)

        type_index = self._edit_typ_combo.findText(foto_typ)
        if type_index >= 0:
            self._edit_typ_combo.setCurrentIndex(type_index)
        else:
            # Fallback to "Övrigt foto" if type not found in list
            fallback_index = self._edit_typ_combo.findText("Övrigt foto")
            self._edit_typ_combo.setCurrentIndex(
                fallback_index if fallback_index >= 0 else 0
            )

        self._edit_group.setVisible(True)

        # Populate person list
        self._person_list_widget.load_for_media_item(media_item)
        self._person_list_group.setVisible(True)
        self._save_persons_btn.setEnabled(False)
        self._delete_button.setEnabled(True)

    def _on_save_metadata(self) -> None:
        """Validate and save edited metadata for the selected photo.

        Checks title length (1–200 chars) and updates the MediaItem's title
        field using the format [Foto_Typ] title. Displays status bar message
        on validation errors. Retains unsaved edits in fields on failure.
        """
        self._clear_status()

        if self._selected_media_item is None:
            return

        # Get values from editing fields
        new_title = self._edit_title_input.text().strip()
        new_foto_typ = self._edit_typ_combo.currentText()

        # Validate title length (1–200 characters)
        if not new_title or len(new_title) > 200:
            self._update_status("Titel måste vara 1–200 tecken.")
            return

        # Format and update the MediaItem title
        formatted_title = self._photo_service.format_title(new_foto_typ, new_title)

        try:
            self._selected_media_item.title = formatted_title
        except Exception as e:
            self._update_status(f"Kunde inte spara: {e}")
            return

        self._clear_status()
        self.refresh()

    def _update_status(self, message: str) -> None:
        """Display a status message in the editing panel.

        Args:
            message: The status message to display.
        """
        self._status_label.setText(message)

    def _clear_status(self) -> None:
        """Clear the status label."""
        self._status_label.setText("")

    def _on_persons_changed(self) -> None:
        """Enable save button when person list is modified."""
        self._save_persons_btn.setEnabled(True)

    def _on_save_persons(self) -> None:
        """Save the current person list to the selected media item.

        Updates mentioned_person_ids and mentioned_names on the MediaItem,
        then syncs Linked_Entity records via PhotoService.
        """
        if self._selected_media_item is None:
            return

        # Get updated lists from widget
        new_person_ids = self._person_list_widget.get_person_ids()
        new_mentioned_names = self._person_list_widget.get_mentioned_names()

        # Update MediaItem fields
        self._selected_media_item.mentioned_person_ids = new_person_ids
        self._selected_media_item.mentioned_names = new_mentioned_names

        # Sync Linked_Entity records with PhotoService
        self._photo_service.sync_linked_entities(
            self._selected_media_item, new_person_ids
        )

        self._save_persons_btn.setEnabled(False)

        # Refresh table in case linked entities changed visibility
        self.refresh()

    def flush_pending_person_list(self) -> None:
        """Flush pending person-list changes to the selected MediaItem.

        Called by PersonEditor._on_save() to ensure pending changes
        are persisted before the save completes.
        """
        if self._save_persons_btn.isEnabled():
            self._on_save_persons()

    def _on_delete_photo(self) -> None:
        """Handle photo deletion/unlinking from the current person.

        Shows a confirmation dialog, removes the LinkedEntity for the
        current person from the selected MediaItem, removes the person
        from mentioned_person_ids, and if no linked_entities remain,
        removes the entire MediaItem from project_data.media.
        """
        if self._selected_media_item is None:
            return

        # Confirmation dialog
        reply = QMessageBox.question(
            self,
            "Ta bort foto",
            "Vill du ta bort kopplingen mellan detta foto och personen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        media_item = self._selected_media_item

        # Remove LinkedEntity for this person
        media_item.linked_entities = [
            le
            for le in media_item.linked_entities
            if not (le.entity_type == "person" and le.entity_id == self._person.id)
        ]

        # Remove person from mentioned_person_ids
        if self._person.id in media_item.mentioned_person_ids:
            media_item.mentioned_person_ids = [
                pid
                for pid in media_item.mentioned_person_ids
                if pid != self._person.id
            ]

        # If no linked_entities remain, remove the entire MediaItem
        if not media_item.linked_entities:
            self._project_data.media = [
                m for m in self._project_data.media if m.id != media_item.id
            ]

        # Clear selection and refresh
        self._selected_media_item = None
        self.refresh()

    def _find_media_item(self, media_id: str) -> MediaItem | None:
        """Find a MediaItem by id in project data."""
        for item in self._project_data.media:
            if item.id == media_id:
                return item
        return None

    def _resolve_media_file_path(self, media_item: MediaItem) -> Path | None:
        """Resolve a MediaItem's file field to an absolute path on disk.

        Tries the path relative to the project folder (foto_mapp's grandparent),
        then falls back to relative to foto_mapp directly.

        Returns:
            The resolved Path if the file exists, or None.
        """
        foto_mapp = self._photo_service._foto_mapp
        # Project folder is foto_mapp's grandparent (media/photos -> media -> project)
        project_folder = foto_mapp.parent.parent

        # Strategy 1: relative to project folder (e.g. "media/photos/photo.jpg")
        candidate = project_folder / Path(media_item.file)
        if candidate.is_file():
            return candidate

        # Strategy 2: relative to foto_mapp directly (legacy, e.g. "photo.jpg")
        candidate = foto_mapp / Path(media_item.file)
        if candidate.is_file():
            return candidate

        return None

    def _show_preview(self, media_item: MediaItem) -> None:
        """Show the selected photo in a separate non-modal preview window.

        Creates or updates a popup window displaying the full image.
        The window stays open until another photo is selected or deselected.

        Args:
            media_item: The MediaItem to preview.
        """
        file_path = self._resolve_media_file_path(media_item)

        if file_path is None:
            self._close_preview_window()
            return

        pixmap = QPixmap(str(file_path))
        if pixmap.isNull():
            self._close_preview_window()
            return

        # Create or reuse preview window
        if self._preview_window is None:
            from PySide6.QtWidgets import QDialog
            self._preview_window = QDialog(self)
            self._preview_window.setWindowTitle("Förhandsgranskning")
            self._preview_window.setModal(False)
            preview_layout = QVBoxLayout(self._preview_window)
            preview_layout.setContentsMargins(0, 0, 0, 0)
            self._preview_image_label = QLabel()
            self._preview_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._preview_image_label.setStyleSheet("background: #222;")
            preview_layout.addWidget(self._preview_image_label)

        # Scale image to fit a reasonable window size
        max_w, max_h = 800, 600
        scaled = pixmap.scaled(
            max_w, max_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._preview_image_label.setPixmap(scaled)

        # Resize window to fit the scaled image
        self._preview_window.resize(scaled.width() + 2, scaled.height() + 2)

        # Update window title with filename
        _, title = self._photo_service.parse_title(media_item.title)
        self._preview_window.setWindowTitle(f"Förhandsgranskning – {title}")

        self._preview_window.show()
        self._preview_window.raise_()

    def _close_preview_window(self) -> None:
        """Close the preview window if open."""
        if self._preview_window is not None:
            self._preview_window.close()
            self._preview_window = None

    def refresh(self) -> None:
        """Reload the photo list from PhotoService.

        Fetches photos linked to the current person, populates the
        table with Foto_Typ and title columns, and toggles between
        table view and empty state as appropriate.
        """
        photos = self._photo_service.get_photos_for_person(self._person.id)

        self._table.setRowCount(0)

        if not photos:
            self._stack_layout.setCurrentWidget(self._empty_label)
            self._edit_group.setVisible(False)
            self._person_list_group.setVisible(False)
            self._close_preview_window()
            self._selected_media_item = None
            self._person_list_widget.clear()
            self._delete_button.setEnabled(False)
            return

        self._stack_layout.setCurrentWidget(self._table)
        self._table.setRowCount(len(photos))

        for row, media_item in enumerate(photos):
            foto_typ, title = self._photo_service.parse_title(media_item.title)

            typ_item = QTableWidgetItem(foto_typ)
            typ_item.setData(Qt.ItemDataRole.UserRole, media_item.id)
            self._table.setItem(row, 0, typ_item)

            title_item = QTableWidgetItem(title)
            self._table.setItem(row, 1, title_item)

            file_item = QTableWidgetItem(media_item.file)
            self._table.setItem(row, 2, file_item)

        # Re-select previously selected item if still present
        if self._selected_media_item:
            for row in range(self._table.rowCount()):
                item = self._table.item(row, 0)
                if (
                    item
                    and item.data(Qt.ItemDataRole.UserRole)
                    == self._selected_media_item.id
                ):
                    self._table.selectRow(row)
                    return

        # If no re-selection, hide editing panels
        self._edit_group.setVisible(False)
        self._person_list_group.setVisible(False)
        self._close_preview_window()
        self._selected_media_item = None
        self._person_list_widget.clear()
        self._delete_button.setEnabled(False)

    def _build_file_filter(self) -> str:
        """Build file dialog filter string from allowed extensions."""
        extensions = " ".join(
            f"*{ext}" for ext in sorted(PhotoService.ALLOWED_EXTENSIONS)
        )
        return f"Bildfiler ({extensions})"

    def _on_add_photo(self) -> None:
        """Handle the photo addition flow.

        Opens a file dialog, validates the extension, prompts for title
        and Foto_Typ, handles file conflicts, copies the file if needed,
        and creates a new MediaItem linked to the current person.
        """
        # Step 1: Open file dialog
        file_filter = self._build_file_filter()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Välj foto",
            "",
            file_filter,
        )

        if not file_path:
            return  # User cancelled

        # Step 2: Validate extension
        if not self._photo_service.validate_file_extension(file_path):
            allowed = ", ".join(sorted(PhotoService.ALLOWED_EXTENSIONS))
            QMessageBox.warning(
                self,
                "Ogiltigt filformat",
                f"Filformatet stöds inte.\n\nAccepterade format: {allowed}",
            )
            return

        # Step 3: Prompt for title
        title, ok = QInputDialog.getText(
            self,
            "Ange titel",
            "Titel för fotot:",
        )
        if not ok:
            return  # User cancelled

        # Validate title length (1-200 characters)
        title = title.strip()
        if not title or len(title) > 200:
            QMessageBox.warning(
                self,
                "Ogiltig titel",
                "Titel måste vara 1\u2013200 tecken.",
            )
            return

        # Step 4: Prompt for Foto_Typ selection
        foto_types = PhotoService.FOTO_TYPES
        default_index = len(foto_types) - 1  # "Övrigt foto" is last
        foto_typ, ok = QInputDialog.getItem(
            self,
            "Välj fototyp",
            "Fototyp:",
            foto_types,
            default_index,
            False,  # not editable
        )
        if not ok:
            return  # User cancelled

        # Step 5: Compute target path and handle file operations
        source = Path(file_path)
        target_path, needs_copy = self._photo_service.compute_target_path(source)

        if needs_copy:
            # Ensure Foto_Mapp exists
            foto_mapp = self._photo_service._foto_mapp
            try:
                foto_mapp.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                QMessageBox.critical(
                    self,
                    "Fel",
                    f"Kunde inte skapa mappen Foto_Mapp:\n{e}",
                )
                return

            # Check for file conflict
            if target_path.exists():
                result = self._show_conflict_dialog(target_path)
                if result == "cancel":
                    return
                elif result == "rename":
                    target_path = self._photo_service.resolve_filename_conflict(
                        target_path
                    )
                # "overwrite" -> proceed with existing target_path

            # Copy file
            try:
                shutil.copy2(str(source), str(target_path))
            except OSError as e:
                QMessageBox.critical(
                    self,
                    "Fel",
                    f"Kunde inte kopiera filen:\n{e}",
                )
                return

            # Store path relative to project folder (media/photos/filename)
            relative_in_mapp = target_path.relative_to(foto_mapp)
            relative_path = Path("media/photos") / relative_in_mapp
        else:
            # File already in Foto_Mapp, target_path is relative within foto_mapp
            relative_path = Path("media/photos") / target_path

        # Step 6: Create MediaItem
        formatted_title = self._photo_service.format_title(foto_typ, title)
        media_item = MediaItem(
            id=str(uuid.uuid4()),
            type="photo",
            file=relative_path.as_posix(),
            title=formatted_title,
            mentioned_person_ids=[self._person.id],
            linked_entities=[
                LinkedEntity(
                    entity_type="person",
                    entity_id=self._person.id,
                )
            ],
        )

        self._project_data.media.append(media_item)

        # Step 7: Refresh display
        self.refresh()

    def _show_conflict_dialog(self, target_path: Path) -> str:
        """Show dialog for file conflict resolution.

        Returns:
            "overwrite", "rename", or "cancel".
        """
        msg = QMessageBox(self)
        msg.setWindowTitle("Filkonflikt")
        msg.setText(
            f"Filen '{target_path.name}' finns redan i Foto_Mapp."
        )
        msg.setInformativeText("Vad vill du g\u00f6ra?")

        overwrite_btn = msg.addButton(
            "Skriv \u00f6ver", QMessageBox.ButtonRole.DestructiveRole
        )
        rename_btn = msg.addButton(
            "Byt namn", QMessageBox.ButtonRole.AcceptRole
        )
        cancel_btn = msg.addButton(
            "Avbryt", QMessageBox.ButtonRole.RejectRole
        )

        msg.setDefaultButton(cancel_btn)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == overwrite_btn:
            return "overwrite"
        elif clicked == rename_btn:
            return "rename"
        return "cancel"
