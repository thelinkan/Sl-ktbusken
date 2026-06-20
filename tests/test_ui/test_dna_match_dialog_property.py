"""Property-based tests for DnaMatchDialog.

Feature: dna-management-from-person-editor

Validates: Requirements 4.3, 4.4, 4.6, 4.7
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from PySide6.QtWidgets import QApplication

from slaktbusken.model.dna import DnaCompany, DnaProfile
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.ui.dialogs.dna_match_dialog import DnaMatchDialog
from tests.conftest import dna_profile_strategy


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_person_id_strategy = st.integers(min_value=1, max_value=9999).map(
    lambda n: f"person_{n}"
)

_shared_cm_strategy = st.floats(min_value=0.01, max_value=10000.00, allow_nan=False)

_shared_pct_strategy = st.floats(min_value=0.01, max_value=100.00, allow_nan=False)

_segment_count_strategy = st.integers(min_value=1, max_value=100000)

_largest_segment_strategy = st.floats(min_value=0.01, max_value=10000.00, allow_nan=False)

_match_source_strategy = st.text(
    alphabet=st.characters(categories=("L", "N")),
    min_size=0,
    max_size=200,
)

# Notes: avoid Unicode whitespace category "Z" (e.g. \xa0) since QPlainTextEdit
# may normalize them. Use letters, numbers, and basic punctuation instead.
_notes_strategy = st.text(
    alphabet=st.characters(
        categories=("L", "N", "P"),
        exclude_characters="\x00",
    ),
    min_size=0,
    max_size=200,
)

# Which required profile field(s) to leave missing
_invalid_scenario_strategy = st.sampled_from(
    ["missing_profile1", "missing_profile2", "missing_both"]
)

_optional_text = st.text(
    alphabet=st.characters(categories=("L", "N")),
    min_size=0,
    max_size=50,
)


# ---------------------------------------------------------------------------
# Property 3: Match creation round-trip
# ---------------------------------------------------------------------------


class TestDnaMatchCreationRoundTrip:
    """Feature: dna-management-from-person-editor, Property 3: Match creation round-trip

    Generate random valid two distinct profile IDs, shared cM, and optional fields.
    Verify resulting DnaMatch has correct profile1_id, profile2_id, shared_cm,
    and optional fields.

    **Validates: Requirements 4.3, 4.4**
    """

    @given(
        person1_id=_person_id_strategy,
        person2_id=_person_id_strategy,
        profile1=dna_profile_strategy(),
        profile2=dna_profile_strategy(),
        shared_cm=_shared_cm_strategy,
        shared_pct=_shared_pct_strategy,
        segment_count=_segment_count_strategy,
        largest_segment=_largest_segment_strategy,
        match_source=_match_source_strategy,
        notes=_notes_strategy,
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_match_creation_round_trip(
        self,
        qtbot,
        person1_id: str,
        person2_id: str,
        profile1: DnaProfile,
        profile2: DnaProfile,
        shared_cm: float,
        shared_pct: float,
        segment_count: int,
        largest_segment: float,
        match_source: str,
        notes: str,
    ) -> None:
        """After programmatically filling a valid match form and accepting,
        created_match SHALL have correct profile1_id, profile2_id, shared_cm,
        shared_percentage, segment_count, largest_segment_cm, match_source, and notes.

        Feature: dna-management-from-person-editor, Property 3: Match creation round-trip
        **Validates: Requirements 4.3, 4.4**
        """
        # Ensure distinct person IDs
        if person1_id == person2_id:
            person2_id = person1_id + "_other"

        # Assign profiles to distinct persons; profile2 must share company_id
        # with profile1 for same-company filtering to include it in the dropdown.
        profile1 = DnaProfile(
            id=profile1.id,
            person_id=person1_id,
            company_id=profile1.company_id,
            test_type=profile1.test_type,
            kit_name=profile1.kit_name,
            kit_id=profile1.kit_id,
        )
        profile2 = DnaProfile(
            id=profile2.id,
            person_id=person2_id,
            company_id=profile1.company_id,
            test_type=profile2.test_type,
            kit_name=profile2.kit_name,
            kit_id=profile2.kit_id,
        )

        # Ensure distinct profile IDs
        if profile1.id == profile2.id:
            profile2 = DnaProfile(
                id=profile2.id + "_alt",
                person_id=profile2.person_id,
                company_id=profile2.company_id,
                test_type=profile2.test_type,
                kit_name=profile2.kit_name,
                kit_id=profile2.kit_id,
            )

        # Create DnaCompanies for label rendering (both profiles share company)
        company = DnaCompany(id=profile1.company_id, name="TestDNA")

        # Build ProjectData with both profiles and their company
        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_companies=[company],
            dna_profiles=[profile1, profile2],
        )

        # Create the dialog with person1 as current person
        dialog = DnaMatchDialog(project_data, person1_id)
        qtbot.addWidget(dialog)

        # Select profile1 in combo_profile1
        idx1 = dialog._combo_profile1.findData(profile1.id)
        assert idx1 != -1, f"Profile1 {profile1.id} not found in dropdown"
        dialog._combo_profile1.setCurrentIndex(idx1)

        # Select profile2 in combo_profile2
        idx2 = dialog._combo_profile2.findData(profile2.id)
        assert idx2 != -1, f"Profile2 {profile2.id} not found in dropdown"
        dialog._combo_profile2.setCurrentIndex(idx2)

        # Set numeric fields
        dialog._spin_shared_cm.setValue(shared_cm)
        dialog._spin_shared_pct.setValue(shared_pct)
        dialog._spin_segment_count.setValue(segment_count)
        dialog._spin_largest_segment.setValue(largest_segment)

        # Set text fields
        dialog._edit_match_source.setText(match_source)
        dialog._edit_notes.setPlainText(notes)

        # Trigger accept
        dialog._on_accept()

        # Verify the created match
        match = dialog.created_match
        assert match is not None, "Expected created_match to be set after accept"
        assert match.profile1_id == profile1.id
        assert match.profile2_id == profile2.id
        # Spinboxes round to 2 decimal places
        assert match.shared_cm == pytest.approx(
            dialog._spin_shared_cm.value(), abs=0.01
        )
        assert match.shared_percentage == pytest.approx(
            dialog._spin_shared_pct.value(), abs=0.01
        )
        assert match.segment_count == dialog._spin_segment_count.value()
        assert match.largest_segment_cm == pytest.approx(
            dialog._spin_largest_segment.value(), abs=0.01
        )
        assert match.match_source == match_source.strip()
        assert match.notes == notes.strip()
        # Verify id is a valid UUID string (non-empty)
        assert len(match.id) > 0


# ---------------------------------------------------------------------------
# Property 4: Match validation rejects invalid forms
# ---------------------------------------------------------------------------


class TestMatchValidationRejectsInvalidForms:
    """Feature: dna-management-from-person-editor, Property 4: Match validation rejects invalid forms

    Generate form states with missing profile 1, missing profile 2, or both missing.
    Verify `_validate()` returns at least one error and `created_match` is `None`.

    **Validates: Requirements 4.6, 4.7**
    """

    @given(
        invalid_scenario=_invalid_scenario_strategy,
        notes=_optional_text,
    )
    @settings(max_examples=100, deadline=None)
    def test_invalid_form_always_fails_validation(
        self,
        qapp: QApplication,
        invalid_scenario: str,
        notes: str,
    ) -> None:
        """When a required profile selection is missing,
        _validate() SHALL return at least one error and created_match
        SHALL be None.

        Feature: dna-management-from-person-editor, Property 4: Match validation rejects invalid forms
        **Validates: Requirements 4.6, 4.7**
        """
        # Set up ProjectData with profiles for current person and another person.
        # Use two profiles for the current person so the combo is NOT auto-selected
        # and remains enabled (auto-select happens only with exactly one profile).
        person_id = "person_1"
        other_person_id = "person_2"
        company = DnaCompany(id="company_1", name="TestDNA")

        profile_current_1 = DnaProfile(
            id="profile_current_1",
            person_id=person_id,
            company_id=company.id,
            test_type="autosomal",
            kit_name="Kit A",
        )
        profile_current_2 = DnaProfile(
            id="profile_current_2",
            person_id=person_id,
            company_id=company.id,
            test_type="y-dna",
            kit_name="Kit A2",
        )
        profile_other = DnaProfile(
            id="profile_other",
            person_id=other_person_id,
            company_id=company.id,
            test_type="autosomal",
            kit_name="Kit B",
        )

        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_companies=[company],
            dna_profiles=[profile_current_1, profile_current_2, profile_other],
        )

        dialog = DnaMatchDialog(
            project_data=project_data,
            person_id=person_id,
        )

        try:
            # Set optional fields
            dialog._edit_notes.setPlainText(notes)

            # Configure profile selections based on the invalid scenario
            if invalid_scenario == "missing_profile1":
                # Leave profile 1 at placeholder (index 0), select profile 2
                dialog._combo_profile1.setCurrentIndex(0)
                dialog._combo_profile2.setCurrentIndex(1)  # First real other profile
            elif invalid_scenario == "missing_profile2":
                # Select profile 1, leave profile 2 at placeholder (index 0)
                dialog._combo_profile1.setCurrentIndex(1)  # First real current profile
                dialog._combo_profile2.setCurrentIndex(0)
            else:  # "missing_both"
                # Leave both at placeholder (index 0)
                dialog._combo_profile1.setCurrentIndex(0)
                dialog._combo_profile2.setCurrentIndex(0)

            # Validate
            errors = dialog._validate()

            # Must have at least one error
            assert len(errors) >= 1, (
                f"Expected at least one validation error when scenario is "
                f"'{invalid_scenario}', but got no errors."
            )

            # created_match must be None (dialog was never accepted successfully)
            assert dialog.created_match is None, (
                "Expected created_match to be None when form is invalid, "
                f"but got {dialog.created_match!r}."
            )
        finally:
            dialog.close()
            dialog.deleteLater()
