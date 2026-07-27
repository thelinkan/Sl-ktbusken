"""Person check engine — orchestrates all enabled person validation checks."""

from __future__ import annotations

import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from slaktbusken.model.event import Event
from slaktbusken.model.family import Family
from slaktbusken.model.media import MediaItem
from slaktbusken.model.person import Person
from slaktbusken.model.project import ProjectData
from slaktbusken.persistence.settings_io import PersonCheckConfig
from slaktbusken.services.checks.date_utils import parse_date_value


@dataclass
class CheckFinding:
    """Ett identifierat dataproblem."""

    person_id: str
    person_display: str
    person_sex: str
    message: str


@dataclass
class CheckContext:
    """Förberäknade lookup-tabeller för effektiv kontrollexekvering."""

    persons_by_id: dict[str, Person] = field(default_factory=dict)
    events_by_id: dict[str, Event] = field(default_factory=dict)
    events_by_person: dict[str, list[Event]] = field(default_factory=dict)
    families_by_person: dict[str, list[Family]] = field(default_factory=dict)
    parents_of: dict[str, list[str]] = field(default_factory=dict)
    children_of: dict[str, list[str]] = field(default_factory=dict)
    siblings_of: dict[str, set[str]] = field(default_factory=dict)
    media_by_id: dict[str, MediaItem] = field(default_factory=dict)
    project_folder: Path | None = None
    main_person_id: str | None = None
    current_year: int = 0
    # Computed lazily by structure_checks for connectivity check
    reachable_from_main: set[str] | None = None


def format_person_display(person: Person, events: list[Event]) -> str:
    """Format person display string: 'Förnamn Efternamn (YYYY\u2013YYYY)'.

    Uses the first name entry from person.names (given + surname).
    Birth year from BIRTH event, death year from DEATH event.
    Missing years replaced with '?'. En-dash between years.
    """
    # Name from first entry
    given = ""
    surname = ""
    if person.names:
        given = person.names[0].given
        surname = person.names[0].surname

    # Find birth year
    birth_year: str = "?"
    for event in events:
        if event.type == "birth":
            for participant in event.participants:
                if participant.person_id == person.id:
                    if event.date:
                        parsed = parse_date_value(event.date)
                        if parsed:
                            birth_year = str(parsed.year)
                    break
            if birth_year != "?":
                break

    # Find death year
    death_year: str = "?"
    for event in events:
        if event.type == "death":
            for participant in event.participants:
                if participant.person_id == person.id:
                    if event.date:
                        parsed = parse_date_value(event.date)
                        if parsed:
                            death_year = str(parsed.year)
                    break
            if death_year != "?":
                break

    name_part = f"{given} {surname}".strip()
    return f"{name_part} ({birth_year}\u2013{death_year})"


class PersonCheckEngine:
    """Kontrollmotor som kör alla aktiverade kontroller."""

    def __init__(
        self,
        data: ProjectData,
        config: PersonCheckConfig,
        project_folder: Path | None = None,
    ) -> None:
        self._data = data
        self._config = config
        self._context = self._build_context(data, project_folder)

    def _build_context(
        self, data: ProjectData, project_folder: Path | None
    ) -> CheckContext:
        """Build lookup tables from ProjectData."""
        ctx = CheckContext()

        # persons_by_id
        ctx.persons_by_id = {p.id: p for p in data.persons}

        # events_by_id
        ctx.events_by_id = {e.id: e for e in data.events}

        # events_by_person: person_id -> list of events where person is participant
        events_by_person: dict[str, list[Event]] = defaultdict(list)
        for event in data.events:
            for participant in event.participants:
                events_by_person[participant.person_id].append(event)
        ctx.events_by_person = dict(events_by_person)

        # families_by_person: person_id -> families person appears in
        families_by_person: dict[str, list[Family]] = defaultdict(list)
        for family in data.families:
            for partner in family.partners:
                families_by_person[partner.person_id].append(family)
            for child_id in family.children:
                families_by_person[child_id].append(family)
        ctx.families_by_person = dict(families_by_person)

        # parents_of: child_id -> parent_ids (from ParentChildLink)
        parents_of: dict[str, list[str]] = defaultdict(list)
        for family in data.families:
            for link in family.parent_child_links:
                if link.parent_id:
                    parents_of[link.child_id].append(link.parent_id)
        ctx.parents_of = dict(parents_of)

        # children_of: parent_id -> child_ids (reverse of parents_of)
        children_of: dict[str, list[str]] = defaultdict(list)
        for child_id, parent_ids in ctx.parents_of.items():
            for parent_id in parent_ids:
                children_of[parent_id].append(child_id)
        ctx.children_of = dict(children_of)

        # siblings_of: person_id -> sibling_ids (children sharing same family)
        siblings_of: dict[str, set[str]] = defaultdict(set)
        for family in data.families:
            children = family.children
            for child_id in children:
                for other_id in children:
                    if other_id != child_id:
                        siblings_of[child_id].add(other_id)
        ctx.siblings_of = dict(siblings_of)

        # project_folder and main_person_id
        ctx.project_folder = project_folder
        ctx.main_person_id = data.project.main_person_id
        ctx.current_year = datetime.date.today().year

        # media_by_id
        ctx.media_by_id = {m.id: m for m in data.media}

        return ctx

    def run_checks(
        self, progress_callback: Callable[[int], None] | None = None
    ) -> list[CheckFinding]:
        """Kör alla aktiverade kontroller och returnera fynd."""
        findings: list[CheckFinding] = []
        persons = self._data.persons
        total = len(persons)

        if total == 0:
            return findings

        # Collect findings grouped per person
        for i, person in enumerate(persons):
            person_events = self._context.events_by_person.get(person.id, [])
            person_families = self._context.families_by_person.get(person.id, [])
            person_display = format_person_display(person, person_events)

            person_findings: list[CheckFinding] = []

            # Age checks (controlled by master_enabled)
            if self._config.age_checks.master_enabled:
                person_findings.extend(
                    self._run_age_checks(
                        person, person_events, person_families, person_display
                    )
                )

            # Logic checks — chronology (each controlled by individual flag)
            person_findings.extend(
                self._run_chronology_checks(
                    person, person_events, person_families, person_display
                )
            )

            # Logic checks — structure
            person_findings.extend(
                self._run_structure_checks(
                    person, person_events, person_families, person_display
                )
            )

            # Logic checks — calendar
            person_findings.extend(
                self._run_calendar_checks(
                    person, person_events, person_families, person_display
                )
            )

            findings.extend(person_findings)

            # Report progress
            if progress_callback is not None:
                progress_callback(int((i + 1) / total * 100))

        return findings

    def _run_age_checks(
        self,
        person: Person,
        events: list[Event],
        families: list[Family],
        person_display: str,
    ) -> list[CheckFinding]:
        """Run age checks if the module is available."""
        try:
            from slaktbusken.services.checks.age_checks import check_age

            return check_age(
                person, events, families, self._config, self._context
            )
        except ImportError:
            return []

    def _run_chronology_checks(
        self,
        person: Person,
        events: list[Event],
        families: list[Family],
        person_display: str,
    ) -> list[CheckFinding]:
        """Run chronology checks if the module is available."""
        try:
            from slaktbusken.services.checks.chronology_checks import (
                check_chronology,
            )

            return check_chronology(
                person, events, families, self._config, self._context
            )
        except ImportError:
            return []

    def _run_structure_checks(
        self,
        person: Person,
        events: list[Event],
        families: list[Family],
        person_display: str,
    ) -> list[CheckFinding]:
        """Run structure checks if the module is available."""
        try:
            from slaktbusken.services.checks.structure_checks import (
                check_structure,
            )

            return check_structure(
                person, events, families, self._config, self._context
            )
        except ImportError:
            return []

    def _run_calendar_checks(
        self,
        person: Person,
        events: list[Event],
        families: list[Family],
        person_display: str,
    ) -> list[CheckFinding]:
        """Run calendar checks if the module is available."""
        try:
            from slaktbusken.services.checks.calendar_checks import (
                check_calendar,
            )

            return check_calendar(
                person, events, families, self._config, self._context
            )
        except ImportError:
            return []
