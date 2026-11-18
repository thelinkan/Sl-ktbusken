"""Pure, Qt-free assembly of an ``Event`` from the state of the event form.

``assemble_event`` works on a deep copy of the loaded event and overwrites only
the fields the form controls, so ``origin`` and any future field pass through a
save untouched. ``prompts_needed`` decides which questions the editor must ask
before citations attached to a date, place or from-place are detached.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping, Optional

from slaktbusken.model.date_semantics import effective_qualifier, validate_date_value
from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef, SourceRef
from slaktbusken.model.event_citations import (
    CitationContext,
    event_citations,
    identical_reference,
)


@dataclass
class CitationRow:
    """One row of the Källor table: a reference and what it applies to."""

    context: CitationContext
    ref: SourceRef


@dataclass
class DateFormState:
    """The date fields of the form. ``text`` is the ISO value (or empty)."""

    text: str = ""
    qualifier: str = "exact"
    value_to: Optional[str] = None
    calendar: str = "gregorian"

    @classmethod
    def from_date(cls, date: Optional[DateValue]) -> "DateFormState":
        """The form state that shows ``date`` as loaded."""
        if date is None:
            return cls()
        return cls(
            text=date.value or "",
            qualifier=effective_qualifier(date),
            value_to=date.value_to,
            calendar=date.calendar,
        )

    def _key(self) -> tuple:
        return (
            (self.text or "").strip(),
            self.qualifier,
            (self.value_to or "").strip(),
            self.calendar,
        )

    def same_as(self, other: "DateFormState") -> bool:
        return self._key() == other._key()


@dataclass
class EventFormState:
    type: str
    custom_type_name: Optional[str] = None
    cause_of_death: Optional[str] = None
    date: DateFormState = field(default_factory=DateFormState)
    place_id: Optional[str] = None
    from_place_id: Optional[str] = None
    citation_rows: list[CitationRow] = field(default_factory=list)
    participants: list[Participant] = field(default_factory=list)
    media_ids: list[str] = field(default_factory=list)


class CitationChoice(Enum):
    KEEP_FOR_NEW_PLACE = "keep_for_new_place"
    MOVE_TO_EVENT = "move_to_event"
    REMOVE_LINKS = "remove_links"
    CANCEL = "cancel"


DEFAULT_CHOICE = CitationChoice.MOVE_TO_EVENT

_REMOVED_CHOICES = (
    CitationChoice.MOVE_TO_EVENT,
    CitationChoice.REMOVE_LINKS,
    CitationChoice.CANCEL,
)
_CHANGED_CHOICES = (
    CitationChoice.KEEP_FOR_NEW_PLACE,
    CitationChoice.MOVE_TO_EVENT,
    CitationChoice.REMOVE_LINKS,
    CitationChoice.CANCEL,
)

CHOICE_LABELS_SV = {
    CitationChoice.KEEP_FOR_NEW_PLACE: "Behåll för nya platsen",
    CitationChoice.MOVE_TO_EVENT: "Flytta till händelsen",
    CitationChoice.REMOVE_LINKS: "Ta bort källhänvisningarna",
    CitationChoice.CANCEL: "Avbryt",
}

_CHANGED_INFO_SV = (
    "Att flytta dem till händelsen bevarar beläggen utan att påstå "
    "att de stöder den nya platsen."
)


@dataclass(frozen=True)
class PromptNeed:
    context: CitationContext  # DATE, PLACE or FROM_PLACE
    kind: str  # "removed" or "changed"
    count: int  # rows affected
    allowed: tuple[CitationChoice, ...]


def prompt_text_sv(need: PromptNeed) -> tuple[str, str]:
    """Return ``(message, informative_text)`` in Swedish for ``need``."""
    n = need.count
    ctx = need.context
    if ctx == CitationContext.DATE:
        return (f"Datumet har {n} källhänvisning(ar). Vad vill du göra med dem?", "")
    name = "Från-platsen" if ctx == CitationContext.FROM_PLACE else "Platsen"
    if need.kind == "removed":
        what = "från-platsen" if ctx == CitationContext.FROM_PLACE else "platsen"
        return (
            f"{name} har {n} källhänvisning(ar) och {what} tas bort. "
            "Vad vill du göra med dem?",
            "",
        )
    return (
        f"{name} byts ut och den gamla {name[0].lower() + name[1:]} har {n} "
        "källhänvisning(ar). Vad vill du göra med dem?",
        _CHANGED_INFO_SV,
    )


def _loaded_place_id(base: Optional[Event], context: CitationContext) -> Optional[str]:
    if base is None:
        return None
    ref = base.place if context == CitationContext.PLACE else base.from_place
    return ref.place_id if ref is not None else None


def _rows(form: EventFormState, context: CitationContext) -> list[CitationRow]:
    return [r for r in form.citation_rows if r.context == context]


def _date_unchanged(base: Optional[Event], form: EventFormState) -> bool:
    """True when ``base`` has a date and the form shows exactly its values."""
    if base is None or base.date is None:
        return False
    return form.date.same_as(DateFormState.from_date(base.date))


def _date_present(base: Optional[Event], form: EventFormState) -> bool:
    return _date_unchanged(base, form) or bool((form.date.text or "").strip()) or (
        form.date.qualifier == "unparsed"
    )


def prompts_needed(base: Optional[Event], form: EventFormState) -> list[PromptNeed]:
    """Questions to ask, in the order date, place, from-place."""
    needs: list[PromptNeed] = []

    date_rows = _rows(form, CitationContext.DATE)
    if date_rows and not _date_present(base, form):
        needs.append(
            PromptNeed(CitationContext.DATE, "removed", len(date_rows), _REMOVED_CHOICES)
        )

    for context, selected in (
        (CitationContext.PLACE, form.place_id),
        (CitationContext.FROM_PLACE, form.from_place_id),
    ):
        rows = _rows(form, context)
        if not rows:
            continue
        if not selected:
            needs.append(PromptNeed(context, "removed", len(rows), _REMOVED_CHOICES))
            continue
        loaded = _loaded_place_id(base, context)
        if loaded is not None and loaded != selected:
            needs.append(PromptNeed(context, "changed", len(rows), _CHANGED_CHOICES))
    return needs


def append_moved(target: list[SourceRef], moved: Iterable[SourceRef]) -> list[SourceRef]:
    """Append each ``moved`` reference to ``target`` unless an identical one is there.

    Only identity of source id, quality, note and aspects is deduplicated, and
    only against what is already in ``target`` (including earlier appends of
    this call). Existing references keep their order and multiplicity.
    """
    for ref in moved:
        if not any(identical_reference(ref, existing) for existing in target):
            target.append(ref)
    return target


def _derived_precision(text: str, qualifier: str) -> str:
    if qualifier != "exact":
        return "approximate"
    n = len(text)
    return "year" if n <= 4 else "month" if n <= 7 else "day"


def build_date(form_date: DateFormState, source_refs: list[SourceRef]) -> DateValue:
    """A new ``DateValue`` from the form (``original_text`` is ``None``)."""
    text = (form_date.text or "").strip()
    value_to = (form_date.value_to or "").strip() or None
    return DateValue(
        value=text,
        precision=_derived_precision(text, form_date.qualifier),
        source_refs=source_refs,
        qualifier=form_date.qualifier,
        value_to=value_to,
        calendar=form_date.calendar,
        original_text=None,
    )


def validate_date_form(form_date: DateFormState) -> list[str]:
    """Swedish errors for a changed, non-empty form date; empty list if valid."""
    if not (form_date.text or "").strip() and form_date.qualifier != "unparsed":
        return []
    return validate_date_value(build_date(form_date, []))


def assemble_event(
    base: Optional[Event],
    form: EventFormState,
    choices: Mapping[CitationContext, CitationChoice],
) -> Event:
    """Build the event to save.

    Raises ``ValueError`` for a changed date that is invalid or when a choice is
    ``CANCEL`` (the caller must not assemble then). A missing choice for a
    context that needs one defaults to ``MOVE_TO_EVENT``, which loses nothing.
    """
    needs = {n.context: n for n in prompts_needed(base, form)}

    def choice_for(context: CitationContext) -> Optional[CitationChoice]:
        if context not in needs:
            return None
        choice = choices.get(context, DEFAULT_CHOICE)
        if choice == CitationChoice.CANCEL:
            raise ValueError("Avbrutet: inga ändringar ska sparas.")
        if choice not in needs[context].allowed:
            raise ValueError(f"Ogiltigt val {choice.value} för {context.value}.")
        return choice

    event = copy.deepcopy(base) if base is not None else Event(
        id=str(uuid.uuid4()), type=form.type, participants=[]
    )

    event.type = form.type
    event.custom_type_name = form.custom_type_name
    event.cause_of_death = form.cause_of_death
    event.participants = copy.deepcopy(form.participants)
    event.media_ids = list(form.media_ids)

    def refs(context: CitationContext) -> list[SourceRef]:
        return [copy.deepcopy(r.ref) for r in _rows(form, context)]

    event_refs = refs(CitationContext.EVENT)
    moved: list[SourceRef] = []

    # Date
    date_rows = refs(CitationContext.DATE)
    if _date_unchanged(base, form):
        assert event.date is not None
        event.date.source_refs = date_rows
    elif _date_present(base, form):
        errors = validate_date_form(form.date)
        if errors:
            raise ValueError("; ".join(errors))
        event.date = build_date(form.date, date_rows)
    else:
        event.date = None
        if choice_for(CitationContext.DATE) == CitationChoice.MOVE_TO_EVENT:
            moved.extend(date_rows)

    # Place and from-place
    for context, selected, attr in (
        (CitationContext.PLACE, form.place_id, "place"),
        (CitationContext.FROM_PLACE, form.from_place_id, "from_place"),
    ):
        rows = refs(context)
        choice = choice_for(context)
        current: Optional[PlaceRef] = getattr(event, attr)
        if not selected:
            setattr(event, attr, None)
            if choice == CitationChoice.MOVE_TO_EVENT:
                moved.extend(rows)
            continue
        if current is not None and current.place_id == selected:
            current.source_refs = rows
        else:
            keep = choice in (None, CitationChoice.KEEP_FOR_NEW_PLACE)
            setattr(event, attr, PlaceRef(place_id=selected, source_refs=rows if keep else []))
            if choice == CitationChoice.MOVE_TO_EVENT:
                moved.extend(rows)

    event.source_refs = append_moved(event_refs, moved)
    return event
