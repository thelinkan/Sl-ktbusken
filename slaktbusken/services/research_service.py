"""Research service: id generation that never reuses an id, and reference integrity.

``IDGenerator`` derives its counter from the ids it is seeded with, and every
existing call site seeds it from the entities that currently exist. After the
entity holding the highest suffix is deleted and the project is saved and
reopened, that suffix is gone from the seed and gets handed out again. For
research data that matters: a reference that was kept on purpose after its
target was deleted could silently start pointing at an unrelated new entity.

``ProjectData.id_high_water_marks`` therefore records, per id prefix, the
highest suffix ever issued. ``ResearchIdGenerator`` seeds from it as well as
from the live ids, and writes the new mark back on every id it issues.

This module is pure: no Qt and no I/O.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field

from slaktbusken.model.id_generator import IDGenerator
from slaktbusken.model.project import ProjectData
from slaktbusken.model.research_case import (
    ResearchAction,
    ResearchCase,
    ResearchEntityLink,
    ResearchHypothesis,
    case_entity_links,
)

#: The entity types whose ids this module issues and protects.
RESEARCH_ID_ENTITY_TYPES: tuple[str, ...] = (
    "research_case",
    "research_hypothesis",
    "research_action",
    "hypothesis_comment",
)


def research_id_prefix(entity_type: str) -> str:
    """Return the id prefix (for example ``"case_"``) for a research entity type.

    Raises:
        ValueError: If *entity_type* is not a research entity type.
    """
    if entity_type not in RESEARCH_ID_ENTITY_TYPES:
        raise ValueError(f"Not a research entity type: {entity_type!r}")
    return IDGenerator._PREFIXES[entity_type]


def live_research_ids(data: ProjectData) -> dict[str, set[str]]:
    """Return the ids currently in use, grouped by research id prefix.

    Includes the hypothesis comments nested inside each hypothesis.
    """
    ids: dict[str, set[str]] = {
        research_id_prefix(entity_type): set() for entity_type in RESEARCH_ID_ENTITY_TYPES
    }
    ids[research_id_prefix("research_case")].update(case.id for case in data.research_cases)
    ids[research_id_prefix("research_hypothesis")].update(
        hypothesis.id for hypothesis in data.research_hypotheses
    )
    ids[research_id_prefix("research_action")].update(
        action.id for action in data.research_actions
    )
    comment_ids = ids[research_id_prefix("hypothesis_comment")]
    for hypothesis in data.research_hypotheses:
        comment_ids.update(comment.id for comment in hypothesis.comments)
    return ids


def _highest_suffix(ids: set[str], prefix: str) -> int:
    """Return the largest numeric suffix among *ids* of the form ``prefix + digits``."""
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    highest = 0
    for used in ids:
        match = pattern.match(used)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest


def reconcile_id_high_water_marks(data: ProjectData) -> None:
    """Raise each research prefix's mark to at least its highest live id suffix.

    Run when a project is loaded, so a project that holds research data but no
    stored marks (written before the marks existed) still never reuses an id.
    A mark is only ever raised, never lowered, and a prefix with no live id and
    no stored mark is left out, so a project without research data keeps an
    empty map.
    """
    for prefix, ids in live_research_ids(data).items():
        highest = _highest_suffix(ids, prefix)
        if highest > data.id_high_water_marks.get(prefix, 0):
            data.id_high_water_marks[prefix] = highest


class ResearchIdGenerator:
    """Issues research ids that are never reused, even after reopening a project.

    Each id issued advances ``ProjectData.id_high_water_marks`` for its prefix,
    so the next id is greater even when the entity just issued has not been
    added to the project yet (for example inside an editor's working copy), and
    even when it is later deleted.
    """

    def __init__(self, data: ProjectData) -> None:
        self._data = data
        reconcile_id_high_water_marks(data)

    def generate(self, entity_type: str) -> str:
        """Return a new id for a research entity type and record its suffix.

        Raises:
            ValueError: If *entity_type* is not a research entity type.
        """
        prefix = research_id_prefix(entity_type)
        live = live_research_ids(self._data)[prefix]

        # Seed the generator with the live ids plus a stand-in for the stored
        # mark, so its high-water-mark logic starts above every id ever issued.
        seed = set(live)
        mark = self._data.id_high_water_marks.get(prefix, 0)
        if mark > 0:
            seed.add(f"{prefix}{mark}")

        new_id = IDGenerator(seed).generate(entity_type)
        self._data.id_high_water_marks[prefix] = int(new_id[len(prefix):])
        return new_id


# ---------------------------------------------------------------------------
# Reference integrity: dependencies, association removal, merge
# ---------------------------------------------------------------------------


@dataclass
class ResearchDependencies:
    """The research data that refers to one entity.

    Attributes:
        cases: Cases that link the entity (as primary or linked entity).
        hypotheses: Hypotheses that name the entity.
        actions: Actions that cite the entity as a source (only for sources).
    """

    cases: list[ResearchCase] = field(default_factory=list)
    hypotheses: list[ResearchHypothesis] = field(default_factory=list)
    actions: list[ResearchAction] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.cases or self.hypotheses or self.actions)


def find_research_dependencies(
    data: ProjectData, entity_type: str, entity_id: str
) -> ResearchDependencies:
    """Return the research data that refers to an entity, without changing anything.

    Works from the stored references, so it also finds references to an entity
    that has already been deleted. Used to tell the user what research a
    deletion or merge touches; deleting an entity never deletes research.
    """
    result = ResearchDependencies()

    for case in data.research_cases:
        if any(
            link.entity_type == entity_type and link.entity_id == entity_id
            for link in case_entity_links(case)
        ):
            result.cases.append(case)

    for hypothesis in data.research_hypotheses:
        if any(
            link.entity_type == entity_type and link.entity_id == entity_id
            for link in hypothesis.linked_entities
        ):
            result.hypotheses.append(hypothesis)

    if entity_type == "source":
        for action in data.research_actions:
            if any(ref.source_id == entity_id for ref in action.source_refs):
                result.actions.append(action)

    return result


def remove_entity_association(
    case: ResearchCase, entity_type: str, entity_id: str
) -> ResearchCase:
    """Remove every link from a case to one entity, and keep the case.

    This is "ta bort kopplingen": the case, its hypotheses and its actions are
    untouched. If the primary link points at the entity it is cleared, and no
    other link is promoted in its place, so the case is left with no primary
    entity until the user chooses one. A case with no primary entity is valid.

    Mutates and returns *case*.
    """
    primary = case.primary_entity_ref
    if (
        primary is not None
        and primary.entity_type == entity_type
        and primary.entity_id == entity_id
    ):
        case.primary_entity_ref = None

    case.linked_entities = [
        link
        for link in case.linked_entities
        if not (link.entity_type == entity_type and link.entity_id == entity_id)
    ]
    return case


@dataclass
class RewireResult:
    """What :func:`rewire_entity_merge` changed.

    Attributes:
        links_rewired: Entity links (on cases and hypotheses) pointed at the survivor.
        links_collapsed: Links removed because they duplicated another link to the survivor.
        source_refs_rewired: Action source references pointed at the surviving source.
    """

    links_rewired: int = 0
    links_collapsed: int = 0
    source_refs_rewired: int = 0


def _collapse_links_to(
    links: list[ResearchEntityLink], entity_type: str, entity_id: str
) -> tuple[list[ResearchEntityLink], int]:
    """Collapse repeated links to one entity into the first of them.

    The first link keeps its position, so the primary link stays the primary
    one. If it has no role and a repeat does, it takes the first non-empty role,
    so a role is never lost to a duplicate. Returns the new list and how many
    links were removed.
    """
    kept: list[ResearchEntityLink] = []
    first: ResearchEntityLink | None = None
    removed = 0
    for link in links:
        if link.entity_type == entity_type and link.entity_id == entity_id:
            if first is None:
                first = link
                kept.append(link)
            else:
                if not first.role and link.role:
                    first.role = link.role
                removed += 1
        else:
            kept.append(link)
    return kept, removed


def rewire_entity_merge(
    data: ProjectData, entity_type: str, old_id: str, survivor_id: str
) -> RewireResult:
    """Point research references at the surviving entity after a merge.

    Every case link and hypothesis link to ``(entity_type, old_id)`` is changed
    to ``survivor_id``; only the id changes, so a link keeps its ``role``. For a
    source merge every action source reference is rewired the same way and keeps
    its ``quality``, ``note`` and ``aspects``. Source references are not
    collapsed even when an action now cites the survivor twice: that would
    discard one citation's quality or note, and the index already lists the
    action once.

    Where a case (or hypothesis) now links the survivor more than once, the
    repeats are collapsed into the first, which keeps its position and takes
    the first non-empty role. Links that were duplicated for other entities are
    left alone.

    Does not set the dirty flag or notify; the caller does, because it knows
    whether the merge is part of a larger operation.
    """
    result = RewireResult()
    if old_id == survivor_id:
        return result

    def rewire(links: list[ResearchEntityLink]) -> int:
        count = 0
        for link in links:
            if link.entity_type == entity_type and link.entity_id == old_id:
                link.entity_id = survivor_id
                count += 1
        return count

    for case in data.research_cases:
        links = case_entity_links(case)
        rewired = rewire(links)
        if not rewired:
            continue
        result.links_rewired += rewired
        if case.primary_entity_ref is not None:
            # Collapse across primary + linked together, in that order.
            combined, removed = _collapse_links_to(links, entity_type, survivor_id)
            case.linked_entities = [
                link for link in combined if link is not case.primary_entity_ref
            ]
        else:
            case.linked_entities, removed = _collapse_links_to(
                case.linked_entities, entity_type, survivor_id
            )
        result.links_collapsed += removed

    for hypothesis in data.research_hypotheses:
        rewired = rewire(hypothesis.linked_entities)
        if not rewired:
            continue
        result.links_rewired += rewired
        hypothesis.linked_entities, removed = _collapse_links_to(
            hypothesis.linked_entities, entity_type, survivor_id
        )
        result.links_collapsed += removed

    if entity_type == "source":
        for action in data.research_actions:
            for source_ref in action.source_refs:
                if source_ref.source_id == old_id:
                    source_ref.source_id = survivor_id
                    result.source_refs_rewired += 1

    return result


# ---------------------------------------------------------------------------
# Deleting a case, and the editor's working copy
# ---------------------------------------------------------------------------


@dataclass
class ResearchChildCounts:
    """How much research belongs to one case, for the delete confirmation.

    Attributes:
        hypotheses: Hypotheses belonging to the case.
        comments: Hypothesis comments across those hypotheses.
        actions: Actions belonging to the case.
    """

    hypotheses: int = 0
    comments: int = 0
    actions: int = 0


def count_case_children(data: ProjectData, case_id: str) -> ResearchChildCounts:
    """Count the hypotheses, comments and actions that deleting a case would remove."""
    hypotheses = [h for h in data.research_hypotheses if h.research_case_id == case_id]
    return ResearchChildCounts(
        hypotheses=len(hypotheses),
        comments=sum(len(h.comments) for h in hypotheses),
        actions=sum(1 for a in data.research_actions if a.research_case_id == case_id),
    )


def delete_case_cascade(data: ProjectData, case_id: str) -> ResearchChildCounts:
    """Delete a case together with exactly its own hypotheses, comments and actions.

    Every other case and its children stay as they are, and no genealogical fact
    is touched. The id high-water marks are not lowered, so the deleted ids are
    never issued again.

    Returns:
        How many hypotheses, comments and actions were removed with the case.

    Raises:
        KeyError: If there is no case with that id; nothing is changed.
    """
    if not any(case.id == case_id for case in data.research_cases):
        raise KeyError(f"Inget forskningsärende med id {case_id!r} att ta bort.")

    counts = count_case_children(data, case_id)
    data.research_cases = [c for c in data.research_cases if c.id != case_id]
    data.research_hypotheses = [
        h for h in data.research_hypotheses if h.research_case_id != case_id
    ]
    data.research_actions = [
        a for a in data.research_actions if a.research_case_id != case_id
    ]
    return counts


@dataclass
class ResearchCaseWorkingCopy:
    """A case and everything that belongs to it, held apart from the project.

    The case editor changes this copy and nothing else while it is open. Nothing
    reaches the project until the copy is validated and applied, so cancelling,
    or a validation failure, leaves the project exactly as it was.

    Attributes:
        case: The case.
        hypotheses: Its hypotheses, each with its comments.
        actions: Its actions.
    """

    case: ResearchCase
    hypotheses: list[ResearchHypothesis] = field(default_factory=list)
    actions: list[ResearchAction] = field(default_factory=list)


def open_working_copy(data: ProjectData, case_id: str) -> ResearchCaseWorkingCopy:
    """Return a deep copy of a case and its hypotheses and actions.

    Raises:
        KeyError: If there is no case with that id.
    """
    for case in data.research_cases:
        if case.id == case_id:
            return ResearchCaseWorkingCopy(
                case=copy.deepcopy(case),
                hypotheses=[
                    copy.deepcopy(h)
                    for h in data.research_hypotheses
                    if h.research_case_id == case_id
                ],
                actions=[
                    copy.deepcopy(a)
                    for a in data.research_actions
                    if a.research_case_id == case_id
                ],
            )
    raise KeyError(f"Inget forskningsärende med id {case_id!r}.")


@dataclass
class ResearchCaseDiff:
    """What applying a working copy would change in the project.

    Each list holds ids. A case that is not in the project yet is ``created``.
    """

    case_created: bool = False
    case_updated: bool = False
    hypotheses_created: list[str] = field(default_factory=list)
    hypotheses_updated: list[str] = field(default_factory=list)
    hypotheses_deleted: list[str] = field(default_factory=list)
    actions_created: list[str] = field(default_factory=list)
    actions_updated: list[str] = field(default_factory=list)
    actions_deleted: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (
            self.case_created or self.case_updated
            or self.hypotheses_created or self.hypotheses_updated or self.hypotheses_deleted
            or self.actions_created or self.actions_updated or self.actions_deleted
        )


def _check_working_copy_ownership(working_copy: ResearchCaseWorkingCopy) -> None:
    """Raise ValueError if a child of the working copy belongs to another case."""
    case_id = working_copy.case.id
    for hypothesis in working_copy.hypotheses:
        if hypothesis.research_case_id != case_id:
            raise ValueError(
                f"Hypotesen {hypothesis.id!r} tillhör inte forskningsärendet {case_id!r}."
            )
    for action in working_copy.actions:
        if action.research_case_id != case_id:
            raise ValueError(
                f"Åtgärden {action.id!r} tillhör inte forskningsärendet {case_id!r}."
            )


def diff_working_copy(
    data: ProjectData, working_copy: ResearchCaseWorkingCopy
) -> ResearchCaseDiff:
    """Describe what applying the working copy would create, update and delete.

    Compares by id. An entity "updated" is one whose id exists in both and whose
    content differs. Does not change the project or the working copy.

    Raises:
        ValueError: If a hypothesis or action in the working copy belongs to a
            different case.
    """
    _check_working_copy_ownership(working_copy)
    case_id = working_copy.case.id
    diff = ResearchCaseDiff()

    existing_case = next((c for c in data.research_cases if c.id == case_id), None)
    diff.case_created = existing_case is None
    diff.case_updated = existing_case is not None and existing_case != working_copy.case

    existing_h = {h.id: h for h in data.research_hypotheses if h.research_case_id == case_id}
    new_h = {h.id: h for h in working_copy.hypotheses}
    diff.hypotheses_created = [i for i in new_h if i not in existing_h]
    diff.hypotheses_deleted = [i for i in existing_h if i not in new_h]
    diff.hypotheses_updated = [
        i for i in new_h if i in existing_h and new_h[i] != existing_h[i]
    ]

    existing_a = {a.id: a for a in data.research_actions if a.research_case_id == case_id}
    new_a = {a.id: a for a in working_copy.actions}
    diff.actions_created = [i for i in new_a if i not in existing_a]
    diff.actions_deleted = [i for i in existing_a if i not in new_a]
    diff.actions_updated = [
        i for i in new_a if i in existing_a and new_a[i] != existing_a[i]
    ]
    return diff


def apply_working_copy(data: ProjectData, working_copy: ResearchCaseWorkingCopy) -> None:
    """Write the working copy into the project in one step.

    Creates, updates and deletes the case's hypotheses and actions together.
    Entities that already exist are replaced where they stand, so project order
    is kept; new ones are appended in working-copy order; ones missing from the
    working copy are removed. Other cases and their children are not touched.

    All checks happen before the project is changed, and the new collections are
    built completely before they replace the old ones, so the project is never
    left half-applied. The project receives deep copies, so the editor can keep
    using its working copy.

    This does not validate, set the dirty flag or notify; the caller does.

    Raises:
        ValueError: If a hypothesis or action belongs to a different case.
            Nothing is changed.
    """
    _check_working_copy_ownership(working_copy)
    case_id = working_copy.case.id

    # Build every new collection first; assign only at the end.
    new_cases = list(data.research_cases)
    case_copy = copy.deepcopy(working_copy.case)
    for index, existing in enumerate(new_cases):
        if existing.id == case_id:
            new_cases[index] = case_copy
            break
    else:
        new_cases.append(case_copy)

    new_hypotheses = _replace_children(
        data.research_hypotheses, working_copy.hypotheses, case_id
    )
    new_actions = _replace_children(data.research_actions, working_copy.actions, case_id)

    data.research_cases = new_cases
    data.research_hypotheses = new_hypotheses
    data.research_actions = new_actions


def _replace_children(existing: list, wanted: list, case_id: str) -> list:
    """Return *existing* with one case's children replaced by *wanted*.

    Children of other cases are kept in place. This case's children keep their
    position when they are in *wanted* (replaced by a copy), are dropped when
    they are not, and new ones are appended in *wanted* order.
    """
    wanted_by_id = {child.id: child for child in wanted}
    result: list = []
    placed: set[str] = set()
    for child in existing:
        if child.research_case_id != case_id:
            result.append(child)
        elif child.id in wanted_by_id:
            result.append(copy.deepcopy(wanted_by_id[child.id]))
            placed.add(child.id)
    for child in wanted:
        if child.id not in placed:
            result.append(copy.deepcopy(child))
    return result
