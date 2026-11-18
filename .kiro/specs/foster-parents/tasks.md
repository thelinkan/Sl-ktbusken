# Implementation Plan: Foster and Adoptive Parents

## Overview

The feature is built bottom-up, following the existing package layout: first the model/project change
and the event-type registration (new Fosterhem type, extended Adoption roles), then the parentage-sync
service that establishes the source-of-truth invariant for both foster and adoptive links, then
persistence/migration and settings, then the shared display resolver and the visual layer, then the
three diagram views and the override UI, then the relationship calculator and kinship terms, then
reports, GEDCOM, and finally the person-editor and person-check wiring. Each layer is integrated as
soon as it exists so nothing is orphaned.

Property-based tests use Hypothesis (already a dev dependency) over shared strategies in
`tests/test_foster/foster_strategies.py`. Each correctness property from the design gets exactly one
property test in its own file, with `@settings(max_examples=100, deadline=None)` and the project's
tag-comment/docstring form. Strategies and properties exercise foster and adoptive symmetrically. UI
behaviour is covered with targeted unit tests of the pure resolver/sync functions rather than through a
Qt event loop.

## Tasks

- [x] 1. Project model and event-type registration
  - [x] 1.1 Add `connection_overrides` to the project model
    - `ProjectData.connection_overrides: dict[str, str] = field(default_factory=dict)` mapping child id → `"biological"`/`"foster"`/`"adoptive"`, empty for new projects
    - _Requirements: 5.1, 5.5, 13.2_
  - [x] 1.2 Register the four händelsetyper in every definition site
    - `foster_home` "Fosterhem", `foster_home_ended` "Fosterhem upphörde", `adoption_ended` "Adoption upphörde" (plus the existing `adoption`): `event_editor.py` (`INDIVIDUAL_EVENT_TYPES`, roles `foster_home`/`foster_home_ended`→`fosterbarn`, `adoption_ended`→`adopterad`), `swedish_locale.py`, `filter_dialog.py`, `person_detail_panel.py`, `icon_registry.py`, `reports/ansedel.py`, `reports/kallrapport.py`; icons fall back to generic when an asset is absent
    - _Requirements: 1.1, 1.2, 1.8_
  - [x] 1.3 Teach the event editor the parent role per placement type
    - Offer `"fosterförälder"` for foster types and `"adoptivförälder"` for adoptive types when adding participants; adoptee child-role `"adopterad"` already exists
    - _Requirements: 1.2_
  - [x] 1.4 Add start-event participant-count validation to the event validator
    - Exactly one child-role; one or two parent-role; exact per-type Swedish messages; an Adoption start event with no parent-role participant stays valid
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 1.7, 1.9, 13.5_
  - [x] 1.5 Add end-event participant and pairing validation
    - End event names the same child and parents as its start (symmetric, Req 1.10); orphan end event yields the exact per-type message; at most one end per start; end-before-start is a warning-level finding
    - _Requirements: 1.10, 2A.1, 2A.3, 2A.4, 2A.6, 2A.7_
  - [x] 1.6 Add the editor one-click fix for an orphan end event
    - When creating an end event with no matching start, offer to create a dateless start of the matching type with the same child and parents in the same step, then pair the end to it
    - _Requirements: 2A.5_

- [x] 2. Parentage sync service (source of truth, both types)
  - [x] 2.1 Create `slaktbusken/services/foster_sync.py` with `sync_parentage_links(project)` and the `_PLACEMENT_START`/`_PLACEMENT_END` tables
    - Derive one family per START event, keyed via `Family.event_ids`; one link per (parent → child) with the event's parentage type; delete derived families whose start event is gone; never touch biological or other links; idempotent
    - END events never create/remove a link; pair each end to the derived family of its matching start by Parent_Set (append end id to that family's `event_ids`); detach an end whose start is gone rather than deleting it
    - Per-set cap of two parents; no project-wide cap on foster or adoptive parents for a child
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.8, 2.9, 2.10, 2A.1, 2A.2_
  - [x] 2.2 Add Parent_Set ordering helper
    - Pure function returning a child's Parent_Sets of a given type ordered by start event `date.value`, undated last in project order, without mutating data
    - _Requirements: 2.5_
  - [x] 2.3 Create shared Hypothesis strategies in `tests/test_foster/foster_strategies.py`
    - Projects with: zero/one/many placement events per child per type, one-and-two-parent sets, mixed biological+foster+adoptive, orphan foster and adoptive links with no event, pre-feature descriptive adoption events, dated/undated events, start events with/without a paired end, orphan end events, end-before-start dates, overrides for present/absent sets
    - _Requirements: 2.1, 2.9, 2A.1, 13.5_
  - [x] 2.4 Write property test for sync idempotence and foster/adoptive-only reconciliation
    - **Property 1 & 2: sync twice == once; biological and other links untouched**
    - **Validates: Requirements 2.2, 2.8**
  - [x] 2.5 Write property test for event⇒link coverage and set cap, both types
    - **Property 3 & 4: every event has exactly its links of its type and vice versa; no set >2, project uncapped**
    - **Validates: Requirements 2.1, 2.9**
  - [x] 2.6 Write property test for end events annotating but never mutating links
    - **Property 9: adding/editing/removing any end event leaves every Derived_Link unchanged; each end pairs to one start by Parent_Set; at most one end per start; an orphan end is flagged not dropped**
    - **Validates: Requirements 2.10, 2A.1, 2A.2, 2A.3, 2A.4**

- [x] 3. Persistence, migration, and settings
  - [x] 3.1 Serialize `connection_overrides`
    - Written as a dict, omitted/empty for untouched projects; read back empty when absent
    - _Requirements: 13.1, 13.2_
  - [x] 3.2 Add the pre-feature orphan-link adoption migration
    - For each orphan foster/adoptive family with no backing placement event, create a dateless Fosterhem/Adoption event, then let `sync_parentage_links` adopt it; preserve pre-feature descriptive adoption events; delete no foster/adoptive data
    - _Requirements: 13.3, 13.5_
  - [x] 3.3 Add parentage fields to `DiagramSettings` and persist them
    - `parentage_show_level: str = "biological"`, `parentage_badge: bool = False`, `parentage_fallback: bool = True`; round-trip through `app_settings_io.py`
    - _Requirements: 4.5, 6.1, 7.4_
  - [x] 3.4 Write property test for backward compatibility
    - **Property 8: loading a pre-feature project loses no foster/adoptive links; descriptive adoption events preserved; overrides default empty**
    - **Validates: Requirements 13.1, 13.3, 13.4, 13.5**

- [x] 4. Shared parent-display resolver
  - [x] 4.1 Create `slaktbusken/ui/views/parent_display.py:resolve_parent_display(...)`
    - Precedence override > show-level > fallback; `non_biological` draws both foster and adoptive; override for a missing set ignored; connection type chosen from each drawn link's `parentage_type`; fallback with both non-biological types draws both
    - Return drawn links grouped by Parent_Set with each set's cardinality (one or two parents), so views can render a one-parent derived set without a partner connector or second-parent placeholder
    - _Requirements: 3.8, 3.9, 3.10, 4.1, 4.2, 4.3, 4.4, 5.2, 5.3, 5.6, 6.2, 6.3, 6.4, 6.5, 6.6_
  - [x] 4.2 Write property test for display precedence and set cardinality
    - **Property 5: override wins over show-level wins over fallback; missing-set override ignored; non_biological draws foster+adoptive; one-parent sets are reported as complete single-parent sets**
    - **Validates: Requirements 3.8, 4.2, 4.3, 4.4, 5.2, 5.3, 5.6, 6.2, 6.3, 6.6_

- [x] 5. Visual layer
  - [x] 5.1 Extend `ConnectionType` and `ConnectionLineItem` in `connection_line.py`
    - Add `FOSTER` and `ADOPTIVE` members; dashed pens with distinct `_FOSTER_COLOR` and `_ADOPTIVE_COLOR`; biological unchanged; optional `badge_text` painted near the path midpoint
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.6, 3.7_

- [x] 6. Wire the three diagram views
  - [x] 6.1 Route `family_view.py` through `resolve_parent_display`
    - Read `DiagramSettings` + `connection_overrides`; draw returned links with their connection type and optional badge
    - For a one-parent derived Parent_Set, draw a single parent box with no partner connector and no second-parent placeholder, centring the drop line on that parent; two-parent sets draw both boxes and the partner connector; biological pairs keep the existing father/mother placeholder for an unknown parent
    - Apply the same single-parent suppression to a sibling's foster/adoptive partner family in STEP 4 of the layout
    - _Requirements: 3.5, 3.8, 3.9, 3.10, 4.2, 4.3, 4.4, 4.6, 6.2_
  - [x] 6.2 Route `ancestry_view.py` through the same resolver
    - Same single-parent rule for one-parent derived Parent_Sets as 6.1
    - _Requirements: 3.5, 3.8, 3.9, 3.10, 4.6_
  - [x] 6.3 Route `descendants_view.py` through the same resolver
    - Same single-parent rule for one-parent derived Parent_Sets as 6.1
    - _Requirements: 3.5, 3.8, 3.9, 3.10, 4.6_
  - [x] 6.4 Add the per-connection override context action
    - Right-click sets/clears `connection_overrides[child_id]` to biological/foster/adoptive/cleared; redraw on change
    - _Requirements: 5.1, 5.4, 5.5_

- [x] 7. Settings dialog (Diagram tab)
  - [x] 7.1 Add Show_Level, badge, and fallback controls
    - Show_Level (Biologiska/Icke-biologiska/Alla), badge checkbox (default off), fallback checkbox (default on); writing any triggers an active-diagram redraw
    - _Requirements: 7.1, 7.2, 7.3, 7.5, 4.1, 4.5, 4.7, 6.1_

- [x] 8. Relationship calculator and kinship terms
  - [x] 8.1 Add the foster branch to `_classify_relationship_type`
    - After the all-blood check and the adoptive check: any foster → `"foster"`; mixed blood/non-blood still → blood; adoptive branch unchanged
    - _Requirements: 8.1, 8.2, 9.1, 9.3, 9.4_
  - [x] 8.2 Add foster Swedish terms to `kinship_terms.py`
    - "fosterfar"/"fostermor"/"fosterbarn" for immediate; `"foster-"`-prefixed terms otherwise; adoption terms unchanged
    - _Requirements: 9.2, 9.4_
  - [x] 8.3 Write property test for blood priority and classification
    - **Property 6: any all-blood path ⇒ no non-blood path returned; mixed ⇒ blood; pure foster ⇒ "foster"; pure adoptive ⇒ "adoption"**
    - **Validates: Requirements 8.2, 8.3, 9.1, 9.3, 9.4_

- [x] 9. Ansedel report
  - [x] 9.1 Annotate foster and adoptive parents in `reports/ansedel.py`
    - Append the Swedish parentage label for non-biological parents, distinctly for foster vs adoptive; biological unannotated; Fosterhem and Adoption events render with their labels
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [x] 10. GEDCOM round-trip
  - [x] 10.1 Emit `FAMC`/`FAMS` with `PEDI` in `exporter.py` `_write_person`
    - `FAMC` for each family where the person is a child, with `2 PEDI foster`/`2 PEDI adopted` for foster/adoptive links; `FAMS` for partner families; biological `FAMC` carries no `PEDI`
    - _Requirements: 11.1, 11.2_
  - [x] 10.1a Export the Adoption event (`1 ADOP`) and Fosterhem event (`1 EVEN` / `2 TYPE Fosterhem`)
    - Add `"adoption": "ADOP"` to `_EVENT_TYPE_TO_TAG` (absent today, so adoption events are dropped on export); add `_write_foster_event` mirroring `_write_flytt_event` and route `foster_home` to it in `_write_person`; emit `DATE`/`PLAC` when present
    - Emit a subordinate `FAMC` on each `ADOP`/`EVEN` pointing at the derived family for its Parent_Set; one structure per Placement_Start_Event
    - _Requirements: 11.2a, 11.2b, 11.2c, 11.2d_
  - [x] 10.1b Carry the Placement_End_Event date on the paired start structure
    - When a placement has an end, encode the span on the same `ADOP`/`EVEN` `DATE` line as a GEDCOM period (`FROM <start> TO <end>`, degrading to `FROM`/`TO` only), or a labelled `NOTE` ("Avslutades: <end>") with structure-loss logging like `_write_flytt_event`; never emit the end as a separate orphan structure
    - _Requirements: 11.2e_
  - [x] 10.2 Read FAMC/`PEDI` in `importer.py` and set `parentage_type`
    - Add FAMC/PEDI reading (the importer reads only family-level CHIL today); `foster`→foster, `adopted`→adoptive, else/absent→biological (replacing the hardcoded biological)
    - _Requirements: 11.3, 11.4, 11.5_
  - [x] 10.3 Back-fill placement events for imported foster/adoptive links BEFORE syncing
    - Share the back-fill helper with the on-load migration (task 3.2); create a Fosterhem/Adoption event per imported foster/adoptive link not already backed; group parents sharing a GEDCOM family for the same child into one event; prefer a matching `ADOP`/`EVEN TYPE Fosterhem` structure's `DATE`/`PLAC` and its `FAMC` parent linkage; reuse an existing `ADOP`-derived adoption event rather than duplicating it
    - _Requirements: 11.6, 11.7, 11.7a, 11.8_
  - [x] 10.3a Reconstruct the Placement_End_Event from an imported end date
    - When an imported `ADOP`/`EVEN TYPE Fosterhem` structure carries an end (period upper bound or labelled note), create the paired end event with that date and the same child and parents as the start
    - _Requirements: 11.10_
  - [x] 10.4 Run `sync_parentage_links` after back-fill, events taking precedence, no imported relationship deleted
    - _Requirements: 11.9_
  - [x] 10.5 Write property test for GEDCOM round-trip with no loss
    - **Property 7: export then import preserves parentage_type AND the event's date/place/parent-set/end-date; every imported foster/adoptive link survives the post-import sync; GEDCOM-family-mates form one Parent_Set; multiple Parent_Sets round-trip as multiple ordered structures; a placement's end date round-trips on the paired structure**
    - **Validates: Requirements 11.1, 11.2, 11.2a, 11.2b, 11.2c, 11.2d, 11.2e, 11.3, 11.4, 11.5, 11.6, 11.7, 11.7a, 11.8, 11.9, 11.10_

- [x] 11. Person editor and person checks
  - [x] 11.1 Make foster and adoptive links read-only in `person_editor.py`
    - Foster/adoptive rows shown read-only labelled "(via händelse)"; no direct add/retype/remove; adding a foster or adoptive parent routes to a pre-populated placement event
    - _Requirements: 2.6, 2.7_
  - [x] 11.2 Make `person_check_engine.py` foster/adoptive-aware
    - Distinguish foster and adoptive from biological in `parents_of`; a person with only non-biological parents is not "saknar föräldrar"; skip meaningless age-gap/chronology checks for foster (and adoptive where meaningless)
    - _Requirements: 12.1, 12.2, 12.4_
  - [x] 11.3 Label foster and adoptive parents in `person_detail_panel.py`
    - Annotate each distinctly in "Föräldrar och syskon"
    - _Requirements: 12.3_
  - [x] 11.4 Wire `sync_parentage_links` into event edits and project load
    - Call `sync_parentage_links(project)` whenever a Placement_Event is created, edited, or deleted, so Derived_Links agree with the current events; the natural single choke point is `project_service.add_event` plus the corresponding event update/delete paths reached from `event_editor._on_save` and the event delete action — call sync after the event mutation commits, for both foster and adoptive types
    - Call `sync_parentage_links(project)` on project open in `project_service.open_project`, AFTER the pre-feature orphan-link migration (task 3.2) has back-filled placement events, so the on-load order is migrate-then-sync and no orphan foster/adoptive link is dropped (Design Decision 1 / Requirement 13.3)
    - Do NOT add a second sync call to the GEDCOM import path (task 10.4 already runs sync after its back-fill); keep sync a no-op-safe single call per mutation given its idempotence
    - _Requirements: 2.3, 13.3_

- [x] 12. Full integration verification
  - [x] 12.1 Run the whole test suite and the app's import/export/report paths
    - Confirm the task 11.4 wiring runs sync on event create/edit/delete and on project load, and that task 10.4 runs it on GEDCOM import, for both types; confirm all three views honour show-level/override/fallback; confirm settings persist across restart
    - _Requirements: 2.3, 4.6, 4.7, 7.5, 11.6, 13.1_

- [x] 13. Participant picker disambiguation and plausibility filtering
  - Builds on the event editor and participant combos introduced in group 1 (`event_editor.py`, `_get_person_display`, `_populate_combos`); listed last but depends on group 1 being in place
  - [x] 13.1 Add a person-display helper that formats "Name (birth–death)" and wire it into the participant combos
    - Derive the birth/death year from the year portion of the person's birth/death event via `_find_event_by_type(person_id, "birth"/"death", data)` (same approach as `reports/ansedel.py`); format the suffix with degradation: both known → " (1914–1978)", birth only → " (1914–)", death only → " (–1978)", neither known → "" (no parentheses); use the en dash `–` (U+2013) consistent with `ui/swedish_locale.py`; extend `_get_person_display` so `_populate_combos` and the participant table both show the suffix
    - _Requirements: 1B.1, 1B.2, 1B.3, 1B.4, 1B.5_
  - [x] 13.2 Add the pure `is_plausible_parent(...)` predicate
    - Module-level, Qt-free function over optional ints `(candidate_birth_year, candidate_death_year, child_birth_year)`; return False only when known dates prove implausibility (candidate born not strictly before the child; candidate died before the child's birth); return True when the child's birth year is unknown or when the candidate's dates are missing/partial
    - _Requirements: 1B.6, 1B.7, 1B.8, 1B.9_
  - [x] 13.3 Rebuild the Parent_Role candidate list in the event editor using the predicate
    - When the current type is a placement type (`foster_home`, `foster_home_ended`, `adoption`, `adoption_ended`) and a Child_Role participant (`fosterbarn`/`adopterad`) with a known birth year is present, populate the parent combo only with candidates for which `is_plausible_parent(...)` is true; otherwise (no child, unknown child birth year, or non-placement type) populate from the full person list; never filter the Child_Role picker
    - _Requirements: 1B.6, 1B.7, 1B.9, 1B.10_
  - [x] 13.4 Unit tests for the display helper and the plausibility predicate
    - Display helper: both-known, birth-only, death-only, neither-known (name only, no parentheses), en-dash separator; predicate: born-after-child, born-same-year-as-child, died-before-child-birth, unknown/partial candidate dates kept, unknown child birth year ⇒ no filtering; editor: the Parent_Role list excludes an implausible person and keeps an unknown-date person for a placement event, and is unfiltered for non-placement types
    - _Requirements: 1B.1, 1B.2, 1B.3, 1B.4, 1B.6, 1B.7, 1B.8, 1B.9, 1B.10_

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Group 13 (participant picker disambiguation and plausibility filtering) is listed last but
  logically builds on the event editor and participant combos from group 1
- Property tests use Hypothesis with `@settings(max_examples=100, deadline=None)` and the project's
  tag-comment/docstring form

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4"] },
    { "id": 2, "tasks": ["1.5", "1.6"] },
    { "id": 3, "tasks": ["2.1", "2.2", "2.3"] },
    { "id": 4, "tasks": ["2.4", "2.5", "2.6", "3.1", "3.2", "3.3"] },
    { "id": 5, "tasks": ["3.4", "4.1", "5.1"] },
    { "id": 6, "tasks": ["4.2", "6.1", "6.2", "6.3", "6.4"] },
    { "id": 7, "tasks": ["7.1", "8.1", "8.2", "8.3"] },
    { "id": 8, "tasks": ["9.1", "10.1", "10.1a", "10.1b", "10.2", "10.3", "10.3a", "10.4"] },
    { "id": 9, "tasks": ["10.5", "11.1", "11.2", "11.3", "11.4"] },
    { "id": 10, "tasks": ["12.1"] },
    { "id": 11, "tasks": ["13.1", "13.2"] },
    { "id": 12, "tasks": ["13.3", "13.4"] }
  ]
}
```
