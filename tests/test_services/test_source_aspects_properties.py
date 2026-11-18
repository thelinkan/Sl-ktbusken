"""Property-based tests for event-type-specific aspect mapping.

Feature: source-management, Property 15: Event-type-specific aspect mapping

Validates: Requirements 9.1
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.services.source_aspects import (
    ASPECT_LABELS,
    EVENT_SOURCE_ASPECTS,
    get_aspects_for_event_type,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Known event types with their expected aspect lists
_KNOWN_EVENT_TYPES = {
    "birth": ["date", "place", "parents", "witnesses"],
    "death": ["date", "place", "cause_of_death"],
    "marriage": ["date", "place", "spouse"],
}

# Unknown event types: any string that is not a registered event type key
# ("_default" is allowed since it maps to the default list itself)
_REGISTERED_EVENT_TYPES = frozenset(EVENT_SOURCE_ASPECTS) - {"_default"}

unknown_event_type = st.text(min_size=0, max_size=50).filter(
    lambda s: s not in _REGISTERED_EVENT_TYPES
)


# ---------------------------------------------------------------------------
# Property 15: Event-type-specific aspect mapping
# ---------------------------------------------------------------------------


class TestEventTypeAspectMappingProperty:
    """Feature: source-management, Property 15: Event-type-specific aspect mapping

    For any event type, the aspect set function SHALL return
    ["date", "place", "parents", "witnesses"] for birth,
    ["date", "place", "cause_of_death"] for death,
    ["date", "place", "spouse"] for marriage,
    and ["date", "place"] for all other types.

    **Validates: Requirements 9.1**
    """

    @given(event_type=st.sampled_from(list(_KNOWN_EVENT_TYPES.keys())))
    @settings(max_examples=100, deadline=None)
    def test_known_types_return_specific_aspect_lists(self, event_type: str) -> None:
        """For the known types (birth, death, marriage), the function always
        returns the specific expected list.

        Feature: source-management, Property 15: Event-type-specific aspect mapping
        **Validates: Requirements 9.1**
        """
        result = get_aspects_for_event_type(event_type)
        expected = _KNOWN_EVENT_TYPES[event_type]
        assert result == expected, (
            f"Expected {expected} for event_type='{event_type}', but got {result}"
        )

    @given(event_type=unknown_event_type)
    @settings(max_examples=100, deadline=None)
    def test_unknown_types_return_default_date_place(self, event_type: str) -> None:
        """For ANY string that is not "birth", "death", or "marriage", the
        function returns ["date", "place"].

        Feature: source-management, Property 15: Event-type-specific aspect mapping
        **Validates: Requirements 9.1**
        """
        result = get_aspects_for_event_type(event_type)
        assert result == ["date", "place"], (
            f"Expected ['date', 'place'] for unknown event_type='{event_type}', "
            f"but got {result}"
        )

    @given(event_type=st.text(min_size=0, max_size=50))
    @settings(max_examples=100, deadline=None)
    def test_all_returned_aspects_have_labels(self, event_type: str) -> None:
        """All returned aspects have labels in ASPECT_LABELS.

        Feature: source-management, Property 15: Event-type-specific aspect mapping
        **Validates: Requirements 9.1**
        """
        result = get_aspects_for_event_type(event_type)
        for aspect in result:
            assert aspect in ASPECT_LABELS, (
                f"Aspect '{aspect}' returned for event_type='{event_type}' "
                f"has no label in ASPECT_LABELS"
            )
