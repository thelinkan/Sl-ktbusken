"""Property tests for AppSettingsService (Properties 7, 8).

Feature: ui-enhancements, Property 7: Recent projects list invariants
Feature: ui-enhancements, Property 8: AppSettings serialization round-trip

**Validates: Requirements 5.1, 5.6, 5.2**
"""

from __future__ import annotations

import os.path
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.persistence.app_settings_io import AppSettings, AppSettingsService, ColumnVisibility


class TestPropertyRecentProjectsInvariants:
    """Property 7: Recent projects list invariants.

    Feature: ui-enhancements, Property 7: Recent projects list invariants

    For any sequence of add_recent_project(path) calls with arbitrary path
    strings, the resulting recent projects list satisfies:
    - The most recently added path is at index 0
    - No duplicate paths exist in the list
    - The list length never exceeds 10
    """

    @given(
        paths=st.lists(
            st.text(min_size=1, max_size=100), min_size=1, max_size=20
        )
    )
    @settings(max_examples=100)
    def test_mru_at_index_zero_no_duplicates_length_bounded(
        self, paths: list[str]
    ) -> None:
        """For any sequence of add_recent_project calls, MRU is at index 0,
        no duplicates exist, and length <= 10.

        Feature: ui-enhancements, Property 7: Recent projects list invariants
        """
        import os.path

        with tempfile.TemporaryDirectory() as tmp_dir:
            svc = AppSettingsService()
            svc.SETTINGS_PATH = Path(tmp_dir) / ".slaktbusken" / "app_settings.json"

            for path in paths:
                svc.add_recent_project(path)

            projects = svc.get_recent_projects()

            # Most recently added path is at index 0 (normalized)
            assert projects[0] == os.path.normpath(paths[-1])

            # No duplicates
            assert len(projects) == len(set(projects))

            # Length never exceeds 10
            assert len(projects) <= 10


class TestPropertyAppSettingsRoundTrip:
    """Property 8: AppSettings serialization round-trip.

    Feature: ui-enhancements, Property 8: AppSettings serialization round-trip

    For any valid AppSettings instance (with a list of 0-10 file path strings
    and an optional default project path), serializing to JSON and then
    deserializing produces an equivalent AppSettings instance.
    """

    @given(
        recent_projects=st.lists(
            st.text(min_size=1, max_size=100), min_size=0, max_size=10, unique=True
        ),
        default_project_path=st.one_of(
            st.none(), st.text(min_size=1, max_size=100)
        ),
        cv_titel=st.booleans(),
        cv_yrke=st.booleans(),
        cv_kluster=st.booleans(),
        cv_dna_company=st.booleans(),
    )
    @settings(max_examples=100)
    def test_serialize_deserialize_round_trip(
        self,
        recent_projects: list[str],
        default_project_path: str | None,
        cv_titel: bool,
        cv_yrke: bool,
        cv_kluster: bool,
        cv_dna_company: bool,
    ) -> None:
        """For any valid AppSettings, JSON round-trip produces equivalent instance.

        Feature: ui-enhancements, Property 8: AppSettings serialization round-trip
        """
        original = AppSettings(
            recent_projects=recent_projects,
            default_project_path=default_project_path,
            column_visibility=ColumnVisibility(
                titel=cv_titel,
                yrke=cv_yrke,
                kluster=cv_kluster,
                dna_company=cv_dna_company,
            ),
        )

        svc = AppSettingsService()

        # Serialize then deserialize
        serialized = svc._serialize(original)
        deserialized = svc._deserialize(serialized)

        assert deserialized.recent_projects == [
            os.path.normpath(p) for p in original.recent_projects
        ]
        assert deserialized.default_project_path == original.default_project_path
        assert deserialized.column_visibility == original.column_visibility
