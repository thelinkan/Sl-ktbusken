"""Property-based tests for triangulation format display.

# Feature: dna-cluster-enhancements, Property 3: Triangulation format with unresolvable fallback

Validates: Requirements 2.1, 2.2
"""

from __future__ import annotations

import re

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.dna import DnaCompany, DnaProfile, DnaTriangulation
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services.triangulation_format import format_triangulation_entry


# ---------------------------------------------------------------------------
# Strategies for controlled test data generation
# ---------------------------------------------------------------------------

_safe_name = st.text(
    alphabet=st.characters(categories=("L",)),
    min_size=1,
    max_size=20,
)


@st.composite
def triangulation_scenario(draw: DrawFn) -> tuple[DnaTriangulation, ProjectData, list[bool]]:
    """Generate a triangulation with controlled resolvability.

    Returns:
        A tuple of (triangulation, project_data, resolvable_flags) where
        resolvable_flags[i] indicates whether profile_ids[i] should be
        resolvable to a person name.
    """
    # Generate company
    company_id = draw(st.just("company_1"))
    company_name = draw(_safe_name)
    company = DnaCompany(id=company_id, name=company_name)

    # Generate profile count (3-6 profiles for triangulation)
    profile_count = draw(st.integers(min_value=3, max_value=6))

    # For each profile, decide if it's resolvable
    resolvable_flags = draw(
        st.lists(st.booleans(), min_size=profile_count, max_size=profile_count)
    )

    profiles: list[DnaProfile] = []
    persons: list[Person] = []
    profile_ids: list[str] = []

    for i in range(profile_count):
        profile_id = f"profile_{i}"
        profile_ids.append(profile_id)

        if resolvable_flags[i]:
            # Create a resolvable chain: profile → person with name
            person_id = f"person_{i}"
            given_name = draw(_safe_name)
            surname = draw(_safe_name)

            person = Person(
                id=person_id,
                sex="U",
                names=[Name(type="birth", given=given_name, surname=surname)],
            )
            persons.append(person)

            profile = DnaProfile(
                id=profile_id,
                person_id=person_id,
                company_id=company_id,
                test_type="autosomal",
            )
            profiles.append(profile)
        else:
            # Choose a reason for unresolvability
            reason = draw(st.sampled_from(["missing_profile", "missing_person", "empty_names"]))

            if reason == "missing_profile":
                # Don't add profile to project at all
                pass
            elif reason == "missing_person":
                # Profile exists but person_id doesn't point to any person
                profile = DnaProfile(
                    id=profile_id,
                    person_id=f"nonexistent_person_{i}",
                    company_id=company_id,
                    test_type="autosomal",
                )
                profiles.append(profile)
            else:  # empty_names
                # Profile and person exist, but person has empty names list
                person_id = f"person_{i}"
                person = Person(id=person_id, sex="U", names=[])
                persons.append(person)

                profile = DnaProfile(
                    id=profile_id,
                    person_id=person_id,
                    company_id=company_id,
                    test_type="autosomal",
                )
                profiles.append(profile)

    triangulation = DnaTriangulation(
        id="tri_1",
        company_id=company_id,
        profile_ids=profile_ids,
    )

    project_data = ProjectData(
        project=ProjectMetadata(title="Test"),
        persons=persons,
        dna_companies=[company],
        dna_profiles=profiles,
    )

    return triangulation, project_data, resolvable_flags


@st.composite
def triangulation_with_missing_company(draw: DrawFn) -> tuple[DnaTriangulation, ProjectData]:
    """Generate a triangulation where the company cannot be resolved."""
    profile_count = draw(st.integers(min_value=3, max_value=5))
    profile_ids = [f"profile_{i}" for i in range(profile_count)]

    # Create profiles and persons so names are resolvable
    profiles: list[DnaProfile] = []
    persons: list[Person] = []

    for i in range(profile_count):
        person_id = f"person_{i}"
        given_name = draw(_safe_name)
        surname = draw(_safe_name)
        persons.append(Person(
            id=person_id,
            sex="U",
            names=[Name(type="birth", given=given_name, surname=surname)],
        ))
        profiles.append(DnaProfile(
            id=f"profile_{i}",
            person_id=person_id,
            company_id="nonexistent_company",
            test_type="autosomal",
        ))

    triangulation = DnaTriangulation(
        id="tri_1",
        company_id="nonexistent_company",
        profile_ids=profile_ids,
    )

    project_data = ProjectData(
        project=ProjectMetadata(title="Test"),
        persons=persons,
        dna_companies=[],  # No companies!
        dna_profiles=profiles,
    )

    return triangulation, project_data


# ---------------------------------------------------------------------------
# Property 3: Triangulation format with unresolvable fallback
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(scenario=triangulation_scenario())
def test_triangulation_format_structure(
    scenario: tuple[DnaTriangulation, ProjectData, list[bool]],
) -> None:
    """**Validates: Requirements 2.1, 2.2**

    For any DnaTriangulation with a valid company_id and a list of profile_ids,
    format_triangulation_entry produces a string matching the expected pattern.
    """
    triangulation, project_data, resolvable_flags = scenario

    result = format_triangulation_entry(triangulation, project_data)

    # Assertion 1: Result starts with company name
    company = project_data.dna_companies[0]
    assert result.startswith(company.name), (
        f"Expected result to start with company name '{company.name}', got: {result}"
    )

    # Assertion 2: Contains "({n} profiler)" where n = len(profile_ids)
    n = len(triangulation.profile_ids)
    expected_count = f"({n} profiler)"
    assert expected_count in result, (
        f"Expected '{expected_count}' in result, got: {result}"
    )

    # Assertion 3: After ": ", contains comma-separated names that are
    # either "{given} {surname}" or "(okänd)"
    colon_pos = result.index(": ")
    names_part = result[colon_pos + 2:]
    names = [name.strip() for name in names_part.split(",")]

    for name in names:
        is_valid_name = name == "(okänd)" or (
            len(name.split()) >= 2 and name != ""
        )
        assert is_valid_name, (
            f"Name '{name}' is neither a valid person name nor '(okänd)' in: {result}"
        )

    # Assertion 4: Total names in the result equals len(profile_ids)
    assert len(names) == n, (
        f"Expected {n} names, got {len(names)} in: {result}"
    )


@settings(max_examples=200)
@given(scenario=triangulation_scenario())
def test_triangulation_format_fallback_correctness(
    scenario: tuple[DnaTriangulation, ProjectData, list[bool]],
) -> None:
    """**Validates: Requirements 2.1, 2.2**

    Unresolvable profiles produce "(okänd)" and resolvable profiles produce
    actual person names.
    """
    triangulation, project_data, resolvable_flags = scenario

    result = format_triangulation_entry(triangulation, project_data)

    colon_pos = result.index(": ")
    names_part = result[colon_pos + 2:]
    names = [name.strip() for name in names_part.split(",")]

    for i, (name, resolvable) in enumerate(zip(names, resolvable_flags)):
        if resolvable:
            assert name != "(okänd)", (
                f"Profile {i} is resolvable but got '(okänd)' in: {result}"
            )
        else:
            assert name == "(okänd)", (
                f"Profile {i} is unresolvable but got '{name}' instead of '(okänd)' in: {result}"
            )


@settings(max_examples=100)
@given(scenario=triangulation_with_missing_company())
def test_triangulation_format_missing_company(
    scenario: tuple[DnaTriangulation, ProjectData],
) -> None:
    """**Validates: Requirements 2.1, 2.2**

    When the company cannot be resolved, the result uses "(okänt företag)".
    """
    triangulation, project_data = scenario

    result = format_triangulation_entry(triangulation, project_data)

    # Result should start with "(okänt företag)"
    assert result.startswith("(okänt företag)"), (
        f"Expected result to start with '(okänt företag)', got: {result}"
    )

    # Structure should still be correct
    n = len(triangulation.profile_ids)
    expected_count = f"({n} profiler)"
    assert expected_count in result, (
        f"Expected '{expected_count}' in result, got: {result}"
    )
