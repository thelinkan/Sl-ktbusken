"""Age-related person validation checks.

Implements checks for maximum age, baptism age, marriage age, partner age
difference, childbirth age, birth intervals, and death-to-burial intervals.
"""

from __future__ import annotations

from slaktbusken.model.event import Event
from slaktbusken.model.family import Family
from slaktbusken.model.person import Person
from slaktbusken.persistence.settings_io import (
    AgeCheckThreshold,
    PersonCheckConfig,
)
from slaktbusken.services.checks.date_utils import (
    ParsedDate,
    age_in_years,
    days_between,
    parse_date_value,
)
from slaktbusken.services.person_check_engine import (
    CheckContext,
    CheckFinding,
    format_person_display,
)


def _get_threshold_for_sex(threshold: AgeCheckThreshold, sex: str) -> int:
    """Return the appropriate threshold value based on sex.

    For unknown sex ("U"), defaults to the male threshold.
    """
    if sex == "F":
        return threshold.female
    return threshold.male


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


def check_max_age(
    person: Person,
    events: list[Event],
    config: PersonCheckConfig,
    context: CheckContext,
) -> list[CheckFinding]:
    """Check if person has an unreasonably high age (Req 6.1).

    Computes age from birth to death. If no death event, uses current year.
    """
    threshold = config.age_checks.max_age
    if not threshold.enabled:
        return []

    birth_date = _find_event_date(events, "birth", person.id)
    if birth_date is None:
        return []

    death_date = _find_event_date(events, "death", person.id)
    if death_date is None:
        # Use current year as a proxy for "still alive"
        death_date = ParsedDate(year=context.current_year, month=None, day=None)

    age = age_in_years(birth_date, death_date)
    if age is None:
        return []

    limit = _get_threshold_for_sex(threshold, person.sex)
    if age > limit:
        return [_make_finding(
            person, events,
            f"Personen har en orimligt hög ålder ({age} år)",
        )]

    return []


def check_max_age_at_baptism(
    person: Person,
    events: list[Event],
    config: PersonCheckConfig,
) -> list[CheckFinding]:
    """Check if person was too old at baptism (Req 6.2)."""
    threshold = config.age_checks.max_age_at_baptism
    if not threshold.enabled:
        return []

    birth_date = _find_event_date(events, "birth", person.id)
    if birth_date is None:
        return []

    baptism_date = _find_event_date(events, "baptism", person.id)
    if baptism_date is None:
        return []

    age = age_in_years(birth_date, baptism_date)
    if age is None:
        return []

    limit = _get_threshold_for_sex(threshold, person.sex)
    if age > limit:
        return [_make_finding(
            person, events,
            f"Äldre än {limit} år vid dop",
        )]

    return []


def check_min_age_at_marriage(
    person: Person,
    events: list[Event],
    families: list[Family],
    config: PersonCheckConfig,
    context: CheckContext,
) -> list[CheckFinding]:
    """Check if person was too young at marriage (Req 6.3)."""
    threshold = config.age_checks.min_age_at_marriage
    if not threshold.enabled:
        return []

    birth_date = _find_event_date(events, "birth", person.id)
    if birth_date is None:
        return []

    findings: list[CheckFinding] = []
    limit = _get_threshold_for_sex(threshold, person.sex)

    for family in families:
        # Only check families where this person is a partner
        is_partner = any(p.person_id == person.id for p in family.partners)
        if not is_partner:
            continue

        for event_id in family.event_ids:
            event = context.events_by_id.get(event_id)
            if event is None or event.type != "marriage":
                continue
            if event.date is None:
                continue
            marriage_date = parse_date_value(event.date)
            if marriage_date is None:
                continue

            age = age_in_years(birth_date, marriage_date)
            if age is None:
                continue

            if age < limit:
                findings.append(_make_finding(
                    person, events,
                    f"Yngre än {limit} år vid äktenskap",
                ))

    return findings


def check_max_age_at_marriage(
    person: Person,
    events: list[Event],
    families: list[Family],
    config: PersonCheckConfig,
    context: CheckContext,
) -> list[CheckFinding]:
    """Check if person was too old at marriage (Req 6.4)."""
    threshold = config.age_checks.max_age_at_marriage
    if not threshold.enabled:
        return []

    birth_date = _find_event_date(events, "birth", person.id)
    if birth_date is None:
        return []

    findings: list[CheckFinding] = []
    limit = _get_threshold_for_sex(threshold, person.sex)

    for family in families:
        is_partner = any(p.person_id == person.id for p in family.partners)
        if not is_partner:
            continue

        for event_id in family.event_ids:
            event = context.events_by_id.get(event_id)
            if event is None or event.type != "marriage":
                continue
            if event.date is None:
                continue
            marriage_date = parse_date_value(event.date)
            if marriage_date is None:
                continue

            age = age_in_years(birth_date, marriage_date)
            if age is None:
                continue

            if age > limit:
                findings.append(_make_finding(
                    person, events,
                    f"Mer än {limit} år mellan två händelser (Vigsel och Födelse)",
                ))

    return findings


def check_max_partner_age_diff(
    person: Person,
    events: list[Event],
    families: list[Family],
    config: PersonCheckConfig,
    context: CheckContext,
) -> list[CheckFinding]:
    """Check if partner age difference is too large (Req 6.5).

    Creates a finding on the YOUNGER partner only to avoid duplicates.
    """
    if not config.age_checks.max_partner_age_diff_enabled:
        return []

    limit = config.age_checks.max_partner_age_diff

    birth_date = _find_event_date(events, "birth", person.id)
    if birth_date is None:
        return []

    findings: list[CheckFinding] = []

    for family in families:
        is_partner = any(p.person_id == person.id for p in family.partners)
        if not is_partner:
            continue

        for partner_ref in family.partners:
            if partner_ref.person_id == person.id:
                continue

            # Get partner's birth date
            partner_events = context.events_by_person.get(partner_ref.person_id, [])
            partner_birth = _find_event_date(partner_events, "birth", partner_ref.person_id)
            if partner_birth is None:
                continue

            # Compute year difference
            diff = abs(birth_date.year - partner_birth.year)
            if diff > limit:
                # Only report on the younger partner
                if birth_date.year > partner_birth.year:
                    # Current person is younger — report
                    findings.append(_make_finding(
                        person, events,
                        f"Största åldersskillnad mellan makar överstigen ({diff} år)",
                    ))
                # If current person is older, skip (finding will be on partner)

    return findings


def check_min_age_at_childbirth(
    person: Person,
    events: list[Event],
    config: PersonCheckConfig,
    context: CheckContext,
) -> list[CheckFinding]:
    """Check if parent was too young at childbirth (Req 6.6)."""
    threshold = config.age_checks.min_age_at_childbirth
    if not threshold.enabled:
        return []

    birth_date = _find_event_date(events, "birth", person.id)
    if birth_date is None:
        return []

    children_ids = context.children_of.get(person.id, [])
    if not children_ids:
        return []

    findings: list[CheckFinding] = []
    limit = _get_threshold_for_sex(threshold, person.sex)

    for child_id in children_ids:
        child_events = context.events_by_person.get(child_id, [])
        child_birth = _find_event_date(child_events, "birth", child_id)
        if child_birth is None:
            continue

        age = age_in_years(birth_date, child_birth)
        if age is None:
            continue

        if age < limit:
            findings.append(_make_finding(
                person, events,
                f"Vid födelsen var föräldern yngre än {limit} år",
            ))

    return findings


def check_max_age_at_childbirth(
    person: Person,
    events: list[Event],
    config: PersonCheckConfig,
    context: CheckContext,
) -> list[CheckFinding]:
    """Check if parent was too old at childbirth (Req 6.7)."""
    threshold = config.age_checks.max_age_at_childbirth
    if not threshold.enabled:
        return []

    birth_date = _find_event_date(events, "birth", person.id)
    if birth_date is None:
        return []

    children_ids = context.children_of.get(person.id, [])
    if not children_ids:
        return []

    findings: list[CheckFinding] = []
    limit = _get_threshold_for_sex(threshold, person.sex)

    for child_id in children_ids:
        child_events = context.events_by_person.get(child_id, [])
        child_birth = _find_event_date(child_events, "birth", child_id)
        if child_birth is None:
            continue

        age = age_in_years(birth_date, child_birth)
        if age is None:
            continue

        if age > limit:
            findings.append(_make_finding(
                person, events,
                f"Vid födelsen var föräldern äldre än {limit} år",
            ))

    return findings


def check_min_days_between_births(
    person: Person,
    events: list[Event],
    config: PersonCheckConfig,
    context: CheckContext,
) -> list[CheckFinding]:
    """Check minimum days between consecutive births for mothers (Req 6.8).

    Only applies to female persons (mothers).
    """
    if not config.age_checks.min_days_between_births_enabled:
        return []

    # Only check for mothers (female)
    if person.sex != "F":
        return []

    children_ids = context.children_of.get(person.id, [])
    if len(children_ids) < 2:
        return []

    limit = config.age_checks.min_days_between_births

    # Collect children's birth dates
    child_births: list[ParsedDate] = []
    for child_id in children_ids:
        child_events = context.events_by_person.get(child_id, [])
        child_birth = _find_event_date(child_events, "birth", child_id)
        if child_birth is not None and child_birth.day is not None and child_birth.month is not None:
            child_births.append(child_birth)

    if len(child_births) < 2:
        return []

    # Sort by date
    child_births.sort(key=lambda d: (d.year, d.month or 1, d.day or 1))

    findings: list[CheckFinding] = []
    for i in range(len(child_births) - 1):
        interval = days_between(child_births[i], child_births[i + 1])
        if interval is not None and interval < limit:
            findings.append(_make_finding(
                person, events,
                f"Kortare tid mellan barnafödslar än {limit} dagar",
            ))

    return findings


def check_max_days_death_to_burial(
    person: Person,
    events: list[Event],
    config: PersonCheckConfig,
) -> list[CheckFinding]:
    """Check max days between death and burial (Req 6.9)."""
    threshold = config.age_checks.max_days_death_to_burial
    if not threshold.enabled:
        return []

    death_date = _find_event_date(events, "death", person.id)
    if death_date is None:
        return []

    burial_date = _find_event_date(events, "burial", person.id)
    if burial_date is None:
        return []

    interval = days_between(death_date, burial_date)
    if interval is None:
        return []

    limit = _get_threshold_for_sex(threshold, person.sex)
    if interval > limit:
        return [_make_finding(
            person, events,
            f"Längre tid mellan död och begravning än {limit} dagar",
        )]

    return []


def check_age(
    person: Person,
    events: list[Event],
    families: list[Family],
    config: PersonCheckConfig,
    context: CheckContext,
) -> list[CheckFinding]:
    """Run all age-related checks for a person.

    This is the main entry point called by PersonCheckEngine.
    """
    findings: list[CheckFinding] = []

    findings.extend(check_max_age(person, events, config, context))
    findings.extend(check_max_age_at_baptism(person, events, config))
    findings.extend(check_min_age_at_marriage(person, events, families, config, context))
    findings.extend(check_max_age_at_marriage(person, events, families, config, context))
    findings.extend(check_max_partner_age_diff(person, events, families, config, context))
    findings.extend(check_min_age_at_childbirth(person, events, config, context))
    findings.extend(check_max_age_at_childbirth(person, events, config, context))
    findings.extend(check_min_days_between_births(person, events, config, context))
    findings.extend(check_max_days_death_to_burial(person, events, config))

    return findings
