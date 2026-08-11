# Feature: residence-periods, Property 30: The residences migration is idempotent
"""Property-based test for migration idempotence.

Feature: residence-periods, Property 30: The residences migration is idempotent

The 0.1→0.2 migration adds `residences: []` when the key is missing and leaves
existing residences unchanged. Applying the migration twice (migrating 0.1→0.2,
then asserting no change when already at 0.2) is a no-op.

**Validates: Requirements 13.4**
"""

from __future__ import annotations

import copy
import json

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.project import ProjectData
from slaktbusken.persistence.migration import MigrationManager
from slaktbusken.persistence.serialization import serialize
from tests.test_model.residence_strategies import consistent_projects


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestMigrationIdempotenceProperty:
    """Property 30: The residences migration is idempotent.

    For any project data at version 0.1, migrating to 0.2 adds `residences: []`
    when missing and leaves existing residences unchanged; applying the migration
    twice (migrating 0.1→0.2, then asserting no change when already at 0.2) is
    a no-op.

    **Validates: Requirements 13.4**
    """

    @given(
        project=consistent_projects(
            min_residences=0,
            max_residences=5,
            include_many_observations=False,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_migration_idempotence(self, project: ProjectData) -> None:
        """Migrating from 0.1 adds residences when missing and leaves existing
        residences unchanged; a second migration on already-current data is a no-op.

        Feature: residence-periods, Property 30: The residences migration is idempotent

        **Validates: Requirements 13.4**
        """
        # Serialize the project to get a realistic data dict.
        json_str = serialize(project)
        data_dict = json.loads(json_str)

        # --- Scenario A: Data at 0.1 with no residences key ---
        data_no_residences = copy.deepcopy(data_dict)
        data_no_residences.pop("residences", None)
        data_no_residences["version"] = "0.1"
        data_no_residences["format_version"] = "0.1"

        # First migration: should add residences: []
        migrated_once = MigrationManager.migrate(data_no_residences, "0.1")
        assert migrated_once["residences"] == []
        assert migrated_once["format_version"] == "0.2"
        assert migrated_once["version"] == "0.2"

        # Second migration attempt: already at 0.2, should be a no-op
        snapshot_after_first = copy.deepcopy(migrated_once)
        migrated_twice = MigrationManager.migrate(migrated_once, "0.2")
        assert migrated_twice == snapshot_after_first

        # --- Scenario B: Data at 0.1 WITH existing residences ---
        data_with_residences = copy.deepcopy(data_dict)
        data_with_residences["version"] = "0.1"
        data_with_residences["format_version"] = "0.1"
        original_residences = copy.deepcopy(data_with_residences.get("residences", []))

        # First migration: should leave existing residences unchanged
        migrated_b_once = MigrationManager.migrate(data_with_residences, "0.1")
        assert migrated_b_once["residences"] == original_residences
        assert migrated_b_once["format_version"] == "0.2"
        assert migrated_b_once["version"] == "0.2"

        # Second migration: already at 0.2, should be a no-op
        snapshot_b = copy.deepcopy(migrated_b_once)
        migrated_b_twice = MigrationManager.migrate(migrated_b_once, "0.2")
        assert migrated_b_twice == snapshot_b
