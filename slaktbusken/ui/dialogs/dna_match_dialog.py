"""DNA Match creation/editing dialog for Släktbusken.

Provides a modal form for creating or editing a DnaMatch between two DNA profiles.
All UI text is in Swedish.
"""

from __future__ import annotations

from typing import Optional
from uuid import uuid4

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.dna import DnaMatch, DnaProfile
from slaktbusken.model.project import ProjectData


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
        parent: Optional parent widget.
    """

    def __init__(
        self,
        project_data: ProjectData,
        person_id: str,
        existing_match: Optional[DnaMatch] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._project_data = project_data
        self._person_id = person_id
        self._existing_match = existing_match
        self._created_match: Optional[DnaMatch] = None
        self._edited_match: Optional[DnaMatch] = None

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

        # Select profile1
        idx1 = self._combo_profile1.findData(self._existing_match.profile1_id)
        if idx1 != -1:
            self._combo_profile1.setCurrentIndex(idx1)

        # Select profile2 (profile1 change triggers filtering of profile2 dropdown)
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
    # Validation
    # ------------------------------------------------------------------

    def _validate(self) -> list[str]:
        """Validate form inputs. Returns list of error messages (empty = valid)."""
        errors: list[str] = []

        # Profile 1 required
        profile1_id = self._combo_profile1.currentData()
        if not profile1_id:
            errors.append("Välj en profil 1.")

        # Profile 2 required
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
        )

        if self._existing_match is not None:
            self._edited_match = match
        else:
            self._created_match = match

        self.accept()
