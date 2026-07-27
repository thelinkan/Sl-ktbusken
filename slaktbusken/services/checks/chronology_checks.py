"""Chronology-related person validation checks.

Implements checks for reasonable dates, event ordering relative to birth and
death, burial timing, and parent–child date constraints.
"""

from __future__ import annotations

from slaktbusken.model.event import Event
from slaktbusken.model.family import Family
from slaktbusken.model.person import Person
from slaktbusken.persistence.settings_io import PersonCheckConfig
from slaktbusken.services.checks.date_utils import (
    ParsedDate,
    compare_dates,
    days_between,
    parse_date_value,
)
from slaktbusken.services.person_check_engine import (
    CheckContext,
    CheckFinding,
    format_person_display,
)

# Event types that are allowed after death
_ALLOWED_AFTER_DEATH = {"burial", "probate", "will"}


def _find_event_date(events: list[Event], event_type: str, person_id: str) -> ParsedDate | None:
    """Find and parse the date of a specific event type for a person."""
    for event in events:
        if event.type == event_type:
            for participant in event.participants:
                if participant.person_id == person_id:
                    if event.date:
                        return parse_date_value(event.date)
                    return None
    return None


def _make_finding(person: Person, events: list[Event], message: str) -> CheckFinding:
    """Create a CheckFinding for the given person."""
    return CheckFinding(
        person_id=person.id,
        person_display=format_person_display(person, events),
        person_sex=person.sex,
        message=message,
    )


def check_reasonable_dates(
    person: Person,
    events: list[Event],
    config: PersonCheckConfig,
    context: CheckContext,
) -> list[CheckFinding]:
    """Check that event dates fall in a reasonable range (Req 8.1).

    Flags dates with year < 1000 or year > current year.
    """
    if not config.logic_checks.reasonable_dates:
        return []

    findings: list[CheckFinding] = []
    current_year = context.current_year

    for event in events:
        if event.date is None:
            continue
        parsed = parse_date_value(event.date)
        if parsed is None:
            continue
        if parsed.year < 1000:
            findings.append(_make_finding(
                person, events,
                f"Orimligt datum: år {parsed.year} är före år 1000",
            ))
        elif parsed.year > current_year:
            findings.append(_make_finding(
                person, events,
                f"Orimligt datum: år {parsed.year} är efter innevarande år ({current_year})",
            ))

    return findings


def check_no_event_before_birth(
    person: Person,
    events: list[Event],
    config: PersonCheckConfig,
) -> list[CheckFinding]:
    """Check that no events occur before the person's birth (Req 8.2).

    Uses compare_dates with precision awareness.
    """
    if not config.logic_checks.no_event_before_birth:
        return []

    birth_date = _find_event_date(events, "birth", person.id)
    if birth_date is None:
        return []

    findings: list[CheckFinding] = []

    for event in events:
        if event.type == "birth":
            continue
        if event.date is None:
            continue
        # Only check events where this person is a participant
        is_participant = any(p.person_id == person.id for p in event.participants)
        if not is_participant:
            continue

        event_date = parse_date_value(event.date)
        if event_date is None:
            continue

        cmp = compare_dates(event_date, birth_date)
        if cmp is not None and cmp < 0:
            findings.append(_make_finding(
                person, events,
                f"Händelse ({event.type}) inträffar före födelsen",
            ))

    return findings


def check_burial_not_before_death(
    person: Person,
    events: list[Event],
    config: PersonCheckConfig,
) -> list[CheckFinding]:
    """Check that burial/estate inventory does not precede death (Req 8.3).

    Applies to BURIAL and ESTATE_INVENTORY events.
    """
    if not config.logic_checks.burial_not_before_death:
        return []

    death_date = _find_event_date(events, "death", person.id)
    if death_date is None:
        return []

    findings: list[CheckFinding] = []

    for event in events:
        if event.type not in ("burial", "probate"):
            continue
        if event.date is None:
            continue
        is_participant = any(p.person_id == person.id for p in event.participants)
        if not is_participant:
            continue

        event_date = parse_date_value(event.date)
        if event_date is None:
            continue

        cmp = compare_dates(event_date, death_date)
        if cmp is not None and cmp < 0:
            findings.append(_make_finding(
                person, events,
                f"Händelse ({event.type}) inträffar före döden",
            ))

    return findings


def check_only_burial_after_death(
    person: Person,
    events: list[Event],
    config: PersonCheckConfig,
) -> list[CheckFinding]:
    """Check that only burial/estate/will events occur after death (Req 8.4).

    Events after death that are NOT BURIAL, ESTATE_INVENTORY, or WILL
    produce a finding.
    """
    if not config.logic_checks.only_burial_after_death:
        return []

    death_date = _find_event_date(events, "death", person.id)
    if death_date is None:
        return []

    findings: list[CheckFinding] = []

    for event in events:
        if event.type == "death":
            continue
        if event.type in _ALLOWED_AFTER_DEATH:
            continue
        if event.date is None:
            continue
        is_participant = any(p.person_id == person.id for p in event.participants)
        if not is_participant:
            continue

        event_date = parse_date_value(event.date)
        if event_date is None:
            continue

        cmp = compare_dates(event_date, death_date)
        if cmp is not None and cmp > 0:
            findings.append(_make_finding(
                person, events,
                f"Händelse ({event.type}) inträffar efter döden",
            ))

    return findings


def check_no_own_events_after_death(
    person: Person,
    events: list[Event],
    config: PersonCheckConfig,
) -> list[CheckFinding]:
    """Check that no own events (role=subject) occur after death (Req 8.5).

    Only flags events where the person is the subject participant.
    Excludes burial, probate, will, and death itself.
    """
    if not config.logic_checks.no_own_events_after_death:
        return []

    death_date = _find_event_date(events, "death", person.id)
    if death_date is None:
        return []

    findings: list[CheckFinding] = []

    for event in events:
        if event.type == "death":
            continue
        if event.type in _ALLOWED_AFTER_DEATH:
            continue
        if event.date is None:
            continue

        # Check if person is the subject participant
        is_subject = any(
            p.person_id == person.id and p.role == "subject"
            for p in event.participants
        )
        if not is_subject:
            continue

        event_date = parse_date_value(event.date)
        if event_date is None:
            continue

        cmp = compare_dates(event_date, death_date)
        if cmp is not None and cmp > 0:
            findings.append(_make_finding(
                person, events,
                f"Egen händelse ({event.type}) inträffar efter döden",
            ))

    return findings


def check_birth_not_after_parent_death(
    person: Person,
    events: list[Event],
    config: PersonCheckConfig,
    context: CheckContext,
) -> list[CheckFinding]:
    """Check birth is not more than 270 days after a parent's death (Req 8.6).

    A child can be born up to 270 days (9 months) after a parent's death
    (posthumous birth). Beyond that, the data is likely erroneous.
    """
    if not config.logic_checks.birth_not_after_parent_death:
        return []

    birth_date = _find_event_date(events, "birth", person.id)
    if birth_date is None:
        return []

    parent_ids = context.parents_of.get(person.id, [])
    if not parent_ids:
        return []

    findings: list[CheckFinding] = []

    for parent_id in parent_ids:
        parent_events = context.events_by_person.get(parent_id, [])
        parent_death = _find_event_date(parent_events, "death", parent_id)
        if parent_death is None:
            continue

        # First check: is birth after parent death at common precision?
        cmp = compare_dates(birth_date, parent_death)
        if cmp is not None and cmp > 0:
            # Birth is after parent death — check if within 270 days
            interval = days_between(parent_death, birth_date)
            if interval is not None:
                if interval > 270:
                    parent = context.persons_by_id.get(parent_id)
                    parent_name = ""
                    if parent and parent.names:
                        parent_name = f"{parent.names[0].given} {parent.names[0].surname}".strip()
                    findings.append(_make_finding(
                        person, events,
                        f"Född mer än 270 dagar efter förälders ({parent_name}) död",
                    ))
            else:
                # Can't compute days (missing day precision) but dates show
                # birth is clearly after parent death at available precision
                # Only flag if year difference makes it impossible
                # (birth year > parent death year + 1 means > 270 days for sure)
                if birth_date.year > parent_death.year + 1:
                    parent = context.persons_by_id.get(parent_id)
                    parent_name = ""
                    if parent and parent.names:
                        parent_name = f"{parent.names[0].given} {parent.names[0].surname}".strip()
                    findings.append(_make_finding(
                        person, events,
                        f"Född mer än 270 dagar efter förälders ({parent_name}) död",
                    ))

    return findings


def check_no_event_before_parent_birth(
    person: Person,
    events: list[Event],
    config: PersonCheckConfig,
    context: CheckContext,
) -> list[CheckFinding]:
    """Check that no events occur before a parent's birth (Req 8.7).

    A person cannot have any events before their parent was born.
    """
    if not config.logic_checks.no_event_before_parent_birth:
        return []

    parent_ids = context.parents_of.get(person.id, [])
    if not parent_ids:
        return []

    findings: list[CheckFinding] = []

    for parent_id in parent_ids:
        parent_events = context.events_by_person.get(parent_id, [])
        parent_birth = _find_event_date(parent_events, "birth", parent_id)
        if parent_birth is None:
            continue

        for event in events:
            if event.date is None:
                continue
            is_participant = any(p.person_id == person.id for p in event.participants)
            if not is_participant:
                continue

            event_date = parse_date_value(event.date)
            if event_date is None:
                continue

            cmp = compare_dates(event_date, parent_birth)
            if cmp is not None and cmp < 0:
                parent = context.persons_by_id.get(parent_id)
                parent_name = ""
                if parent and parent.names:
                    parent_name = f"{parent.names[0].given} {parent.names[0].surname}".strip()
                findings.append(_make_finding(
                    person, events,
                    f"Händelse ({event.type}) inträffar före förälders ({parent_name}) födelse",
                ))

    return findings


def check_chronology(
    person: Person,
    events: list[Event],
    families: list[Family],
    config: PersonCheckConfig,
    context: CheckContext,
) -> list[CheckFinding]:
    """Run all chronology-related checks for a person.

    This is the main entry point called by PersonCheckEngine.
    """
    findings: list[CheckFinding] = []

    findings.extend(check_reasonable_dates(person, events, config, context))
    findings.extend(check_no_event_before_birth(person, events, config))
    findings.extend(check_burial_not_before_death(person, events, config))
    findings.extend(check_only_burial_after_death(person, events, config))
    findings.extend(check_no_own_events_after_death(person, events, config))
    findings.extend(check_birth_not_after_parent_death(person, events, config, context))
    findings.extend(check_no_event_before_parent_birth(person, events, config, context))

    return findings
