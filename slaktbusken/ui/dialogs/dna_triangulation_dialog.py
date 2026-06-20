"""DNA Triangulation creation/editing dialog for Släktbusken.

Provides a modal form for creating or editing a DnaTriangulation.
The dialog works like the DNA match dialog: pick a company, select profiles,
and enter shared cM, segment count, and largest segment cM.
All UI text is in Swedish.
"""

from __future__ import annotations

from typing import Optional
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.dna import DnaProfile, DnaTriangulation
from slaktbusken.model.person import Person
from slaktbusken.model.project import ProjectData


def has_dna_match(
    person_a_id: str, person_b_id: str, project_data: ProjectData
) -> bool:
    """Check if any DNA match links profiles of person A with profiles of person B.

    Checks both directions: profile1_id belonging to A and profile2_id to B,
    or profile1_id belonging to B and profile2_id to A.
    """
    profiles_a = {
        p.id for p in project_data.dna_profiles if p.person_id == person_a_id
    }
    profiles_b = {
        p.id for p in project_data.dna_profiles if p.person_id == person_b_id
    }

    for match in project_data.dna_matches:
        if (
            match.profile1_id in profiles_a and match.profile2_id in profiles_b
        ) or (
            match.profile1_id in profiles_b and match.profile2_id in profiles_a
        ):
            return True
    return False


def get_eligible_triangulation_persons(
    active_person_id: str,
    selected_person_ids: list[str],
    company_id: str | None,
    project_data: ProjectData,
) -> list[Person]:
    """Return persons eligible to be added to a triangulation.

    A person is eligible if:
    1. They are not the active person
    2. They are not already selected
    3. A DNA match exists between the active person and the candidate
    4. For each already-selected person, a DNA match exists between
       that selected person and the candidate
    5. If company_id is set, the candidate has at least one DnaProfile
       with that company_id
    """
    eligible: list[Person] = []

    for person in project_data.persons:
        # Rule 1: not the active person
        if person.id == active_person_id:
            continue

        # Rule 2: not already selected
        if person.id in selected_person_ids:
            continue

        # Rule 5: if company filter, candidate must have a profile in that company
        if company_id:
            has_company_profile = any(
                p.company_id == company_id and p.person_id == person.id
                for p in project_data.dna_profiles
            )
            if not has_company_profile:
                continue

        # Rule 3: match with active person
        if not has_dna_match(active_person_id, person.id, project_data):
            continue

        # Rule 4: match with every already-selected person
        all_match = True
        for selected_id in selected_person_ids:
            if not has_dna_match(selected_id, person.id, project_data):
                all_match = False
                break

        if all_match:
            eligible.append(person)

    return eligible


def _profile_display_label(profile: DnaProfile, project_data: ProjectData) -> str:
    """Build a human-readable label for a DNA profile dropdown entry."""
    # Find the person who owns this profile
    person_name = ""
    for person in project_data.persons:
        if person.id == profile.person_id:
            if person.names:
                name = person.names[0]
                parts = []
                if name.given:
                    parts.append(name.given)
                if name.surname:
                    parts.append(name.surname)
                if parts:
                    person_name = " ".join(parts)
            break

    company_name = ""
    for company in project_data.dna_companies:
        if company.id == profile.company_id:
            company_name = company.name
            break

    if profile.kit_name:
        label = profile.kit_name
    elif profile.kit_id:
        label = profile.kit_id
    else:
        label = profile.test_type

    if person_name:
        return f"{person_name} — {label} ({company_name})"
    return f"{label} ({company_name})"


class DnaTriangulationDialog(QDialog):
    """Modal dialog for creating or editing a DNA triangulation.

    Works like the DNA match dialog: select company, pick profiles (min 3),
    and enter shared cM, segment count, largest segment cM.

    Args:
        project_data: The ProjectData containing all entities.
        person_id: The ID of the active person.
        existing_triangulation: Optional existing DnaTriangulation to edit.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        project_data: ProjectData,
        person_id: str,
        existing_triangulation: Optional[DnaTriangulation] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._project_data = project_data
        self._person_id = person_id
        self._existing_triangulation = existing_triangulation
        self._created_triangulation: Optional[DnaTriangulation] = None
        self._edited_triangulation: Optional[DnaTriangulation] = None

        self.setWindowTitle("Ny triangulering")
        self.setMinimumWidth(450)

        self._setup_ui()
        self._populate_fields()

        if self._existing_triangulation is not None:
            self._apply_edit_mode()

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def created_triangulation(self) -> Optional[DnaTriangulation]:
        """The created DnaTriangulation, or None if dialog was cancelled."""
        return self._created_triangulation

    @property
    def edited_triangulation(self) -> Optional[DnaTriangulation]:
        """The edited DnaTriangulation, or None if dialog was cancelled."""
        return self._edited_triangulation

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

        self._spin_shared_cm = QDoubleSpinBox()
        self._spin_shared_cm.setRange(0.00, 10000.00)
        self._spin_shared_cm.setDecimals(2)
        self._spin_shared_cm.setSingleStep(0.01)
        self._spin_shared_cm.setValue(0.00)
        self._spin_shared_cm.setSpecialValueText("—")
        form.addRow("Delad cM:", self._spin_shared_cm)

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

        self._edit_notes = QPlainTextEdit()
        self._edit_notes.setMaximumHeight(80)
        self._edit_notes.setPlaceholderText("Valfritt, max 2000 tecken")
        form.addRow("Anteckningar:", self._edit_notes)

        layout.addLayout(form)

        # Profile selection section
        self._label_profiles = QLabel("Välj profiler (minst 3):")
        layout.addWidget(self._label_profiles)

        self._list_profiles = QListWidget()
        self._list_profiles.setSelectionMode(
            QListWidget.SelectionMode.MultiSelection
        )
        layout.addWidget(self._list_profiles)

        # Info label shown when fewer than 3 profiles available
        self._label_info = QLabel("")
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

        # Connect company change to re-filter profiles
        self._combo_company.currentIndexChanged.connect(
            self._on_company_changed
        )

    # ------------------------------------------------------------------
    # Field population
    # ------------------------------------------------------------------

    def _populate_fields(self) -> None:
        """Populate dropdowns with available values."""
        # Company dropdown
        self._combo_company.addItem("— Välj företag —", "")
        for company in self._project_data.dna_companies:
            self._combo_company.addItem(company.name, company.id)

    # ------------------------------------------------------------------
    # Edit mode
    # ------------------------------------------------------------------

    def _apply_edit_mode(self) -> None:
        """Pre-fill the form with values from the existing triangulation."""
        assert self._existing_triangulation is not None

        self.setWindowTitle("Redigera triangulering")

        # Select company
        idx = self._combo_company.findData(
            self._existing_triangulation.company_id
        )
        if idx != -1:
            self._combo_company.setCurrentIndex(idx)

        # Set numeric fields
        self._spin_shared_cm.setValue(
            self._existing_triangulation.shared_cm
        )
        self._spin_segment_count.setValue(
            self._existing_triangulation.segment_count
        )
        self._spin_largest_segment.setValue(
            self._existing_triangulation.largest_segment_cm
        )

        # Set notes
        self._edit_notes.setPlainText(self._existing_triangulation.notes)

        # Pre-select profiles from existing triangulation
        self._refresh_profile_list()
        for i in range(self._list_profiles.count()):
            item = self._list_profiles.item(i)
            if item:
                profile_id = item.data(Qt.ItemDataRole.UserRole)
                if profile_id in self._existing_triangulation.profile_ids:
                    item.setSelected(True)

    # ------------------------------------------------------------------
    # Profile list management
    # ------------------------------------------------------------------

    def _on_company_changed(self) -> None:
        """Re-filter profile list when company changes."""
        self._refresh_profile_list()

    def _refresh_profile_list(self) -> None:
        """Refresh the profile selection list based on selected company."""
        self._list_profiles.clear()

        company_id = self._combo_company.currentData()
        if not company_id:
            self._label_info.setText(
                "Välj ett företag för att visa tillgängliga profiler."
            )
            self._label_info.setVisible(True)
            return

        # Filter profiles by company
        profiles = [
            p for p in self._project_data.dna_profiles
            if p.company_id == company_id
        ]

        if len(profiles) < 3:
            self._label_info.setText(
                "Minst 3 profiler i samma företag krävs för triangulering."
            )
            self._label_info.setVisible(True)
        else:
            self._label_info.setVisible(False)

        for profile in profiles:
            label = _profile_display_label(profile, self._project_data)
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, profile.id)
            self._list_profiles.addItem(item)

    def _get_selected_profile_ids(self) -> list[str]:
        """Return IDs of currently selected profiles in the list."""
        selected_ids: list[str] = []
        for i in range(self._list_profiles.count()):
            item = self._list_profiles.item(i)
            if item and item.isSelected():
                profile_id = item.data(Qt.ItemDataRole.UserRole)
                if profile_id:
                    selected_ids.append(profile_id)
        return selected_ids

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate(self) -> list[str]:
        """Validate form inputs. Returns list of error messages (empty = valid)."""
        errors: list[str] = []

        # Company required
        company_id = self._combo_company.currentData()
        if not company_id:
            errors.append("Välj ett företag.")

        # Shared cM required (> 0)
        if self._spin_shared_cm.value() <= 0:
            errors.append("Delad cM måste anges.")

        # At least 3 profiles selected
        selected_ids = self._get_selected_profile_ids()
        if len(selected_ids) < 3:
            errors.append("Minst tre profiler måste väljas.")

        # Notes max length
        notes_text = self._edit_notes.toPlainText()
        if len(notes_text) > 2000:
            errors.append("Anteckningar får inte överstiga 2000 tecken.")

        return errors

    # ------------------------------------------------------------------
    # Accept handler
    # ------------------------------------------------------------------

    def _on_accept(self) -> None:
        """Handle OK click: validate and create/edit triangulation or show errors."""
        errors = self._validate()
        if errors:
            self._label_error.setText("\n".join(errors))
            return

        # Clear any previous error
        self._label_error.setText("")

        company_id = self._combo_company.currentData()
        profile_ids = self._get_selected_profile_ids()

        # Build the DnaTriangulation
        triangulation_id = (
            self._existing_triangulation.id
            if self._existing_triangulation is not None
            else str(uuid4())
        )

        cluster_id = (
            self._existing_triangulation.cluster_id
            if self._existing_triangulation is not None
            else None
        )

        triangulation = DnaTriangulation(
            id=triangulation_id,
            company_id=company_id,
            profile_ids=profile_ids,
            shared_cm=self._spin_shared_cm.value(),
            segment_count=self._spin_segment_count.value(),
            largest_segment_cm=self._spin_largest_segment.value(),
            cluster_id=cluster_id,
            notes=self._edit_notes.toPlainText().strip(),
        )

        if self._existing_triangulation is not None:
            self._edited_triangulation = triangulation
        else:
            self._created_triangulation = triangulation

        self.accept()
