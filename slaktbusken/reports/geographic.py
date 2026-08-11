"""Geographic consistency report module.

Checks place hierarchy relationships and coordinate data, reporting
issues as structured ReportContent for the report preview system.

Also provides :func:`residence_places_for_person`, which returns the
residence places of a person in the timeline order defined by
Requirement 11.10, each labelled with the interval string from the
Residence_Formatter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData
from slaktbusken.reports.content import (
    EmptyStateBlock,
    HeadingBlock,
    ListBlock,
    ReportContent,
)
from slaktbusken.services.residence_query import residence_timeline
from slaktbusken.ui.swedish_locale import format_residence_interval


@dataclass
class GeoIssue:
    """A single geographic consistency issue found during validation."""

    place_id: str
    place_name: str
    check_type: str  # "county_no_country", "parish_no_county", "sub_no_parish", "missing_coords"


# Place types that must have a parish ancestor.
_SUB_PARISH_TYPES = frozenset({"church", "cemetery", "village", "farm", "school"})


def _has_ancestor_of_type(
    place: Place,
    ancestor_type: str,
    places_by_id: dict[str, Place],
) -> bool:
    """Walk the parent chain and return True if an ancestor of *ancestor_type* is found.

    Detects circular references via a visited set and treats a cycle as
    "ancestor not found" (returns False).
    """
    visited: set[str] = {place.id}
    current_id = place.parent_place_id

    while current_id is not None:
        if current_id in visited:
            # Circular reference detected — treat as ancestor not found.
            return False
        if current_id not in places_by_id:
            # Parent does not exist in the dataset.
            return False
        parent = places_by_id[current_id]
        if parent.type == ancestor_type:
            return True
        visited.add(current_id)
        current_id = parent.parent_place_id

    return False


def check_geographic_consistency(places: list[Place]) -> list[GeoIssue]:
    """Validate geographic hierarchy and coordinate data for all places.

    Returns a list of GeoIssue instances describing the problems found.
    """
    places_by_id: dict[str, Place] = {p.id: p for p in places}
    issues: list[GeoIssue] = []

    for place in places:
        if place.type == "county":
            if not _has_ancestor_of_type(place, "country", places_by_id):
                issues.append(
                    GeoIssue(
                        place_id=place.id,
                        place_name=place.name,
                        check_type="county_no_country",
                    )
                )

        elif place.type == "parish":
            if not _has_ancestor_of_type(place, "county", places_by_id):
                issues.append(
                    GeoIssue(
                        place_id=place.id,
                        place_name=place.name,
                        check_type="parish_no_county",
                    )
                )
            if place.latitude is None or place.longitude is None:
                issues.append(
                    GeoIssue(
                        place_id=place.id,
                        place_name=place.name,
                        check_type="missing_coords",
                    )
                )

        elif place.type in _SUB_PARISH_TYPES:
            if not _has_ancestor_of_type(place, "parish", places_by_id):
                issues.append(
                    GeoIssue(
                        place_id=place.id,
                        place_name=place.name,
                        check_type="sub_no_parish",
                    )
                )

    return issues


def generate_geographic_report(data: ProjectData) -> ReportContent:
    """Generate a full geographic consistency report from project data.

    Returns a ReportContent with four labeled sections covering hierarchy
    and coordinate checks, using Swedish labels and empty-state messages.
    """
    report = ReportContent(title="Geografisk konsistens")

    if not data.places:
        report.blocks.append(
            EmptyStateBlock(text="Det finns inga platser att kontrollera.")
        )
        return report

    issues = check_geographic_consistency(data.places)

    # Group issues by check_type.
    county_no_country = [i for i in issues if i.check_type == "county_no_country"]
    parish_no_county = [i for i in issues if i.check_type == "parish_no_county"]
    sub_no_parish = [i for i in issues if i.check_type == "sub_no_parish"]
    missing_coords = [i for i in issues if i.check_type == "missing_coords"]

    sections: list[tuple[str, list[GeoIssue]]] = [
        ("Län utan land", county_no_country),
        ("Församlingar utan län", parish_no_county),
        ("Undertyper utan församling", sub_no_parish),
        ("Församlingar utan koordinater", missing_coords),
    ]

    for heading_text, section_issues in sections:
        report.blocks.append(HeadingBlock(text=heading_text, level=2))
        if section_issues:
            report.blocks.append(
                ListBlock(
                    items=[
                        f"{issue.place_name} (id: {issue.place_id})"
                        for issue in section_issues
                    ]
                )
            )
        else:
            report.blocks.append(EmptyStateBlock(text="Inga problem hittades."))

    return report


@dataclass
class ResidencePlaceEntry:
    """A residence place entry for geographic display.

    Each entry carries the place, the interval string from the
    Residence_Formatter, and identifiers for further navigation.
    """

    place_id: str
    place_name: str
    interval_display: str
    residence_id: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None


def residence_places_for_person(
    data: ProjectData, person_id: str
) -> list[ResidencePlaceEntry]:
    """Return the residence places of *person_id* in timeline order.

    Each entry is labelled with the interval string from the
    Residence_Formatter. The ordering follows Requirement 11.10:
    ``start.earliest`` ascending, ``start.latest`` ascending (absent
    sorts earlier), then place display name in Swedish alphabetical order.

    The timeline order is provided by :func:`residence_timeline` from the
    residence query service (Requirement 8.7), which implements the same
    sort keys.

    *data* and every entity it holds are left unchanged.
    """
    places_by_id = {place.id: place for place in data.places}
    facts = residence_timeline(data, person_id)

    entries: list[ResidencePlaceEntry] = []
    for fact in facts:
        place = places_by_id.get(fact.place_id)
        place_name = place.name if place else fact.place_id
        interval_display = format_residence_interval(fact.start, fact.end)
        entries.append(
            ResidencePlaceEntry(
                place_id=fact.place_id,
                place_name=place_name,
                interval_display=interval_display,
                residence_id=fact.id,
                latitude=place.latitude if place else None,
                longitude=place.longitude if place else None,
            )
        )

    return entries
