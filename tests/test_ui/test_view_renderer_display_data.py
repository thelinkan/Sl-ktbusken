"""Integration tests for view renderer _build_display_data.

Verifies that all three view renderers (family_view, ancestry_view,
descendants_view) correctly populate the display_data dictionary
with DNA profiles, clusters, events, and media fields.

Requirements: 1.1, 2.1, 3.1, 4.1, 5.1, 6.1, 7.1
"""

from __future__ import annotations

import pytest

from slaktbusken.model.dna import DnaCluster, DnaCompany, DnaProfile
from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.ui.views.ancestry_view import (
    _build_display_data as ancestry_build_display_data,
)
from slaktbusken.ui.views.descendants_view import (
    _build_display_data as descendants_build_display_data,
)
from slaktbusken.ui.views.family_view import (
    _build_display_data as family_build_display_data,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_person(
    person_id: str = "p1",
    names: list[Name] | None = None,
    profile_media_id: str | None = None,
) -> Person:
    """Create a person with configurable names."""
    if names is None:
        names = [Name(type="birth", given="Erik", surname="Svensson")]
    return Person(id=person_id, sex="male", names=names, profile_media_id=profile_media_id)


def _make_project_data(
    persons: list[Person] | None = None,
    events: list[Event] | None = None,
    places: list[Place] | None = None,
    dna_companies: list[DnaCompany] | None = None,
    dna_profiles: list[DnaProfile] | None = None,
    dna_clusters: list[DnaCluster] | None = None,
    main_person_id: str | None = None,
) -> ProjectData:
    """Create ProjectData with configurable entities."""
    return ProjectData(
        project=ProjectMetadata(title="Test", main_person_id=main_person_id),
        persons=persons or [],
        events=events or [],
        places=places or [],
        dna_companies=dna_companies or [],
        dna_profiles=dna_profiles or [],
        dna_clusters=dna_clusters or [],
    )


# ---------------------------------------------------------------------------
# Test: has_multiple_names
# ---------------------------------------------------------------------------


class TestDisplayDataHasMultipleNames:
    """Tests for the has_multiple_names field in display_data."""

    def test_display_data_has_multiple_names_true(self) -> None:
        """Person with 2 names → has_multiple_names is True."""
        person = _make_person(
            names=[
                Name(type="birth", given="Anna", surname="Karlsson"),
                Name(type="married", given="Anna", surname="Svensson"),
            ]
        )
        project_data = _make_project_data(persons=[person])

        result = family_build_display_data(person, project_data)

        assert result["has_multiple_names"] is True

    def test_display_data_has_multiple_names_false(self) -> None:
        """Person with 1 name → has_multiple_names is False."""
        person = _make_person(
            names=[Name(type="birth", given="Erik", surname="Svensson")]
        )
        project_data = _make_project_data(persons=[person])

        result = family_build_display_data(person, project_data)

        assert result["has_multiple_names"] is False


# ---------------------------------------------------------------------------
# Test: cause_of_death
# ---------------------------------------------------------------------------


class TestDisplayDataCauseOfDeath:
    """Tests for the cause_of_death field in display_data."""

    def test_display_data_cause_of_death(self) -> None:
        """Person with death event that has cause_of_death → field populated."""
        person = _make_person()
        death_event = Event(
            id="e1",
            type="death",
            participants=[Participant(person_id="p1", role="subject")],
            date=DateValue(value="1920-03-15", precision="exact"),
            cause_of_death="Hjärtsvikt",
        )
        project_data = _make_project_data(persons=[person], events=[death_event])

        result = family_build_display_data(person, project_data)

        assert result["cause_of_death"] == "Hjärtsvikt"

    def test_display_data_cause_of_death_none_when_no_death(self) -> None:
        """Person with no death event → cause_of_death is None."""
        person = _make_person()
        birth_event = Event(
            id="e1",
            type="birth",
            participants=[Participant(person_id="p1", role="subject")],
            date=DateValue(value="1850-01-01", precision="exact"),
        )
        project_data = _make_project_data(persons=[person], events=[birth_event])

        result = family_build_display_data(person, project_data)

        assert result["cause_of_death"] is None


# ---------------------------------------------------------------------------
# Test: dna_companies
# ---------------------------------------------------------------------------


class TestDisplayDataDnaCompanies:
    """Tests for the dna_companies field in display_data."""

    def test_display_data_dna_companies_populated(self) -> None:
        """Person with 2 DnaProfile records → dna_companies has 2 entries sorted."""
        person = _make_person()
        companies = [
            DnaCompany(id="c1", name="MyHeritage"),
            DnaCompany(id="c2", name="AncestryDNA"),
        ]
        profiles = [
            DnaProfile(id="dp1", person_id="p1", company_id="c1", test_type="autosomal"),
            DnaProfile(id="dp2", person_id="p1", company_id="c2", test_type="autosomal"),
        ]
        project_data = _make_project_data(
            persons=[person], dna_companies=companies, dna_profiles=profiles
        )

        result = family_build_display_data(person, project_data)

        assert len(result["dna_companies"]) == 2
        # Sorted alphabetically by name
        assert result["dna_companies"][0] == {"name": "AncestryDNA", "logo": None}
        assert result["dna_companies"][1] == {"name": "MyHeritage", "logo": None}

    def test_display_data_dna_companies_empty_when_no_profiles(self) -> None:
        """Person with no DNA profiles → dna_companies is []."""
        person = _make_person()
        project_data = _make_project_data(persons=[person])

        result = family_build_display_data(person, project_data)

        assert result["dna_companies"] == []


# ---------------------------------------------------------------------------
# Test: clusters
# ---------------------------------------------------------------------------


class TestDisplayDataClusters:
    """Tests for the clusters field in display_data."""

    def test_display_data_clusters_populated(self) -> None:
        """Person in 2 DnaCluster records → clusters has 2 entries sorted."""
        person = _make_person()
        clusters = [
            DnaCluster(id="cl1", name="Zetterström", person_ids=["p1"], color="#FF0000"),
            DnaCluster(id="cl2", name="Andersson", person_ids=["p1"], color="#00FF00"),
        ]
        project_data = _make_project_data(persons=[person], dna_clusters=clusters)

        result = family_build_display_data(person, project_data)

        assert len(result["clusters"]) == 2
        # Sorted alphabetically by name
        assert result["clusters"][0] == {"name": "Andersson", "color": "#00FF00"}
        assert result["clusters"][1] == {"name": "Zetterström", "color": "#FF0000"}

    def test_display_data_clusters_capped_at_5(self) -> None:
        """Person in 7 clusters → clusters has length 5."""
        person = _make_person()
        clusters = [
            DnaCluster(id=f"cl{i}", name=f"Cluster {i:02d}", person_ids=["p1"])
            for i in range(7)
        ]
        project_data = _make_project_data(persons=[person], dna_clusters=clusters)

        result = family_build_display_data(person, project_data)

        assert len(result["clusters"]) == 5

    def test_display_data_clusters_empty_when_not_member(self) -> None:
        """Person not in any cluster → clusters is []."""
        person = _make_person()
        clusters = [
            DnaCluster(id="cl1", name="Other Cluster", person_ids=["p99"]),
        ]
        project_data = _make_project_data(persons=[person], dna_clusters=clusters)

        result = family_build_display_data(person, project_data)

        assert result["clusters"] == []


# ---------------------------------------------------------------------------
# Test: profile_photo
# ---------------------------------------------------------------------------


class TestDisplayDataProfilePhoto:
    """Tests for the profile_photo field in display_data."""

    def test_display_data_profile_photo_is_none(self) -> None:
        """Person with profile_media_id → profile_photo is still None (loaded by caller)."""
        person = _make_person(profile_media_id="media_123")
        project_data = _make_project_data(persons=[person])

        result = family_build_display_data(person, project_data)

        assert result["profile_photo"] is None


# ---------------------------------------------------------------------------
# Test: all views produce same fields
# ---------------------------------------------------------------------------


class TestAllViewsProduceSameFields:
    """Test that all three view renderers produce identical display_data."""

    def test_all_views_produce_same_fields(self) -> None:
        """Call _build_display_data from all three views with the same input.

        Verify the results are identical.
        """
        person = _make_person(
            names=[
                Name(type="birth", given="Karl", surname="Svensson"),
                Name(type="married", given="Karl", surname="Johansson"),
            ],
            profile_media_id="photo_001",
        )
        place = Place(id="pl1", type="city", name="Stockholm")
        death_event = Event(
            id="e1",
            type="death",
            participants=[Participant(person_id="p1", role="subject")],
            date=DateValue(value="1920-11-05", precision="exact"),
            place=PlaceRef(place_id="pl1"),
            cause_of_death="Lunginflammation",
        )
        birth_event = Event(
            id="e2",
            type="birth",
            participants=[Participant(person_id="p1", role="subject")],
            date=DateValue(value="1855-06-20", precision="exact"),
            place=PlaceRef(place_id="pl1"),
        )
        companies = [
            DnaCompany(id="c1", name="23andMe"),
            DnaCompany(id="c2", name="FamilyTreeDNA"),
        ]
        profiles = [
            DnaProfile(id="dp1", person_id="p1", company_id="c1", test_type="autosomal"),
            DnaProfile(id="dp2", person_id="p1", company_id="c2", test_type="y-dna"),
        ]
        clusters = [
            DnaCluster(id="cl1", name="Nordic", person_ids=["p1"], color="#0000FF"),
            DnaCluster(id="cl2", name="Baltic", person_ids=["p1"], color="#FFFF00"),
        ]
        project_data = _make_project_data(
            persons=[person],
            events=[death_event, birth_event],
            places=[place],
            dna_companies=companies,
            dna_profiles=profiles,
            dna_clusters=clusters,
        )

        family_result = family_build_display_data(person, project_data)
        ancestry_result = ancestry_build_display_data(person, project_data)
        descendants_result = descendants_build_display_data(person, project_data)

        # All three should produce the same keys
        assert set(family_result.keys()) == set(ancestry_result.keys())
        assert set(family_result.keys()) == set(descendants_result.keys())

        # All three should produce the same values
        assert family_result == ancestry_result
        assert family_result == descendants_result

        # Verify specific expected values are correct
        assert family_result["has_multiple_names"] is True
        assert family_result["cause_of_death"] == "Lunginflammation"
        assert family_result["birth_date"] == "1855-06-20"
        assert family_result["birth_place"] == "Stockholm"
        assert family_result["death_date"] == "1920-11-05"
        assert family_result["death_place"] == "Stockholm"
        assert family_result["profile_photo"] is None
        assert len(family_result["dna_companies"]) == 2
        assert family_result["dna_companies"][0]["name"] == "23andMe"
        assert family_result["dna_companies"][1]["name"] == "FamilyTreeDNA"
        assert len(family_result["clusters"]) == 2
        assert family_result["clusters"][0]["name"] == "Baltic"
        assert family_result["clusters"][1]["name"] == "Nordic"
