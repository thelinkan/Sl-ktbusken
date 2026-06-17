# Implementation Plan: Primary Name Asterisk (Tilltalsnamn)

## Overview

Implement the Swedish genealogy convention of marking a person's tilltalsnamn with an asterisk. The implementation starts with a pure parsing module, adds rendering with underline in Person Box and Person List Panel, ensures transparent search/filter, and adds editor validation. Each step builds incrementally on the previous.

## Tasks

- [x] 1. Create name parser module with core parsing logic
  - [x] 1.1 Create `slaktbusken/model/name_parser.py` with `ParsedGivenName` dataclass and `parse_given_name` function
    - Define the `ParsedGivenName` frozen dataclass with fields: `parts`, `tilltalsnamn_index`, `display_string`, `raw`
    - Implement `parse_given_name(given: str) -> ParsedGivenName` that splits on whitespace, detects trailing `*` on name parts, raises `ValueError` if more than one marker found
    - Handle edge cases: empty string, single name, embedded asterisks (e.g., "O*Brien" treated as literal)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.7_

  - [x] 1.2 Implement `format_given_name` and `validate_given_name_markers` in `slaktbusken/model/name_parser.py`
    - Implement `format_given_name(parsed: ParsedGivenName) -> str` that reconstructs the raw string by appending `*` after the tilltalsnamn part
    - Implement `validate_given_name_markers(given: str) -> list[str]` that checks for multiple markers, standalone `*`, leading `*`, whitespace-preceded `*`
    - Return descriptive error messages for each validation failure
    - _Requirements: 1.6, 1.7, 5.4, 5.5_

  - [x] 1.3 Write property tests for name parser (Properties 1–6)
    - **Property 1: Correct Tilltalsnamn Identification**
    - **Property 2: No-Marker Returns None**
    - **Property 3: Embedded Asterisks Are Literal**
    - **Property 4: Parse-Format Round Trip**
    - **Property 5: Multiple Markers Rejected**
    - **Property 6: Malformed Markers Rejected**
    - Create `tests/test_model/test_name_parser.py` with Hypothesis strategies and `@settings(max_examples=200)`
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.6, 1.7, 5.4, 5.5**

  - [x] 1.4 Write example-based unit tests for name parser
    - Create `tests/test_model/test_name_parser_examples.py`
    - Test "Kent Torbjörn*" → tilltalsnamn="Torbjörn", index=1
    - Test "Anna*" → tilltalsnamn="Anna", index=0
    - Test "Erik Johan" → tilltalsnamn=None
    - Test empty string → empty parts, None index
    - Test "Karl* Erik*" → raises ValueError
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.7_

- [x] 2. Checkpoint - Ensure parser tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Integrate name parser into Person Box rendering
  - [x] 3.1 Update view layer `_build_display_data` to include parsed name
    - In `slaktbusken/ui/views/family_view.py`, `ancestry_view.py`, and `descendants_view.py`, call `parse_given_name()` on `Name.given` and store result under `"name_parsed"` key in display_data
    - Handle parsing errors gracefully (fall back to raw string without underline)
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.2 Update `PersonBoxItem.paint()` in `slaktbusken/ui/widgets/person_box.py` to render tilltalsnamn with underline
    - Read `display_data["name_parsed"]` in the paint method
    - If `tilltalsnamn_index` is present, draw the name line with selective underline using `QFont.setUnderline(True)` only for the tilltalsnamn segment
    - If no marker or parse failure, render all names without underline (existing behaviour)
    - Ensure the raw asterisk is never displayed
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 3.3 Write unit tests for Person Box tilltalsnamn rendering
    - Add tests to `tests/test_ui/` verifying PersonBoxItem renders underline for marked name
    - Test no-marker case renders without underline
    - Test multiple markers case underlines only first marked part
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 4. Integrate name parser into Person List Panel
  - [x] 4.1 Extend `PersonDisplayInfo` and update `PersonListPanel` to use parsed name
    - Add `tilltalsnamn_index: int | None` field to `PersonDisplayInfo`
    - Update `_format_person_display` to use `parse_given_name()` and store clean display_string in the `given` field for sorting/filtering
    - Store `tilltalsnamn_index` from parsed result
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.4_

  - [x] 4.2 Render tilltalsnamn with HTML underline in Person List Panel
    - Use `QLabel` as item widget with HTML `<u>` tags around the tilltalsnamn part
    - Render non-tilltalsnamn parts without underline
    - Ensure raw asterisk is never displayed in the list
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [x] 4.3 Update filter logic to use clean name (asterisk removed)
    - Ensure `filter_persons` matches against `display_string` (asterisk removed) using case-insensitive substring matching
    - Ensure literal asterisk in search term is treated as a literal character
    - Ensure sorting uses clean given name
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 4.4 Write property tests for filter and sort (Properties 7–8)
    - **Property 7: Filter Matches on Clean Name**
    - **Property 8: Sort Uses Clean Name**
    - Add to `tests/test_model/test_name_parser.py` or `tests/test_ui/test_person_list_filter.py`
    - **Validates: Requirements 4.1, 4.4**

  - [x] 4.5 Write example-based unit tests for Person List Panel rendering and filtering
    - Add tests to `tests/test_ui/test_person_list_filter.py`
    - Test search for "Torbjörn" finds "Kent Torbjörn*"
    - Test search for "Kent" finds "Kent Torbjörn*"
    - Test literal asterisk in search term
    - _Requirements: 4.1, 4.2, 4.3, 4.5_

- [x] 5. Checkpoint - Ensure all rendering and filter tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Add editor validation for asterisk markers
  - [x] 6.1 Integrate `validate_given_name_markers` into `PersonEditor` save flow
    - In `slaktbusken/ui/editors/person_editor.py`, call `validate_given_name_markers()` on the given-name input field before saving
    - If validation fails, display the first error via `_update_status()`, switch to the Names tab, and abort save
    - Ensure the raw asterisk remains visible in the editor input field
    - Enforce maximum 100 characters for the given-name input field
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 6.2 Write unit tests for editor validation
    - Add tests to `tests/test_ui/test_person_editor.py`
    - Test that multiple markers triggers validation error and blocks save
    - Test that malformed marker triggers validation error and blocks save
    - Test that valid single marker allows save
    - Test that given-name field is limited to 100 characters
    - _Requirements: 5.1, 5.4, 5.5_

- [x] 7. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The `name_parser.py` module is pure Python with no Qt dependency, enabling straightforward testing
- All UI rendering uses the structured `ParsedGivenName` result — no ad-hoc asterisk stripping

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["1.3", "1.4"] },
    { "id": 3, "tasks": ["3.1", "4.1"] },
    { "id": 4, "tasks": ["3.2", "4.2", "4.3", "6.1"] },
    { "id": 5, "tasks": ["3.3", "4.4", "4.5", "6.2"] }
  ]
}
```
