# Implementation Plan: Research Cases, Hypotheses and Research Log

## Overview

The feature is built bottom-up through the existing package layout, mirroring how the Residence_Fact feature was staged: first the pure model and its collections, then validation, persistence and migration, then the research index and service with reference integrity, then the central overview and case editor, then the reusable research tab woven into every entity editor, then indicators and settings, then the filter dialog, and finally the consistency report and GEDCOM-preservation verification, closing with a regression pass. Every layer is integrated into the Project as soon as it exists so nothing is orphaned.

Unit tests use `pytest`; property-based tests use Hypothesis (already a dev dependency) over shared strategies in `tests/test_model/research_strategies.py`. Tests assert behavior, not the mere presence of fields or widgets. UI behavior is covered through the pure helpers (`ResearchIndex`, validators, serialization, `filter_persons`, `build_person_display_list`) so the bulk of coverage runs without a live Qt event loop.

Internal keys, identifiers, and comments are English; every user-facing string is Swedish.

## Tasks

- [ ] 1. Research data model
  - [x] 1.1 Create `slaktbusken/model/research_case.py` with dataclasses and constants
    - `ResearchEntityLink`, `HypothesisComment`, `ResearchHypothesis`, `ResearchAction`, `ResearchCase` exactly as in the design data model, `id` first, `from __future__ import annotations`, no Qt/IO imports, `source_refs: list[SourceRef]` reusing `model.event.SourceRef`
    - `ResearchAction.__post_init__` calls `normalize_completed_date` so an empty or whitespace-only `completed_date` becomes `None`; no path stores an empty string
    - Constants `SUPPORTED_ENTITY_TYPES`, `VALID_RESEARCH_STATUSES`, `VALID_RESEARCH_PRIORITIES`, `VALID_HYPOTHESIS_ASSESSMENTS`
    - Pure helpers `is_pending`, `case_entity_links`, link-count-for-entity, `normalize_completed_date` (None for empty/whitespace, else trimmed), and `is_valid_calendar_date` (ISO shape AND a real calendar date; compose `date_utils.parse_date_value` with `date_utils.is_valid_swedish_calendar` — `parse_date_value` alone accepts "2026-02-30", so the calendar check is required; accepts year/month/day precision); all leave inputs unchanged
    - _Requirements: 1.1, 3.1, 4.1, 5.1, 6.1, 6.4, 7.8, 6.9_
  - [x] 1.2 Write tests for `normalize_completed_date` and `is_valid_calendar_date`
    - Empty/whitespace/`None` normalize to `None`; a valid date trims and stays; "2026-02-30" and "2026-13-01" are rejected by `is_valid_calendar_date`; year and month precision accepted; an action constructed with `completed_date=""` is pending
    - _Requirements: 6.4, 7.8, 6.9_
  - [x] 1.3 Create shared Hypothesis strategies in `tests/test_model/research_strategies.py`
    - `entity_links()`, `hypothesis_comments()`, `hypotheses()`, `actions()`, `research_cases()`, `consistent_projects()`
    - Deliberately include empty cases, cases with no links, duplicate links, conflicting hypothesis assessments, pending and completed actions, length boundaries at 200/1000/10000 characters, absent vs empty-string fields, and unresolved references
    - _Requirements: 1.6, 3.2, 3.7, 4.6, 6.6_
  - [ ] 1.4 Write unit + property tests for model helpers
    - `is_pending` is true exactly when `completed_date is None`; `case_entity_links` yields primary first then linked and mutates nothing; defaults are status `open`, priority `normal`, assessment `unassessed`
    - _Requirements: 1.1, 4.1, 6.4_

- [ ] 2. Project collections and identifiers
  - [x] 2.1 Add the three collections and id prefixes
    - `ProjectData.research_cases`, `research_hypotheses`, `research_actions`, each `list[...] = field(default_factory=list)` after `residences`, empty for a new Project, preserving insertion order
    - Add `research_case`/`research_hypothesis`/`research_action`/`hypothesis_comment` prefixes to `IDGenerator._PREFIXES`
    - Add `ProjectData.id_high_water_marks: dict[str, int] = field(default_factory=dict)` for the non-reuse mechanism
    - _Requirements: 1.2, 1.3, 4.2, 6.2, 2.3_
  - [ ] 2.2 Implement persistent id non-reuse for research entities
    - Add a `ResearchIdGenerator` helper (in `research_service.py`) that seeds an `IDGenerator` from live research ids **and** `max(stored_mark, live_high_water)` per research prefix, generates an id, and writes the new mark back into `ProjectData.id_high_water_marks`
    - On load, if research data is present but `id_high_water_marks` lacks a research prefix, initialize that prefix's mark from the maximum live suffix so non-reuse holds going forward
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6_
  - [ ] 2.3 Write tests for collection order and identifier uniqueness
    - Insertion order preserved; `IDGenerator.generate` yields unique ids per prefix
    - **Non-reuse across save/reopen**: create `case_7`, delete it, serialize+deserialize, create another case ⇒ the new id is not `case_7`; the persisted `id_high_water_marks` round-trips; a project with research data but no stored map reconstructs the mark on load; a freed id is not reused within one session
    - _Requirements: 1.2, 1.3, 4.3, 5.3, 6.3, 2.1, 2.3, 2.4, 2.5_

- [ ] 3. Validation
  - [x] 3.1 Implement `validate_research_case`, `validate_research_hypothesis`, `validate_research_action`, `validate_hypothesis_comment` in `slaktbusken/model/validators.py`
    - Return `list[str]` of the exact Swedish messages from the requirements; referential checks gated on optional id-set arguments; validate `completed_date` and comment `date` with `is_valid_calendar_date` (real calendar date, not shape-only), so "2026-02-30" is an error
    - Status/priority/assessment validity; length limits; unknown entity type; missing-entity reference; duplicate-link warning; missing-case reference for hypotheses/actions
    - _Requirements: 1.4, 1.5, 1.7, 1.9, 3.4, 3.5, 3.7, 4.4, 4.7, 4.10, 5.5, 6.5, 6.7, 6.8, 9.4_
  - [ ] 3.2 Write tests for the validators
    - Empty case is valid at the model layer; each invalid value yields its one message; duplicate link yields the warning; missing references detected only when id-sets are supplied; valid entities yield an empty list; an impossible calendar date is rejected for both comment and completion dates
    - _Requirements: 1.4, 1.5, 1.6, 1.7, 3.2, 3.4, 3.5, 3.7, 4.4, 4.7, 5.5, 6.5, 6.7, 9_

- [ ] 4. Persistence and migration
  - [ ] 4.1 Extend `slaktbusken/persistence/serialization.py`
    - Add the three collection names to `entity_fields`; add to `_ENTITY_MAP`; add nested registries for `linked_entities`, hypothesis `comments`, action `source_refs`, and the optional `primary_entity_ref`
    - Add `_deserialize_research` mirroring `_deserialize_residences`: ignore+log unknown fields, keep+log unresolved references, raise `CorruptedFileError` with a Swedish section-naming message for a present non-list section; normalize any empty-string `completed_date` to `None` on load
    - Persist `id_high_water_marks` as a plain `dict[str,int]`, omitted when empty like `connection_overrides`; on load reconstruct absent research-prefix marks from the max live suffix
    - _Requirements: 29.1, 29.6, 29.7, 2.4_
  - [ ] 4.2 Bump format version to 0.3 and register the migration
    - `CURRENT_VERSION = "0.3"` in `migration.py` and `file_io.py`; `ProjectData.version` default and `ProjectService.create_project` write `"0.3"`
    - Register `@MigrationManager.register("0.2","0.3")` adding the three empty collections, idempotent, bumping both `version` and `format_version`
    - _Requirements: 29.4, 29.5_
  - [ ] 4.3 Write persistence + migration tests
    - Round-trip equality: absent `completed_date` stays absent, empty strings stay empty, `sort_order` int preserved, nested comments and `source_refs` in order, zero-hypothesis/zero-action cases, zero-comment hypotheses
    - Missing/null sections ⇒ empty collections, zero errors; non-list section ⇒ `CorruptedFileError` leaving the open project unchanged; 0.2→0.3 migration idempotent; a real 0.2 project loads unchanged and saves at 0.3
    - _Requirements: 29.2, 29.3, 29.4, 29.5, 29.6, 29.7, 29.8_

- [ ] 5. Research index
  - [ ] 5.1 Create `slaktbusken/services/research_index.py`
    - `ResearchCaseCounts` and `ResearchIndex` built once from `ProjectData`, following `foster_sync._ProjectIndex`; reverse maps for cases-by-entity (deduped per case, only links whose target resolves), actions-by-case, hypotheses-by-case, actions-by-source, and a separate hypotheses-by-entity map; pure and read-only
    - Methods `cases_for_entity`, `counts_for_entity`, `actions_for_source`, `actions_for_case`, `hypotheses_for_case`, `pending_action_count`, `hypotheses_for_entity` (returns `(hypothesis, owning_case)` pairs, kept out of the case/count maps)
    - Broken (unresolved) links contribute to no entity-keyed lookup or count
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.9, 26.3_
  - [ ] 5.2 Write index tests
    - Case linked to an entity twice appears once and counts once; non-closed/total counts; actions-by-source spanning multiple cases; pending-action count; a freshly built index reflects a close/reopen; `hypotheses_for_entity` returns linking hypotheses with their case and does not change counts; a broken link is absent from entity lookups and counts; near-constant lookup on a large synthetic project
    - _Requirements: 3.8, 12.2, 12.3, 12.4, 12.6, 12.8, 12.9, 22.3, 26.3_

- [ ] 6. Research service, CRUD, and reference integrity
  - [ ] 6.1 Add research CRUD to `slaktbusken/services/project_service.py`
    - `add/update/delete_research_case`, `add/update/delete_research_hypothesis`, `add/update/delete_research_action`; each validates (shape only), mutates in place, sets `self._dirty = True`, and triggers the Research_Changed_Notification; issues new ids through the `ResearchIdGenerator` so deleted ids are not reused
    - `commit_research_case_working_copy(working_copy)` — validate the entire case graph, write nothing on any error, else apply all creates/updates/deletes as one in-memory operation; `delete_case_cascade` removes a case and exactly its own hypotheses/comments/actions and returns the child counts
    - _Requirements: 1.10, 10.6, 10.7, 11.2, 19.8, 19.9, 19.10, 19.11, 20.3, 29.8_
  - [ ] 6.2 Extend `slaktbusken/services/research_service.py` (created in task 2.2) with pure functions
    - `find_research_dependencies(data, entity_type, entity_id)`; `rewire_entity_merge(data, entity_type, old_id, survivor_id)` moving every link and `source_ref` to the survivor **preserving `SourceRef.quality/note/aspects` and link `role`**, then collapsing within-case duplicates keeping a non-empty `role`; `remove_entity_association(case, entity_type, entity_id)` dropping one link and nulling `primary_entity_ref` with no auto-promote when it was the removed link; `delete_case_cascade` and a working-copy diff helper backing 6.1
    - _Requirements: 19.4, 21.2, 27.3, 27.4, 27.5, 27.6, 27.7_
  - [ ] 6.3 Integrate with delete service and merge paths
    - Confirm `execute_person_deletion` and other entity deletions remove no research and keep stale references; add `find_research_dependencies` reporting; call `rewire_entity_merge` from existing entity-merge entry points; emit the Research_Changed_Notification after a deletion or merge that affects research
    - _Requirements: 27.1, 27.2, 27.3, 13.1_
  - [ ] 6.4 Add the Research_Changed_Notification and wire open-view refresh
    - Add an `Application.research_changed` signal emitted by every research mutation, merge rewire, and research-affecting deletion; connect it to `refresh()` on the person list, the diagram panel, open `ResearchOverview` windows, and the research tab/section of each open person/place/source/event/media/DNA editor; views register/deregister their slot on open/close; refresh preserves selection and never clobbers unrelated unsaved edits
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6_
  - [ ] 6.5 Write service and integrity tests
    - Create/update/delete sets dirty; transactional commit writes nothing when any child is invalid and leaves `ProjectData` unchanged; a cancelled Working_Copy changes nothing; delete of a referenced entity keeps all research and leaves stale refs; merge rewires to survivor, collapses duplicates, and preserves `SourceRef.quality/note/aspects` and link `role`; remove-association drops one link without deleting the case and nulls primary with no auto-promote; `delete_case_cascade` returns correct counts and removes only that case's children; emitting `research_changed` refreshes a registered view and a deleted case disappears from an open overview
    - _Requirements: 1.10, 19.4, 19.9, 19.11, 21.2, 27.1, 27.2, 27.3, 27.6, 27.7, 13.2, 13.4_

- [ ] 7. Source aspects and localization
  - [x] 7.1 Extend `slaktbusken/services/source_aspects.py`
    - Add a `research_case` entry to `ENTITY_SOURCE_ASPECTS` and its Swedish labels to `ASPECT_LABELS`; frame action source refs as examined/consulted sources (a "Granskade källor" context), not hypothesis evidence
    - _Requirements: 9.6, 9.7, 9.8_
  - [x] 7.2 Extend `slaktbusken/ui/swedish_locale.py`
    - Add `RESEARCH_STATUS_LABELS`, `RESEARCH_PRIORITY_LABELS`, `HYPOTHESIS_ASSESSMENT_LABELS`, `RESEARCH_ENTITY_TYPE_LABELS`, and getter + reverse-lookup helpers with the fallback-to-key convention
    - _Requirements: 19.7, 30.6_
  - [x] 7.3 Write label tests
    - Every internal value maps to its Swedish label; reverse lookups round-trip; unknown keys fall back to the key
    - _Requirements: 30.6_

- [ ] 8. Central research interface
  - [ ] 8.1 Create `slaktbusken/ui/editors/research_case_editor.py`
    - `ResearchCaseEditor(QWidget)` with `save_requested`/`cancel_requested` that **edits a deep-copied Working_Copy** and never mutates `ProjectData` until a validated commit; sections Frågeställning, Status, Prioritet, Berörda objekt, Hypoteser, Nästa åtgärder, Genomförda åtgärder, Slutsats; status/priority combos using the locale getters; hypotheses with assessment combo, reasoning, dated-comments sub-list defaulting comment date to today and never storing an empty-string date; two action lists split by `completed_date` with the "Åtgärden genomförd" checkbox, editable "Färdigdatum" (clearing while checked normalizes to `None`, never ""), drag-reorder for pending, and an examined-source attach/detach under "Granskade källor"
    - "Berörda objekt": set/clear primary with no auto-promote on primary removal; a dangling link renders "(saknat objekt)" and offers removal only
    - On save call `commit_research_case_working_copy`: validate the whole graph (incl. non-empty `title`, message "Forskningsärendet måste ha en rubrik."), write nothing on any error and keep the editor open, else commit atomically; cancel/failure leaves `ProjectData` unchanged
    - Closing warning dialog "Forskningsärendet har öppna åtgärder" only on a status transition into `closed` with pending actions, buttons "Gå tillbaka"/"Avsluta ändå", non-blocking; info message when adding a pending action to a closed case
    - _Requirements: 5.4, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 8.1, 8.2, 8.3, 8.4, 9.3, 9.8, 10.2, 10.3, 10.4, 10.5, 11.1, 11.3, 19.1, 19.2, 19.3, 19.4, 19.7, 19.8, 19.9, 19.10, 19.11, 19.12, 26.2_
  - [ ] 8.2 Add the destructive case-deletion confirmation
    - Shared confirmation path for deleting a case from the Research_Overview and the Research_Case_Editor: a dialog naming the child counts ("Att ta bort forskningsärendet tar även bort {h} hypoteser, {k} hypoteskommentarer och {å} forskningsåtgärder. Detta kan inte ångras.") with "Ta bort"/"Avbryt"; confirm runs `delete_case_cascade`, cancel changes nothing; wording distinct from "ta bort kopplingen"
    - _Requirements: 20.1, 20.2, 20.3, 20.4, 20.5_
  - [ ] 8.3 Create `slaktbusken/ui/research_overview.py`
    - One window with three modes over the same data: **case mode** (sortable table Rubrik/Status/Prioritet/Huvudobjekt/Antal hypoteser/Nästa åtgärder/Antal åtgärder resolved at render time; filter bar for status, priority, linked entity type, specific linked entity, has/none pending actions, has/none hypotheses, free text; "visa avslutade" toggle; create/open); **to-do mode** (pending actions, default excluding closed cases with an include toggle, navigation to action and case); **hypothesis mode** (one row per Research_Hypothesis showing statement, assessment label, and owning case title, sortable and searchable, opening the owning case)
    - Register a `refresh()` slot for the Research_Changed_Notification
    - _Requirements: 18.3, 18.4, 18.5, 18.6, 18.7, 18.8, 18.9, 13.2_
  - [ ] 8.4 Wire the Forskning menu and Application openers
    - `main_window.py`: add `action_research_overview`/`action_research_todo`/`action_research_hypotheses`, a `menu_bar.addMenu("&Forskning")`, and enable toggling in `_update_project_actions`
    - `app.py`: `show_research_overview(initial_mode)` and `open_research_case(case_id=None, prepopulate=None)` following the `show_dna_editor`/`open_person_editor` dialog pattern, writing back on accept, setting dirty; own the `research_changed` signal and fan it out to open views
    - _Requirements: 18.1, 18.2, 13.1_
  - [ ] 8.5 Write overview/editor logic tests
    - Pure filter and to-do selection logic: default to-do excludes closed cases and the include toggle adds them; hypothesis mode lists one row per hypothesis with assessment and owning case; close-with-pending confirmation path keeps actions pending and cancel restores status; reopen keeps children; completion checkbox round-trips preserving title/text/sources/order and clearing the date never stores ""; reorder persists via `sort_order`; a validation error in the Working_Copy leaves `ProjectData` unchanged; mandatory title blocks save; case-delete confirmation counts children and cancel preserves them
    - _Requirements: 7.4, 7.5, 7.8, 8.2, 8.4, 10.2, 10.3, 10.4, 10.7, 18.6, 18.8, 19.9, 19.11, 19.12, 20.1, 20.2_

- [ ] 9. Reusable research tab and existing-editor integration
  - [ ] 9.1 Create `slaktbusken/ui/widgets/research_tab.py`
    - `ResearchTab(QWidget)` modeled on `BoendenTab`, taking project data, an `(entity_type, entity_id)`, and a `ResearchIndex`; a directly-linked-cases list (status, priority, pending indication) with signals `open_case_requested`, `create_case_requested`, `link_existing_requested`, `remove_association_requested`; a separate **"Förekommer i hypoteser"** section listing `index.hypotheses_for_entity(...)` (statement, assessment, owning case title; opens the owning case) that never feeds counts; a dangling link marked "(saknat objekt)" with removal only; a `refresh()` method for the Research_Changed_Notification
    - _Requirements: 17.1, 21.1, 21.2, 22.1, 22.2, 22.3, 22.4, 22.5, 26.2, 30.5_
  - [ ] 9.2 Integrate the tab into person, place, media editors
    - Insert via `tab_widget.insertTab(...)` like `_setup_boenden_tab`; create-from-editor prepopulates the current entity as `primary_entity_ref`; remove-association drops the link without deleting the case; register the tab's `refresh()` for the Research_Changed_Notification
    - _Requirements: 21.1, 21.2, 21.3, 21.4, 21.7, 13.2_
  - [ ] 9.3 Integrate contextual research into event, family/relationship, and DNA views
    - Event editor compact research section that does not discard unsaved event changes; family/parent-child contextual access using `family`/`event` types; DNA match and cluster views using `dna_match`/`dna_cluster` types
    - _Requirements: 21.5, 21.6, 21.8, 21.9_
  - [ ] 9.4 Build the source editor "Forskning" tab
    - Two sections: "Forskningsärenden om denna källa" (`cases_for_entity`) and "Forskningsåtgärder där källan används" (`actions_for_source`) showing action title, completion state, completed date, owning case title and status, framed as an examined source and never as hypothesis evidence; unique-case aggregate counts; navigation to action, to owning case, to a source-linked case, and from an action to its source; register `refresh()` for the notification
    - _Requirements: 23.1, 23.2, 23.3, 23.4, 23.5, 23.6, 23.7, 9.7, 13.2_
  - [ ] 9.5 Write integration-logic tests
    - Create-from-person sets primary ref; the same case is returned for every linked entity by the index; "Förekommer i hypoteser" lists a hypothesis that names a person whose case is not directly linked to that person, without changing the person's indicator counts; source-editor direct cases and action-usage (incl. cases not directly linked to the source) resolve correctly; unique-case counts; navigation helpers preserve unsaved edits (tested at the controller level)
    - _Requirements: 21.3, 21.9, 22.1, 22.3, 23.2, 23.3, 23.5, 30.4_

- [ ] 10. Indicators and settings
  - [ ] 10.1 Create `slaktbusken/ui/widgets/research_indicator.py`
    - Helper mapping `ResearchCaseCounts` to indicator state (`none`/`grey`/`orange`, never green) and the tooltip "{total} forskningsärenden, varav {open} öppna"
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_
  - [ ] 10.2 Add the person-list "Forskningsärenden" column
    - Add `research: bool` to `PersonListConfig` and `ColumnVisibility`; add a `research_counts` field to `PersonDisplayInfo` filled from a `ResearchIndex` in `build_person_display_list`; render "{open}/{total}" with the indicator colour and empty when none; make it sortable by non-closed then total; wire visibility through `apply_person_list_config` and the header context menu; persist via existing settings
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6_
  - [ ] 10.3 Add the diagram research indicator
    - Add `research: bool` to `PersonBoxConfig`; paint a compact indicator in `PersonBoxItem._build_lines` using the helper; add a "Forskningsärenden" checkbox to the settings diagram tab "Personruta – synliga fält"; click opens the person's research; keep selection/navigation unchanged; keep this setting independent of the person-list column
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5_
  - [ ] 10.4 Add indicators to other entity views where markers already exist
    - Place/event/source/media/DNA list and detail indicators from directly linked cases, excluding indirect action references (the source-editor action section remains the sole exception); broken links never render as valid navigable links anywhere
    - _Requirements: 17.1, 17.2, 17.3, 26.2, 26.3_
  - [ ] 10.5 Write indicator and settings tests
    - State/colour rules incl. never-green and empty-when-none; tooltip text; counts update on close/reopen; column visibility respects and persists the setting; diagram and person-list settings are independent
    - _Requirements: 14.2, 14.3, 14.4, 14.5, 14.6, 15.4, 15.5, 16.5_

- [ ] 11. Person list filter dialog
  - [x] 11.1 Refactor `filter_dialog.py` into a two-column resizable layout
    - Left: Namnfilter, Datumintervall, Församling, DNA-kluster; right: Händelsetyper (scroll) and Forskningsärenden; resizable and scrollable; Filtrera/Rensa kept at the bottom
    - _Requirements: 24.1, 24.2_
  - [ ] 11.2 Add research filters to the dialog and criteria
    - "Forskningsärenden" group with existence, status, and action combos using the exact Swedish options; extend `FilterCriteria` with `research_existence`/`research_status`/`research_action`; `_on_clear` resets them to "Alla"; disable/normalize impossible combinations
    - _Requirements: 24.3, 24.4, 24.5, 24.8, 24.9_
  - [ ] 11.3 Extend `filter_persons` to apply research filters
    - Apply the research filters through a `ResearchIndex` on directly linked cases; the combined status+action filter evaluates both conditions against the same linked case of the person; leave existing filters unchanged
    - _Requirements: 24.6, 24.7, 24.9_
  - [ ] 11.4 Write filter tests
    - Each research filter selection; the same-case combination rule (a person with one closed case with a pending action and a separate open case with a completed action is handled per-case); existing filters still function; clear resets research filters
    - _Requirements: 24.4, 24.5, 24.6, 24.7, 24.9_

- [ ] 12. Consistency report and GEDCOM preservation
  - [ ] 12.1 Create `slaktbusken/reports/research_consistency.py`
    - `ResearchIssue(severity, check_type, message, case_id, hypothesis_id, action_id, comment_id, ref_entity_type, ref_entity_id)` carrying the affected research entity identity for future navigation; pure `check_research_consistency(data)` running every error and informational check and populating the identity fields; each `message` names the owning case by title or id; `generate_research_consistency_report(data)` grouping by severity then type into Swedish `HeadingBlock`+`ListBlock`/`EmptyStateBlock` sections ("Inga problem hittades." when empty)
    - _Requirements: 25.1, 25.2, 25.3, 25.4, 25.5, 25.6, 25.7_
  - [ ] 12.2 Wire the report into the menu and generator
    - Add `generate_research_consistency` to `ReportGeneratorService`; promote a Forskningsrapporter/Konsistensrapporter placeholder in `report_menu.py` to a stored action; connect it in `main_window` to a handler showing `ReportPreviewDialog`
    - _Requirements: 25.1_
  - [ ] 12.3 Extend GEDCOM export omissions
    - Add research-entity counts to `_collect_omissions` under a Swedish label ("Forskningsärenden"); make no importer change
    - _Requirements: 28.5_
  - [ ] 12.4 Write consistency and GEDCOM tests
    - Each error check fires on crafted broken data and the finding carries the affected entity identity; each informational check fires; a case with no entity and no action is valid and not deleted; a GEDCOM re-import preserves research and creates no duplicates; a person absent from a later GEDCOM does not delete its research; export reports the research omission counts
    - _Requirements: 25.2, 25.3, 25.5, 25.6, 28.2, 28.3, 28.4, 28.5_

- [ ] 13. Full regression pass
  - [ ] 13.1 Verify descriptive-only invariant across the feature
    - Assert that closing a case, rejecting a hypothesis, completing an action, and setting a conclusion change no `Person`/`Event`/`Family`/`Place`/`Source`/`Media`/DNA data
    - _Requirements: 10.6, 23.8, 31.1_
  - [ ] 13.2 Run the full existing test suite and confirm no regressions
    - Confirm pre-feature projects still load, existing person-list filters and columns still behave, existing reports and GEDCOM round-trips are unchanged, and the diagram renders unchanged when the research indicator is off
    - _Requirements: 24.9, 28.1, 29.3, 31.6_
  - [ ] 13.3 Confirm non-goals are not implemented
    - No automatic fact changes, no generated conclusions, no confidence percentages, no automatic DNA validation, no external services/reminders/calendar/multi-user, no automatic hypothesis revision history, no research GEDCOM export, no separate research database
    - _Requirements: 31.1, 31.2, 31.3, 31.4, 31.5, 31.6_

## Notes

- Each task references specific requirements for traceability (requirement numbers refer to `requirements.md`)
- Property-based tests use Hypothesis with the shared strategies from task 1.3; unit tests cover specific examples and edge cases
- UI behavior is verified through the pure helpers (`ResearchIndex`, validators, serialization, `filter_persons`, `build_person_display_list`) so most tests run without a live Qt event loop
- Task 2.2 creates `research_service.py` (with `ResearchIdGenerator`); task 6.2 extends the same file
- Task 6.4 defines the `Application.research_changed` signal early so CRUD (6.1) can emit it; each view registers its own `refresh()` slot in the task that builds it (8.3, 9.1, 9.4, 10.2, 10.3)
- No Swedish user-facing string is hard-coded outside `swedish_locale.py` where a label dictionary applies; identifiers and comments stay in English
- The research collections and `id_high_water_marks` are additive; the 0.2 to 0.3 migration (task 4.2) must not alter any existing data
- Task 13 is a verification pass and should not introduce new behavior

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "7.1", "7.2", "11.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "2.1", "3.1", "7.3"] },
    { "id": 2, "tasks": ["1.4", "2.2", "3.2", "4.1", "4.2", "5.1", "6.4", "12.1", "12.3"] },
    { "id": 3, "tasks": ["2.3", "4.3", "5.2", "6.2", "10.1", "11.2", "12.2"] },
    { "id": 4, "tasks": ["6.1", "6.3", "9.1", "10.2", "11.3"] },
    { "id": 5, "tasks": ["6.5", "8.1", "8.3", "10.4", "11.4", "12.4"] },
    { "id": 6, "tasks": ["8.2", "8.4"] },
    { "id": 7, "tasks": ["8.5", "9.2", "9.3", "9.4", "10.3"] },
    { "id": 8, "tasks": ["9.5", "10.5", "13.1"] },
    { "id": 9, "tasks": ["13.2", "13.3"] }
  ]
}
```
