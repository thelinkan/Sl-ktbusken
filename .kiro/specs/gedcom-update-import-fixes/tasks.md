# Implementation Plan: GEDCOM Update Import Fixes

## Overview

This plan fixes 5 bugs in the GEDCOM update import flow:
1. Mixed English/Swedish text in completion dialog
2. Duplicate events created instead of updating existing ones
3. Events attached to wrong persons (event-to-person mapping leaks between INDI records)
4. Single-word PLAC values silently dropped
5. Insufficient detail in import report

The workflow follows the bug condition methodology: write exploration and preservation tests BEFORE the fix using real GEDCOM test fixtures (Test-1 through Test-4 at `tests/fixtures/gedcom/`), implement fixes in isolation, then verify both test classes pass.

## Tasks

- [x] 1. Write bug condition exploration tests
  - **Property 1: Bug Condition** - GEDCOM Update Import Defects
  - **CRITICAL**: These tests MUST FAIL on unfixed code - failure confirms the bugs exist
  - **DO NOT attempt to fix the tests or the code when they fail**
  - **NOTE**: These tests encode the expected behavior - they will validate the fixes when they pass after implementation
  - **GOAL**: Surface counterexamples that demonstrate all 5 bugs exist
  - **Scoped PBT Approach**: Scope each property to concrete failing cases using real GEDCOM test fixtures (Test-1 through Test-4)
  - Test 1a: Import a GEDCOM with two-level place (e.g. "Falun, Kopparbergs län") via `ImportService.run()` which triggers validation — assert validation warnings do NOT contain English place type names like "county", "country", "parish" (Bug 1, from Bug Condition in design)
  - Test 1b: Import Test-1.ged as base, then reimport same file as update — assert event count for each person does NOT increase (Bug 2, from Bug Condition in design)
  - Test 1c: Import Test-2.ged as update (adds Sune + events), assert each person's events belong ONLY to that person — no leakage between INDI records (Bug 3, from Bug Condition in design)
  - Test 1d: Import a GEDCOM event with `2 PLAC Falun` (single-word), assert place is preserved on the event — not None/dropped (Bug 4, from Bug Condition in design)
  - Test 1e: Trigger a warning condition during import, assert warning includes xref, person name, event type, raw value, and reason (Bug 5, from Bug Condition in design)
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests FAIL (this is correct — it proves the bugs exist)
  - Document counterexamples found (e.g., English text in dialog, doubled event count, wrong person_id on events, None place_ref, unstructured warning strings)
  - Mark task complete when tests are written, run, and failures are documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 2. Write preservation property tests (BEFORE implementing fixes)
  - **Property 2: Preservation** - Existing GEDCOM Import Behavior Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Observe: Full initial import of Test-1.ged creates 3 persons, 1 family, correct events on UNFIXED code
  - Observe: Multi-word PLAC values ("Falun, Dalarna, Sverige") resolve correctly on UNFIXED code
  - Observe: Update import of Test-2.ged (after Test-1) adds Sune, marriage event on F1, FAMC link — existing events on Stina/Anders/Bettan are untouched on UNFIXED code
  - Observe: New persons added during update import (Sune in Test-2) get their events attached correctly on UNFIXED code
  - Observe: Import of clean GEDCOM data produces no spurious warnings on UNFIXED code
  - Write property-based tests capturing observed behavior patterns:
    - Property: For any GEDCOM file imported as initial import, all persons/families/events/places are created correctly (Preservation Req 3.1)
    - Property: For any multi-word PLAC value, place is normalized and stored correctly (Preservation Req 3.3)
    - Property: For any update import with unchanged events, those events remain unmodified (Preservation Req 3.4)
    - Property: For any update import adding entirely new persons with valid records, persons and events are created correctly (Preservation Req 3.2)
    - Property: For any clean GEDCOM import, report contains no spurious warnings (Preservation Req 3.5)
  - Verify all tests PASS on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3. Fix Bug 1: Swedish-only validation messages

  - [x] 3.1 Translate place type names in validation error messages
    - Add a `_PLACE_TYPE_SWEDISH` dictionary in `slaktbusken/model/validators.py` mapping English place type identifiers to Swedish: county→län, country→land, parish→församling, church→kyrka, cemetery→kyrkogård, village→by, farm→gård, school→skola
    - Update `_validate_place_hierarchy` to use `_PLACE_TYPE_SWEDISH.get(place.type, place.type)` in all error messages
    - Update the `_VALID_PLACE_TYPES` error message in `validate_place` to show Swedish names
    - Verify that all validation messages visible to users (via `ImportService.run` → `ValidationService.validate_project` → `_validate_place`) are fully Swedish
    - _Bug_Condition: validationWarningContainsEnglishPlaceType(warning)_
    - _Expected_Behavior: all_text_is_swedish(validation_warnings)_
    - _Preservation: Validation logic unchanged — only display names translated_
    - _Requirements: 2.1_

- [x] 4. Fix Bug 2: Event deduplication on update import

  - [x] 4.1 Implement event matching and deduplication in _update_person
    - In `slaktbusken/gedcom/importer.py`, modify `_update_person` to query existing events for the person before calling `_create_person_events`
    - Match incoming events by (person_id, event_type, date, place) tuple
    - If matching event exists: skip or update if changed
    - Only create truly new events (no match found)
    - _Bug_Condition: existingPersonHasMatchingEvents(input.person, input.events) AND duplicatesCreated(input)_
    - _Expected_Behavior: count_events_for_person(person_id) == expected_count (no duplicates)_
    - _Preservation: New events for persons who didn't previously have them are still created_
    - _Requirements: 2.2, 3.2, 3.4_

- [x] 5. Fix Bug 3: Event isolation between INDI records

  - [x] 5.1 Implement event state reset between INDI records
    - In `slaktbusken/gedcom/importer.py`, locate `_process_persons` loop over INDI records
    - Add explicit reset of event-related state at the start of each INDI record iteration
    - Verify `person_id` is correctly scoped to each iteration — no variable leaking from previous iteration
    - Ensure `_create_person_events` receives only events belonging to the current INDI record
    - _Bug_Condition: newPersonReceivedEventsFromOtherINDI(input.person, input.events)_
    - _Expected_Behavior: all_events_for(person_id).all(e => e.participant.person_id == person_id)_
    - _Preservation: Events for correctly-structured new persons are still attached properly_
    - _Requirements: 2.3, 3.2_

- [ ] 6. Fix Bug 4: Single-word PLAC value preservation

  - [ ] 6.1 Implement single-word place fallback in _resolve_place
    - In `slaktbusken/gedcom/importer.py`, modify `_resolve_place` to handle single-word PLAC values
    - When `map_place` returns `None` for a single-word place: store raw place string on the event (create minimal Place record or use raw_place field)
    - Log a structured warning with person, event type, and raw PLAC value
    - Do NOT silently drop the place
    - _Bug_Condition: input.placValue IS single_word AND placeDropped(input.event)_
    - _Expected_Behavior: event.place IS NOT None OR event.raw_place == raw_value_
    - _Preservation: Multi-word PLAC values ("Falun, Dalarna, Sverige") continue to normalize correctly_
    - _Requirements: 2.4, 3.3_

- [ ] 7. Fix Bug 5: Structured import warnings

  - [ ] 7.1 Introduce WarningEntry dataclass and structured warning generation
    - Create a `WarningEntry` dataclass (or structured dict) with fields: gedcom_file, record_xref, person_or_family_name, event_type, raw_value, reason, action_taken
    - Replace free-text `self._warnings.append(...)` calls with structured `WarningEntry` instances
    - Update `format_result` and report rendering to include all structured fields
    - Ensure each warning in the report shows: GEDCOM file, xref (@I10@), person/family name, event type, raw GEDCOM value, reason, and action taken
    - _Bug_Condition: input.warnings.any(w => w.lacksStructuredDetail())_
    - _Expected_Behavior: warning.xref IS NOT None AND warning.reason IS NOT None AND all required fields present_
    - _Preservation: Clean imports with no issues produce no warnings (no false positives from new warning system)_
    - _Requirements: 2.5, 3.5_

- [ ] 8. Verify all fixes pass exploration and preservation tests

  - [ ] 8.1 Verify bug condition exploration tests now pass
    - **Property 1: Expected Behavior** - GEDCOM Update Import Defects Fixed
    - **IMPORTANT**: Re-run the SAME tests from task 1 — do NOT write new tests
    - The tests from task 1 encode the expected behavior for all 5 bugs
    - When these tests pass, it confirms all bugs are fixed:
      - Bug 1: format_result returns all-Swedish text
      - Bug 2: No duplicate events after reimport
      - Bug 3: Events are isolated per INDI record
      - Bug 4: Single-word places are preserved
      - Bug 5: Warnings contain full structured detail
    - Run bug condition exploration tests from step 1
    - **EXPECTED OUTCOME**: Tests PASS (confirms all bugs are fixed)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [ ] 8.2 Verify preservation tests still pass
    - **Property 2: Preservation** - Existing GEDCOM Import Behavior Still Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm: full initial import still works, multi-word places still normalize, unchanged events still untouched, new persons still created correctly, clean imports still produce no warnings
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [ ] 9. Checkpoint - Ensure all tests pass
  - Run full test suite including both bug condition and preservation tests
  - Verify no regressions in existing tests
  - Ensure all tests pass, ask the user if questions arise

## Notes

- GEDCOM test fixtures at `tests/fixtures/gedcom/` (Test-1 through Test-4) provide real-world incremental update scenarios from MinSläkt export
- Test-1: Base with 3 persons (Stina, Anders, Bettan) + 1 family
- Test-2: Adds Sune (Anders' father), marriage event on F1, FAMC link on Anders
- Test-3: Adds Rut, Lena, name change on Stina, xref renumbering
- Test-4: Adds Stina's parents, more xref changes
- Test-5 and Test-6 are planned but not yet available
- Primary files to modify: `slaktbusken/gedcom/importer.py`, `slaktbusken/services/import_service.py`
- Property-based tests use Hypothesis for stronger coverage guarantees
- Each bug fix is isolated to minimize regression risk
- The 5 bugs are independent but share the same importer codebase, so interaction effects must be verified

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1", "2"] },
    { "id": 1, "tasks": ["3.1", "4.1", "5.1", "6.1", "7.1"] },
    { "id": 2, "tasks": ["8.1", "8.2"] },
    { "id": 3, "tasks": ["9"] }
  ]
}
```
