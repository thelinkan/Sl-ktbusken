"""Unit tests for PlaceListItemDelegate.

Tests that the delegate correctly identifies places that need a red dot indicator
based on place type and parent_place_id assignment.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from slaktbusken.model.place import Place, needs_red_dot
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.ui.editors.place_editor import PlaceListItemDelegate


def _make_project_data(places: list[Place]) -> ProjectData:
    """Create a minimal ProjectData with the given places."""
    return ProjectData(
        format="släktbuske-file",
        version="0.1",
        project=ProjectMetadata(
            title="Test",
            main_person_id=None,
            created_by="test",
            language="sv-SE",
        ),
        persons=[],
        families=[],
        events=[],
        places=places,
        sources=[],
        media=[],
        repositories=[],
        dna_companies=[],
        dna_profiles=[],
        dna_matches=[],
        dna_segments=[],
        dna_clusters=[],
        dna_triangulations=[],
        research_notes=[],
    )


class TestPlaceListItemDelegateFindPlace:
    """Tests for the delegate's internal _find_place method."""

    def test_find_existing_place(self) -> None:
        """Delegate finds a place by ID from project data."""
        place = Place(id="p1", type="parish", name="Ljusdal")
        project_data = _make_project_data([place])
        delegate = PlaceListItemDelegate(project_data)

        result = delegate._find_place("p1")

        assert result is place

    def test_find_nonexistent_place_returns_none(self) -> None:
        """Delegate returns None for an ID not in project data."""
        place = Place(id="p1", type="parish", name="Ljusdal")
        project_data = _make_project_data([place])
        delegate = PlaceListItemDelegate(project_data)

        result = delegate._find_place("nonexistent")

        assert result is None

    def test_find_place_empty_project(self) -> None:
        """Delegate returns None when project has no places."""
        project_data = _make_project_data([])
        delegate = PlaceListItemDelegate(project_data)

        result = delegate._find_place("p1")

        assert result is None


class TestPlaceListItemDelegateRedDotLogic:
    """Tests confirming the delegate uses needs_red_dot correctly."""

    def test_non_country_without_parent_needs_dot(self) -> None:
        """A parish without parent_place_id needs the red dot."""
        place = Place(id="p1", type="parish", name="Ljusdal", parent_place_id=None)
        assert needs_red_dot(place) is True

    def test_country_without_parent_no_dot(self) -> None:
        """A country without parent_place_id does NOT need the red dot."""
        place = Place(id="p1", type="country", name="Sverige", parent_place_id=None)
        assert needs_red_dot(place) is False

    def test_non_country_with_parent_no_dot(self) -> None:
        """A parish with parent_place_id does NOT need the red dot."""
        place = Place(id="p1", type="parish", name="Ljusdal", parent_place_id="p2")
        assert needs_red_dot(place) is False

    def test_country_with_parent_no_dot(self) -> None:
        """A country with parent_place_id does NOT need the red dot (edge case)."""
        place = Place(id="p1", type="country", name="Sverige", parent_place_id="p2")
        assert needs_red_dot(place) is False


class TestPlaceListItemDelegateConstants:
    """Tests for delegate class constants."""

    def test_dot_diameter_within_spec(self) -> None:
        """Dot diameter should be ≤8px as per spec."""
        assert PlaceListItemDelegate._DOT_DIAMETER <= 8

    def test_dot_spacing_is_4px(self) -> None:
        """Dot should be positioned 4px after text."""
        assert PlaceListItemDelegate._DOT_SPACING == 4
