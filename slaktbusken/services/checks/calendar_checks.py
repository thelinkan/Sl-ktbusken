"""Calendar-related person validation checks.

Implements checks for Swedish calendar validity (Req 9.5) and
media file existence (Req 9.4).
"""

from __future__ import annotations

from pathlib import Path

from slaktbusken.model.event import Event
from slaktbusken.model.family import Family
from slaktbusken.model.person import Person
from slaktbusken.persistence.settings_io import PersonCheckConfig
from slaktbusken.services.checks.date_utils import (
    is_valid_swedish_calendar,
    parse_date_value,
)
from slaktbusken.services.person_check_engine import (
    CheckContext,
    CheckFinding,
    format_person_display,
)


def _make_finding(person: Person, events: list[Event], message: str) -> CheckFinding:
    """Create a CheckFinding for the given person."""
    return CheckFinding(
        person_id=person.id,
        person_display=format_person_display(person, events),
        person_sex=person.sex,
        message=message,
    )


def check_valid_swedish_calendar(
    person: Person,
    events: list[Event],
    config: PersonCheckConfig,
    context: CheckContext,
) -> list[CheckFinding]:
    """Validate all event dates against the Swedish calendar (Req 9.5).

    Checks each event date for the person using is_valid_swedish_calendar().
    Dates in the non-existent range 1753-02-18 to 1753-02-28, or invalid
    day-of-month for the applicable calendar system, produce a finding.
    """
    if not config.logic_checks.valid_swedish_calendar:
        return []

    findings: list[CheckFinding] = []

    for event in events:
        if event.date is None:
            continue
        # Only check events where this person is a participant
        is_participant = any(p.person_id == person.id for p in event.participants)
        if not is_participant:
            continue

        parsed = parse_date_value(event.date)
        if parsed is None:
            continue

        if not is_valid_swedish_calendar(parsed):
            date_str = event.date.value
            findings.append(_make_finding(
                person, events,
                f"Ogiltigt datum enligt svenska kalendern: {date_str}",
            ))

    return findings


def check_media_files_exist(
    person: Person,
    events: list[Event],
    config: PersonCheckConfig,
    context: CheckContext,
) -> list[CheckFinding]:
    """Check that media files referenced by the person's events exist (Req 9.4).

    For each event where the person is a participant, checks all media_ids.
    Looks up the MediaItem by ID and verifies that the file exists relative
    to the project folder. If project_folder is None, skip this check entirely.
    """
    if not config.logic_checks.media_files_exist:
        return []

    if context.project_folder is None:
        return []

    findings: list[CheckFinding] = []
    checked_media_ids: set[str] = set()

    for event in events:
        # Only check events where this person is a participant
        is_participant = any(p.person_id == person.id for p in event.participants)
        if not is_participant:
            continue

        for media_id in event.media_ids:
            # Avoid duplicate checks for same media within this person
            if media_id in checked_media_ids:
                continue
            checked_media_ids.add(media_id)

            media_item = context.media_by_id.get(media_id)
            if media_item is None:
                findings.append(_make_finding(
                    person, events,
                    f"Mediaobjekt saknas: {media_id}",
                ))
                continue

            # Check if the file exists relative to the project folder
            file_path = Path(context.project_folder) / media_item.file
            if not file_path.exists():
                findings.append(_make_finding(
                    person, events,
                    f"Mediafil saknas: {media_item.file}",
                ))

    return findings


def check_calendar(
    person: Person,
    events: list[Event],
    families: list[Family],
    config: PersonCheckConfig,
    context: CheckContext,
) -> list[CheckFinding]:
    """Run all calendar-related checks for a person.

    This is the main entry point called by PersonCheckEngine.
    """
    findings: list[CheckFinding] = []

    findings.extend(check_valid_swedish_calendar(person, events, config, context))
    findings.extend(check_media_files_exist(person, events, config, context))

    return findings
