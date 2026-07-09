"""Property-based tests for media consistency report.

Feature: report-menu
Validates: Requirements 4.2
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import given, settings

from slaktbusken.model.project import ProjectData
from slaktbusken.reports.media_consistency import check_media_consistency

from tests.conftest import project_data_strategy


# ---------------------------------------------------------------------------
# Oracle functions (independent verification)
# ---------------------------------------------------------------------------


def _oracle_compute_orphaned_media_ids(data: ProjectData) -> set[str]:
    """Oracle: independently compute which MediaItem IDs are orphaned.

    A MediaItem is orphaned if it:
    - has no linked_entities
    - is not referenced by any Person's profile_media_id
    - is not referenced in any Event's media_ids
    - is not referenced in any Source's media_ids
    - is not referenced by any DnaCompany's logo_media_id
    """
    # Collect all externally referenced media IDs
    referenced: set[str] = set()

    for person in data.persons:
        if person.profile_media_id:
            referenced.add(person.profile_media_id)

    for event in data.events:
        for media_id in event.media_ids:
            referenced.add(media_id)

    for source in data.sources:
        for media_id in source.media_ids:
            referenced.add(media_id)

    for company in data.dna_companies:
        if company.logo_media_id:
            referenced.add(company.logo_media_id)

    # A media item is orphaned if it has no linked_entities AND is not referenced
    orphaned_ids: set[str] = set()
    for item in data.media:
        has_linked_entities = bool(item.linked_entities)
        is_referenced = item.id in referenced
        if not has_linked_entities and not is_referenced:
            orphaned_ids.add(item.id)

    return orphaned_ids


# ---------------------------------------------------------------------------
# Property 4: Orphaned media detection
# Feature: report-menu, Property 4: Orphaned media detection
# ---------------------------------------------------------------------------


@given(data=project_data_strategy())
@settings(max_examples=100)
def test_orphaned_media_detection_matches_oracle(data: ProjectData) -> None:
    """For any ProjectData, check_media_consistency returns orphaned issues for exactly
    the MediaItems that have no linked_entities and are not referenced by any Person's
    profile_media_id, Event's media_ids, Source's media_ids, or DnaCompany's logo_media_id.

    Validates: Requirements 4.2
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        project_folder = Path(tmp_dir)
        issues = check_media_consistency(data, project_folder)

    # Extract orphaned media IDs from the actual function output
    actual_orphaned_ids = {
        issue.media_id for issue in issues if issue.issue_type == "orphaned"
    }

    # Compute expected orphaned IDs using oracle
    expected_orphaned_ids = _oracle_compute_orphaned_media_ids(data)

    assert actual_orphaned_ids == expected_orphaned_ids, (
        f"Mismatch: actual={actual_orphaned_ids}, expected={expected_orphaned_ids}"
    )
