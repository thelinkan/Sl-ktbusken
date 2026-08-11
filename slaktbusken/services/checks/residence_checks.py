"""Residence coverage checks for the Person_Check_Engine.

Turns coverage gaps, open-endpoint suggestions and timeline gaps from
:mod:`slaktbusken.services.residence_coverage` into :class:`CheckFinding`
records, ordered by first uncovered year ascending with open-endpoint findings
last (Requirement 5.9).

Three :class:`~slaktbusken.persistence.settings_io.LogicCheckConfig` flags
gate each category independently:

- ``residence_coverage_gaps``
- ``residence_open_endpoints``
- ``residence_timeline_gaps``

Pure module: no Qt, no I/O, no mutation of the Project.
"""

from __future__ import annotations

from slaktbusken.model.event import Event
from slaktbusken.model.family import Family
from slaktbusken.model.person import Person
from slaktbusken.persistence.settings_io import PersonCheckConfig
from slaktbusken.services.checks.date_utils import parse_date_value
from slaktbusken.services.person_check_engine import (
    CheckContext,
    CheckFinding,
    format_person_display,
)
from slaktbusken.services.residence_coverage import analyze_person


def check_residence(
    person: Person,
    events: list[Event],
    families: list[Family],
    config: PersonCheckConfig,
    context: CheckContext,
) -> list[CheckFinding]:
    """Run all residence coverage checks for *person*.

    This is the main entry point called by :class:`PersonCheckEngine`.
    Returns :class:`CheckFinding` records ordered by first uncovered year
    ascending, with open-endpoint findings sorted last.
    """
    logic = config.logic_checks
    any_enabled = (
        logic.residence_coverage_gaps
        or logic.residence_open_endpoints
        or logic.residence_timeline_gaps
    )
    if not any_enabled:
        return []

    # Access the full ProjectData through the context's persons_by_id
    # We need the ProjectData — retrieve it from the context
    # The context doesn't carry ProjectData directly, so we import here
    # and reconstruct what we need. However, the engine passes the data;
    # we need to extend the call. Instead, we'll pass data via context.
    #
    # The engine has self._data but check functions receive (person, events,
    # families, config, context). We access data through a new attribute
    # on CheckContext that the engine sets.
    data = getattr(context, "project_data", None)
    if data is None:
        return []

    result = analyze_person(person.id, data)

    person_display = format_person_display(person, events)

    # Collect findings with a sort key: (first_year, is_open_endpoint)
    # Open-endpoint findings sort last (use a large sentinel year).
    _OPEN_ENDPOINT_SORT = float("inf")

    keyed_findings: list[tuple[float, CheckFinding]] = []

    # Coverage gaps
    if logic.residence_coverage_gaps:
        for gap in result.coverage_gaps:
            finding = CheckFinding(
                person_id=person.id,
                person_display=person_display,
                person_sex=person.sex,
                message=gap.suggestion,
            )
            keyed_findings.append((gap.first_year, finding))

    # Open-endpoint suggestions (sorted last)
    if logic.residence_open_endpoints:
        for suggestion in result.open_endpoint_suggestions:
            finding = CheckFinding(
                person_id=person.id,
                person_display=person_display,
                person_sex=person.sex,
                message=suggestion.suggestion,
            )
            keyed_findings.append((_OPEN_ENDPOINT_SORT, finding))

    # Timeline gaps
    if logic.residence_timeline_gaps:
        for gap in result.timeline_gaps:
            if gap.first_year == gap.last_year:
                msg = f"Personens boenden täcker inte år {gap.first_year}."
            else:
                msg = (
                    f"Personens boenden täcker inte perioden "
                    f"{gap.first_year}\u2013{gap.last_year}."
                )
            finding = CheckFinding(
                person_id=person.id,
                person_display=person_display,
                person_sex=person.sex,
                message=msg,
            )
            keyed_findings.append((gap.first_year, finding))

    # Sort by first uncovered year ascending; open-endpoint findings last
    keyed_findings.sort(key=lambda t: t[0])

    return [f for _, f in keyed_findings]
