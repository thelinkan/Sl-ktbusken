"""Property-based tests for DNA match display formatting and filtering.

Feature: dna-match-list-enhancement

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 2.3, 2.4, 2.5, 2.6
"""

from __future__ import annotations

import re

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from slaktbusken.model.dna import DnaMatch, DnaProfile
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.ui.dna_match_display import (
    format_match_entry,
    matches_filter,
    resolve_person_display_name,
)
from slaktbusken.ui.editors.dna_editor import DnaEditor
from slaktbusken.ui.editors.dna_editor import DnaEditor
from tests.conftest import dna_match_strategy, dna_profile_strategy, person_strategy


# ---------------------------------------------------------------------------
# Custom strategies for referential integrity
# ---------------------------------------------------------------------------

_NAME_TYPES = ["birth", "married", "adopted", "other"]
_SEX_VALUES = ["M", "F", "X", "U"]


@st.composite
def _empty_name_person_strategy(draw: DrawFn) -> Person:
    """Generate a Person with an empty first name entry (both given and surname empty)."""
    person_id = draw(st.integers(min_value=1, max_value=9999).map(lambda n: f"person_{n}"))
    sex = draw(st.sampled_from(_SEX_VALUES))
    # First name has empty given and surname
    empty_name = Name(type="birth", given="", surname="")
    return Person(id=person_id, sex=sex, names=[empty_name])


@st.composite
def _person_with_no_names_strategy(draw: DrawFn) -> Person:
    """Generate a Person with an empty names list."""
    person_id = draw(st.integers(min_value=1, max_value=9999).map(lambda n: f"person_{n}"))
    sex = draw(st.sampled_from(_SEX_VALUES))
    return Person(id=person_id, sex=sex, names=[])


@st.composite
def linked_project_data_strategy(draw: DrawFn) -> tuple[DnaMatch, ProjectData]:
    """Generate a DnaMatch with a ProjectData that has varying levels of linkage.

    Randomly decides for each profile whether to:
    - Include the DnaProfile and linked Person (happy path)
    - Include the DnaProfile but omit the Person (person_id fallback)
    - Include the DnaProfile with a Person that has empty names (okänd fallback)
    - Omit the DnaProfile entirely (profile_id fallback)
    """
    match = draw(dna_match_strategy())

    profiles: list[DnaProfile] = []
    persons: list[Person] = []

    for profile_id in [match.profile1_id, match.profile2_id]:
        scenario = draw(st.sampled_from([
            "full_chain",
            "no_profile",
            "no_person",
            "empty_names",
            "empty_name_fields",
        ]))

        if scenario == "no_profile":
            # Don't add a profile for this ID -> fallback to profile_id
            continue

        # Create a profile with matching ID
        base_profile = draw(dna_profile_strategy())
        profile = DnaProfile(
            id=profile_id,
            person_id=base_profile.person_id,
            company_id=base_profile.company_id,
            test_type=base_profile.test_type,
            kit_name=base_profile.kit_name,
            kit_id=base_profile.kit_id,
        )
        profiles.append(profile)

        if scenario == "no_person":
            # Profile exists but person doesn't -> fallback to person_id
            continue

        if scenario == "empty_names":
            # Person exists but has no names -> "(okänd)"
            person = Person(id=profile.person_id, sex="U", names=[])
            persons.append(person)
        elif scenario == "empty_name_fields":
            # Person exists but first name has empty given+surname -> "(okänd)"
            person = Person(
                id=profile.person_id,
                sex="U",
                names=[Name(type="birth", given="", surname="")],
            )
            persons.append(person)
        else:
            # Full chain - person with valid names
            base_person = draw(person_strategy())
            person = Person(
                id=profile.person_id,
                sex=base_person.sex,
                names=base_person.names,
                profile_media_id=base_person.profile_media_id,
                notes=base_person.notes,
            )
            persons.append(person)

    project_data = ProjectData(
        project=ProjectMetadata(title="Test"),
        dna_profiles=profiles,
        persons=persons,
    )

    return match, project_data


# ---------------------------------------------------------------------------
# Property 1: Name Resolution and Format Correctness
# ---------------------------------------------------------------------------


class TestNameResolutionAndFormatCorrectness:
    """Feature: dna-match-list-enhancement, Property 1: Name Resolution and Format Correctness

    For any DnaMatch with two profile IDs, and for any ProjectData containing
    (or not containing) the referenced DnaProfiles and Persons, the output of
    format_match_entry SHALL:
    - Contain the en-dash separator ' – ' between two resolved names
    - End with ': {shared_cm} cM ({segment_count} segment)' where shared_cm is
      formatted to one decimal place
    - Have Person1 name equal to resolve_person_display_name(match.profile1_id, project_data)
      and Person2 name equal to resolve_person_display_name(match.profile2_id, project_data)

    **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**
    """

    @given(data=linked_project_data_strategy())
    @settings(max_examples=200)
    def test_format_contains_en_dash_separator(
        self,
        data: tuple[DnaMatch, ProjectData],
    ) -> None:
        """format_match_entry output SHALL contain the en-dash separator ' – '.

        Feature: dna-match-list-enhancement, Property 1: Name Resolution and Format Correctness
        **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**
        """
        match, project_data = data
        result = format_match_entry(match, project_data)

        assert " \u2013 " in result, (
            f"Expected en-dash separator ' – ' in output, got: {result!r}"
        )

    @given(data=linked_project_data_strategy())
    @settings(max_examples=200)
    def test_format_ends_with_cm_and_segment(
        self,
        data: tuple[DnaMatch, ProjectData],
    ) -> None:
        """format_match_entry output SHALL end with ': {shared_cm} cM ({segment_count} segment)'.

        Feature: dna-match-list-enhancement, Property 1: Name Resolution and Format Correctness
        **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**
        """
        match, project_data = data
        result = format_match_entry(match, project_data)

        expected_cm = f"{match.shared_cm:.1f}"
        expected_suffix = f": {expected_cm} cM ({match.segment_count} segment)"
        assert result.endswith(expected_suffix), (
            f"Expected output to end with {expected_suffix!r}, got: {result!r}"
        )

    @given(data=linked_project_data_strategy())
    @settings(max_examples=200)
    def test_format_resolved_names_match(
        self,
        data: tuple[DnaMatch, ProjectData],
    ) -> None:
        """format_match_entry output SHALL use the same names as resolve_person_display_name.

        Feature: dna-match-list-enhancement, Property 1: Name Resolution and Format Correctness
        **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**
        """
        match, project_data = data
        result = format_match_entry(match, project_data)

        name1 = resolve_person_display_name(match.profile1_id, project_data)
        name2 = resolve_person_display_name(match.profile2_id, project_data)

        expected_cm = f"{match.shared_cm:.1f}"
        expected = f"{name1} \u2013 {name2}: {expected_cm} cM ({match.segment_count} segment)"
        assert result == expected, (
            f"Expected: {expected!r}\nGot: {result!r}"
        )

    @given(data=linked_project_data_strategy())
    @settings(max_examples=200)
    def test_cm_value_has_one_decimal_place(
        self,
        data: tuple[DnaMatch, ProjectData],
    ) -> None:
        """The shared_cm value SHALL be formatted to exactly one decimal place.

        Feature: dna-match-list-enhancement, Property 1: Name Resolution and Format Correctness
        **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**
        """
        match, project_data = data
        result = format_match_entry(match, project_data)

        # Extract the cM value from the formatted string using regex
        cm_match = re.search(r": (\d+\.\d+) cM", result)
        assert cm_match is not None, (
            f"Could not find cM value pattern in output: {result!r}"
        )
        cm_str = cm_match.group(1)
        # Verify exactly one decimal place
        decimal_part = cm_str.split(".")[1]
        assert len(decimal_part) == 1, (
            f"Expected 1 decimal place in cM value, got {len(decimal_part)}: {cm_str!r}"
        )

    @given(data=linked_project_data_strategy())
    @settings(max_examples=200)
    def test_resolve_person_display_name_fallbacks(
        self,
        data: tuple[DnaMatch, ProjectData],
    ) -> None:
        """resolve_person_display_name SHALL return correct fallbacks:
        - profile_id when no DnaProfile found
        - person_id when no Person found
        - "(okänd)" when names empty or first name fields empty
        - "given surname".strip() when full chain resolves

        Feature: dna-match-list-enhancement, Property 1: Name Resolution and Format Correctness
        **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**
        """
        match, project_data = data

        for profile_id in [match.profile1_id, match.profile2_id]:
            resolved = resolve_person_display_name(profile_id, project_data)

            # Find profile
            profile = None
            for p in project_data.dna_profiles:
                if p.id == profile_id:
                    profile = p
                    break

            if profile is None:
                # Fallback: return profile_id
                assert resolved == profile_id, (
                    f"Expected profile_id fallback {profile_id!r}, got {resolved!r}"
                )
                continue

            # Find person
            person = None
            for ps in project_data.persons:
                if ps.id == profile.person_id:
                    person = ps
                    break

            if person is None:
                # Fallback: return person_id
                assert resolved == profile.person_id, (
                    f"Expected person_id fallback {profile.person_id!r}, got {resolved!r}"
                )
                continue

            # Check names
            if not person.names:
                assert resolved == "(okänd)", (
                    f"Expected '(okänd)' for empty names, got {resolved!r}"
                )
                continue

            first_name = person.names[0]
            display = f"{first_name.given} {first_name.surname}".strip()

            if not display:
                assert resolved == "(okänd)", (
                    f"Expected '(okänd)' for empty name fields, got {resolved!r}"
                )
            else:
                assert resolved == display, (
                    f"Expected display name {display!r}, got {resolved!r}"
                )


# ---------------------------------------------------------------------------
# Additional strategies for filter testing
# ---------------------------------------------------------------------------


@st.composite
def matches_and_project_data_strategy(draw: DrawFn) -> tuple[list[DnaMatch], ProjectData]:
    """Generate a list of DnaMatch entries and a ProjectData with some profiles/persons."""
    matches = draw(st.lists(dna_match_strategy(), min_size=0, max_size=5))

    # Generate some profiles and persons that may or may not match the match profile IDs
    profiles = draw(st.lists(dna_profile_strategy(), min_size=0, max_size=5))
    persons = draw(st.lists(person_strategy(), min_size=0, max_size=5))

    project_data = ProjectData(
        project=ProjectMetadata(title="Test"),
        dna_profiles=profiles,
        persons=persons,
    )

    return matches, project_data


# ---------------------------------------------------------------------------
# Property 2: Filter Correctness
# ---------------------------------------------------------------------------


class TestFilterCorrectness:
    """Feature: dna-match-list-enhancement, Property 2: Filter Correctness

    For any list of DnaMatch entries and for any filter string, the result of
    matches_filter(matches, filter_text, project_data) SHALL contain exactly those
    matches where filter_text.lower() is a substring of either resolved person
    display name. When filter_text is empty, all matches SHALL be returned.

    **Validates: Requirements 2.3, 2.4, 2.5, 2.6**
    """

    @given(
        data=matches_and_project_data_strategy(),
        filter_text=st.text(min_size=0, max_size=20),
    )
    @settings(max_examples=100)
    def test_filter_returns_exactly_matching_subset(
        self,
        data: tuple[list[DnaMatch], ProjectData],
        filter_text: str,
    ) -> None:
        """matches_filter returns exactly those matches where filter_text.lower()
        is a substring of either resolved person display name.

        Feature: dna-match-list-enhancement, Property 2: Filter Correctness
        **Validates: Requirements 2.3, 2.4, 2.5, 2.6**
        """
        matches, project_data = data

        # Compute expected result manually (oracle)
        if not filter_text:
            expected = matches
        else:
            lower_filter = filter_text.lower()
            expected = [
                m
                for m in matches
                if lower_filter
                in resolve_person_display_name(m.profile1_id, project_data).lower()
                or lower_filter
                in resolve_person_display_name(m.profile2_id, project_data).lower()
            ]

        # Call the function under test
        result = matches_filter(matches, filter_text, project_data)

        assert result == expected, (
            f"Filter '{filter_text}' produced incorrect result.\n"
            f"Expected {len(expected)} matches, got {len(result)}."
        )

    @given(data=matches_and_project_data_strategy())
    @settings(max_examples=100)
    def test_empty_filter_returns_all_matches(
        self,
        data: tuple[list[DnaMatch], ProjectData],
    ) -> None:
        """When filter_text is empty, all matches SHALL be returned.

        Feature: dna-match-list-enhancement, Property 2: Filter Correctness
        **Validates: Requirements 2.3, 2.4, 2.5, 2.6**
        """
        matches, project_data = data

        result = matches_filter(matches, "", project_data)

        assert result == matches, (
            f"Empty filter should return all {len(matches)} matches, "
            f"but got {len(result)}."
        )


# ---------------------------------------------------------------------------
# Fixture for QApplication (required for Qt widget tests)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# Property 4: Filter Text Preservation on Refresh
# ---------------------------------------------------------------------------


class TestFilterTextPreservationOnRefresh:
    """Feature: dna-match-list-enhancement, Property 4: Filter Text Preservation on Refresh

    For any filter text currently in the Match_Filter input, when a data-change
    refresh occurs, the Match_Filter text SHALL remain unchanged after the
    refresh completes.

    **Validates: Requirements 3.3**
    """

    @given(
        filter_text=st.text(min_size=0, max_size=50),
        matches=st.lists(dna_match_strategy(), min_size=0, max_size=5),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_filter_text_preserved_after_refresh(
        self, qtbot, filter_text, matches
    ):
        """Filter text SHALL remain unchanged after _refresh_matches_list is called.

        Feature: dna-match-list-enhancement, Property 4: Filter Text Preservation on Refresh
        **Validates: Requirements 3.3**
        """
        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_matches=matches,
        )
        editor = DnaEditor(project_data=project_data, project_path=None)
        qtbot.addWidget(editor)

        # Set the filter text
        editor._ui.match_filter_input.setText(filter_text)

        # Trigger a refresh (simulating data change)
        editor._refresh_matches_list()

        # Assert filter text is preserved
        assert editor._ui.match_filter_input.text() == filter_text


# ---------------------------------------------------------------------------
# Strategies for filter consistency after data change
# ---------------------------------------------------------------------------


@st.composite
def linked_matches_with_filter_strategy(
    draw: DrawFn,
) -> tuple[list[DnaMatch], str, ProjectData]:
    """Generate a list of DnaMatch entries with linked profiles/persons and a filter text.

    Produces matches where some have full resolution chains (profile → person → name)
    so the filter has meaningful data to test against.
    """
    # Generate some persons with real names
    persons = draw(st.lists(person_strategy(), min_size=1, max_size=4))
    # Generate profiles linked to those persons
    profiles: list[DnaProfile] = []
    for person in persons:
        profile = draw(dna_profile_strategy())
        profile = DnaProfile(
            id=profile.id,
            person_id=person.id,
            company_id=profile.company_id,
            test_type=profile.test_type,
            kit_name=profile.kit_name,
            kit_id=profile.kit_id,
        )
        profiles.append(profile)

    # Generate matches that reference the created profiles
    profile_ids = [p.id for p in profiles]
    matches: list[DnaMatch] = []
    num_matches = draw(st.integers(min_value=1, max_value=5))
    for _ in range(num_matches):
        base_match = draw(dna_match_strategy())
        p1_id = draw(st.sampled_from(profile_ids))
        p2_id = draw(st.sampled_from(profile_ids))
        match = DnaMatch(
            id=base_match.id,
            profile1_id=p1_id,
            profile2_id=p2_id,
            shared_cm=base_match.shared_cm,
            shared_percentage=base_match.shared_percentage,
            segment_count=base_match.segment_count,
            largest_segment_cm=base_match.largest_segment_cm,
            match_source=base_match.match_source,
            notes=base_match.notes,
        )
        matches.append(match)

    # Use a substring from one of the person names as filter text (or random text)
    filter_source = draw(st.sampled_from(["from_name", "random"]))
    if filter_source == "from_name" and persons:
        chosen_person = draw(st.sampled_from(persons))
        if chosen_person.names:
            full_name = f"{chosen_person.names[0].given} {chosen_person.names[0].surname}".strip()
            if full_name:
                # Pick a substring of the name
                start = draw(st.integers(min_value=0, max_value=max(0, len(full_name) - 1)))
                end = draw(st.integers(min_value=start + 1, max_value=len(full_name)))
                filter_text = full_name[start:end]
            else:
                filter_text = draw(st.text(min_size=0, max_size=10))
        else:
            filter_text = draw(st.text(min_size=0, max_size=10))
    else:
        filter_text = draw(st.text(min_size=0, max_size=10))

    project_data = ProjectData(
        project=ProjectMetadata(title="Test"),
        dna_profiles=profiles,
        persons=persons,
        dna_matches=matches,
    )

    return matches, filter_text, project_data


# ---------------------------------------------------------------------------
# Property 3: Filter Consistency After Data Change
# ---------------------------------------------------------------------------


class TestFilterConsistencyAfterDataChange:
    """Feature: dna-match-list-enhancement, Property 3: Filter Consistency After Data Change

    For any set of DnaMatch entries, for any active filter text, and for any
    data mutation (add, remove, or modify a match), after the mutation and
    refresh, the displayed list SHALL equal matches_filter(current_matches,
    filter_text, project_data).

    **Validates: Requirements 3.1, 3.2, 3.4, 3.5**
    """

    @given(
        data=linked_matches_with_filter_strategy(),
        new_match=dna_match_strategy(),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_add_match_then_refresh_displays_fresh_filter(
        self,
        qtbot,
        data: tuple[list[DnaMatch], str, ProjectData],
        new_match: DnaMatch,
    ) -> None:
        """After adding a match and refreshing, displayed list matches fresh filter application.

        Feature: dna-match-list-enhancement, Property 3: Filter Consistency After Data Change
        **Validates: Requirements 3.1, 3.2, 3.4, 3.5**
        """
        _initial_matches, filter_text, project_data = data

        # Create editor with initial data
        editor = DnaEditor(project_data=project_data, project_path=None, parent=None)
        qtbot.addWidget(editor)

        # Set filter text
        editor._ui.match_filter_input.setText(filter_text)

        # Add a new match to project data
        # Make the new match reference profiles that exist in our data
        if project_data.dna_profiles:
            profile_ids = [p.id for p in project_data.dna_profiles]
            new_match = DnaMatch(
                id=new_match.id,
                profile1_id=profile_ids[0],
                profile2_id=profile_ids[-1],
                shared_cm=new_match.shared_cm,
                shared_percentage=new_match.shared_percentage,
                segment_count=new_match.segment_count,
                largest_segment_cm=new_match.largest_segment_cm,
                match_source=new_match.match_source,
                notes=new_match.notes,
            )
        project_data.dna_matches.append(new_match)

        # Refresh the list (simulates data change trigger)
        editor._refresh_matches_list()

        # Read displayed item IDs
        displayed_ids = []
        for i in range(editor._ui.matches_list.count()):
            item = editor._ui.matches_list.item(i)
            displayed_ids.append(item.data(Qt.ItemDataRole.UserRole))

        # Compute expected via fresh filter application
        expected_matches = matches_filter(
            project_data.dna_matches, filter_text, project_data
        )
        expected_ids = [m.id for m in expected_matches]

        assert displayed_ids == expected_ids, (
            f"After adding a match with filter '{filter_text}', "
            f"displayed IDs {displayed_ids} != expected IDs {expected_ids}"
        )

    @given(data=linked_matches_with_filter_strategy())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_remove_match_then_refresh_displays_fresh_filter(
        self,
        qtbot,
        data: tuple[list[DnaMatch], str, ProjectData],
    ) -> None:
        """After removing a match and refreshing, displayed list matches fresh filter application.

        Feature: dna-match-list-enhancement, Property 3: Filter Consistency After Data Change
        **Validates: Requirements 3.1, 3.2, 3.4, 3.5**
        """
        _initial_matches, filter_text, project_data = data

        # Create editor with initial data
        editor = DnaEditor(project_data=project_data, project_path=None, parent=None)
        qtbot.addWidget(editor)

        # Set filter text
        editor._ui.match_filter_input.setText(filter_text)

        # Remove a match from project data (if any exist)
        if project_data.dna_matches:
            project_data.dna_matches.pop(0)

        # Refresh the list (simulates data change trigger)
        editor._refresh_matches_list()

        # Read displayed item IDs
        displayed_ids = []
        for i in range(editor._ui.matches_list.count()):
            item = editor._ui.matches_list.item(i)
            displayed_ids.append(item.data(Qt.ItemDataRole.UserRole))

        # Compute expected via fresh filter application
        expected_matches = matches_filter(
            project_data.dna_matches, filter_text, project_data
        )
        expected_ids = [m.id for m in expected_matches]

        assert displayed_ids == expected_ids, (
            f"After removing a match with filter '{filter_text}', "
            f"displayed IDs {displayed_ids} != expected IDs {expected_ids}"
        )
