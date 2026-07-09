"""Unit tests for the geographic consistency report module."""

from __future__ import annotations

from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.reports.content import EmptyStateBlock, HeadingBlock, ListBlock
from slaktbusken.reports.geographic import (
    GeoIssue,
    check_geographic_consistency,
    generate_geographic_report,
)


# ---------------------------------------------------------------------------
# Helper factory
# ---------------------------------------------------------------------------


def _make_project(places: list[Place]) -> ProjectData:
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        places=places,
    )


# ---------------------------------------------------------------------------
# check_geographic_consistency tests
# ---------------------------------------------------------------------------


class TestCheckGeographicConsistency:
    """Tests for the check_geographic_consistency function."""

    def test_empty_list_returns_no_issues(self) -> None:
        assert check_geographic_consistency([]) == []

    def test_county_with_country_parent_no_issue(self) -> None:
        places = [
            Place(id="p1", type="country", name="Sverige"),
            Place(id="p2", type="county", name="Stockholms län", parent_place_id="p1"),
        ]
        issues = check_geographic_consistency(places)
        assert not any(i.check_type == "county_no_country" for i in issues)

    def test_county_without_country_reports_issue(self) -> None:
        places = [
            Place(id="p1", type="county", name="Stockholms län"),
        ]
        issues = check_geographic_consistency(places)
        assert len(issues) == 1
        assert issues[0].check_type == "county_no_country"
        assert issues[0].place_id == "p1"
        assert issues[0].place_name == "Stockholms län"

    def test_county_with_indirect_country_ancestor(self) -> None:
        """County -> some intermediate -> country should pass."""
        places = [
            Place(id="p1", type="country", name="Sverige"),
            Place(id="p2", type="county", name="Mellanlän", parent_place_id="p1"),
            Place(id="p3", type="county", name="Underlän", parent_place_id="p2"),
        ]
        # p3 is a county whose ancestor chain has a county (p2) whose parent is a country
        issues = check_geographic_consistency(places)
        # p3 has country in its ancestor chain
        county_issues = [i for i in issues if i.check_type == "county_no_country"]
        assert not any(i.place_id == "p3" for i in county_issues)

    def test_parish_without_county_reports_issue(self) -> None:
        places = [
            Place(id="p1", type="parish", name="Hovs församling", latitude=57.0, longitude=12.0),
        ]
        issues = check_geographic_consistency(places)
        parish_issues = [i for i in issues if i.check_type == "parish_no_county"]
        assert len(parish_issues) == 1
        assert parish_issues[0].place_id == "p1"

    def test_parish_with_county_ancestor_no_hierarchy_issue(self) -> None:
        places = [
            Place(id="p1", type="county", name="Hallands län"),
            Place(id="p2", type="parish", name="Hovs församling", parent_place_id="p1", latitude=57.0, longitude=12.0),
        ]
        issues = check_geographic_consistency(places)
        assert not any(i.check_type == "parish_no_county" for i in issues)

    def test_parish_missing_latitude(self) -> None:
        places = [
            Place(id="p1", type="county", name="Hallands län"),
            Place(id="p2", type="parish", name="Test", parent_place_id="p1", latitude=None, longitude=12.0),
        ]
        issues = check_geographic_consistency(places)
        coord_issues = [i for i in issues if i.check_type == "missing_coords"]
        assert len(coord_issues) == 1
        assert coord_issues[0].place_id == "p2"

    def test_parish_missing_longitude(self) -> None:
        places = [
            Place(id="p1", type="county", name="Hallands län"),
            Place(id="p2", type="parish", name="Test", parent_place_id="p1", latitude=57.0, longitude=None),
        ]
        issues = check_geographic_consistency(places)
        coord_issues = [i for i in issues if i.check_type == "missing_coords"]
        assert len(coord_issues) == 1

    def test_parish_missing_both_coords(self) -> None:
        places = [
            Place(id="p1", type="county", name="Hallands län"),
            Place(id="p2", type="parish", name="Test", parent_place_id="p1"),
        ]
        issues = check_geographic_consistency(places)
        coord_issues = [i for i in issues if i.check_type == "missing_coords"]
        assert len(coord_issues) == 1

    def test_parish_with_both_coords_no_issue(self) -> None:
        places = [
            Place(id="p1", type="county", name="Hallands län"),
            Place(id="p2", type="parish", name="Test", parent_place_id="p1", latitude=57.0, longitude=12.0),
        ]
        issues = check_geographic_consistency(places)
        assert not any(i.check_type == "missing_coords" for i in issues)

    def test_sub_types_without_parish_reports_issue(self) -> None:
        for sub_type in ("church", "cemetery", "village", "farm", "school"):
            places = [
                Place(id="p1", type=sub_type, name=f"Test {sub_type}"),
            ]
            issues = check_geographic_consistency(places)
            sub_issues = [i for i in issues if i.check_type == "sub_no_parish"]
            assert len(sub_issues) == 1, f"Expected issue for {sub_type}"
            assert sub_issues[0].place_id == "p1"

    def test_sub_type_with_parish_ancestor_no_issue(self) -> None:
        places = [
            Place(id="p1", type="parish", name="Hovs församling", latitude=57.0, longitude=12.0),
            Place(id="p2", type="church", name="Hovs kyrka", parent_place_id="p1"),
        ]
        issues = check_geographic_consistency(places)
        assert not any(i.check_type == "sub_no_parish" for i in issues)

    def test_circular_parent_reference_treated_as_missing_ancestor(self) -> None:
        """A circular parent chain should be treated as ancestor not found."""
        places = [
            Place(id="p1", type="county", name="Cykel A", parent_place_id="p2"),
            Place(id="p2", type="county", name="Cykel B", parent_place_id="p1"),
        ]
        issues = check_geographic_consistency(places)
        county_issues = [i for i in issues if i.check_type == "county_no_country"]
        assert len(county_issues) == 2

    def test_self_referencing_parent_treated_as_missing_ancestor(self) -> None:
        """A place pointing to itself as parent should not cause infinite loop."""
        places = [
            Place(id="p1", type="county", name="Själv", parent_place_id="p1"),
        ]
        issues = check_geographic_consistency(places)
        county_issues = [i for i in issues if i.check_type == "county_no_country"]
        assert len(county_issues) == 1

    def test_country_type_not_checked(self) -> None:
        """Countries themselves should not produce any issues."""
        places = [
            Place(id="p1", type="country", name="Sverige"),
        ]
        issues = check_geographic_consistency(places)
        assert issues == []


# ---------------------------------------------------------------------------
# generate_geographic_report tests
# ---------------------------------------------------------------------------


class TestGenerateGeographicReport:
    """Tests for the generate_geographic_report function."""

    def test_title_is_correct(self) -> None:
        data = _make_project([])
        report = generate_geographic_report(data)
        assert report.title == "Geografisk konsistens"

    def test_empty_places_returns_empty_state(self) -> None:
        data = _make_project([])
        report = generate_geographic_report(data)
        assert len(report.blocks) == 1
        assert isinstance(report.blocks[0], EmptyStateBlock)
        assert report.blocks[0].text == "Det finns inga platser att kontrollera."

    def test_no_issues_shows_four_sections_with_empty_states(self) -> None:
        places = [
            Place(id="p1", type="country", name="Sverige"),
            Place(id="p2", type="county", name="Hallands län", parent_place_id="p1"),
            Place(id="p3", type="parish", name="Hovs", parent_place_id="p2", latitude=57.0, longitude=12.0),
            Place(id="p4", type="church", name="Hovs kyrka", parent_place_id="p3"),
        ]
        data = _make_project(places)
        report = generate_geographic_report(data)

        # Should have 4 sections, each with heading + empty state = 8 blocks
        assert len(report.blocks) == 8
        headings = [b for b in report.blocks if isinstance(b, HeadingBlock)]
        empty_states = [b for b in report.blocks if isinstance(b, EmptyStateBlock)]
        assert len(headings) == 4
        assert len(empty_states) == 4
        for es in empty_states:
            assert es.text == "Inga problem hittades."

    def test_section_headings_are_correct(self) -> None:
        places = [Place(id="p1", type="country", name="Sverige")]
        data = _make_project(places)
        report = generate_geographic_report(data)

        headings = [b for b in report.blocks if isinstance(b, HeadingBlock)]
        assert headings[0].text == "Län utan land"
        assert headings[0].level == 2
        assert headings[1].text == "Församlingar utan län"
        assert headings[1].level == 2
        assert headings[2].text == "Undertyper utan församling"
        assert headings[2].level == 2
        assert headings[3].text == "Församlingar utan koordinater"
        assert headings[3].level == 2

    def test_issues_rendered_as_list_block(self) -> None:
        places = [
            Place(id="county1", type="county", name="Orphan County"),
        ]
        data = _make_project(places)
        report = generate_geographic_report(data)

        # First section should have a ListBlock
        # blocks[0] = heading, blocks[1] = list
        assert isinstance(report.blocks[1], ListBlock)
        assert "Orphan County (id: county1)" in report.blocks[1].items

    def test_multiple_issues_in_one_section(self) -> None:
        places = [
            Place(id="c1", type="county", name="Län A"),
            Place(id="c2", type="county", name="Län B"),
        ]
        data = _make_project(places)
        report = generate_geographic_report(data)

        assert isinstance(report.blocks[1], ListBlock)
        assert len(report.blocks[1].items) == 2
