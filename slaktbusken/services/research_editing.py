"""Pure editing operations on a research case working copy.

The case editor changes a ``ResearchCaseWorkingCopy`` and nothing else while it
is open. The rules for doing so (completing and reopening actions, ordering,
primary entity handling, the closing warning) live here, without Qt, so they can
be tested directly and the widget stays a thin layer over them.

Nothing here touches ``ProjectData`` except to read it: ids for new items are
issued by :class:`WorkingCopyIdAllocator`, which keeps its counters locally, so
cancelling the editor leaves the project, including its id high-water marks,
exactly as it was.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

from slaktbusken.model.project import ProjectData
from slaktbusken.model.research_case import (
    HypothesisComment,
    ResearchAction,
    ResearchCase,
    ResearchEntityLink,
    ResearchHypothesis,
    is_pending,
    normalize_completed_date,
)
from slaktbusken.services.research_service import (
    ResearchCaseWorkingCopy,
    live_research_ids,
    remove_entity_association,
    research_id_prefix,
)

_ID_SUFFIX = re.compile(r"^(.*?)(\d+)$")


def today_iso() -> str:
    """Return today's local date as ÅÅÅÅ-MM-DD."""
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# Ids
# ---------------------------------------------------------------------------


class WorkingCopyIdAllocator:
    """Issues ids for new items in a working copy without touching the project.

    An id is greater than every live id of its kind in the project, than the
    stored high-water mark, than every id already in the working copy, and than
    every id this allocator issued before, so it never collides and a previously
    deleted id is not handed out again. The counters are kept here only.
    """

    def __init__(self, data: ProjectData, working_copy: ResearchCaseWorkingCopy) -> None:
        self._data = data
        self._working_copy = working_copy
        self._issued: dict[str, int] = {}

    def _highest(self, prefix: str, ids: set[str]) -> int:
        highest = 0
        for used in ids:
            match = re.fullmatch(rf"{re.escape(prefix)}(\d+)", used)
            if match:
                highest = max(highest, int(match.group(1)))
        return highest

    def _working_copy_ids(self, prefix: str) -> set[str]:
        wc = self._working_copy
        if prefix == research_id_prefix("research_case"):
            return {wc.case.id}
        if prefix == research_id_prefix("research_hypothesis"):
            return {h.id for h in wc.hypotheses}
        if prefix == research_id_prefix("research_action"):
            return {a.id for a in wc.actions}
        return {c.id for h in wc.hypotheses for c in h.comments}

    def generate(self, entity_type: str) -> str:
        """Return a new id for a research entity type."""
        prefix = research_id_prefix(entity_type)
        highest = max(
            self._highest(prefix, live_research_ids(self._data)[prefix]),
            self._highest(prefix, self._working_copy_ids(prefix)),
            self._data.id_high_water_marks.get(prefix, 0),
            self._issued.get(prefix, 0),
        )
        self._issued[prefix] = highest + 1
        return f"{prefix}{highest + 1}"


def new_case_working_copy(
    data: ProjectData, primary: Optional[ResearchEntityLink] = None
) -> ResearchCaseWorkingCopy:
    """Return a working copy holding one new, empty case.

    The case id is chosen from the project's counters without advancing them.
    *primary* optionally prepopulates the case's primary entity.
    """
    working_copy = ResearchCaseWorkingCopy(case=ResearchCase(id=""))
    allocator = WorkingCopyIdAllocator(data, working_copy)
    working_copy.case.id = allocator.generate("research_case")
    if primary is not None:
        working_copy.case.primary_entity_ref = ResearchEntityLink(
            primary.entity_type, primary.entity_id, primary.role
        )
    return working_copy


# ---------------------------------------------------------------------------
# Actions: order, completion
# ---------------------------------------------------------------------------


def _id_key(identifier: str) -> tuple[str, int, str]:
    """Order ids by prefix then number, so ``action_2`` comes before ``action_10``."""
    match = _ID_SUFFIX.match(identifier)
    if match:
        return (match.group(1), int(match.group(2)), identifier)
    return (identifier, 0, identifier)


def date_sort_value(value: Optional[str]) -> str:
    """Return a full ÅÅÅÅ-MM-DD for comparison, using the first day of a coarser value."""
    if not value:
        return ""
    parts = value.split("-")
    year = parts[0]
    month = parts[1] if len(parts) > 1 else "01"
    day = parts[2] if len(parts) > 2 else "01"
    return f"{year}-{month}-{day}"


def pending_actions(actions: list[ResearchAction]) -> list[ResearchAction]:
    """Return the pending actions by ``sort_order`` ascending, ties by id."""
    return sorted(
        (a for a in actions if is_pending(a)),
        key=lambda a: (a.sort_order, _id_key(a.id)),
    )


def completed_actions(actions: list[ResearchAction]) -> list[ResearchAction]:
    """Return the completed actions, newest first; ties by id ascending."""
    ordered = sorted(
        (a for a in actions if not is_pending(a)), key=lambda a: _id_key(a.id)
    )
    # Stable sort: equal dates keep the ascending-id order from above.
    return sorted(ordered, key=lambda a: date_sort_value(a.completed_date), reverse=True)


def next_sort_order(actions: list[ResearchAction]) -> int:
    """Return a ``sort_order`` that places a new action after every existing one."""
    return max((a.sort_order for a in actions), default=-1) + 1


def add_action(
    working_copy: ResearchCaseWorkingCopy,
    allocator: WorkingCopyIdAllocator,
    title: str = "",
) -> ResearchAction:
    """Add a new pending action at the end of the pending list."""
    action = ResearchAction(
        id=allocator.generate("research_action"),
        research_case_id=working_copy.case.id,
        title=title,
        sort_order=next_sort_order(working_copy.actions),
    )
    working_copy.actions.append(action)
    return action


def set_action_completed(
    action: ResearchAction, completed: bool, today: Optional[str] = None
) -> None:
    """Turn the "Åtgärden genomförd" control on or off.

    On: keeps an existing completion date, otherwise uses today. Off: the date
    becomes ``None``. Title, text, source references and ``sort_order`` are never
    touched, so the change is reversible (Requirements 7.2, 7.4, 7.5, 8.4).
    """
    if completed:
        if action.completed_date is None:
            action.completed_date = today or today_iso()
    else:
        action.completed_date = None


def set_action_completed_date(action: ResearchAction, text: str) -> bool:
    """Edit the "Färdigdatum" field of a completed action.

    An empty or whitespace-only value never gets stored: the action returns to
    pending (``None``), which is the "turn the control off" choice of
    Requirement 7.3. Any other text is stored as typed and left to the validator.

    Returns:
        True if the action is still completed afterwards.
    """
    normalized = normalize_completed_date(text)
    action.completed_date = normalized
    return normalized is not None


def reorder_pending(
    working_copy: ResearchCaseWorkingCopy, ordered_ids: list[str]
) -> None:
    """Give the pending actions ``sort_order`` 0..n-1 in the chosen order.

    Pending actions missing from *ordered_ids* follow in their current order.
    Completed actions keep their ``sort_order``, so reopening one later puts it
    back where it was (Requirement 8.4) relative to the values it still holds.
    """
    pending = {a.id: a for a in working_copy.actions if is_pending(a)}
    ordered = [pending[i] for i in ordered_ids if i in pending]
    rest = [a for a in pending_actions(working_copy.actions) if a.id not in set(ordered_ids)]
    for position, action in enumerate(ordered + rest):
        action.sort_order = position


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def closing_warning_count(
    old_status: str, new_status: str, actions: list[ResearchAction]
) -> int:
    """Return the number of pending actions the closing warning must name.

    Non-zero only for a transition *into* ``closed`` (from another status) while
    pending actions exist; saving an already closed case, or any other
    transition, never warns (Requirements 10.2, 10.5).
    """
    if new_status != "closed" or old_status == "closed":
        return 0
    return sum(1 for a in actions if is_pending(a))


def closing_warning_text(count: int) -> str:
    """Return the body of the "Forskningsärendet har öppna åtgärder" dialog."""
    return (
        f"Forskningsärendet har fortfarande {count} forskningsåtgärder utan "
        f"färdigdatum. Vill du ändå avsluta ärendet?"
    )


CLOSED_CASE_PENDING_INFO = (
    "Väntande åtgärder som hör till avslutade ärenden visas inte i vyn "
    "\"Att göra\" som standard. Åtgärden har lagts till."
)


# ---------------------------------------------------------------------------
# Linked entities
# ---------------------------------------------------------------------------


def _same(link: ResearchEntityLink, entity_type: str, entity_id: str) -> bool:
    return link.entity_type == entity_type and link.entity_id == entity_id


def is_linked(case: ResearchCase, entity_type: str, entity_id: str) -> bool:
    """Return True when the case already links this entity (as primary or not)."""
    if case.primary_entity_ref is not None and _same(
        case.primary_entity_ref, entity_type, entity_id
    ):
        return True
    return any(_same(link, entity_type, entity_id) for link in case.linked_entities)


def add_link(
    case: ResearchCase, entity_type: str, entity_id: str, role: str = ""
) -> bool:
    """Add a link unless the entity is already linked; True if one was added."""
    if is_linked(case, entity_type, entity_id):
        return False
    case.linked_entities.append(ResearchEntityLink(entity_type, entity_id, role))
    return True


def remove_link(case: ResearchCase, entity_type: str, entity_id: str) -> None:
    """Remove the association ("ta bort kopplingen"); never promotes a new primary."""
    remove_entity_association(case, entity_type, entity_id)


def set_primary(case: ResearchCase, entity_type: str, entity_id: str) -> None:
    """Make an entity the primary one without changing the set of linked entities.

    A link already in ``linked_entities`` is moved to ``primary_entity_ref``; the
    previous primary, if any, becomes an ordinary linked entity. No duplicate
    link is created (Requirement 19.5).
    """
    if case.primary_entity_ref is not None and _same(
        case.primary_entity_ref, entity_type, entity_id
    ):
        return

    promoted: Optional[ResearchEntityLink] = None
    remaining: list[ResearchEntityLink] = []
    for link in case.linked_entities:
        if promoted is None and _same(link, entity_type, entity_id):
            promoted = link
        else:
            remaining.append(link)
    if promoted is None:
        promoted = ResearchEntityLink(entity_type, entity_id)

    if case.primary_entity_ref is not None:
        remaining.insert(0, case.primary_entity_ref)
    case.primary_entity_ref = promoted
    case.linked_entities = remaining


def demote_primary(case: ResearchCase) -> None:
    """Turn the primary link into an ordinary linked entity (no primary remains)."""
    if case.primary_entity_ref is None:
        return
    case.linked_entities.insert(0, case.primary_entity_ref)
    case.primary_entity_ref = None


# ---------------------------------------------------------------------------
# Hypotheses and comments
# ---------------------------------------------------------------------------


def add_hypothesis(
    working_copy: ResearchCaseWorkingCopy, allocator: WorkingCopyIdAllocator
) -> ResearchHypothesis:
    """Add an empty, unassessed hypothesis to the working copy."""
    hypothesis = ResearchHypothesis(
        id=allocator.generate("research_hypothesis"),
        research_case_id=working_copy.case.id,
    )
    working_copy.hypotheses.append(hypothesis)
    return hypothesis


def add_comment(
    hypothesis: ResearchHypothesis,
    allocator: WorkingCopyIdAllocator,
    today: Optional[str] = None,
) -> HypothesisComment:
    """Append a comment dated today; the hypothesis' assessment is not touched."""
    comment = HypothesisComment(
        id=allocator.generate("hypothesis_comment"), date=today or today_iso()
    )
    hypothesis.comments.append(comment)
    return comment


def normalize_comment_date(text: str) -> str:
    """Trim a comment date; an empty date stays empty (never invented)."""
    return text.strip()
