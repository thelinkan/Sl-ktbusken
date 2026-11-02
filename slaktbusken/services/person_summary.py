"""Person summaries (name, lifespan, birth and death text) built in one pass.

Qt-free. ``PersonSummaryIndex.build`` is O(persons + events): it never scans
all events per person.
"""

from __future__ import annotations

from dataclasses import dataclass

from slaktbusken.model.event import DateValue
from slaktbusken.model.project import ProjectData
from slaktbusken.services.checks.date_utils import parse_date_value

UNKNOWN_PERSON = "Okänd person"


@dataclass(frozen=True)
class PersonSummary:
    """Display data for one person."""

    person_id: str
    name: str
    birth_date: str
    birth_place: str
    death_date: str
    death_place: str
    birth_year: str
    death_year: str

    @property
    def lifespan_text(self) -> str:
        """``1829–1890``, ``(1829)``-style variants without parentheses
        handled by :func:`format_lifespan`."""
        return format_lifespan(self.birth_year, self.death_year)

    @property
    def birth_text(self) -> str:
        return _join("f.", self.birth_date, self.birth_place)

    @property
    def death_text(self) -> str:
        return _join("d.", self.death_date, self.death_place)


def format_lifespan(birth_year: str, death_year: str) -> str:
    """Both years ``1829–1890``, birth only ``(1829)``, death only ``(–1890)``;
    neither gives an empty string."""
    if birth_year and death_year:
        return f"{birth_year}\u2013{death_year}"
    if birth_year:
        return f"({birth_year})"
    if death_year:
        return f"(\u2013{death_year})"
    return ""


def _join(prefix: str, date_text: str, place_text: str) -> str:
    body = " ".join(part for part in (date_text, place_text) if part)
    return f"{prefix} {body}" if body else ""


def _year_of(date: DateValue | None) -> str:
    if date is None or not date.value:
        return ""
    parsed = parse_date_value(date)
    return str(parsed.year) if parsed else ""


class PersonSummaryIndex:
    """Read-only summaries for every person, derived on demand.

    ``build`` only indexes the first birth and death event of each person (one
    pass over the events); the :class:`PersonSummary` of a person is formed on
    first access and then kept. The results equal those of forming all
    summaries up front.
    """

    def __init__(
        self,
        summaries: dict[str, PersonSummary] | None = None,
        *,
        _persons: dict[str, object] | None = None,
        _births: dict[str, object] | None = None,
        _deaths: dict[str, object] | None = None,
        _place_names: dict[str, str] | None = None,
    ) -> None:
        self._summaries: dict[str, PersonSummary] = dict(summaries or {})
        # Persons whose summary is formed lazily; empty for the eager form.
        self._persons = _persons or {}
        self._births = _births or {}
        self._deaths = _deaths or {}
        self._place_names = _place_names or {}

    @classmethod
    def build(cls, data: ProjectData) -> "PersonSummaryIndex":
        place_names = {place.id: place.name for place in data.places}
        # First birth/death event per person, in stored event order.
        births: dict[str, object] = {}
        deaths: dict[str, object] = {}
        for event in data.events:
            if event.type == "birth":
                target = births
            elif event.type == "death":
                target = deaths
            else:
                continue
            for participant in event.participants:
                target.setdefault(participant.person_id, event)

        persons = {person.id: person for person in data.persons}
        return cls(
            _persons=persons, _births=births, _deaths=deaths, _place_names=place_names
        )

    def _form(self, person) -> PersonSummary:
        if person.names:
            name = f"{person.names[0].given} {person.names[0].surname}".strip()
        else:
            name = ""
        birth = self._births.get(person.id)
        death = self._deaths.get(person.id)
        place_names = self._place_names
        return PersonSummary(
            person_id=person.id,
            name=name,
            birth_date=_date_text(birth),
            birth_place=_place_text(birth, place_names),
            death_date=_date_text(death),
            death_place=_place_text(death, place_names),
            birth_year=_year_of(birth.date) if birth else "",
            death_year=_year_of(death.date) if death else "",
        )

    def get(self, person_id: str) -> PersonSummary | None:
        summary = self._summaries.get(person_id)
        if summary is None:
            person = self._persons.get(person_id)
            if person is not None:
                summary = self._summaries[person_id] = self._form(person)
        return summary

    def __contains__(self, person_id: str) -> bool:
        return person_id in self._summaries or person_id in self._persons

    def __iter__(self):
        ids = list(self._persons)
        ids += [pid for pid in self._summaries if pid not in self._persons]
        return iter([self.get(pid) for pid in ids])

    def __len__(self) -> int:
        return len(self._persons) + sum(
            1 for pid in self._summaries if pid not in self._persons
        )
    def name(self, person_id: str) -> str:
        summary = self.get(person_id)
        return summary.name if summary and summary.name else (
            person_id if summary else UNKNOWN_PERSON
        )

    def lifespan_text(self, person_id: str) -> str:
        summary = self.get(person_id)
        return summary.lifespan_text if summary else ""

    def birth_text(self, person_id: str) -> str:
        summary = self.get(person_id)
        return summary.birth_text if summary else ""

    def death_text(self, person_id: str) -> str:
        summary = self.get(person_id)
        return summary.death_text if summary else ""


def _date_text(event) -> str:
    if event is None or event.date is None:
        return ""
    return event.date.value or ""


def _place_text(event, place_names: dict[str, str]) -> str:
    if event is None or event.place is None:
        return ""
    return place_names.get(event.place.place_id, event.place.place_id)
