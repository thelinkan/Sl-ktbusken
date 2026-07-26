"""Unit tests for EditPhotoDialog – Titel och typ section.

Verifies that:
- The title/type section is present with correct widgets
- Title field loads from parsed MediaItem.title
- Type combo loads from parsed MediaItem.title
- Title validation rejects empty/whitespace-only and >200 char titles
- Title validation accepts valid titles (1–200 chars)
- _get_composed_title() returns '[Fototyp] Titel' format
- No separate "Spara ändringar" button exists in this section
- Error label is hidden by default and shown on validation failure

Covers Requirements 3.1, 3.2, 3.3, 3.4, 3.5.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QComboBox, QGroupBox, QLabel, QLineEdit

from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.project import ProjectData
from slaktbusken.services.photo_service import PhotoService
from slaktbusken.ui.dialogs.edit_photo_dialog import EditPhotoDialog


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def photo_service() -> PhotoService:
    """Return a PhotoService instance for testing."""
    project_data = ProjectData()
    return PhotoService(project_data, Path("/tmp/foton"))


@pytest.fixture()
def media_item_portrait() -> MediaItem:
    """Return a MediaItem with a portrait title."""
    return MediaItem(
        id="m1",
        type="photo",
        file="photo1.jpg",
        title="[Porträtt] Barnfoto",
        linked_entities=[
            LinkedEntity(entity_type="person", entity_id="p1")
        ],
    )


@pytest.fixture()
def media_item_no_prefix() -> MediaItem:
    """Return a MediaItem without a [Type] prefix in title."""
    return MediaItem(
        id="m2",
        type="photo",
        file="photo2.jpg",
        title="Gammal bild utan prefix",
        linked_entities=[],
    )


@pytest.fixture()
def dialog(media_item_portrait, photo_service) -> EditPhotoDialog:
    """Return an EditPhotoDialog loaded with a portrait media item."""
    project_data = ProjectData()
    return EditPhotoDialog(
        media_item=media_item_portrait,
        project_data=project_data,
        photo_service=photo_service,
    )


class TestTitleTypeSectionLayout:
    """Tests for section layout and widget presence."""

    def test_section_is_groupbox_with_correct_title(self, dialog: EditPhotoDialog):
        """The title/type section should be a QGroupBox titled 'Titel och typ'."""
        assert isinstance(dialog._title_type_group, QGroupBox)
        assert dialog._title_type_group.title() == "Titel och typ"

    def test_title_edit_exists(self, dialog: EditPhotoDialog):
        """A QLineEdit for title should exist."""
        assert isinstance(dialog._title_edit, QLineEdit)

    def test_title_edit_max_length(self, dialog: EditPhotoDialog):
        """Title field should have maxLength of 200."""
        assert dialog._title_edit.maxLength() == 200

    def test_type_combo_exists(self, dialog: EditPhotoDialog):
        """A QComboBox for photo type should exist."""
        assert isinstance(dialog._type_combo, QComboBox)

    def test_type_combo_has_all_types(self, dialog: EditPhotoDialog):
        """The combo should contain all FOTO_TYPES."""
        expected = PhotoService.FOTO_TYPES
        items = [dialog._type_combo.itemText(i) for i in range(dialog._type_combo.count())]
        assert items == expected

    def test_no_separate_save_button_in_section(self, dialog: EditPhotoDialog):
        """No 'Spara ändringar' button should exist in the title/type section."""
        from PySide6.QtWidgets import QPushButton

        buttons = dialog._title_type_group.findChildren(QPushButton)
        save_buttons = [b for b in buttons if "Spara" in b.text()]
        assert len(save_buttons) == 0

    def test_error_label_exists_and_hidden(self, dialog: EditPhotoDialog):
        """Error label should exist and be hidden by default."""
        assert isinstance(dialog._title_error_label, QLabel)
        assert dialog._title_error_label.isHidden()


class TestTitleTypeDataLoading:
    """Tests for loading title/type data from MediaItem."""

    def test_loads_title_from_prefixed_format(
        self, media_item_portrait, photo_service
    ):
        """Title field should contain just the title part (without prefix)."""
        project_data = ProjectData()
        dlg = EditPhotoDialog(
            media_item=media_item_portrait,
            project_data=project_data,
            photo_service=photo_service,
        )
        assert dlg._title_edit.text() == "Barnfoto"

    def test_loads_type_from_prefixed_format(
        self, media_item_portrait, photo_service
    ):
        """Type combo should have the correct type selected."""
        project_data = ProjectData()
        dlg = EditPhotoDialog(
            media_item=media_item_portrait,
            project_data=project_data,
            photo_service=photo_service,
        )
        assert dlg._type_combo.currentText() == "Porträtt"

    def test_loads_title_without_prefix(
        self, media_item_no_prefix, photo_service
    ):
        """Title without prefix should load raw title and default to 'Övrigt foto'."""
        project_data = ProjectData()
        dlg = EditPhotoDialog(
            media_item=media_item_no_prefix,
            project_data=project_data,
            photo_service=photo_service,
        )
        assert dlg._title_edit.text() == "Gammal bild utan prefix"
        assert dlg._type_combo.currentText() == "Övrigt foto"


class TestTitleValidation:
    """Tests for title validation logic."""

    def test_valid_title_returns_no_errors(self, dialog: EditPhotoDialog):
        """A normal title should produce no validation errors."""
        dialog._title_edit.setText("Valid title")
        errors = dialog._validate_title()
        assert errors == []
        assert dialog._title_error_label.isHidden()

    def test_empty_title_returns_error(self, dialog: EditPhotoDialog):
        """Empty title should produce a validation error."""
        dialog._title_edit.setText("")
        errors = dialog._validate_title()
        assert len(errors) == 1
        assert not dialog._title_error_label.isHidden()

    def test_whitespace_only_title_returns_error(self, dialog: EditPhotoDialog):
        """Whitespace-only title should produce a validation error."""
        dialog._title_edit.setText("   ")
        errors = dialog._validate_title()
        assert len(errors) == 1
        assert not dialog._title_error_label.isHidden()

    def test_title_over_200_chars_returns_error(self, dialog: EditPhotoDialog):
        """Title longer than 200 chars should produce a validation error via service."""
        # QLineEdit maxLength prevents >200 chars via UI, but validate_title
        # should still catch it if called directly with longer text
        from slaktbusken.services.photo_service import PhotoService

        errors = PhotoService.validate_title("A" * 201)
        assert len(errors) == 1

    def test_title_exactly_200_chars_is_valid(self, dialog: EditPhotoDialog):
        """Title of exactly 200 chars should be valid."""
        dialog._title_edit.setText("A" * 200)
        errors = dialog._validate_title()
        assert errors == []

    def test_error_label_hidden_after_valid_input(self, dialog: EditPhotoDialog):
        """Error label should be hidden when validation passes after a failure."""
        dialog._title_edit.setText("")
        dialog._validate_title()
        assert not dialog._title_error_label.isHidden()

        dialog._title_edit.setText("Now valid")
        dialog._validate_title()
        assert dialog._title_error_label.isHidden()


class TestComposedTitle:
    """Tests for title composition."""

    def test_compose_title_with_portrait(self, dialog: EditPhotoDialog):
        """Composed title should be '[Porträtt] Barnfoto'."""
        dialog._title_edit.setText("Barnfoto")
        dialog._type_combo.setCurrentText("Porträtt")
        assert dialog._get_composed_title() == "[Porträtt] Barnfoto"

    def test_compose_title_with_different_type(self, dialog: EditPhotoDialog):
        """Composed title changes when type changes."""
        dialog._title_edit.setText("Min titel")
        dialog._type_combo.setCurrentText("Gruppfoto")
        assert dialog._get_composed_title() == "[Gruppfoto] Min titel"
