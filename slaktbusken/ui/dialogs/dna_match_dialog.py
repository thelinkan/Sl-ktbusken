"""DNA Match creation/editing dialog for Släktbusken.

Provides a modal form for creating or editing a DnaMatch between two DNA profiles.
All UI text is in Swedish.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from uuid import uuid4

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.dna import DnaMatch, DnaProfile
from slaktbusken.model.project import ProjectData
from slaktbusken.services.dna_match_csv_parser import (
    MatchCsvParseResult,
    parse_match_csv,
)
from slaktbusken.services.match_segment_storage import save_match_segments


def _profile_display_label(profile: DnaProfile, project_data: ProjectData) -> str:
    """Build a human-readable label for a DNA profile dropdown entry."""
    company_name = ""
    for company in project_data.dna_companies:
        if company.id == profile.company_id:
            company_name = company.name
            break

    if profile.kit_name:
        return f"{profile.kit_name} ({company_name}, {profile.test_type})"
    if profile.kit_id:
        return f"{profile.kit_id} ({company_name}, {profile.test_type})"
    return f"({company_name}, {profile.test_type})"


class DnaMatchDialog(QDialog):
    """Modal dialog for creating or editing a DNA match.

    Args:
        project_data: The ProjectData containing DNA profiles.
        person_id: The ID of the current person.
        existing_match: Optional existing DnaMatch to edit.
        project_path: Optional path to the project file or folder for segment storage.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        project_data: ProjectData,
        person_id: str,
        existing_match: Optional[DnaMatch] = None,
        project_path: Optional[Path] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._project_data = project_data
        self._person_id = person_id
        self._existing_match = existing_match
        self._created_match: Optional[DnaMatch] = None
        self._edited_match: Optional[DnaMatch] = None
        self._parsed_result: Optional[MatchCsvParseResult] = None

        # Resolve project path for segment storage
        if project_path is not None:
            if project_path.is_dir():
                self._project_path = project_path
            else:
                self._project_path = project_path.parent
        else:
            self._project_path: Optional[Path] = None

        self.setWindowTitle("Ny DNA-matchning")
        self.setMinimumWidth(400)

        self._setup_ui()
        self._populate_fields()
        self._check_profiles()

        if self._existing_match is not None:
            self._apply_edit_mode()

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def created_match(self) -> Optional[DnaMatch]:
        """The created DnaMatch, or None if dialog was cancelled."""
        return self._created_match

    @property
    def edited_match(self) -> Optional[DnaMatch]:
        """The edited DnaMatch, or None if dialog was cancelled."""
        return self._edited_match

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Build the dialog UI programmatically."""
        layout = QVBoxLayout(self)

        # Form layout for fields
        form = QFormLayout()

        self._combo_profile1 = QComboBox()
        form.addRow("Profil 1:", self._combo_profile1)

        self._combo_profile2 = QComboBox()
        form.addRow("Profil 2:", self._combo_profile2)

        self._spin_shared_cm = QDoubleSpinBox()
        self._spin_shared_cm.setRange(0.01, 10000.00)
        self._spin_shared_cm.setDecimals(2)
        self._spin_shared_cm.setSingleStep(0.01)
        form.addRow("Delad cM:", self._spin_shared_cm)

        self._spin_shared_pct = QDoubleSpinBox()
        self._spin_shared_pct.setRange(0.00, 100.00)
        self._spin_shared_pct.setDecimals(2)
        self._spin_shared_pct.setSingleStep(0.01)
        self._spin_shared_pct.setValue(0.00)
        self._spin_shared_pct.setSpecialValueText("—")
        form.addRow("Delad %:", self._spin_shared_pct)

        self._spin_segment_count = QSpinBox()
        self._spin_segment_count.setRange(0, 100000)
        self._spin_segment_count.setValue(0)
        self._spin_segment_count.setSpecialValueText("—")
        form.addRow("Antal segment:", self._spin_segment_count)

        self._spin_largest_segment = QDoubleSpinBox()
        self._spin_largest_segment.setRange(0.00, 10000.00)
        self._spin_largest_segment.setDecimals(2)
        self._spin_largest_segment.setSingleStep(0.01)
        self._spin_largest_segment.setValue(0.00)
        self._spin_largest_segment.setSpecialValueText("—")
        form.addRow("Största segment cM:", self._spin_largest_segment)

        self._edit_match_source = QLineEdit()
        self._edit_match_source.setMaxLength(200)
        self._edit_match_source.setText("internal")
        self._edit_match_source.setPlaceholderText("Max 200 tecken")
        form.addRow("Matchkälla:", self._edit_match_source)

        self._edit_notes = QPlainTextEdit()
        self._edit_notes.setMaximumHeight(100)
        self._edit_notes.setPlaceholderText("Valfritt, max 2000 tecken")
        form.addRow("Anteckningar:", self._edit_notes)

        layout.addLayout(form)

        # --- Match data paste section (between Anteckningar and profile selection info) ---
        self._setup_paste_section(layout)

        # Info label shown when no other profiles exist
        self._label_info = QLabel(
            "Inga andra DNA-profiler finns att matcha mot."
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

    def _setup_paste_section(self, parent_layout: QVBoxLayout) -> None:
        """Set up the match data paste section."""
        # Label
        paste_label = QLabel("Klistra in matchdata:")
        parent_layout.addWidget(paste_label)

        # Text area for pasting CSV data
        self._paste_text = QPlainTextEdit()
        self._paste_text.setMaximumHeight(80)
        self._paste_text.setPlaceholderText(
            "Klistra in CSV-data från MyHeritage här..."
        )
        parent_layout.addWidget(self._paste_text)

        # Parse button
        btn_layout = QHBoxLayout()
        self._btn_parse = QPushButton("Tolka data")
        self._btn_parse.clicked.connect(self._on_parse_paste)
        btn_layout.addWidget(self._btn_parse)
        btn_layout.addStretch()
        parent_layout.addLayout(btn_layout)

        # Parse status/error label
        self._label_parse_status = QLabel("")
        self._label_parse_status.setWordWrap(True)
        self._label_parse_status.setVisible(False)
        parent_layout.addWidget(self._label_parse_status)

        # Segment preview table
        self._segment_table = QTableWidget()
        self._segment_table.setColumnCount(4)
        self._segment_table.setHorizontalHeaderLabels(
            ["Kromosom", "Start", "Slut", "cM"]
        )
        self._segment_table.setMaximumHeight(120)
        self._segment_table.setVisible(False)
        header = self._segment_table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        parent_layout.addWidget(self._segment_table)

        # Total shared cM label
        self._label_total_cm = QLabel("")
        self._label_total_cm.setVisible(False)
        parent_layout.addWidget(self._label_total_cm)

    # ------------------------------------------------------------------
    # Field population
    # ------------------------------------------------------------------

    def _populate_fields(self) -> None:
        """Populate dropdowns with available profiles."""
        # Profile 1: current person's profiles
        person_profiles = [
            p
            for p in self._project_data.dna_profiles
            if p.person_id == self._person_id
        ]

        self._combo_profile1.addItem("— Välj profil —", "")
        for profile in person_profiles:
            label = _profile_display_label(profile, self._project_data)
            self._combo_profile1.addItem(label, profile.id)

        # Profile 2: initially disabled with placeholder only
        self._combo_profile2.addItem("— Välj profil —", "")
        self._combo_profile2.setEnabled(False)

        # Connect profile1 change signal to filter profile2
        self._combo_profile1.currentIndexChanged.connect(
            self._on_profile1_changed
        )

        # Pre-select if exactly one profile; disable dropdown in that case
        if len(person_profiles) == 1:
            self._combo_profile1.setCurrentIndex(1)
            self._combo_profile1.setEnabled(False)

    def _check_profiles(self) -> None:
        """Check if other profiles exist; if not, show info and disable OK."""
        other_profiles = [
            p
            for p in self._project_data.dna_profiles
            if p.person_id != self._person_id
        ]
        if not other_profiles:
            self._label_info.setText(
                "Inga andra DNA-profiler finns att matcha mot."
            )
            self._label_info.setVisible(True)
            ok_button = self._button_box.button(
                QDialogButtonBox.StandardButton.Ok
            )
            if ok_button:
                ok_button.setEnabled(False)

    # ------------------------------------------------------------------
    # Edit mode
    # ------------------------------------------------------------------

    def _apply_edit_mode(self) -> None:
        """Pre-fill the form with values from the existing match."""
        assert self._existing_match is not None

        self.setWindowTitle("Redigera DNA-matchning")

        # In edit mode, profile1 might not belong to self._person_id
        # (the match could have been created from the other person's side).
        # Ensure both profiles are present in their dropdowns.

        # If profile1_id is not already in the combo, add it
        idx1 = self._combo_profile1.findData(self._existing_match.profile1_id)
        if idx1 == -1:
            # Profile1 belongs to another person — add it to the dropdown
            profile1 = next(
                (p for p in self._project_data.dna_profiles
                 if p.id == self._existing_match.profile1_id),
                None,
            )
            if profile1:
                label = _profile_display_label(profile1, self._project_data)
                self._combo_profile1.addItem(label, profile1.id)
            idx1 = self._combo_profile1.findData(self._existing_match.profile1_id)

        if idx1 != -1:
            self._combo_profile1.setCurrentIndex(idx1)

        # After setting profile1, _on_profile1_changed fires and repopulates
        # profile2. Now select profile2.
        idx2 = self._combo_profile2.findData(self._existing_match.profile2_id)
        if idx2 == -1:
            # Profile2 not found (different company or not included) — add it
            profile2 = next(
                (p for p in self._project_data.dna_profiles
                 if p.id == self._existing_match.profile2_id),
                None,
            )
            if profile2:
                label = _profile_display_label(profile2, self._project_data)
                self._combo_profile2.addItem(label, profile2.id)
            idx2 = self._combo_profile2.findData(self._existing_match.profile2_id)

        if idx2 != -1:
            self._combo_profile2.setCurrentIndex(idx2)

        # Populate numeric fields
        self._spin_shared_cm.setValue(self._existing_match.shared_cm)
        self._spin_shared_pct.setValue(self._existing_match.shared_percentage)
        self._spin_segment_count.setValue(self._existing_match.segment_count)
        self._spin_largest_segment.setValue(self._existing_match.largest_segment_cm)

        # Populate text fields
        self._edit_match_source.setText(self._existing_match.match_source)
        self._edit_notes.setPlainText(self._existing_match.notes)

    # ------------------------------------------------------------------
    # Profile filtering
    # ------------------------------------------------------------------

    def _on_profile1_changed(self) -> None:
        """Filter profile2 options to same-company profiles when profile1 changes."""
        profile1_id = self._combo_profile1.currentData()

        ok_button = self._button_box.button(
            QDialogButtonBox.StandardButton.Ok
        )

        # No valid selection — disable profile2, hide info
        if not profile1_id:
            self._combo_profile2.clear()
            self._combo_profile2.addItem("— Välj profil —", "")
            self._combo_profile2.setEnabled(False)
            self._label_info.setVisible(False)
            if ok_button:
                ok_button.setEnabled(True)
            return

        # Look up profile1's company_id
        profile1_company_id = None
        for p in self._project_data.dna_profiles:
            if p.id == profile1_id:
                profile1_company_id = p.company_id
                break

        # Clear and repopulate profile2
        self._combo_profile2.clear()
        self._combo_profile2.addItem("— Välj profil —", "")

        # Filter: same company_id, exclude profile1 itself
        matching_profiles = [
            p
            for p in self._project_data.dna_profiles
            if p.company_id == profile1_company_id and p.id != profile1_id
        ]

        for profile in matching_profiles:
            label = _profile_display_label(profile, self._project_data)
            self._combo_profile2.addItem(label, profile.id)

        if not matching_profiles:
            # No matching profiles for this company
            self._label_info.setText(
                "Det finns inga matchbara profiler för detta företag."
            )
            self._label_info.setVisible(True)
            self._combo_profile2.setEnabled(False)
            if ok_button:
                ok_button.setEnabled(False)
        else:
            # Matching profiles exist
            self._label_info.setVisible(False)
            self._combo_profile2.setEnabled(True)
            if ok_button:
                ok_button.setEnabled(True)

    # ------------------------------------------------------------------
    # Paste parsing
    # ------------------------------------------------------------------

    def _on_parse_paste(self) -> None:
        """Handle the 'Tolka data' button click: parse pasted CSV data."""
        text = self._paste_text.toPlainText().strip()
        if not text:
            self._clear_parse_preview()
            return

        try:
            result = parse_match_csv(text)
        except ValueError as e:
            self._show_parse_error(str(e))
            return

        self._parsed_result = result
        self._show_parse_preview(result)

        # Suggest profile 2 if not already set and match_name is available
        if result.match_name and not self._combo_profile2.currentData():
            self._suggest_profile2(result.match_name)

    def _show_parse_error(self, message: str) -> None:
        """Display a parse error message."""
        self._label_parse_status.setText(message)
        self._label_parse_status.setStyleSheet("color: red;")
        self._label_parse_status.setVisible(True)
        self._segment_table.setVisible(False)
        self._label_total_cm.setVisible(False)
        self._parsed_result = None

    def _clear_parse_preview(self) -> None:
        """Clear the parse preview area."""
        self._label_parse_status.setVisible(False)
        self._segment_table.setVisible(False)
        self._label_total_cm.setVisible(False)
        self._parsed_result = None

    def _show_parse_preview(self, result: MatchCsvParseResult) -> None:
        """Display parsed segment preview table and total cM."""
        segments = result.segments

        # Set up table
        self._segment_table.setRowCount(len(segments))
        for row_idx, seg in enumerate(segments):
            self._segment_table.setItem(
                row_idx, 0, QTableWidgetItem(seg.chromosome)
            )
            self._segment_table.setItem(
                row_idx, 1, QTableWidgetItem(str(seg.start_position))
            )
            self._segment_table.setItem(
                row_idx, 2, QTableWidgetItem(str(seg.end_position))
            )
            self._segment_table.setItem(
                row_idx, 3, QTableWidgetItem(f"{seg.centimorgans:.2f}")
            )
        self._segment_table.setVisible(True)

        # Calculate and display total shared cM
        total_cm = sum(seg.centimorgans for seg in segments)
        status_parts = [f"Totalt delad cM: {total_cm:.2f}"]
        if result.skipped_rows > 0:
            status_parts.append(
                f"({result.skipped_rows} rader hoppades över)"
            )
        self._label_total_cm.setText(" ".join(status_parts))
        self._label_total_cm.setVisible(True)

        # Clear any previous error and show success
        self._label_parse_status.setText(
            f"{len(segments)} segment tolkade."
        )
        self._label_parse_status.setStyleSheet("color: green;")
        self._label_parse_status.setVisible(True)

    # ------------------------------------------------------------------
    # Profile 2 suggestion
    # ------------------------------------------------------------------

    def _suggest_profile2(self, match_name: str) -> None:
        """Search for a matching person and suggest their profile as Profile 2.

        Performs case-insensitive substring match on given name and surname.
        Excludes Profile 1's person from results.
        """
        match_name_lower = match_name.lower()
        profile1_id = self._combo_profile1.currentData()

        # Find profile1's person_id to exclude
        profile1_person_id = None
        if profile1_id:
            for p in self._project_data.dna_profiles:
                if p.id == profile1_id:
                    profile1_person_id = p.person_id
                    break

        # Search persons whose name matches
        matching_person_ids: list[str] = []
        for person in self._project_data.persons:
            if person.id == profile1_person_id:
                continue
            for name in person.names:
                given_lower = name.given.lower() if name.given else ""
                surname_lower = name.surname.lower() if name.surname else ""
                if (
                    match_name_lower in given_lower
                    or match_name_lower in surname_lower
                    or given_lower in match_name_lower
                    or surname_lower in match_name_lower
                ):
                    matching_person_ids.append(person.id)
                    break

        if not matching_person_ids:
            # No matching person found - show warning
            reply = QMessageBox.question(
                self,
                "Ingen matchande person",
                f"Ingen person hittades som matchar '{match_name}'.\n"
                "Vill du skapa matchningen ändå utan Profil 2?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.No:
                self._clear_parse_preview()
            return

        # Find a DNA profile belonging to a matching person (same company as profile1)
        profile1_company_id = None
        if profile1_id:
            for p in self._project_data.dna_profiles:
                if p.id == profile1_id:
                    profile1_company_id = p.company_id
                    break

        for person_id in matching_person_ids:
            for profile in self._project_data.dna_profiles:
                if (
                    profile.person_id == person_id
                    and profile.company_id == profile1_company_id
                    and profile.id != profile1_id
                ):
                    # Found a matching profile - select it in combo
                    idx = self._combo_profile2.findData(profile.id)
                    if idx != -1:
                        self._combo_profile2.setCurrentIndex(idx)
                        return

        # Matching person found but no matching profile in same company
        # Still no profile to suggest, but person exists
        return

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate(self) -> list[str]:
        """Validate form inputs. Returns list of error messages (empty = valid)."""
        errors: list[str] = []

        # Profile 1 required
        profile1_id = self._combo_profile1.currentData()
        if not profile1_id:
            errors.append("Välj en profil 1.")

        # Profile 2 required (unless user confirmed no-match via paste)
        profile2_id = self._combo_profile2.currentData()
        if not profile2_id:
            errors.append("Välj en profil 2.")

        # Profiles must differ
        if profile1_id and profile2_id and profile1_id == profile2_id:
            errors.append("Profil 1 och Profil 2 måste vara olika.")

        # Shared cM required (> 0)
        if self._spin_shared_cm.value() <= 0:
            errors.append("Delad cM måste anges.")

        # Notes max length
        notes_text = self._edit_notes.toPlainText()
        if len(notes_text) > 2000:
            errors.append("Anteckningar får inte överstiga 2000 tecken.")

        return errors

    # ------------------------------------------------------------------
    # Accept handler
    # ------------------------------------------------------------------

    def _on_accept(self) -> None:
        """Handle OK click: validate and create/edit match or show errors."""
        errors = self._validate()
        if errors:
            self._label_error.setText("\n".join(errors))
            return

        # Clear any previous error
        self._label_error.setText("")

        # Build the DnaMatch
        match_id = (
            self._existing_match.id
            if self._existing_match is not None
            else str(uuid4())
        )

        # Check for existing segment data replacement
        if (
            self._parsed_result is not None
            and self._existing_match is not None
            and self._existing_match.segment_file
        ):
            reply = QMessageBox.question(
                self,
                "Ersätt segmentdata",
                "Ersätt befintlig segmentdata?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.No:
                return

        # Determine segment_file value
        segment_file = (
            self._existing_match.segment_file
            if self._existing_match is not None
            else None
        )

        # Save parsed segments if available
        if self._parsed_result is not None and self._project_path is not None:
            segment_file = save_match_segments(
                self._project_path, match_id, self._parsed_result.segments
            )

        match = DnaMatch(
            id=match_id,
            profile1_id=self._combo_profile1.currentData(),
            profile2_id=self._combo_profile2.currentData(),
            shared_cm=self._spin_shared_cm.value(),
            shared_percentage=self._spin_shared_pct.value(),
            segment_count=self._spin_segment_count.value(),
            largest_segment_cm=self._spin_largest_segment.value(),
            match_source=self._edit_match_source.text().strip(),
            notes=self._edit_notes.toPlainText().strip(),
            segment_file=segment_file,
        )

        if self._existing_match is not None:
            self._edited_match = match
        else:
            self._created_match = match

        self.accept()
