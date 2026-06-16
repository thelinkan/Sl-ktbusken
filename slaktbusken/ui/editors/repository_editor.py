"""Repository editor widget.

Provides a split-panel editor for Repository records: a filterable list
on the left and a detail form on the right with fields for name, type,
address, phone list, email list, web list, notes, and external IDs.
Validates that a name (1-200 chars) and type are present before save.
All UI text is in Swedish.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QInputDialog, QListWidgetItem, QMessageBox, QWidget

from slaktbusken.model.project import ProjectData
from slaktbusken.model.source import Repository
from slaktbusken.ui.generated.ui_repository_editor import Ui_RepositoryEditor

logger = logging.getLogger(__name__)

# Mapping from internal type codes to Swedish display names
_TYPE_TO_DISPLAY: dict[str, str] = {
    "archive": "Arkiv",
    "library": "Bibliotek",
    "digital_archive": "Digitalt arkiv",
    "museum": "Museum",
    "church_office": "Kyrkokontor",
    "other": "Övrigt",
}

# Reverse mapping from Swedish display names to internal codes
_DISPLAY_TO_TYPE: dict[str, str] = {v: k for k, v in _TYPE_TO_DISPLAY.items()}


class RepositoryEditor(QWidget):
    """Editor widget for Repository records with list and detail panels.

    Left panel shows a filterable list of all repositories in the project.
    Right panel provides a form to edit a selected or new repository,
    including list management for phone numbers, email addresses, web URLs,
    and external IDs.

    Args:
        project_data: The current project data containing all entities.
        repository: Optional existing Repository to edit. If None, creates a new repository.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        project_data: ProjectData,
        repository: Optional[Repository] = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the repository editor.

        Args:
            project_data: The current project data containing all entities.
            repository: Optional existing Repository to edit. If None, creates a new repository.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._project_data = project_data
        self._repository = repository
        self._saved_repository: Optional[Repository] = None

        # Set up UI from generated form
        self._ui = Ui_RepositoryEditor()
        self._ui.setupUi(self)

        self._connect_signals()
        self._refresh_repository_list()

        if self._repository is not None:
            self._load_repository()
            self._select_repository_in_list(self._repository.id)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def saved_repository(self) -> Optional[Repository]:
        """The saved Repository result, or None if not yet saved."""
        return self._saved_repository

    def get_repository(self) -> Optional[Repository]:
        """Return the saved repository, or None if save was not performed.

        Returns:
            The Repository object if save was successful, None otherwise.
        """
        return self._saved_repository

    # ------------------------------------------------------------------
    # Private: setup
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        """Wire up UI signals to handler slots."""
        # Left panel
        self._ui.filter_input.textChanged.connect(self._on_filter_changed)
        self._ui.repository_list.currentItemChanged.connect(
            self._on_repository_selected
        )
        self._ui.add_repository_button.clicked.connect(self._on_add_repository)
        self._ui.delete_repository_button.clicked.connect(
            self._on_delete_repository
        )

        # Phone management
        self._ui.add_phone_button.clicked.connect(self._on_add_phone)
        self._ui.remove_phone_button.clicked.connect(self._on_remove_phone)

        # Email management
        self._ui.add_email_button.clicked.connect(self._on_add_email)
        self._ui.remove_email_button.clicked.connect(self._on_remove_email)

        # Web management
        self._ui.add_web_button.clicked.connect(self._on_add_web)
        self._ui.remove_web_button.clicked.connect(self._on_remove_web)

        # External IDs management
        self._ui.add_external_id_button.clicked.connect(self._on_add_external_id)
        self._ui.remove_external_id_button.clicked.connect(
            self._on_remove_external_id
        )

        # Save / Cancel
        self._ui.save_button.clicked.connect(self._on_save)
        self._ui.cancel_button.clicked.connect(self._on_cancel)

    # ------------------------------------------------------------------
    # Private: repository list (left panel)
    # ------------------------------------------------------------------

    def _refresh_repository_list(self) -> None:
        """Rebuild the repository list from project data."""
        self._ui.repository_list.clear()
        for repo in self._project_data.repositories:
            item = QListWidgetItem(repo.name or repo.id)
            item.setData(Qt.ItemDataRole.UserRole, repo.id)
            self._ui.repository_list.addItem(item)

    def _select_repository_in_list(self, repository_id: str) -> None:
        """Select the repository with the given ID in the list widget.

        Args:
            repository_id: The ID of the repository to select.
        """
        for i in range(self._ui.repository_list.count()):
            item = self._ui.repository_list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == repository_id:
                self._ui.repository_list.setCurrentItem(item)
                break

    def _on_filter_changed(self, text: str) -> None:
        """Filter the repository list by name (case-insensitive).

        Args:
            text: The current filter string.
        """
        search = text.lower()
        for i in range(self._ui.repository_list.count()):
            item = self._ui.repository_list.item(i)
            if item:
                visible = search in item.text().lower()
                item.setHidden(not visible)

    def _on_repository_selected(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        """Load the selected repository into the edit form.

        Args:
            current: The newly selected list item, or None.
            _previous: The previously selected list item (unused).
        """
        if current is None:
            self._clear_form()
            return

        repo_id = current.data(Qt.ItemDataRole.UserRole)
        repo = self._find_repository_by_id(repo_id)
        if repo:
            self._repository = repo
            self._load_repository()

    def _on_add_repository(self) -> None:
        """Clear the form to create a new repository."""
        self._repository = None
        self._ui.repository_list.clearSelection()
        self._clear_form()
        self._clear_status()

    def _on_delete_repository(self) -> None:
        """Delete the currently selected repository from project data."""
        current = self._ui.repository_list.currentItem()
        if current is None:
            self._update_status("Välj ett arkiv att ta bort.")
            return

        repo_id = current.data(Qt.ItemDataRole.UserRole)

        # Check for referencing sources (via repository_refs)
        referencing_sources = self._find_referencing_sources(repo_id)
        if referencing_sources:
            source_lines: list[str] = []
            for s in referencing_sources:
                parts = [s.title]
                if s.provider:
                    parts.append(s.provider)
                source_lines.append(f"  • {' — '.join(parts)}")
            source_list = "\n".join(source_lines)
            reply = QMessageBox.warning(
                self,
                "Varning",
                f"Detta arkiv refereras av följande källor:\n\n"
                f"{source_list}\n\n"
                "Vill du verkligen ta bort arkivet?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._project_data.repositories = [
            r for r in self._project_data.repositories if r.id != repo_id
        ]

        if self._repository and self._repository.id == repo_id:
            self._repository = None

        self._refresh_repository_list()
        self._clear_form()
        self._clear_status()
        logger.info("Arkiv borttaget: %s", repo_id)

    def _find_referencing_sources(self, repo_id: str) -> list:
        """Find all sources that reference a given repository via repository_refs.

        Args:
            repo_id: The repository ID to search for.

        Returns:
            List of Source objects referencing this repository.
        """
        referencing = []
        for source in self._project_data.sources:
            for repo_ref in source.repository_refs:
                if repo_ref.repository_id == repo_id:
                    referencing.append(source)
                    break
        return referencing

    # ------------------------------------------------------------------
    # Private: load repository data into form
    # ------------------------------------------------------------------

    def _load_repository(self) -> None:
        """Populate all form fields from the current repository."""
        if self._repository is None:
            return

        self._ui.name_input.setText(self._repository.name)

        # Set type combo
        display_type = _TYPE_TO_DISPLAY.get(self._repository.type, "Övrigt")
        type_index = self._ui.type_combo.findText(display_type)
        if type_index >= 0:
            self._ui.type_combo.setCurrentIndex(type_index)

        # Address
        self._ui.address_input.setText(self._repository.address or "")

        # Phone list
        self._ui.phone_list.clear()
        for phone in self._repository.phone:
            self._ui.phone_list.addItem(phone)

        # Email list
        self._ui.email_list.clear()
        for email in self._repository.email:
            self._ui.email_list.addItem(email)

        # Web list
        self._ui.web_list.clear()
        for web in self._repository.web:
            self._ui.web_list.addItem(web)

        # External IDs list
        self._ui.external_ids_list.clear()
        for ext_id in self._repository.external_ids:
            self._ui.external_ids_list.addItem(ext_id)

        # Notes
        self._ui.notes_input.setPlainText(self._repository.notes)

        self._clear_status()

    # ------------------------------------------------------------------
    # Private: phone management
    # ------------------------------------------------------------------

    def _on_add_phone(self) -> None:
        """Show input dialog and add a phone number to the list."""
        text, ok = QInputDialog.getText(
            self, "Lägg till telefon", "Telefonnummer:"
        )
        if ok and text.strip():
            self._ui.phone_list.addItem(text.strip())

    def _on_remove_phone(self) -> None:
        """Remove the selected phone number from the list."""
        current = self._ui.phone_list.currentRow()
        if current >= 0:
            self._ui.phone_list.takeItem(current)
        else:
            self._update_status("Välj ett telefonnummer att ta bort.")

    # ------------------------------------------------------------------
    # Private: email management
    # ------------------------------------------------------------------

    def _on_add_email(self) -> None:
        """Show input dialog and add an email address to the list."""
        text, ok = QInputDialog.getText(
            self, "Lägg till e-post", "E-postadress:"
        )
        if ok and text.strip():
            self._ui.email_list.addItem(text.strip())

    def _on_remove_email(self) -> None:
        """Remove the selected email address from the list."""
        current = self._ui.email_list.currentRow()
        if current >= 0:
            self._ui.email_list.takeItem(current)
        else:
            self._update_status("Välj en e-postadress att ta bort.")

    # ------------------------------------------------------------------
    # Private: web management
    # ------------------------------------------------------------------

    def _on_add_web(self) -> None:
        """Show input dialog and add a web URL to the list."""
        text, ok = QInputDialog.getText(
            self, "Lägg till webbadress", "URL:"
        )
        if ok and text.strip():
            self._ui.web_list.addItem(text.strip())

    def _on_remove_web(self) -> None:
        """Remove the selected web URL from the list."""
        current = self._ui.web_list.currentRow()
        if current >= 0:
            self._ui.web_list.takeItem(current)
        else:
            self._update_status("Välj en webbadress att ta bort.")

    # ------------------------------------------------------------------
    # Private: external IDs management
    # ------------------------------------------------------------------

    def _on_add_external_id(self) -> None:
        """Show input dialog and add an external ID to the list."""
        text, ok = QInputDialog.getText(
            self, "Lägg till externt ID", "Externt ID:"
        )
        if ok and text.strip():
            self._ui.external_ids_list.addItem(text.strip())

    def _on_remove_external_id(self) -> None:
        """Remove the selected external ID from the list."""
        current = self._ui.external_ids_list.currentRow()
        if current >= 0:
            self._ui.external_ids_list.takeItem(current)
        else:
            self._update_status("Välj ett externt ID att ta bort.")

    # ------------------------------------------------------------------
    # Private: save / cancel
    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        """Validate and save the repository data.

        Validates that name (1-200 chars) and type are present.
        On success, stores the result in saved_repository.
        """
        name = self._ui.name_input.text().strip()

        # Validate name
        if not name:
            self._update_status("Namn krävs.")
            return
        if len(name) > 200:
            self._update_status("Namn får vara max 200 tecken.")
            return

        # Get type
        display_type = self._ui.type_combo.currentText()
        repo_type = _DISPLAY_TO_TYPE.get(display_type)
        if not repo_type:
            self._update_status("Välj en typ.")
            return

        # Address
        address = self._ui.address_input.text().strip() or None

        # Collect lists
        phone = [
            self._ui.phone_list.item(i).text()
            for i in range(self._ui.phone_list.count())
        ]
        email = [
            self._ui.email_list.item(i).text()
            for i in range(self._ui.email_list.count())
        ]
        web = [
            self._ui.web_list.item(i).text()
            for i in range(self._ui.web_list.count())
        ]
        external_ids = [
            self._ui.external_ids_list.item(i).text()
            for i in range(self._ui.external_ids_list.count())
        ]

        # Notes
        notes = self._ui.notes_input.toPlainText()

        # Determine repository ID
        repo_id = self._repository.id if self._repository else str(uuid.uuid4())

        self._saved_repository = Repository(
            id=repo_id,
            name=name,
            type=repo_type,
            address=address,
            phone=phone,
            email=email,
            web=web,
            notes=notes,
            external_ids=external_ids,
        )

        self._clear_status()
        logger.info("Arkiv sparat: %s", repo_id)
        self.close()

    def _on_cancel(self) -> None:
        """Close the editor without saving."""
        self._saved_repository = None
        self.close()

    # ------------------------------------------------------------------
    # Private: helpers
    # ------------------------------------------------------------------

    def _find_repository_by_id(self, repo_id: str) -> Optional[Repository]:
        """Look up a repository by ID in project data.

        Args:
            repo_id: The repository ID to find.

        Returns:
            The Repository if found, None otherwise.
        """
        for repo in self._project_data.repositories:
            if repo.id == repo_id:
                return repo
        return None

    def _clear_form(self) -> None:
        """Reset all form fields to empty/default state."""
        self._ui.name_input.clear()
        self._ui.type_combo.setCurrentIndex(0)
        self._ui.address_input.clear()
        self._ui.phone_list.clear()
        self._ui.email_list.clear()
        self._ui.web_list.clear()
        self._ui.external_ids_list.clear()
        self._ui.notes_input.clear()

    def _update_status(self, message: str) -> None:
        """Update the status label text with a validation message.

        Args:
            message: The status message to display.
        """
        self._ui.status_label.setText(message)

    def _clear_status(self) -> None:
        """Clear the status label."""
        self._ui.status_label.setText("")
