"""Reusable photo list section widget for PlaceEditor and EventEditor.

Provides a QListWidget of linked photos with configurable action buttons
(view, edit, add, remove) and signals for photo operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QListWidget, QPushButton, QVBoxLayout, QWidget

from slaktbusken.services.photo_tagging_service import PhotoTaggingService

if TYPE_CHECKING:
    from slaktbusken.model.project import ProjectData
    from slaktbusken.services.photo_service import PhotoService


class PhotoSectionWidget(QWidget):
    """Reusable photo list section for editors.

    Provides a list of linked photos and buttons for view, edit, add, remove.
    Button configuration depends on the mode parameter:
    - "place": buttons are "Visa foto", "Redigera foto", "Lägg till foto"
    - "event": buttons are "Lägg till foto", "Redigera foto", "Ta bort foto"
    """

    photo_added = Signal(str)  # Emits new media_item.id
    photo_edited = Signal(str)  # Emits edited media_item.id

    def __init__(
        self,
        project_data: "ProjectData",
        photo_service: "PhotoService",
        entity_type: str,
        entity_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._project_data = project_data
        self._photo_service = photo_service
        self._entity_type = entity_type
        self._entity_id = entity_id
        self._tagging_service = PhotoTaggingService(project_data)

        # Maps list row index to MediaItem id
        self._photo_ids: list[str] = []

        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        """Build the widget layout with photo list and action buttons."""
        layout = QVBoxLayout(self)

        # Photo list
        self._photo_list = QListWidget()
        self._photo_list.currentRowChanged.connect(self._on_selection_changed)
        layout.addWidget(self._photo_list)

        # Button row
        button_layout = QHBoxLayout()

        if self._entity_type == "place":
            # PlaceEditor mode: "Visa foto", "Redigera foto", "Lägg till foto"
            self._view_button = QPushButton("Visa foto")
            self._view_button.setEnabled(False)
            self._view_button.clicked.connect(self._on_view_photo)
            button_layout.addWidget(self._view_button)

            self._edit_button = QPushButton("Redigera foto")
            self._edit_button.setEnabled(False)
            self._edit_button.clicked.connect(self._on_edit_photo)
            button_layout.addWidget(self._edit_button)

            self._add_button = QPushButton("Lägg till foto")
            self._add_button.clicked.connect(self._on_add_photo)
            button_layout.addWidget(self._add_button)

        elif self._entity_type == "event":
            # EventEditor mode: "Lägg till foto", "Redigera foto", "Ta bort foto"
            self._add_button = QPushButton("Lägg till foto")
            self._add_button.clicked.connect(self._on_add_photo)
            button_layout.addWidget(self._add_button)

            self._edit_button = QPushButton("Redigera foto")
            self._edit_button.setEnabled(False)
            self._edit_button.clicked.connect(self._on_edit_photo)
            button_layout.addWidget(self._edit_button)

            self._remove_button = QPushButton("Ta bort foto")
            self._remove_button.setEnabled(False)
            self._remove_button.clicked.connect(self._on_remove_photo)
            button_layout.addWidget(self._remove_button)

        button_layout.addStretch()
        layout.addLayout(button_layout)

    def _on_selection_changed(self, row: int) -> None:
        """Enable/disable buttons based on photo selection."""
        has_selection = row >= 0

        if self._entity_type == "place":
            self._view_button.setEnabled(has_selection)
            self._edit_button.setEnabled(has_selection)
        elif self._entity_type == "event":
            self._edit_button.setEnabled(has_selection)
            self._remove_button.setEnabled(has_selection)

    def _on_view_photo(self) -> None:
        """Handle 'Visa foto' button click.

        The actual viewer dialog is opened by the integrating widget
        via connecting to the photo list selection or overriding this method.
        This is a hook for the parent (PlaceEditor) to connect to.
        """
        # Viewing is handled by the integrating widget (PlaceEditor)

    def _on_edit_photo(self) -> None:
        """Handle 'Redigera foto' button click. Emits photo_edited signal."""
        row = self._photo_list.currentRow()
        if row >= 0 and row < len(self._photo_ids):
            self.photo_edited.emit(self._photo_ids[row])

    def _on_add_photo(self) -> None:
        """Handle 'Lägg till foto' button click.

        The actual file dialog and MediaItem creation is handled by the
        integrating widget. The photo_added signal is emitted after the
        integrating widget creates the photo and calls emit_photo_added().
        """
        # Adding is handled by the integrating widget (PlaceEditor/EventEditor)

    def _on_remove_photo(self) -> None:
        """Handle 'Ta bort foto' button click.

        Removal logic is handled by the integrating widget (EventEditor).
        """

    def refresh(self) -> None:
        """Reload photos from project data."""
        self._photo_list.clear()
        self._photo_ids.clear()

        if self._entity_type == "place":
            photos = self._tagging_service.get_photos_for_place(self._entity_id)
        elif self._entity_type == "event":
            photos = self._tagging_service.get_photos_for_event(self._entity_id)
        else:
            photos = []

        for photo in photos:
            self._photo_list.addItem(photo.title)
            self._photo_ids.append(photo.id)

    def get_selected_photo_id(self) -> str | None:
        """Return the ID of the currently selected photo, or None."""
        row = self._photo_list.currentRow()
        if row >= 0 and row < len(self._photo_ids):
            return self._photo_ids[row]
        return None

    def emit_photo_added(self, media_item_id: str) -> None:
        """Emit the photo_added signal. Called by integrating widget after adding."""
        self.photo_added.emit(media_item_id)

    @property
    def photo_list(self) -> QListWidget:
        """Expose the internal QListWidget for external connections."""
        return self._photo_list

    @property
    def add_button(self) -> QPushButton:
        """Expose the add button for external signal connections."""
        return self._add_button

    @property
    def view_button(self) -> QPushButton | None:
        """Expose the view button (place mode only)."""
        return getattr(self, "_view_button", None)

    @property
    def edit_button(self) -> QPushButton:
        """Expose the edit button for external signal connections."""
        return self._edit_button

    @property
    def remove_button(self) -> QPushButton | None:
        """Expose the remove button (event mode only)."""
        return getattr(self, "_remove_button", None)
