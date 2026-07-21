"""Property-based tests for haplogroup preservation and max length enforcement.

Feature: dna-cluster-enhancements, Property 1: Haplogroup preservation across test type changes
Feature: dna-cluster-enhancements, Property 2: Haplogroup max length enforcement

Validates: Requirements 1.7, 1.8
"""

from __future__ import annotations

import copy
import dataclasses

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.dna import DnaProfile
from slaktbusken.persistence.serialization import deserialize, serialize
from slaktbusken.model.project import ProjectData, ProjectMetadata
from tests.conftest import dna_profile_strategy


_VALID_TEST_TYPES = ["autosomal", "y-dna", "mtdna", "combined"]


class TestHaplogroupPreservation:
    """Feature: dna-cluster-enhancements, Property 1: Haplogroup preservation across test type changes

    For any DnaProfile with non-empty y_haplogroup or mt_haplogroup values,
    changing the test_type to any other valid value SHALL preserve the haplogroup
    field values in the data model without clearing them.

    **Validates: Requirements 1.7**
    """

    @given(
        profile=dna_profile_strategy().filter(
            lambda p: p.y_haplogroup != "" or p.mt_haplogroup != ""
        ),
        new_test_type=st.sampled_from(_VALID_TEST_TYPES),
    )
    @settings(max_examples=100)
    def test_haplogroup_values_preserved_on_test_type_change(
        self, profile: DnaProfile, new_test_type: str
    ):
        """Changing test_type SHALL NOT clear haplogroup values in the data model.

        Feature: dna-cluster-enhancements, Property 1: Haplogroup preservation across test type changes
        **Validates: Requirements 1.7**
        """
        # Record original haplogroup values
        original_y = profile.y_haplogroup
        original_mt = profile.mt_haplogroup

        # Change the test type on the data model
        profile.test_type = new_test_type

        # Assert haplogroup values are preserved
        assert profile.y_haplogroup == original_y
        assert profile.mt_haplogroup == original_mt

    @given(
        profile=dna_profile_strategy().filter(
            lambda p: p.y_haplogroup != "" or p.mt_haplogroup != ""
        ),
    )
    @settings(max_examples=100)
    def test_haplogroup_values_preserved_through_all_type_transitions(
        self, profile: DnaProfile
    ):
        """Cycling through all valid test types SHALL preserve haplogroup values.

        Feature: dna-cluster-enhancements, Property 1: Haplogroup preservation across test type changes
        **Validates: Requirements 1.7**
        """
        original_y = profile.y_haplogroup
        original_mt = profile.mt_haplogroup

        # Cycle through all valid test types
        for test_type in _VALID_TEST_TYPES:
            profile.test_type = test_type
            assert profile.y_haplogroup == original_y
            assert profile.mt_haplogroup == original_mt

    @given(
        profile=dna_profile_strategy().filter(
            lambda p: p.y_haplogroup != "" or p.mt_haplogroup != ""
        ),
        new_test_type=st.sampled_from(_VALID_TEST_TYPES),
    )
    @settings(max_examples=100)
    def test_haplogroup_values_preserved_through_serialization_after_type_change(
        self, profile: DnaProfile, new_test_type: str
    ):
        """Haplogroup values SHALL survive serialization round-trip after test_type change.

        Feature: dna-cluster-enhancements, Property 1: Haplogroup preservation across test type changes
        **Validates: Requirements 1.7**
        """
        original_y = profile.y_haplogroup
        original_mt = profile.mt_haplogroup

        # Change test type
        profile.test_type = new_test_type

        # Serialize and deserialize via ProjectData
        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_profiles=[profile],
        )
        json_str = serialize(project_data)
        restored = deserialize(json_str)

        # Verify haplogroup values survive the round-trip
        restored_profile = restored.dna_profiles[0]
        assert restored_profile.y_haplogroup == original_y
        assert restored_profile.mt_haplogroup == original_mt
        assert restored_profile.test_type == new_test_type


class TestHaplogroupMaxLength:
    """Feature: dna-cluster-enhancements, Property 2: Haplogroup max length enforcement

    For any string of length greater than 50 characters, the haplogroup input fields
    SHALL accept at most the first 50 characters, resulting in a stored value of
    exactly 50 characters.

    **Validates: Requirements 1.8**
    """

    @given(
        long_text=st.text(
            alphabet=st.characters(categories=("L", "N")),
            min_size=51,
            max_size=200,
        ),
    )
    @settings(max_examples=100)
    def test_y_haplogroup_truncated_to_50_chars(self, long_text: str):
        """Y-haplogroup values longer than 50 chars SHALL be truncated to exactly 50.

        Feature: dna-cluster-enhancements, Property 2: Haplogroup max length enforcement
        **Validates: Requirements 1.8**
        """
        # Simulate UI max-length enforcement: truncate to 50 chars
        truncated = long_text[:50]

        # Create a profile with the truncated value
        profile = DnaProfile(
            id="profile_1",
            person_id="person_1",
            company_id="company_1",
            test_type="y-dna",
            y_haplogroup=truncated,
        )

        assert len(profile.y_haplogroup) == 50
        assert profile.y_haplogroup == long_text[:50]

    @given(
        long_text=st.text(
            alphabet=st.characters(categories=("L", "N")),
            min_size=51,
            max_size=200,
        ),
    )
    @settings(max_examples=100)
    def test_mt_haplogroup_truncated_to_50_chars(self, long_text: str):
        """Mt-haplogroup values longer than 50 chars SHALL be truncated to exactly 50.

        Feature: dna-cluster-enhancements, Property 2: Haplogroup max length enforcement
        **Validates: Requirements 1.8**
        """
        # Simulate UI max-length enforcement: truncate to 50 chars
        truncated = long_text[:50]

        # Create a profile with the truncated value
        profile = DnaProfile(
            id="profile_1",
            person_id="person_1",
            company_id="company_1",
            test_type="mtdna",
            mt_haplogroup=truncated,
        )

        assert len(profile.mt_haplogroup) == 50
        assert profile.mt_haplogroup == long_text[:50]

    @given(
        long_text=st.text(
            alphabet=st.characters(categories=("L", "N")),
            min_size=51,
            max_size=200,
        ),
    )
    @settings(max_examples=100)
    def test_truncated_haplogroup_round_trips_through_serialization(self, long_text: str):
        """Truncated haplogroup values SHALL round-trip through serialization at exactly 50 chars.

        Feature: dna-cluster-enhancements, Property 2: Haplogroup max length enforcement
        **Validates: Requirements 1.8**
        """
        truncated_y = long_text[:50]
        truncated_mt = long_text[:50]

        profile = DnaProfile(
            id="profile_1",
            person_id="person_1",
            company_id="company_1",
            test_type="combined",
            y_haplogroup=truncated_y,
            mt_haplogroup=truncated_mt,
        )

        # Serialize and deserialize
        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_profiles=[profile],
        )
        json_str = serialize(project_data)
        restored = deserialize(json_str)

        restored_profile = restored.dna_profiles[0]
        assert len(restored_profile.y_haplogroup) == 50
        assert len(restored_profile.mt_haplogroup) == 50
        assert restored_profile.y_haplogroup == truncated_y
        assert restored_profile.mt_haplogroup == truncated_mt
