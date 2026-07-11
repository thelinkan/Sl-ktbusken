"""Provider editor widget (Leverantörer och Källtyper).

Provides a split-panel editor for managing source providers (Leverantörer)
and their associated source types (Källtyper). Left panel has two list
sections with CRUD buttons; right panel shows an edit form with validation.
All UI text is in Swedish.
"""

from __future__ import annotations

import logging
import uuid

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.project import ProjectData
from slaktbusken.model.source import Kalltyp, Leverantor
from slaktbusken.services.source_validation import (
    delete_kalltyp,
    delete_leverantor,
    get_kalltyper_for_leverantor,
    is_kalltyp_referenced,
    is_leverantor_referenced,
    is_kalltyp_name_unique,
    validate_comment,
    validate_name,
    validate_root_url,
)

logger = logging.getLogger(__name__)

# Editing mode constants
_MODE_NONE = "none"
_MODE_ADD_LEVERANTOR = "add_leverantor"
_MODE_EDIT_LEVERANTOR = "edit_leverantor"
_MODE_ADD_KALLTYP = "add_kalltyp"
_MODE_EDIT_KALLTYP = "edit_kalltyp"


class ProviderEditor(QWidget):
    """Editor widget for Leverantörer and their Källtyper.

    Split-panel layout with leverantör list (top-left), källtyp sub-list
    (bottom-left), and edit form (right). Modifies project_data in-place.

    Args:
        project_data: The current project data containing all entities.
        parent: Optional parent widget.
    """

    save_requested = Signal()
    cancel_requested = Signal()

    def __init__(
        self,
        project_data: ProjectData,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the provider editor.

        Args:
            project_data: The current project data containing all entities.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._project_data = project_data
        self._edit_mode: str = _MODE_NONE
        self._editing_id: str = ""  # ID of item being edited

        self._build_ui()
        self._connect_signals()
        self._refresh_leverantor_list()
        self._update_button_states()
        self._hide_form()

    # ------------------------------------------------------------------
    # Private: UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Build the complete widget layout programmatically."""
        main_layout = QHBoxLayout(self)

        # --- Left panel ---
        left_panel = QVBoxLayout()

        # Leverantör section
        left_panel.addWidget(QLabel("Leverantörer"))
        self._leverantor_list = QListWidget()
        left_panel.addWidget(self._leverantor_list)

        lev_btn_layout = QHBoxLayout()
        self._lev_add_btn = QPushButton("Lägg till")
        self._lev_remove_btn = QPushButton("Ta bort")
        self._lev_edit_btn = QPushButton("Redigera")
        lev_btn_layout.addWidget(self._lev_add_btn)
        lev_btn_layout.addWidget(self._lev_remove_btn)
        lev_btn_layout.addWidget(self._lev_edit_btn)
        left_panel.addLayout(lev_btn_layout)

        # Källtyp section
        left_panel.addWidget(QLabel("Källtyper"))
        self._kalltyp_list = QListWidget()
        left_panel.addWidget(self._kalltyp_list)

        kt_btn_layout = QHBoxLayout()
        self._kt_add_btn = QPushButton("Lägg till")
        self._kt_remove_btn = QPushButton("Ta bort")
        self._kt_edit_btn = QPushButton("Redigera")
        kt_btn_layout.addWidget(self._kt_add_btn)
        kt_btn_layout.addWidget(self._kt_remove_btn)
        kt_btn_layout.addWidget(self._kt_edit_btn)
        left_panel.addLayout(kt_btn_layout)

        main_layout.addLayout(left_panel, stretch=1)

        # --- Right panel (edit form) ---
        right_panel = QVBoxLayout()

        self._form_title_label = QLabel("")
        self._form_title_label.setStyleSheet("font-weight: bold;")
        right_panel.addWidget(self._form_title_label)

        right_panel.addWidget(QLabel("Namn:"))
        self._name_input = QLineEdit()
        self._name_input.setMaxLength(100)
        right_panel.addWidget(self._name_input)

        right_panel.addWidget(QLabel("Kommentar:"))
        self._comment_input = QPlainTextEdit()
        self._comment_input.setMaximumHeight(80)
        right_panel.addWidget(self._comment_input)

        self._root_url_label = QLabel("Rot-URL:")
        right_panel.addWidget(self._root_url_label)
        self._root_url_input = QLineEdit()
        self._root_url_input.setMaxLength(2048)
        right_panel.addWidget(self._root_url_input)

        # Validation error label
        self._error_label = QLabel("")
        self._error_label.setStyleSheet("color: red;")
        self._error_label.setWordWrap(True)
        right_panel.addWidget(self._error_label)

        # Form buttons
        form_btn_layout = QHBoxLayout()
        self._save_form_btn = QPushButton("Spara")
        self._cancel_form_btn = QPushButton("Avbryt")
        form_btn_layout.addWidget(self._save_form_btn)
        form_btn_layout.addWidget(self._cancel_form_btn)
        right_panel.addLayout(form_btn_layout)

        right_panel.addStretch()

        # Status label at bottom of right panel
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        right_panel.addWidget(self._status_label)

        main_layout.addLayout(right_panel, stretch=1)

    def _connect_signals(self) -> None:
        """Wire up UI signals to handler slots."""
        # Leverantör buttons
        self._lev_add_btn.clicked.connect(self._on_lev_add)
        self._lev_remove_btn.clicked.connect(self._on_lev_remove)
        self._lev_edit_btn.clicked.connect(self._on_lev_edit)

        # Källtyp buttons
        self._kt_add_btn.clicked.connect(self._on_kt_add)
        self._kt_remove_btn.clicked.connect(self._on_kt_remove)
        self._kt_edit_btn.clicked.connect(self._on_kt_edit)

        # List selection changes
        self._leverantor_list.currentItemChanged.connect(
            self._on_leverantor_selection_changed
        )
        self._kalltyp_list.currentItemChanged.connect(
            self._on_kalltyp_selection_changed
        )

        # Form buttons
        self._save_form_btn.clicked.connect(self._on_form_save)
        self._cancel_form_btn.clicked.connect(self._on_form_cancel)

    # ------------------------------------------------------------------
    # Private: list management
    # ------------------------------------------------------------------

    def _refresh_leverantor_list(self) -> None:
        """Rebuild the leverantör list from project data."""
        self._leverantor_list.clear()
        for lev in self._project_data.leverantorer:
            item = QListWidgetItem(lev.name)
            item.setData(Qt.ItemDataRole.UserRole, lev.id)
            self._leverantor_list.addItem(item)

    def _refresh_kalltyp_list(self) -> None:
        """Rebuild the källtyp list for the currently selected leverantör."""
        self._kalltyp_list.clear()
        lev_id = self._get_selected_leverantor_id()
        if not lev_id:
            return

        kalltyper = get_kalltyper_for_leverantor(
            lev_id, self._project_data.kalltyper
        )
        for kt in kalltyper:
            item = QListWidgetItem(kt.name)
            item.setData(Qt.ItemDataRole.UserRole, kt.id)
            self._kalltyp_list.addItem(item)

    # ------------------------------------------------------------------
    # Private: selection helpers
    # ------------------------------------------------------------------

    def _get_selected_leverantor_id(self) -> str:
        """Return the ID of the currently selected leverantör, or empty string."""
        current = self._leverantor_list.currentItem()
        if current is None:
            return ""
        return current.data(Qt.ItemDataRole.UserRole) or ""

    def _get_selected_kalltyp_id(self) -> str:
        """Return the ID of the currently selected källtyp, or empty string."""
        current = self._kalltyp_list.currentItem()
        if current is None:
            return ""
        return current.data(Qt.ItemDataRole.UserRole) or ""

    # ------------------------------------------------------------------
    # Private: button state management
    # ------------------------------------------------------------------

    def _update_button_states(self) -> None:
        """Enable/disable buttons based on current selection and references."""
        lev_id = self._get_selected_leverantor_id()
        kt_id = self._get_selected_kalltyp_id()

        # Leverantör buttons
        has_lev_selection = bool(lev_id)
        self._lev_edit_btn.setEnabled(has_lev_selection)

        if has_lev_selection:
            if is_leverantor_referenced(lev_id, self._project_data.sources):
                self._lev_remove_btn.setEnabled(False)
                self._lev_remove_btn.setToolTip(
                    "Kan inte ta bort — leverantören används av en eller flera källor."
                )
            else:
                self._lev_remove_btn.setEnabled(True)
                self._lev_remove_btn.setToolTip("")
        else:
            self._lev_remove_btn.setEnabled(False)
            self._lev_remove_btn.setToolTip("")

        # Källtyp buttons - only enable when a leverantör is selected
        self._kt_add_btn.setEnabled(has_lev_selection)

        has_kt_selection = bool(kt_id)
        self._kt_edit_btn.setEnabled(has_kt_selection)

        if has_kt_selection:
            if is_kalltyp_referenced(kt_id, self._project_data.sources):
                self._kt_remove_btn.setEnabled(False)
                self._kt_remove_btn.setToolTip(
                    "Kan inte ta bort — källtypen används av en eller flera källor."
                )
            else:
                self._kt_remove_btn.setEnabled(True)
                self._kt_remove_btn.setToolTip("")
        else:
            self._kt_remove_btn.setEnabled(False)
            self._kt_remove_btn.setToolTip("")

    def _on_leverantor_selection_changed(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        """Handle leverantör list selection change."""
        self._refresh_kalltyp_list()
        self._update_button_states()
        self._clear_status()

    def _on_kalltyp_selection_changed(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        """Handle källtyp list selection change."""
        self._update_button_states()

    # ------------------------------------------------------------------
    # Private: Leverantör actions
    # ------------------------------------------------------------------

    def _on_lev_add(self) -> None:
        """Start adding a new leverantör — show form."""
        self._edit_mode = _MODE_ADD_LEVERANTOR
        self._editing_id = ""
        self._show_form("Lägg till leverantör", show_url=False)
        self._clear_form_fields()

    def _on_lev_edit(self) -> None:
        """Start editing the selected leverantör — show form."""
        lev_id = self._get_selected_leverantor_id()
        if not lev_id:
            return

        lev = self._find_leverantor(lev_id)
        if lev is None:
            return

        self._edit_mode = _MODE_EDIT_LEVERANTOR
        self._editing_id = lev_id
        self._show_form("Redigera leverantör", show_url=False)
        self._name_input.setText(lev.name)
        self._comment_input.setPlainText(lev.comment)

    def _on_lev_remove(self) -> None:
        """Attempt to remove the selected leverantör."""
        lev_id = self._get_selected_leverantor_id()
        if not lev_id:
            return

        # Check if referenced
        if is_leverantor_referenced(lev_id, self._project_data.sources):
            self._update_status(
                "Kan inte ta bort — leverantören används av en eller flera källor."
            )
            return

        # Check for associated källtyper
        associated_kt = get_kalltyper_for_leverantor(
            lev_id, self._project_data.kalltyper
        )

        if associated_kt:
            # Check if any of the associated källtyper are referenced
            for kt in associated_kt:
                if is_kalltyp_referenced(kt.id, self._project_data.sources):
                    self._update_status(
                        "Kan inte ta bort — en eller flera källtyper används av källor."
                    )
                    return

            # Cascade delete confirmation
            kt_names = ", ".join(kt.name for kt in associated_kt)
            reply = QMessageBox.question(
                self,
                "Bekräfta borttagning",
                f"Leverantören har följande källtyper som också kommer tas bort:\n\n"
                f"{kt_names}\n\n"
                f"Vill du fortsätta?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Perform deletion
        success, msg = delete_leverantor(
            lev_id,
            self._project_data.leverantorer,
            self._project_data.kalltyper,
            self._project_data.sources,
        )

        if success:
            self._refresh_leverantor_list()
            self._refresh_kalltyp_list()
            self._update_button_states()
            self._hide_form()
            self._update_status("Leverantör borttagen.")
            logger.info("Leverantör borttagen: %s", lev_id)
        else:
            self._update_status(msg)

    # ------------------------------------------------------------------
    # Private: Källtyp actions
    # ------------------------------------------------------------------

    def _on_kt_add(self) -> None:
        """Start adding a new källtyp — show form."""
        lev_id = self._get_selected_leverantor_id()
        if not lev_id:
            return

        self._edit_mode = _MODE_ADD_KALLTYP
        self._editing_id = ""
        self._show_form("Lägg till källtyp", show_url=True)
        self._clear_form_fields()

    def _on_kt_edit(self) -> None:
        """Start editing the selected källtyp — show form."""
        kt_id = self._get_selected_kalltyp_id()
        if not kt_id:
            return

        kt = self._find_kalltyp(kt_id)
        if kt is None:
            return

        self._edit_mode = _MODE_EDIT_KALLTYP
        self._editing_id = kt_id
        self._show_form("Redigera källtyp", show_url=True)
        self._name_input.setText(kt.name)
        self._comment_input.setPlainText(kt.comment)
        self._root_url_input.setText(kt.root_url)

    def _on_kt_remove(self) -> None:
        """Attempt to remove the selected källtyp."""
        kt_id = self._get_selected_kalltyp_id()
        if not kt_id:
            return

        if is_kalltyp_referenced(kt_id, self._project_data.sources):
            self._update_status(
                "Kan inte ta bort — källtypen används av en eller flera källor."
            )
            return

        success, msg = delete_kalltyp(
            kt_id,
            self._project_data.kalltyper,
            self._project_data.sources,
        )

        if success:
            self._refresh_kalltyp_list()
            self._update_button_states()
            self._hide_form()
            self._update_status("Källtyp borttagen.")
            logger.info("Källtyp borttagen: %s", kt_id)
        else:
            self._update_status(msg)

    # ------------------------------------------------------------------
    # Private: form management
    # ------------------------------------------------------------------

    def _show_form(self, title: str, show_url: bool) -> None:
        """Show the right-panel edit form with appropriate fields.

        Args:
            title: The form title text.
            show_url: Whether to show the root_url field.
        """
        self._form_title_label.setText(title)
        self._form_title_label.setVisible(True)
        self._name_input.setVisible(True)
        self._comment_input.setVisible(True)
        self._root_url_label.setVisible(show_url)
        self._root_url_input.setVisible(show_url)
        self._error_label.setVisible(True)
        self._error_label.setText("")
        self._save_form_btn.setVisible(True)
        self._cancel_form_btn.setVisible(True)
        self._name_input.setFocus()

    def _hide_form(self) -> None:
        """Hide the right-panel edit form."""
        self._form_title_label.setVisible(False)
        self._name_input.setVisible(False)
        self._comment_input.setVisible(False)
        self._root_url_label.setVisible(False)
        self._root_url_input.setVisible(False)
        self._error_label.setVisible(False)
        self._save_form_btn.setVisible(False)
        self._cancel_form_btn.setVisible(False)
        self._edit_mode = _MODE_NONE
        self._editing_id = ""

    def _clear_form_fields(self) -> None:
        """Reset form input fields to empty."""
        self._name_input.clear()
        self._comment_input.clear()
        self._root_url_input.clear()
        self._error_label.setText("")

    def _on_form_save(self) -> None:
        """Validate and save the form data based on current edit mode."""
        if self._edit_mode == _MODE_ADD_LEVERANTOR:
            self._save_new_leverantor()
        elif self._edit_mode == _MODE_EDIT_LEVERANTOR:
            self._save_edited_leverantor()
        elif self._edit_mode == _MODE_ADD_KALLTYP:
            self._save_new_kalltyp()
        elif self._edit_mode == _MODE_EDIT_KALLTYP:
            self._save_edited_kalltyp()

    def _on_form_cancel(self) -> None:
        """Cancel the current form operation and hide the form."""
        self._hide_form()
        self._clear_status()

    # ------------------------------------------------------------------
    # Private: save operations
    # ------------------------------------------------------------------

    def _save_new_leverantor(self) -> None:
        """Validate and create a new Leverantör."""
        name = self._name_input.text().strip()
        comment = self._comment_input.toPlainText()

        # Validate name
        valid, error = validate_name(name)
        if not valid:
            self._error_label.setText(error)
            return

        # Validate comment
        valid, error = validate_comment(comment)
        if not valid:
            self._error_label.setText(error)
            return

        new_lev = Leverantor(
            id=str(uuid.uuid4()),
            name=name,
            comment=comment,
        )
        self._project_data.leverantorer.append(new_lev)

        self._refresh_leverantor_list()
        self._select_leverantor_by_id(new_lev.id)
        self._hide_form()
        self._update_status(f"Leverantör '{name}' tillagd.")
        logger.info("Leverantör tillagd: %s (%s)", new_lev.id, name)

    def _save_edited_leverantor(self) -> None:
        """Validate and update an existing Leverantör."""
        lev = self._find_leverantor(self._editing_id)
        if lev is None:
            return

        name = self._name_input.text().strip()
        comment = self._comment_input.toPlainText()

        # Validate name
        valid, error = validate_name(name)
        if not valid:
            self._error_label.setText(error)
            return

        # Validate comment
        valid, error = validate_comment(comment)
        if not valid:
            self._error_label.setText(error)
            return

        lev.name = name
        lev.comment = comment

        self._refresh_leverantor_list()
        self._select_leverantor_by_id(lev.id)
        self._hide_form()
        self._update_status(f"Leverantör '{name}' uppdaterad.")
        logger.info("Leverantör uppdaterad: %s (%s)", lev.id, name)

    def _save_new_kalltyp(self) -> None:
        """Validate and create a new Källtyp."""
        lev_id = self._get_selected_leverantor_id()
        if not lev_id:
            self._error_label.setText("Ingen leverantör vald.")
            return

        name = self._name_input.text().strip()
        comment = self._comment_input.toPlainText()
        root_url = self._root_url_input.text().strip()

        # Validate name
        valid, error = validate_name(name)
        if not valid:
            self._error_label.setText(error)
            return

        # Check uniqueness within leverantör
        if not is_kalltyp_name_unique(
            lev_id, name, self._project_data.kalltyper
        ):
            self._error_label.setText(
                "En källtyp med samma namn finns redan för denna leverantör."
            )
            return

        # Validate comment
        valid, error = validate_comment(comment)
        if not valid:
            self._error_label.setText(error)
            return

        # Validate root_url
        valid, error = validate_root_url(root_url)
        if not valid:
            self._error_label.setText(error)
            return

        new_kt = Kalltyp(
            id=str(uuid.uuid4()),
            leverantor_id=lev_id,
            name=name,
            comment=comment,
            root_url=root_url,
        )
        self._project_data.kalltyper.append(new_kt)

        self._refresh_kalltyp_list()
        self._hide_form()
        self._update_status(f"Källtyp '{name}' tillagd.")
        logger.info("Källtyp tillagd: %s (%s)", new_kt.id, name)

    def _save_edited_kalltyp(self) -> None:
        """Validate and update an existing Källtyp."""
        kt = self._find_kalltyp(self._editing_id)
        if kt is None:
            return

        name = self._name_input.text().strip()
        comment = self._comment_input.toPlainText()
        root_url = self._root_url_input.text().strip()

        # Validate name
        valid, error = validate_name(name)
        if not valid:
            self._error_label.setText(error)
            return

        # Check uniqueness within leverantör (excluding self)
        if not is_kalltyp_name_unique(
            kt.leverantor_id,
            name,
            self._project_data.kalltyper,
            exclude_id=kt.id,
        ):
            self._error_label.setText(
                "En källtyp med samma namn finns redan för denna leverantör."
            )
            return

        # Validate comment
        valid, error = validate_comment(comment)
        if not valid:
            self._error_label.setText(error)
            return

        # Validate root_url
        valid, error = validate_root_url(root_url)
        if not valid:
            self._error_label.setText(error)
            return

        kt.name = name
        kt.comment = comment
        kt.root_url = root_url

        self._refresh_kalltyp_list()
        self._hide_form()
        self._update_status(f"Källtyp '{name}' uppdaterad.")
        logger.info("Källtyp uppdaterad: %s (%s)", kt.id, name)

    # ------------------------------------------------------------------
    # Private: helpers
    # ------------------------------------------------------------------

    def _find_leverantor(self, lev_id: str) -> Leverantor | None:
        """Find a Leverantör by ID in project data."""
        for lev in self._project_data.leverantorer:
            if lev.id == lev_id:
                return lev
        return None

    def _find_kalltyp(self, kt_id: str) -> Kalltyp | None:
        """Find a Källtyp by ID in project data."""
        for kt in self._project_data.kalltyper:
            if kt.id == kt_id:
                return kt
        return None

    def _select_leverantor_by_id(self, lev_id: str) -> None:
        """Select the leverantör with the given ID in the list."""
        for i in range(self._leverantor_list.count()):
            item = self._leverantor_list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == lev_id:
                self._leverantor_list.setCurrentItem(item)
                break

    def _update_status(self, message: str) -> None:
        """Update the status label text."""
        self._status_label.setText(message)

    def _clear_status(self) -> None:
        """Clear the status label."""
        self._status_label.setText("")
