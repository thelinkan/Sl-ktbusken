"""DNA Profile creation/edit dialog for Släktbusken.

Provides a modal form for creating or editing a DnaProfile associated with a person.
Includes raw DNA data import functionality (AncestryDNA, MyHeritage).
All UI text is in Swedish.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.dna import DnaProfile
from slaktbusken.model.project import ProjectData

logger = logging.getLogger(__name__)

# Display labels mapped to stored values for test types
_TEST_TYPE_ITEMS: list[tuple[str, str]] = [
    ("Autosomal", "autosomal"),
    ("Y-DNA", "y-dna"),
    ("mtDNA", "mtdna"),
]

_MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB


class DnaProfileDialog(QDialog):
    """Modal dialog for creating or editing a DNA profile for the current person.

    Args:
        project_data: The ProjectData containing DNA companies.
        person_id: The ID of the person this profile belongs to.
        existing_profile: Optional existing profile to edit. When provided,
            the dialog enters edit mode with pre-populated fields.
        project_path: Optional path to the project file (.json.gz) on disk,
            or the project folder. Required for raw DNA import functionality.
            If a file path, its parent is used as the project folder.
            If a directory, it is used directly as the project folder.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        project_data: ProjectData,
        person_id: str,
        existing_profile: Optional[DnaProfile] = None,
        project_path: Optional[Path] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._project_data = project_data
        self._person_id = person_id
        self._existing_profile = existing_profile
        # Resolve project folder from project_path
        if project_path is not None:
            if project_path.is_dir():
                self._project_folder = project_path
            else:
                self._project_folder = project_path.parent
        else:
            self._project_folder = None
        self._created_profile: Optional[DnaProfile] = None
        self._edited_profile: Optional[DnaProfile] = None
        # Track pending raw_data_file change (None = no change, "" = remove, str = set)
        self._pending_raw_data_file: Optional[str] = None
        self._raw_data_changed = False

        if self._existing_profile is not None:
            self.setWindowTitle("Redigera DNA-profil")
        else:
            self.setWindowTitle("Ny DNA-profil")
        self.setMinimumWidth(400)

        self._setup_ui()
        self._populate_fields()
        self._prepopulate_edit_fields()
        self._check_companies()

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def created_profile(self) -> Optional[DnaProfile]:
        """The created DnaProfile, or None if dialog was cancelled."""
        return self._created_profile

    @property
    def edited_profile(self) -> Optional[DnaProfile]:
        """The edited DnaProfile, or None if dialog was cancelled or not in edit mode."""
        return self._edited_profile

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

        # --- Raw DNA data section ---
        self._setup_raw_data_section(layout)

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

    def _setup_raw_data_section(self, parent_layout: QVBoxLayout) -> None:
        """Set up the raw DNA data import section of the dialog."""
        # Section label
        section_label = QLabel("<b>Rå DNA-data</b>")
        parent_layout.addWidget(section_label)

        # Current status display
        self._label_raw_status = QLabel("Ingen fil")
        self._label_raw_status.setObjectName("label_raw_status")
        parent_layout.addWidget(self._label_raw_status)

        # Buttons row
        btn_layout = QHBoxLayout()

        self._btn_import_raw = QPushButton("Importera DNA-data...")
        self._btn_import_raw.setObjectName("btn_import_raw")
        self._btn_import_raw.clicked.connect(self._on_import_raw_data)
        btn_layout.addWidget(self._btn_import_raw)

        self._btn_remove_raw = QPushButton("Ta bort")
        self._btn_remove_raw.setObjectName("btn_remove_raw")
        self._btn_remove_raw.clicked.connect(self._on_remove_raw_data)
        self._btn_remove_raw.setEnabled(False)
        btn_layout.addWidget(self._btn_remove_raw)

        btn_layout.addStretch()
        parent_layout.addLayout(btn_layout)

        # Reuse section (only visible if other profiles for same person have raw data)
        self._reuse_layout = QHBoxLayout()
        self._combo_reuse = QComboBox()
        self._combo_reuse.setObjectName("combo_reuse")
        self._btn_reuse = QPushButton("Använd befintlig")
        self._btn_reuse.setObjectName("btn_reuse")
        self._btn_reuse.clicked.connect(self._on_reuse_raw_data)

        self._reuse_layout.addWidget(QLabel("Befintlig data:"))
        self._reuse_layout.addWidget(self._combo_reuse, 1)
        self._reuse_layout.addWidget(self._btn_reuse)

        parent_layout.addLayout(self._reuse_layout)

        # Initially hide reuse section; populated later
        self._combo_reuse.setVisible(False)
        self._btn_reuse.setVisible(False)

        # Update raw status display
        self._update_raw_status_display()
        self._populate_reuse_options()

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

    def _prepopulate_edit_fields(self) -> None:
        """Pre-populate form fields when editing an existing profile."""
        if self._existing_profile is None:
            return

        # Pre-select company
        company_index = self._combo_company.findData(
            self._existing_profile.company_id
        )
        if company_index >= 0:
            self._combo_company.setCurrentIndex(company_index)

        # Pre-select test type
        test_type_index = self._combo_test_type.findData(
            self._existing_profile.test_type
        )
        if test_type_index >= 0:
            self._combo_test_type.setCurrentIndex(test_type_index)

        # Pre-fill text fields
        self._edit_kit_name.setText(self._existing_profile.kit_name or "")
        self._edit_kit_id.setText(self._existing_profile.kit_id or "")
        self._edit_notes.setPlainText(self._existing_profile.notes or "")

    # ------------------------------------------------------------------
    # Raw data helpers
    # ------------------------------------------------------------------

    def _get_current_raw_data_file(self) -> Optional[str]:
        """Get the current effective raw_data_file value considering pending changes."""
        if self._raw_data_changed:
            return self._pending_raw_data_file if self._pending_raw_data_file else None
        if self._existing_profile:
            return self._existing_profile.raw_data_file
        return None

    def _update_raw_status_display(self) -> None:
        """Update the raw data status label and button states."""
        current_file = self._get_current_raw_data_file()
        if current_file:
            self._label_raw_status.setText(f"Fil: {current_file}")
            self._btn_remove_raw.setEnabled(True)
        else:
            self._label_raw_status.setText("Ingen fil")
            self._btn_remove_raw.setEnabled(False)

    def _populate_reuse_options(self) -> None:
        """Populate the reuse dropdown with raw data files from same person's other profiles."""
        self._combo_reuse.clear()

        # Find other profiles for the same person that have raw_data_file set
        reusable_files: list[str] = []
        current_profile_id = self._existing_profile.id if self._existing_profile else None

        for profile in self._project_data.dna_profiles:
            if profile.person_id != self._person_id:
                continue
            if profile.id == current_profile_id:
                continue
            if profile.raw_data_file:
                if profile.raw_data_file not in reusable_files:
                    reusable_files.append(profile.raw_data_file)

        if reusable_files:
            for filename in reusable_files:
                self._combo_reuse.addItem(filename, filename)
            self._combo_reuse.setVisible(True)
            self._btn_reuse.setVisible(True)
            # Also show the label (parent of _reuse_layout)
        else:
            self._combo_reuse.setVisible(False)
            self._btn_reuse.setVisible(False)

    # ------------------------------------------------------------------
    # Raw data actions
    # ------------------------------------------------------------------

    def _on_import_raw_data(self) -> None:
        """Handle the 'Importera DNA-data...' button click."""
        if self._project_folder is None:
            QMessageBox.warning(
                self,
                "Projekt ej sparat",
                "Projektet måste sparas innan DNA-data kan importeras.",
            )
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Välj DNA-datafil",
            "",
            "DNA-filer (*.txt *.csv);;Alla filer (*)",
        )

        if not file_path:
            return

        source_path = Path(file_path)

        # Check file size
        try:
            file_size = source_path.stat().st_size
        except OSError as e:
            QMessageBox.critical(
                self,
                "Filfel",
                f"Kunde inte läsa filen: {e}",
            )
            return

        if file_size > _MAX_FILE_SIZE_BYTES:
            QMessageBox.critical(
                self,
                "Filen är för stor",
                "Filen är för stor. Maximal filstorlek är 100 MB.",
            )
            return

        # Show busy cursor during parsing
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()

        try:
            from slaktbusken.services.dna_raw_parser import parse_raw_dna_file

            result = parse_raw_dna_file(source_path)
        except ValueError as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(
                self,
                "Format ej igenkänt",
                str(e),
            )
            return
        except Exception as e:
            QApplication.restoreOverrideCursor()
            logger.exception("Unexpected error parsing raw DNA file")
            QMessageBox.critical(
                self,
                "Fel vid import",
                f"Ett oväntat fel uppstod: {e}",
            )
            return

        # Determine profile_id for filename
        profile_id = (
            self._existing_profile.id if self._existing_profile else str(uuid4())
        )
        # If creating a new profile, store the ID for later use
        if self._existing_profile is None:
            self._new_profile_id = profile_id

        filename = f"raw_{profile_id}.json"

        # Write parsed data to dna/ subfolder
        try:
            import json

            # Ensure dna/ folder exists
            dna_folder = self._project_folder / "dna"
            dna_folder.mkdir(parents=True, exist_ok=True)

            # Serialize records to list of dicts
            records_data = [
                {
                    "rsid": rec.rsid,
                    "chromosome": rec.chromosome,
                    "position": rec.position,
                    "alleles": rec.alleles,
                }
                for rec in result.records
            ]
            output_data = {
                "format": result.format_detected,
                "record_count": len(result.records),
                "skipped_rows": result.skipped_rows,
                "records": records_data,
            }

            file_path_out = dna_folder / filename
            file_path_out.write_text(
                json.dumps(output_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            QApplication.restoreOverrideCursor()
            logger.exception("Error writing raw DNA data file")
            QMessageBox.critical(
                self,
                "Skrivfel",
                f"Kunde inte spara DNA-data: {e}",
            )
            return

        QApplication.restoreOverrideCursor()

        # Update pending state
        self._pending_raw_data_file = filename
        self._raw_data_changed = True
        self._update_raw_status_display()

        # Show warning if rows were skipped
        if result.skipped_rows > 0:
            QMessageBox.warning(
                self,
                "Ofullständig import",
                f"Importen slutfördes men {result.skipped_rows} "
                f"rader kunde inte tolkas och hoppades över.",
            )

        # Success feedback
        if result.skipped_rows == 0:
            QMessageBox.information(
                self,
                "Import klar",
                f"Importerade {len(result.records)} SNP-poster "
                f"({result.format_detected}).",
            )

    def _on_remove_raw_data(self) -> None:
        """Handle the 'Ta bort' button click — remove raw data file association."""
        self._pending_raw_data_file = None
        self._raw_data_changed = True
        self._update_raw_status_display()

    def _on_reuse_raw_data(self) -> None:
        """Handle the 'Använd befintlig' button click — reuse another profile's raw data."""
        selected_file = self._combo_reuse.currentData()
        if selected_file:
            self._pending_raw_data_file = selected_file
            self._raw_data_changed = True
            self._update_raw_status_display()

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
        """Handle OK click: validate and create/update profile or show errors."""
        errors = self._validate()
        if errors:
            self._label_error.setText("\n".join(errors))
            return

        # Clear any previous error
        self._label_error.setText("")

        # Determine raw_data_file value
        raw_data_file: Optional[str] = None
        if self._raw_data_changed:
            raw_data_file = self._pending_raw_data_file
        elif self._existing_profile:
            raw_data_file = self._existing_profile.raw_data_file

        if self._existing_profile is not None:
            # Edit mode: preserve original id and person_id
            self._edited_profile = DnaProfile(
                id=self._existing_profile.id,
                person_id=self._existing_profile.person_id,
                company_id=self._combo_company.currentData(),
                test_type=self._combo_test_type.currentData(),
                kit_name=self._edit_kit_name.text().strip(),
                kit_id=self._edit_kit_id.text().strip(),
                notes=self._edit_notes.toPlainText().strip(),
                raw_data_file=raw_data_file,
            )
        else:
            # Create mode: use stored ID if import was done, otherwise new uuid4
            profile_id = getattr(self, "_new_profile_id", None) or str(uuid4())
            self._created_profile = DnaProfile(
                id=profile_id,
                person_id=self._person_id,
                company_id=self._combo_company.currentData(),
                test_type=self._combo_test_type.currentData(),
                kit_name=self._edit_kit_name.text().strip(),
                kit_id=self._edit_kit_id.text().strip(),
                notes=self._edit_notes.toPlainText().strip(),
                raw_data_file=raw_data_file,
            )
        self.accept()
