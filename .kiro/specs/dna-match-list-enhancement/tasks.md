# Implementation Plan: DNA Match List Enhancement

## Overview

Enhance the DNA match list in the DnaEditor to display both persons' names (resolved via DnaMatch → DnaProfile → Person) and add a text-based person filter. Implementation follows a pure-function extraction pattern: testable logic lives in a new `dna_match_display.py` module, while the UI layer wires it into the existing `DnaEditor`.

## Tasks

- [ ] 1. Create pure logic module for name resolution and match formatting
  - [ ] 1.1 Create `slaktbusken/ui/dna_match_display.py` with `resolve_person_display_name` function
    - Implement the resolution chain: profile_id → DnaProfile → person_id → Person → names[0] → "given surname"
    - Implement fallbacks: profile not found → return profile_id, person not found → return person_id, names empty or first entry both fields empty → return "(okänd)"
    - _Requirements: 1.2, 1.3, 1.4, 1.5_

  - [ ] 1.2 Add `format_match_entry` function to `slaktbusken/ui/dna_match_display.py`
    - Format output as "{Person1} – {Person2}: {shared_cm} cM ({segment_count} segment)"
    - Use en-dash (U+2013) surrounded by spaces between names
    - Format shared_cm to one decimal place
    - _Requirements: 1.1_

  - [ ] 1.3 Add `matches_filter` function to `slaktbusken/ui/dna_match_display.py`
    - Accept list of DnaMatch, filter_text string, and ProjectData
    - Return only matches where filter_text is a case-insensitive substring of either resolved person display name
    - Return all matches when filter_text is empty
    - _Requirements: 2.3, 2.4, 2.5, 2.6_

  - [ ] 1.4 Write property test for name resolution and format correctness
    - **Property 1: Name Resolution and Format Correctness**
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**
    - Create `tests/test_ui/test_dna_match_display_property.py`
    - Generate DnaMatch, DnaProfile, Person instances with Hypothesis
    - Assert format_match_entry output contains en-dash separator, correct names from resolve_person_display_name, and correctly formatted cM value

  - [ ] 1.5 Write property test for filter correctness
    - **Property 2: Filter Correctness**
    - **Validates: Requirements 2.3, 2.4, 2.5, 2.6**
    - Assert matches_filter returns exactly those matches where filter_text.lower() is substring of either resolved person display name
    - Assert empty filter_text returns all matches

- [ ] 2. Checkpoint - Ensure pure logic tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. Integrate filter widget and updated display into DnaEditor UI
  - [ ] 3.1 Add `QLineEdit` filter widget to the matches tab UI
    - Add `self.match_filter_input = QLineEdit` to `Ui_DnaEditor` in `slaktbusken/ui/generated/ui_dna_editor.py`
    - Set placeholder text to "Filtrera på person…"
    - Insert into `matches_left_layout` before the matches list widget
    - _Requirements: 2.1, 2.2_

  - [ ] 3.2 Modify `DnaEditor._refresh_matches_list` to use new formatting and filter
    - Import `format_match_entry`, `matches_filter` from `dna_match_display`
    - Read current filter text from `self._ui.match_filter_input`
    - Apply `matches_filter` to get filtered list of matches
    - Use `format_match_entry` for each match item display text
    - Preserve filter text across refreshes (do not clear the input)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 3.3_

  - [ ] 3.3 Connect filter signal and add refresh handler
    - Connect `self._ui.match_filter_input.textChanged` signal to a new `_on_match_filter_changed` slot
    - `_on_match_filter_changed` calls `_refresh_matches_list` to re-apply the filter
    - Ensure existing data-change refresh paths (add/remove/save match) continue to call `_refresh_matches_list`
    - _Requirements: 2.3, 2.4, 2.5, 3.1, 3.2, 3.4, 3.5_

  - [ ] 3.4 Write property test for filter consistency after data change
    - **Property 3: Filter Consistency After Data Change**
    - **Validates: Requirements 3.1, 3.2, 3.4, 3.5**
    - Simulate add/remove/modify of a DnaMatch with an active filter
    - Assert displayed list equals fresh application of matches_filter to current data

  - [ ] 3.5 Write property test for filter text preservation on refresh
    - **Property 4: Filter Text Preservation on Refresh**
    - **Validates: Requirements 3.3**
    - Set filter text, trigger data-change refresh, assert filter text unchanged

  - [ ] 3.6 Write unit tests for UI integration
    - Test placeholder text is "Filtrera på person…"
    - Test QLineEdit is positioned above the list widget in the layout
    - Test shared_cm formatting edge cases: 7.0 → "7.0", 15.333 → "15.3", 100.0 → "100.0"
    - _Requirements: 2.2_

- [ ] 4. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The project already uses Hypothesis for property-based testing (reuse existing strategies from `tests/conftest.py`)
- Pure logic module enables testing without Qt widget instantiation

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["1.4", "1.5"] },
    { "id": 3, "tasks": ["3.1"] },
    { "id": 4, "tasks": ["3.2", "3.3"] },
    { "id": 5, "tasks": ["3.4", "3.5", "3.6"] }
  ]
}
```
