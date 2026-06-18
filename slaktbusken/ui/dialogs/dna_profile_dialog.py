"""DNA Profile creation dialog for Släktbusken.

Provides a modal form for creating a new DnaProfile associated with a person.
All UI text is in Swedish.
"""

from __future__ import annotations

from typing import Optional
from uuid import uuid4

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.dna import DnaProfile
from slaktbusken.model.project import ProjectData


# Display labels mapped to stored values for test types
_TEST_TYPE_ITEMS: list[tuple[str, str]] = [
    ("Autosomal", "autosomal"),
    ("Y-DNA", "y-dna"),
    ("mtDNA", "mtdna"),
]


class DnaProfileDialog(QDialog):
    """Modal dialog for creating a new DNA profile for the current person.

    Args:
        project_data: The ProjectData containing DNA companies.
        person_id: The ID of the person this profile belongs to.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        project_data: ProjectData,
        person_id: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._project_data = project_data
        self._person_id = person_id
        self._created_profile: Optional[DnaProfile] = None

        self.setWindowTitle("Ny DNA-profil")
        self.setMinimumWidth(400)

        self._setup_ui()
        self._populate_fields()
        self._check_companies()

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def created_profile(self) -> Optional[DnaProfile]:
        """The created DnaProfile, or None if dialog was cancelled."""
        return self._created_profile

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Build the dialog UI programmatically."""
        layout = QVBoxLayout(self)

        # Form layout for fields
        form = QFormLayout()

        self._combo_company = QComboBox()
        form.addRow("Företag:", self._combo_company)

        self._combo_test_type = QComboBox()
        form.addRow("Testtyp:", self._combo_test_type)

        self._edit_kit_name = QLineEdit()
        self._edit_kit_name.setMaxLength(100)
        self._edit_kit_name.setPlaceholderText("Valfritt, max 100 tecken")
        form.addRow("Kit-namn:", self._edit_kit_name)

        self._edit_kit_id = QLineEdit()
        self._edit_kit_id.setMaxLength(50)
        self._edit_kit_id.setPlaceholderText("Valfritt, max 50 tecken")
        form.addRow("Kit-ID:", self._edit_kit_id)

        self._edit_notes = QPlainTextEdit()
        self._edit_notes.setMaximumHeight(100)
        self._edit_notes.setPlaceholderText("Valfritt, max 2000 tecken")
        form.addRow("Anteckningar:", self._edit_notes)

        layout.addLayout(form)

        # Info label shown when no companies exist
        self._label_info = QLabel(
            "Inga DNA-företag finns i projektet. Skapa företag först."
        )
        self._label_info.setWordWrap(True)
        self._label_info.setVisible(False)
        layout.addWidget(self._label_info)

        # Error/status label
        self._label_error = QLabel("")
        self._label_error.setWordWrap(True)
        self._label_error.setStyleSheet("color: red;")
        layout.addWidget(self._label_error)

        # Button box
        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._button_box.accepted.connect(self._on_accept)
        self._button_box.rejected.connect(self.reject)
        layout.addWidget(self._button_box)

    # ------------------------------------------------------------------
    # Field population
    # ------------------------------------------------------------------

    def _populate_fields(self) -> None:
        """Populate dropdowns with available data."""
        # Company dropdown: placeholder + companies
        self._combo_company.addItem("— Välj företag —", "")
        for company in self._project_data.dna_companies:
            self._combo_company.addItem(company.name, company.id)

        # Test type dropdown: placeholder + types
        self._combo_test_type.addItem("— Välj testtyp —", "")
        for display_name, value in _TEST_TYPE_ITEMS:
            self._combo_test_type.addItem(display_name, value)

    def _check_companies(self) -> None:
        """Check if companies exist; if not, show info and disable OK."""
        if not self._project_data.dna_companies:
            self._label_info.setVisible(True)
            ok_button = self._button_box.button(
                QDialogButtonBox.StandardButton.Ok
            )
            if ok_button:
                ok_button.setEnabled(False)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate(self) -> list[str]:
        """Validate form inputs. Returns list of error messages (empty = valid)."""
        errors: list[str] = []

        # Company required
        company_id = self._combo_company.currentData()
        if not company_id:
            errors.append("Välj ett DNA-företag.")

        # Test type required
        test_type = self._combo_test_type.currentData()
        if not test_type:
            errors.append("Välj en testtyp.")

        # Notes max length
        notes_text = self._edit_notes.toPlainText()
        if len(notes_text) > 2000:
            errors.append("Anteckningar får inte överstiga 2000 tecken.")

        return errors

    # ------------------------------------------------------------------
    # Accept handler
    # ------------------------------------------------------------------

    def _on_accept(self) -> None:
        """Handle OK click: validate and create profile or show errors."""
        errors = self._validate()
        if errors:
            self._label_error.setText("\n".join(errors))
            return

        # Clear any previous error
        self._label_error.setText("")

        # Build the DnaProfile
        self._created_profile = DnaProfile(
            id=str(uuid4()),
            person_id=self._person_id,
            company_id=self._combo_company.currentData(),
            test_type=self._combo_test_type.currentData(),
            kit_name=self._edit_kit_name.text().strip(),
            kit_id=self._edit_kit_id.text().strip(),
            notes=self._edit_notes.toPlainText().strip(),
        )
        self.accept()
