"""Tests for the research labels in the Swedish locale module.

Every internal research value maps to its Swedish label, reverse lookups
round-trip, and an unknown key falls back to itself.

**Validates: Requirements 19.7, 30.6**
"""

from __future__ import annotations

import pytest

from slaktbusken.model.research_case import (
    SUPPORTED_ENTITY_TYPES,
    VALID_HYPOTHESIS_ASSESSMENTS,
    VALID_RESEARCH_PRIORITIES,
    VALID_RESEARCH_STATUSES,
)
from slaktbusken.ui.swedish_locale import (
    HYPOTHESIS_ASSESSMENT_LABELS,
    RESEARCH_ENTITY_TYPE_LABELS,
    RESEARCH_PRIORITY_LABELS,
    RESEARCH_STATUS_LABELS,
    get_hypothesis_assessment_label,
    get_research_entity_type_label,
    get_research_priority_label,
    get_research_status_label,
    hypothesis_assessment_from_label,
    research_priority_from_label,
    research_status_from_label,
)


class TestStatusLabels:
    @pytest.mark.parametrize(
        ("key", "label"),
        [
            ("open", "Öppen"),
            ("in_progress", "Pågår"),
            ("on_hold", "Vilande"),
            ("closed", "Avslutad"),
        ],
    )
    def test_each_status_has_its_swedish_label(self, key: str, label: str) -> None:
        """**Validates: Requirements 19.7**"""
        assert get_research_status_label(key) == label

    def test_labels_cover_exactly_the_valid_statuses(self) -> None:
        assert set(RESEARCH_STATUS_LABELS) == set(VALID_RESEARCH_STATUSES)

    @pytest.mark.parametrize("key", VALID_RESEARCH_STATUSES)
    def test_reverse_lookup_round_trips(self, key: str) -> None:
        assert research_status_from_label(get_research_status_label(key)) == key

    def test_unknown_status_falls_back_to_the_key(self) -> None:
        assert get_research_status_label("archived") == "archived"

    def test_unknown_label_has_no_key(self) -> None:
        assert research_status_from_label("Okänd") is None


class TestPriorityLabels:
    @pytest.mark.parametrize(
        ("key", "label"), [("low", "Låg"), ("normal", "Normal"), ("high", "Hög")]
    )
    def test_each_priority_has_its_swedish_label(self, key: str, label: str) -> None:
        """**Validates: Requirements 19.7**"""
        assert get_research_priority_label(key) == label

    def test_labels_cover_exactly_the_valid_priorities(self) -> None:
        assert set(RESEARCH_PRIORITY_LABELS) == set(VALID_RESEARCH_PRIORITIES)

    @pytest.mark.parametrize("key", VALID_RESEARCH_PRIORITIES)
    def test_reverse_lookup_round_trips(self, key: str) -> None:
        assert research_priority_from_label(get_research_priority_label(key)) == key

    def test_unknown_priority_falls_back_to_the_key(self) -> None:
        assert get_research_priority_label("urgent") == "urgent"

    def test_unknown_label_has_no_key(self) -> None:
        assert research_priority_from_label("Brådskande") is None


class TestAssessmentLabels:
    @pytest.mark.parametrize(
        ("key", "label"),
        [
            ("unassessed", "Ej bedömd"),
            ("possible", "Möjlig"),
            ("strong_support", "Starkt stöd"),
            ("confirmed", "Bekräftad"),
            ("rejected", "Avfärdad"),
        ],
    )
    def test_each_assessment_has_its_swedish_label(self, key: str, label: str) -> None:
        """**Validates: Requirements 30.6**"""
        assert get_hypothesis_assessment_label(key) == label

    def test_labels_cover_exactly_the_valid_assessments(self) -> None:
        assert set(HYPOTHESIS_ASSESSMENT_LABELS) == set(VALID_HYPOTHESIS_ASSESSMENTS)

    @pytest.mark.parametrize("key", VALID_HYPOTHESIS_ASSESSMENTS)
    def test_reverse_lookup_round_trips(self, key: str) -> None:
        assert hypothesis_assessment_from_label(get_hypothesis_assessment_label(key)) == key

    def test_unknown_assessment_falls_back_to_the_key(self) -> None:
        assert get_hypothesis_assessment_label("likely") == "likely"

    def test_unknown_label_has_no_key(self) -> None:
        assert hypothesis_assessment_from_label("Sannolik") is None


class TestEntityTypeLabels:
    @pytest.mark.parametrize(
        ("key", "label"),
        [
            ("person", "Person"),
            ("family", "Familj"),
            ("event", "Händelse"),
            ("place", "Plats"),
            ("source", "Källa"),
            ("media", "Media"),
            ("dna_match", "DNA-matchning"),
            ("dna_cluster", "DNA-kluster"),
        ],
    )
    def test_each_entity_type_has_its_swedish_label(self, key: str, label: str) -> None:
        """**Validates: Requirements 30.6**"""
        assert get_research_entity_type_label(key) == label

    def test_labels_cover_exactly_the_supported_entity_types(self) -> None:
        assert set(RESEARCH_ENTITY_TYPE_LABELS) == set(SUPPORTED_ENTITY_TYPES)

    def test_unknown_entity_type_falls_back_to_the_key(self) -> None:
        assert get_research_entity_type_label("residence") == "residence"


class TestLabelsAreDistinct:
    """Each dictionary is a bijection, so a label identifies one key."""

    @pytest.mark.parametrize(
        "labels",
        [
            RESEARCH_STATUS_LABELS,
            RESEARCH_PRIORITY_LABELS,
            HYPOTHESIS_ASSESSMENT_LABELS,
            RESEARCH_ENTITY_TYPE_LABELS,
        ],
    )
    def test_no_two_keys_share_a_label(self, labels: dict[str, str]) -> None:
        assert len(set(labels.values())) == len(labels)
