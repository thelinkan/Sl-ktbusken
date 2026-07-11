"""Unit tests for the ProviderEditor widget.

Tests layout verification, button enable/disable states,
edit and cancel workflows, and validation error display.
"""

from __future__ import annotations

import pytest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.source import Kalltyp, Leverantor, Source
from slaktbusken.ui.editors.provider_editor import ProviderEditor


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def empty_project() -> ProjectData:
    """Create an empty project data for testing."""
    return ProjectData(project=ProjectMetadata(title="Test"))


@pytest.fixture()
def project_with_leverantor() -> ProjectData:
    """Create a project with one unreferenced leverantör."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        leverantorer=[
            Leverantor(id="lev_1", name="Arkiv Digital", comment="En kommentar"),
        ],
    )


@pytest.fixture()
def project_with_leverantor_and_kalltyp() -> ProjectData:
    """Create a project with a leverantör and one källtyp."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        leverantorer=[
            Leverantor(id="lev_1", name="Arkiv Digital", comment=""),
        ],
        kalltyper=[
            Kalltyp(
                id="kt_1",
                leverantor_id="lev_1",
                name="Husförhörslängd",
                comment="",
                root_url="",
            ),
        ],
    )


@pytest.fixture()
def project_with_referenced_leverantor() -> ProjectData:
    """Create a project where the leverantör is referenced by a source."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        leverantorer=[
            Leverantor(id="lev_1", name="Arkiv Digital", comment=""),
        ],
        kalltyper=[
            Kalltyp(id="kt_1", leverantor_id="lev_1", name="Husförhörslängd"),
        ],
        sources=[
            Source(
                id="src_1",
                provider="Arkiv Digital",
                source_type="Husförhörslängd",
                title="Ljusdal AI:17",
                leverantor_id="lev_1",
                kalltyp_id="kt_1",
            ),
        ],
    )


# ============================================================================
# Test: Dialog opens with correct layout (Requirement 1.1)
# ============================================================================


class TestProviderEditorLayout:
    """Verify ProviderEditor opens with the correct layout and widgets."""

    def test_can_instantiate_with_project_data(self, qapp, empty_project):
        """ProviderEditor can be instantiated with project_data."""
        editor = ProviderEditor(empty_project)
        assert editor is not None

    def test_has_leverantor_list_widget(self, qapp, empty_project):
        """Editor has a leverantör list widget."""
        editor = ProviderEditor(empty_project)
        assert editor._leverantor_list is not None
        assert editor._leverantor_list.count() == 0

    def test_has_kalltyp_list_widget(self, qapp, empty_project):
        """Editor has a källtyp list widget."""
        editor = ProviderEditor(empty_project)
        assert editor._kalltyp_list is not None
        assert editor._kalltyp_list.count() == 0

    def test_has_leverantor_buttons(self, qapp, empty_project):
        """Editor has 'Lägg till', 'Ta bort', 'Redigera' buttons for leverantörer."""
        editor = ProviderEditor(empty_project)
        assert editor._lev_add_btn.text() == "Lägg till"
        assert editor._lev_remove_btn.text() == "Ta bort"
        assert editor._lev_edit_btn.text() == "Redigera"

    def test_has_kalltyp_buttons(self, qapp, empty_project):
        """Editor has 'Lägg till', 'Ta bort', 'Redigera' buttons for källtyper."""
        editor = ProviderEditor(empty_project)
        assert editor._kt_add_btn.text() == "Lägg till"
        assert editor._kt_remove_btn.text() == "Ta bort"
        assert editor._kt_edit_btn.text() == "Redigera"

    def test_form_initially_hidden(self, qapp, empty_project):
        """The edit form is initially hidden."""
        editor = ProviderEditor(empty_project)
        assert editor._name_input.isHidden()
        assert editor._comment_input.isHidden()
        assert editor._save_form_btn.isHidden()
        assert editor._cancel_form_btn.isHidden()

    def test_leverantor_list_populated_from_project_data(
        self, qapp, project_with_leverantor
    ):
        """Leverantör list shows items from project data."""
        editor = ProviderEditor(project_with_leverantor)
        assert editor._leverantor_list.count() == 1
        item = editor._leverantor_list.item(0)
        assert item.text() == "Arkiv Digital"


# ============================================================================
# Test: Buttons enable/disable states (Requirement 1.5)
# ============================================================================


class TestButtonStates:
    """Verify button enable/disable logic based on selection and references."""

    def test_no_leverantor_selected_remove_disabled(self, qapp, project_with_leverantor):
        """With no leverantör selected, 'Ta bort' is disabled."""
        editor = ProviderEditor(project_with_leverantor)
        # Clear selection
        editor._leverantor_list.setCurrentItem(None)
        editor._update_button_states()
        assert not editor._lev_remove_btn.isEnabled()

    def test_no_leverantor_selected_edit_disabled(self, qapp, project_with_leverantor):
        """With no leverantör selected, 'Redigera' is disabled."""
        editor = ProviderEditor(project_with_leverantor)
        editor._leverantor_list.setCurrentItem(None)
        editor._update_button_states()
        assert not editor._lev_edit_btn.isEnabled()

    def test_no_kalltyp_selected_remove_disabled(
        self, qapp, project_with_leverantor_and_kalltyp
    ):
        """With no källtyp selected, 'Ta bort' for källtyper is disabled."""
        editor = ProviderEditor(project_with_leverantor_and_kalltyp)
        editor._kalltyp_list.setCurrentItem(None)
        editor._update_button_states()
        assert not editor._kt_remove_btn.isEnabled()

    def test_no_kalltyp_selected_edit_disabled(
        self, qapp, project_with_leverantor_and_kalltyp
    ):
        """With no källtyp selected, 'Redigera' for källtyper is disabled."""
        editor = ProviderEditor(project_with_leverantor_and_kalltyp)
        editor._kalltyp_list.setCurrentItem(None)
        editor._update_button_states()
        assert not editor._kt_edit_btn.isEnabled()

    def test_kt_add_disabled_when_no_leverantor_selected(self, qapp, empty_project):
        """'Lägg till' for källtyper is disabled when no leverantör is selected."""
        editor = ProviderEditor(empty_project)
        assert not editor._kt_add_btn.isEnabled()

    def test_selecting_leverantor_enables_edit(self, qapp, project_with_leverantor):
        """Selecting a leverantör enables 'Redigera'."""
        editor = ProviderEditor(project_with_leverantor)
        editor._leverantor_list.setCurrentRow(0)
        assert editor._lev_edit_btn.isEnabled()

    def test_selecting_unreferenced_leverantor_enables_remove(
        self, qapp, project_with_leverantor
    ):
        """Selecting an unreferenced leverantör enables 'Ta bort'."""
        editor = ProviderEditor(project_with_leverantor)
        editor._leverantor_list.setCurrentRow(0)
        assert editor._lev_remove_btn.isEnabled()

    def test_referenced_leverantor_disables_remove(
        self, qapp, project_with_referenced_leverantor
    ):
        """Selecting a referenced leverantör keeps 'Ta bort' disabled."""
        editor = ProviderEditor(project_with_referenced_leverantor)
        editor._leverantor_list.setCurrentRow(0)
        assert not editor._lev_remove_btn.isEnabled()

    def test_referenced_kalltyp_disables_remove(
        self, qapp, project_with_referenced_leverantor
    ):
        """Selecting a referenced källtyp keeps 'Ta bort' disabled."""
        editor = ProviderEditor(project_with_referenced_leverantor)
        # Select the leverantör to populate the källtyp list
        editor._leverantor_list.setCurrentRow(0)
        # Now select the källtyp
        editor._kalltyp_list.setCurrentRow(0)
        assert not editor._kt_remove_btn.isEnabled()

    def test_selecting_leverantor_enables_kt_add(
        self, qapp, project_with_leverantor
    ):
        """Selecting a leverantör enables 'Lägg till' for källtyper."""
        editor = ProviderEditor(project_with_leverantor)
        editor._leverantor_list.setCurrentRow(0)
        assert editor._kt_add_btn.isEnabled()


# ============================================================================
# Test: Edit and cancel workflows (Requirement 2.3)
# ============================================================================


class TestEditAndCancelWorkflows:
    """Verify edit form show/hide and data handling for add/edit/cancel."""

    def test_add_leverantor_shows_form(self, qapp, empty_project):
        """Clicking 'Lägg till' for leverantörer shows the form."""
        editor = ProviderEditor(empty_project)
        editor._lev_add_btn.click()
        assert not editor._name_input.isHidden()
        assert not editor._save_form_btn.isHidden()
        assert not editor._cancel_form_btn.isHidden()

    def test_cancel_hides_form(self, qapp, empty_project):
        """Clicking 'Avbryt' hides the form."""
        editor = ProviderEditor(empty_project)
        editor._lev_add_btn.click()
        assert not editor._name_input.isHidden()
        editor._cancel_form_btn.click()
        assert editor._name_input.isHidden()
        assert editor._save_form_btn.isHidden()

    def test_cancel_discards_input(self, qapp, empty_project):
        """After cancel, no data is added to project_data."""
        editor = ProviderEditor(empty_project)
        editor._lev_add_btn.click()
        editor._name_input.setText("Ny Leverantör")
        editor._cancel_form_btn.click()
        assert len(empty_project.leverantorer) == 0

    def test_edit_leverantor_populates_form(self, qapp, project_with_leverantor):
        """Clicking 'Redigera' populates form with current leverantör data."""
        editor = ProviderEditor(project_with_leverantor)
        editor._leverantor_list.setCurrentRow(0)
        editor._lev_edit_btn.click()
        assert editor._name_input.text() == "Arkiv Digital"
        assert editor._comment_input.toPlainText() == "En kommentar"

    def test_save_with_valid_data_creates_leverantor(self, qapp, empty_project):
        """Clicking 'Spara' with valid data creates the entity."""
        editor = ProviderEditor(empty_project)
        editor._lev_add_btn.click()
        editor._name_input.setText("Ny Leverantör")
        editor._save_form_btn.click()
        assert len(empty_project.leverantorer) == 1
        assert empty_project.leverantorer[0].name == "Ny Leverantör"

    def test_save_hides_form(self, qapp, empty_project):
        """After saving, the form is hidden."""
        editor = ProviderEditor(empty_project)
        editor._lev_add_btn.click()
        editor._name_input.setText("Ny Leverantör")
        editor._save_form_btn.click()
        assert editor._name_input.isHidden()

    def test_add_kalltyp_shows_form_with_url_field(
        self, qapp, project_with_leverantor
    ):
        """Clicking 'Lägg till' for källtyper shows form with URL field."""
        editor = ProviderEditor(project_with_leverantor)
        editor._leverantor_list.setCurrentRow(0)
        editor._kt_add_btn.click()
        assert not editor._name_input.isHidden()
        assert not editor._root_url_input.isHidden()

    def test_save_kalltyp_with_valid_data(self, qapp, project_with_leverantor):
        """Saving a new källtyp adds it to project data."""
        editor = ProviderEditor(project_with_leverantor)
        editor._leverantor_list.setCurrentRow(0)
        editor._kt_add_btn.click()
        editor._name_input.setText("Husförhörslängd")
        editor._save_form_btn.click()
        assert len(project_with_leverantor.kalltyper) == 1
        assert project_with_leverantor.kalltyper[0].name == "Husförhörslängd"
        assert project_with_leverantor.kalltyper[0].leverantor_id == "lev_1"

    def test_edit_kalltyp_populates_form(
        self, qapp, project_with_leverantor_and_kalltyp
    ):
        """Clicking 'Redigera' for källtyp populates form with data."""
        editor = ProviderEditor(project_with_leverantor_and_kalltyp)
        editor._leverantor_list.setCurrentRow(0)
        editor._kalltyp_list.setCurrentRow(0)
        editor._kt_edit_btn.click()
        assert editor._name_input.text() == "Husförhörslängd"


# ============================================================================
# Test: Validation error display (Requirements 1.2, 1.3)
# ============================================================================


class TestValidationErrorDisplay:
    """Verify validation error messages are displayed correctly."""

    def test_empty_name_shows_error(self, qapp, empty_project):
        """Empty name shows 'Namn krävs.' in error label."""
        editor = ProviderEditor(empty_project)
        editor._lev_add_btn.click()
        editor._name_input.setText("")
        editor._save_form_btn.click()
        assert editor._error_label.text() == "Namn krävs."
        # Entity should not be created
        assert len(empty_project.leverantorer) == 0

    def test_whitespace_only_name_shows_error(self, qapp, empty_project):
        """Whitespace-only name shows 'Namn krävs.' in error label."""
        editor = ProviderEditor(empty_project)
        editor._lev_add_btn.click()
        editor._name_input.setText("   ")
        editor._save_form_btn.click()
        assert editor._error_label.text() == "Namn krävs."
        assert len(empty_project.leverantorer) == 0

    def test_name_too_long_shows_error(self, qapp, empty_project):
        """Name exceeding 100 characters shows appropriate error."""
        editor = ProviderEditor(empty_project)
        editor._lev_add_btn.click()
        # QLineEdit has maxLength 100, so we set it programmatically
        editor._name_input.setMaxLength(200)  # temporarily allow longer input
        editor._name_input.setText("A" * 101)
        editor._save_form_btn.click()
        assert "100" in editor._error_label.text()
        assert len(empty_project.leverantorer) == 0

    def test_duplicate_kalltyp_name_shows_error(
        self, qapp, project_with_leverantor_and_kalltyp
    ):
        """Duplicate källtyp name shows error message."""
        editor = ProviderEditor(project_with_leverantor_and_kalltyp)
        editor._leverantor_list.setCurrentRow(0)
        editor._kt_add_btn.click()
        editor._name_input.setText("Husförhörslängd")  # Already exists
        editor._save_form_btn.click()
        assert "redan" in editor._error_label.text().lower() or \
               "finns" in editor._error_label.text().lower()
        # Should not create a duplicate
        assert len(project_with_leverantor_and_kalltyp.kalltyper) == 1

    def test_valid_input_clears_error(self, qapp, empty_project):
        """Valid input after a validation error clears the error and creates entity."""
        editor = ProviderEditor(empty_project)
        editor._lev_add_btn.click()
        # First try with empty name
        editor._name_input.setText("")
        editor._save_form_btn.click()
        assert editor._error_label.text() == "Namn krävs."
        # Now enter valid name
        editor._name_input.setText("Valid Name")
        editor._save_form_btn.click()
        assert len(empty_project.leverantorer) == 1
        # Form should be hidden (error label hidden)
        assert editor._error_label.isHidden()
