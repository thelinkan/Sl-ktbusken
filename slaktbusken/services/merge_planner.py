"""Merge planner: decisions, plan dataclasses and the copy-on-write working copy.

Qt-free. Planning never mutates ``ProjectData``, the translation data or the
settings (Requirements 20.4, 20.11, 26.8). Every object the plan wants to
change is cloned first and the clone is recorded in a :class:`MergeChangeSet`;
:func:`apply_change_set` builds a *new* ``ProjectData`` from it and
:func:`build_sync_view` builds the throw-away structure on which the real
``sync_parentage_links`` runs (Requirement 23.12, 26.2).

This module holds the infrastructure only. The per-category planning is added
by later tasks through :func:`register_plan_step`, one slot per category:

==============  ==========================================  =========
Slot            Content                                     Task
==============  ==========================================  =========
attributes      sex, title, occupation, notes, profile      11.2
names           name union and primary-name choice          11.2
events          participants, role conflicts, similar       11.2
residences      reassigned, never collapsed                 11.2
media_sources   media links, annotations, source refs       11.3
dna             profiles, admin ids, clusters               11.3
research        ``WorkingCopy.rewire_research``             11.3
other_refs      main person, connection overrides, notes    11.3
families        rewire, collapse, cycle and self checks     11.4
reconcile       after the sync: synced vs. intended links   11.4
candidates      redirect and collision                      11.5
identity        translation mappings and aliases            11.5
==============  ==========================================  =========

A step is ``func(ctx: PlanContext) -> None``. It reads ``ctx.data`` (never
writes it), edits objects only through ``ctx.work`` and reports through
``ctx.add_item`` / ``ctx.add_conflict`` / ``ctx.add_unresolved`` /
``ctx.note_dedup``. A step reports user-facing problems as conflicts and does
not raise for them.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field, fields, is_dataclass, replace
from enum import Enum
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

from slaktbusken.model.event import SourceRef
from slaktbusken.model.family import Family
from slaktbusken.model.project import ProjectData
from slaktbusken.services import person_reference_index as pri
from slaktbusken.services.foster_sync import sync_parentage_links
from slaktbusken.services.research_service import (
    RewireResult,
    find_research_dependencies,
    rewire_entity_merge,
)

THIRD_PERSON_MESSAGE = "Exakt två personer krävs för en sammanslagning."
RESEARCH_REWIRE_FAILED_MESSAGE = "Forskningslänkarna kunde inte skrivas om."
PREVIEW_UNAVAILABLE_MESSAGE = "Förhandsgranskningen är inte tillgänglig."

NameKey = tuple  # (given, surname, type, event_id)

SEVERITY_BLOCKING = "blocking"
SEVERITY_WARNING = "warning"


class MergeRefusal(ValueError):
    """A merge request that is refused outright (for example a third person)."""


class MergePlanError(RuntimeError):
    """An unexpected failure while building a plan. The preview is unavailable."""


# ---------------------------------------------------------------------------
# Decisions (section 10.1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MergeDecisions:
    """The user's choices for one merge of exactly two persons.

    The constructor refuses anything but two different person ids and a
    survivor that is one of them (Requirements 33.5, 33.6). The survivor is
    never defaulted (20.8).
    """

    first_person_id: str
    second_person_id: str
    survivor_id: Optional[str] = None
    survivor_confirmed: bool = False
    sex: Optional[str] = None
    title_from: Optional[str] = None
    occupation_from: Optional[str] = None
    profile_media_id: Optional[str] = None
    notes_mode: str = "concatenate"  # keep_survivor | keep_other | concatenate
    primary_name: Optional[NameKey] = None
    participant_roles: Mapping[str, str] = field(default_factory=dict)
    connection_override: Optional[str] = None

    def __post_init__(self) -> None:
        if (
            not self.first_person_id
            or not self.second_person_id
            or self.first_person_id == self.second_person_id
        ):
            raise MergeRefusal(THIRD_PERSON_MESSAGE)
        if self.survivor_id is not None and self.survivor_id not in self.person_ids:
            raise MergeRefusal(THIRD_PERSON_MESSAGE)
        # Read-only snapshot, so a frozen decision cannot be changed through
        # the dict the caller passed in.
        object.__setattr__(
            self, "participant_roles", MappingProxyType(dict(self.participant_roles))
        )

    @classmethod
    def from_person_ids(cls, person_ids: Sequence[str], **choices: Any) -> "MergeDecisions":
        """Build decisions from a sequence of ids; anything but two is refused."""
        ids = list(person_ids)
        if len(ids) != 2:
            raise MergeRefusal(THIRD_PERSON_MESSAGE)
        return cls(first_person_id=ids[0], second_person_id=ids[1], **choices)

    @property
    def person_ids(self) -> tuple[str, str]:
        return (self.first_person_id, self.second_person_id)

    @property
    def retired_id(self) -> Optional[str]:
        """The other person once a survivor is chosen, else ``None``."""
        if self.survivor_id is None:
            return None
        return (
            self.second_person_id
            if self.survivor_id == self.first_person_id
            else self.first_person_id
        )

    def __hash__(self) -> int:  # participant_roles is a mapping
        return hash(
            (
                self.person_ids, self.survivor_id, self.survivor_confirmed, self.sex,
                self.title_from, self.occupation_from, self.profile_media_id,
                self.notes_mode, self.primary_name,
                tuple(sorted(self.participant_roles.items())), self.connection_override,
            )
        )


# ---------------------------------------------------------------------------
# Plan parts (section 10.2)
# ---------------------------------------------------------------------------


class Disposition(Enum):
    PRESERVED = "Bevaras"
    COMBINED = "Slås ihop"
    REASSIGNED = "Flyttas till behållen person"
    LEFT_SEPARATE = "Lämnas separat"
    FLAGGED = "Flaggad"
    EXCLUDED = "Utesluten efter val"


@dataclass(frozen=True)
class PlanItem:
    category: str
    item_id: str
    label: str
    disposition: Disposition
    detail: str = ""


@dataclass(frozen=True)
class MergeConflict:
    severity: str  # "blocking" | "warning"
    code: str
    section: str
    message: str  # Swedish, names the subjects
    subjects: tuple[str, ...] = ()

    @property
    def is_blocking(self) -> bool:
        return self.severity == SEVERITY_BLOCKING


@dataclass(frozen=True)
class UnresolvedChoice:
    """A required user choice that has not been made (Requirement 21.17)."""

    key: str  # "survivor", "sex", "title", "primary_name", "participant_role:<event>", ...
    section: str
    label: str  # Swedish
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReferenceImpact:
    """Reference count per inventory row with its rule (Requirement 22.17)."""

    key: str
    rule: str
    retired_count: int
    survivor_count: int


@dataclass(frozen=True)
class RewireSummary:
    links_rewired: int = 0
    links_collapsed: int = 0


@dataclass(frozen=True)
class CandidateOps:
    redirected: tuple[str, ...] = ()
    collided: tuple[str, ...] = ()
    archived: tuple[str, ...] = ()


@dataclass(frozen=True)
class IdentityOps:
    mappings_moved: tuple[str, ...] = ()
    aliases_rewritten: tuple[str, ...] = ()


@dataclass(frozen=True)
class PreviewModel:
    """Summary of the synchronised working copy (read after the sync)."""

    family_count: int = 0
    parent_child_link_count: int = 0
    added_family_ids: tuple[str, ...] = ()
    removed_family_ids: tuple[str, ...] = ()
    changed_family_ids: tuple[str, ...] = ()


LEDGER_KEYS = (
    "persons", "names", "events", "participants", "residences", "observations",
    "source_refs", "media_items", "media_person_links", "annotations",
    "dna_profiles", "dna_matches", "dna_segments", "dna_clusters",
    "research_cases", "research_hypotheses", "hypothesis_comments",
    "research_actions", "research_notes", "candidates", "candidate_comments",
    "families", "parent_child_links",
)


@dataclass(frozen=True)
class InformationLedger:
    """Counts of information-bearing records (section 10.14)."""

    counts: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(self, "counts", MappingProxyType(dict(self.counts)))

    def __hash__(self) -> int:
        return hash(tuple(sorted(self.counts.items())))

    def __getitem__(self, key: str) -> int:
        return self.counts[key]

    def adjusted(self, deltas: Mapping[str, int]) -> "InformationLedger":
        """A new ledger with *deltas* added (documented deduplications are negative)."""
        unknown = set(deltas) - set(self.counts)
        if unknown:
            raise KeyError(f"Okänd räknare: {sorted(unknown)}")
        return InformationLedger({k: v + deltas.get(k, 0) for k, v in self.counts.items()})

    def differences(self, other: "InformationLedger") -> dict[str, tuple[int, int]]:
        """``{key: (self, other)}`` for every counter that differs."""
        keys = set(self.counts) | set(other.counts)
        return {
            k: (self.counts.get(k, 0), other.counts.get(k, 0))
            for k in sorted(keys)
            if self.counts.get(k, 0) != other.counts.get(k, 0)
        }


def _count_instances(obj: Any, cls: type) -> int:
    """Number of *cls* instances reachable through dataclass fields and lists."""
    if isinstance(obj, cls):
        total = 1
    else:
        total = 0
    if is_dataclass(obj) and not isinstance(obj, type):
        for f in fields(obj):
            total += _count_instances(getattr(obj, f.name), cls)
    elif isinstance(obj, (list, tuple)):
        for x in obj:
            total += _count_instances(x, cls)
    return total


def compute_ledger(data: ProjectData) -> InformationLedger:
    """Count the information-bearing records of *data* (read-only)."""
    candidates = getattr(data, "merge_candidates", None) or []
    c: dict[str, int] = {k: 0 for k in LEDGER_KEYS}
    c["persons"] = len(data.persons)
    c["names"] = sum(len(p.names) for p in data.persons)
    c["events"] = len(data.events)
    c["participants"] = sum(len(e.participants) for e in data.events)
    c["residences"] = len(data.residences)
    c["observations"] = sum(len(r.observations) for r in data.residences)
    c["source_refs"] = _count_instances(data.events, SourceRef) + _count_instances(
        data.residences, SourceRef
    )
    c["media_items"] = len(data.media)
    c["media_person_links"] = sum(
        sum(1 for le in m.linked_entities if le.entity_type == "person")
        + len(m.mentioned_person_ids)
        for m in data.media
    )
    c["annotations"] = sum(len(m.annotations) for m in data.media)
    c["dna_profiles"] = len(data.dna_profiles)
    c["dna_matches"] = len(data.dna_matches)
    c["dna_segments"] = len(data.dna_segments)
    c["dna_clusters"] = len(data.dna_clusters)
    c["research_cases"] = len(data.research_cases)
    c["research_hypotheses"] = len(data.research_hypotheses)
    c["hypothesis_comments"] = sum(len(h.comments) for h in data.research_hypotheses)
    c["research_actions"] = len(data.research_actions)
    c["research_notes"] = len(data.research_notes)
    c["candidates"] = len(candidates)
    c["candidate_comments"] = sum(len(x.comments) for x in candidates)
    c["families"] = len(data.families)
    c["parent_child_links"] = sum(len(f.parent_child_links) for f in data.families)
    return InformationLedger(c)


# ---------------------------------------------------------------------------
# Change set and copy-on-write application (section 10.3)
# ---------------------------------------------------------------------------

#: Collections of ``ProjectData`` a change set may touch.
COLLECTIONS = (
    "persons", "families", "events", "residences", "media", "dna_profiles",
    "dna_matches", "dna_segments", "dna_clusters", "dna_triangulations",
    "research_notes", "research_cases", "research_hypotheses", "research_actions",
    "merge_candidates", "merge_history",
)

#: Scalar targets of ``MergeChangeSet.scalars``.
SCALAR_KEYS = ("main_person_id", "connection_overrides", "id_high_water_marks")


@dataclass
class MergeChangeSet:
    replaced: dict[str, dict[str, Any]] = field(default_factory=dict)
    removed: dict[str, set[str]] = field(default_factory=dict)
    added: dict[str, list[Any]] = field(default_factory=dict)
    scalars: dict[str, Any] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not (
            any(self.replaced.values()) or any(self.removed.values())
            or any(self.added.values()) or self.scalars
        )

    def touched_collections(self) -> set[str]:
        names: set[str] = set()
        for part in (self.replaced, self.removed, self.added):
            names.update(k for k, v in part.items() if v)
        return names


def _check_collection(name: str) -> None:
    if name not in COLLECTIONS:
        raise KeyError(f"Okänd samling: {name}")


def _apply_collection(old: list[Any], cs: MergeChangeSet, name: str) -> list[Any]:
    replaced = cs.replaced.get(name, {})
    removed = cs.removed.get(name, set())
    result = [replaced.get(x.id, x) for x in old if x.id not in removed]
    result.extend(cs.added.get(name, ()))
    return result


def apply_change_set(data: ProjectData, cs: MergeChangeSet) -> ProjectData:
    """Return a **new** ``ProjectData``; *data* and its objects are not touched.

    Touched collections are new lists, untouched collections are the same list
    objects, and unchanged objects are shared.
    """
    for key in cs.scalars:
        if key not in SCALAR_KEYS:
            raise KeyError(f"Okänt skalärt fält: {key}")
    updates: dict[str, Any] = {}
    for name in cs.touched_collections():
        _check_collection(name)
        updates[name] = _apply_collection(getattr(data, name), cs, name)
    if "main_person_id" in cs.scalars:
        updates["project"] = replace(data.project, main_person_id=cs.scalars["main_person_id"])
    if "connection_overrides" in cs.scalars:
        updates["connection_overrides"] = dict(cs.scalars["connection_overrides"])
    if "id_high_water_marks" in cs.scalars:
        updates["id_high_water_marks"] = dict(cs.scalars["id_high_water_marks"])
    return replace(data, **updates)


def clone_family_structural(family: Family) -> Family:
    """New ``Family`` with new lists; partner and link objects are reused."""
    return Family(
        id=family.id,
        partners=list(family.partners),
        children=list(family.children),
        parent_child_links=list(family.parent_child_links),
        event_ids=list(family.event_ids),
    )


def clone_family_deep(family: Family) -> Family:
    """Family whose partners and links are new objects too (safe to edit in place)."""
    return Family(
        id=family.id,
        partners=[replace(p) for p in family.partners],
        children=list(family.children),
        parent_child_links=[replace(l) for l in family.parent_child_links],
        event_ids=list(family.event_ids),
    )


#: Cloner per collection; anything not listed is deep-copied.
_CLONERS: dict[str, Callable[[Any], Any]] = {"families": clone_family_deep}


def build_sync_view(data: ProjectData, cs: MergeChangeSet) -> ProjectData:
    """The throw-away structure on which ``sync_parentage_links`` runs.

    ``persons`` and ``events`` follow the change set (events are shared, the
    sync only reads them); **every** family is a structural clone because the
    sync reassigns ``event_ids`` on all of them. Other collections are shared
    and never touched by the sync.
    """
    view = apply_change_set(data, cs)
    view.families = [clone_family_structural(f) for f in view.families]
    return view


def record_sync_result(
    data: ProjectData, view: ProjectData, cs: MergeChangeSet
) -> PreviewModel:
    """Fold the families of the synchronised *view* into *cs* and summarise them.

    The engine commits the families of the view, so ids generated by the sync
    match the preview (section 10.13). Families equal to their original are
    not recorded, so an unchanged project yields no family changes.
    """
    original = {f.id: f for f in data.families}
    view_by_id = {f.id: f for f in view.families}
    removed = sorted(set(original) - set(view_by_id))
    added = [f for f in view.families if f.id not in original]
    changed = [
        f for f in view.families if f.id in original and f != original[f.id]
    ]
    # The change set may already hold family edits made by the planning steps;
    # the view is derived from them, so its version wins.
    for f in changed:
        cs.replaced.setdefault("families", {})[f.id] = f
    cs.removed.setdefault("families", set()).update(removed)
    cs.added["families"] = [
        *[x for x in cs.added.get("families", []) if x.id not in view_by_id],
        *added,
    ]
    for gone in removed:
        cs.replaced.get("families", {}).pop(gone, None)
    return PreviewModel(
        family_count=len(view.families),
        parent_child_link_count=sum(len(f.parent_child_links) for f in view.families),
        added_family_ids=tuple(f.id for f in added),
        removed_family_ids=tuple(removed),
        changed_family_ids=tuple(f.id for f in changed),
    )


class WorkingCopy:
    """Copy-on-write access to the project for planning steps.

    ``edit(collection, id)`` returns the clone of an object, creating and
    recording it on first use; the original is never returned for editing.
    """

    def __init__(self, data: ProjectData) -> None:
        self._data = data
        self.change_set = MergeChangeSet()
        self._index: dict[str, dict[str, Any]] = {}

    def original(self, collection: str, object_id: str) -> Any:
        _check_collection(collection)
        if collection not in self._index:
            self._index[collection] = {x.id: x for x in getattr(self._data, collection)}
        return self._index[collection][object_id]

    def edit(self, collection: str, object_id: str) -> Any:
        """The editable clone of one object (created once, then reused)."""
        replaced = self.change_set.replaced.setdefault(collection, {})
        if object_id not in replaced:
            if object_id in self.change_set.removed.get(collection, ()):
                raise KeyError(f"{collection}/{object_id} är borttagen")
            original = self.original(collection, object_id)
            replaced[object_id] = _CLONERS.get(collection, copy.deepcopy)(original)
        return replaced[object_id]

    def remove(self, collection: str, object_id: str) -> None:
        _check_collection(collection)
        self.original(collection, object_id)  # must exist
        self.change_set.removed.setdefault(collection, set()).add(object_id)
        self.change_set.replaced.get(collection, {}).pop(object_id, None)

    def add(self, collection: str, obj: Any) -> None:
        _check_collection(collection)
        self.change_set.added.setdefault(collection, []).append(obj)

    def set_scalar(self, key: str, value: Any) -> None:
        if key not in SCALAR_KEYS:
            raise KeyError(f"Okänt skalärt fält: {key}")
        self.change_set.scalars[key] = value

    def rewire_research(self, retired: str, survivor: str) -> RewireSummary:
        """Run ``rewire_entity_merge`` for ``person`` on copies (section 10.11).

        Only the cases and hypotheses that reference *retired* are copied; the
        helper mutates the copies, which are recorded as replacements.
        """
        try:
            deps = find_research_dependencies(self._data, "person", retired)
            shell = ProjectData(
                research_cases=[self.edit("research_cases", c.id) for c in deps.cases],
                research_hypotheses=[
                    self.edit("research_hypotheses", h.id) for h in deps.hypotheses
                ],
            )
            result: RewireResult = rewire_entity_merge(shell, "person", retired, survivor)
        except Exception as exc:  # the helper's failure aborts the plan (22.12)
            raise MergePlanError(RESEARCH_REWIRE_FAILED_MESSAGE) from exc
        return RewireSummary(result.links_rewired, result.links_collapsed)


# ---------------------------------------------------------------------------
# Fingerprint (section 10.4 step 17, Requirement 26.9)
# ---------------------------------------------------------------------------


def _canonical(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return [type(obj).__name__, {f.name: _canonical(getattr(obj, f.name)) for f in fields(obj)}]
    if isinstance(obj, (list, tuple)):
        return [_canonical(x) for x in obj]
    if isinstance(obj, (set, frozenset)):
        return sorted((_canonical(x) for x in obj), key=lambda v: json.dumps(v, sort_keys=True))
    if isinstance(obj, Mapping):
        return {str(k): _canonical(v) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))}
    if isinstance(obj, Enum):
        return obj.value
    return obj


def compute_fingerprint(
    data: ProjectData,
    person_ids: Iterable[str],
    index: pri.PersonReferenceIndex,
    translation: Any = None,
) -> str:
    """SHA-256 over every object the plan read.

    That is: the two persons, every object the reference index found, all
    candidates and history entries, the translation mappings of the two ids,
    all identity aliases and the id high-water marks.
    """
    ids = set(person_ids)
    seen: dict[int, Any] = {}
    for by_id in index.refs.values():
        for objs in by_id.values():
            for o in objs:
                seen[id(o)] = o
    parts: list[str] = []

    def add(tag: str, obj: Any) -> None:
        parts.append(json.dumps([tag, _canonical(obj)], sort_keys=True, ensure_ascii=False))

    for p in data.persons:
        if p.id in ids:
            add("person", p)
    for o in seen.values():
        add("ref", o)
    for cand in getattr(data, "merge_candidates", None) or []:
        add("candidate", cand)
    for entry in getattr(data, "merge_history", None) or []:
        add("history", entry)
    add("marks", dict(data.id_high_water_marks))
    add("main_person", data.project.main_person_id)
    add("overrides", {k: v for k, v in data.connection_overrides.items() if k in ids})
    if translation is not None:
        for m in getattr(translation, "persons", None) or []:
            if getattr(m, "app_id", None) in ids:
                add("mapping", m)
        for a in getattr(translation, "person_aliases", None) or []:
            add("alias", a)
    digest = hashlib.sha256()
    for part in sorted(parts):
        digest.update(part.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Plan (section 10.2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MergePlan:
    survivor_id: Optional[str]
    retired_id: Optional[str]
    decisions: MergeDecisions
    content_revision: int
    fingerprint: str
    items: tuple[PlanItem, ...]
    unresolved: tuple[UnresolvedChoice, ...]
    conflicts: tuple[MergeConflict, ...]
    reference_impacts: tuple[ReferenceImpact, ...]
    research: RewireSummary
    candidate_ops: CandidateOps
    identity_ops: IdentityOps
    change_set: MergeChangeSet
    preview: PreviewModel
    ledger_before: InformationLedger
    ledger_after_expected: InformationLedger

    @property
    def blocking(self) -> tuple[MergeConflict, ...]:
        return tuple(c for c in self.conflicts if c.is_blocking)

    @property
    def warnings(self) -> tuple[MergeConflict, ...]:
        return tuple(c for c in self.conflicts if not c.is_blocking)

    @property
    def can_execute(self) -> bool:
        return (
            self.survivor_id is not None
            and self.decisions.survivor_confirmed
            and not self.blocking
            and not self.unresolved
        )


# ---------------------------------------------------------------------------
# Plan context, step registry and pipeline (section 10.4)
# ---------------------------------------------------------------------------


@dataclass
class PlanContext:
    """What a planning step sees and fills. ``data`` is read-only by contract."""

    data: ProjectData
    translation: Any
    decisions: MergeDecisions
    survivor_id: str
    retired_id: str
    index: pri.PersonReferenceIndex
    work: WorkingCopy
    items: list[PlanItem] = field(default_factory=list)
    conflicts: list[MergeConflict] = field(default_factory=list)
    unresolved: list[UnresolvedChoice] = field(default_factory=list)
    ledger_deltas: dict[str, int] = field(default_factory=dict)
    research: RewireSummary = RewireSummary()
    candidate_ops: CandidateOps = CandidateOps()
    identity_ops: IdentityOps = IdentityOps()
    sync_view: Optional[ProjectData] = None
    _item_keys: set[tuple[str, str]] = field(default_factory=set)

    def add_item(
        self, category: str, item_id: str, label: str, disposition: Disposition, detail: str = ""
    ) -> None:
        """Add a plan item; each (category, id) has exactly one disposition (21.1)."""
        key = (category, item_id)
        if key in self._item_keys:
            raise MergePlanError(f"Dubbel disposition för {category}/{item_id}")
        self._item_keys.add(key)
        self.items.append(PlanItem(category, item_id, label, disposition, detail))

    def add_conflict(
        self, severity: str, code: str, section: str, message: str, subjects: Sequence[str] = ()
    ) -> None:
        self.conflicts.append(MergeConflict(severity, code, section, message, tuple(subjects)))

    def add_unresolved(
        self, key: str, section: str, label: str, options: Sequence[str] = ()
    ) -> None:
        self.unresolved.append(UnresolvedChoice(key, section, label, tuple(options)))

    def note_dedup(self, counter: str, count: int = 1) -> None:
        """Record a documented deduplication (the ledger drops by *count*)."""
        if counter not in LEDGER_KEYS:
            raise KeyError(f"Okänd räknare: {counter}")
        self.ledger_deltas[counter] = self.ledger_deltas.get(counter, 0) - count


PlanStep = Callable[[PlanContext], None]

#: Pipeline order. Steps 12 (sync view) happens between "families" and "reconcile".
PIPELINE_SLOTS = (
    "attributes", "names", "events", "residences", "media_sources", "dna",
    "research", "other_refs", "families", "reconcile", "candidates", "identity",
)

_PLAN_STEPS: dict[str, list[PlanStep]] = {slot: [] for slot in PIPELINE_SLOTS}


def register_plan_step(slot: str, func: PlanStep) -> PlanStep:
    """Register *func* in a pipeline slot (usable as a decorator factory result)."""
    if slot not in _PLAN_STEPS:
        raise KeyError(f"Okänd planeringsplats: {slot}")
    if func not in _PLAN_STEPS[slot]:
        _PLAN_STEPS[slot].append(func)
    return func


def plan_step(slot: str) -> Callable[[PlanStep], PlanStep]:
    """Decorator form of :func:`register_plan_step`."""

    def decorator(func: PlanStep) -> PlanStep:
        return register_plan_step(slot, func)

    return decorator


def registered_steps(slot: str) -> tuple[PlanStep, ...]:
    return tuple(_PLAN_STEPS[slot])


def _run_slot(ctx: PlanContext, slot: str) -> None:
    for step in _PLAN_STEPS[slot]:
        step(ctx)


def _reference_impacts(
    index: pri.PersonReferenceIndex, survivor: str, retired: str
) -> tuple[ReferenceImpact, ...]:
    impacts = []
    for loc in pri.PERSON_REFERENCE_INVENTORY:
        r, s = index.count(loc.key, retired), index.count(loc.key, survivor)
        if r or s:
            impacts.append(ReferenceImpact(loc.key, loc.rule, r, s))
    return tuple(impacts)


def build_plan(
    data: ProjectData,
    translation: Any,
    decisions: MergeDecisions,
    content_revision: int = 0,
) -> MergePlan:
    """Build a :class:`MergePlan`. Reads *data* and *translation*, writes neither.

    Refuses anything but two different existing persons. While the survivor is
    not chosen the plan holds only the survivor-choice item (section 10.4
    step 1). An unexpected exception becomes :class:`MergePlanError`; the
    caller shows "Förhandsgranskningen är inte tillgänglig." and disables
    execution (26.10).
    """
    existing = {p.id for p in data.persons}
    if not all(pid in existing for pid in decisions.person_ids):
        raise MergeRefusal(THIRD_PERSON_MESSAGE)

    index = pri.PersonReferenceIndex.build(data, decisions.person_ids, translation)
    fingerprint = compute_fingerprint(data, decisions.person_ids, index, translation)
    ledger_before = compute_ledger(data)
    survivor, retired = decisions.survivor_id, decisions.retired_id

    if survivor is None or retired is None:
        return MergePlan(
            survivor_id=None, retired_id=None, decisions=decisions,
            content_revision=content_revision, fingerprint=fingerprint,
            items=(), unresolved=(
                UnresolvedChoice(
                    "survivor", "survivor", "Välj vilken person som ska behållas.",
                    decisions.person_ids,
                ),
            ),
            conflicts=(), reference_impacts=(), research=RewireSummary(),
            candidate_ops=CandidateOps(), identity_ops=IdentityOps(),
            change_set=MergeChangeSet(), preview=PreviewModel(),
            ledger_before=ledger_before, ledger_after_expected=ledger_before,
        )

    ctx = PlanContext(
        data=data, translation=translation, decisions=decisions,
        survivor_id=survivor, retired_id=retired, index=index, work=WorkingCopy(data),
    )
    try:
        for slot in PIPELINE_SLOTS[: PIPELINE_SLOTS.index("reconcile")]:
            _run_slot(ctx, slot)

        # Step 12: the real sync on a throw-away structure.
        ctx.work.change_set.removed.setdefault("persons", set()).add(retired)
        view = build_sync_view(data, ctx.work.change_set)
        sync_parentage_links(view)
        ctx.sync_view = view
        preview = record_sync_result(data, view, ctx.work.change_set)

        for slot in PIPELINE_SLOTS[PIPELINE_SLOTS.index("reconcile"):]:
            _run_slot(ctx, slot)
    except MergePlanError:
        raise
    except Exception as exc:
        raise MergePlanError(PREVIEW_UNAVAILABLE_MESSAGE) from exc

    deltas = dict(ctx.ledger_deltas)
    deltas["persons"] = deltas.get("persons", 0) - 1  # the retired person
    return MergePlan(
        survivor_id=survivor, retired_id=retired, decisions=decisions,
        content_revision=content_revision, fingerprint=fingerprint,
        items=tuple(ctx.items), unresolved=tuple(ctx.unresolved),
        conflicts=tuple(ctx.conflicts),
        reference_impacts=_reference_impacts(index, survivor, retired),
        research=ctx.research, candidate_ops=ctx.candidate_ops,
        identity_ops=ctx.identity_ops, change_set=ctx.work.change_set, preview=preview,
        ledger_before=ledger_before,
        ledger_after_expected=ledger_before.adjusted(deltas),
    )


# Registers the person planning steps (attributes, names, events, residences).
# Imported last so `plan_step` and the planner classes already exist.
from slaktbusken.services import merge_planner_person  # noqa: E402,F401
from slaktbusken.services import merge_planner_refs  # noqa: E402,F401
