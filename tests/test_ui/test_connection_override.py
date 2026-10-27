"""Unit tests for the connection-override dict helper.

Covers ``apply_connection_override``, the pure dict mutation that the
context-menu handler uses to set or clear a child's parentage override in
``ProjectData.connection_overrides`` (Requirements 5.1, 5.4, 5.5). The helper
is factored out of the GUI handler so it can be tested without a Qt event loop.
"""

from __future__ import annotations

import pytest

from slaktbusken.app import apply_connection_override


class TestApplyConnectionOverride:
    """Tests for apply_connection_override."""

    @pytest.mark.parametrize(
        ("action_type", "expected_value"),
        [
            ("override_biological", "biological"),
            ("override_foster", "foster"),
            ("override_adoptive", "adoptive"),
        ],
    )
    def test_set_override_on_empty_dict(self, action_type, expected_value):
        """Setting an override writes the matching parentage value."""
        overrides: dict[str, str] = {}
        changed = apply_connection_override(overrides, action_type, "child_1")
        assert changed is True
        assert overrides == {"child_1": expected_value}

    def test_set_override_replaces_existing_value(self):
        """Changing an existing override to a different value mutates the dict."""
        overrides = {"child_1": "biological"}
        changed = apply_connection_override(overrides, "override_foster", "child_1")
        assert changed is True
        assert overrides == {"child_1": "foster"}

    def test_set_override_same_value_is_noop(self):
        """Setting the value the child already holds reports no change."""
        overrides = {"child_1": "foster"}
        changed = apply_connection_override(overrides, "override_foster", "child_1")
        assert changed is False
        assert overrides == {"child_1": "foster"}

    def test_clear_removes_existing_override(self):
        """Clearing removes the child's entry and reports a change."""
        overrides = {"child_1": "adoptive", "child_2": "foster"}
        changed = apply_connection_override(overrides, "override_clear", "child_1")
        assert changed is True
        assert overrides == {"child_2": "foster"}

    def test_clear_on_absent_child_is_noop(self):
        """Clearing a child with no override reports no change."""
        overrides = {"child_2": "foster"}
        changed = apply_connection_override(overrides, "override_clear", "child_1")
        assert changed is False
        assert overrides == {"child_2": "foster"}

    def test_unknown_action_is_noop(self):
        """An unrecognised action type leaves the dict untouched."""
        overrides = {"child_1": "foster"}
        changed = apply_connection_override(overrides, "something_else", "child_1")
        assert changed is False
        assert overrides == {"child_1": "foster"}
