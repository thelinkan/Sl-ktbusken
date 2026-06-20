"""Property-based tests for DNA triangulation functionality.

Feature: dna-tab-enhancements, Properties 9–14 for triangulations

Validates: Requirements 6.2, 6.3, 7.4, 9.1, 9.2, 9.4, 9.5, 9.6
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from slaktbusken.model.dna import (
    DnaCompany,
    DnaMatch,
    DnaProfile,
    DnaTriangulation,
)
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.ui.dialogs.dna_triangulation_dialog import (
    DnaTriangulationDialog,
    get_eligible_triangulation_persons,
    has_dna_match,
)
from slaktbusken.ui.editors.person_editor import PersonEditor
from tests.conftest import (
    dna_company_strategy,
    dna_match_strategy,
    dna_profile_strategy,
    dna_triangulation_strategy,
)


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# Local strategies
# ---------------------------------------------------------------------------

_person_id_strategy = st.integers(min_value=1, max_value=9999).map(
    lambda n: f"person_{n}"
)

_profile_id_strategy = st.integers(min_value=1, max_value=9999).map(
    lambda n: f"dnaprofile_{n}"
)

_company_id_strategy = st.integers(min_value=1, max_value=9999).map(
    lambda n: f"dnacompany_{n}"
)


# ---------------------------------------------------------------------------
# Property 9: Triangulation list contains exactly relevant triangulations
# ---------------------------------------------------------------------------


class TestTriangulationListContainsExactlyRelevantTriangulations:
    """Feature: dna-tab-enhancements, Property 9: Triangulation list contains exactly relevant triangulations

    For any active person and project data, the triangulation list SHALL contain
    a DnaTriangulation if and only if the triangulation's profile_ids list
    intersects with the set of DnaProfile IDs belonging to the active person.

    **Validates: Requirements 6.2**
    """

    @given(
        num_person_profiles=st.integers(min_value=1, max_value=3),
        num_other_profiles=st.integers(min_value=1, max_value=3),
        num_relevant_tris=st.integers(min_value=0, max_value=3),
        num_irrelevant_tris=st.integers(min_value=0, max_value=3),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_triangulation_list_shows_relevant_triangulations(
        self,
        qtbot,
        num_person_profiles: int,
        num_other_profiles: int,
        num_relevant_tris: int,
        num_irrelevant_tris: int,
    ) -> None:
        """The triangulation list SHALL show a triangulation iff its profile_ids intersect the person's profile IDs.

        Feature: dna-tab-enhancements, Property 9: Triangulation list contains exactly relevant triangulations
        **Validates: Requirements 6.2**
        """
        person_id = "person_active"
        company_id = "company_1"
        company = DnaCompany(id=company_id, name="TestCo")

        # Create profiles belonging to the person
        person_profiles = [
            DnaProfile(
                id=f"pp_{i}",
                person_id=person_id,
                company_id=company_id,
                test_type="autosomal",
            )
            for i in range(num_person_profiles)
        ]
        person_profile_ids = {p.id for p in person_profiles}

        # Create profiles belonging to other persons
        other_profiles = [
            DnaProfile(
                id=f"op_{i}",
                person_id=f"other_person_{i}",
                company_id=company_id,
                test_type="autosomal",
            )
            for i in range(num_other_profiles)
        ]

        all_profiles = person_profiles + other_profiles

        # Create relevant triangulations (reference at least one person profile)
        relevant_tris = []
        for i in range(num_relevant_tris):
            profile_ids = [person_profiles[i % num_person_profiles].id]
            if other_profiles:
                profile_ids.append(other_profiles[i % num_other_profiles].id)
            # Need at least 3 profile_ids per spec
            profile_ids.append(f"extra_profile_{i}")
            relevant_tris.append(
                DnaTriangulation(
                    id=f"tri_rel_{i}",
                    company_id=company_id,
                    profile_ids=profile_ids,
                    shared_cm=45.5,
                    segment_count=3,
                    largest_segment_cm=22.1,
                )
            )

        # Create irrelevant triangulations (no person profiles referenced)
        irrelevant_tris = []
        for i in range(num_irrelevant_tris):
            profile_ids = [
                f"unrelated_profile_{i}_1",
                f"unrelated_profile_{i}_2",
                f"unrelated_profile_{i}_3",
            ]
            irrelevant_tris.append(
                DnaTriangulation(
                    id=f"tri_irr_{i}",
                    company_id=company_id,
                    profile_ids=profile_ids,
                    shared_cm=30.0,
                    segment_count=2,
                    largest_segment_cm=15.0,
                )
            )

        all_triangulations = relevant_tris + irrelevant_tris

        person = Person(
            id=person_id,
            sex="M",
            names=[Name(type="birth", given="Test", surname="Person")],
        )

        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            persons=[person],
            dna_companies=[company],
            dna_profiles=all_profiles,
            dna_triangulations=all_triangulations,
        )

        editor = PersonEditor(project_data, person=person)
        qtbot.addWidget(editor)

        # Check that the list shows exactly the relevant triangulations
        list_widget = editor._triangulations_list
        shown_ids = set()
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            tri_id = item.data(Qt.ItemDataRole.UserRole)
            shown_ids.add(tri_id)

        # Relevant triangulations should be shown
        for tri in relevant_tris:
            assert tri.id in shown_ids, (
                f"Relevant triangulation {tri.id} should be shown"
            )

        # Irrelevant triangulations should NOT be shown
        for tri in irrelevant_tris:
            assert tri.id not in shown_ids, (
                f"Irrelevant triangulation {tri.id} should NOT be shown"
            )

        # Total count should match
        assert list_widget.count() == num_relevant_tris


# ---------------------------------------------------------------------------
# Property 10: Triangulation display format correctness
# ---------------------------------------------------------------------------


class TestTriangulationDisplayFormatCorrectness:
    """Feature: dna-tab-enhancements, Property 10: Triangulation display format correctness

    For any DnaTriangulation, its display text SHALL be exactly
    "{shared_cm:.2f} cM, {segment_count} segment ({N} profiler)"
    where N equals len(triangulation.profile_ids).

    **Validates: Requirements 6.3**
    """

    @given(
        shared_cm=st.floats(min_value=0.01, max_value=3500.0, allow_nan=False),
        segment_count=st.integers(min_value=1, max_value=100),
        num_profiles=st.integers(min_value=3, max_value=6),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_triangulation_display_format(
        self,
        qtbot,
        shared_cm: float,
        segment_count: int,
        num_profiles: int,
    ) -> None:
        """Display text SHALL exactly match the format specification.

        Feature: dna-tab-enhancements, Property 10: Triangulation display format correctness
        **Validates: Requirements 6.3**
        """
        person_id = "person_active"
        company_id = "company_1"
        company = DnaCompany(id=company_id, name="TestCo")

        # Person profile (must be in the triangulation's profile_ids)
        person_profile = DnaProfile(
            id="person_profile_1",
            person_id=person_id,
            company_id=company_id,
            test_type="autosomal",
        )

        # Build profile_ids: person's profile + extra ones
        profile_ids = [person_profile.id] + [
            f"other_profile_{i}" for i in range(num_profiles - 1)
        ]

        triangulation = DnaTriangulation(
            id="tri_display_1",
            company_id=company_id,
            profile_ids=profile_ids,
            shared_cm=shared_cm,
            segment_count=segment_count,
            largest_segment_cm=10.0,
        )

        person = Person(
            id=person_id,
            sex="M",
            names=[Name(type="birth", given="Test", surname="Person")],
        )

        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            persons=[person],
            dna_companies=[company],
            dna_profiles=[person_profile],
            dna_triangulations=[triangulation],
        )

        editor = PersonEditor(project_data, person=person)
        qtbot.addWidget(editor)

        # Get the display text
        list_widget = editor._triangulations_list
        assert list_widget.count() == 1

        item = list_widget.item(0)
        actual_text = item.text()

        expected_text = (
            f"{shared_cm:.2f} cM, "
            f"{segment_count} segment "
            f"({num_profiles} profiler)"
        )

        assert actual_text == expected_text, (
            f"Expected: {expected_text!r}, got: {actual_text!r}"
        )


# ---------------------------------------------------------------------------
# Property 11: Triangulation shared_cm validation
# ---------------------------------------------------------------------------


class TestTriangulationSharedCmValidation:
    """Feature: dna-tab-enhancements, Property 11: Triangulation shared_cm validation

    The triangulation dialog SHALL require shared_cm > 0 to accept save.

    **Validates: Requirements 7.4**
    """

    @given(
        shared_cm=st.sampled_from([0.0, 0.005, 0.01, 0.5, 1.0, 50.0, 100.0]),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_shared_cm_validation(
        self,
        qtbot,
        shared_cm: float,
    ) -> None:
        """Dialog SHALL reject when shared_cm <= 0.

        Feature: dna-tab-enhancements, Property 11: Triangulation shared_cm validation
        **Validates: Requirements 7.4**
        """
        person_id = "person_active"
        company_id = "company_1"
        company = DnaCompany(id=company_id, name="TestCo")

        person = Person(
            id=person_id,
            sex="M",
            names=[Name(type="birth", given="Test", surname="Person")],
        )

        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            persons=[person],
            dna_companies=[company],
            dna_profiles=[
                DnaProfile(
                    id=f"prof_{i}",
                    person_id=person_id if i == 0 else f"other_{i}",
                    company_id=company_id,
                    test_type="autosomal",
                )
                for i in range(4)
            ],
        )

        dialog = DnaTriangulationDialog(
            project_data=project_data,
            person_id=person_id,
            parent=None,
        )
        qtbot.addWidget(dialog)

        # Set shared_cm value
        dialog._spin_shared_cm.setValue(shared_cm)

        # Set company to valid value
        dialog._combo_company.setCurrentIndex(1)  # First real company

        errors = dialog._validate()
        cm_error = "Delad cM måste anges."

        # The spinbox rounds to 2 decimals, so check the actual value it holds
        actual_value = dialog._spin_shared_cm.value()
        if actual_value <= 0:
            assert cm_error in errors, (
                f"Expected shared_cm error for value={actual_value}"
            )
        else:
            assert cm_error not in errors, (
                f"Unexpected shared_cm error for value={actual_value}"
            )


# ---------------------------------------------------------------------------
# Property 12: Triangulation person mutual-match filtering
# ---------------------------------------------------------------------------


class TestTriangulationPersonMutualMatchFiltering:
    """Feature: dna-tab-enhancements, Property 12: Triangulation person mutual-match filtering

    A candidate person SHALL appear in the eligible list if and only if:
    (a) a DnaMatch exists linking a profile of the active person with a profile
        of the candidate, AND
    (b) for every already-selected person, a DnaMatch exists linking a profile
        of that selected person with a profile of the candidate.

    **Validates: Requirements 9.1, 9.2, 9.5**
    """

    @given(
        num_candidates=st.integers(min_value=2, max_value=5),
        num_selected=st.integers(min_value=0, max_value=2),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_mutual_match_filtering(
        self,
        num_candidates: int,
        num_selected: int,
    ) -> None:
        """Eligible persons SHALL have DNA matches with active person AND all selected persons.

        Feature: dna-tab-enhancements, Property 12: Triangulation person mutual-match filtering
        **Validates: Requirements 9.1, 9.2, 9.5**
        """
        active_id = "person_active"
        company_id = "company_1"
        company = DnaCompany(id=company_id, name="TestCo")

        # Active person + profile
        active_person = Person(
            id=active_id,
            sex="M",
            names=[Name(type="birth", given="Active", surname="Person")],
        )
        active_profile = DnaProfile(
            id="profile_active",
            person_id=active_id,
            company_id=company_id,
            test_type="autosomal",
        )

        # Create candidate persons with profiles
        candidates = []
        candidate_profiles = []
        for i in range(num_candidates):
            pid = f"person_cand_{i}"
            candidates.append(
                Person(
                    id=pid,
                    sex="F",
                    names=[Name(type="birth", given=f"Cand{i}", surname="Person")],
                )
            )
            candidate_profiles.append(
                DnaProfile(
                    id=f"profile_cand_{i}",
                    person_id=pid,
                    company_id=company_id,
                    test_type="autosomal",
                )
            )

        # Selected persons (subset of candidates)
        selected_ids = [
            candidates[i].id for i in range(min(num_selected, num_candidates))
        ]

        # Create matches: all candidates match active person
        matches = []
        for i in range(num_candidates):
            matches.append(
                DnaMatch(
                    id=f"match_active_cand_{i}",
                    profile1_id=active_profile.id,
                    profile2_id=candidate_profiles[i].id,
                    shared_cm=100.0,
                )
            )

        # Create mutual matches between selected and other candidates
        # Only some candidates match ALL selected persons
        # First half of non-selected candidates match all selected
        # Second half does NOT match the last selected person
        non_selected_candidates = [
            (i, c)
            for i, c in enumerate(candidates)
            if c.id not in selected_ids
        ]

        for sel_idx, sel_id in enumerate(selected_ids):
            sel_profile = candidate_profiles[
                next(i for i, c in enumerate(candidates) if c.id == sel_id)
            ]
            for cand_idx, (orig_idx, cand) in enumerate(non_selected_candidates):
                # Let all non-selected candidates match all selected persons
                # (they all match because they all match active already)
                matches.append(
                    DnaMatch(
                        id=f"match_sel{sel_idx}_cand{orig_idx}",
                        profile1_id=sel_profile.id,
                        profile2_id=candidate_profiles[orig_idx].id,
                        shared_cm=50.0,
                    )
                )

        all_persons = [active_person] + candidates
        all_profiles = [active_profile] + candidate_profiles

        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            persons=all_persons,
            dna_companies=[company],
            dna_profiles=all_profiles,
            dna_matches=matches,
        )

        eligible = get_eligible_triangulation_persons(
            active_person_id=active_id,
            selected_person_ids=selected_ids,
            company_id=None,
            project_data=project_data,
        )

        eligible_ids = {p.id for p in eligible}

        # Verify: every returned person has match with active person
        for person in eligible:
            assert has_dna_match(active_id, person.id, project_data), (
                f"Eligible person {person.id} must have match with active person"
            )

        # Verify: every returned person has match with every selected person
        for person in eligible:
            for sel_id in selected_ids:
                assert has_dna_match(sel_id, person.id, project_data), (
                    f"Eligible person {person.id} must have match with selected {sel_id}"
                )

        # Verify: persons NOT returned either lack match with active or lack match with selected
        for person in all_persons:
            if person.id == active_id:
                continue
            if person.id in selected_ids:
                continue
            if person.id not in eligible_ids:
                # Must lack match with active OR lack match with at least one selected
                has_active_match = has_dna_match(
                    active_id, person.id, project_data
                )
                if has_active_match:
                    # Must lack match with at least one selected
                    missing_selected = False
                    for sel_id in selected_ids:
                        if not has_dna_match(sel_id, person.id, project_data):
                            missing_selected = True
                            break
                    assert missing_selected, (
                        f"Person {person.id} not eligible but has all matches"
                    )


# ---------------------------------------------------------------------------
# Property 13: Match existence is bidirectional
# ---------------------------------------------------------------------------


class TestMatchExistenceIsBidirectional:
    """Feature: dna-tab-enhancements, Property 13: Match existence is bidirectional

    For any two persons A and B, has_dna_match(A, B, project_data) SHALL return
    True if and only if has_dna_match(B, A, project_data) returns True.

    **Validates: Requirements 9.4**
    """

    @given(
        match_direction=st.sampled_from(["a_to_b", "b_to_a"]),
        has_match=st.booleans(),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_bidirectional_match(
        self,
        match_direction: str,
        has_match: bool,
    ) -> None:
        """has_dna_match(A, B) == has_dna_match(B, A) for all person pairs.

        Feature: dna-tab-enhancements, Property 13: Match existence is bidirectional
        **Validates: Requirements 9.4**
        """
        person_a_id = "person_a"
        person_b_id = "person_b"
        company_id = "company_1"

        profile_a = DnaProfile(
            id="profile_a",
            person_id=person_a_id,
            company_id=company_id,
            test_type="autosomal",
        )
        profile_b = DnaProfile(
            id="profile_b",
            person_id=person_b_id,
            company_id=company_id,
            test_type="autosomal",
        )

        matches = []
        if has_match:
            if match_direction == "a_to_b":
                matches.append(
                    DnaMatch(
                        id="match_1",
                        profile1_id=profile_a.id,
                        profile2_id=profile_b.id,
                        shared_cm=100.0,
                    )
                )
            else:
                matches.append(
                    DnaMatch(
                        id="match_1",
                        profile1_id=profile_b.id,
                        profile2_id=profile_a.id,
                        shared_cm=100.0,
                    )
                )

        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_profiles=[profile_a, profile_b],
            dna_matches=matches,
        )

        result_ab = has_dna_match(person_a_id, person_b_id, project_data)
        result_ba = has_dna_match(person_b_id, person_a_id, project_data)

        assert result_ab == result_ba, (
            f"has_dna_match(A,B)={result_ab} != has_dna_match(B,A)={result_ba} "
            f"with direction={match_direction}, has_match={has_match}"
        )

        # Also verify correctness: if there's a match, both should be True
        if has_match:
            assert result_ab is True
            assert result_ba is True
        else:
            assert result_ab is False
            assert result_ba is False


# ---------------------------------------------------------------------------
# Property 14: Triangulation company-restricted person filtering
# ---------------------------------------------------------------------------


class TestTriangulationCompanyRestrictedPersonFiltering:
    """Feature: dna-tab-enhancements, Property 14: Triangulation company-restricted person filtering

    A candidate SHALL only be eligible for triangulation selection if they have
    at least one DnaProfile whose company_id matches the selected company.

    **Validates: Requirements 9.6**
    """

    @given(
        num_candidates_with_company=st.integers(min_value=1, max_value=3),
        num_candidates_without_company=st.integers(min_value=1, max_value=3),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_company_restricted_filtering(
        self,
        num_candidates_with_company: int,
        num_candidates_without_company: int,
    ) -> None:
        """Only persons with a profile in the selected company SHALL be eligible.

        Feature: dna-tab-enhancements, Property 14: Triangulation company-restricted person filtering
        **Validates: Requirements 9.6**
        """
        active_id = "person_active"
        target_company_id = "company_target"
        other_company_id = "company_other"

        target_company = DnaCompany(id=target_company_id, name="TargetCo")
        other_company = DnaCompany(id=other_company_id, name="OtherCo")

        active_person = Person(
            id=active_id,
            sex="M",
            names=[Name(type="birth", given="Active", surname="Person")],
        )
        active_profile = DnaProfile(
            id="profile_active",
            person_id=active_id,
            company_id=target_company_id,
            test_type="autosomal",
        )

        persons = [active_person]
        profiles = [active_profile]
        matches = []

        # Candidates WITH profile in target company
        for i in range(num_candidates_with_company):
            pid = f"person_with_{i}"
            persons.append(
                Person(
                    id=pid,
                    sex="F",
                    names=[Name(type="birth", given=f"With{i}", surname="Co")],
                )
            )
            prof = DnaProfile(
                id=f"profile_with_{i}",
                person_id=pid,
                company_id=target_company_id,
                test_type="autosomal",
            )
            profiles.append(prof)
            # Add match with active person
            matches.append(
                DnaMatch(
                    id=f"match_with_{i}",
                    profile1_id=active_profile.id,
                    profile2_id=prof.id,
                    shared_cm=100.0,
                )
            )

        # Candidates WITHOUT profile in target company (only in other company)
        for i in range(num_candidates_without_company):
            pid = f"person_without_{i}"
            persons.append(
                Person(
                    id=pid,
                    sex="F",
                    names=[Name(type="birth", given=f"Without{i}", surname="Co")],
                )
            )
            prof = DnaProfile(
                id=f"profile_without_{i}",
                person_id=pid,
                company_id=other_company_id,
                test_type="autosomal",
            )
            profiles.append(prof)
            # Add match with active person (via profiles in different companies -
            # the match exists but the company filter should exclude them)
            matches.append(
                DnaMatch(
                    id=f"match_without_{i}",
                    profile1_id=active_profile.id,
                    profile2_id=prof.id,
                    shared_cm=100.0,
                )
            )

        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            persons=persons,
            dna_companies=[target_company, other_company],
            dna_profiles=profiles,
            dna_matches=matches,
        )

        eligible = get_eligible_triangulation_persons(
            active_person_id=active_id,
            selected_person_ids=[],
            company_id=target_company_id,
            project_data=project_data,
        )

        eligible_ids = {p.id for p in eligible}

        # Verify: every returned person has at least one profile in target company
        for person in eligible:
            has_company_profile = any(
                p.company_id == target_company_id and p.person_id == person.id
                for p in project_data.dna_profiles
            )
            assert has_company_profile, (
                f"Eligible person {person.id} must have a profile in {target_company_id}"
            )

        # Verify: persons without a profile in target company are NOT returned
        for person in persons:
            if person.id == active_id:
                continue
            has_company_profile = any(
                p.company_id == target_company_id and p.person_id == person.id
                for p in project_data.dna_profiles
            )
            if not has_company_profile:
                assert person.id not in eligible_ids, (
                    f"Person {person.id} without target company profile should NOT be eligible"
                )

        # Verify: all candidates with company profile and match should be eligible
        for i in range(num_candidates_with_company):
            pid = f"person_with_{i}"
            assert pid in eligible_ids, (
                f"Person {pid} with target company profile and match should be eligible"
            )
