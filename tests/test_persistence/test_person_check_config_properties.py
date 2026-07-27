# Feature: kontrollera-personer, Property 1: Settings serialization round-trip
"""Property tests for PersonCheckConfig settings persistence round-trip.

Feature: kontrollera-personer, Property 1: Settings serialization round-trip

**Validates: Requirements 4.6, 5.6, 7.2, 10.1, 10.2, 10.4**
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.persistence.settings_io import (
    AgeCheckConfig,
    AgeCheckThreshold,
    LogicCheckConfig,
    PersonCheckConfig,
    ProjectSettings,
    read_settings,
    write_settings,
)


# --- Hypothesis strategies ---

@st.composite
def age_check_threshold_strategy(draw: st.DrawFn) -> AgeCheckThreshold:
    """Generate a random AgeCheckThreshold with valid values."""
    return AgeCheckThreshold(
        enabled=draw(st.booleans()),
        male=draw(st.integers(min_value=0, max_value=999)),
        female=draw(st.integers(min_value=0, max_value=999)),
    )


@st.composite
def age_check_config_strategy(draw: st.DrawFn) -> AgeCheckConfig:
    """Generate a random AgeCheckConfig with valid values."""
    return AgeCheckConfig(
        master_enabled=draw(st.booleans()),
        max_age=draw(age_check_threshold_strategy()),
        max_age_at_baptism=draw(age_check_threshold_strategy()),
        min_age_at_marriage=draw(age_check_threshold_strategy()),
        max_age_at_marriage=draw(age_check_threshold_strategy()),
        max_partner_age_diff=draw(st.integers(min_value=0, max_value=999)),
        max_partner_age_diff_enabled=draw(st.booleans()),
        min_age_at_childbirth=draw(age_check_threshold_strategy()),
        max_age_at_childbirth=draw(age_check_threshold_strategy()),
        min_days_between_births=draw(st.integers(min_value=0, max_value=9999)),
        min_days_between_births_enabled=draw(st.booleans()),
        max_days_death_to_burial=draw(age_check_threshold_strategy()),
    )


@st.composite
def logic_check_config_strategy(draw: st.DrawFn) -> LogicCheckConfig:
    """Generate a random LogicCheckConfig with all boolean fields."""
    return LogicCheckConfig(
        reasonable_dates=draw(st.booleans()),
        no_event_before_birth=draw(st.booleans()),
        burial_not_before_death=draw(st.booleans()),
        only_burial_after_death=draw(st.booleans()),
        no_own_events_after_death=draw(st.booleans()),
        birth_not_after_parent_death=draw(st.booleans()),
        no_event_before_parent_birth=draw(st.booleans()),
        no_incest=draw(st.booleans()),
        must_have_relations=draw(st.booleans()),
        no_ancestor_cycle=draw(st.booleans()),
        media_files_exist=draw(st.booleans()),
        valid_swedish_calendar=draw(st.booleans()),
        connected_to_main_person=draw(st.booleans()),
    )


@st.composite
def person_check_config_strategy(draw: st.DrawFn) -> PersonCheckConfig:
    """Generate a random PersonCheckConfig with valid values."""
    return PersonCheckConfig(
        age_checks=draw(age_check_config_strategy()),
        logic_checks=draw(logic_check_config_strategy()),
    )


class TestPropertySettingsRoundTrip:
    """Property 1: Settings serialization round-trip.

    For any valid PersonCheckConfig instance, serializing to dict and
    deserializing back SHALL produce an equivalent configuration.
    Additionally, for any partial dict missing some keys, deserialization
    SHALL fill missing keys with defaults while preserving existing values.
    """

    @given(config=person_check_config_strategy())
    @settings(max_examples=200)
    def test_full_round_trip(self, config: PersonCheckConfig) -> None:
        """Full round-trip: write settings with random config, read back, assert equality.

        # Feature: kontrollera-personer, Property 1: Settings serialization round-trip
        **Validates: Requirements 4.6, 5.6, 7.2, 10.1, 10.2, 10.4**
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings_path = Path(tmp_dir) / "settings.json"

            # Create ProjectSettings with the generated PersonCheckConfig
            original = ProjectSettings(person_check_config=config)

            # Write to a temp file
            write_settings(original, settings_path)

            # Read back
            loaded = read_settings(settings_path)

            # Compare using dataclasses.asdict for deep equality
            assert asdict(loaded.person_check_config) == asdict(config)

    @given(config=person_check_config_strategy(), draw_data=st.data())
    @settings(max_examples=200)
    def test_partial_dict_deserialization(
        self, config: PersonCheckConfig, draw_data: st.DataObject
    ) -> None:
        """Partial dict: randomly remove keys, verify defaults fill missing, existing preserved.

        # Feature: kontrollera-personer, Property 1: Settings serialization round-trip
        **Validates: Requirements 4.6, 5.6, 7.2, 10.1, 10.2, 10.4**
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings_path = Path(tmp_dir) / "settings.json"

            # Serialize to dict
            full_dict = asdict(config)

            # Randomly remove some keys from nested dicts
            age_checks_dict = full_dict["age_checks"]
            logic_checks_dict = full_dict["logic_checks"]

            # Determine which top-level age_checks keys to remove
            age_keys = list(age_checks_dict.keys())
            keys_to_remove_age = draw_data.draw(
                st.lists(st.sampled_from(age_keys), unique=True),
                label="age_keys_to_remove",
            )

            # Determine which logic_checks keys to remove
            logic_keys = list(logic_checks_dict.keys())
            keys_to_remove_logic = draw_data.draw(
                st.lists(st.sampled_from(logic_keys), unique=True),
                label="logic_keys_to_remove",
            )

            # Remove selected keys
            for key in keys_to_remove_age:
                del age_checks_dict[key]
            for key in keys_to_remove_logic:
                del logic_checks_dict[key]

            # Write partial dict as JSON (wrapped in person_check_config key)
            data = {"person_check_config": full_dict}
            settings_path.write_text(
                json.dumps(data, indent=2) + "\n", encoding="utf-8"
            )

            # Read back
            loaded = read_settings(settings_path)
            loaded_dict = asdict(loaded.person_check_config)

            # Get defaults for comparison
            defaults = PersonCheckConfig()
            defaults_dict = asdict(defaults)

            # Verify: present keys retain their values
            original_full = asdict(config)
            for key in age_checks_dict:
                assert loaded_dict["age_checks"][key] == age_checks_dict[key], (
                    f"age_checks.{key} should retain its value"
                )
            for key in logic_checks_dict:
                assert loaded_dict["logic_checks"][key] == logic_checks_dict[key], (
                    f"logic_checks.{key} should retain its value"
                )

            # Verify: missing keys are filled with defaults
            for key in keys_to_remove_age:
                assert loaded_dict["age_checks"][key] == defaults_dict["age_checks"][key], (
                    f"age_checks.{key} should fall back to default"
                )
            for key in keys_to_remove_logic:
                assert loaded_dict["logic_checks"][key] == defaults_dict["logic_checks"][key], (
                    f"logic_checks.{key} should fall back to default"
                )
