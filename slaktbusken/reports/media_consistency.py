"""Media consistency report module.

Checks media file references against project data and the file system,
reporting orphaned records, unlinked files, missing files, and duplicate
references as structured ReportContent for the report preview system.
"""

from __future__ import annotations

import logging
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from slaktbusken.model.project import ProjectData
from slaktbusken.reports.content import (
    EmptyStateBlock,
    HeadingBlock,
    ListBlock,
    ParagraphBlock,
    ReportContent,
)

logger = logging.getLogger(__name__)


def _normalize_path(path_str: str) -> str:
    """Normalize a file path string to NFC Unicode form for consistent comparison.

    File systems may store filenames in different Unicode normalization forms
    (NFC vs NFD), causing characters like å, ä, ö to compare unequal even
    though they look identical. This normalizes to NFC for reliable matching.
    """
    return unicodedata.normalize("NFC", path_str)


@dataclass
class MediaIssue:
    """A single media consistency issue found during validation."""

    issue_type: str  # "orphaned", "unlinked_file", "missing_file", "duplicate"
    media_id: str | None
    file_path: str
    title: str | None = None


def _collect_referenced_media_ids(data: ProjectData) -> set[str]:
    """Collect all media IDs referenced by persons, events, sources, and DNA companies."""
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

    return referenced


def _scan_media_folder(project_folder: Path) -> tuple[set[str], list[str]]:
    """Scan the media subfolder for all files, returning relative paths.

    Returns:
        A tuple of (relative_paths_set, warnings_list).
        If the media folder is inaccessible, returns an empty set and a warning message.
    """
    media_folder = project_folder / "media"
    warnings: list[str] = []

    if not media_folder.exists():
        return set(), []

    try:
        # Try listing to verify access
        files_on_disk: set[str] = set()
        for file_path in media_folder.rglob("*"):
            if file_path.is_file():
                # Store relative path from project_folder, normalized to NFC
                relative = file_path.relative_to(project_folder)
                normalized = _normalize_path(str(relative).replace("\\", "/"))
                files_on_disk.add(normalized)
        return files_on_disk, warnings
    except PermissionError:
        logger.warning("Media subfolder is inaccessible: %s", media_folder)
        warnings.append(f"Mediamappen är otillgänglig: {media_folder}")
        return set(), warnings


def check_media_consistency(
    data: ProjectData, project_folder: Path
) -> list[MediaIssue]:
    """Validate media references against project data and the file system.

    Performs four checks:
    1. Orphaned media records — MediaItems not referenced anywhere
    2. Unlinked files — Files on disk not matching any MediaItem.file
    3. Missing files — MediaItem.file values not found on disk
    4. Duplicate references — Multiple MediaItems sharing same file value

    Returns a list of MediaIssue instances describing the problems found.
    """
    issues: list[MediaIssue] = []

    # Gather all externally referenced media IDs
    referenced_ids = _collect_referenced_media_ids(data)

    # Check 1: Orphaned media records
    for item in data.media:
        has_linked_entities = bool(item.linked_entities)
        is_referenced = item.id in referenced_ids
        if not has_linked_entities and not is_referenced:
            issues.append(
                MediaIssue(
                    issue_type="orphaned",
                    media_id=item.id,
                    file_path=item.file,
                    title=item.title,
                )
            )

    # Scan disk for media files
    files_on_disk, scan_warnings = _scan_media_folder(project_folder)

    # Build set of known media file paths (from MediaItems), normalized to NFC
    known_media_files: set[str] = set()
    for item in data.media:
        if item.file:
            known_media_files.add(_normalize_path(item.file))

    # Check 2: Unlinked files — files on disk not in any MediaItem
    for file_path in sorted(files_on_disk):
        if file_path not in known_media_files:
            issues.append(
                MediaIssue(
                    issue_type="unlinked_file",
                    media_id=None,
                    file_path=file_path,
                )
            )

    # Check 3: Missing files — MediaItem.file not found on disk
    for item in data.media:
        if item.file and _normalize_path(item.file) not in files_on_disk:
            issues.append(
                MediaIssue(
                    issue_type="missing_file",
                    media_id=item.id,
                    file_path=item.file,
                    title=item.title,
                )
            )

    # Check 4: Duplicate references — multiple MediaItems with same file value
    file_counter: Counter[str] = Counter()
    for item in data.media:
        if item.file:
            file_counter[_normalize_path(item.file)] += 1

    duplicate_files = {f for f, count in file_counter.items() if count >= 2}
    for item in data.media:
        if item.file and _normalize_path(item.file) in duplicate_files:
            issues.append(
                MediaIssue(
                    issue_type="duplicate",
                    media_id=item.id,
                    file_path=item.file,
                    title=item.title,
                )
            )

    # Add scan warnings as issues (for inaccessible folders)
    # These are handled in generate_media_report via separate scan

    return issues


def generate_media_report(
    data: ProjectData, project_folder: Path
) -> ReportContent:
    """Generate a full media consistency report from project data.

    Returns a ReportContent with four labeled sections covering orphaned,
    unlinked, missing, and duplicate media checks, using Swedish labels
    and empty-state messages.
    """
    report = ReportContent(title="Mediakonsistens")

    # Check for inaccessible media folder
    _, scan_warnings = _scan_media_folder(project_folder)
    if scan_warnings:
        for warning_text in scan_warnings:
            report.blocks.append(ParagraphBlock(text=f"⚠ {warning_text}"))

    issues = check_media_consistency(data, project_folder)

    # Group issues by type
    orphaned = [i for i in issues if i.issue_type == "orphaned"]
    unlinked = [i for i in issues if i.issue_type == "unlinked_file"]
    missing = [i for i in issues if i.issue_type == "missing_file"]
    duplicates = [i for i in issues if i.issue_type == "duplicate"]

    sections: list[tuple[str, list[MediaIssue]]] = [
        ("Föräldralösa mediaposter", orphaned),
        ("Olänkade filer", unlinked),
        ("Saknade filer", missing),
        ("Duplicerade filreferenser", duplicates),
    ]

    for heading_text, section_issues in sections:
        report.blocks.append(HeadingBlock(text=heading_text, level=2))
        if section_issues:
            report.blocks.append(
                ListBlock(
                    items=[
                        _format_issue(issue) for issue in section_issues
                    ]
                )
            )
        else:
            report.blocks.append(EmptyStateBlock(text="Inga problem hittades."))

    return report


def _format_issue(issue: MediaIssue) -> str:
    """Format a MediaIssue into a human-readable list item."""
    parts: list[str] = []
    if issue.title:
        parts.append(issue.title)
    if issue.media_id:
        parts.append(f"(id: {issue.media_id})")
    parts.append(f"[{issue.file_path}]")
    return " ".join(parts)
