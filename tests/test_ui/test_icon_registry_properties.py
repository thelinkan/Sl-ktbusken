"""Property-based tests for IconRegistry.

Feature: ui-enhancements, Property 1: Event icon registry completeness
Feature: ui-enhancements, Property 2: Event icon fallback for unrecognized types

Validates: Requirements 1.1, 1.5
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from PySide6.QtWidgets import QApplication

from slaktbusken.ui.icons import IconRegistry

# The complete set of recognized event types as defined in the design.
RECOGNIZED_EVENT_TYPES = [
    "birth",
    "baptism",
    "death",
    "burial",
    "cremation",
    "marriage",
    "divorce",
    "divorce_filed",
    "engagement",
    "emigration",
    "immigration",
    "census",
    "confirmation",
    "first_communion",
    "adoption",
    "blessing",
    "graduation",
    "retirement",
    "will",
    "name_change",
    "gender_correction",
    "custom_individual_event",
    "custom_family_event",
]


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestEventIconRegistryCompleteness:
    """Feature: ui-enhancements, Property 1: Event icon registry completeness

    For every event type in the defined set, verify get_event_icon()
    returns a valid non-null QPixmap distinct from the fallback.

    **Validates: Requirements 1.1**
    """

    @given(event_type=st.sampled_from(RECOGNIZED_EVENT_TYPES))
    @settings(max_examples=100, deadline=None)
    def test_recognized_event_type_returns_valid_non_null_pixmap(
        self, event_type: str
    ) -> None:
        """Property 1: Every recognized event type returns a valid,
        non-null QPixmap distinct from the generic fallback icon.

        Feature: ui-enhancements, Property 1: Event icon registry completeness
        **Validates: Requirements 1.1**
        """
        registry = IconRegistry()
        pixmap = registry.get_event_icon(event_type)

        # The pixmap must not be null
        assert not pixmap.isNull(), (
            f"get_event_icon('{event_type}') returned a null QPixmap"
        )

        # The pixmap must be distinct from the fallback
        fallback = registry.get_event_icon("__nonexistent__")
        assert pixmap.cacheKey() != fallback.cacheKey(), (
            f"get_event_icon('{event_type}') returned the same pixmap as "
            f"the fallback icon (cacheKey={pixmap.cacheKey()})"
        )


class TestEventIconFallbackForUnrecognizedTypes:
    """Feature: ui-enhancements, Property 2: Event icon fallback for unrecognized types

    For arbitrary strings not in the recognized set, verify get_event_icon()
    returns the generic fallback icon without raising.

    **Validates: Requirements 1.5**
    """

    @given(
        event_type=st.text().filter(
            lambda s: s not in RECOGNIZED_EVENT_TYPES
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_unrecognized_event_type_returns_fallback_without_raising(
        self, event_type: str
    ) -> None:
        """Property 2: Any unrecognized event type string returns the
        generic fallback icon (never null, never raises an exception).

        Feature: ui-enhancements, Property 2: Event icon fallback for unrecognized types
        **Validates: Requirements 1.5**
        """
        registry = IconRegistry()

        # Must not raise any exception
        pixmap = registry.get_event_icon(event_type)

        # The pixmap must not be null
        assert not pixmap.isNull(), (
            f"get_event_icon('{event_type!r}') returned a null QPixmap"
        )

        # The pixmap must be the same as the fallback
        fallback = registry.get_event_icon("__nonexistent__")
        assert pixmap.cacheKey() == fallback.cacheKey(), (
            f"get_event_icon('{event_type!r}') returned a pixmap different "
            f"from the fallback (got cacheKey={pixmap.cacheKey()}, "
            f"expected={fallback.cacheKey()})"
        )
