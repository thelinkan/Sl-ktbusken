"""Comparison session behind the Person_Comparison_Window (Qt-free).

All behaviour with a requirement lives here so it can be tested without Qt:
slot contents, swap, assignment, the navigation stack, per-view selection,
pair-action enablement, Shared_Person ids, comparison rows and the
"Fortsätt till sammanslagning" enablement.

Two persons are the same person only when their ids are identical. There is no
similarity logic in this module: nothing is matched, ranked or suggested by
name, date, place or family position.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Optional, Sequence

from slaktbusken.model.event import DateValue, Event
from slaktbusken.model.merge_candidate import MergeCandidate
from slaktbusken.model.person import Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.candidate_index import CandidateIndex

MAX_DEPTH = 20

SELF_COMPARE_MESSAGE = "En person kan inte jämföras med sig själv."
SAME_PAIR_MESSAGE = "Samma registrerade person kan inte vara kandidat till sig själv."
DEPTH_REACHED_MESSAGE = (
    "Det största antalet nivåer av deljämförelser (20) är uppnått."
)

STATUS_NONE = "none"
STATUS_EQUAL = "equal"
STATUS_DIFFERS = "differs"
STATUS_MISSING_LEFT = "missing_left"
STATUS_MISSING_RIGHT = "missing_right"

STATUS_LABELS = {
    STATUS_DIFFERS: "Avviker",
    STATUS_MISSING_LEFT: "Saknas",
    STATUS_MISSING_RIGHT: "Saknas",
}

IDENTITY_EVENT_TYPES = (
    "birth",
    "baptism",
    "christening",
    "death",
    "burial",
    "marriage",
    "divorce",
    "adoption",
    "foster_home",
)

EVENT_LABELS = {
    "birth": "Födelse",
    "baptism": "Dop",
    "christening": "Dop",
    "death": "Död",
    "burial": "Begravning",
    "marriage": "Vigsel",
    "divorce": "Skilsmässa",
    "adoption": "Adoption",
    "foster_home": "Fosterhem",
}

SHARED_PERSON_TOOLTIP = "Samma registrerade person i båda familjevyerna"
LEGEND_TEXT = (
    "Avviker är en observation att väga in och är inget bevis för att "
    "personerna är olika individer."
)


# --------------------------------------------------------------------------
# Value objects


@dataclass(frozen=True)
class ViewContext:
    """One navigation-stack entry (Requirement 14.1)."""

    slot_persons: tuple[Optional[str], Optional[str]]
    focus: tuple[Optional[str], Optional[str]]
    expansion: tuple[frozenset[str], frozenset[str]]
    zoom: tuple[float, float]
    selection: tuple[Optional[str], Optional[str]]


class PushResult(Enum):
    PUSHED = "pushed"
    DEPTH_REACHED = "depth_reached"
    NOT_ALLOWED = "not_allowed"


@dataclass(frozen=True)
class SetSlotResult:
    ok: bool
    message: str = ""


@dataclass(frozen=True)
class PairActionState:
    """State of "Markera som kandidater" and "Jämför dessa"."""

    enabled: bool
    left_id: Optional[str] = None
    right_id: Optional[str] = None
    reason: str = ""


@dataclass(frozen=True)
class ComparisonRow:
    key: str
    label: str
    left: tuple[str, ...]
    right: tuple[str, ...]
    status: str = STATUS_NONE
    left_source_ids: tuple[str, ...] = ()
    right_source_ids: tuple[str, ...] = ()

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, "")


@dataclass(frozen=True)
class MenuState:
    """Enablement of the person-list context-menu entries."""

    compare_enabled: bool
    mark_candidates_enabled: bool


# --------------------------------------------------------------------------
# Person-list helpers (Requirements 8.4 to 8.7, 9.1)


def menu_state(selected_count: int) -> MenuState:
    """"Jämför personer..." for one or two rows, candidates for exactly two."""
    return MenuState(
        compare_enabled=selected_count in (1, 2),
        mark_candidates_enabled=selected_count == 2,
    )


def order_by_person_list(
    selected_ids: Iterable[str], list_order: Sequence[str]
) -> list[str]:
    """Selected ids in the order they appear in the person list.

    Duplicates are dropped; ids not in the list keep their given order after
    the listed ones, so the same selection always yields the same order.
    """
    position = {pid: i for i, pid in enumerate(list_order)}
    unique = list(dict.fromkeys(selected_ids))
    listed = sorted((p for p in unique if p in position), key=position.__getitem__)
    return listed + [p for p in unique if p not in position]


def slots_for_selection(
    selected_ids: Iterable[str], list_order: Sequence[str]
) -> tuple[Optional[str], Optional[str]]:
    """Slot contents when opening from the person list (9.1 to 9.3)."""
    ordered = order_by_person_list(selected_ids, list_order)
    if len(ordered) == 2:
        return (ordered[0], ordered[1])
    if len(ordered) == 1:
        return (ordered[0], None)
    return (None, None)


# --------------------------------------------------------------------------
# Session


@dataclass
class _ViewState:
    focus: Optional[str] = None
    expansion: frozenset[str] = frozenset()
    zoom: float = 1.0
    selection: Optional[str] = None


@dataclass
class ComparisonSession:
    """State of one comparison window."""

    MAX_DEPTH = MAX_DEPTH

    slots: list[Optional[str]] = field(default_factory=lambda: [None, None])
    _views: list[_ViewState] = field(
        default_factory=lambda: [_ViewState(), _ViewState()]
    )
    _stack: list[ViewContext] = field(default_factory=list)

    # -- construction ------------------------------------------------------

    @classmethod
    def from_selection(
        cls, selected_ids: Iterable[str], list_order: Sequence[str]
    ) -> "ComparisonSession":
        session = cls()
        left, right = slots_for_selection(selected_ids, list_order)
        session.slots = [left, right]
        session._reset_view(0)
        session._reset_view(1)
        return session

    @classmethod
    def from_pair(cls, left: Optional[str], right: Optional[str]) -> "ComparisonSession":
        session = cls()
        if left is not None and left == right:
            right = None
        session.slots = [left, right]
        session._reset_view(0)
        session._reset_view(1)
        return session

    # -- slots -------------------------------------------------------------

    def slot_persons(self) -> tuple[Optional[str], Optional[str]]:
        return (self.slots[0], self.slots[1])

    def _reset_view(self, view: int) -> None:
        old = self._views[view]
        self._views[view] = _ViewState(focus=self.slots[view], zoom=old.zoom)

    def set_slot(self, slot: int, person_id: Optional[str]) -> SetSlotResult:
        """Assign ``person_id`` (or clear with ``None``); rejects the person
        the other slot holds and keeps the previous content (9.10)."""
        _check_index(slot)
        if person_id is not None and person_id == self.slots[1 - slot]:
            return SetSlotResult(False, SELF_COMPARE_MESSAGE)
        self.slots[slot] = person_id
        self._reset_view(slot)
        return SetSlotResult(True)

    def swap(self) -> None:
        """Swap the slot persons, also when one slot is empty (9.6)."""
        self.slots.reverse()
        zooms = (self._views[0].zoom, self._views[1].zoom)
        self._views[0] = _ViewState(focus=self.slots[0], zoom=zooms[1])
        self._views[1] = _ViewState(focus=self.slots[1], zoom=zooms[0])

    def clear_missing(self, existing_ids: set[str]) -> list[int]:
        """Clear slots whose person no longer exists (10.14); returns them."""
        cleared = []
        for slot in (0, 1):
            pid = self.slots[slot]
            if pid is not None and pid not in existing_ids:
                self.slots[slot] = None
                self._reset_view(slot)
                cleared.append(slot)
        return cleared

    # -- per-view state ----------------------------------------------------

    def select(self, view: int, person_id: Optional[str]) -> None:
        """Select one person per view, replacing any previous one (13.1)."""
        _check_index(view)
        self._views[view].selection = person_id

    def selection(self, view: int) -> Optional[str]:
        _check_index(view)
        return self._views[view].selection

    def selections(self) -> tuple[Optional[str], Optional[str]]:
        return (self._views[0].selection, self._views[1].selection)

    def focus(self, view: int) -> Optional[str]:
        _check_index(view)
        return self._views[view].focus

    def set_focus(self, view: int, person_id: Optional[str]) -> None:
        """Navigate within a view; the slot person stays unchanged (10.9)."""
        _check_index(view)
        self._views[view].focus = person_id

    def expansion(self, view: int) -> frozenset[str]:
        _check_index(view)
        return self._views[view].expansion

    def set_expansion(self, view: int, person_ids: Iterable[str]) -> None:
        _check_index(view)
        self._views[view].expansion = frozenset(person_ids)

    def zoom(self, view: int) -> float:
        _check_index(view)
        return self._views[view].zoom

    def set_zoom(self, view: int, zoom: float) -> None:
        _check_index(view)
        self._views[view].zoom = zoom

    # -- pair actions ------------------------------------------------------

    def pair_action_state(self) -> PairActionState:
        left, right = self.selections()
        if left is None or right is None:
            return PairActionState(False, left, right)
        if left == right:
            return PairActionState(False, left, right, SAME_PAIR_MESSAGE)
        return PairActionState(True, left, right)

    # -- navigation stack --------------------------------------------------

    def context(self) -> ViewContext:
        return ViewContext(
            slot_persons=self.slot_persons(),
            focus=(self._views[0].focus, self._views[1].focus),
            expansion=(self._views[0].expansion, self._views[1].expansion),
            zoom=(self._views[0].zoom, self._views[1].zoom),
            selection=self.selections(),
        )

    def restore(self, ctx: ViewContext) -> None:
        self.slots = [ctx.slot_persons[0], ctx.slot_persons[1]]
        self._views = [
            _ViewState(ctx.focus[i], ctx.expansion[i], ctx.zoom[i], ctx.selection[i])
            for i in (0, 1)
        ]

    @property
    def depth(self) -> int:
        return len(self._stack)

    def can_go_back(self) -> bool:
        return bool(self._stack)

    def compare_selected(self) -> PushResult:
        """"Jämför dessa": push the context and show the selected pair (14.1).

        At 20 entries nothing changes (14.10).
        """
        state = self.pair_action_state()
        if not state.enabled:
            return PushResult.NOT_ALLOWED
        if len(self._stack) >= MAX_DEPTH:
            return PushResult.DEPTH_REACHED
        self._stack.append(self.context())
        zooms = (self._views[0].zoom, self._views[1].zoom)
        self.slots = [state.left_id, state.right_id]
        self._views = [
            _ViewState(focus=self.slots[0], zoom=zooms[0]),
            _ViewState(focus=self.slots[1], zoom=zooms[1]),
        ]
        return PushResult.PUSHED

    def back(self) -> bool:
        """Pop exactly one entry and restore it exactly (14.4)."""
        if not self._stack:
            return False
        self.restore(self._stack.pop())
        return True

    # -- shared persons and candidate relation -----------------------------

    @staticmethod
    def shared_person_ids(
        left_visible: Iterable[str], right_visible: Iterable[str]
    ) -> set[str]:
        """Ids visible in both views: identical ids only (12.1, 12.7, 33.3)."""
        return set(left_visible) & set(right_visible)

    @staticmethod
    def candidate_relation(
        left_id: Optional[str], right_id: Optional[str], index: CandidateIndex
    ) -> Optional[MergeCandidate]:
        """Saved candidate of an unordered pair of different ids, else None
        (12.3, 12.5, 12.6)."""
        if left_id is None or right_id is None or left_id == right_id:
            return None
        return index.candidate_for_pair(left_id, right_id)

    def current_candidate(self, index: CandidateIndex) -> Optional[MergeCandidate]:
        """Candidate of the current slot pair; always re-read, never carried
        over from a previous pair (9.12)."""
        return self.candidate_relation(self.slots[0], self.slots[1], index)

    def candidate_for_selected_pair(
        self, index: CandidateIndex
    ) -> Optional[MergeCandidate]:
        left, right = self.selections()
        return self.candidate_relation(left, right, index)

    # -- merge entry -------------------------------------------------------

    def can_continue_to_merge(self) -> bool:
        """Enabled only for two different persons (20.2, 20.3)."""
        left, right = self.slots
        return left is not None and right is not None and left != right

    # -- comparison table --------------------------------------------------

    def rows(self, data: ProjectData) -> list[ComparisonRow]:
        return build_rows(data, self.slots[0], self.slots[1])


def _check_index(i: int) -> None:
    if i not in (0, 1):
        raise ValueError("slot/view index must be 0 or 1")


# --------------------------------------------------------------------------
# Comparison rows (Requirement 11)


def _norm(text: Optional[str]) -> str:
    return (text or "").strip().casefold()


def _display(text: Optional[str]) -> str:
    return (text or "").strip()


@dataclass(frozen=True)
class _Item:
    """One value: comparison key, display text and source ids."""

    key: tuple
    text: str
    sources: tuple[str, ...] = ()


def _date_sources(date: Optional[DateValue]) -> tuple[str, ...]:
    if date is None:
        return ()
    return tuple(ref.source_id for ref in date.source_refs)


def _date_place_item(
    date: Optional[DateValue],
    place_id: Optional[str],
    place_names: dict[str, str],
    place_refs: Sequence = (),
) -> Optional[_Item]:
    date_value = _display(date.value) if date else ""
    precision = _norm(date.precision) if date and date_value else ""
    place_text = ""
    if place_id:
        place_text = _display(place_names.get(place_id, place_id))
    if not date_value and not place_text:
        return None
    text = " ".join(part for part in (date_value, place_text) if part)
    sources = _date_sources(date) + tuple(r.source_id for r in place_refs)
    return _Item(("dp", _norm(date_value), precision, _norm(place_text)), text, sources)


def _text_items(value: Optional[str]) -> list[_Item]:
    text = _display(value)
    return [_Item(("t", _norm(text)), text)] if text else []


def _name_text(name) -> str:
    return f"{_display(name.given)} {_display(name.surname)}".strip()


def _person_events(data: ProjectData, person_id: Optional[str]) -> dict[str, list[Event]]:
    by_type: dict[str, list[Event]] = {}
    if person_id is None:
        return by_type
    for event in data.events:
        if any(p.person_id == person_id for p in event.participants):
            by_type.setdefault(event.type, []).append(event)
    return by_type


def _event_items(events: Sequence[Event], place_names: dict[str, str]) -> list[_Item]:
    items = []
    for event in events:
        item = _date_place_item(
            event.date,
            event.place.place_id if event.place else None,
            place_names,
            event.place.source_refs if event.place else (),
        )
        if item is not None:
            items.append(item)
    return items


def _span_text(endpoint) -> str:
    parts = [_display(endpoint.earliest), _display(endpoint.latest)]
    if not any(parts):
        return ""
    return "\u2013".join(parts)


def _residence_items(
    data: ProjectData, person_id: Optional[str], place_names: dict[str, str]
) -> list[_Item]:
    items = []
    if person_id is None:
        return items
    for fact in data.residences:
        if fact.person_id != person_id:
            continue
        place = _display(place_names.get(fact.place_id, fact.place_id))
        start, end = _span_text(fact.start), _span_text(fact.end)
        if not (place or start or end):
            continue
        text = " ".join(
            part
            for part in (
                place,
                f"från {start}" if start else "",
                f"till {end}" if end else "",
            )
            if part
        )
        sources = tuple(o.source_ref.source_id for o in fact.observations)
        items.append(
            _Item(
                (
                    "res",
                    _norm(place),
                    _norm(fact.start.earliest),
                    _norm(fact.start.latest),
                    _norm(fact.end.earliest),
                    _norm(fact.end.latest),
                ),
                text,
                sources,
            )
        )
    return items


def _dna_items(data: ProjectData, person_id: Optional[str]) -> list[_Item]:
    items = []
    if person_id is None:
        return items
    companies = {c.id: c.name for c in data.dna_companies}
    for profile in data.dna_profiles:
        if profile.person_id != person_id:
            continue
        company = _display(companies.get(profile.company_id, profile.company_id))
        test_type = _display(profile.test_type)
        kit_id = _display(profile.kit_id)
        if not (company or test_type or kit_id):
            continue
        text = ", ".join(part for part in (company, test_type, kit_id) if part)
        items.append(_Item(("dna", _norm(company), _norm(test_type), _norm(kit_id)), text))
    return items


def _classify(
    left: Sequence[_Item], right: Sequence[_Item], both_filled: bool
) -> str:
    if not both_filled:
        return STATUS_NONE
    if left and right:
        left_keys = {i.key for i in left}
        right_keys = {i.key for i in right}
        return STATUS_EQUAL if left_keys == right_keys else STATUS_DIFFERS
    if left:
        return STATUS_MISSING_RIGHT
    if right:
        return STATUS_MISSING_LEFT
    return STATUS_EQUAL


def _row(
    key: str,
    label: str,
    left: Sequence[_Item],
    right: Sequence[_Item],
    both_filled: bool,
) -> ComparisonRow:
    def texts(items: Sequence[_Item]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(i.text for i in items))

    def sources(items: Sequence[_Item]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(s for i in items for s in i.sources))

    return ComparisonRow(
        key=key,
        label=label,
        left=texts(left),
        right=texts(right),
        status=_classify(left, right, both_filled),
        left_source_ids=sources(left),
        right_source_ids=sources(right),
    )


def build_rows(
    data: ProjectData, left_id: Optional[str], right_id: Optional[str]
) -> list[ComparisonRow]:
    """Resolve all comparison rows from project data at call time (11.2).

    With an empty slot the populated column is shown and no row carries a mark
    (11.9). Values are never stored by the caller as authoritative copies.
    """
    persons = {p.id: p for p in data.persons}
    left = persons.get(left_id) if left_id else None
    right = persons.get(right_id) if right_id else None
    both = left is not None and right is not None
    place_names = {p.id: p.name for p in data.places}
    media_titles = {m.id: getattr(m, "title", "") for m in data.media}

    def person_rows(extract) -> tuple[list[_Item], list[_Item]]:
        return (
            extract(left) if left is not None else [],
            extract(right) if right is not None else [],
        )

    def primary_name(p: Person) -> list[_Item]:
        if not p.names:
            return []
        text = _name_text(p.names[0])
        return [_Item(("t", _norm(text)), text)] if text else []

    def other_names(p: Person) -> list[_Item]:
        items = []
        for name in p.names[1:]:
            text = _name_text(name)
            if text:
                items.append(_Item(("t", _norm(text)), text))
        return items

    def profile_photo(p: Person) -> list[_Item]:
        media_id = _display(p.profile_media_id)
        if not media_id:
            return []
        title = _display(media_titles.get(media_id)) or media_id
        return [_Item(("media", media_id), title)]

    rows: list[ComparisonRow] = []

    def add(key: str, label: str, extract) -> None:
        li, ri = person_rows(extract)
        rows.append(_row(key, label, li, ri, both))

    add("name", "Namn", primary_name)
    add("alt_names", "Alternativa namn", other_names)
    add("sex", "Kön", lambda p: _text_items(p.sex))

    left_events = _person_events(data, left_id if left else None)
    right_events = _person_events(data, right_id if right else None)

    def event_row(key: str, label: str, etype: str) -> None:
        rows.append(
            _row(
                key,
                label,
                _event_items(left_events.get(etype, ()), place_names),
                _event_items(right_events.get(etype, ()), place_names),
                both,
            )
        )

    event_row("birth", "Födelse", "birth")
    event_row("death", "Död", "death")
    add("occupation", "Yrke", lambda p: _text_items(p.occupation))
    add("title", "Titel", lambda p: _text_items(p.title))
    add("notes", "Anteckningar", lambda p: _text_items(p.notes))
    add("profile_photo", "Profilfoto", profile_photo)

    for etype in IDENTITY_EVENT_TYPES:
        if etype in ("birth", "death"):
            continue
        if etype in left_events or etype in right_events:
            event_row(f"event:{etype}", EVENT_LABELS[etype], etype)

    rows.append(
        _row(
            "residences",
            "Boenden",
            _residence_items(data, left_id if left else None, place_names),
            _residence_items(data, right_id if right else None, place_names),
            both,
        )
    )
    rows.append(
        _row(
            "dna",
            "DNA-profiler",
            _dna_items(data, left_id if left else None),
            _dna_items(data, right_id if right else None),
            both,
        )
    )
    return rows
