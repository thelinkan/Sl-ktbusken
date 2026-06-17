"""Media editor widget.

Provides a split-panel editor for MediaItem records: a filterable media
list on the left, and a form on the right with file selection, media type,
title, linked entities management, and type-specific fields (publication
info, transcription, mentioned persons).
Validates that title, file, and at least one linked entity are set before
saving a new item. All UI text is in Swedish.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QListWidgetItem, QMessageBox, QWidget

from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.project import ProjectData
from slaktbusken.ui.generated.ui_media_editor import Ui_MediaEditor

logger = logging.getLogger(__name__)

# Media type mapping: internal key -> Swedish display name
MEDIA_TYPE_MAP: dict[str, str] = {
    "photo": "Foto",
    "source_image": "Källbild",
    "death_notice": "Dödsannons",
    "obituary": "Nekrolog",
    "funeral_program": "Begravningsprogram",
    "grave_photo": "Gravfoto",
    "map": "Karta",
    "logo": "Logotyp",
    "document": "Dokument",
}

# Reverse mapping: Swedish display name -> internal key
MEDIA_TYPE_REVERSE: dict[str, str] = {v: k for k, v in MEDIA_TYPE_MAP.items()}

# Entity type mapping: internal key -> Swedish display name
ENTITY_TYPE_MAP: dict[str, str] = {
    "person": "Person",
    "event": "Händelse",
    "source": "Källa",
    "place": "Plats",
}

# Reverse mapping: Swedish display name -> internal key
ENTITY_TYPE_REVERSE: dict[str, str] = {v: k for k, v in ENTITY_TYPE_MAP.items()}

# Types that show publication fields (newspaper, date, page)
PUBLICATION_TYPES: set[str] = {"death_notice", "obituary"}

# Types that show transcription field
TRANSCRIPTION_TYPES: set[str] = {
    "source_image",
    "death_notice",
    "obituary",
    "funeral_program",
    "document",
}

# Types that show mentioned persons
MENTIONED_TYPES: set[str] = {
    "photo",
    "source_image",
    "death_notice",
    "obituary",
    "funeral_program",
    "grave_photo",
    "document",
}


class MediaEditor(QWidget):
    """Editor widget for MediaItem records with list and form panels.

    Displays a filterable media list on the left and a full edit form on the
    right. Type-specific fields dynamically show/hide depending on the
    selected media type.

    Args:
        project_data: The current project data containing all entities.
        media_item: Optional existing MediaItem to edit. If None, creates new.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        project_data: ProjectData,
        media_item: Optional[MediaItem] = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the media editor.

        Args:
            project_data: The current project data containing all entities.
            media_item: Optional existing MediaItem to edit. If None, creates new.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._project_data = project_data
        self._media_item = media_item
        self._saved_media: Optional[MediaItem] = None
        self._is_new = media_item is None

        # Set up UI from generated form
        self._ui = Ui_MediaEditor()
        self._ui.setupUi(self)

        self._populate_type_combo()
        self._populate_entity_type_combo()
        self._connect_signals()
        self._update_type_specific_fields()
        self._refresh_media_list()

        if self._media_item is not None:
            self._load_media_item()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def saved_media(self) -> Optional[MediaItem]:
        """The saved MediaItem result, or None if not yet saved."""
        return self._saved_media

    def get_media_item(self) -> Optional[MediaItem]:
        """Return the saved media item, or None if save was not performed.

        Returns:
            The MediaItem object if save was successful, None otherwise.
        """
        return self._saved_media

    # ------------------------------------------------------------------
    # Private: setup
    # ------------------------------------------------------------------

    def _populate_type_combo(self) -> None:
        """Fill the media type combo box with Swedish display names."""
        self._ui.media_type_combo.clear()
        for internal_key, display_name in MEDIA_TYPE_MAP.items():
            self._ui.media_type_combo.addItem(display_name, internal_key)

    def _populate_entity_type_combo(self) -> None:
        """Fill the entity type combo box with Swedish display names."""
        self._ui.entity_type_combo.clear()
        for internal_key, display_name in ENTITY_TYPE_MAP.items():
            self._ui.entity_type_combo.addItem(display_name, internal_key)

    def _connect_signals(self) -> None:
        """Wire up UI signals to handler slots."""
        # Media type change -> update type-specific fields visibility
        self._ui.media_type_combo.currentIndexChanged.connect(
            self._update_type_specific_fields
        )

        # Search filter
        self._ui.search_input.textChanged.connect(self._on_search_changed)

        # List buttons
        self._ui.add_media_button.clicked.connect(self._on_add_media)
        self._ui.delete_media_button.clicked.connect(self._on_delete_media)

        # Media list selection
        self._ui.media_list.currentItemChanged.connect(self._on_media_selected)

        # File browse
        self._ui.browse_button.clicked.connect(self._on_browse_file)
        self._ui.file_input.textChanged.connect(self._check_file_exists)

        # Linked entity buttons
        self._ui.add_entity_button.clicked.connect(self._on_add_entity)
        self._ui.remove_entity_button.clicked.connect(self._on_remove_entity)

        # Mentioned persons buttons
        self._ui.add_mentioned_button.clicked.connect(self._on_add_mentioned)
        self._ui.remove_mentioned_button.clicked.connect(self._on_remove_mentioned)

        # Save/Cancel
        self._ui.save_button.clicked.connect(self._on_save)
        self._ui.cancel_button.clicked.connect(self._on_cancel)

    # ------------------------------------------------------------------
    # Private: type-specific fields visibility
    # ------------------------------------------------------------------

    def _update_type_specific_fields(self) -> None:
        """Show/hide type-specific fields based on selected media type."""
        current_type = self._ui.media_type_combo.currentData() or ""

        # Publication fields (newspaper, date, page)
        pub_visible = current_type in PUBLICATION_TYPES
        self._ui.newspaper_label.setVisible(pub_visible)
        self._ui.newspaper_input.setVisible(pub_visible)
        self._ui.pub_date_label.setVisible(pub_visible)
        self._ui.pub_date_input.setVisible(pub_visible)
        self._ui.pub_page_label.setVisible(pub_visible)
        self._ui.pub_page_input.setVisible(pub_visible)

        # Transcription field
        trans_visible = current_type in TRANSCRIPTION_TYPES
        self._ui.transcription_label.setVisible(trans_visible)
        self._ui.transcription_input.setVisible(trans_visible)

        # Mentioned persons
        mentioned_visible = current_type in MENTIONED_TYPES
        self._ui.mentioned_label.setVisible(mentioned_visible)
        self._ui.mentioned_persons_list.setVisible(mentioned_visible)
        self._ui.mentioned_person_input.setVisible(mentioned_visible)
        self._ui.add_mentioned_button.setVisible(mentioned_visible)
        self._ui.remove_mentioned_button.setVisible(mentioned_visible)

        # Hide entire group if no type-specific fields for this type
        has_fields = pub_visible or trans_visible or mentioned_visible
        self._ui.type_specific_group.setVisible(has_fields)

    # ------------------------------------------------------------------
    # Private: media list management
    # ------------------------------------------------------------------

    def _refresh_media_list(self, filter_text: str = "") -> None:
        """Rebuild the media list, optionally filtering by title or file.

        Args:
            filter_text: Case-insensitive filter string for title or file.
        """
        self._ui.media_list.clear()
        filter_lower = filter_text.lower()

        for media in self._project_data.media:
            if filter_lower:
                title_match = filter_lower in media.title.lower()
                file_match = filter_lower in media.file.lower()
                if not title_match and not file_match:
                    continue

            display = media.title or media.file or media.id
            type_name = MEDIA_TYPE_MAP.get(media.type, media.type)
            display = f"{display} ({type_name})"

            # Add missing-file indicator in the list
            file_path = self._resolve_file_path(media.file)
            if file_path and not os.path.exists(file_path):
                display = f"⚠ {display}"

            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, media.id)
            self._ui.media_list.addItem(item)

    def _on_search_changed(self, text: str) -> None:
        """Handle search input text changes.

        Args:
            text: The current search text.
        """
        self._refresh_media_list(text)

    def _on_media_selected(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        """Handle media list selection change.

        Args:
            current: The newly selected item, or None.
            _previous: The previously selected item (unused).
        """
        if current is None:
            return

        media_id = current.data(Qt.ItemDataRole.UserRole)
        for media in self._project_data.media:
            if media.id == media_id:
                self._media_item = media
                self._is_new = False
                self._load_media_item()
                break

    def _on_add_media(self) -> None:
        """Clear the form to create a new media item."""
        self._media_item = None
        self._is_new = True
        self._clear_form()
        self._clear_status()

    def _on_delete_media(self) -> None:
        """Remove the selected media item from the project data."""
        current = self._ui.media_list.currentItem()
        if not current:
            self._update_status("Välj ett mediaobjekt att ta bort.")
            return

        media_id = current.data(Qt.ItemDataRole.UserRole)

        reply = QMessageBox.warning(
            self,
            "Varning",
            "Vill du verkligen ta bort detta mediaobjekt?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._project_data.media = [
            m for m in self._project_data.media if m.id != media_id
        ]
        self._media_item = None
        self._is_new = True
        self._clear_form()
        self._refresh_media_list(self._ui.search_input.text())
        self._clear_status()

    # ------------------------------------------------------------------
    # Private: file management
    # ------------------------------------------------------------------

    def _on_browse_file(self) -> None:
        """Open a file dialog to select a media file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Välj mediafil",
            "",
            "Alla filer (*.*)",
        )
        if file_path:
            # Convert to relative path with forward slashes if possible
            self._ui.file_input.setText(file_path.replace("\\", "/"))

    def _check_file_exists(self, text: str) -> None:
        """Check if the file path exists and show/hide the missing indicator.

        Args:
            text: The current file path text.
        """
        if not text.strip():
            self._ui.missing_file_label.setVisible(False)
            return

        resolved = self._resolve_file_path(text.strip())
        if resolved and not os.path.exists(resolved):
            self._ui.missing_file_label.setVisible(True)
        else:
            self._ui.missing_file_label.setVisible(False)

    def _resolve_file_path(self, file_value: str) -> str:
        """Resolve a relative file path to an absolute path.

        Uses the project file's directory as base if available,
        otherwise returns the path as-is.

        Args:
            file_value: The file path value (may be relative).

        Returns:
            The resolved absolute file path.
        """
        if not file_value:
            return ""
        # If already absolute, return as-is
        if os.path.isabs(file_value):
            return file_value
        # Otherwise return as-is (resolution would need project base path)
        return file_value

    # ------------------------------------------------------------------
    # Private: linked entity management
    # ------------------------------------------------------------------

    def _on_add_entity(self) -> None:
        """Add a linked entity from the input fields."""
        entity_type = self._ui.entity_type_combo.currentData()
        entity_id = self._ui.entity_id_input.text().strip()
        role = self._ui.entity_role_input.text().strip()

        if not entity_id:
            self._update_status("Ange ett entitets-ID.")
            return

        # Build display string
        type_display = ENTITY_TYPE_MAP.get(entity_type, entity_type)
        display = f"{type_display}: {entity_id}"
        if role:
            display = f"{display} ({role})"

        item = QListWidgetItem(display)
        item.setData(Qt.ItemDataRole.UserRole, {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "role": role,
        })
        self._ui.linked_entities_list.addItem(item)

        # Clear input fields
        self._ui.entity_id_input.clear()
        self._ui.entity_role_input.clear()
        self._clear_status()

    def _on_remove_entity(self) -> None:
        """Remove the currently selected linked entity."""
        current = self._ui.linked_entities_list.currentItem()
        if not current:
            self._update_status("Välj en entitet att ta bort.")
            return

        row = self._ui.linked_entities_list.row(current)
        self._ui.linked_entities_list.takeItem(row)
        self._clear_status()

    # ------------------------------------------------------------------
    # Private: mentioned persons management
    # ------------------------------------------------------------------

    def _on_add_mentioned(self) -> None:
        """Add a mentioned person ID to the list."""
        person_id = self._ui.mentioned_person_input.text().strip()
        if not person_id:
            self._update_status("Ange ett person-ID.")
            return

        item = QListWidgetItem(person_id)
        item.setData(Qt.ItemDataRole.UserRole, person_id)
        self._ui.mentioned_persons_list.addItem(item)
        self._ui.mentioned_person_input.clear()
        self._clear_status()

    def _on_remove_mentioned(self) -> None:
        """Remove the currently selected mentioned person."""
        current = self._ui.mentioned_persons_list.currentItem()
        if not current:
            self._update_status("Välj en person att ta bort.")
            return

        row = self._ui.mentioned_persons_list.row(current)
        self._ui.mentioned_persons_list.takeItem(row)
        self._clear_status()

    # ------------------------------------------------------------------
    # Private: load media item data
    # ------------------------------------------------------------------

    def _load_media_item(self) -> None:
        """Populate all fields from the current media item."""
        if self._media_item is None:
            return

        # File path
        self._ui.file_input.setText(self._media_item.file)

        # Media type
        type_index = self._ui.media_type_combo.findData(self._media_item.type)
        if type_index >= 0:
            self._ui.media_type_combo.setCurrentIndex(type_index)

        # Title
        self._ui.title_input.setText(self._media_item.title)

        # Linked entities
        self._refresh_linked_entities_list()

        # Publication fields
        if self._media_item.publication:
            pub = self._media_item.publication
            self._ui.newspaper_input.setText(str(pub.get("newspaper", "") or ""))
            self._ui.pub_date_input.setText(str(pub.get("date", "") or ""))
            self._ui.pub_page_input.setText(str(pub.get("page", "") or ""))
        else:
            self._ui.newspaper_input.clear()
            self._ui.pub_date_input.clear()
            self._ui.pub_page_input.clear()

        # Transcription
        self._ui.transcription_input.setPlainText(
            self._media_item.transcription or ""
        )

        # Mentioned persons
        self._refresh_mentioned_persons_list()

        # Check file exists
        self._check_file_exists(self._media_item.file)

    def _refresh_linked_entities_list(self) -> None:
        """Populate the linked entities list from the current media item."""
        self._ui.linked_entities_list.clear()

        if self._media_item is None:
            return

        for entity in self._media_item.linked_entities:
            type_display = ENTITY_TYPE_MAP.get(entity.entity_type, entity.entity_type)
            display = f"{type_display}: {entity.entity_id}"
            if entity.role:
                display = f"{display} ({entity.role})"

            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, {
                "entity_type": entity.entity_type,
                "entity_id": entity.entity_id,
                "role": entity.role,
            })
            self._ui.linked_entities_list.addItem(item)

    def _refresh_mentioned_persons_list(self) -> None:
        """Populate the mentioned persons list from the current media item."""
        self._ui.mentioned_persons_list.clear()

        if self._media_item is None:
            return

        for person_id in self._media_item.mentioned_person_ids:
            item = QListWidgetItem(person_id)
            item.setData(Qt.ItemDataRole.UserRole, person_id)
            self._ui.mentioned_persons_list.addItem(item)

    # ------------------------------------------------------------------
    # Private: save / cancel
    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        """Validate and save the media item data.

        Validates that title, file, and at least one linked entity (for new
        items) are set. On success, stores the result in saved_media.
        """
        # Validate: file required
        file_path = self._ui.file_input.text().strip()
        if not file_path:
            self._update_status("Fil krävs.")
            return

        # Validate: title required
        title = self._ui.title_input.text().strip()
        if not title:
            self._update_status("Titel krävs.")
            return

        # Validate: at least one linked entity for new items
        entity_count = self._ui.linked_entities_list.count()
        if self._is_new and entity_count == 0:
            self._update_status(
                "Minst en länkad entitet krävs för nya mediaobjekt."
            )
            return

        # Collect media type
        media_type = self._ui.media_type_combo.currentData()

        # Collect linked entities
        linked_entities: list[LinkedEntity] = []
        for i in range(self._ui.linked_entities_list.count()):
            item = self._ui.linked_entities_list.item(i)
            if item:
                data = item.data(Qt.ItemDataRole.UserRole)
                if data:
                    linked_entities.append(
                        LinkedEntity(
                            entity_type=data["entity_type"],
                            entity_id=data["entity_id"],
                            role=data.get("role", ""),
                        )
                    )

        # Collect publication info (if applicable)
        publication: Optional[dict] = None
        if media_type in PUBLICATION_TYPES:
            newspaper = self._ui.newspaper_input.text().strip()
            pub_date = self._ui.pub_date_input.text().strip()
            pub_page = self._ui.pub_page_input.text().strip()
            if newspaper or pub_date or pub_page:
                publication = {}
                if newspaper:
                    publication["newspaper"] = newspaper
                if pub_date:
                    publication["date"] = pub_date
                if pub_page:
                    publication["page"] = pub_page

        # Collect transcription (if applicable)
        transcription: Optional[str] = None
        if media_type in TRANSCRIPTION_TYPES:
            text = self._ui.transcription_input.toPlainText()
            if text.strip():
                transcription = text

        # Collect mentioned person IDs (if applicable)
        mentioned_person_ids: list[str] = []
        if media_type in MENTIONED_TYPES:
            for i in range(self._ui.mentioned_persons_list.count()):
                item = self._ui.mentioned_persons_list.item(i)
                if item:
                    pid = item.data(Qt.ItemDataRole.UserRole)
                    if pid:
                        mentioned_person_ids.append(pid)

        # Determine media ID
        media_id = self._media_item.id if self._media_item else str(uuid.uuid4())

        self._saved_media = MediaItem(
            id=media_id,
            type=media_type,
            file=file_path.replace("\\", "/"),
            title=title,
            linked_entities=linked_entities,
            publication=publication,
            transcription=transcription,
            mentioned_person_ids=mentioned_person_ids,
        )

        # Update or add to project data
        if self._media_item:
            # Update existing
            self._project_data.media = [
                self._saved_media if m.id == media_id else m
                for m in self._project_data.media
            ]
        else:
            # Add new
            self._project_data.media.append(self._saved_media)

        self._media_item = self._saved_media
        self._is_new = False
        self._refresh_media_list(self._ui.search_input.text())
        self._clear_status()
        logger.info("Media sparad: %s", media_id)

    def _on_cancel(self) -> None:
        """Close the editor without saving."""
        self._saved_media = None
        self.close()

    # ------------------------------------------------------------------
    # Private: helpers
    # ------------------------------------------------------------------

    def _clear_form(self) -> None:
        """Reset all form fields to empty/default state."""
        self._ui.file_input.clear()
        self._ui.media_type_combo.setCurrentIndex(0)
        self._ui.title_input.clear()
        self._ui.linked_entities_list.clear()
        self._ui.entity_id_input.clear()
        self._ui.entity_role_input.clear()
        self._ui.newspaper_input.clear()
        self._ui.pub_date_input.clear()
        self._ui.pub_page_input.clear()
        self._ui.transcription_input.clear()
        self._ui.mentioned_persons_list.clear()
        self._ui.mentioned_person_input.clear()
        self._ui.missing_file_label.setVisible(False)

    def _update_status(self, message: str) -> None:
        """Update the status label text with an error/info message.

        Args:
            message: The status message to display.
        """
        self._ui.status_label.setText(message)

    def _clear_status(self) -> None:
        """Clear the status label."""
        self._ui.status_label.setText("")
