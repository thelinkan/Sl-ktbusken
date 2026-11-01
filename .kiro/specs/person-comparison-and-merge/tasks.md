# Implementation Plan: Person Comparison and Merge

## Overview

Implementation language: Python (PySide6 for UI), as used by the design. The plan follows nine phases: reference inventory and merge rules; candidate model and persistence; candidate register, saved state and research integration; comparison window; indicators, settings and the research person filter; merge planning and review; atomic merge engine with checksum-based recovery; GEDCOM and consistency integration; regression, performance and mandatory-test enforcement.

Services are Qt-free and built first in each phase; UI tasks wire them afterwards. Each phase ends with a checkpoint. The seven user decisions in design.md are carried into these tasks as follows: decision 1 and 2 (candidate redirect and collision) in 11.5, 11.15, 11.16; decision 3 (families stay separate, preview computed after `sync_parentage_links` on a working copy) in 11.1, 11.4, 11.12, 11.14; decision 4 (project file plus `persons.json` as one crash-recoverable operation) in 13.1 to 13.7 and 13.13 to 13.15, 13.20; decision 5 (UI labels) in 9.2, 9.3 and 9.6; decision 6 (seven distinct children) in 11.4, 11.13 and 11.20; decision 7 (performance limits and benchmark) in 7.2 and 17.1 to 17.3.

The decisions of the requirements update (design "Decisions from the requirements update (round 2)", R1 to R8) are carried into these tasks as follows:

- **R1 Revision and dirty flag:** `revision`, `content_revision`, `clean_content_revision`, `is_saved_state()` and the adopt step (dirty flag cleared, revision plus one, one notification) in 5.16, tests in 5.17 and 13.23, engine use in 13.5.
- **R2 Saved_State_Precondition (replaces the earlier "commit saves unsaved edits"):** editor registry and `UnsavedChangesParticipant` protocol in 5.18, participation by the Person_Editor and all other editors in 5.19, registry completeness test in 5.20, wizard flow "Spara och fortsätt" / "Avbryt" and the editor block message in 11.17, engine step 0 re-check in 13.24, no plan rebuild after a plain save through `content_revision` in 5.16 and 11.17, tests for Properties 47 and 48 in 13.22 and 13.23. No task saves unsaved edits together with a merge.
- **R3 Checksum-based recovery and Recovery_Refusal:** journal and manifest in 13.2, protocol in 13.3, recovery algorithm with decision tables A to D and `RecoveryRefusedError` in 13.4, open-time integration in 13.6, refusal dialog in 13.7, fault-injection wrappers in 13.16, crash matrix in 13.13 and 13.14, subprocess crashes in 13.15, refusal matrix (Property 49) in 13.20.
- **R4 Format version 0.4:** `normalise_version_fields` / `assert_equal_except_version_fields`, golden 0.3 fixtures and the frozen 0.3 serialiser in 3.13, meta-tests in 3.14, version bump in 3.5, Property 45 in 3.12.
- **R5 Siblings:** shown in the comparison family views in 7.2 and 7.5, tests in 7.16 and 7.17.
- **R6 Research gateway person filter:** `build_person_scope` and row builders in 9.10, `ResearchOverview` filter and banner in 9.11, gateway and `Application` signatures in 9.12, both indicators in 9.4, 9.5 and 9.13, Property 50 and widget tests in 9.14 and 9.15.
- **R7 GEDCOM warning:** `gedcom/capabilities.py` and the wizard warning in 11.18, test in 11.19; the follow-up TRK-1 is recorded in 17.7 and is OUT OF SCOPE for this feature's implementation tasks.
- **R8 Mandatory tests:** registry, `pytest.ini` and conftest hooks in 1.7, runner script in 17.5, guard test in 17.6, mandatory run checkpoint 18, final checkpoint 19. The tasks that write tests of the six Mandatory_Test_Groups (the enforcement set of the no-skip hook and guard) are 1.3, 1.6, 5.17, 5.20, 11.7, 11.11 to 11.14, 11.20, 13.8, 13.9, 13.11 to 13.15, 13.17 to 13.20, 13.22, 13.23, 15.4 and 17.6. All other test tasks in this plan are required as well; there are no optional tasks.
- **Decision 8 (multi-selection in the Person_List, Req 8.4 to 8.7, 8.12 to 8.16):** `ExtendedSelection`, the pure `rows_after_right_click` and the `mousePressEvent` / `contextMenuEvent` handling in 7.18, menu entries and signals in 7.7, Property 51 in 7.19, regression tests in `tests/test_ui/test_person_list_selection.py` in 7.19 and 7.20.
- **Decision 9 (duplicate-event warnings, Req 21.14, 21.15, Similar_Event_Rule):** pure `is_similar_event_pair` and `find_similar_event_pairs` in 1.2, planning use in 11.2, Property 28 in 11.8 and the example and edge-case table in 11.21, both in `tests/test_services/test_similar_events.py`.
- **Decision 10 (backup scope, Req 7.9, 7.10):** the `persons.json` backup rules apply only to `MigrationManager.create_backup` (3.5, tested in 3.15) and the merge Recovery_Point (13.2, 13.3). No task implements a general-purpose project backup feature.
- **Decision 11 (GEDCOM):** the non-destructive update handling TRK-1 is a recorded, out-of-scope follow-up (17.7); the wizard warning is 11.18.
- **Decision 12 (labels, Req 17.1 to 17.3, 18.1):** the Person_List header context-menu toggle and the Settings_Dialog checkbox are exactly "Forskningsuppslag och dubletter"; the column header is "Forskningsuppslag"; the diagram checkboxes are "Forskningsuppslag" and "Sammanslagningskandidater" (9.2, 9.3, 9.4, 9.6).

The design's remaining open questions are implemented with the design's stated defaults: roll-forward when a target already holds exactly the new content (13.4, now checksum-based); format version bump to 0.4 (3.5); siblings shown in the family view (7.2, 7.5); person-list research glyph click calls the gateway with a person filter (9.4, 9.13); wizard warns about update-import overwrite (11.18). The other defaults are placed in 3.5, 7.7, 9.2 and 11.2.

## Tasks

- [x] 1. Phase 1: Reference inventory, merge rules and mandatory-test infrastructure
  - [x] 1.1 Create the Person_Reference_Inventory and `PersonReferenceIndex`
    - Create `slaktbusken/services/person_reference_index.py` with `PERSON_REFERENCE_INVENTORY`: one row per location of design section 4, each with exactly one Reference_Rule, a handler name and a dedupe statement
    - Implement `PersonReferenceIndex.build(data, {survivor, retired})` as one pass per collection, with dictionary lookups afterwards and per-location counts for the preview
    - Implement `missing_handlers()` so the engine can refuse a merge naming each location without a handler
    - Add the allow-list for generic reference fields such as `LinkedEntity.entity_id`
    - _Requirements: 1.1, 1.2, 1.3, 1.6, 1.7, 22.17, 32.5_

  - [x] 1.2 Implement pure merge rule functions
    - Create `slaktbusken/services/merge_rules.py` with attribute resolution (sex, title, occupation, profile media, notes concatenation with visible separator), name union with identity `(given, surname, type, event_id)` and primary-name reordering, `rewrite_participants`, link collapse for media links, research note links, cluster ids and parent-child links
    - Whitespace-only counts as empty; a non-empty value is never overwritten by an empty one; no function chooses a survivor by a computed criterion
    - Implement the Similar_Event_Rule as pure functions: `is_similar_event_pair(event_1, event_2, max_day_distance=365) -> bool` and `find_similar_event_pairs(events_person_1, events_person_2) -> list[tuple[str, str]]` (sorted `(event_id_of_person_1, event_id_of_person_2)`); type equal (custom type name too); both events dated, precision taken from `date_span.precision_of` of the ISO value (not `DateValue.precision`), malformed value counts as no date; dates compatible when equal at the coarser shared precision or when both are full dates at most 365 days apart (`date_span.expand_iso(value).start`; the 365-day branch never applies to year-only or month-only dates); places do not contradict when at least one side has no place (`None` or empty `place_id`) or both ids are equal; type, date and place must all hold; events of the same person are never compared and an event shared by both persons is skipped
    - _Requirements: 1.4, 21.2, 21.3, 21.4, 21.5, 21.6, 21.7, 21.8, 21.9, 21.10, 21.12, 21.13, 21.14, 21.15, 22.3, 22.9, 23.2, 23.3_

  - [x] 1.3 Write inventory completeness tests (Mandatory group a: reference preservation)
    - Module `tests/test_services/test_person_reference_index.py` with `pytestmark = pytest.mark.mandatory_integrity`; required, never skipped
    - `test_inventory_lists_every_person_reference_field`: reflection over `slaktbusken.model` dataclasses finds every `*person_id` / `*person_ids` field in the inventory or the allow-list
    - `test_inventory_check_fails_for_unlisted_field`: a synthetic dataclass with a `person_id` field fails the check and names class and field
    - _Requirements: 1.8, 35.1, 35.2_

  - [x] 1.4 Write property test for names and notes
    - **Property 26: Notes and names**
    - **Validates: Requirements 21.6, 21.8, 21.9, 21.10**
    - Module `tests/properties/test_property_26_notes_names.py` (not mapped to a Mandatory_Test_Group by the design)

  - [x] 1.5 Write property test for event participants
    - **Property 27: Event participants**
    - **Validates: Requirements 21.12, 21.13**
    - Module `tests/properties/test_property_27_participants.py` (not mapped to a Mandatory_Test_Group by the design)

  - [x] 1.6 Write property test for link collapse (Mandatory group a: reference preservation)
    - **Property 30: Link collapse**
    - **Validates: Requirements 22.3, 22.9, 23.2, 23.3, 23.4, 23.5, 24.7**
    - Module `tests/test_services/test_merge_reference_rules.py` with `pytestmark = pytest.mark.mandatory_integrity`; function named `test_property_30_link_collapse`; at least 100 examples; required, never skipped

  - [x] 1.7 Create the mandatory-test registry, marker configuration and conftest hooks
    - Create `tests/mandatory_groups.py` with `MandatoryGroup` and `MANDATORY_GROUPS` for the six groups (reference_preservation, family_relationship_integrity, failed_merges, crash_recovery, retired_id_preservation, gedcom_reimport_after_merge), exactly as in the design table: modules, mapped properties and the `required_tests` names; this file is the single source for the hooks, the guard test and the runner
    - Also define `WINDOWS_ONLY_TESTS` in that file: the module `tests/test_services/test_commit_preflight.py` and its platform-conditional test names (see 13.21); these tests are required, are the only tests allowed a `skipif`, and the only permitted condition is `sys.platform != "win32"`
    - Create or extend `pytest.ini`: register markers `mandatory_integrity`, `windows_only` and `slow` (benchmarks only), set `--strict-markers`; no `-m`, `-k`, `--deselect` or `--ignore` in `addopts`
    - Create or extend `tests/conftest.py`: `pytest_collection_modifyitems` raises `pytest.UsageError` ("Obligatoriskt test har skip, skipif eller xfail: <nodeid>") for any mandatory item with `skip`, `skipif`, `xfail`, `slow` or another opt-out marker (also via `pytest.param(..., marks=...)`); `pytest_runtest_makereport` hook wrapper turns every skipped or xfail report of a mandatory item into a failure with "Obligatoriskt test hoppades över eller förväntades misslyckas" and an unexpected xpass into a failure; with `SBK_MANDATORY_STRICT=1`, `pytest_collection_finish` and `pytest_deselected` abort with exit code 3 when a required test is not collected or a mandatory item is deselected; load the Hypothesis profile `sbk` (default example count, no lowering)
    - The same `pytest_runtest_makereport` wrapper also turns a skipped report of a `windows_only` test into a failure ("Windows-test hoppades över på Windows") when `sys.platform == "win32"`; on other platforms those tests skip normally
    - A mandatory module imports PySide6, the GEDCOM modules and Hypothesis unconditionally (collection error, never a skip)
    - _Requirements: 35.1, 35.2, 35.3, 35.5, 35.6_

- [~] 2. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Phase 2: Candidate model, persistence and version 0.4
  - [x] 3.1 Create the candidate model, id prefixes, project fields and validators
    - Create `slaktbusken/model/merge_candidate.py` with `MergeCandidate`, `MergeCandidateComment`, `MergeHistoryEntry`, `ArchivedCandidate`, `MergedIdentityMapping`, constants, `pair_key`, `ASSESSMENT_LABELS_SV`
    - Add `merge_candidates`, `merge_history` and the transient `merge_load_findings` to `ProjectData`
    - Register prefixes `mergecand_`, `mergecomment_`, `merge_` in `IDGenerator._PREFIXES`
    - Add `validate_merge_candidate`, `validate_merge_candidate_comment`, `validate_merge_history_entry` returning Swedish messages, reusing `is_valid_calendar_date`
    - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 4.1, 4.3, 34.1, 34.2_

  - [x] 3.2 Write example tests for the model and id prefixes
    - Module `tests/test_model/test_merge_candidate.py`
    - Defaults, `pair_key` symmetry, prefix regex isolation between `mergecand_`, `mergecomment_`, `merge_`, equality of `ASSESSMENT_LABELS_SV` and the locale labels
    - _Requirements: 2.2, 3.1, 34.9_

  - [x] 3.3 Implement `id_registry` and protect retired person ids
    - Create `slaktbusken/services/id_registry.py` with `ProtectedIdGenerator`, `reconcile_id_high_water_marks`, `retired_person_ids`, `issue_person_id`
    - Make `research_service.reconcile_id_high_water_marks` delegate to the registry and keep `ResearchIdGenerator` as a thin subclass
    - Replace the four direct person-id generator call sites (`app.py` twice, `GEDCOMImporter.__init__`, `ParentService.__init__`) with `issue_person_id`; seed the importer's own generator with `retired_person_ids` as well
    - Keep `id_high_water_marks` empty for projects without research or merge data
    - _Requirements: 2.3, 7.5, 7.6, 28.3, 34.9_

  - [x] 3.4 Write property test for candidate, comment and history id prefixes
    - **Property 3: Ids of candidates, comments, history entries and retired persons are never reissued** (prefix part)
    - **Validates: Requirements 2.3, 7.5, 7.6, 28.3, 34.9**
    - Module `tests/test_services/test_id_registry.py`; the retired-person part is the required task 13.19

  - [x] 3.5 Implement serialization, tolerant loading, migration to 0.4 and backup
    - Write and read `merge_candidates` and `merge_history`, extend `_NESTED_LIST_TYPES`, add `_deserialize_merge_section` that keeps readable fields, records `LoadFinding` entries and preserves unreadable items in `unreadable_merge_items`; raise `CorruptedFileError` for a non-list section
    - Register the additive idempotent migration `0.3 -> 0.4`; set version 0.4 together in `MigrationManager.CURRENT_VERSION`, `file_io.CURRENT_VERSION`, the `ProjectData.version` default and `ProjectService.create_project`; for unmerged projects only the two version fields differ (Requirement 7.14)
    - Split `FilePersistence.encode` out of `save` for later reuse by the commit
    - Extend `MigrationManager.create_backup` through a shared helper `backup_project_files(path, old_version)` that also copies `translation/persons.json` when present and skips it silently otherwise; same naming and location rules as earlier migrations
    - Scope (design finding 10): these `persons.json` backup rules apply ONLY to `MigrationManager.create_backup` and to the merge Recovery_Point taken by the Merge_Transaction (13.3). Do NOT add a general-purpose project backup feature, setting, menu entry or API; no task in this plan implements one
    - Must run after 3.13 so the golden 0.3 fixtures are produced by the pre-feature code
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.7, 7.8, 7.9, 7.10, 7.11, 7.14, 32.1_

  - [x] 3.6 Write property test for the project round trip (required by Requirement 32.6)
    - **Property 1: Project round trip with merge data**
    - **Validates: Requirements 2.1, 4.6, 7.1, 7.4, 28.11**
    - Module `tests/test_persistence/test_merge_persistence.py`; required, no skip, xfail or deselect; not part of the six Mandatory_Test_Groups

  - [x] 3.7 Add Identity_Alias support to `translation_io`
    - Add `IdentityAlias`, `TranslationData.person_aliases`, `read_person_aliases`, alias argument to `write_persons`, `write_all` pass-through, and pure `dumps_persons(person_mappings, family_mappings, aliases) -> bytes`
    - A file without `identity_aliases` loads with an empty list; reading then writing gives equal content
    - _Requirements: 30.1, 30.2, 30.3, 30.10_

  - [x] 3.8 Write example tests for alias read and write
    - Module `tests/test_persistence/test_translation_aliases.py`
    - File without aliases, aliases round trip, `dumps_persons` equals bytes written by `write_persons`
    - _Requirements: 30.2, 30.3_

  - [x] 3.9 Write property test for the 0.4 migration
    - **Property 2: Migration to 0.4 is additive and idempotent**
    - **Validates: Requirements 7.2, 7.3**
    - Module `tests/properties/test_property_02_migration.py`

  - [x] 3.10 Write property test for malformed merge data
    - **Property 4: Malformed merge data is kept and reported**
    - **Validates: Requirements 7.7**
    - Module `tests/properties/test_property_04_malformed_merge_data.py`

  - [x] 3.11 Write property test for validators
    - **Property 5: Validation of assessments, comments and dates**
    - **Validates: Requirements 3.2, 4.3, 4.4**
    - Module `tests/properties/test_property_05_validators.py`

  - [x] 3.12 Write property test and example tests for unaffected projects
    - **Property 45: Projects without merge data are unaffected**
    - **Validates: Requirements 7.14, 32.1**
    - Module `tests/properties/test_property_45_unaffected_projects.py`; compare with the frozen 0.3 serialiser only through `assert_equal_except_version_fields` (3.13)
    - Include the version-consistency test (four version constants equal, migration path from 0.1 to 0.4)

  - [x] 3.13 Create the version-compatibility helper, frozen 0.3 serialiser and golden fixtures
    - Create `tests/helpers/compat.py` with `VERSION_KEYS`, `PLACEHOLDER`, `decode_project`, `normalise_version_fields` (replaces only the values of the top-level `version` and `format_version`; absent keys stay absent; nothing nested is touched; input not modified) and `assert_equal_except_version_fields(before, after, old_versions, new_version)` (deep order-sensitive comparison, fails for a wrong old or new version, lists the first 10 differing JSON paths)
    - Create `tests/helpers/frozen_serialiser_v0_3.py` (frozen copy of the 0.3 serialiser used by Property 45)
    - Create `scripts/make_compat_fixtures.py` and commit `tests/fixtures/compat/v0_3_*.json` (empty, research cases, residences, mixed project with foster families and DNA), generated with the code before this feature; run this task before 3.5 changes the version
    - No other helper may normalise anything else; every compatibility and regression test uses this helper only
    - _Requirements: 7.14, 32.1_

  - [x] 3.14 Write meta-tests for the compat helper and golden-fixture tests
    - Module `tests/test_persistence/test_version_compat.py`
    - Meta-tests: only `version`/`format_version` differences pass; any other top-level difference fails; a nested key called `version` or `format_version` differing fails; a missing `version` fails; an extra empty `merge_candidates` or `merge_history` list fails; inputs unchanged; `before` 0.4 or `after` 0.3 fails
    - Golden tests: load, migrate and save each golden 0.3 file and compare; build the same project in code, serialise with the new code and compare
    - _Requirements: 7.14, 32.1_

  - [x] 3.15 Write tests for the migration backup scope (Req 7.9, 7.10)
    - Module `tests/test_persistence/test_backup_scope.py`
    - `MigrationManager.create_backup` copies `translation/persons.json` next to the project backup when it exists, and completes without error and without that file when it does not exist; naming and location are the same as for earlier migrations
    - A static test asserts that `backup_project_files` is referenced only by `MigrationManager.create_backup` and the Merge_Transaction backup, and that no other backup API was added
    - The Recovery_Point side (with and without `persons.json`) is covered by the crash matrix in 13.13
    - _Requirements: 7.8, 7.9, 7.10_

- [~] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Phase 3: Candidate register, saved state and research integration
  - [x] 5.1 Implement the candidate service and `ProjectService` API
    - Create `slaktbusken/services/merge_candidate_service.py` with create, set assessment, enable or disable, link or unlink research case, add, edit and delete comment, all copy-validate-swap
    - Add `ProjectService` wrappers that set the dirty flag and notify merge listeners through the counters of 5.16
    - Reject equal ids, unknown persons, duplicate unordered pairs and unknown research cases with the Swedish messages in the design; return the existing candidate for a duplicate pair
    - Never create a candidate from computed similarity
    - _Requirements: 2.3, 2.4, 2.5, 2.6, 2.7, 2.9, 2.10, 3.3, 3.4, 3.6, 3.7, 4.2, 4.4, 4.5, 5.1, 5.5, 5.6, 5.7, 33.9_

  - [x] 5.2 Write property test for unordered pair identity (required by Requirement 32.6)
    - **Property 6: Unordered pair identity and uniqueness**
    - **Validates: Requirements 2.9, 5.5, 5.6, 5.7**
    - Module `tests/test_services/test_merge_candidate_service.py`; required, no skip, xfail or deselect; not part of the six Mandatory_Test_Groups

  - [x] 5.3 Integrate candidates with research cases
    - Implement "Skapa forskningsärende" as one operation creating the `ResearchCase` and two `ResearchEntityLink` entries (one per person) and setting `research_case_id`, rolled back completely on failure
    - Implement removing the association without deleting case, links or candidate
    - Ensure `delete_service` leaves candidates that reference a deleted research case unmodified
    - Never derive a Candidate_Assessment from a hypothesis assessment or the reverse
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.8_

  - [x] 5.4 Implement redirect resolution
    - Create `slaktbusken/services/redirect_resolution.py` with `RedirectResolver` over `merge_history`: terminating resolution, cycle detection with no person resolved and a reported cycle, ordering by merge date then creation sequence, `merged_into(survivor)`
    - _Requirements: 28.5, 28.6, 28.7, 28.8, 28.9_

  - [x] 5.5 Write property test for redirect resolution
    - **Property 23: Redirect resolution**
    - **Validates: Requirements 28.5, 28.6, 28.7, 28.8**
    - Module `tests/properties/test_property_23_redirect_resolution.py`

  - [x] 5.6 Implement register filtering, search and sorting logic
    - Create `slaktbusken/services/candidate_register.py` (Qt-free): default view of enabled candidates with assessment `unreviewed`, `possible` or `confirmed`; filters for rejected and disabled; case-insensitive search over person name, person id, comment text and research case title that includes disabled candidates when either person matches; sorting; latest-comment cell rule
    - _Requirements: 3.8, 5.2, 5.3, 5.4, 15.2, 15.3, 15.4, 15.5, 15.9, 15.12_

  - [x] 5.7 Write property test for register filtering
    - **Property 10: Register filtering, search and sorting**
    - **Validates: Requirements 3.8, 5.2, 5.3, 5.4, 15.2, 15.3, 15.4, 15.5, 15.9**
    - Module `tests/properties/test_property_10_register_filtering.py`

  - [x] 5.8 Add Swedish labels, `MergeGateway` and the candidate editor dialog
    - Add `get_candidate_assessment_label` and `get_candidate_section_label` to `ui/swedish_locale.py`
    - Create `ui/merge/merge_gateway.py` mirroring `research_gateway.py` (`open_comparison`, `mark_candidates`, `open_candidate`, `open_register`, `open_history`, `merge_changed`, `set_merge_gateway`, `get_merge_gateway`)
    - Create `CandidateEditorDialog` with assessment selector, enabled toggle, research case picker (reusing `research_case_picker_dialog`), dated comments with the confirmation prompt for deletion, and unsaved-text protection
    - _Requirements: 3.1, 3.4, 3.9, 4.2, 4.4, 4.7, 4.8, 6.2, 6.3, 6.5, 13.6, 13.11, 13.12_

  - [x] 5.9 Build the Candidate_Register window and register it in the application
    - Create the "Sammanslagningskandidater" window with the columns, filters, search, sorting, empty-table message and edit actions from Requirement 15
    - Make `Application` implement and register the `MergeGateway`; create the single `EditorRegistry` instance (5.18) owned by `Application`; add the main-window action to open the register
    - _Requirements: 8.1, 8.8, 8.9, 15.1, 15.2, 15.6, 15.7, 15.8, 15.10, 15.11, 15.12, 26.14_

  - [x] 5.10 Add the candidate section to the Person_Editor
    - Show the person's candidates with a "Visa historiska" toggle, a create action disabled until the person is first saved, and links to the editor, comparison and register
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7, 16.8, 16.9, 16.12_

  - [x] 5.11 Write widget tests for the editor dialog, register and editor section
    - Module `tests/test_ui/test_candidate_register.py`
    - Columns, filters, empty state, comment deletion prompt, unsaved text protection, section visibility toggle (pytest-qt, offscreen)
    - _Requirements: 4.4, 4.7, 4.8, 15.1, 15.12, 16.1_

  - [x] 5.12 Write property test for read-only candidate operations
    - **Property 7: Candidate operations never change genealogical data and are always explicit**
    - **Validates: Requirements 2.4, 2.7, 3.4, 3.7, 13.10, 15.7, 33.9**
    - Module `tests/properties/test_property_07_candidate_read_only.py`

  - [x] 5.13 Write property test for field-local edits
    - **Property 8: Assessment, enabled and comment edits change only their own field**
    - **Validates: Requirements 3.6, 4.5, 5.1**
    - Module `tests/properties/test_property_08_field_local_edits.py`

  - [x] 5.14 Write property test for failed edits
    - **Property 9: A failed candidate edit leaves the stored state unchanged**
    - **Validates: Requirements 3.9, 6.4, 13.7**
    - Module `tests/properties/test_property_09_failed_edits.py`

  - [x] 5.15 Write property test for editor section visibility
    - **Property 22: Editor section visibility**
    - **Validates: Requirements 16.1, 16.8**
    - Module `tests/properties/test_property_22_editor_section_visibility.py`

  - [x] 5.16 Implement the Revision_Counter, content revision and saved state in `ProjectService` (R1)
    - In `slaktbusken/services/project_service.py` turn `_dirty` into a property that keeps its name and meaning; the setter with `True` calls `_record_change()` which increments `revision` and `content_revision` and notifies merge listeners; `False` increments nothing
    - Add `revision`, `content_revision`, `clean_content_revision` (set by `open_project`, `save_project` and the adopt step), `is_saved_state()` returning `not _dirty and content_revision == clean_content_revision`, `add_merge_listener`, `notify_merge_changed`
    - `save_project` increments `revision` but not `content_revision`; `save_project` raises `MergeInProgressError` while the engine runs
    - Add the adopt step `adopt_committed_state(...)`: writes the private dirty value `False` (not through the `True` setter), increments `revision` and `content_revision` by exactly one each and notifies listeners exactly once
    - All counters are in-memory and never serialised
    - _Requirements: 26.9, 26.12, 27.1, 27.8, 27.24_

  - [x] 5.17 Write tests for the revision counters and saved state (Mandatory group c: failed merges)
    - Module `tests/test_services/test_saved_state.py` with `pytestmark = pytest.mark.mandatory_integrity`; required, never skipped
    - A legacy `_dirty = True` write increments `revision` and `content_revision` once and notifies once; `False` increments nothing; a save increments `revision` only and leaves `content_revision` and the plan fingerprint equal; `is_saved_state()` is false for a mutation that forgot the flag; the adopt step clears the dirty flag, increments each counter by exactly one and notifies exactly once
    - _Requirements: 26.12, 27.1, 27.24_

  - [x] 5.18 Implement the editor registry and `UnsavedChangesParticipant` protocol (R2)
    - Create `slaktbusken/services/editor_registry.py` (Qt-free): `ResolutionResult` (saved, discarded, still_unsaved), `UnsavedChangesParticipant` protocol (`editor_title`, `has_unsaved_changes()`, `request_resolution()`), `EditorRegistry` with `register`, `unregister` (weak references) and `unsaved_editors()` in registration order
    - The registry never calls a save or discard method of an editor
    - _Requirements: 26.14, 27.23_

  - [x] 5.19 Make the Person_Editor and all other editors participate in the registry (R2)
    - In `slaktbusken/ui/editors/`: `PersonEditor` implements `has_unsaved_changes()` by comparing its widgets to the loaded person and `request_resolution()` by showing its own modal prompt ("Spara", "Kasta ändringar", "Avbryt") parented to the editor; the event, family, place, source, media, DNA, research case and translation editors register on construction and unregister on `destroyed`; editors that already expose `is_dirty()` delegate to it
    - `request_resolution()` is called only when the user presses "Gå till redigeraren" in the wizard; nothing is saved or discarded automatically
    - _Requirements: 26.14, 27.23_

  - [x] 5.20 Write registry tests and the editor completeness test (Mandatory group c: failed merges)
    - Module `tests/test_services/test_saved_state.py` (same module as 5.17, mandatory marker); required, never skipped
    - Registry order, weak references, `unsaved_editors()` with a counting `FakeEditor`; a completeness test enumerates the `QWidget` subclasses in `slaktbusken/ui/editors` and fails for any class that is neither registered nor exempted with a documented reason
    - _Requirements: 26.14, 27.23_

- [~] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Phase 4: Comparison window
  - [x] 7.1 Implement `PersonSummaryIndex` and `PersonSearchIndex`
    - Create `services/person_summary.py` (one pass over events and persons: name, lifespan text, birth and death text) and `services/person_search.py` (substring search over name, id and dates, at least two characters, at most 50 results, results distinguishable by dates, places and ids)
    - _Requirements: 9.7, 9.8, 19.8, 19.10_

  - [x] 7.2 Implement `DiagramLookup` and remove per-box scans from the diagram views
    - Create `services/diagram_lookup.py` with render-scoped indexes for events, DNA profiles, clusters and persons; use it in the family, ancestry and descendants views and in `PersonBoxItem` data building
    - Keep siblings in the family view (Requirement 10.5); the lookup must expose siblings so the Comparison_Family_View can render them
    - Output of every `display_data` must be equal with and without the lookup
    - _Requirements: 10.5, 12.7, 32.3, 32.4_

  - [x] 7.3 Implement `ComparisonSession`
    - Create `services/comparison_session.py` (Qt-free): slot contents, swap, assign with rejection of the same person, navigation stack with maximum depth 20 and exact context restore, per-view selection state, pair-action enablement, Shared_Person set by identical id only (including sibling ids), comparison rows with "Avviker" and "Saknas" classification, menu enablement and slot order from the person list, "Fortsätt till sammanslagning" enablement
    - No similarity logic anywhere
    - _Requirements: 9.1, 9.6, 9.10, 9.12, 10.5, 11.2, 11.3, 11.4, 11.5, 11.9, 12.1, 12.3, 12.5, 12.6, 12.7, 13.1, 13.3, 13.4, 13.5, 14.1, 14.2, 14.3, 14.4, 14.9, 14.10, 20.2, 20.3, 33.3_

  - [x] 7.4 Write property test for menu enablement and selection order
    - **Property 11: Menu enablement and selection order**
    - **Validates: Requirements 8.4, 8.5, 8.6, 8.7, 9.1**
    - Module `tests/properties/test_property_11_menu_enablement.py`

  - [x] 7.5 Build the Person_Comparison_Window
    - Create `ui/merge/` comparison window: horizontal `QSplitter` with two Person_Slots (Slot_Search_Control above a Comparison_Family_View with independent navigation, expansion and zoom) and the Comparison_Table; each Comparison_Family_View shows parents, partners, children and siblings (sibling row); resizable and maximizable; empty-state indication; clear a slot when its person is deleted; refresh within the stated times on project change
    - Apply the same diagram settings as the main diagram
    - _Requirements: 9.2, 9.3, 9.4, 9.5, 9.7, 9.8, 9.9, 9.11, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 10.10, 10.11, 10.12, 10.13, 10.14, 11.1, 11.6, 11.7, 11.10, 11.11, 18.13_

  - [x] 7.6 Add shared markers, pair selection, candidate panel and sub-comparison
    - Shared_Person marker in both views (ids only, siblings included), candidate relation display, one selected person per view with pair actions "Markera som sammanslagningskandidater" and "Jämför dessa", candidate panel for the current pair, navigation back, depth-20 message, "Fortsätt till sammanslagning" button
    - _Requirements: 10.5, 12.1, 12.2, 12.3, 12.4, 12.8, 13.1, 13.2, 13.3, 13.5, 13.6, 13.8, 13.9, 13.11, 14.5, 14.6, 14.7, 14.8, 14.10, 9.12, 20.1_

  - [x] 7.7 Add menu and context-menu entry points
    - Add "Jämför personer..." to the Person menu, comparison and candidate actions to diagram box menus, and extend `ContextMenuBuilder.build_person_menu(selected_ids: Sequence[str])` (ids ordered by row): "Markera som sammanslagningskandidater" enabled only for exactly two ids, "Jämför personer..." enabled for one or two ids, both disabled for none or three or more
    - Add the signals `compare_requested(list)` and `mark_candidates_requested(list)` carrying the ordered ids (the existing `context_menu_action(str, str)` signal is unchanged) and connect them in `Application` to the `MergeGateway`
    - Disable all feature actions while no project is open
    - The selection mode and right-click handling of the Person_List itself are done in 7.18
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.10, 8.11, 9.1_

  - [x] 7.8 Write widget tests for the comparison window
    - Module `tests/test_ui/test_comparison_window.py`
    - Layout, search widget results, shared badge, action area, entry-point enablement, diagram lookup equivalence
    - _Requirements: 10.1, 12.1, 8.4, 8.5_

  - [x] 7.9 Write property test for slot search
    - **Property 12: Slot search**
    - **Validates: Requirements 9.7**
    - Module `tests/properties/test_property_12_slot_search.py`

  - [x] 7.10 Write property test for slot operations
    - **Property 13: Slot operations**
    - **Validates: Requirements 9.6, 9.10, 9.12, 20.2, 20.3**
    - Module `tests/properties/test_property_13_slot_operations.py`

  - [x] 7.11 Write property test for independent view state
    - **Property 14: Independent view state**
    - **Validates: Requirements 10.7, 10.8, 10.9, 10.14**
    - Module `tests/properties/test_property_14_independent_view_state.py`

  - [x] 7.12 Write property test for comparison row classification
    - **Property 15: Comparison row classification**
    - **Validates: Requirements 11.2, 11.3, 11.4, 11.5, 11.9**
    - Module `tests/properties/test_property_15_row_classification.py`

  - [x] 7.13 Write property test for shared persons and candidate relations
    - **Property 16: Shared persons and candidate relations depend on ids only**
    - **Validates: Requirements 12.1, 12.3, 12.5, 12.6, 12.7, 33.3**
    - Module `tests/properties/test_property_16_shared_persons.py`

  - [x] 7.14 Write property test for pair selection
    - **Property 17: Pair selection**
    - **Validates: Requirements 13.1, 13.3, 13.4, 13.5**
    - Module `tests/properties/test_property_17_pair_selection.py`

  - [x] 7.15 Write property test for the navigation stack
    - **Property 18: Navigation stack**
    - **Validates: Requirements 14.1, 14.2, 14.3, 14.4, 14.9, 14.10**
    - Module `tests/properties/test_property_18_navigation_stack.py`

  - [x] 7.16 Write widget test for siblings in the comparison family views (R5)
    - Module `tests/test_ui/test_comparison_window.py` (run after 7.8)
    - A focal person with two siblings renders three boxes in the sibling row of the `ComparisonFamilyView`; the sibling ids are part of the visible id set used for Shared_Person markers
    - _Requirements: 10.5, 12.1_

  - [x] 7.17 Write example tests for same-ID relatives and same-named siblings (required by Requirement 32.7)
    - Module `tests/test_services/test_comparison_session_examples.py`; required, no skip, xfail or deselect
    - Same-ID relatives present in both views get the Shared_Person marker in both (12.1); two siblings with the same name in one view and across both views get no shared marker unless their ids are identical (12.7)
    - _Requirements: 12.1, 12.7, 32.7_

  - [x] 7.18 Implement multi-selection and right-click handling in the Person_List
    - In `slaktbusken/ui/person_list_panel.py` switch `_tree_widget` from `SingleSelection` to `ExtendedSelection`; Ctrl-click and Shift-click use standard Qt behaviour and are not reimplemented (Req 8.13)
    - Keep current-person navigation: `currentItemChanged` still drives `person_selected` and the diagram; a plain click selects exactly one row and sets the current person exactly as before this feature (Req 8.12); add no second navigation path
    - Add the module-level pure function `rows_after_right_click(selected_rows, clicked_row) -> list[int]` (no Qt types): empty list for `None`, the unchanged selection when the clicked row is inside it, otherwise only the clicked row
    - Override `mousePressEvent`: for the right button over an already selected item accept the event and do NOT pass it to `QTreeWidget.mousePressEvent` (selection, current item and anchor stay); over an unselected item pass it on unchanged so only that row is selected (Req 8.15); left and middle buttons are passed on unchanged
    - Override `contextMenuEvent`: read `selectedItems()` after the press, convert to person ids ordered by row, call `ContextMenuBuilder.build_person_menu(selected_ids)`; never call `setCurrentItem`, `clearSelection` or `setSelection`; a keyboard-invoked menu uses the current selection as is; right-click on empty space opens the menu with both entries disabled
    - Keep the candidate/research indicator refresh from clearing the selection or scroll position (Req 17.12)
    - _Requirements: 8.4, 8.5, 8.6, 8.7, 8.12, 8.13, 8.14, 8.15_

  - [x] 7.19 Write property test for the right-click selection rule
    - **Property 51: Right-click selection rule**
    - **Validates: Requirements 8.14, 8.15**
    - Module `tests/test_ui/test_person_list_selection.py`: pure tests of `rows_after_right_click` over generated selections and clicked rows (inside: same rows in the same order; outside: exactly the clicked row; none: no rows; for a selection of two or more and a right-click inside it, the person ids passed to the menu equal the ids before the click); also the pure examples
    - Tag `# Feature: person-comparison-and-merge, Property 51: Right-click selection rule`

  - [x] 7.20 Write person-list selection regression tests (Req 8.16)
    - Module `tests/test_ui/test_person_list_selection.py` (run after 7.19; pytest-qt, offscreen, `exec` of the menu replaced by a recording stub)
    - (1) A plain click selects one row and `person_selected` and the current person are set as before this feature; (2) Ctrl-click adds a second row and Ctrl-click on a selected row removes it; (3) Shift-click selects the contiguous range from the anchor; (4) with two rows selected the context menu enables "Jämför personer..." and "Markera som sammanslagningskandidater", with one row only the first, with three rows or none neither; (5) right-click on a row inside a two-person selection leaves `selectedItems()` unchanged and opens the menu with both ids; (6) right-click on a row outside the selection selects only that row and opens the menu with that id; (7) right-click on empty space opens a menu with both entries disabled; (8) a Ctrl-click that changes the current item still navigates to that person
    - _Requirements: 8.4, 8.5, 8.6, 8.12, 8.13, 8.14, 8.15, 8.16_

- [~] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
  - Includes `tests/test_ui/test_person_list_selection.py` (Property 51 and the Req 8.16 regression tests) and the existing person-list tests, unmodified.

- [x] 9. Phase 5: Indicators, settings and research person filter
  - [x] 9.1 Implement `CandidateIndex`, indicator colour and tooltips
    - Create `services/candidate_index.py` with the single `indicator_colour` function (blue, orange, grey, none), per-person relations, tooltip lines in the specified Swedish form ordered by group then name, five-line limit with a summary line, lifespan rendering without empty parentheses, "Okänd person" fallback, names from current data or Merge_History
    - _Requirements: 19.1, 19.2, 19.3, 19.4, 19.5, 19.6, 19.7, 19.8, 19.9, 19.10, 19.11, 28.4_

  - [x] 9.2 Add `PersonBoxConfig.merge_candidates` and settings readers
    - Add the field and read it in `settings_io.read_settings` and `app_settings_io` with a default for files lacking the key; map a missing `PersonListConfig.research` to the combined setting enabled
    - Label the Person_List header context-menu toggle for the research column exactly "Forskningsuppslag och dubletter" (the same text as the Settings_Dialog checkbox of 9.3); both controls change the same combined setting (`PersonListConfig.research`)
    - _Requirements: 17.1, 17.3, 17.12, 17.13, 17.14, 18.3, 18.11, 18.12_

  - [x] 9.3 Update Settings_Dialog labels (user decision 5)
    - Person-list checkbox exactly "Forskningsuppslag och dubletter" (controls both the research indicator and the Candidate_Indicator); diagram checkboxes exactly "Forskningsuppslag" (existing `PersonBoxConfig.research`) and "Sammanslagningskandidater", independent of each other and of the person-list setting; keep attribute names `_pl_check_research` and `_check_research`
    - _Requirements: 17.1, 17.2, 17.3, 18.1, 18.2, 18.3_

  - [x] 9.4 Add the person-list `ResearchColumnDelegate`
    - Draw research glyph and candidate indicator with non-overlapping hit rectangles, set the research column header to exactly "Forskningsuppslag" (replacing "Forskningsärenden"; the column count is unchanged), tooltips via the 500 ms wake-up hint
    - A click on the research glyph emits `research_indicator_clicked(person_id)` (connected to the research gateway with a person filter in 9.13); a click on the candidate indicator opens the candidate or register for that person and never reaches the research glyph handler
    - _Requirements: 17.4, 17.5, 17.6, 17.7, 17.8, 17.9, 17.10, 17.11, 19.6_

  - [x] 9.5 Add candidate indicators to diagram person boxes
    - Draw the indicator in `PersonBoxItem` independent of the research marker, with its own hit rectangle, 500 ms hover tooltip, click handling through the gateway, and no overlap with the research marker or the Shared_Person marker
    - The research marker's `mousePressEvent` calls `show_research_for_entity("person", id, person_filter=id)` (comparison family views reuse `PersonBoxItem` and behave the same)
    - _Requirements: 18.4, 18.5, 18.6, 18.7, 18.8, 18.9, 18.10, 18.13, 18.14, 19.6_

  - [x] 9.6 Write example tests for settings and labels
    - Module `tests/test_ui/test_merge_indicators.py`
    - Exact labels of the three checkboxes ("Forskningsuppslag och dubletter", "Forskningsuppslag", "Sammanslagningskandidater"), of the header context-menu toggle ("Forskningsuppslag och dubletter") and of the column header ("Forskningsuppslag"), old `PersonListConfig.research` value read into the combined setting, file without `merge_candidates` key, unchanged attribute names
    - _Requirements: 17.1, 17.2, 17.14, 18.1, 18.2, 18.12_

  - [x] 9.7 Write property test for indicator colour precedence
    - **Property 19: Indicator colour precedence**
    - **Validates: Requirements 17.11, 19.1, 19.2, 19.3, 19.4, 19.5, 28.4**
    - Module `tests/properties/test_property_19_indicator_colour.py`

  - [x] 9.8 Write property test for tooltip content and ordering
    - **Property 20: Tooltip content and ordering**
    - **Validates: Requirements 19.6, 19.7, 19.8**
    - Module `tests/properties/test_property_20_tooltips.py`

  - [x] 9.9 Write property test for exclusive hit targets
    - **Property 21: Exclusive indicator hit targets**
    - **Validates: Requirements 17.7, 18.6, 18.10**
    - Module `tests/properties/test_property_21_hit_targets.py`

  - [x] 9.10 Add `build_person_scope` and optional `person_scope` to the research row builders (R6)
    - In `slaktbusken/ui/research_overview.py` (no-Qt part) add `PersonResearchScope` and `build_person_scope(index, person_id)` from `ResearchIndex` (cases from `cases_for_entity("person", pid)`, pending actions of those cases, hypotheses of those cases plus `hypotheses_for_entity("person", pid)`)
    - Add the optional parameter `person_scope=None` to `build_overview_case_rows`, `build_todo_rows` and `build_overview_hypothesis_rows`; with `None` the rows are identical to the pre-feature rows; with a scope closed cases and their actions are included
    - _Requirements: 17.6, 17.8, 17.15, 17.16_

  - [x] 9.11 Add the person filter, banner and "Visa alla" to `ResearchOverview` (R6)
    - `set_person_filter(person_id)` and `person_filter()`: build the scope once per refresh, switch the status filter to "all" (remember the previous choice), refill the cases, to-do and hypotheses pages; `set_person_filter(None)` restores the remembered choice; `refresh()` keeps the filter
    - Banner above the tabs, visible only while filtered: "Filtrerat på person: <namn> (<person-id>)" and button "Visa alla" with an accessible name and a place in the tab order; a missing person shows "Okänd person (<id>)" and empty tables
    - The person filter is independent of the case page's "Valfritt objekt..." filter
    - _Requirements: 17.8, 17.15, 17.16_

  - [x] 9.12 Extend the research gateway and `Application` with the optional `person_filter` (R6)
    - Add `person_filter: Optional[str] = None` to `show_research_for_entity` in `ui/research_gateway.py` (Protocol) and `Application`, and to `Application.show_research_overview`; `show_research_overview` clears any earlier person filter when called without one so every existing caller (menu entries, editors' tabs, `show_research_for_entity("place", id)`) behaves exactly as before
    - One overview window is reused: a call with a person filter raises it, sets the filter and switches to the cases page
    - _Requirements: 17.6, 17.8, 17.16, 18.14_

  - [x] 9.13 Connect the person-list research indicator to the gateway (R6)
    - In `Application` connect `PersonListPanel.research_indicator_clicked` to `show_research_for_entity("person", pid, person_filter=pid)`
    - _Requirements: 17.6, 17.8, 17.16_

  - [x] 9.14 Write property test for the research overview person filter
    - **Property 50: Research overview person filter**
    - **Validates: Requirements 17.6, 17.8, 17.15, 17.16, 18.14**
    - Module `tests/test_ui/test_research_person_filter.py` (pure tests, no Qt): rows under a person scope equal the unfiltered rows restricted by an independent brute-force definition; a `None` scope returns the pre-feature rows; case row ids equal `cases_for_entity` and their count equals the indicator total

  - [x] 9.15 Write widget tests for the research person filter
    - Module `tests/test_ui/test_research_person_filter.py` (run after 9.14)
    - Banner shows name and id; "Visa alla" restores the unfiltered tables and the previous status choice; a deleted person shows the empty state; a research change keeps the filter; a click on the research glyph in the person list and on a diagram box calls the gateway with `person_filter`; a click on the candidate glyph does not; each existing caller opens an unfiltered overview with no banner and the same rows and widget state as before
    - _Requirements: 17.8, 17.15, 17.16, 18.14_

- [~] 10. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Phase 6: Merge planning and review
  - [x] 11.1 Implement `MergeDecisions`, `MergePlan` and the working copy
    - Create `services/merge_planner.py` with decision and plan dataclasses, `PlanItem` dispositions, `MergeConflict`, `UnresolvedChoice`, `InformationLedger`, and the copy-on-write working structure (structural clones of affected families, events, media and research objects; research rewire run on copies)
    - The plan records `content_revision` and a SHA-256 `fingerprint` over every object it read
    - Refuse a third person with "Exakt två personer krävs för en sammanslagning."
    - Planning never mutates `ProjectData`, translation files or settings
    - _Requirements: 20.4, 20.11, 26.2, 26.8, 26.9, 33.5, 33.6_

  - [x] 11.2 Implement attribute, name, event and residence planning
    - Attributes with unresolved choices, names with primary-name choice, event copies with rewritten participants, role conflicts, residences reassigned and never collapsed, connection override handling
    - Duplicate-event warnings: call `find_similar_event_pairs` (from 1.2) on the events that have Person 1 and Person 2 as participants before the merge; each pair yields a non-blocking `MergeConflict(severity="warning", code="similar_event", section="events", subjects=(id_1, id_2))` with the Swedish text "Händelserna kan vara dubbletter: <typ> <datum> och <typ> <datum>"
    - Both events of every warned pair stay as separate records with unchanged ids; the plan contains no combined, merged or deleted event because of a warning and requests no choice
    - _Requirements: 21.2, 21.3, 21.4, 21.5, 21.6, 21.7, 21.8, 21.9, 21.10, 21.11, 21.12, 21.13, 21.14, 21.15, 21.16, 21.17_

  - [x] 11.3 Implement source, media, DNA, research and other-reference planning
    - Source references untouched, media person links, mentions and annotations, DNA profiles, admin ids and clusters with warnings, research rewire through `rewire_entity_merge` on copies, main person, remaining inventory locations with counts and rules
    - _Requirements: 1.5, 22.1, 22.2, 22.3, 22.4, 22.5, 22.6, 22.7, 22.8, 22.9, 22.10, 22.11, 22.12, 22.13, 22.14, 22.15, 22.16, 22.17_

  - [x] 11.4 Implement family and relative planning with synchronised preview (user decisions 3 and 6)
    - Rewire families on structural clones, collapse duplicates, keep different-type links with one warning per pair, build the working copy and run the real `sync_parentage_links` on it, reconcile intended and synchronised links, run `validate_family` on every changed family, detect cycles and self-relationships, warn about equivalent families without merging them, never pair relatives (two-Brita example gives seven distinct children)
    - Compute the ledger and post-merge validation inputs; the preview is computed after the sync
    - _Requirements: 23.1, 23.2, 23.3, 23.4, 23.5, 23.6, 23.7, 23.8, 23.9, 23.10, 23.11, 23.12, 23.13, 24.1, 24.2, 24.3, 24.4, 24.5, 24.6, 24.7, 24.8, 25.1, 25.2, 25.3, 25.4, 25.5, 25.6, 26.2_

  - [x] 11.5 Implement candidate redirect and collision (user decisions 1 and 2)
    - Create `services/merge_candidate_redirect.py`: redirect B-C to A-C keeping id, enabled flag, research case and comments in order, `confirmed` becomes `possible`, `rejected` and disabled unchanged, one dated redirect comment; archive the direct candidate and self-after-redirect candidates in full
    - Collision: keep the existing id and `enabled`, take the redirected research case only when the existing one is empty, keep the common effective assessment or set `unreviewed` with one dated explanatory Swedish comment naming both assessments and ids, comments ordered existing then redirected then redirect comment then explanatory comment, archive the redirected candidate, result independent of storage order
    - _Requirements: 29.1, 29.2, 29.3, 29.4, 29.5, 29.6, 29.7, 29.8, 29.9, 29.10, 29.12, 29.13, 29.14, 29.15_

  - [x] 11.6 Write property test for read-only planning
    - **Property 24: Read-only operations leave all stored state equal**
    - **Validates: Requirements 11.8, 20.4, 20.11, 26.8, 31.6**
    - Module `tests/properties/test_property_24_read_only_planning.py`

  - [x] 11.7 Write property test for attribute resolution (Mandatory group a: reference preservation)
    - **Property 25: Attribute resolution**
    - **Validates: Requirements 1.3, 20.8, 21.2, 21.3, 21.4, 21.5, 21.7, 21.17, 22.4, 22.5, 22.15, 22.16, 26.4**
    - Module `tests/test_services/test_merge_reference_rules.py` (mandatory marker); function named `test_property_25_attribute_resolution`; required, never skipped

  - [x] 11.8 Write property test for duplicate-event warnings
    - **Property 28: Duplicate-event warnings (Similar_Event_Rule)**
    - **Validates: Requirements 21.14, 21.15**
    - Module `tests/test_services/test_similar_events.py` (required; not part of the six Mandatory_Test_Groups)
    - Generated events: a warning exactly when type is equal, both dates are present and compatible (equal at the coarser shared precision, or both full dates at most 365 days apart) and the places do not contradict (one side has none, or equal ids); no warning for pairs of one person, type-only, place-only or type+place without compatible dates, undated or malformed-date events, or contradicting places; for any project and decisions both events of every warned pair are present with unchanged ids and the plan has no combined, merged or deleted event

  - [x] 11.9 Build the Merge_Review wizard and preview
    - Create the `ui/merge/` wizard (`merge_review_wizard.py`, `merge_pages.py`, `merge_preview.py`): survivor choice with confirmation and reset-message on change, review sections for person data, names, events, residences, sources and media, DNA, research, families, relatives, other references; preview "Förhandsgranskning av sammanslagning" with blocking conflicts and warnings; plan building on a worker; rebuild with notice when `ProjectService.content_revision` or the fingerprint changes (a save alone never triggers a rebuild); disabled execution while any choice or conflict is unresolved; Execute button "Slå samman personer"
    - Second confirmation names both persons and ids and contains no statement about saving unsaved edits (none can exist)
    - _Requirements: 20.1, 20.5, 20.6, 20.7, 20.8, 20.9, 20.10, 20.12, 21.9, 21.17, 26.1, 26.3, 26.4, 26.5, 26.6, 26.7, 26.9, 26.10_

  - [x] 11.10 Write widget tests for the wizard
    - Module `tests/test_ui/test_merge_wizard.py`
    - Sections, survivor reset message, confirmation dialogs and their text (no sentence about saving unsaved edits), preview styles, disabled execution
    - _Requirements: 20.12, 26.4, 26.5, 26.9_

  - [x] 11.11 Write property test for cycles and self-relationships (Mandatory group b: family relationship integrity)
    - **Property 32: Cycle and self-relationship detection**
    - **Validates: Requirements 23.6, 23.7**
    - Module `tests/test_services/test_merge_family_integrity.py` with `pytestmark = pytest.mark.mandatory_integrity`; function named `test_property_32_cycle_and_self_relationship`; required, never skipped

  - [x] 11.12 Write property test for families staying separate (Mandatory group b: family relationship integrity)
    - **Property 33: Families stay separate**
    - **Validates: Requirements 23.9, 23.10**
    - Module `tests/test_services/test_merge_family_integrity.py`; function named `test_property_33_families_stay_separate`; required, never skipped

  - [x] 11.13 Write property test for relatives staying distinct (Mandatory group b: family relationship integrity)
    - **Property 34: Relatives stay distinct**
    - **Validates: Requirements 24.1, 24.2, 24.3, 24.4, 24.8, 33.4**
    - Module `tests/test_services/test_merge_family_integrity.py`; function named `test_property_34_relatives_stay_distinct`; required, never skipped
    - Include the two-Brita example (seven distinct children) and the same-named siblings example

  - [x] 11.14 Write property test for plan equals synchronised result (Mandatory group b: family relationship integrity)
    - **Property 35: Plan equals synchronised result**
    - **Validates: Requirements 23.12, 23.13, 26.2**
    - Module `tests/test_services/test_merge_family_integrity.py`; function named `test_property_35_plan_equals_synchronised_result`; required, never skipped

  - [x] 11.15 Write property test for candidate redirect (required by Requirement 32.7)
    - **Property 37: Candidate redirect**
    - **Validates: Requirements 29.1, 29.2, 29.3, 29.4, 29.5, 29.8, 29.9, 29.12**
    - Module `tests/test_services/test_merge_candidate_redirect.py`; required, no skip, xfail or deselect; not part of the six Mandatory_Test_Groups

  - [x] 11.16 Write property test for candidate collision (required by Requirement 32.7)
    - **Property 38: Candidate collision**
    - **Validates: Requirements 29.6, 29.7, 29.10, 29.13, 29.14, 29.15**
    - Module `tests/test_services/test_merge_candidate_redirect.py`; required, no skip, xfail or deselect
    - Include the parametrized 16-combination assessment table, the four `enabled` combinations and the five `research_case_id` combinations

  - [x] 11.17 Implement the Saved_State_Precondition flow in the wizard (R2)
    - In `merge_review_wizard.py`, when "Slå samman personer" is pressed run, before anything else: (1) ask the `EditorRegistry`; if any editor holds unsaved changes show the blocking message "Redigeraren <titel> har osparade ändringar. Spara eller kasta ändringarna i redigeraren och försök igen." with a "Gå till redigeraren" button per editor calling `request_resolution()`, re-check after each resolution, offer no "Spara och fortsätt" and no second confirmation, and never save or discard editor content; (2) only when no editor is unsaved, if the dirty flag is true show a choice with exactly "Spara och fortsätt" and "Avbryt"
    - "Spara och fortsätt" calls `ProjectService.save_project`; on success continue without rebuilding the plan when `plan.content_revision == service.content_revision` and the fingerprint is unchanged; on failure show "Projektet kunde inte sparas. Ingenting har slagits samman.", keep the wizard open, start no merge and leave data and translation files unchanged; "Avbryt" returns to the preview without saving and with all decisions intact
    - Remove any wording or code path that saves unsaved edits together with the merge
    - _Requirements: 26.6, 26.9, 26.11, 26.12, 26.13, 26.14_

  - [x] 11.18 Add the GEDCOM update warning constant and the preview warning (R7)
    - Create `slaktbusken/gedcom/capabilities.py` with `NON_DESTRUCTIVE_UPDATE_AVAILABLE = False`
    - In `merge_preview.py` show the single Swedish warning constant "En senare GEDCOM-uppdatering kan skriva över namn, anteckningar, titel och yrke för den behållna personen. Granska en sådan import noggrant." above the buttons (before the second confirmation) while the constant is `False`, once, not repeated in other sections; hidden when `True`
    - _Requirements: 26.15, 30.13, 30.15, 33.10_

  - [x] 11.19 Write test for the GEDCOM update warning
    - Module `tests/test_gedcom/test_update_warning.py`
    - Warning visible in the preview before the second confirmation while the constant is `False`; absent when `True`
    - _Requirements: 26.15, 30.13, 30.15_

  - [x] 11.20 Write example tests for family relationship integrity (Mandatory group b: family relationship integrity)
    - Module `tests/test_services/test_merge_family_integrity.py` (mandatory marker); required, never skipped
    - Named tests: `test_cycle_blocks_merge`, `test_self_partner_blocks_merge`, `test_self_parent_child_link_blocks_merge`, `test_parent_child_link_types_preserved`, `test_foster_adoptive_families_resynchronised`, `test_two_brita_seven_distinct_children`, `test_same_name_siblings_stay_distinct`, `test_duplicate_families_stay_separate_with_warning`
    - _Requirements: 23.6, 23.7, 23.9, 23.10, 23.12, 24.1, 24.4, 24.8, 35.1_

  - [x] 11.21 Write Similar_Event_Rule example and edge-case tests (Req 21.14, 21.15)
    - Module `tests/test_services/test_similar_events.py` (run after 11.8); required, no skip, xfail or deselect
    - The five examples of Requirement 21.14 as parametrised cases: two Births with no date or different years (no warning); two Births with equal full dates and the same or no place (warning); equal full dates in different places (no warning); two Marriages 10 years apart in the same place (no warning); two Marriages 100 days apart with no place (warning)
    - Precision cases: year-only 1850 against full 1850-03-12 (warning), month 1850-03 against 1850-03-12 (warning), 1850 against 1851-03-12 (no warning), full dates exactly 365 days apart (warning) and 366 days apart (no warning), year-only pair a year apart (no warning, the 365-day branch needs two full dates), `precision="approximate"` with a full ISO value (compared by the ISO value), malformed date (no warning)
    - Edge cases: type-only, place-only and type+place without compatible dates (no warning); an undated event on either side (no warning); two similar events that both belong to Person 1 (no warning); an event shared by both persons (skipped); custom types with different `custom_type_name` (no warning)
    - Every case also asserts, through the planner of 11.2, that both events are present with unchanged ids and that the warning is non-blocking
    - _Requirements: 21.14, 21.15_

- [~] 12. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 13. Phase 7: Atomic merge engine and checksum-based recovery
  - [x] 13.1 Implement `CommitFs` abstraction and pre-flight checks
    - Create `services/commit/fs_ops.py` (`CommitFs` protocol, `RealFs` with fsync, Windows replace with retry) and `services/commit/preflight.py` (locked file, read-only file, disk space, existing lock file) returning the Swedish messages naming the file; a refusal changes nothing
    - _Requirements: 27.14, 27.20_

  - [x] 13.2 Implement Merge_Journal and backup manifest
    - Create `services/commit/journal.py`: journal with txid, targets, temp files, `existed_before`, `old_sha256`, `new_sha256` and its own `journal_sha256`; manifest of the Recovery_Point with its own checksum; VALID, DAMAGED and ABSENT journal and VALID, UNUSABLE and ABSENT manifest detection; a leftover `journal.tmp` does not count as a journal
    - _Requirements: 27.14, 27.15, 27.25, 7.12_

  - [x] 13.3 Implement `MergeTransaction.commit`
    - Create `services/commit/transaction.py` following design section 13.2: pre-flight, lock, backup directory taken from the saved files, temp files written and fsynced, journal written, replace `persons.json` first and the project file last (the logical commit point), cleanup steps that never affect data; works with and without `persons.json`; on error runs the same recovery decision as a crash at that point
    - Catch only `Exception`, at the protocol runner and the cleanup steps; no `finally` that removes artifacts
    - The Recovery_Point copies `translation/persons.json` when present and completes without it otherwise (Req 7.9, 7.10, shared helper of 3.5); this is one of the only two backups to which those criteria apply, and no general-purpose backup feature is added
    - _Requirements: 7.9, 7.10, 7.12, 27.14, 27.15, 27.16, 27.17, 27.18_

  - [x] 13.4 Implement checksum-based startup recovery with Recovery_Refusal (R3)
    - Create `services/commit/recovery.py` with `recover_if_needed` and the deterministic algorithm of design sections 13.7 and 13.8, deciding only by SHA-256 content checksums: a target equal to the expected NEW checksum is already replaced, equal to OLD (or absent where it did not exist) is not yet replaced, anything else is OTHER
    - Roll forward when every target is NEW, or OLD with a temp file equal to the NEW checksum (order T then P); otherwise roll back from a verified backup (order P then T); completed when all targets are NEW; encode decision tables A (two targets), B (all combinations of target, temp and backup state), C (every crash point) and D (refusal rows R1 to R10) as data used by the classifier
    - Refuse (`RecoveryRefusedError` carrying `RecoveryRefusal(code, project_path, journal_path, temp_paths, backup_dir, target_states)`) when a target matches neither state, when the journal is damaged and the manifest unusable, when the backup needed for a roll back is missing or corrupt, or when the journal is absent and the targets are in mixed states; the refusal path is read-only: it writes, renames, deletes and touches nothing, does not call `FilePersistence.load` and opens no project
    - Idempotent; the in-process decision after an error equals the decision after a crash at the same point; cleanup order restore temps, backup directory, lock, `journal.tmp`, journal last; Swedish outcome messages "Sammanslagningen slutfördes." / "Sammanslagningen återställdes."; the Swedish refusal message names the project file, journal, every temp file and the backup folder, states that they are preserved and gives the next step
    - _Requirements: 7.13, 27.16, 27.17, 27.18, 27.21, 27.25_

  - [x] 13.5 Implement `MergeEngine`
    - Create `services/merge_engine.py`: refuse on inventory locations without handler, revalidate `content_revision` and the plan fingerprint, build working data, move `PersonMapping` entries of the retired person into `identity_aliases` and repoint earlier aliases to the final survivor, add the `MergeHistoryEntry` with archived candidates, raise `id_high_water_marks["person_"]` to the retired suffix, post-merge validation with the information ledger, encode project and `persons.json` bytes, commit through `MergeTransaction`
    - The Recovery_Point is taken from the saved state; the commit contains no unsaved pre-merge edit
    - After a successful commit call the adopt step of 5.16: dirty flag false, `revision` plus one, `content_revision` plus one, listeners notified exactly once
    - Any failure before or during commit leaves in-memory data, history, dirty flag and `revision` unchanged; a Recovery_Refusal is reported and touches nothing
    - _Requirements: 1.4, 1.6, 26.9, 27.1, 27.2, 27.3, 27.4, 27.5, 27.8, 27.9, 27.10, 27.15, 27.24, 28.1, 28.2, 28.3, 28.12, 29.11, 30.1, 30.10_

  - [x] 13.6 Integrate commit and recovery into `ProjectService`
    - Run `recover_if_needed` before `FilePersistence.load` on `open_project`; on `RecoveryRefusedError` keep the previous project state, open nothing and re-raise; return the `RecoveryOutcome` message otherwise; refuse an ordinary save while a journal exists (also after a refusal) with "En sammanslagning är inte avslutad. Starta om Släktbusken."; expose the engine hooks and the adopt step
    - _Requirements: 7.12, 7.13, 27.16, 27.17, 27.25_

  - [x] 13.7 Wire commit execution and recovery messages into the UI
    - Run the disk phase on a worker with a progress overlay and no cancel button; adopt data on the UI thread; refresh views; show success, failure and recovery outcome messages from the design table; show the Recovery_Refusal message in a modal `QMessageBox` with a selectable text area (paths copyable) when opening a project is refused and write details to the application log outside the project directory; open the Merge_History view for a person
    - _Requirements: 27.6, 27.7, 27.11, 27.12, 27.13, 27.25, 28.9, 28.10_

  - [x] 13.8 Write property test for no stale references (Mandatory group a: reference preservation)
    - **Property 29: No stale reference to the retired person**
    - **Validates: Requirements 1.4, 22.2, 22.6, 22.13, 22.14, 27.4, 28.2, 29.12, 30.12**
    - Module `tests/test_services/test_merge_reference_rules.py` (mandatory marker); function named `test_property_29_no_stale_reference`; required, never skipped

  - [x] 13.9 Write property test for information preservation (Mandatory group a: reference preservation)
    - **Property 31: Information is never lost**
    - **Validates: Requirements 21.11, 21.15, 21.16, 22.1, 22.7, 22.10, 23.8, 32.6**
    - Module `tests/test_services/test_merge_reference_rules.py` (mandatory marker); function named `test_property_31_information_never_lost`; required, never skipped

  - [x] 13.10 Write property test for order independence (required by Requirement 32.6)
    - **Property 36: Confluence and order independence**
    - **Validates: Requirements 25.1, 25.2, 25.3, 25.4**
    - Module `tests/test_services/test_merge_order.py`; required, no skip, xfail or deselect; not part of the six Mandatory_Test_Groups

  - [x] 13.11 Write failed-merge tests (Mandatory group c: failed merges)
    - **Property 39: A failing merge leaves everything unchanged in memory**
    - **Validates: Requirements 22.12, 27.3, 27.5, 27.8, 28.12, 29.11**
    - Module `tests/test_services/test_merge_failures.py` with `pytestmark = pytest.mark.mandatory_integrity`; required, never skipped
    - `test_property_39_failing_merge_leaves_everything_unchanged`; `test_failed_merge_leaves_data_unchanged` parametrised over plan invalid, post-merge validation failure, research rewire error, encode error and write error; `test_failed_merge_leaves_translation_files_unchanged`; `test_failed_merge_leaves_dirty_flag_unchanged` (also `revision` unchanged, no history entry added)

  - [x] 13.12 Write identity-alias tests (Mandatory group f: GEDCOM re-import after a merge)
    - **Property 42: Identity aliases**
    - **Validates: Requirements 30.1, 30.2, 30.3, 30.10**
    - Module `tests/test_gedcom/test_merge_reimport.py` with `pytestmark = pytest.mark.mandatory_integrity`; function named `test_property_42_identity_aliases`; covers read-then-write equality of `persons.json`, a file without aliases, a merge moving every mapping into an alias with unchanged `gedcom_id` and `fingerprint`, and merging an earlier survivor into a third person; required, never skipped

  - [x] 13.13 Write fault-injection property test for crash atomicity (Mandatory group d: crash recovery)
    - **Property 40: Crash atomicity of the Merge_Transaction**
    - **Validates: Requirements 7.12, 27.16, 27.17, 27.18, 27.19, 30.9**
    - Module `tests/test_services/test_commit_faults.py` with `pytestmark = pytest.mark.mandatory_integrity`; required, never skipped, not marked `slow`
    - `test_crash_matrix_every_operation` (exhaustive over operation numbers discovered by a dry run; kinds crash before or after, I/O error before or after, partial write, persistent permission error and power loss; with and without `persons.json`; including the points between the `persons.json` replace and the project replace, table C rows 11, 11b, 11c, 12b, 12c); every operation number maps to a row of table C and the observed decision equals that row's decision; asserts all-or-nothing by checksum, outcome message exactly when a journal existed, no leftover journal, temp file, backup directory or lock, no orphaned mapping or alias, project loads and re-import does not resurrect the retired person, dirty flag and revision as expected
    - Also `test_property_40_crash_atomicity`

  - [x] 13.14 Write property test for deterministic and idempotent recovery (Mandatory group d: crash recovery)
    - **Property 41: Recovery is deterministic and idempotent**
    - **Validates: Requirements 27.16, 27.17, 27.21**
    - Module `tests/test_services/test_commit_faults.py` (mandatory marker); required, never skipped
    - `test_recovery_idempotent`, `test_crash_during_recovery_converges` (second fault dimension: a crash injected into recovery itself), `test_property_41_recovery_deterministic`

  - [x] 13.15 Write subprocess crash tests (Mandatory group d: crash recovery)
    - Module `tests/test_services/test_commit_subprocess.py` with `pytestmark = pytest.mark.mandatory_integrity`; required, never skipped, not marked `slow` (runs by default)
    - `test_os_exit_at_representative_points`: real `os._exit(42)` at representative operation numbers, asserting the same all-or-nothing checks as the crash matrix
    - _Requirements: 27.19, 35.1_

  - [x] 13.16 Implement the fault-injection filesystem wrappers
    - Create `tests/helpers/fault_fs.py` with `CountingFs`, `FaultFs` (crash before or after, I/O error, partial write, persistent permission error) and `PowerLossFs` implementing the `CommitFs` protocol, plus an in-memory `CommitFs` for table-driven classifier tests; a restart is simulated by constructing a new `ProjectService` and calling `open_project`
    - _Requirements: 27.19_

  - [x] 13.17 Write one test per Reference_Rule row (Mandatory group a: reference preservation)
    - Module `tests/test_services/test_merge_reference_rules.py` (mandatory marker); required, never skipped
    - `test_every_inventory_row_has_a_rule_test` (fails when an inventory row has no rule test), `test_rewire_rows_leave_no_retired_reference`, and one example test per Reference_Rule row of the inventory
    - _Requirements: 1.3, 1.4, 1.8, 35.1_

  - [x] 13.18 Write the handler check test (Mandatory group a: reference preservation)
    - Module `tests/test_services/test_person_reference_index.py` (mandatory marker, run after 1.3); required, never skipped
    - `test_merge_refused_when_handler_missing`: a temporary inventory row without a handler makes `execute` return an error naming the location and leaves project data, files and dirty flag equal
    - _Requirements: 1.6, 35.1_

  - [x] 13.19 Write retired-ID preservation tests (Mandatory group e: retired-ID preservation)
    - **Property 3: Ids of candidates, comments, history entries and retired persons are never reissued** (retired-person part)
    - **Validates: Requirements 2.3, 7.5, 7.6, 28.3, 34.9**
    - Module `tests/test_services/test_retired_ids.py` with `pytestmark = pytest.mark.mandatory_integrity`; required, never skipped
    - `test_retired_id_never_reissued`, `test_retired_id_with_highest_suffix_not_reissued`, `test_retired_id_not_reissued_after_save_and_reopen`, `test_importer_seeded_with_retired_ids`, `test_property_3_retired_ids`; merges are performed with the real engine

  - [x] 13.20 Write the Recovery_Refusal matrix (Mandatory group d: crash recovery)
    - **Property 49: Recovery is refused, never guessed**
    - **Validates: Requirements 7.13, 27.16, 27.19, 27.25**
    - Module `tests/test_services/test_commit_recovery_refusal.py` with `pytestmark = pytest.mark.mandatory_integrity`; required, never skipped
    - Create `tests/helpers/make_interrupted_state.py` to build one real on-disk interrupted state per refusal row R1 to R9 of table D
    - Named tests: `test_refusal_project_file_matches_neither`, `test_refusal_persons_json_matches_neither`, `test_refusal_one_new_other_neither`, `test_refusal_corrupt_journal`, `test_refusal_backup_missing_or_corrupt`, `test_refusal_preserves_every_artifact_byte_for_byte`, `test_property_49_recovery_refused_never_guessed`
    - Each refusal asserts: directory snapshot (path, size, SHA-256, modification time) identical before and after; `RecoveryRefusedError` with the expected code; project not opened and `FilePersistence.load` not called; the Swedish message contains every path and the preservation statements; a second open gives the same refusal; a manual restore of the backup plus renaming the journal lets the project open
    - A table-driven test feeds every row of tables A and B to the classifier through the in-memory `CommitFs` and asserts the decision per named row

  - [x] 13.21 Write pre-flight tests
    - Module `tests/test_services/test_commit_preflight.py` (not one of the six Mandatory_Test_Groups; required for completion)
    - The only platform-conditional tests are those that need Windows file-sharing semantics (a file opened by a second handle without write sharing); they carry `@pytest.mark.windows_only` and `@pytest.mark.skipif(sys.platform != "win32", reason="Kräver Windows")` with exactly that condition and no other skip reason. They MUST run (not skip) on the Windows development machine; the conftest hook of 1.7 turns a skip of a `windows_only` test on `win32` into a failure, and the guard test (17.6) and runner (17.5) check this. Every other test in the module is unconditional
    - Read-only target, second handle without write sharing (Windows only, as above), directory without create permission via `FaultFs`, insufficient space via a `disk_usage` stub; each asserts a message naming the file, no change in memory or on disk, and an open wizard
    - _Requirements: 27.20_

  - [x] 13.22 Write the Saved_State_Precondition tests (Mandatory group c: failed merges)
    - **Property 47: A merge executes only from a saved state**
    - **Validates: Requirements 26.6, 26.11, 26.14, 27.22, 27.23, 27.24**
    - Module `tests/test_services/test_saved_state.py` (mandatory marker); required, never skipped; uses a counting `FakeEditor` and the real `MergeEngine` on a project saved to a temporary directory
    - `test_dirty_project_refused` (exact message "Projektet har osparade ändringar. Spara projektet innan sammanslagningen."), a `content_revision` differing from `clean_content_revision` is refused, `test_unsaved_editor_refused` (one or several editors, message naming them), `test_property_47_merge_only_from_saved_state`; for each refusal the directory snapshot, `ProjectData`, dirty flag, `revision` and the editors' unsaved state are unchanged and no editor method other than `has_unsaved_changes` was called (no save, discard or `request_resolution`); a successful merge commits the serialisation of the plan applied to the saved state

  - [x] 13.23 Write the commit-bookkeeping and wizard-flow tests (Mandatory group c: failed merges)
    - **Property 48: Commit bookkeeping and plan staleness**
    - **Validates: Requirements 26.9, 26.12, 27.1, 27.8, 27.24**
    - Module `tests/test_services/test_saved_state.py` (mandatory marker, run after 13.22); required, never skipped
    - After a successful merge: dirty false, `revision` and `content_revision` each plus one, exactly one listener call, `is_saved_state()` true; after a failed merge (also a rolled-back one) dirty flag, `revision` and notifications unchanged; a plain save leaves `content_revision` and the fingerprint unchanged so the plan is not rebuilt (counting planner); a content change between plan and execution reports the plan as stale and rebuilds it
    - Wizard flow (pytest-qt): an unsaved editor shows the block message and neither "Spara och fortsätt" nor the second confirmation, and `request_resolution` is called only when the button is pressed; a dirty project offers exactly two buttons; "Avbryt" saves nothing; "Spara och fortsätt" with a failing save (a `FaultFs` on the save path) starts no merge and leaves files unchanged; the second confirmation text contains no sentence about saving unsaved edits
    - Function named `test_property_48_commit_bookkeeping`

  - [x] 13.24 Add the Saved_State_Precondition re-check as step 0 of `MergeEngine.execute` (R2)
    - In `services/merge_engine.py` run `Preconditions.check` first, before pre-flight, with the live registry: `service.is_saved_state()` else refuse with "Projektet har osparade ändringar. Spara projektet innan sammanslagningen."; `registry.unsaved_editors()` empty else refuse with the Requirement 26.14 message naming the editors
    - A refusal changes nothing in memory or on disk, leaves the dirty flag and `revision` unchanged, and calls no save, commit, discard or resolution method of anything
    - _Requirements: 26.14, 27.22, 27.23_

- [~] 14. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 15. Phase 8: GEDCOM and consistency integration
  - [x] 15.1 Add alias resolution and the retired-id guard to the importer
    - In `GEDCOMImporter._process_persons`, resolve aliases before `classify_persons` by xref and fingerprint; never create a person with a retired id (including in `_update_person`); list matched merged-identity records with differing fields while leaving the survivor unchanged; flag a record resolving to more than one active person without assigning it; add `merged_identity_matches` and `ambiguous_records` to the import result; drop a second partner that resolves to the same person with the warning "Båda partnerna i familjen <xref> pekar på samma person."
    - Do not change the existing overwrite of names, notes, title and occupation by an update import (temporary limitation, warned in 11.18; the fix is TRK-1, see 17.7)
    - _Requirements: 30.4, 30.5, 30.6, 30.7, 30.8, 30.13_

  - [x] 15.2 Add export omission counts
    - Report `Sammanslagningskandidater` and `Sammanslagningshistorik` counts in `GEDCOMExporter._collect_omissions` when non-zero; ensure the retired person is not exported
    - _Requirements: 30.12_

  - [x] 15.3 Implement the Merge_Consistency_Report
    - Create `reports/merge_consistency.py` (`MergeIssue`, `check_merge_consistency`, `generate_merge_consistency_report`) following `research_consistency.py`; add "Sammanslagning och dubletter" to `ReportMenuBuilder` after "Forskningskonsistens" and wire `MainWindow` and `ReportService`; read-only; Swedish placeholder for missing persons; "Rapporten kunde inte skapas." with no partial report on error
    - _Requirements: 5.8, 6.7, 31.1, 31.2, 31.3, 31.4, 31.5, 31.6, 31.7, 31.8, 31.9_

  - [x] 15.4 Write property test and regression tests for re-import (Mandatory group f: GEDCOM re-import after a merge)
    - **Property 43: Re-import after a merge**
    - **Validates: Requirements 30.4, 30.5, 30.6, 30.7, 30.8**
    - Module `tests/test_gedcom/test_merge_reimport.py` (mandatory marker, run after 13.12); required, never skipped
    - Named tests: `test_reimport_identical_file_does_not_recreate_retired_person`, `test_reimport_edited_variant_matches_by_fingerprint`, `test_reimport_counts_unchanged`, `test_both_partners_same_person_gives_warning`, `test_negative_without_alias_recreates_person`, `test_property_43_reimport_after_merge`
    - Include the seven regression steps in the design (identical re-import, edited variant with renumbered xrefs, husband-and-wife variant, negative test without alias)
    - _Requirements: 30.4, 30.5, 30.6, 30.7, 30.8, 30.11, 35.1_

  - [~] 15.5 Write property test for consistency report findings
    - **Property 44: Consistency report findings**
    - **Validates: Requirements 5.8, 6.7, 31.2, 31.3, 31.4, 31.5**
    - Module `tests/test_reports/test_merge_consistency.py`

  - [x] 15.6 Write export test
    - Module `tests/test_gedcom/test_merge_export.py`
    - Export contains every active person and not the Merged_Away_Person
    - _Requirements: 30.12_

- [~] 16. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 17. Phase 9: Regression, performance and mandatory-test enforcement
  - [x] 17.1 Implement the deterministic synthetic benchmark generator
    - Create `tests/benchmarks/synthetic_project.py`: seeded generator for 20,000 persons and 2,000 candidates with generations, multiple partnerships, shared ancestors, all four parentage types and the stated candidate mix; identical output for the same seed
    - _Requirements: 32.9_

  - [x] 17.2 Write property test for benchmark determinism
    - **Property 46: Benchmark data is deterministic**
    - **Validates: Requirements 32.9**
    - Module `tests/properties/test_property_46_benchmark_determinism.py`

  - [~] 17.3 Write performance benchmarks with documented environment
    - Create `tests/benchmarks/test_merge_performance.py` (`@pytest.mark.slow`, offscreen Qt): candidate index below 1 s and comparison family views below 2 s at 20,000 persons and 2,000 candidates; 3 warm-up runs and 30, 10 and 5 measured runs; gate on the maximum; record median and p95; record the design targets (index under 50 ms, comparison refresh under 600 ms, list indicators under 20 ms extra) without gating them; plan build time with a 10 s regression guard
    - Write `ENVIRONMENT.md` and `benchmark-results.json` per run (CPU, RAM, OS, Python and PySide6 versions, power plan, run counts, statistic used); a failing gate prints the measured duration and the limit and does not modify the project
    - _Requirements: 32.3, 32.4, 32.8, 32.10, 32.11_

  - [~] 17.4 Run and extend the regression and convention tests
    - Re-run the existing suite unmodified, including research indicator settings, person list enhancements, family, ancestry and descendants view tests, GEDCOM tests and foster sync tests; compare serialisations only through `assert_equal_except_version_fields`
    - Add the subprocess import test that loads each new service and commit module with `PySide6` blocked, and static tests for the scope limits (no scoring, proposing or automatic assessment functions)
    - _Requirements: 32.1, 32.2, 33.1, 33.2, 33.3, 33.4, 33.9, 34.5, 34.6_

  - [x] 17.5 Implement `scripts/run_mandatory_tests.py` and document the mandatory command
    - Create `scripts/run_mandatory_tests.py`: set `QT_QPA_PLATFORM=offscreen` and `SBK_MANDATORY_STRICT=1`; run `python -m pytest tests/test_meta <all module paths from MANDATORY_GROUPS> --strict-markers -p no:randomly --junitxml=<tmp>`; read the JUnit XML and per group check that at least as many tests ran as there are required names, that all passed and that none was skipped, xfail-ed or deselected; print one Swedish line per group ("Obligatoriska testgrupper: ...") and exit non-zero for any failure, empty group or missing required test
    - On `win32` the runner also runs `tests/test_services/test_commit_preflight.py` and fails when any `windows_only` test in it was skipped (on other platforms those tests may skip)
    - Create `tests/MANDATORY_TESTS.md`, add the command to the testing section of `README.md`, and add a CI workflow step under `.github/workflows` that runs the script in addition to the full suite (`python -m pytest`)
    - _Requirements: 35.3, 35.4, 35.5_

  - [~] 17.6 Write the mandatory-groups guard test
    - Create `tests/test_meta/test_mandatory_groups_guard.py` (itself mandatory; the only module outside the six groups that the runner includes), static and fast: parse every module of `MANDATORY_GROUPS` plus `test_merge_persistence.py`, `test_merge_candidate_service.py` and `test_merge_order.py` with `ast` and fail on `pytest.mark.skip`, `skipif`, `xfail`, `slow`, `optional`, `pytest.skip`, `pytest.xfail`, `pytest.importorskip`, `unittest.skip`, `skipIf`, `skipUnless` (also inside `parametrize(..., marks=...)`) and on a missing `pytestmark`; fail when a `required_tests` name is not defined in its module; fail on `@settings(max_examples=N)` with `N < 100` or `derandomize=True` in a mandatory module and when a mandatory property number has no test tagged `# Feature: person-comparison-and-merge, Property N:`
    - Scan `pytest.ini`, `pyproject.toml`, `setup.cfg`, `tox.ini` and every `conftest.py` for `addopts` with `-m`, `-k`, `--deselect` or `--ignore`, for `collect_ignore` / `collect_ignore_glob` naming a mandatory module, and for a missing `mandatory_integrity` marker registration; run `python -m pytest --collect-only -q -p no:cacheprovider` in a subprocess and require every required test in the output; check that a CI workflow calls `scripts/run_mandatory_tests.py` when `.github/workflows` exists
    - Windows-only preflight tests: `test_windows_only_skipif_condition` parses `test_commit_preflight.py` with `ast` and requires that every `skipif` in it uses exactly the condition `sys.platform != "win32"` and sits on a test marked `windows_only`; `test_windows_only_tests_run_on_windows` (effective only when `sys.platform == "win32"`, otherwise it asserts the static part only) collects the module in a subprocess and fails when a `windows_only` test is reported skipped
    - `test_environment_available` imports `PySide6.QtWidgets`, `pytest-qt`, `hypothesis` and `slaktbusken.gedcom.importer`, creates a `QApplication` on the offscreen platform and asserts instead of skipping
    - Prove the detection with fixtures: a temporary module containing each forbidden construct, a module with a lowered `max_examples`, a registry entry naming a missing test must each be reported, and a clean module must pass; also test the conftest hooks with a temporary project (a skipped mandatory test becomes a failure, an xpass becomes a failure, a deselected required test aborts the strict run)
    - _Requirements: 35.1, 35.2, 35.3, 35.5, 35.6_

  - [x] 17.7 Record TRK-1 in the release checklist (documentation entry only; OUT OF SCOPE follow-up, not implemented by this feature)
    - Add an entry to `docs/release-checklist.md` (create the file if it does not exist): "TRK-1 Non-destructive GEDCOM update handling: an update import must not silently overwrite user-edited or merged data of an active person and every difference is presented for review before any change is applied; needed before Släktbusken 1.0 (release blocker); separate spec; acceptance: an update import leaves every field of every active person unchanged until the user accepts a difference, and the wizard warning of 11.18 is removed by flipping `NON_DESTRUCTIVE_UPDATE_AVAILABLE` in the same change"
    - This task only records the item. Implementing TRK-1 (baseline snapshots, three-way comparison, review dialog) is NOT part of this feature and has no task here
    - _Requirements: 30.14, 33.10_

- [~] 18. Checkpoint - Mandatory run with zero skipped
  - Run `python scripts/run_mandatory_tests.py` and require exit code 0, every one of the six Mandatory_Test_Groups non-empty with all required tests present and passed, and zero skipped, xfail-ed, deselected or missing tests; on Windows also require that no `windows_only` preflight test was skipped; ask the user if questions arise.

- [~] 19. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
  - The feature counts as complete only when `python scripts/run_mandatory_tests.py` exits with 0 with zero skipped mandatory tests AND the full suite (`python -m pytest`) passes (Requirements 35.3, 35.4).

## Notes

- There are no optional tasks: every task, including every test task, is required for the feature to count as complete; no task carries an optional marker
- The six Mandatory_Test_Groups of Requirement 35 are the enforcement set of the no-skip hook (1.7), the runner (17.5) and the guard test (17.6): a reference preservation, Properties 25, 29, 30, 31; b family relationship integrity, 32 to 35; c failed merges, 39, 47 and 48; d crash recovery, 40, 41, 49; e retired-ID preservation, 3; f GEDCOM re-import, 42, 43. Their tests are never skipped, xfail-ed, deselected, marked `slow` or conditionally skipped; mandatory modules set `pytestmark = pytest.mark.mandatory_integrity` and are executed by `python scripts/run_mandatory_tests.py`
- All other tests are also required (Properties 1, 2, 4 to 24, 26 to 28, 36 to 38, 44 to 46, 50, 51, the widget tests, benchmarks and examples), including the tests that Requirement 32.6 and 32.7 demand (Properties 1, 6, 36, 37, 38 and the same-ID and same-name examples), but they are not subject to the mandatory no-skip hook, except that `windows_only` tests must not be skipped on Windows (13.21, 1.7, 17.5, 17.6). Benchmarks carry the `slow` marker only for selection and still have to pass in the full run
- The platform-conditional preflight tests in `test_commit_preflight.py` stay conditional on `sys.platform != "win32"`; on the Windows development machine they must run, and a skip there is reported as a failure
- Test modules of the six groups use the exact module paths and test names of the design registry (created in 1.7), so that the runner and the guard test (17.6) find them; several tasks that write the same mandatory module are placed in different waves
- Property tests that the design does not map to a Mandatory_Test_Group (Properties 2, 4, 5, 7 to 24, 26, 27, 28, 44, 45, 46, 50, 51) are required and not subject to the no-skip hook; their modules are one file per property under `tests/properties/` (or the module named in the task) so that tasks in the same wave never write the same file
- Backup scope (design finding 10): the `persons.json` backup rules of Req 7.9 and 7.10 apply only to `MigrationManager.create_backup` and the merge Recovery_Point; no task implements a general-purpose backup feature
- The Person_List multi-selection (7.18 to 7.20, Req 8.12 to 8.16) and the Similar_Event_Rule (1.2, 11.2, 11.8, 11.21, Req 21.14, 21.15) are covered by `tests/test_ui/test_person_list_selection.py` and `tests/test_services/test_similar_events.py`
- Each task references specific requirements for traceability; each property test task references its design property number
- Property tests use Hypothesis with at least 100 examples and carry the tag `# Feature: person-comparison-and-merge, Property N: <title>`
- Fault-injection loops are exhaustive over operation numbers, not sampled
- TRK-1 (non-destructive GEDCOM update handling, needed before Släktbusken 1.0) is OUT OF SCOPE for the implementation tasks of this feature; it is only recorded by task 17.7 and shown to users through the wizard warning of 11.18
- Checkpoints ensure incremental validation; checkpoint 18 runs the mandatory command with zero skips; checkpoint 19 requires the full suite, including every non-mandatory test, to pass
- This workflow only creates planning artifacts; no production code is written by it

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.7", "3.1", "3.13", "5.18", "9.10"] },
    { "id": 1, "tasks": ["1.2", "1.3", "3.2", "3.3", "3.5", "3.7", "3.11", "5.4", "5.6", "7.1", "9.11", "13.1", "17.5", "17.7"] },
    { "id": 2, "tasks": ["1.4", "1.5", "1.6", "3.4", "3.6", "3.8", "3.9", "3.10", "3.12", "3.14", "3.15", "5.5", "5.7", "5.16", "7.2", "9.1", "9.2", "9.12", "9.14", "13.2", "13.16"] },
    { "id": 3, "tasks": ["5.1", "5.17", "7.3", "9.7", "9.8", "11.1", "13.3", "17.1"] },
    { "id": 4, "tasks": ["5.2", "5.3", "5.8", "5.12", "5.13", "7.4", "7.9", "7.10", "7.11", "7.12", "7.13", "7.14", "7.15", "7.17", "9.3", "11.2", "13.4", "17.2"] },
    { "id": 5, "tasks": ["5.9", "5.10", "5.14", "7.5", "9.4", "11.3"] },
    { "id": 6, "tasks": ["5.11", "5.15", "5.19", "7.6", "9.5", "9.13", "11.4", "11.6", "11.7", "11.8"] },
    { "id": 7, "tasks": ["5.20", "7.7", "9.6", "9.9", "11.5", "11.11", "11.21"] },
    { "id": 8, "tasks": ["7.8", "7.18", "9.15", "11.9", "11.12", "11.15", "13.5"] },
    { "id": 9, "tasks": ["7.16", "7.19", "11.13", "11.16", "11.17", "11.18", "13.6", "13.8", "13.10", "13.11", "13.18", "13.19", "13.24", "15.1", "15.2"] },
    { "id": 10, "tasks": ["7.20", "11.10", "11.14", "11.19", "13.7", "13.9", "13.12", "13.13", "13.15", "13.20", "13.21", "13.22", "15.6"] },
    { "id": 11, "tasks": ["11.20", "13.14", "13.17", "13.23", "15.3", "15.4"] },
    { "id": 12, "tasks": ["15.5", "17.3", "17.4", "17.6"] }
  ]
}
```
