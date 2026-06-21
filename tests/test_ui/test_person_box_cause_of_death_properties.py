"""Property-based tests for cause of death display and truncation on PersonBoxItem.

Feature: enhanced-name-cards

Validates: Requirements 6.1, 6.2, 6.4
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from PySide6.QtWidgets import QApplication

from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.ui.widgets.person_box import PersonBoxItem, _CAUSE_OF_DEATH_MAX_LEN


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
# Strategies
# ---------------------------------------------------------------------------

# Cause of death strings of varying lengths including edge cases
cause_of_death_strategy = st.one_of(
    st.just(""),                    # empty
    st.just("x"),                   # 1 char
    st.text(min_size=50, max_size=50, alphabet=st.characters(categories=("L", "N", "P", "Z"))),  # exactly 50
    st.text(min_size=51, max_size=51, alphabet=st.characters(categories=("L", "N", "P", "Z"))),  # exactly 51
    st.text(min_size=500, max_size=600, alphabet=st.characters(categories=("L", "N", "P", "Z"))),  # 500+
    st.text(min_size=1, max_size=200, alphabet=st.characters(categories=("L", "N", "P", "Z"))),  # general non-empty
)

# Config toggle for cause_of_death field
config_toggle_strategy = st.booleans()


# ---------------------------------------------------------------------------
# Property 11: Cause of death display and truncation
# ---------------------------------------------------------------------------


class TestCauseOfDeathDisplayAndTruncation:
    """Feature: enhanced-name-cards, Property 11: Cause of death display and truncation

    Generate cause_of_death strings of varying lengths (0, 1, 50, 51, 500+)
    and config toggle states. Verify correct display/hide behavior and
    truncation logic.

    **Validates: Requirements 6.1, 6.2, 6.4**
    """

    _PREFIX = "Dödsorsak: "

    @given(config_enabled=config_toggle_strategy, cause=cause_of_death_strategy)
    @settings(max_examples=100, deadline=None)
    def test_config_disabled_no_cause_of_death_line(
        self, qapp, config_enabled: bool, cause: str
    ) -> None:
        """When config cause_of_death is False, no cause of death line appears.

        Feature: enhanced-name-cards, Property 11: Cause of death display and truncation
        **Validates: Requirements 6.1, 6.2, 6.4**
        """
        if config_enabled:
            # This test only checks the disabled case
            return

        config = PersonBoxConfig(cause_of_death=False)
        display_data = {
            "name": "Test Person",
            "cause_of_death": cause,
        }

        box = PersonBoxItem(
            person_id="p1", display_data=display_data, config=config
        )
        lines = box._lines

        for line in lines:
            assert not line.startswith(self._PREFIX), (
                f"Cause of death line should be absent when config is disabled, "
                f"but found '{line}' in {lines}"
            )

    @given(cause=st.one_of(st.none(), st.just("")))
    @settings(max_examples=100, deadline=None)
    def test_config_enabled_empty_value_no_line(
        self, qapp, cause
    ) -> None:
        """When config is enabled but value is empty/None, no cause of death line appears.

        Feature: enhanced-name-cards, Property 11: Cause of death display and truncation
        **Validates: Requirements 6.1, 6.2, 6.4**
        """
        config = PersonBoxConfig(cause_of_death=True)
        display_data = {
            "name": "Test Person",
            "cause_of_death": cause,
        }

        box = PersonBoxItem(
            person_id="p1", display_data=display_data, config=config
        )
        lines = box._lines

        for line in lines:
            assert not line.startswith(self._PREFIX), (
                f"Cause of death line should be absent when value is "
                f"{cause!r}, but found '{line}' in {lines}"
            )

    @given(
        cause=st.text(
            min_size=1,
            max_size=_CAUSE_OF_DEATH_MAX_LEN,
            alphabet=st.characters(categories=("L", "N", "P", "Z")),
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_config_enabled_short_value_displayed_verbatim(
        self, qapp, cause: str
    ) -> None:
        """When config enabled and value length <= 50, line is displayed verbatim.

        Feature: enhanced-name-cards, Property 11: Cause of death display and truncation
        **Validates: Requirements 6.1, 6.2, 6.4**
        """
        config = PersonBoxConfig(cause_of_death=True)
        display_data = {
            "name": "Test Person",
            "cause_of_death": cause,
        }

        box = PersonBoxItem(
            person_id="p1", display_data=display_data, config=config
        )
        lines = box._lines

        expected_line = f"{self._PREFIX}{cause}"
        assert expected_line in lines, (
            f"Expected line '{expected_line}' in {lines} for cause={cause!r} "
            f"(len={len(cause)})"
        )

    @given(
        cause=st.text(
            min_size=_CAUSE_OF_DEATH_MAX_LEN + 1,
            max_size=600,
            alphabet=st.characters(categories=("L", "N", "P", "Z")),
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_config_enabled_long_value_truncated_with_ellipsis(
        self, qapp, cause: str
    ) -> None:
        """When config enabled and value length > 50, line is truncated with ellipsis.

        Feature: enhanced-name-cards, Property 11: Cause of death display and truncation
        **Validates: Requirements 6.1, 6.2, 6.4**
        """
        config = PersonBoxConfig(cause_of_death=True)
        display_data = {
            "name": "Test Person",
            "cause_of_death": cause,
        }

        box = PersonBoxItem(
            person_id="p1", display_data=display_data, config=config
        )
        lines = box._lines

        expected_line = f"{self._PREFIX}{cause[:_CAUSE_OF_DEATH_MAX_LEN]}\u2026"
        assert expected_line in lines, (
            f"Expected truncated line '{expected_line}' in {lines} for "
            f"cause of length {len(cause)}"
        )

        # Also verify the full (untruncated) line is NOT present
        full_line = f"{self._PREFIX}{cause}"
        assert full_line not in lines, (
            f"Full untruncated line should NOT be present for cause of "
            f"length {len(cause)}, but found '{full_line}' in {lines}"
        )
