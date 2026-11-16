# Implementation Plan: Data Integrity and Loss Prevention (Package 1, release 0.3.0)

## Overview

The plan implements the design in `design.md`. The implementation language is Python 3 (PySide6 for UI), as in the existing code base. Tests use pytest and Hypothesis (profile `sbk`).

Every test sub-task is mandatory. No sub-task is marked optional, because all tests of this spec belong to the mandatory group "Dataskydd" and the confirmed-bug acceptance tests must not be skippable. Test modules live in `tests/test_dataskydd/` and are registered in `tests/mandatory_groups.py` in task 12.1, the only task that edits that file.

All approval items AP1 to AP5 are decided by the user and binding. The tasks implement them as follows:

| Item | Decision | Tasks |
|---|---|---|
| AP1 | Origin on legacy events only on an exact one-to-one content match; project change; count in the Swedish import log | 10.1, 10.2, 10.5, 10.7 |
| AP2 | Staged translation plus write-ahead intent at save, extended by digest verification, conflict refusal, fault-injection tests and external-modification tests | 11.1 to 11.7 |
| AP3 | "Från plats" selector for flytt events, separate citation contexts and prompts | 9.2, 9.4 |
| AP4 (changed) | Residence duplication fixed in this package with `ResidenceFact.origins` | 2.1 to 2.5, 10.1, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 13.1 |
| AP5 | Family events kept on update import; matcher decides | 10.2, 10.7 |

No task implements Package 2. No task commits to git.

## Tasks

- [x] 1. Prepare the test scaffolding and measure the snapshot cost
  - [x] 1.1 Create the Dataskydd test package and inspect the mandatory-group guard
    - Create `tests/test_dataskydd/` with `__init__.py`, `strategies.py` (empty Hypothesis strategy module to be filled by later tasks), `change_path_allowlist.py` and `residence_construction_allowlist.py` (empty allow-list structures with `(module, function, reason)` entries).
    - Give every module in the package `pytestmark = pytest.mark.mandatory_integrity`.
    - Read `tests/test_meta/test_mandatory_groups_guard.py`, `tests/conftest.py` and `scripts/run_mandatory_tests.py`. Record in a comment at the top of `strategies.py` whether `MandatoryGroup.properties` can be an empty tuple and how `required_tests` prefix entries (`test_dp_property_*`) are matched. Do not edit `tests/mandatory_groups.py` in this task.
    - Add `tests/fixtures/project_v0_4.json.gz` generated from a project that has approximate dates, date citations, place citations, flytt events with `from_place`, residences (including residences that earlier update imports duplicated and two residences linked through a flytt event) and GEDCOM-imported events without origin.
    - _Requirements: 22.1, 22.4, 21.7_

  - [x] 1.2 Build the large-project generator, measure the full snapshot and report the figure
    - Create `tests/helpers/large_project.py` with a deterministic `make_project(n_persons)` that yields about 2.5 events per person, 4,000 families, 2,000 places and 800 sources for 10,000 persons.
    - Create `scripts/measure_edit_session.py` that times the full snapshot (a list of `(entity, copy)` pairs for every list field of `ProjectData`, plus `project` and `connection_overrides`) and the in-place restore on that project, and prints both times.
    - Run it and write the figures into the final report of this task and into a comment in `tests/test_dataskydd/test_edit_session_performance.py` (created in 7.3). If the total exceeds 1.5 s, report it to the user; do NOT change the snapshot scope and do not implement a scoped snapshot (Requirements 1.12 and 1.13). The implementation continues with the full snapshot.
    - _Requirements: 1.12, 1.13_

- [x] 2. Extend the data model, serialization and format version
  - [x] 2.1 Extend the model: date qualifiers, event citations, event origin
    - In `slaktbusken/model/event.py` add to `DateValue` the fields `qualifier="exact"`, `value_to=None`, `calendar="gregorian"`, `original_text=None`; add `Event.source_refs` and `Event.origin`.
    - Create `slaktbusken/model/record_origin.py` with the dataclass `RecordOrigin` (`owner_kind`, `owner_id`, `owner_xref`, `tag_key`, `index`, `record_hash`, `uid=None`, `instance=0`), used by `Event.origin` (single optional) and by the new `ResidenceFact.origins` (`list[RecordOrigin]`, default empty) in `slaktbusken/model/residence.py`. Add the function `origin_key(origin)` (owner kind, owner id, tag key, record hash, instance, uid or empty string) to the same module. Equal origins on several residences of one owner are valid data and produce no validation finding.
    - In `slaktbusken/model/validators.py` validate the invariants of the Data Models table in `design.md` (including `instance >= 0`; allowed qualifiers and calendars, empty `value` only for `unparsed`, `value_to` rules, precision rules, the legacy combination `exact` plus `approximate`) and of `RecordOrigin` (owner kind, residence origins are `INDI` and `RESI`, 64-hex hash, non-negative index; next to `validate_residence`, `validators.py:1363`). Julian dates are checked with the calendar-aware check of task 5.1 once it exists; until then only the regex shape is checked. Keep every existing 0.4 value valid.
    - _Requirements: 12.1, 14.1, 14.2, 14.3, 14.4, 14.5, 19.1, 19.2, 22.1, 22.2_

  - [x] 2.2 Serialize and deserialize the new fields, omitting defaults
    - In `slaktbusken/persistence/serialization.py` register `(Event, "source_refs"): SourceRef` in the deep-nested list table (L361), `(Event, "origin"): RecordOrigin` in `_NESTED_OPTIONAL_TYPES` (L349) and `(ResidenceFact, "origins"): RecordOrigin` in `_NESTED_LIST_TYPES` (L314). `_serialize_dataclass` already omits `None` optionals and empty default lists (L185-215), so each new key is written only when it differs from the default; read missing keys as defaults. Confirm that `_deserialize_residences` (L563-600) keeps `origins` and still ignores unknown fields.
    - _Requirements: 12.2, 14.7, 19.1, 22.1_

  - [x] 2.3 Bump the format to 0.5 with the additive migration
    - Set `MigrationManager.CURRENT_VERSION` and `file_io.CURRENT_VERSION` (`file_io.py:20`) to "0.5"; register `_migrate_0_4_to_0_5` (version keys only); change the default `ProjectData.version` (`model/project.py:51`).
    - Search the repository for other literal "0.4" format versions (`create_project`, fixtures) and update them without touching historical migration tests.
    - Confirm that the existing backup procedure runs for 0.4 files and that a too-new file is refused.
    - _Requirements: 21.1, 21.2, 21.3, 21.5, 21.6_

  - [x] 2.4 Register the event and residence origins in the person-reference inventory
    - In `slaktbusken/services/person_reference_index.py` add the inventory rows `event.origin` (owner class `RecordOrigin`, path `owner_id`, rule `H`, no handler, statement "Provenance of an imported event; never rewritten") and `residence.origins` (path `origins[].owner_id`, rule `H`, "Provenance of an imported residence; never rewritten"). No allow-list entry is needed: the completeness check flags only names ending in `person_id` or `person_ids` (F12). Do not add a collector to `PersonReferenceIndex.build` (an `H` row needs none).
    - Add `test_reference_rule_event_origin` and `test_reference_rule_residence_origins` to `tests/test_services/test_merge_reference_rules.py` (the existing `test_every_inventory_row_has_a_rule_test`, L1258, fails without them) following the pattern of the existing `H` row tests; confirm that `test_reference_summary_lists_every_preserve_and_historical_row` (`test_merge_planner_refs.py:182`) passes with the new rows and that `merge_engine._validate_result` ignores rows without a handler.
    - _Requirements: 19.9, 22.26_

  - [x] 2.5 Write model, serialization and migration tests
    - `test_serialization_0_5.py`: **Property 12: Date, event and residence serialization round-trips and omits defaults** (`test_dp_property_12_*`), plus `test_event_source_refs_serialize_only_when_non_empty`, `test_event_source_refs_round_trip`, `test_origin_serialization_round_trip`, `test_origin_instance_round_trip` (including a missing `instance` key read as 0 and equal origins on two residences), `test_residence_origins_serialize_only_when_non_empty`, `test_residence_origins_round_trip`, `test_date_value_defaults_and_validation`, `test_date_value_serialization_omits_defaults`, `test_unparsed_validation`.
    - `test_migration_0_5.py`: **Property 21: Migration to 0.5 is additive and idempotent** (`test_dp_property_21_*`), plus `test_migration_0_4_to_0_5_only_changes_version`, `test_migration_creates_backup`, `test_migration_is_idempotent`, `test_v0_4_fixture_opens_and_round_trips`, `test_v0_4_residences_round_trip_without_origins`, `test_newer_version_refused`, `test_old_precision_approximate_not_rewritten_on_open`.
    - **Validates: Requirements 12.1, 12.2, 14.1, 14.7, 16.5, 19.1, 21.1 to 21.6, 22.1**
    - _Requirements: 12.1, 12.2, 12.7, 14.1, 14.7, 14.11, 16.5, 19.1, 19.14, 21.1, 21.2, 21.3, 21.4, 21.5, 21.6, 21.7, 22.1, 22.33_

- [x] 3. Introduce the shared event-citation helper
  - [x] 3.1 Implement the Citation_Helper
    - Create `slaktbusken/model/event_citations.py` with `CitationContext`, `EventCitation`, `event_citations`, `cited_source_ids`, `event_cites_source`, `context_label_sv` and `identical_reference`, as specified in `design.md`.
    - _Requirements: 6.7, 13.1, 13.2_

  - [x] 3.2 Move every consumer to the helper
    - Replace direct reads in `reports/kallrapport.py`, `reports/ansedel.py`, `services/source_stats.py` (`event_cited_sources`, `compute_usage_stats`), `ui/dialogs/usage_detail_dialog.py` (both places), `ui/editors/source_editor.py` (`_find_referencing_events`, usage list, delete check), `services/validation_service.py` (include the context in messages), `gedcom/exporter.py` (event-level SOUR directly under the event record, plus date and place citations as today), `services/comparison_session.py` and the has-source icon logic of the Person_Editor lists.
    - Make unique-source reports deduplicate by source id while keeping each distinct (context, quality, note, aspects) entry.
    - Locate any other source-deletion cleanup or source-merge rewiring that touches event citations (search for `source_id` rewiring in `services/` and `delete_service.py`) and route it through the helper; confirm that the merge planner count (`_count_instances`) includes `Event.source_refs`.
    - In `gedcom/importer.py` (`_create_event` and `_create_family_event`, which today attach SOUR lines to the date) import event-level SOUR lines as `Event.source_refs` regardless of date presence; stop attaching them to the date.
    - _Requirements: 12.4, 12.5, 13.3, 13.4, 13.5, 13.6, 13.7_

  - [x] 3.3 Write the citation guard test
    - `test_event_citations.py::test_guard_no_direct_source_refs_reads`: an `ast` scan of `slaktbusken/**/*.py` that allows `.source_refs` only in `model/`, `persistence/serialization.py`, `model/event_citations.py` and the research modules named in the design.
    - **Validates: Requirement 13.8**
    - _Requirements: 13.8_

  - [x] 3.4 Write helper and consumer tests
    - **Property 5: The citation helper returns every reference exactly once** (`test_dp_property_5_*`).
    - **Property 6: Consumers agree on cited sources and keep distinct citation contexts** (`test_dp_property_6_*`).
    - Examples: `test_event_citations_returns_all_locations_once`, `test_consumers_agree_on_cited_sources`, `test_source_delete_refused_for_every_context`, `test_unique_source_report_keeps_distinct_contexts`, `test_validation_reports_context`, `test_merge_counts_event_level_refs`, `test_comparison_uses_all_citation_contexts`, `test_importer_event_level_sour_without_date`, `test_exporter_event_level_sour`.
    - **Validates: Requirements 12.4, 12.5, 13.1 to 13.7**
    - _Requirements: 12.4, 12.5, 12.7, 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.9_

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement date semantics, GEDCOM date parsing and export
  - [x] 5.1 Implement Date_Semantics
    - Create `slaktbusken/model/date_semantics.py`: `effective_qualifier` (only `exact` plus `approximate` is `about`), `is_real_date` (Gregorian and Julian leap rules), `validate_date_value` (Swedish messages), `julian_to_gregorian` (via Julian Day Number, for bounds only), `in_swedish_window`, `date_bounds` (open bounds; unknown for `unparsed` and for Julian endpoints in 1700-02 to 1712-02; union of as-written and converted spans for other Julian dates), `format_date_sv`, `is_exact`, `exact_value`, `sort_key`. Build Julian spans without `date_span.expand_iso` (it is Gregorian-only). Do not duplicate or call `is_valid_swedish_calendar`, and model neither the 1700-1712 calendar nor 30 February 1712.
    - Replace the temporary shape-only Julian check of task 2.1 with `is_real_date`.
    - _Requirements: 14.2, 14.3, 14.6, 14.8, 14.9, 14.10, 15.1, 15.2, 15.3, 15.4, 15.6, 15.7, 15.8_

  - [x] 5.2 Replace the GEDCOM date parser and wire it into the importer
    - Create `slaktbusken/gedcom/dates.py` with `parse_gedcom_date`, `format_gedcom_date` and `export_gedcom_date` following the grammar and the input-to-result table in `design.md`: Swedish month names, ISO, dotted, per-endpoint and leading calendar escapes, Julian as written, dual year `YYYY/YY` to unparsed, impossible days and Julian-only days without escape to unparsed, unsupported escapes and mixed calendars to unparsed, INT, parenthesised phrases, reversed ranges.
    - Replace `parse_gedcom_date` at `importer.py:314` (and the second parser at ~L395-440) and its uses in `_create_event` and `_create_family_event` so that a non-empty DATE line always yields a `DateValue` and unparsed dates add the Swedish Import_Log warnings of the design; store `original_text` under the policy of the design.
    - Make `_parse_resi_date` delegate tokenising and validation to the new module while keeping its `Endpoint` result; keep all existing residence tests green.
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 9.11, 9.12, 9.13, 9.14_

  - [x] 5.3 Export dates with qualifiers, ranges, calendar and original text
    - In `gedcom/exporter.py` replace `_format_date` (`exporter.py:1098`, which writes `ABT` for every approximate precision at L1149) and the placement-event period output with `export_gedcom_date`; write `@#DJULIAN@` before each endpoint of a Julian date, verbatim original text when consistent, verbatim text for unparsed dates, and a Swedish warning in the export log for stale original text. `ABT` is written only for effective qualifier `about`. Apply the same rules to ordinary and placement events. Leave the residence endpoint formatter (`_iso_to_gedcom_date`, L471-525) on its own `Endpoint` model.
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8_

  - [x] 5.4 Audit consumers of date values
    - Apply the consumer audit table of `design.md` to every reader of `date.value` that assumes an exact date: `residence_inference.py` (L236-295), `residence_coverage.py:461`, `residence_edit_ops.py:742`, `person_summary.py` (L63-67, L177), `merge_rules.py` (L287-307), `foster_sync.py` (L506-508), `calendar_checks.py:65` and `comparison_session.py:440`. Use `exact_value`, `is_exact`, `sort_key` or `format_date_sv`; tolerate an empty `value` (unparsed) and qualifier dates; a non-exact date must never be treated as exact.
    - Update `services/checks/date_utils.py`: `parse_date_value` returns `None` for unparsed dates and fills `ParsedDate.precision` from the effective qualifier; age and interval functions return `None` unless both dates are exact. Leave `is_valid_swedish_calendar` and `_to_julian_day_number` unchanged.
    - Search once more for any other `precision == "approximate"` reader (the earlier search found only the exporter and `date_utils`) and fix it.
    - _Requirements: 14.6, 14.10, 15.5, 15.7_

  - [x] 5.5 Write date tests
    - `test_date_semantics.py`: **Property 10: A day date is accepted exactly when it is real in its calendar**, **Property 11: Date bounds are consistent, conservative for Julian dates and unknown in the Swedish window**, **Property 22: Qualifier semantics never read a qualified date as exact or `before` as `about`** (`test_dp_property_10_*`, `_11_*`, `_22_*`), plus `test_leap_year_rules_gregorian`, `test_leap_year_rules_julian`, `test_julian_to_gregorian_conversion_round_trip`, `test_legacy_exact_approximate_is_about`, `test_explicit_before_never_about`, `test_date_bounds_per_qualifier`, `test_julian_bounds_conservative`, `test_swedish_window_bounds_unknown`, `test_swedish_date_formatting`, `test_consumers_treat_qualified_dates_as_not_exact`, `test_invalid_day_unparsed_in_import`, `test_date_validity_property`, `test_swedish_calendar_not_modelled_by_date_semantics`.
    - `test_gedcom_dates.py`: **Property 7: GEDCOM date parsing is total and never loses or falsifies a date**, **Property 8: Structured dates round-trip through GEDCOM text**, **Property 9: A stale original text is never exported** (`test_dp_property_7_*`, `_8_*`, `_9_*`), plus `test_import_between_and`, `test_import_from_to`, `test_import_from_only_and_to_only`, `test_import_before_after_about_estimated_calculated`, `test_import_int_phrase`, `test_import_julian_as_written`, `test_import_julian_escape_per_endpoint`, `test_import_julian_swedish_window_kept_as_written`, `test_import_dual_year_becomes_unparsed`, `test_import_swedish_month_names`, `test_import_iso_and_dotted_dates`, `test_import_invalid_dates_become_unparsed`, `test_import_exceptional_swedish_dates_become_unparsed` (30 FEB 1712, 29 FEB 1700 without escape), `test_import_mixed_calendar_range_becomes_unparsed`, `test_import_unknown_phrase_becomes_unparsed_with_warning`, `test_import_residence_dates_use_same_interpretation`, `test_no_date_line_is_ever_dropped`, `test_from_to_never_becomes_exact_year`, `test_export_qualifiers`, `test_export_ranges`, `test_export_julian_escape`, `test_export_original_text_verbatim`, `test_export_unparsed_verbatim`, `test_export_stale_original_text_uses_structured`, `test_export_before_never_abt`, `test_gedcom_date_round_trip_property`.
    - **Validates: Requirements 9.1 to 9.14, 11.1 to 11.8, 14.2 to 14.10, 15.1 to 15.8**
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 9.11, 9.12, 9.13, 9.14, 9.15, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9, 14.6, 14.8, 14.9, 14.10, 14.11, 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7, 15.8, 15.9_

- [x] 6. Introduce the single change-marking API
  - [x] 6.1 Add `mark_changed` and the Project_Service mutation methods
    - In `slaktbusken/services/project_service.py` add `mark_changed(reason)`, `delete_place` and `add_places`. Keep the `_dirty` setter for internal use only. (`adopt_working_copy` and the pending translation come in task 11.2, the session methods in task 7.1.)
    - _Requirements: 4.1, 5.1, 17.1, 17.4, 17.5_

  - [x] 6.2 Replace direct dirty writers and fix B3 and B4
    - Replace every `project_service._dirty = True` in `slaktbusken/app.py` (L380, 459, 536, 1012, 1564, 1607, 1637, 2170, 2201, 2281) and `services/delete_service.py` (~L442) with `mark_changed`.
    - `place_editor._on_delete_place` (~L1793) calls `Project_Service.delete_place`; the existing referenced-place refusal stays and marks nothing.
    - `place_translation_editor` "skapa platser" (~L750) calls `Project_Service.add_places` once for the whole operation.
    - Replace any other raw collection mutation outside an Edit_Session found by the guard of task 6.3 with a Project_Service call.
    - _Requirements: 4.1, 4.2, 5.1, 5.2, 17.3, 17.4_

  - [x] 6.3 Write change-path coverage tests and static guards
    - `test_change_paths.py`: the change-path registry (every confirmed path and every known path of Person_Editor, Event_Editor, Residence_Editor, Place_Editor, Place_Translation_Editor, Source_Editor and delete service; the GEDCOM import path is registered by task 11.5 because the import is rebuilt in task 11.2), **Property 20: Every mutation path marks the project changed exactly when data changed** (`test_dp_property_20_*`), `test_every_registered_path_marks_exactly_when_changed`, `test_change_path_registry_covers_known_paths`, `test_place_delete_marks_dirty_and_bumps_revision`, `test_place_delete_refused_does_not_mark_dirty`, `test_create_places_marks_dirty_once`, `test_create_places_none_created_stays_clean`, `test_mark_changed_sets_dirty_bumps_revision_notifies_once`, `test_service_methods_for_place_delete_and_create_call_mark_changed_once`.
    - `test_change_path_guards.py`: `test_guard_no_external_dirty_assignment`, `test_no_external_dirty_assignment` and `test_guard_no_unlisted_collection_mutation` (static `ast` guards described in `design.md`); generate the initial allow-list in `change_path_allowlist.py`, review every entry and give it a reason.
    - **Validates: Requirements 4.1 to 4.3, 5.1 to 5.3, 17.1 to 17.6, 18.1 to 18.7**
    - _Requirements: 4.3, 5.3, 17.6, 18.1, 18.2, 18.3, 18.4, 18.5, 18.6, 18.7_

- [x] 7. Implement edit sessions and fix the person editor Avbryt (B1, B5)
  - [x] 7.1 Implement `EditSession`
    - Create `slaktbusken/services/edit_session.py` with the full snapshot (every list field of `ProjectData` except `SESSION_EXCLUDED_FIELDS`, plus `project` and `connection_overrides`), `has_changes`, `commit`, `rollback`, `register_created_file`, `EditSessionBusy`, `UnsavedEditorsBlock`, `EditSessionRefused` and `EditSessionConflict`.
    - In `project_service.py` add `begin_edit_session` (checks the Session_Start_Conditions (a) to (f) and (c2, Import_Save_Unfinished) of the design in order and raises the Swedish messages of the design table; condition (b) names every blocking editor by its `editor_title`), `active_edit_session`, `set_import_in_progress`, and the deferral of `mark_changed` while a session is active; `commit` applies one call if `has_changes()`; `rollback` calls `notify_merge_changed` once without touching dirty state or counters.
    - Write the docstring decision that the snapshot is always the full snapshot and that a reduced scope needs the proof and approval of Requirement 1.13.
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.13, 2.1, 2.4, 17.2_

  - [x] 7.2 Integrate the session into the person editor, nested editors and the app
    - `app.py`: the three `PersonEditor` sites (L351, L433, L877; `open_person_editor` at L309) start the session before the dialog opens, commit it on accept and roll it back on reject or close. Remove the `project_service._dirty = True` writes tied to these flows.
    - Nested editors (Place, Source, media, repository, Event, Residence) opened from the Person_Editor run inside the same session; register created files with `register_created_file` (`source_editor.py:937-938`, the DNA logo copy at `dna_editor.py:186-189` when reachable from a person editor).
    - `app.import_gedcom` (L1118), merge and person deletion check `active_edit_session` and refuse with the Swedish message of Requirement 1.8 naming the open person editor by `editor_title`.
    - Show the Swedish refusal and conflict messages from the design's Error Handling table.
    - _Requirements: 1.1, 1.2, 1.5, 1.6, 1.8, 1.9, 1.10, 1.11, 2.1, 2.2, 2.3, 2.5_

  - [x] 7.3 Write edit-session tests
    - `test_edit_session.py`: **Property 1: Cancelling an edit session restores state exactly** and **Property 2: Committing an edit session marks the project changed exactly when data changed** (`test_dp_property_1_*`, `test_dp_property_2_*`), plus `test_cancel_after_remove_event_restores_event`, `test_cancel_after_delete_residence_restores_residence`, `test_cancel_after_parent_family_edit_restores_families`, `test_cancel_after_new_family_removes_family`, `test_cancel_restores_identity_of_entities`, `test_cancel_leaves_dirty_and_revision_unchanged`, `test_save_unchanged_does_not_mark_dirty`, `test_second_session_refused`, `test_conflict_detected_refuses_rollback`, `test_session_start_refused_when_unsafe` (one example per condition (a) to (f) and (c2), message names the editor title), `test_session_snapshot_covers_every_project_data_field`, `test_cancel_removes_nested_created_place`, `test_cancel_removes_nested_created_source`, `test_cancel_restores_nested_deleted_place`, `test_cancel_removes_nested_created_media`, `test_save_keeps_nested_created_entities`, `test_mark_changed_deferred_in_edit_session`, `test_edit_session_restores_residence_origins`. Include headless reproductions of the two B1 cases using the real `_on_remove_event` and `_on_delete_residence`, and a nested creation in `leverantorer` and in a research collection.
    - `test_edit_session_performance.py`: `test_edit_session_10k_persons_reports_time_within_bound` (prints times, `UserWarning` above 1.5 s, fails above 10 s, records the figure of task 1.2).
    - **Validates: Requirements 1.1 to 1.14, 2.1 to 2.6, 17.2**
    - _Requirements: 1.2, 1.3, 1.4, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.12, 1.14, 2.2, 2.3, 2.5, 2.6, 17.6_

- [x] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Fix the event editor (B6, B7, B8) and expose qualifiers and unparsed dates
  - [x] 9.1 Implement the pure event assembler
    - Create `slaktbusken/ui/editors/event_assembler.py` with `CitationRow`, `DateFormState`, `EventFormState`, `CitationChoice`, `PromptNeed`, `prompts_needed`, `assemble_event` and `append_moved` as specified. `assemble_event` works on `copy.deepcopy(base)` and overwrites only form-controlled fields, so `from_place`, `origin` and future fields pass through. Keep the date unchanged (including `original_text`) when the form date fields equal the loaded values. Prompts: date removed, place or from-place removed (three choices), place or from-place changed (four choices); unchanged contexts never prompt. `append_moved` skips only a reference identical to one already in the target context and never reorders or deduplicates existing references.
    - _Requirements: 6.1, 6.3, 6.4, 6.5, 6.7, 6.8, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.10, 7.11, 8.1, 8.5, 8.6, 12.3, 12.6, 16.2, 16.3, 16.4_

  - [x] 9.2 Wire the assembler into the Event_Editor UI
    - In `ui/editors/event_editor.py` replace the Event construction at ~L2038-2085 with `assemble_event` (the current code builds `PlaceRef(place_id=...)` freshly at L2052 and drops `from_place`); load rows for event, date, place and from_place citations (fixes L902-905); add the "Gäller" column; add the qualifier combo, the range-end field and the calendar choice; reconcile the existing approximate/precision control with qualifier `about`; reject dates that are not real in the chosen calendar with the Swedish message of the design.
    - Show the prompts of the design with their Swedish texts, the default button "Flytta till händelsen" for removal and change, and "Avbryt" aborting the whole save; collect all answers before calling `assemble_event`.
    - Show an unparsed date read-only with "Tolkades inte vid import" and the explanation text of the design; a new date replaces it.
    - Add the "Från plats" combo (approved AP3), visible only while the event type is `flytt`, bound to `EventFormState.from_place_id`; clearing it stores `from_place` as absent; its citations keep the context "Från plats" with the prompts of the design; changing the type away from `flytt` keeps `from_place` and its citations.
    - Use the active session for nested place and source creation as established in task 7.2.
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10, 7.11, 8.1, 8.4, 8.5, 8.6, 8.7, 12.6, 15.5, 16.1, 16.3, 16.4_

  - [x] 9.3 Preserve from_place in the residence editor
    - Make the Residence_Editor path that creates or saves flytt events keep `from_place` and its citations (`residence_editor.py:1667-1678` creates the event; route edits of an existing flytt through the assembler or copy the base event).
    - _Requirements: 8.2_

  - [x] 9.4 Write event editor tests
    - `test_event_assembler.py`: **Property 3: Opening and saving an event without edits is the identity**, **Property 4: Removing or changing a date, place or from-place preserves or drops citations as chosen**, **Property 13: Original text survives edits that do not change the date** (`test_dp_property_3_*`, `_4_*`, `_13_*`), plus `test_empty_date_keeps_citations_as_event_level`, `test_clear_date_prompt_move_preserves_all_fields`, `test_clear_date_prompt_remove_keeps_source_record`, `test_clear_date_prompt_cancel_preserves_state`, `test_move_dedupes_only_exact_identical_references`, `test_move_keeps_distinct_citation_details`, `test_place_citations_survive_save`, `test_open_save_unchanged_event_no_prompt`, `test_remove_place_prompt_move_to_event`, `test_remove_place_prompt_remove_links`, `test_remove_place_prompt_cancel_preserves_state`, `test_remove_from_place_prompt_move_to_event`, `test_change_place_prompt_keep_for_new_place`, `test_change_place_prompt_move_to_event`, `test_change_place_prompt_remove_links`, `test_change_place_prompt_cancel_preserves_state`, `test_change_from_place_prompt_choices`, `test_change_place_without_citations_no_prompt`, `test_multiple_prompts_cancel_changes_nothing`, `test_no_prompt_choice_deletes_a_source_record`, `test_event_editor_save_preserves_from_place`, `test_residence_editor_save_preserves_from_place`, `test_open_save_without_edit_is_identity_for_flytt`, `test_clear_from_place_stores_none`, `test_from_place_citations_keep_separate_context`, `test_type_change_away_from_flytt_keeps_from_place`, `test_unparsed_date_preserved_by_unrelated_edit`, `test_unparsed_date_replaced_only_by_explicit_new_date`, `test_original_text_cleared_when_date_changed`, `test_unparsed_date_save_reopen_round_trip`, `test_editor_add_citation_defaults_to_event_level`, `test_invalid_day_rejected_in_editor`. Include headless reproductions of B6, B7 and B8.
    - `test_event_editor_ui.py` (offscreen Qt): `test_place_citations_shown_in_table_with_context`, `test_prompt_default_is_move`, `test_change_place_prompt_default_is_move`, `test_unparsed_date_shown_read_only_with_explanation`, `test_from_place_selector_shown_only_for_flytt`, `test_from_place_selector_sets_from_place`.
    - **Validates: Requirements 6.1 to 6.9, 7.1 to 7.12, 8.1 to 8.8, 12.3, 12.6, 15.5, 16.1 to 16.6**
    - _Requirements: 6.9, 7.12, 8.8, 12.7, 15.9, 16.6_

- [x] 10. Implement GEDCOM event and residence identity (B10, M4, M5)
  - [x] 10.1 Implement the record hash and the generic identity matcher
    - Create `slaktbusken/gedcom/translation/record_identity.py` with `IncomingRecord` (kind `event` or `residence`, owner kind and id, owner xref, tag key, index, record hash, uid, lazy `fingerprint`), `PoolEntry` (object plus one origin), `OriginGroup` and `build_origin_groups` (pool entries grouped by `origin_key`; a group has one or several members), `Outcome`, `MatchResult` (`members`, `candidates`, `instance`, `outcome`), `record_hash` (canonical form of the design: whitespace collapsed, `CHAN`/`_UPD`/`_CRE`/`_UID` excluded, `SOUR` pointers resolved to app source ids and other pointers replaced by a token, sibling groups ordered by tag with the order of same-tag siblings kept; used for event records and `RESI` records), `event_fingerprint`, `residence_fingerprint` (person, place, Endpoint earliest, latest, event id and note, role, notes, Observations in order; `Endpoint.precision` excluded), `tag_key_of` and the pure `match_records(incoming, pool, legacy_pool, foreign)` following the algorithm of the design (step 0 groups, step 1 uid, step 2 tag key and hash, step 3 legacy fingerprint, step 4 new).
    - The claim unit is the Origin_Group. An incoming record that pairs with a group claims all its members; pairing in step 2 counts groups (a group created by a split counts once, separately imported identical records are separate groups because their `instance` differs) and orders them by `instance`; a uid shared by several unclaimed groups claims nothing. Legacy objects are never grouped. `NEW`, `NEW_AMBIGUOUS` and `LEGACY_CLAIMED` results carry an `instance`: the smallest unused value among the owner's origins with equal tag key and hash, also counting values assigned earlier in the same call.
    - There is no step that claims by tag and index, by event type and place, or by residence date and place, and no step reads `index`. The legacy fingerprint is evaluated only when the legacy pool still holds an unclaimed object. Each Origin_Group and each legacy object is claimed at most once. The function never alters an object.
    - Put the fixed golden vectors for `record_hash` (two event records and two `RESI` records) next to the module so that task 10.5 can pin them.
    - _Requirements: 10.1, 10.8, 10.10, 10.11, 19.3, 19.4, 19.5, 19.6, 19.7, 22.3, 22.4, 22.5, 22.6, 22.9, 22.14, 22.25, 22.27, 22.28, 22.30, 22.31, 19.12, 19.13_

  - [x] 10.2 Use the matcher for events and set `Event.origin` in the importer
    - In `gedcom/importer.py` collect the event records of an owner into `IncomingRecord` objects and call `match_records` once per owner in `_create_person_events` (INDI) and in `_create_family` and `_update_family` (FAM). Resolve the owner id from `_person_xref_map` or `_family_xref_map`; build `pool`, `legacy_pool` and `foreign` as in the design.
    - Replace `_existing_event_keys` and the key set built at `importer.py:2127-2136` and the check at ~L2986-2992. Per result: `UNCHANGED` skip every member of the claimed group without any write, id or place resolution; `CHANGED_UID` skip with the Swedish notice of the design (one per incoming record); `LEGACY_CLAIMED` set `origin` including the matcher's `instance` (the only allowed modification, AP1), count it in `ImportResult.events_claimed` and report "{n} befintliga händelser kopplades till GEDCOM-posterna och fick ursprungsmärkning."; `NEW` and `NEW_AMBIGUOUS` create the event with `origin` (storing the matcher's `instance`) and, for the latter, add the Swedish notice naming the new event and at most five candidates. Run the placement bookkeeping for new events only. Never update `origin.index`.
    - Remove the deletion and recreation of family events at `importer.py:2700-2751`; keep every id of `family.event_ids` and append the ids of new events (AP5).
    - Run the idempotence property of task 10.7 against the whole-project post-steps (`importer.py:1292-1315`); if it fails because a post-step rewrites existing data, make that step idempotent.
    - _Requirements: 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 10.10, 10.11, 10.12, 10.14, 19.2, 19.4, 19.5, 19.7, 19.8, 19.11, 19.12, 19.13_

  - [x] 10.3 Use the matcher for residences and set `ResidenceFact.origins` in the importer
    - Split `_create_residence` (`importer.py:2238-2349`) into `_resolve_residence_place` (place resolution, coordinates, mappings and the place warnings of today), `_derive_residence` (pure: dates through `_parse_resi_date`, Observations from SOUR lines; empty id) and `_add_residence` (issues the id, sets `origins` to one `RecordOrigin` with the `instance` assigned by the matcher, appends).
    - In `_create_person_events` collect the `RESI` children of the person into `IncomingRecord` objects (kind `residence`, tag key `RESI`), call `match_records` once for the person, and walk the children in file order. `UNCHANGED`: skip entirely, for every member of the claimed Origin_Group, so that the halves of a split residence are all left alone and no third residence is created (no id, place, coordinates, mapping, warning or write). `CHANGED_UID`: skip with one Swedish notice, every member unchanged. `LEGACY_CLAIMED`: set `origins` (one origin with the matcher's `instance`), count in `ImportResult.residences_claimed`, report "{n} befintliga boenden kopplades till GEDCOM-posterna och fick ursprungsmärkning.", and add the duplicate notice of Requirement 22.16 when identical unclaimed legacy residences remain. `NEW` and `NEW_AMBIGUOUS`: resolve the place, derive, add; the date and place warnings now appear only for created residences; for `NEW_AMBIGUOUS` add the Swedish notice with at most five candidates.
    - Add `ImportResult.residences_added`, `residences_claimed`, `events_claimed` and the line "Boenden: {n} nya, {m} kopplade till befintliga" in `ImportService.format_result`.
    - Create no flytt event, set and clear no `Endpoint.event_id`, and merge, delete, reorder or modify no existing residence (the only write to an existing residence is adding `origins` to an exactly matching legacy residence). Merged_Identity_Records and ambiguous records create no residence (they never reach this code, F10).
    - _Requirements: 22.2, 22.3, 22.4, 22.5, 22.6, 22.7, 22.8, 22.9, 22.10, 22.11, 22.12, 22.13, 22.14, 22.15, 22.16, 22.17, 22.18, 22.19, 22.20, 22.21, 22.23, 22.24, 22.25, 22.27, 22.28, 22.29, 22.30, 22.31_

  - [x] 10.4 Preserve residence origins in every residence edit path
    - Replace the field-by-field `ResidenceFact(...)` rebuilds of F31 that keep the id with `dataclasses.replace(existing, ...)`: `residence_edit_ops.py:145, 183, 227, 316`; `residence_editor.py:1009, 1705, 1735, 2088` and `build_fact_from_fields` (L1407-1450, use `replace` on `self._residence` when editing an existing fact); `person_editor.py:1864`.
    - Split (`residence_edit_ops.py:420, 446`): both halves get `copy.deepcopy(fact.origins)`, every field including `instance`, so that both halves are members of the same Origin_Groups (this is deliberate; the matcher of task 10.1 handles it). Merge (`residence_edit_ops.py:584`): `earlier.origins` followed by the origins of `later` whose `origin_key` is not already present (equal Origin_Keys are deduplicated, so merging two split halves leaves the origin once; residences from different records keep both origins). No operation changes `instance`, `record_hash`, `owner_id`, `index` or `uid` of an origin. New residences typed by the user (`residence_editor.py:1023`, `person_editor.py:1793`) keep an empty list.
    - Fill `tests/test_dataskydd/residence_construction_allowlist.py` with the two new-residence sites and a reason each.
    - Search `services/`, `ui/` and `gedcom/` once more for any code that copies or duplicates an `Event` (F42 found none) and record the result in the task report; if one exists, route its origin handling through the same Origin_Group rule and add it to `test_event_origin_is_not_copied_by_any_event_operation`.
    - _Requirements: 22.22, 22.29, 19.13_

  - [x] 10.5 Write identity tests
    - `test_record_identity.py`: **Property 14: The identity matcher claims each record at most once, only on identity evidence** and **Property 15: The record hash is canonical for harmless differences and sensitive to meaningful ones** (`test_dp_property_14_*`, `_15_*`; both generate event records and `RESI` records), plus `test_origin_set_on_import`, `test_residence_origin_set_on_import`, `test_record_hash_ignores_change_tracking_tags`, `test_record_hash_ignores_order_of_distinct_tags`, `test_record_hash_keeps_order_of_repeated_tags`, `test_record_hash_stable_under_source_renumbering`, `test_record_hash_golden_vectors`, `test_residence_record_hash_ignores_change_tracking_tags`, `test_residence_record_hash_resolves_source_pointers`, `test_residence_record_hash_sensitive_to_date_place_and_sources`, `test_matcher_order_uid_hash_legacy`, `test_matcher_claims_once`, `test_matcher_never_claims_by_tag_and_index`, `test_matcher_legacy_fingerprint_one_to_one`, `test_matcher_never_matches_on_type_and_place_alone`, `test_matcher_property_no_duplicates_no_merges`, `test_matcher_owner_id_survives_xref_renumbering`, `test_residence_matcher_claims_pair_once`, `test_residence_matcher_never_matches_on_date_and_place_alone`, `test_residence_matcher_never_claims_by_tag_and_index`, `test_residence_matcher_owner_id_survives_xref_renumbering`, `test_edited_imported_event_not_modified_by_reimport`, `test_origin_instance_assigned_smallest_unused`, `test_matcher_origin_group_claimed_once_as_a_whole`, `test_matcher_distinguishes_origin_group_from_ambiguity`, `test_origin_group_split_counts_as_one_record`, `test_residence_changed_uid_with_group_leaves_all_members_unchanged`, `test_event_origin_duplicate_on_two_events_is_one_group`, `test_event_origin_is_not_copied_by_any_event_operation`. The generator of Property 14 produces pools with several objects (and one object twice) carrying equal origins, residences with two origins, legacy objects and foreign objects, and checks the claims against a simple reference model (count of groups, no claim on `foreign`, `instance` unused and distinct).
    - Put the strategies for GEDCOM records in `tests/test_dataskydd/strategies_gedcom.py`.
    - **Validates: Requirements 10.1, 19.2 to 19.8, 19.12, 19.13, 22.2 to 22.9, 22.27, 22.28, 22.30, 22.31**
    - _Requirements: 10.1, 19.2, 19.3, 19.4, 19.5, 19.6, 19.7, 19.8, 19.12, 19.13, 19.14, 22.2, 22.3, 22.4, 22.5, 22.9, 22.25, 22.27, 22.28, 22.30, 22.31, 22.33_

  - [x] 10.6 Write merge and origin tests
    - `test_merge_origin.py`: **Property 23: A merge preserves every event and residence origin** (`test_dp_property_23_*`, small generated projects, fixed example count), plus `test_merge_preserves_event_origin` (planner and engine), `test_residence_merge_origin` (planner and engine), `test_event_origin_in_person_reference_inventory`, `test_residence_origin_in_person_reference_inventory` (the completeness test passes and the rows are `H`), `test_merged_identity_record_creates_no_events`, `test_survivor_record_matches_only_own_origin_events`, `test_reimport_resi_merged_identity_record_creates_none` and `test_reimport_resi_after_person_merge_considers_only_survivor_origins`.
    - **Validates: Requirements 19.9, 19.10, 19.11, 22.20, 22.21, 22.26**
    - _Requirements: 19.9, 19.10, 19.11, 19.14, 22.20, 22.21, 22.26, 22.33_

  - [x] 10.7 Write event and combined re-import tests
    - `test_reimport.py`: **Property 16: Repeated import is stable and never removes, merges, duplicates or silently rewrites events and residences** and **Property 17: Dateless events and identical residence records stay distinct** (`test_dp_property_16_*`, `_17_*`; the generators produce person and family event records, `RESI` records in every date form with and without `PLAC`, `_ADPL`, `MAP`, `SOUR`, `NOTE` and `_UID`, identical records and `EVEN` TYPE Flytt records; the perturbations are those of the property, including residence merge, split, split then merge, merge of residences from different records and a save and reopen between the imports, all through `residence_edit_ops`, a flytt link between two residences, legacy records and a person merge), plus `test_dateless_same_type_place_events_stay_distinct`, `test_reimport_identical_file_creates_no_events`, `test_reimport_is_idempotent_property`, `test_reimport_is_idempotent_with_resi_property`, `test_reimport_reordered_records_creates_no_events`, `test_reimport_inserted_record_creates_one_event`, `test_reimport_removed_record_keeps_event`, `test_reimport_identical_records_pair_by_count`, `test_reimport_after_user_edit_leaves_event_unchanged`, `test_reimport_changed_record_creates_new_with_notice`, `test_reimport_uid_match_changed_record_reports_without_modifying`, `test_reimport_never_removes_existing_events`, `test_reimport_family_events_preserved`, `test_family_event_ids_never_dropped`, `test_deleted_imported_event_reappears_known_limitation`, `test_ambiguous_event_creates_new_with_review_notice`, `test_legacy_event_claim_reported_in_import_log`, `test_legacy_event_claim_marks_project_changed`. Include a headless reproduction of B10 and the re-import of a legacy (pre-0.5) project.
    - **Validates: Requirements 10.1 to 10.15, 22.10 to 22.15**
    - _Requirements: 10.15, 10.16, 19.7, 22.10, 22.33_

  - [x] 10.8 Write residence re-import, legacy and edit-path tests
    - `test_residence_reimport.py`: `test_reimport_resi_file_creates_no_residences`, `test_reimport_resi_reordered_creates_none`, `test_reimport_resi_inserted_record_creates_one`, `test_reimport_resi_removed_record_keeps_residence`, `test_reimport_resi_identical_records_pair_by_count`, `test_reimport_resi_changed_record_creates_new_with_notice`, `test_reimport_resi_uid_changed_record_reports_without_modifying`, `test_reimport_after_user_edit_leaves_residence_unchanged`, `test_reimport_after_user_edited_observations_leaves_residence_unchanged`, `test_reimport_resi_sour_change_creates_new_residence`, `test_deleted_imported_residence_reappears_known_limitation`, `test_residence_unchanged_writes_nothing_and_resolves_no_place`, `test_import_creates_no_flytt_event_from_residence`, `test_reimport_keeps_flytt_links_between_residences`, `test_reimport_keeps_flytt_event_count_with_resi`, `test_flytt_event_edited_in_app_not_duplicated_by_reimport`, `test_no_residence_is_merged_or_removed_by_import`, `test_residence_save_reopen_reimport_creates_none` (import, save, reopen, import again).
    - `test_residence_legacy.py`: **Property 26: A legacy residence is claimed only on exact content, one to one** (`test_dp_property_26_*`), plus `test_legacy_residence_exact_match_is_claimed_once`, `test_legacy_residence_with_different_content_is_not_claimed`, `test_legacy_residence_same_date_and_place_but_different_role_is_not_claimed`, `test_legacy_duplicates_are_kept_and_reported`, `test_legacy_claim_reported_in_import_log`, `test_legacy_claim_marks_project_changed`; use the v0.4 fixture with duplicated residences.
    - `test_residence_edit_paths.py`: **Property 25: Residence origins survive every residence edit operation** (`test_dp_property_25_*`), plus `test_residence_origins_survive_every_edit_operation`, `test_residence_editor_save_keeps_origins`, `test_residence_split_gives_both_halves_the_origins`, `test_residence_merge_combines_origins` and `test_guard_residence_construction_preserves_origins`.
    - **Validates: Requirements 22.6 to 22.25**
    - _Requirements: 22.6, 22.7, 22.8, 22.9, 22.10, 22.11, 22.12, 22.13, 22.14, 22.15, 22.16, 22.17, 22.18, 22.19, 22.22, 22.23, 22.24, 22.25, 22.33_

  - [x] 10.9 Write origin group regression tests
    - `test_origin_groups.py` with strategies in `tests/test_dataskydd/strategies_origin_groups.py` (a new module, so that this task does not write a file of another task): **Property 28: An unchanged re-import after any sequence of residence splits and merges creates, deletes and modifies nothing** (`test_dp_property_28_*`; generates GEDCOM files with `RESI` records including identical records and `_UID`, imports them, applies a generated sequence of split, merge, edit and save-and-reopen steps through `residence_edit_ops` and the project service, re-imports the same file and asserts that no residence is created, deleted or modified, that the Canonical_Form is equal, that the number of Origin_Groups per `(tag key, record hash)` is unchanged and that the Import_Log has no ambiguity notice; a second variant duplicates an event origin on a second event), plus the importer-level examples `test_reimport_after_residence_split_creates_no_residence_and_changes_none` (both halves equal before and after, no third residence), `test_reimport_after_split_then_merge_again_creates_none` (merged residence carries the origin once), `test_reimport_after_merge_of_residences_from_different_records_creates_none` (merged residence carries two origins and claims both incoming records), `test_reimport_after_split_save_reopen_creates_none`, `test_reimport_after_split_and_edit_of_one_half_leaves_both_unchanged`, `test_identical_resi_records_imported_twice_then_one_split_pairs_by_origin_group` (two groups, a third identical incoming record creates exactly one residence), `test_legacy_residence_split_before_first_import_is_never_grouped` (v0.4 fixture: legacy residence split at a gap; neither half is claimed unless exactly equal, both halves stay unchanged, one new residence and a notice are created) and `test_residence_split_merge_import_sequences_property` (the example-level driver of the sequence generator with fixed seeds, kept next to the property so that a failing sequence is reproduced by name).
    - **Validates: Requirements 19.13, 22.27 to 22.32**
    - _Requirements: 19.13, 22.27, 22.28, 22.29, 22.30, 22.31, 22.32, 22.33_

- [x] 11. Make the import atomic and the save crash-consistent and conflict-safe (B2, OQ4, AP2)
  - [x] 11.1 Add the translation staging mode
    - `gedcom/translation/__init__.py`: `TranslationManager(translation_dir, *, overlay=None)`; with an overlay `load_translations` returns a deep copy of the overlay and `map_place`/`map_source` read a shared read-only view; without an overlay behaviour is unchanged.
    - `gedcom/importer.py`: `GEDCOMImporter(project_data, translation_dir, *, overlay=None, stage_only=False)`; with `stage_only=True` skip `save_translations` (`importer.py:1318`) and return the mutated `TranslationData` in `ImportResult.translation`. Defaults keep existing callers and tests unchanged.
    - Add `dumps_sources` and `dumps_places` to `persistence/translation_io.py` next to `dumps_persons` (shared by the comparison of task 11.2 and the save of task 11.3).
    - _Requirements: 20.1, 20.2_

  - [x] 11.2 Make the import atomic, capture the translation base and mark the project changed
    - `services/import_service.py`: refuse when a session is active, the Editor_Registry reports unsaved editors (naming the editor by `editor_title`) or Import_Save_Unfinished holds; call `set_import_in_progress`; capture the translation base (SHA-256 of each of the three translation files or `absent`) unless a pending translation exists; deep-copy `project_data`; run the importer on the copy with `stage_only=True` and `overlay=project_service.pending_translation.data`; validate; capture the base again and abort the import with "Översättningsfilerna ändrades under importen. Ingenting har ändrats." when it differs, discarding the working copy and leaving the project data, the pending translation, the dirty state and the files as they were; compare Canonical_Forms and the serialised staged and effective translation data; adopt nothing when both are equal.
    - `services/project_service.py`: `adopt_working_copy(work, pending, reason)` assigns every field of `work` onto the existing `ProjectData` instance, stores `pending` (`PendingTranslation(data, base)`, only when the translation data changed; a second import keeps the base of the first) and calls `mark_changed` once; `pending_translation` property; `close_project` and `open_project` clear it.
    - `app.import_gedcom` (L1118-1180) passes the project service and refreshes views through the listeners; no direct `_dirty` write.
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 20.1, 20.3, 20.4, 20.5, 20.13, 20.14, 20.15_

  - [x] 11.3 Save the translation files with digest verification and recover at open
    - Create `slaktbusken/services/commit/translation_commit.py` with `TranslationCommit.commit(project_bytes, pending, expected_project_digest)` following steps S1 to S8 of the design: pre-flight with `Preflight.check`; digest verification of the project file (must equal the Disk_Digest) and of each translation file (must equal its base digest or the digest of the new content); write the Translation_Intent through a temp file and a replace; write and verify the project temp and each translation temp; verify again and replace the project file (commit point); verify each translation file again, skip files that are already new, replace the others; remove the intent. Conflicts and errors follow the table of the design: before the commit point only the intent and temps that this save attempt created are removed, and the project stays dirty with the pending translation kept in memory for retry; after the commit point the intent and temps are kept until the save is completed or resolved, and Import_Save_Unfinished is entered. An unresolved conflict at open is raised through the existing recovery-refusal mechanism (task 11.4). Raise `SaveConflict(files)`, `SaveFailed` and `ImportSaveUnfinished(files)` with the Swedish messages of the design.
    - Add `recover_translation_intent(project_file, fs)` with the decision table of the design (complete, discard, or refuse with codes T1 to T5) and `ImportSaveRefusal` (code, project path, intent path, temp paths, per-file states, Swedish `message`), raised inside `RecoveryRefusedError`. Verify each file immediately before writing it during recovery, and remove the intent only after every translation file is new. Reuse `CommitFs`, `Preflight`, `sha256_hex` and `temp_path_for`.
    - `persistence/file_io.py`: add `FilePersistence.write_bytes` (the temp-file and `os.replace` part of `save`, which now calls it) and `FilePersistence.load_with_digest` (returns the data and the SHA-256 of the bytes read).
    - `services/project_service.py`: `disk_digest` (set by `open_project` and `save_project`), `import_save_unfinished`, `save_project` encodes once and writes through `write_bytes` or `TranslationCommit`, clears the pending translation after success and keeps it on failure; `open_project` calls `recover_translation_intent` after the merge recovery and before loading, records the message in `last_recovery_message` and, on refusal, adds the path to `_refused_projects`; `is_merge_journal_pending` is also true while Import_Save_Unfinished holds; `begin_edit_session` gets the condition (c2).
    - _Requirements: 20.6, 20.7, 20.8, 20.9, 20.10, 20.11, 20.16, 20.17, 20.18, 20.19, 20.20, 20.21_

  - [x] 11.4 Integrate conflicts, refusals and blocked states into the application
    - `app.py` save handler (L1096-1116): show the Swedish message of `SaveConflict` (naming the files, with the next steps), `SaveFailed` and `ImportSaveUnfinished` in message boxes, keep the project open and dirty after a refused save, and refresh the status.
    - `app.py` open sites (L1073, L2227, L2408): the refusal reaches `_report_open_failure` (L1804-1817) through `RecoveryRefusedError`, so no change is needed there beyond tests; `ui/merge/recovery_dialogs.py`: `show_recovery_outcome` gets an optional `title` argument and the recovery message of an interrupted import save is shown under the title "Avbruten sparning".
    - `ui/editors/place_translation_editor.py`, `ui/editors/source_translation_editor.py` and the app entry points that open them refuse while a pending translation exists ("Spara projektet innan du redigerar översättningarna. En import väntar på att sparas.") and while Import_Save_Unfinished holds ("En sparning av en import är inte avslutad. Starta om Släktbusken för att slutföra eller kontrollera filerna."). `app.import_gedcom` and the save handler refuse with the same text while Import_Save_Unfinished holds.
    - _Requirements: 20.8, 20.11, 20.12, 20.17, 20.18, 20.19, 20.20_

  - [x] 11.5 Write atomicity tests
    - `test_import_atomicity.py`: **Property 18: A failed or cancelled import changes nothing** and **Property 19: A successful import marks the project changed exactly once, and a no-op import not at all** (`test_dp_property_18_*`, `_19_*`), plus `test_import_marks_dirty_and_bumps_revision` (headless reproduction of B2), `test_noop_import_does_not_mark_dirty`, `test_import_notifies_listeners_once`, `test_close_after_import_prompts_to_save`, `test_translation_only_change_marks_dirty`, `test_failed_import_leaves_project_unchanged`, `test_failed_import_leaves_translation_files_byte_identical`, `test_cancelled_import_leaves_project_unchanged`, `test_import_writes_no_translation_file_before_save`, `test_successful_import_adopts_once`, `test_noop_import_adopts_nothing`, `test_import_refused_with_unsaved_editor`, `test_import_records_translation_base`, `test_translation_file_changed_during_import_aborts_import`, `test_second_import_uses_pending_translation`, `test_close_without_save_discards_pending_translation`, `test_translation_editors_refuse_while_pending`, `test_unsaved_import_then_new_person_never_aliases_mapping`.
    - Add the GEDCOM import path to the change-path registry in `test_change_paths.py` (created in task 6.3) so that `test_every_registered_path_marks_exactly_when_changed` and `test_change_path_registry_covers_known_paths` cover it.
    - **Validates: Requirements 3.1 to 3.6, 18.1, 18.2, 20.1 to 20.5, 20.12 to 20.15**
    - _Requirements: 3.6, 18.1, 18.2, 20.22_

  - [x] 11.6 Write fault-injection tests for the save protocol and the recovery
    - Create `tests/test_dataskydd/fault_fs.py`: `FaultFs` (a `CommitFs` wrapper that counts operations, fails at the n-th operation with `OSError` or raises `SimulatedCrash(BaseException)`, and runs a callback before a chosen operation so that a test can change a file at an exact point) and `SimulatedCrash`.
    - `test_translation_commit.py`: **Property 24: A save with a pending translation is crash-consistent** (`test_dp_property_24_*`; Hypothesis chooses project content and pending translation, the injection point is enumerated; each case runs the real recovery on real files in a temporary directory), plus `test_save_writes_intent_project_translation_in_order`, `test_save_failure_before_project_replace_restores_state`, `test_save_fault_before_intent`, `test_save_fault_after_intent`, `test_save_fault_after_project_write`, `test_save_fault_after_each_translation_write` (parametrised over the translation files), `test_save_fault_before_intent_removal`, `test_save_fault_at_every_fs_call_as_exception`, `test_save_fault_at_every_fs_call_as_crash`, `test_crash_at_every_save_step_recovers_consistently`, `test_recovery_fault_at_every_fs_call`, `test_recovery_is_idempotent_after_crash`, `test_open_completes_translation_when_project_is_new`, `test_open_discards_intent_when_project_is_old`.
    - Every case asserts the two allowed end states (old project with old translation files, or new project with new translation files), no remaining intent or temporary file, and, for exceptions, the in-process state (dirty and pending kept before the commit point; Import_Save_Unfinished after it).
    - **Validates: Requirements 20.6, 20.9, 20.16, 20.21**
    - _Requirements: 20.6, 20.9, 20.16, 20.21, 20.22_

  - [x] 11.7 Write external-modification and refusal tests
    - `test_translation_conflicts.py`: **Property 27: A file changed outside Släktbusken is never overwritten** (`test_dp_property_27_*`; Hypothesis chooses the file and the replacement bytes, the point in time is enumerated: before the save, between any two operations of the save, between a crash and the recovery), plus `test_translation_file_changed_between_import_and_save_refuses_save`, `test_translation_file_already_new_is_accepted_at_save`, `test_translation_file_changed_before_commit_point_removes_own_artifacts`, `test_translation_file_changed_after_commit_point_preserves_intent`, `test_project_file_changed_between_open_and_save_refuses_save`, `test_project_file_changed_before_commit_point_removes_own_artifacts`, `test_translation_file_changed_before_recovery_refuses_open`, `test_project_file_changed_before_recovery_refuses_open`, `test_project_file_missing_before_recovery_refuses_open`, `test_damaged_intent_refuses_open_and_is_kept_byte_identical`, `test_conflict_messages_name_files_and_state_in_swedish`, `test_conflict_refusal_blocks_normal_save`, `test_conflict_refusal_changes_no_file`, `test_unfinished_import_save_blocks_save_import_and_translation_editors`.
    - Each test asserts byte identity of the externally changed file after the save or the recovery, the refusal message text (Swedish, naming the file and its state), that a refusing recovery leaves the intent byte-identical, and that no translation file other than the conflicting one is written during a refusal.
    - **Validates: Requirements 20.7, 20.8, 20.10, 20.11, 20.16 to 20.20**
    - _Requirements: 20.7, 20.8, 20.10, 20.11, 20.16, 20.17, 20.18, 20.19, 20.20, 20.22_

- [x] 12. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 13. Add cross-component round-trip tests
  - [x] 13.1 Write save, reopen, export and import round-trip tests
    - `test_round_trips.py`: build a project with all new fields (event citations, place and from_place citations, every qualifier, a Julian date, an unparsed date with original text, event origin, residences with origins and without, a flytt link between two residences); save and reopen it; export it to GEDCOM and import into a new project; assert that dates, qualifiers, citations (as multisets per event), `from_place` and original texts survive, and that a second import of the exported file creates no events and no residences. Include a save of an imported project (pending translation) followed by reopen and a re-import that creates no events and no residences.
    - _Requirements: 11.9, 12.7, 14.11, 16.6, 20.22, 21.7, 22.33_

- [x] 14. Register the mandatory group
  - [x] 14.1 Register the Dataskydd group and finish the guard
    - In `tests/mandatory_groups.py` add `MandatoryGroup(key="data_protection", title_sv="Dataskydd", ...)` with all modules of `tests/test_dataskydd/` and every acceptance test named in the requirements, plus `test_dp_property_N_*` prefix entries for Properties 1 to 28. Use the `properties` value recorded in task 1.1. This spec authorises the edit of the file that the earlier spec froze.
    - Add `test_group_registration.py::test_dataskydd_group_registered_and_complete` that imports the registry, asserts the group exists with title "Dataskydd", that every required test exists, and that no test in the package carries `skip`, `skipif` or `xfail`.
    - Run `scripts/run_mandatory_tests.py` and confirm the group is reported under "Dataskydd" with zero skips beyond the one defined Windows-only test.
    - _Requirements: 23.1, 23.2, 23.3, 23.4, 23.5, 23.6, 23.7_

- [x] 15. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Requirement traceability

| Requirement | Implemented by | Tested by |
|---|---|---|
| 1 Edit session, Avbryt | 7.1, 7.2 | 7.3 |
| 2 Nested creations | 7.1, 7.2 | 7.3 |
| 3 Import marks changed | 11.2 | 11.5 |
| 4 Place delete | 6.1, 6.2 | 6.3 |
| 5 Skapa platser | 6.1, 6.2 | 6.3 |
| 6 Date citations | 3.1, 9.1, 9.2 | 9.4 |
| 7 Place and from-place citations | 3.1, 9.1, 9.2 | 9.4 |
| 8 from_place and the "Från plats" selector (AP3) | 9.1, 9.2, 9.3 | 9.4 |
| 9 Date import | 5.2 | 5.5 |
| 10 Re-import of events (and RESI together) | 10.1, 10.2, 10.3 | 10.7 |
| 11 Date export | 5.3 | 5.5 |
| 12 Event citations | 2.1, 2.2, 3.2, 9.1 | 2.5, 3.4, 9.4 |
| 13 Citation helper | 3.1, 3.2 | 3.3, 3.4 |
| 14 Date qualifiers and bounds | 2.1, 5.1, 5.4 | 2.5, 5.5 |
| 15 Calendar validation | 5.1, 5.2, 9.2 | 5.5, 9.4 |
| 16 Unparsed dates | 9.1, 9.2 | 9.4 |
| 17 mark_changed | 6.1, 6.2, 7.1 | 6.3, 7.3 |
| 18 Change-path guard | 6.2, 11.5 | 6.3, 11.5 |
| 19 Event identity (AP1, AP5), including Origin_Instance (19.12) and event origin groups (19.13) | 2.1, 2.2, 2.4, 10.1, 10.2, 10.4 | 2.5, 10.5, 10.6, 10.7, 10.9 |
| 20 Atomic import, conflict-safe crash-consistent save (AP2) | 11.1, 11.2, 11.3, 11.4 | 11.5, 11.6, 11.7 |
| 21 Format 0.5 | 2.3 | 2.5 |
| 22 Residence identity (AP4), including origin groups (22.27 to 22.32) | 2.1, 2.2, 2.4, 10.1, 10.3, 10.4 | 2.5, 7.3, 10.5, 10.6, 10.7, 10.8, 10.9, 13.1 |
| 23 Mandatory group | 14.1 | 14.1 |

## Notes

- No task is optional. Every test sub-task is required because all tests belong to the mandatory group "Dataskydd".
- Each test sub-task names the design properties it implements and the requirement clauses it validates.
- The approval items AP1 to AP5 are decided and implemented as listed in the Overview. The design records the few choices that the user may still veto (`design.md`, "Decisions made in this revision").
- Task 1.2 reports the measured snapshot time and never changes the snapshot scope by itself.
- Task 14.1 is the only task that edits `tests/mandatory_groups.py`.
- Strategies for new test tasks go into their own module (`strategies_gedcom.py` and similar) so that tasks of one wave never write the same file.
- Package 2 (Advanced Person Filtering) is out of scope. Task 5.1 provides `date_bounds` only as preparation.
- Do not commit as part of any task unless the user asks.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "2.1", "6.1"] },
    { "id": 1, "tasks": ["2.2", "2.4", "3.1", "5.1", "7.1", "10.1"] },
    { "id": 2, "tasks": ["2.3", "3.2", "6.2"] },
    { "id": 3, "tasks": ["2.5", "3.3", "5.2", "5.4", "6.3", "7.2", "9.1"] },
    { "id": 4, "tasks": ["3.4", "5.3", "7.3", "9.2", "9.3", "11.1"] },
    { "id": 5, "tasks": ["5.5", "9.4", "10.2", "10.4", "11.2"] },
    { "id": 6, "tasks": ["10.3", "11.3"] },
    { "id": 7, "tasks": ["10.5", "10.6", "10.7", "10.8", "11.4", "11.6"] },
    { "id": 8, "tasks": ["10.9", "11.5", "11.7"] },
    { "id": 9, "tasks": ["13.1"] },
    { "id": 10, "tasks": ["14.1"] }
  ]
}
```
