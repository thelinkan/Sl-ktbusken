# Implementation Plan

## Overview

This plan implements the fix for the ArkivDigital reference format equivalence bug using the exploratory bugfix workflow: (1) write tests to confirm the bug on unfixed code, (2) write preservation tests to capture existing correct behavior, (3) implement the fix, and (4) verify all tests pass.

## Tasks

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - ArkivDigital Reference Format Equivalence
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists in `parse_reference()` and `map_gedcom_source()`
  - **Scoped PBT Approach**: Scope the property to concrete failing cases:
    - `"ArkivDigital: Karlstads stadsförsamling (S) AIIa:7 (1906-1910) Bild: 300 Sida: 16"` → assert `leverantor_id` is set to "Arkiv Digital" and `kalltyp_id` is derived from "AIIa" → "Församlingsbok"
    - `"Ed (S) AI:16 (1866-1870) Bild 58 / sid 51 (AID: v10726.b58.s51, NAD: SE/VA/13090)"` → assert `reference_text` does NOT contain "(AID:" or "(NAD:"
    - Assert that prefixed GEDCOM import populates `arkivreferenser` entries when AID/NAD can be derived
    - Assert both colon variant `"Ed (S) AI:16 (1866-1870) Bild: 58 Sida: 51"` and slash variant produce equivalent Leverantör, Källtyp, and title
  - Bug Condition from design: `isBugCondition(input)` = (has_prefix AND leverantor_id NOT assigned) OR (has_aid_nad AND aid_nad_text IN reference_text) OR (colon/slash variants produce different Source records)
  - Expected Behavior from design: prefix stripped → Leverantör = "Arkiv Digital", Källtyp from CHURCH_BOOK_SERIES_LABELS; reference_text excludes AID/NAD parenthetical; arkivreferenser populated when AID/NAD present
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists)
  - Document counterexamples found (e.g., "leverantor_id is empty string", "reference_text contains (AID: v10726...)")
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Non-ArkivDigital Behavior Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - **IMPORTANT**: Write and run these tests BEFORE implementing the fix
  - Observe: `parse_reference()` with non-ArkivDigital strings returns unchanged results on unfixed code
  - Observe: `map_gedcom_source()` with non-ArkivDigital GEDCOM sources assigns no Leverantör/Källtyp on unfixed code
  - Observe: Sveriges Dödbok Webb pattern ("SDB" detection) assigns Leverantör "Rötter.se" and Källtyp "Sveriges Dödbok Webb" on unfixed code
  - Observe: Census pattern `rX.pXXXXX` assigns Leverantör "Arkiv Digital" and Källtyp "Folkräkning" on unfixed code
  - Observe: Existing clipboard full pattern (slash variant) correctly extracts `aid_ref` and `nad_ref` into arkivreferenser on unfixed code
  - Observe: Existing clipboard short pattern (AID only) correctly parses with single arkivreferens on unfixed code
  - Write property-based tests using Hypothesis:
    - Generate random non-ArkivDigital strings → assert `parse_reference()` returns same result before and after fix
    - Generate random GEDCOM source objects without ArkivDigital markers → assert `map_gedcom_source()` output is unchanged
    - Test SDB, census, and no-match patterns produce same results
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 3. Fix for ArkivDigital reference format equivalence

  - [x] 3.1 Strip AID/NAD from reference_text in `parse_arkiv_digital()`
    - In `slaktbusken/parsing/reference_parser.py`, function `parse_arkiv_digital()`
    - For full pattern and short pattern matches, set `reference_text` to the text preceding the `(AID: ...)` parenthesis (trimmed) rather than the full input string
    - For Bild colon pattern, defensively strip any trailing `(AID: ...)` parenthetical if present
    - _Bug_Condition: isBugCondition(input) where has_aid_nad AND aid_nad_text IN reference_text_
    - _Expected_Behavior: reference_text does NOT contain "(AID:" or "(NAD:" — only text preceding parenthesis (trimmed)_
    - _Preservation: Existing arkivreferenser extraction from AID/NAD values must still work correctly_
    - _Requirements: 2.3, 2.4_

  - [x] 3.2 Strip "ArkivDigital:" prefix in `parse_reference()` before pattern matching
    - In `slaktbusken/parsing/reference_parser.py`, function `parse_reference()`
    - At the top of the function, detect and strip "ArkivDigital:" prefix (case-insensitive) before attempting pattern matching
    - This ensures prefixed strings are normalized to the same input as non-prefixed strings
    - _Bug_Condition: isBugCondition(input) where has_prefix AND parsing fails to match known patterns_
    - _Expected_Behavior: prefix stripped, remaining text parsed through standard ArkivDigital patterns, leverantor_name = "Arkiv Digital", kalltyp_name derived from series code_
    - _Preservation: Non-prefixed strings must continue to parse identically_
    - _Requirements: 2.1, 2.2_

  - [x] 3.3 Assign Leverantör ID and Källtyp ID in `map_gedcom_source()` for ArkivDigital sources
    - In `slaktbusken/gedcom/translation/source_translation.py`, function `map_gedcom_source()`
    - When `detect_arkiv_digital()` returns True, invoke `parse_reference()` on the stripped text
    - Use returned `leverantor_name` and `kalltyp_name` to look up corresponding IDs from provided `leverantorer` and `kalltyper` lists
    - Assign these IDs to the Source entity
    - _Bug_Condition: isBugCondition(input) where has_prefix AND leverantor_id NOT assigned AND kalltyp_id NOT assigned_
    - _Expected_Behavior: leverantor_id corresponds to "Arkiv Digital", kalltyp_id derived from series code via CHURCH_BOOK_SERIES_LABELS_
    - _Preservation: Non-ArkivDigital GEDCOM sources must not have their Leverantör/Källtyp assignment modified_
    - _Requirements: 2.1_

  - [x] 3.4 Populate arkivreferenser from parsed result in GEDCOM import
    - In `slaktbusken/gedcom/translation/source_translation.py`, function `map_gedcom_source()`
    - If `parse_reference()` returns arkivreferenser entries (AID and/or NAD), transfer them to the Source entity
    - Store one ArkivReferens for "Arkiv Digital" with AID value, one for "Nationell Arkivdatabas" with NAD value
    - If neither AID nor NAD is present in the text, do not create any arkivreferenser entries
    - _Bug_Condition: isBugCondition(input) where GEDCOM source with AID/NAD values does not populate arkivreferenser_
    - _Expected_Behavior: arkivreferenser populated when AID/NAD present; empty when not present_
    - _Preservation: Existing clipboard/paste arkivreferenser extraction must continue working_
    - _Requirements: 2.3_

  - [x] 3.5 Strip AID/NAD parenthetical in `_derive_reference_text()`
    - In `slaktbusken/gedcom/translation/source_translation.py`, function `_derive_reference_text()`
    - After stripping the "ArkivDigital:" prefix, also strip any trailing `(AID: ...)` or `(AID: ..., NAD: ...)` parenthetical
    - Trim resulting whitespace
    - Use regex pattern `\s*\(AID:\s*[^)]*\)\s*$` to match and remove the suffix
    - _Bug_Condition: isBugCondition(input) where aid_nad_text IN reference_text after _derive_reference_text()_
    - _Expected_Behavior: returned reference_text contains only human-readable text, no machine-readable AID/NAD identifiers_
    - _Preservation: Strings without AID/NAD parenthetical must be returned unchanged (after prefix stripping)_
    - _Requirements: 2.4_

  - [x] 3.6 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - ArkivDigital Reference Format Equivalence
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied:
      - Leverantör ID and Källtyp ID assigned for prefixed sources
      - reference_text does not contain AID/NAD identifiers
      - arkivreferenser populated when AID/NAD present
      - Colon and slash variants produce equivalent output
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 3.7 Verify preservation tests still pass
    - **Property 2: Preservation** - Non-ArkivDigital Behavior Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all preservation tests still pass after fix:
      - Non-ArkivDigital GEDCOM sources import identically
      - SDB detection still assigns "Rötter.se" / "Sveriges Dödbok Webb"
      - Census patterns still produce "Arkiv Digital" / "Folkräkning"
      - Existing clipboard full/short pattern parsing unchanged
      - Unmatched references remain unmodified

- [x] 4. Checkpoint - Ensure all tests pass
  - Run full test suite to confirm no regressions
  - Verify both Property 1 (bug condition) and Property 2 (preservation) tests pass
  - Verify existing unit tests in the project still pass
  - Ensure all tests pass, ask the user if questions arise

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "tasks": ["1", "2"],
      "description": "Write exploration and preservation tests on UNFIXED code"
    },
    {
      "wave": 2,
      "tasks": ["3.1", "3.2", "3.3", "3.4", "3.5"],
      "description": "Implement the fix across reference_parser.py and source_translation.py"
    },
    {
      "wave": 3,
      "tasks": ["3.6", "3.7"],
      "description": "Verify bug condition test passes and preservation tests still pass"
    },
    {
      "wave": 4,
      "tasks": ["4"],
      "description": "Final checkpoint - ensure all tests pass"
    }
  ]
}
```

## Notes

- Tasks 1 and 2 MUST be completed before any implementation work in task 3
- Task 1 is expected to FAIL on unfixed code (confirms the bug exists)
- Task 2 is expected to PASS on unfixed code (captures baseline behavior)
- Implementation sub-tasks (3.1–3.5) can be done in any order but all must complete before verification (3.6, 3.7)
- Uses Hypothesis library for property-based testing (already present in project)
