# Design Document

## Overview

The Research Cases feature adds a project-level research management system to Släktbusken. It is implemented as a new vertical slice that reuses the existing architecture end to end: new dataclasses in `slaktbusken/model/`, new top-level collections on `ProjectData`, reflection-based JSON persistence with a registered migration, Swedish-returning validators, a rebuild-on-demand index service, `ProjectService` CRUD with the dirty flag, a reusable research tab widget embedded in existing editors, a central overview window reached from a new **Forskning** menu, person-list and diagram indicators driven by the existing settings system, an extended filter dialog, a consistency report in the existing report framework, and reference-integrity hooks into deletion and merge.

The design holds to one invariant throughout: **research is descriptive and never mutates a genealogical fact as a side effect.** No hypothesis, conclusion, status change, or action completion touches a `Person`, `Event`, `Family`, `Place`, `Source`, `Media`, or DNA record. The research collections are a parallel, additive layer.

The feature raises the project format version from `0.2` to `0.3`.

This design mirrors the structure the Residence_Fact feature established at 0.2, because that feature is the most recent full-stack addition and its serialization, migration, delete-cascade, settings, and formatter patterns are the proven template to follow.

## Architecture

### Layered placement

```
model/            research_case.py          (dataclasses + pure helpers)
                  validators.py             (+ validate_research_* functions)
                  project.py                (+ 3 collections + id_high_water_marks on ProjectData)
                  id_generator.py           (+ 4 id prefixes)

persistence/      serialization.py          (+ entity_fields, registries, research deserializer, HWM map)
                  migration.py              (+ 0.2->0.3 migration; CURRENT_VERSION=0.3)
                  file_io.py                (CURRENT_VERSION=0.3)
                  settings_io.py            (+ PersonListConfig/PersonBoxConfig fields)
                  app_settings_io.py        (+ ColumnVisibility.research field)

services/         research_service.py       (CRUD + reference integrity + merge-rewire + ResearchIdGenerator)
                  research_index.py          (rebuild-on-demand lookup bundle)
                  project_service.py         (+ add/update/delete research + commit working copy)
                  delete_service.py          (+ find_research_dependencies; no research deletion)
                  source_aspects.py          (+ research_case entity aspects)

reports/          research_consistency.py    (Issue + check_* + generate_*)
                  generator.py               (+ generate_research_consistency)

gedcom/           exporter.py                (_collect_omissions += research counts)

ui/               research_overview.py       (central window; three modes)
  editors/        research_case_editor.py    (one-case editor; Working_Copy)
  widgets/        research_tab.py            (reusable "Forskning" tab, embedded everywhere)
                  research_indicator.py      (shared indicator rendering helper)
  dialogs/        filter_dialog.py           (two-column refactor + research filters)
  person_list_panel.py                       (+ research column, FilterCriteria fields)
  person_box.py (widgets/)                   (+ research indicator)
  main_window.py                             (+ Forskning menu, report action wiring)
  report_menu.py                             (promote placeholders)
  swedish_locale.py                          (+ research label dicts + getters)
app.py            Application                (+ show_research_overview, open_research_case, research_changed)
```

### Data-flow invariants

1. **Single source of truth.** Research entities live only in `ProjectData.research_cases`, `ProjectData.research_hypotheses`, and `ProjectData.research_actions`. Nothing copies them onto persons, places, or sources. Every view resolves display text from the referenced entity at render time (Requirement 3.6, 30.3).
2. **Derive, never cache-and-invalidate.** The `ResearchIndex` is rebuilt from `ProjectData` on demand, like `foster_sync._ProjectIndex` and `PersonCheckEngine._build_context`. Callers that render many rows (person list, overview) build it once per refresh and query it per row. There is no persisted index and no invalidation protocol (Requirement 12).
3. **Mutation through `ProjectService` + dirty flag.** All creates/updates/deletes go through `ResearchService` functions invoked by `ProjectService` methods that set `self._dirty = True`, matching `add_event`/`update_event`/`delete_event` (Requirement 1.10, 29.8).
4. **Reference integrity without destruction.** Deleting an entity never deletes research; merging rewires research references to the survivor. Broken references are kept and surfaced by the validator and the consistency report (Requirements 27, 29.7).
5. **Open views refresh on a notification.** Rebuilding the index does not repaint drawn widgets; an `Application.research_changed` signal fans out to every open research-aware view's `refresh()` (Requirement 13).

## Components and Interfaces

### 1. Model — `slaktbusken/model/research_case.py`

All plain `@dataclass` with `id` first, `from __future__ import annotations`, no Qt/IO imports — matching `residence.py`.

```python
@dataclass
class ResearchEntityLink:
    """A reference from research data to a project entity.

    Mirrors model.media.LinkedEntity. `role` is a free-text relationship
    descriptor (e.g. "candidate", "research_context"); empty when unused.
    """
    entity_type: str          # one of SUPPORTED_ENTITY_TYPES
    entity_id: str
    role: str = ""


@dataclass
class HypothesisComment:
    """A dated free-text observation about a hypothesis."""
    id: str
    date: str = ""            # "" or a Valid_Calendar_Date (YYYY / YYYY-MM / YYYY-MM-DD)
    text: str = ""


@dataclass
class ResearchHypothesis:
    """A proposed explanation belonging to one research case."""
    id: str
    research_case_id: str
    statement: str = ""
    assessment: str = "unassessed"   # VALID_HYPOTHESIS_ASSESSMENTS
    reasoning: str = ""
    linked_entities: list[ResearchEntityLink] = field(default_factory=list)
    comments: list[HypothesisComment] = field(default_factory=list)


@dataclass
class ResearchAction:
    """Planned or completed research work belonging to one research case."""
    id: str
    research_case_id: str
    title: str = ""
    text: str = ""
    # None => pending. A completed action holds a non-empty Valid_Calendar_Date.
    # An empty string is never stored: normalize_completed_date() maps ""/whitespace
    # to None in __post_init__ and wherever the editor sets the field.
    completed_date: Optional[str] = None
    sort_order: int = 0
    source_refs: list[SourceRef] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Normalized_Completion_Date (Req 7): an empty or whitespace-only value
        # can never represent a completed action, so collapse it to None.
        self.completed_date = normalize_completed_date(self.completed_date)


@dataclass
class ResearchCase:
    """A research question that may concern zero or more project entities."""
    id: str
    title: str = ""
    description: str = ""
    status: str = "open"             # VALID_RESEARCH_STATUSES
    priority: str = "normal"         # VALID_RESEARCH_PRIORITIES
    conclusion: str = ""
    primary_entity_ref: Optional[ResearchEntityLink] = None
    linked_entities: list[ResearchEntityLink] = field(default_factory=list)
```

Module-level constants (English keys):

```python
SUPPORTED_ENTITY_TYPES = frozenset({
    "person", "family", "event", "place",
    "source", "media", "dna_match", "dna_cluster",
})
VALID_RESEARCH_STATUSES   = ("open", "in_progress", "on_hold", "closed")
VALID_RESEARCH_PRIORITIES = ("low", "normal", "high")
VALID_HYPOTHESIS_ASSESSMENTS = (
    "unassessed", "possible", "strong_support", "confirmed", "rejected",
)
```

Pure helpers (no mutation):
- `is_pending(action: ResearchAction) -> bool` — `action.completed_date is None` (Requirement 6.4).
- `case_entity_links(case) -> list[ResearchEntityLink]` — `primary_entity_ref` first then `linked_entities`, used by the index and dedupe.
- `count_links_for_entity(case, entity_type, entity_id) -> int` — count of links to one entity (for the dedupe warning, Requirement 3.7).
- `normalize_completed_date(value) -> Optional[str]` — returns `None` for `None`, empty, or whitespace-only input, otherwise the trimmed string. The single chokepoint that enforces Normalized_Completion_Date (Requirement 7); called from `ResearchAction.__post_init__`, the editor's completion-control handler, and the deserializer so no path can land an empty string in `completed_date`.
- `is_valid_calendar_date(value) -> bool` — true for a non-empty string that is both ISO-8601-shaped (ÅÅÅÅ / ÅÅÅÅ-MM / ÅÅÅÅ-MM-DD) **and** a real calendar date. It composes the project's existing date utilities in `slaktbusken/services/checks/date_utils.py`: `parse_date_value` (which only range-checks month 1–12 and day 1–31 — not enough on its own, it accepts "2026-02-30") **followed by** `is_valid_swedish_calendar`, which performs true days-in-month and leap-year validation. Using the shape-only `_ISO_DATE_RE` alone, or `parse_date_value` alone, would wrongly accept "2026-02-30"; the composition rejects it and "2026-13-01" (Requirements 5.5, 6.7, 7). Year and month precision are accepted; day precision is permitted but never required for a completion or comment date. (The helper wraps the plain string in a `DateValue(value, precision="exact")` to call `parse_date_value`, then checks the returned `ParsedDate` with `is_valid_swedish_calendar`.)

Design decisions:
- **`source_refs` uses `SourceRef`** (from `model/event.py`), the one citation type used across events, places, and residences, satisfying Requirement 9.6 (no incompatible duplicate structure). A `SourceRef` whose `source_id` resolves to a Source is a reference to that Source; page-level nuance remains in the Source's own `structured_reference`, exactly as residence observations work. A `source_ref` on a Research_Action records a Source **examined** during the work, not **evidence** for a hypothesis: no code derives hypothesis support from it, the editor frames it under a "Granskade källor" section, and hypothesis evidence is expressed only through `reasoning` and `HypothesisComment`s (Requirements 9.7–9.9).
- **Hypotheses/actions are top-level collections** keyed back to their case by `research_case_id`, matching the starter's persistence block and letting the index and consistency report iterate them without walking every case. Hypothesis comments nest inside their hypothesis (Requirement 29.1).
- **`primary_entity_ref` reuses `ResearchEntityLink`** with `role` unused, avoiding a second reference type.

### 2. Validators — `slaktbusken/model/validators.py`

New functions following the established signature `validate_<entity>(entity, valid_*_ids=None) -> list[str]`, referential checks gated on optional id-sets so the functions stay pure.

```python
def validate_research_case(
    case: ResearchCase,
    valid_entity_ids: Optional[dict[str, set[str]]] = None,  # entity_type -> ids
) -> list[str]: ...

def validate_research_hypothesis(
    hyp: ResearchHypothesis,
    valid_case_ids: Optional[set[str]] = None,
    valid_entity_ids: Optional[dict[str, set[str]]] = None,
) -> list[str]: ...

def validate_research_action(
    action: ResearchAction,
    valid_case_ids: Optional[set[str]] = None,
    valid_source_ids: Optional[set[str]] = None,
) -> list[str]: ...
```

Messages are the exact Swedish strings in the requirements. `completed_date` and comment `date` are validated with `is_valid_calendar_date` (real calendar date, not shape-only) rather than `_ISO_DATE_RE` alone, so an impossible day such as "2026-02-30" is an error (Requirements 5.5, 6.7, 7). `valid_entity_ids` is a per-type id-set map the caller builds once from `ProjectData` (persons/families/events/places/sources/media/dna_matches/dna_clusters). The unknown-type / missing-entity checks (3.4, 3.5) live in the `validate_*` functions. The duplicate-link check (Requirement 3.7) is a warning, not an error, so it lives in `research_case_findings(case)`, which returns `ResearchFinding(case_id, severity, message)` objects exactly as `event_findings` does for events; it yields one finding per case however many duplicates there are. `validate_research_hypothesis` also validates the hypothesis's nested comments, so validating a whole Working_Copy is one call per entity. A dedicated `validate_hypothesis_comment` checks the `date` as a Valid_Calendar_Date (Requirement 5.5). `validate_research_action` also treats an empty-string `completed_date` as a normalization fault that should already have been collapsed to `None`; because the model normalizes on construction, the validator sees only `None` or a non-empty value and never needs a separate "empty string" branch.

`ProjectService` add/update methods call these with `None` id-sets (shape validation only, matching `add_person`/`add_event`); the `ValidationService` and the consistency report call them with full id-sets for referential checks.

### 3. IDs and non-reuse — `slaktbusken/model/id_generator.py` + persisted high-water mark

Add to `_PREFIXES`:

```python
'research_case': 'case_',
'research_hypothesis': 'hypothesis_',
'research_action': 'action_',
'hypothesis_comment': 'hypcomment_',
```

**The non-reuse problem (Requirement 2).** `IDGenerator`'s docstring claims ids are "never reused, even after deletion", but that guarantee holds **only within one generator instance's lifetime**. Every call site seeds the generator from the entities *currently present* — `IDGenerator({p.id for p in data.persons})`, `residence_editor._make_id_generator`, etc. The next-suffix is `high_water_mark(prefix) + 1`, where the high-water mark is computed over the seed set. So if you create `case_7`, delete it, save, and reopen, the seed set no longer contains `case_7`, the high-water mark falls back to 6, and the next created case becomes `case_7` again — reusing a freed id. For research data this is dangerous: a dangling reference (kept on purpose for the consistency report) could silently re-point at a brand-new, unrelated case after a reopen.

Verified in code: `id_generator.py` derives the mark from `self._used_ids` only, and no call site persists or re-seeds a mark across sessions. The claim is therefore not implementable with the current seeding pattern alone.

**Chosen mechanism — persisted per-prefix high-water mark (Requirement 2 option a).** Add a small persisted map on the project, `ProjectData.id_high_water_marks: dict[str, int]` (prefix → highest suffix ever issued). On every research id generation, the issued suffix updates the stored mark via `max`. When a generator is constructed for research ids, it is seeded both from the live research ids **and** from the persisted marks, so a reopened project's mark never regresses below any id ever issued. This:
- keeps ids human-readable (`case_8` after `case_7` is deleted, not `case_7` reused),
- round-trips with the research collections under the same backward-compatibility rules — absent map on a pre-feature project defaults to `{}` and is reconstructed lazily from the max live suffix on first write (Requirement 2.4),
- requires no change to the format of existing non-research ids (the map is additive and, for research, authoritative).

A thin `ResearchIdGenerator` wrapper (or a helper in `research_service.py`) owns this: it builds an `IDGenerator` seeded from live research ids **and** `max(mark, live_high_water)` per research prefix, generates, and writes the new mark back. Serialization adds `id_high_water_marks` as a plain `dict[str,int]` (omitted when empty, like `connection_overrides`); the 0.2→0.3 migration does not need to add it (absent defaults to `{}`), but the loader initializes it from existing research ids if research data is present without a stored map.

Alternative options considered and rejected for v1: a full project-wide used-id ledger (heavier, duplicates information already in the entities) and UUID ids (breaks the human-readable `case_N` convention the rest of the app uses). The persisted-mark approach is the smallest change that actually satisfies non-reuse.

### 4. Persistence — `serialization.py`, `migration.py`, `file_io.py`

**`serialization.py`:**
- Append `"research_cases", "research_hypotheses", "research_actions"` to the `entity_fields` list in `serialize()`.
- Add to `_ENTITY_MAP`: `"research_cases": ResearchCase`, `"research_hypotheses": ResearchHypothesis`, `"research_actions": ResearchAction`.
- Add to `_NESTED_LIST_TYPES`: `(ResearchCase, "linked_entities"): ResearchEntityLink`, `(ResearchHypothesis, "linked_entities"): ResearchEntityLink`, `(ResearchHypothesis, "comments"): HypothesisComment`, `(ResearchAction, "source_refs"): SourceRef`.
- Add to `_NESTED_OPTIONAL_TYPES`: `(ResearchCase, "primary_entity_ref"): ResearchEntityLink`.
- The existing omit-defaults behavior gives the round-trip guarantees of Requirement 29.2 for free: `completed_date` is `Optional[str]` with default `None` so absent stays absent; empty strings with `default=""` are omitted and restored as `""`; `sort_order` has default `0` (an int, not omitted by the empty-string/empty-list rules, so it round-trips).
- Add a `_deserialize_research(raw_items, log)` guard mirroring `_deserialize_residences`: unknown fields ignored and logged with the entity id; present-but-not-a-list research section raises `CorruptedFileError` with a Swedish message naming the section (Requirement 29.6); unresolved references kept and logged (Requirement 29.7); any empty-string `completed_date` normalized to `None` on load.
- Persist `id_high_water_marks: dict[str, int]` (Requirement 2) as a plain dict, omitted when empty like `connection_overrides`. On load, if research data is present but the map is absent, initialize each research prefix's mark from the max live suffix so non-reuse holds going forward.

**`migration.py`:** set `CURRENT_VERSION = "0.3"` and register:

```python
@MigrationManager.register("0.2", "0.3")
def _migrate_0_2_to_0_3(data: dict) -> dict:
    for key in ("research_cases", "research_hypotheses", "research_actions"):
        if key not in data:
            data[key] = []
    data["format_version"] = "0.3"
    data["version"] = "0.3"
    return data
```

Idempotent (only adds missing keys), bumps both version fields (Requirement 29.4).

**`file_io.py`:** set `CURRENT_VERSION = "0.3"` so the newer-version guard and migration path work. `ProjectData.version` default becomes `"0.3"` and `ProjectService.create_project` writes `version="0.3"`.

### 5. Research Index — `slaktbusken/services/research_index.py`

A dataclass bundle built once from `ProjectData`, following `foster_sync._ProjectIndex`. No caching across calls, no invalidation protocol.

```python
@dataclass
class ResearchCaseCounts:
    non_closed: int
    total: int

class ResearchIndex:
    def __init__(self, data: ProjectData) -> None:
        # Build reverse maps once:
        #   _cases_by_entity: (entity_type, entity_id) -> list[ResearchCase]  (deduped, resolving only)
        #   _actions_by_case: case_id -> list[ResearchAction]
        #   _hypotheses_by_case: case_id -> list[ResearchHypothesis]
        #   _actions_by_source: source_id -> list[ResearchAction]
        #   _hypotheses_by_entity: (entity_type, entity_id) -> list[(hyp, case)]  (separate!)
        ...
    def cases_for_entity(self, entity_type, entity_id) -> list[ResearchCase]: ...
    def counts_for_entity(self, entity_type, entity_id) -> ResearchCaseCounts: ...
    def actions_for_source(self, source_id) -> list[ResearchAction]: ...
    def actions_for_case(self, case_id) -> list[ResearchAction]: ...
    def hypotheses_for_case(self, case_id) -> list[ResearchHypothesis]: ...
    def pending_action_count(self, case_id) -> int: ...
    # Hypotheses that explicitly reference an entity via their linked_entities,
    # each paired with its owning case. Powers "Förekommer i hypoteser"
    # (Req 12.9, 22). Kept in a separate map so it never feeds indicators.
    def hypotheses_for_entity(
        self, entity_type, entity_id
    ) -> list[tuple[ResearchHypothesis, ResearchCase]]: ...
```

Build detail: `_cases_by_entity` dedupes per case using `case_entity_links` so a case linking an entity through both `primary_entity_ref` and `linked_entities` appears once (Requirements 3.8, 12.2, 12.3), and — crucially for broken references — is keyed on links whose referenced entity still resolves in `ProjectData`, so a dangling link contributes to no entity-keyed lookup, no indicator, and no count (Requirement 26.3). A separate `_hypotheses_by_entity` map keys each hypothesis by the entities its `linked_entities` name; it is never merged into `_cases_by_entity`, keeping the "Förekommer i hypoteser" relationship out of indicator counts (Requirements 12.9, 22.3). `non_closed` counts cases whose `status != "closed"`. The build is O(cases + links + actions + hypotheses); lookups are dict hits (Requirement 12.8). The index is pure and read-only (Requirement 12.1).

### 6. Research Service — `slaktbusken/services/research_service.py` + `ProjectService`

Pure module functions plus `ProjectService` methods, matching the delete-service split.

`ProjectService` gains:
- `add_research_case(case)`, `update_research_case(case)`, `delete_research_case(case_id)` — the delete also removes that case's hypotheses and actions (they are meaningless without their case) but leaves all other research untouched.
- `add_research_hypothesis`, `update_research_hypothesis`, `delete_research_hypothesis`.
- `add_research_action`, `update_research_action`, `delete_research_action`.
- `commit_research_case_working_copy(working_copy)` — the single transactional entry point the Research_Case_Editor calls on save (below).

Each validates (shape only, `None` id-sets) via the Research_Validator, mutates the collection in place, sets `self._dirty = True`, and emits the Research_Changed_Notification (section 6a), exactly like `add_event` plus the new signal. New ids are issued through the persisted-high-water-mark `ResearchIdGenerator` of section 3 so deleted ids are never reused across save/reopen.

**Transactional editing (Working_Copy, Requirement 19.8–19.11).** The Research_Case_Editor never mutates `ProjectData`. It is handed a deep copy — the `ResearchCase` plus copies of its `ResearchHypothesis`, `HypothesisComment`, and `ResearchAction` objects (new entities get provisional ids from the generator). All edits, completions, reorders, and comment changes happen on this Working_Copy. On save, `commit_research_case_working_copy`:
1. validates the entire Working_Copy (case + every hypothesis + every comment + every action) via the Research_Validator and the editor-level rules (non-empty title, Requirement 19.12);
2. if any error, returns the Swedish messages and writes nothing — `ProjectData` is untouched and the editor stays open with edits intact (Requirement 19.9);
3. if valid, computes the diff against the current `ProjectData` (cases/hypotheses/actions created, updated, deleted) and applies it as one in-memory operation, then sets dirty and emits the notification (Requirement 19.10).
On cancel or a failed commit, the Working_Copy is discarded and `ProjectData` is exactly as before (Requirement 19.11). This is the application-model transaction; it does not need DB-style rollback because nothing is written until step 3, and step 3 is a plain list reassignment that either fully happens or is not reached.

`research_service.py` pure functions:
- `find_research_dependencies(data, entity_type, entity_id) -> ResearchDependencies` — returns the cases, hypotheses, and actions referencing an entity (Requirement 27.5); used to report consequences, never to delete. Also reused to build the counts shown in the delete-confirmation dialog (section 14a).
- `delete_case_cascade(data, case_id) -> DeletedResearchCounts` — removes a case and exactly its own hypotheses, comments, and actions, returning the counts for the confirmation dialog (Requirement 20). Leaves all other research and every genealogical fact untouched.
- `rewire_entity_merge(data, entity_type, old_id, survivor_id) -> None` — rewrites every `ResearchEntityLink` and `ResearchAction.source_ref` from `old_id` to `survivor_id`, then collapses any link duplicated within a case (Requirement 27.3, 27.4). It rewires **only the referenced id**: a rewired `SourceRef` keeps its `quality`, `note`, and `aspects`; a rewired `ResearchEntityLink` keeps its `role` (Requirements 27.6, 27.7). When collapsing a duplicate link within a case it keeps a non-empty `role` over an empty one, else the first in order. This fills the codebase gap (no existing reference-rewiring helper) and is the one place merges call.
- `remove_entity_association(case, entity_type, entity_id) -> ResearchCase` — drops a single link from a case without deleting the case (Requirement 21.2, 20.4); if the removed link was the `primary_entity_ref`, `primary_entity_ref` becomes `None` and no other link is auto-promoted (Requirement 19.4).

### 6a. Refresh of open views — `Research_Changed_Notification`

Rebuilding the `ResearchIndex` does not repaint a widget that is already on screen, so the design adds an explicit notification (Requirement 13). The simplest fit for the existing Qt/`Application` structure is a single Qt signal owned by `Application` (e.g. `research_changed = Signal()`), emitted by every `ProjectService` research mutation and by the merge/delete rewire paths. `Application` connects it to the refresh entry points of every open research-aware view: the person list (`refresh()`), the diagram panel (re-render), any open `ResearchOverview` windows, and the research tab/section of each open person/place/source/event/media/DNA editor. Each handler builds a fresh `ResearchIndex` and re-reads its rows, indicators, counts, and tooltips, preserving selection and scroll position where practical and never discarding unsaved edits in a view that did not originate the change (Requirement 13.6, 30.4). Views register/deregister their refresh slot on open/close so the signal fans out only to live widgets. This keeps the index pure and stateless while making open windows consistent.

### 7. Delete / Merge integration — `slaktbusken/services/delete_service.py`

- `execute_person_deletion` and the other entity deletions **do not** remove research entities and **do not** null research references (Requirement 27.1, 27.2). The stale link is kept on purpose so the consistency report can surface it. After such a deletion `Application` emits the Research_Changed_Notification so open views drop the now-broken entity from their navigable research links.
- Add `find_research_dependencies` reporting (delegating to `research_service`) so a deletion dialog can list affected research, mirroring `find_residence_dependencies`.
- Wherever the app merges entities, call `research_service.rewire_entity_merge` as part of the merge so research references follow the survivor, preserving `SourceRef.quality/note/aspects` and link `role` (Requirement 27.3, 27.6, 27.7), then emit the notification. Since no general person-merge exists yet, this design provides the rewire helper and wires it into whatever merge entry points exist; the helper is the contract.
- **Broken-reference display policy (Requirement 26).** A kept-but-dangling link is never shown as a valid navigable link. The `ResearchIndex` entity-keyed maps only contain links whose target resolves, so broken links never reach an indicator or count. Where a research tab or the editor's "Berörda objekt" must still show a dangling link so the user can repair it, it renders with a Swedish "(saknat objekt)" marker and offers removal (via `remove_entity_association`) or relinking, following the association-removal rules, deleting no case.

### 8. Source aspects — `slaktbusken/services/source_aspects.py`

Add a `research_case` entry to `ENTITY_SOURCE_ASPECTS` with aspect keys and Swedish labels in `ASPECT_LABELS`, so a `SourceRef` cited from a research action can carry aspects consistent with the rest of the app, framed as an examined source (Requirement 9.6–9.8):

```python
ENTITY_SOURCE_ASPECTS["research_case"] = ["examined", "result", "transcription"]
ASPECT_LABELS.update({
    "examined": "Granskad", "result": "Resultat", "transcription": "Avskrift",
})
```

### 9. Consistency report — `slaktbusken/reports/research_consistency.py` + `generator.py`

Follows `geographic.py` exactly: an Issue dataclass, a pure check function, a generate function returning `ReportContent`.

```python
@dataclass
class ResearchIssue:
    severity: str        # "error" | "info" (grouping only; framework has no enum)
    check_type: str      # e.g. "missing_entity", "orphan_hypothesis", ...
    message: str         # Swedish, render-ready, naming the affected case
    # Identity of the affected research entity, for a future "navigate from
    # report" feature (Requirement 25.6). The rendered ListBlock line stays
    # plain Swedish text; these fields travel on the issue, not in the string.
    case_id: str | None = None
    hypothesis_id: str | None = None
    action_id: str | None = None
    comment_id: str | None = None
    # For a broken reference: the stored link target that no longer resolves.
    ref_entity_type: str | None = None
    ref_entity_id: str | None = None

def check_research_consistency(data: ProjectData) -> list[ResearchIssue]: ...

def generate_research_consistency_report(data: ProjectData) -> ReportContent:
    report = ReportContent(title="Forskningskonsistens")
    # Two top-level areas: "Fel" then "Informationspunkter", each a set of
    # HeadingBlock(level=2) + ListBlock / EmptyStateBlock("Inga problem hittades.")
    ...
```

`check_research_consistency` builds the per-type id-sets once, runs every error check of Requirement 25.2 and every informational check of 25.3, tags each issue `error` or `info`, and populates the identity fields so a later navigation feature can open the affected case/hypothesis/action/comment or the broken reference (Requirement 25.6). Each `message` names the owning Research_Case by title or `id` so the finding is actionable on its own (Requirement 25.7). The generate function groups by severity then by `check_type` into labelled Swedish sections — the established way to express severity without a framework enum. `ReportGeneratorService` gets a `generate_research_consistency(self, data)` method.

### 10. GEDCOM — `slaktbusken/gedcom/exporter.py`

Only `_collect_omissions` changes: add counts for `research_cases`, `research_hypotheses`, and `research_actions` under a Swedish label ("Forskningsärenden", and optionally sub-labels), exactly as `research_notes` ("Forskningsanteckningar") is already reported (Requirement 28.5). The importer needs no change: it only overwrites GEDCOM-derived fields of matched entities and preserves app ids via `TranslationData`/`PersonMapping`, so research referencing those ids survives re-import and no duplicate research is created (Requirements 28.1–28.4). A verification test asserts this; no production importer code is modified.

### 11. UI — reusable research tab — `slaktbusken/ui/widgets/research_tab.py`

A `ResearchTab(QWidget)` modeled on `BoendenTab`: given the project data, an `(entity_type, entity_id)`, and a `ResearchIndex`, it lists the directly linked cases and emits signals the host editor connects:

```python
class ResearchTab(QWidget):
    open_case_requested = Signal(str)            # case_id
    create_case_requested = Signal()
    link_existing_requested = Signal()
    remove_association_requested = Signal(str)   # case_id
    open_hypothesis_case_requested = Signal(str) # case_id (from the hypotheses section)

    def refresh(self) -> None: ...   # rebuilds from a fresh ResearchIndex
```

It renders two parts: a **directly-linked cases** list (status, priority, pending indicator) driving the create/link/open/remove signals, and a separate **"Förekommer i hypoteser"** section listing `index.hypotheses_for_entity(entity_type, entity_id)` — each row showing the hypothesis `statement`, its assessment, and its owning case title, opening the owning case on activation (Requirements 22, 12.9). The hypotheses section is visually and logically separate from the case list and never contributes to indicator counts (Requirement 22.3). A dangling link the editor must show for repair is marked "(saknat objekt)" and offers removal only (Requirement 26.2). The widget exposes `refresh()` so `Application` can repaint it on a Research_Changed_Notification (Requirement 13).

Every integrating editor (person, place, event, media, source, DNA) inserts this one widget, satisfying the "reuse over per-type implementations" rule (Requirement 30.5). The source editor uses a richer variant (below) but shares the case-list part.

Host editors insert it the way `PersonEditor._setup_boenden_tab` inserts `BoendenTab`:

```python
def _setup_forskning_tab(self) -> None:
    self._forskning_tab = ResearchTab(self._project_data, ("person", self._person.id), index)
    idx = self._ui.tab_widget.indexOf(self._ui.photos_tab)
    self._ui.tab_widget.insertTab(idx, self._forskning_tab, "Forskning")
    self._forskning_tab.create_case_requested.connect(self._on_create_research_case)
    ...
```

`_on_create_research_case` opens the `ResearchCaseEditor` via `Application`, prepopulating the current entity as `primary_entity_ref` (Requirement 21.3). The event and DNA editors, which may lack a `QTabWidget`, embed the same widget in a compact section instead (Requirement 21.5, 21.8).

### 12. UI — source editor research tab

The source editor's "Forskning" tab has two sections (Requirement 23):
- **"Forskningsärenden om denna källa"** — `index.cases_for_entity("source", source_id)`.
- **"Forskningsåtgärder där källan används"** — `index.actions_for_source(source_id)`, each row showing title, completion state, `completed_date`, owning case title and status (resolved at render time), with navigation to the action, its case, and to create a source-linked case. Aggregate case counts use the distinct set of owning case ids (Requirement 23.5). This section lists the source as an **examined** source (consistent with the "Granskade källor" framing of action source refs, Requirement 9.8); it never presents an action's use of the source as evidence for any hypothesis (Requirement 9.7).

### 13. UI — Research Overview — `slaktbusken/ui/research_overview.py`

A window built like other `Application`-opened dialogs: `Application.show_research_overview(initial_mode)` creates a `QDialog(self.main_window)` hosting the overview widget. The overview has **three modes over the same window and data** (Requirement 18.2), selected by the three menu items and switchable in the window:
- **Case mode ("Forskningsöversikt")** — a `QTableWidget`/`QTreeWidget` of cases with the columns of Requirement 18.3, the filter bar of Requirement 18.4, a "visa avslutade" toggle, and create/open buttons.
- **To-do mode ("Att göra")** — pending actions, default excluding closed cases with an include toggle, each row showing its owning case title and navigating to both action and case (Requirement 18.6, 18.7).
- **Hypothesis mode ("Hypoteser")** — a table with **one row per Research_Hypothesis** (not per case), showing `statement`, assessment (via the locale label), and owning case title, with sorting and free-text search over statement and case title, opening the owning case on activation. This replaces the earlier "cases that have hypotheses" filter so the view lists individual hypotheses (Requirement 18.8, 18.9).
All three modes share one window, one data source, and no separate persistence. The overview registers a `refresh()` slot for the Research_Changed_Notification (Requirement 13).

### 14. UI — Research Case Editor — `slaktbusken/ui/editors/research_case_editor.py`

A `QWidget` with `save_requested`/`cancel_requested` signals (the standard editor contract) that **edits a Working_Copy** (section 6a / Requirement 19.8–19.11): on open it deep-copies the case and its hypotheses, comments, and actions; all UI edits mutate only the copy; nothing reaches `ProjectData` until a validated transactional commit. It contains: Frågeställning (title + description), Status and Prioritet combos (Swedish labels mapped to internal values via `swedish_locale` getters), Berörda objekt (link list with add/remove/set-primary and navigation; removing the primary link clears `primary_entity_ref` with no auto-promote, Requirement 19.4; dangling links shown "(saknat objekt)"), Hypoteser (list of hypotheses each with assessment combo, reasoning, and a dated-comments sub-list that defaults a new comment's date to today and never stores an empty-string date), Nästa åtgärder and Genomförda åtgärder (two lists driven by `completed_date`, with the "Åtgärden genomförd" checkbox, editable "Färdigdatum", drag-reorder for pending, and an examined-source attach/detach under "Granskade källor"; clearing the date while checked never stores an empty string — it normalizes to `None`), and Slutsats.

On save the editor calls `commit_research_case_working_copy`: the whole Working_Copy is validated first, and if any error (including an empty `title`, Requirement 19.12, message "Forskningsärendet måste ha en rubrik.") the editor shows the Swedish messages and writes nothing (Requirement 19.9). A valid commit applies all creates/updates/deletes atomically, sets dirty, and emits the notification (Requirement 19.10); cancel or a failed commit discards the copy leaving `ProjectData` unchanged (Requirement 19.11). The closing-warning dialog (Requirement 10.2) fires only on a status transition into `closed` with pending actions and is non-blocking. Deleting the case from the editor routes through the destructive-delete confirmation of section 14a.

### 14a. UI — destructive case-deletion confirmation

Both the Research_Overview and the Research_Case_Editor delete a case through one confirmation path (Requirement 20). Before deleting, the caller computes the child counts via `find_research_dependencies`/`delete_case_cascade`'s count and shows a `QMessageBox` with the Swedish body "Att ta bort forskningsärendet tar även bort {h} hypoteser, {k} hypoteskommentarer och {å} forskningsåtgärder. Detta kan inte ångras." and buttons "Ta bort" / "Avbryt". Confirm runs `delete_case_cascade` (case + its own children only), sets dirty, emits the notification; cancel changes nothing. This is wording-distinct from "ta bort kopplingen" (remove association), which drops a single link via `remove_entity_association` and shows no case-deletion warning (Requirement 20.4, 20.5).

### 15. UI — indicators, person list column, diagram, settings

- **`slaktbusken/ui/widgets/research_indicator.py`** — a small helper returning indicator state (`none`/`grey`/`orange`) and tooltip text from `ResearchCaseCounts`, so the list delegate, the diagram box, and other entity views share one rule (Requirement 14). Colours: orange for any non-closed case, neutral grey when all closed, nothing when zero; never green.
- **Person list** (`person_list_panel.py`) — add a "Forskningsärenden" column. `build_person_display_list` takes the `ResearchIndex` and fills a `research_counts: ResearchCaseCounts | None` field on `PersonDisplayInfo`; the cell renders "{open}/{total}" with the indicator colour. Sorting adds a research key (non-closed then total) to the data-level sort. Visibility extends `PersonListConfig` (`research: bool`) and the `ColumnVisibility` dataclass (`research: bool`), wired through `apply_person_list_config` / the header context menu exactly like the existing columns (Requirement 15).
- **Diagram** (`widgets/person_box.py`) — add a `research: bool` field to `PersonBoxConfig`; `_build_lines` paints a compact indicator when set, using `research_indicator`. The settings dialog diagram tab gains a "Forskningsärenden" checkbox in "Personruta – synliga fält". Clicking it opens the person's research (Requirement 16.3). Person-list and diagram settings are separate fields, hence independent (Requirement 16.5).
- **Settings** — new boolean fields on `PersonListConfig`, `PersonBoxConfig`, and `ColumnVisibility`; `_deserialize_settings` already defaults missing keys, so old settings files load unchanged.

### 16. UI — filter dialog — `slaktbusken/ui/dialogs/filter_dialog.py`

Refactor `_setup_ui` into a two-column `QHBoxLayout` of two `QVBoxLayout`s (left: Namnfilter, Datumintervall, Församling, DNA-kluster; right: Händelsetyper scroll + Forskningsärenden), inside a resizable scrollable dialog, keeping the Filtrera/Rensa row at the bottom (Requirement 24.1, 24.2). Add a "Forskningsärenden" group with three combos (existence, status, action). Extend `FilterCriteria` with `research_existence`, `research_status`, `research_action` fields and extend `filter_persons` to apply them through a `ResearchIndex` passed in alongside the existing arguments. The combined status+action filter evaluates both conditions against the *same* linked case of the person (Requirement 24.7) by checking per-case rather than per-person aggregates. `_on_clear` resets the new combos to their "Alla" default (Requirement 24.9).

### 17. UI — menu and Application wiring

- `main_window.py`: `_setup_actions` adds `action_research_overview`, `action_research_todo`, `action_research_hypotheses`, each `triggered`-connected to an `Application` method; `_setup_menu_bar` adds `menu_bar.addMenu("&Forskning")` between Verktyg and Karta; `_update_project_actions` toggles the three (Requirement 18.1).
- `app.py`: `show_research_overview(initial_mode="overview"|"todo"|"hypotheses")` and `open_research_case(case_id=None, prepopulate=None)` follow the `show_dna_editor`/`open_person_editor` pattern (build `QDialog`, host widget, connect save/cancel, `exec()`, on accept write to `project_service.data`, set dirty). `Application` owns the `research_changed` signal (section 6a); every research mutation, merge rewire, and entity deletion that affects research emits it, and `Application` fans it out to the `refresh()` slots of the person list, the diagram, every open `ResearchOverview`, and the research tab/section of every open entity editor, so already-open windows update without reopening (Requirement 13). Open windows register and deregister their refresh slot on show/close.
- `report_menu.py`: promote a "Forskningsrapporter"/"Konsistensrapporter" placeholder to `self.action_research_consistency`; `main_window` connects it to a `_generate_research_consistency` handler that builds `ReportContent` and shows `ReportPreviewDialog`.

### 18. Localization — `slaktbusken/ui/swedish_locale.py`

Add label dicts and getters with the existing fallback-to-key convention:

```python
RESEARCH_STATUS_LABELS   = {"open":"Öppen","in_progress":"Pågår","on_hold":"Vilande","closed":"Avslutad"}
RESEARCH_PRIORITY_LABELS = {"low":"Låg","normal":"Normal","high":"Hög"}
HYPOTHESIS_ASSESSMENT_LABELS = {
    "unassessed":"Ej bedömd","possible":"Möjlig","strong_support":"Starkt stöd",
    "confirmed":"Bekräftad","rejected":"Avfärdad",
}
RESEARCH_ENTITY_TYPE_LABELS = {
    "person":"Person","family":"Familj","event":"Händelse","place":"Plats",
    "source":"Källa","media":"Media","dna_match":"DNA-matchning","dna_cluster":"DNA-kluster",
}
```

Plus `get_research_status_label`, `get_research_priority_label`, `get_hypothesis_assessment_label`, and reverse `*_from_label` lookups for the editor combos.

## Data Models

### JSON shape (on disk, inside the gzipped project)

```json
{
  "format": "släktbuske-file",
  "version": "0.3",
  "format_version": "0.3",
  "project": { "...": "..." },
  "persons": [], "families": [], "events": [], "residences": [],
  "places": [], "sources": [], "media": [],
  "research_cases": [
    {
      "id": "case_1",
      "title": "Vem var Anna Andersdotters far?",
      "description": "Fadern anges inte i födelseboken.",
      "status": "in_progress",
      "priority": "high",
      "primary_entity_ref": { "entity_type": "person", "entity_id": "person_123" },
      "linked_entities": [
        { "entity_type": "person", "entity_id": "person_789", "role": "candidate" },
        { "entity_type": "event",  "entity_id": "event_456",  "role": "research_context" }
      ]
    }
  ],
  "research_hypotheses": [
    {
      "id": "hypothesis_1",
      "research_case_id": "case_1",
      "statement": "Per Persson är Annas biologiska far.",
      "assessment": "possible",
      "comments": [
        { "id": "hypcomment_1", "date": "2026-10-30",
          "text": "En ny DNA-matchning stärker hypotesen, men ytterligare belägg behövs." }
      ]
    }
  ],
  "research_actions": [
    {
      "id": "action_1",
      "research_case_id": "case_1",
      "title": "Kontrollera Ljusdal AI:17",
      "text": "Personen återfanns inte.",
      "sort_order": 1,
      "source_refs": [ { "source_id": "source_42", "quality": "secondary" } ]
    }
  ],
  "id_high_water_marks": { "case_": 1, "hypothesis_": 1, "action_": 1, "hypcomment_": 1 }
}
```

Note how omit-defaults keeps the JSON clean: `conclusion`, empty `linked_entities`, and an absent `completed_date` simply do not appear and are restored to their defaults on load (Requirement 29.2, 29.3). A pending action never carries a `completed_date` key at all (the field is `None`); an empty-string value is never written because the model normalizes it to `None` (Requirement 7). `id_high_water_marks` (Requirement 2) persists the highest suffix ever issued per research prefix so a deleted id is not reused after reopen; it is omitted when empty and, if absent on a project that already holds research data, is reconstructed on load from the maximum live suffix per prefix.

### Field reference

| Entity | Field | Type | Default | Notes |
|---|---|---|---|---|
| ResearchCase | id | str | — | prefix `case_` |
| | title | str | "" | ≤200 |
| | description | str | "" | ≤10000 (Frågeställning) |
| | status | str | "open" | open/in_progress/on_hold/closed |
| | priority | str | "normal" | low/normal/high |
| | conclusion | str | "" | ≤10000; independent of status |
| | primary_entity_ref | ResearchEntityLink? | None | optional |
| | linked_entities | list[ResearchEntityLink] | [] | ordered |
| ResearchHypothesis | id / research_case_id | str | — | prefixes `hypothesis_` |
| | statement | str | "" | ≤1000 |
| | assessment | str | "unassessed" | manual only |
| | reasoning | str | "" | ≤10000 |
| | linked_entities | list[ResearchEntityLink] | [] | |
| | comments | list[HypothesisComment] | [] | nested |
| HypothesisComment | id | str | — | prefix `hypcomment_` |
| | date | str | "" | "" or Valid_Calendar_Date |
| | text | str | "" | ≤10000 |
| ResearchAction | id / research_case_id | str | — | prefix `action_` |
| | title | str | "" | ≤200 |
| | text | str | "" | ≤10000 |
| | completed_date | str? | None | None ⇒ pending; never ""; Valid_Calendar_Date when set |
| | sort_order | int | 0 | manual order for pending |
| | source_refs | list[SourceRef] | [] | reuses SourceRef; examined, not evidence |
| ProjectData | id_high_water_marks | dict[str,int] | {} | persisted per-prefix mark; non-reuse (Req 2) |

## Error Handling

- **Validation failures** surface as Swedish error-string lists from the Research_Validator. `ProjectService` add/update methods raise `ValidationError(errors)` on shape failures (matching `add_person`); the Research_Case_Editor catches it and shows the messages without saving (Requirement 19.9).
- **Corrupt research section** (present but not a list) aborts the load with a Swedish message naming the section, leaving the open project untouched, mirroring the `residences` `CorruptedFileError` path (Requirement 29.6).
- **Unresolved references** never abort a load or delete an entity; they are kept, logged to the load log, and reported later by the validator and the consistency report (Requirements 29.7, 27.2).
- **Newer file version** raises `UnsupportedVersionError` via the existing guard once `CURRENT_VERSION` is 0.3, so an older build cannot overwrite 0.3 research data (Requirement 29.5).
- **Failed save** is non-destructive: the existing atomic temp-file-then-`os.replace` in `FilePersistence.save` means a failed write leaves the prior file intact (Requirement 29.8).
- **Closing-warning dialog** is advisory, never blocking; "Avsluta ändå" proceeds and marks no action complete (Requirement 10.3, 10.4).
- **Transactional commit failure** discards the Working_Copy and leaves `ProjectData` unchanged (Requirement 19.11).

## Testing Strategy

Tests follow the project's conventions: `pytest` unit tests plus Hypothesis property-based tests where a round-trip or invariant is natural (the `.hypothesis` cache in the repo confirms Hypothesis is in use). Tests assert behavior, not the mere presence of a field or widget. UI logic is tested through the pure helpers (`filter_persons`, `build_person_display_list`, `ResearchIndex`, validators, serialization) so most coverage needs no live Qt.

Key test areas, mapped to requirements:

- **Model & validators** — status/priority/assessment validity and defaults (R1, R4); empty case valid at model level (R1.6, R3.2); length limits (R1.7, R4.10, R6.8); unknown entity type and missing-entity reference (R3.4, R3.5); duplicate-link warning (R3.7); pending vs completed by `completed_date` with empty-string normalized to `None` (R6.4, R7.8); `is_valid_calendar_date` rejects impossible days like "2026-02-30" for comment and completion dates and accepts year/month precision (R5.5, R6.7, R6.9).
- **ID non-reuse (R2)** — create `case_7`, delete it, save, reopen, create another case ⇒ the new id is not `case_7`; the persisted `id_high_water_marks` round-trips; a project holding research data but no stored map initializes the mark from live ids on load; within-session freed ids are not reused.
- **Serialization & migration** — round-trip equality incl. absent `completed_date` stays absent, empty strings stay empty, `sort_order` int, nested comments and `source_refs` in order, zero-hypothesis/zero-action cases (R29.2); missing/null section ⇒ empty, zero errors (R29.3); non-list section ⇒ `CorruptedFileError` (R29.6); 0.2→0.3 migration idempotent and bumps both versions (R29.4); pre-feature (0.2) project loads unchanged then saves at 0.3.
- **Index** — case appears once when linked twice (R3.8, R12.3); counts of non-closed/total; actions-by-source spanning multiple cases (R12.4); pending-action count; `hypotheses_for_entity` returns hypotheses that link an entity, paired with their case, and never enters counts (R12.9, R22.3); a broken link contributes to no entity-keyed lookup (R26.3); rebuild reflects a close/reopen (R12.6).
- **Service / integrity** — create/update/delete sets dirty (R1.10); transactional commit: a validation error in any child writes nothing and leaves `ProjectData` unchanged, cancel discards the Working_Copy (R19.8–19.11); delete of a referenced entity deletes no research and keeps stale refs (R27.1, R27.2); `rewire_entity_merge` moves refs to survivor, collapses duplicates, and preserves `SourceRef.quality/note/aspects` and link `role` (R27.3, R27.4, R27.6, R27.7); `remove_entity_association` drops one link without deleting the case and nulls primary with no auto-promote (R19.4, R21.2); `delete_case_cascade` returns correct child counts and removes only that case's children (R20).
- **Refresh (R13)** — emitting `research_changed` causes a registered open view's `refresh()` to run; a deleted case disappears from an open overview; an open person editor's indicator updates on close/reopen; refresh preserves selection and does not clobber unrelated unsaved edits (tested at the controller level).
- **Lifecycle** — close with pending actions after confirmation keeps actions pending (R10.2–10.4); cancel restores prior status; reopen keeps all children intact (R10.7); add pending action to closed case leaves status closed and shows the info message (R11).
- **Actions** — multiple pending actions; mark completed sets today's date unless one exists (R7.2); clearing the date while checked never stores an empty string (R7.3, R7.8); uncheck returns to pending preserving title/text/sources/order (R7.4, R7.5); reorder persists (R8.2); to-do default excludes closed cases (R18.6); examined-source refs stay optional and usable for a negative result and are never treated as hypothesis evidence (R9.5, R9.7).
- **Hypotheses** — multiple per case incl. conflicting (R4.6); change assessment; add/edit/remove comments; comments survive an assessment change (R5.7); reject keeps the hypothesis and its comments (R4.8); hypothesis-table overview mode lists one row per hypothesis with assessment and owning case (R18.8); "Förekommer i hypoteser" lists hypotheses referencing an entity without affecting counts (R22).
- **Entity integration** — create from person editor sets primary ref (R21.3); same case visible from every linked entity editor (R21.9); removing the primary link clears it with no auto-promote (R19.4); case-delete confirmation names child counts and cancel preserves everything while association-removal shows no such warning (R20); source-editor direct cases (R23.2) and action-usage incl. cases not directly linked to the source (R23.3); unique-case counts (R23.5); navigation preserves unsaved edits (R30.4); mandatory title on save with an initially empty editor allowed (R19.12).
- **Existing UI** — person-list research column respects visibility settings (R15.4, R15.5); diagram indicator respects its independent setting (R16.5); indicator state/counts update on close/reopen (R14.6); broken links show "(saknat objekt)" and are not navigable as valid (R26.2); person-list filter combines status+action within the same case (R24.7); existing filters still work (R24.9); two-column filter layout resizes (R24.2).
- **Consistency & GEDCOM** — each error and info check fires on crafted data and each finding carries the affected entity identity (R25.2, R25.3, R25.6); case with no entity and no action is valid and not deleted (R25.5); research preserved and not duplicated across a GEDCOM re-import (R28.2, R28.3); export omission records research counts (R28.5).

Temporary files created during verification are cleaned up; no production genealogical data is mutated by any research test.

## Design Decisions and Rationale

1. **Top-level hypothesis/action collections, nested comments.** Matches the starter's persistence block and lets the index and consistency report iterate without walking every case, while comments — always small and always owned by one hypothesis — stay nested so they serialize and reorder with it. (R29.1)
2. **Reuse `SourceRef` for action citations.** The starter asks explicitly not to introduce a duplicate citation structure. `SourceRef` is the one citation type across events, places, and residences; residence observations already prove it carries page-level nuance via the Source's `structured_reference`. (R9.6)
3. **Reuse `LinkedEntity` shape (`ResearchEntityLink`) over a new universal `EntityRef`.** No universal entity-reference type exists in the codebase; `LinkedEntity(entity_type, entity_id, role)` is the established generic link and is already reused by `ResearchNote`. Adding `role` to it covers the starter's per-link role requirement without a new abstraction. (R3.1)
4. **Rebuild-on-demand index, no cache.** The codebase has no cached index or invalidation framework; every index is rebuilt from authoritative data (`_ProjectIndex`, `CheckContext`). Following that keeps the derived data from ever becoming a competing source of truth. (R12.1, R12.6)
5. **One reusable `ResearchTab` across all editors.** Satisfies the "prefer reusable widgets over per-entity implementations" rule and guarantees a case edited from one entity shows current everywhere. The source editor's indirect action-usage section is the single documented exception to the directly-linked-only indicator rule. (R17.3, R21.9, R30.5)
6. **Format bump to 0.3 with an idempotent additive migration.** Exactly how 0.1→0.2 added `residences`. Pre-feature projects migrate by gaining three empty lists and nothing else; re-applying the migration is a no-op. (R29.3, R29.4)
7. **Merge rewire helper fills a real gap.** No reference-rewiring helper exists today, and there is no general person-merge. The design provides `rewire_entity_merge` as the contract so that when a merge path exists (now or later) research references follow the survivor and never dangle. (R27.3, R27.4)
8. **Descriptive-only invariant enforced structurally.** No research code path writes to a genealogical entity. Closing, rejecting, completing, and concluding all stay within the research collections. This is the feature's central guarantee and the reason every "SHALL change no … fact" criterion holds by construction. (R10.6, R23.8, R31.1)
9. **Persisted high-water mark for id non-reuse.** The existing `IDGenerator` only guarantees non-reuse within one instance seeded from live ids, so a deleted highest id is reused after reopen. Persisting a per-prefix mark in the project file is the smallest change that makes non-reuse real while keeping human-readable `case_N` ids; a UUID scheme was rejected as inconsistent with the rest of the app and a full used-id ledger as redundant. (R2)
10. **Transactional editing via a Working_Copy.** The editor touches a deep copy and commits all-or-nothing after validating the whole case graph, so a validation failure or cancel cannot leave `ProjectData` half-edited. This is an application-model transaction, not DB rollback: nothing is written until a single final apply step. (R19.8–19.11)
11. **Empty-string completion dates normalized to `None` at the model boundary.** A single `normalize_completed_date` chokepoint in `__post_init__`, the editor, and the deserializer guarantees no action is ever "completed" on an empty string, so the pending/completed partition is unambiguous everywhere. (R7, R6.4)
12. **Explicit refresh notification for open views.** Rebuilding the index does not repaint a drawn widget, so an `Application.research_changed` signal fans out to every open research-aware view's `refresh()`. This keeps the index pure and stateless while making all open windows consistent. (R13)
13. **Hypothesis references are discovery, not indicators.** Hypotheses that name an entity are surfaced in a separate "Förekommer i hypoteser" section via a separate index map, deliberately kept out of indicator counts so the indicator stays a measure of directly linked cases only. (R12.9, R22, R14.1)
14. **Examined source ≠ hypothesis evidence.** A `source_ref` on an action records a consulted volume (incl. a negative result) and never becomes hypothesis evidence; hypothesis support lives in `reasoning` and comments. This keeps the two concepts independent as the final design principle requires. (R9.7–9.9)
15. **Broken references kept but never shown as valid.** A dangling link is preserved for the consistency report, excluded from index entity lookups and counts, and rendered "(saknat objekt)" with a repair/remove affordance, so nothing stale looks valid. (R26)
16. **Real calendar-date validation.** Completion and comment dates are validated as real dates, not just ISO-shaped strings, reusing `date_utils.parse_date_value` composed with `date_utils.is_valid_swedish_calendar`; day precision is optional. (R6.9, R5.5, R6.7)

## Requirements Coverage Map

| Requirement | Primary design sections |
|---|---|
| R1 Research Case entity | Model (1), Validators (2), IDs (3), Service (6) |
| R2 Identifier non-reuse | IDs and non-reuse (3), Persistence (4) |
| R3 Entity links | Model (1), Validators (2), Index (5) |
| R4 Hypotheses | Model (1), Validators (2), Service (6) |
| R5 Hypothesis comments | Model (1), Validators (2), Case Editor (14) |
| R6 Research actions | Model (1), Validators (2), Service (6) |
| R7 Complete/reopen action | Case Editor (14) |
| R8 Action ordering | Model (1), Case Editor (14) |
| R9 Source refs on actions | Model (1), Source aspects (8), Validators (2) |
| R10 Status independence | Model (1), Case Editor (14) |
| R11 Actions on closed case | Service (6), Case Editor (14) |
| R12 Research index | Index (5) |
| R13 Refresh open views | Refresh notification (6a), App wiring (17) |
| R14 Indicators | Indicators (15) |
| R15 Person list column | Person list (15), Settings (15) |
| R16 Diagram indicator | Diagram (15), Settings (15) |
| R17 Other entity views | Research tab (11), indicators (15) |
| R18 Forskning menu / overview | Overview (13), Menu/App wiring (17) |
| R19 Case editor | Case Editor (14), Service transactional commit (6) |
| R20 Delete confirmation | Case-deletion confirmation (14a), Service (6) |
| R21 Editor integration | Research tab (11), App wiring (17) |
| R22 Hypotheses referencing entity | Research tab (11), Index (5) |
| R23 Source editor tab | Source editor tab (12), Index (5) |
| R24 Filter dialog | Filter dialog (16) |
| R25 Consistency report | Consistency report (9) |
| R26 Broken-ref display | Delete/Merge (7), Index (5), Research tab (11) |
| R27 Delete/merge | Service (6), Delete/Merge (7) |
| R28 GEDCOM | GEDCOM (10) |
| R29 Persistence/migration | Persistence (4) |
| R30 UX/navigation | Research tab (11), Overview (13), Case Editor (14), Localization (18) |
| R31 Non-goals | Design Decisions (8) |
