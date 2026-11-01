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
    """Read-only summaries for every person, derived on demand."""

    def __init__(self, summaries: dict[str, PersonSummary]) -> None:
        self._summaries = summaries

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

        summaries: dict[str, PersonSummary] = {}
        for person in data.persons:
            if person.names:
                name = f"{person.names[0].given} {person.names[0].surname}".strip()
            else:
                name = ""
            birth = births.get(person.id)
            death = deaths.get(person.id)
            summaries[person.id] = PersonSummary(
                person_id=person.id,
                name=name,
                birth_date=_date_text(birth),
                birth_place=_place_text(birth, place_names),
                death_date=_date_text(death),
                death_place=_place_text(death, place_names),
                birth_year=_year_of(birth.date) if birth else "",
                death_year=_year_of(death.date) if death else "",
            )
        return cls(summaries)

    def get(self, person_id: str) -> PersonSummary | None:
        return self._summaries.get(person_id)

    def __contains__(self, person_id: str) -> bool:
        return person_id in self._summaries

    def __iter__(self):
        return iter(self._summaries.values())

    def __len__(self) -> int:
        return len(self._summaries)

    def name(self, person_id: str) -> str:
        summary = self._summaries.get(person_id)
        return summary.name if summary and summary.name else (
            person_id if summary else UNKNOWN_PERSON
        )

    def lifespan_text(self, person_id: str) -> str:
        summary = self._summaries.get(person_id)
        return summary.lifespan_text if summary else ""

    def birth_text(self, person_id: str) -> str:
        summary = self._summaries.get(person_id)
        return summary.birth_text if summary else ""

    def death_text(self, person_id: str) -> str:
        summary = self._summaries.get(person_id)
        return summary.death_text if summary else ""


def _date_text(event) -> str:
    if event is None or event.date is None:
        return ""
    return event.date.value or ""


def _place_text(event, place_names: dict[str, str]) -> str:
    if event is None or event.place is None:
        return ""
    return place_names.get(event.place.place_id, event.place.place_id)
