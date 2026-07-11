"""Unit tests for source aspect mapping.

Tests cover the EVENT_SOURCE_ASPECTS dict, ASPECT_LABELS dict,
and the get_aspects_for_event_type function.

Requirements: 9.1
"""

from __future__ import annotations

from slaktbusken.services.source_aspects import (
    ASPECT_LABELS,
    EVENT_SOURCE_ASPECTS,
    get_aspects_for_event_type,
)


class TestEventSourceAspects:
    """Tests for the EVENT_SOURCE_ASPECTS constant."""

    def test_birth_aspects(self) -> None:
        """Birth events have date, place, parents, and witnesses."""
        assert EVENT_SOURCE_ASPECTS["birth"] == ["date", "place", "parents", "witnesses"]

    def test_death_aspects(self) -> None:
        """Death events have date, place, and cause_of_death."""
        assert EVENT_SOURCE_ASPECTS["death"] == ["date", "place", "cause_of_death"]

    def test_marriage_aspects(self) -> None:
        """Marriage events have date, place, and spouse."""
        assert EVENT_SOURCE_ASPECTS["marriage"] == ["date", "place", "spouse"]

    def test_default_aspects(self) -> None:
        """Default aspects are date and place."""
        assert EVENT_SOURCE_ASPECTS["_default"] == ["date", "place"]


class TestAspectLabels:
    """Tests for the ASPECT_LABELS constant."""

    def test_date_label(self) -> None:
        assert ASPECT_LABELS["date"] == "Datum"

    def test_place_label(self) -> None:
        assert ASPECT_LABELS["place"] == "Plats"

    def test_parents_label(self) -> None:
        assert ASPECT_LABELS["parents"] == "Föräldrar"

    def test_witnesses_label(self) -> None:
        assert ASPECT_LABELS["witnesses"] == "Vittnen"

    def test_cause_of_death_label(self) -> None:
        assert ASPECT_LABELS["cause_of_death"] == "Dödsorsak"

    def test_spouse_label(self) -> None:
        assert ASPECT_LABELS["spouse"] == "Make/maka"

    def test_all_aspects_have_labels(self) -> None:
        """Every aspect used in EVENT_SOURCE_ASPECTS has a corresponding label."""
        all_aspects = set()
        for aspects in EVENT_SOURCE_ASPECTS.values():
            all_aspects.update(aspects)
        for aspect in all_aspects:
            assert aspect in ASPECT_LABELS, f"Missing label for aspect: {aspect}"


class TestGetAspectsForEventType:
    """Tests for get_aspects_for_event_type function."""

    def test_birth(self) -> None:
        """Birth returns specific aspects."""
        assert get_aspects_for_event_type("birth") == ["date", "place", "parents", "witnesses"]

    def test_death(self) -> None:
        """Death returns specific aspects."""
        assert get_aspects_for_event_type("death") == ["date", "place", "cause_of_death"]

    def test_marriage(self) -> None:
        """Marriage returns specific aspects."""
        assert get_aspects_for_event_type("marriage") == ["date", "place", "spouse"]

    def test_unknown_type_returns_default(self) -> None:
        """Unknown event types return the default aspects."""
        assert get_aspects_for_event_type("baptism") == ["date", "place"]

    def test_empty_string_returns_default(self) -> None:
        """Empty string returns the default aspects."""
        assert get_aspects_for_event_type("") == ["date", "place"]

    def test_arbitrary_string_returns_default(self) -> None:
        """Any arbitrary string returns the default aspects."""
        assert get_aspects_for_event_type("some_random_event") == ["date", "place"]
