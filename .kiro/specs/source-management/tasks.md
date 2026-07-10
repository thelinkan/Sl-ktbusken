# Implementation Plan: Source Management

## Overview

This plan implements the source management feature in incremental steps, starting with data model extensions, then core logic/services, then UI components, and finally wiring everything together. Each task builds on previous work to ensure no orphaned code. The implementation uses Python with PySide6 following existing project patterns.

## Tasks

- [ ] 1. Data model extensions
  - [ ] 1.1 Add Leverantor and Kalltyp dataclasses to model/source.py
    - Create `Leverantor` dataclass with fields: id (str), name (str), comment (str, default "")
    - Create `Kalltyp` dataclass with fields: id (str), leverantor_id (str), name (str), comment (str, default ""), root_url (str, default "")
    - Add fields to `Source` dataclass: leverantor_id (str, default ""), kalltyp_id (str, default ""), arkivreferens (str, default "")
    - _Requirements: 1.1, 2.1, 10.1_

  - [ ] 1.2 Extend SourceRef with aspects field in model/event.py
    - Add `aspects: list[str] = field(default_factory=list)` to `SourceRef` dataclass
    - Ensure serialization/deserialization handles the new field (backward-compatible with existing data lacking the field)
    - _Requirements: 9.1, 9.3_

  - [ ] 1.3 Extend ProjectData with leverantorer and kalltyper lists in model/project.py
    - Add `leverantorer: list[Leverantor] = field(default_factory=list)` to `ProjectData`
    - Add `kalltyper: list[Kalltyp] = field(default_factory=list)` to `ProjectData`
    - Ensure import of Leverantor and Kalltyp in the module
    - _Requirements: 1.1, 2.1, 3.1_

  - [ ] 1.4 Write property test for SourceRef aspects serialization round-trip
    - **Property 16: Aspect persistence round-trip**
    - **Validates: Requirements 9.3**

- [ ] 2. Validation and core logic
  - [ ] 2.1 Implement name validation function
    - Create a validation module or extend existing validation with `validate_name(value: str, max_length: int = 100) -> tuple[bool, str]`
    - Accept if stripped value is non-empty and ≤ max_length characters
    - Reject empty/whitespace-only strings with "Namn krävs."
    - Reject strings > max_length with "Namn får vara högst {max_length} tecken."
    - Also implement comment validation (max 500 chars) and root_url validation (max 2048 chars)
    - _Requirements: 1.2, 1.3, 2.2_

  - [ ] 2.2 Write property test for name validation
    - **Property 1: Name validation for Leverantör and Källtyp**
    - **Validates: Requirements 1.2, 1.3, 2.2**

  - [ ] 2.3 Implement Källtyp name uniqueness check
    - Function `is_kalltyp_name_unique(leverantor_id: str, name: str, kalltyper: list[Kalltyp], exclude_id: str = "") -> bool`
    - Case-sensitive comparison within same Leverantör
    - _Requirements: 2.7_

  - [ ] 2.4 Write property test for Källtyp name uniqueness within Leverantör
    - **Property 5: Källtyp name uniqueness within Leverantör**
    - **Validates: Requirements 2.7**

  - [ ] 2.5 Implement deletion logic with reference checks
    - Function to check if a Leverantör is referenced by any Source (via `leverantor_id`)
    - Function to check if a Källtyp is referenced by any Source (via `kalltyp_id`)
    - Function for cascade delete of unreferenced Leverantör (removes Leverantör + all its Källtyper)
    - _Requirements: 1.6, 1.7, 1.8, 1.9, 2.5, 2.6_

  - [ ] 2.6 Write property test for referenced entities cannot be deleted
    - **Property 2: Referenced entities cannot be deleted**
    - **Validates: Requirements 1.6, 2.5**

  - [ ] 2.7 Write property test for cascade delete removes all associated Källtyper
    - **Property 3: Cascade delete removes all associated Källtyper**
    - **Validates: Requirements 1.8**

  - [ ] 2.8 Write property test for Källtyp filtering by Leverantör
    - **Property 4: Källtyp filtering by Leverantör**
    - **Validates: Requirements 2.1**

- [ ] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Reference parsing module
  - [ ] 4.1 Create parsing/reference_parser.py with ParsedReference dataclass and entry point
    - Define `ParsedReference` dataclass with fields: leverantor_name, kalltyp_name, title, reference_text, structured_fields, arkivreferens
    - Implement `parse_reference(text: str) -> Optional[ParsedReference]` that delegates to sub-parsers
    - Define `CHURCH_BOOK_SERIES_LABELS` mapping from series codes to Källtyp names
    - _Requirements: 7.1, 7.5, 8.5_

  - [ ] 4.2 Implement Arkiv Digital full and short reference patterns
    - Full pattern: `{parish} ({county_code}) {series}:{volume} ({years}) Bild {image} / sid {page} (AID: {aid_ref}, NAD: {nad_ref})`
    - Short pattern: `{description} ({year}) Bild {image} / sid {page} (AID: {aid_ref})`
    - Set leverantor_name to "Arkiv Digital", derive kalltyp_name from series via mapping
    - Format title as "{parish} {series}:{volume} Sida: {page}"
    - Store AID and NAD in structured_fields
    - _Requirements: 7.1, 7.2_

  - [ ] 4.3 Write property test for Arkiv Digital church book reference parsing round-trip
    - **Property 9: Arkiv Digital church book reference parsing round-trip**
    - **Validates: Requirements 7.1, 7.2**

  - [ ] 4.4 Implement Arkiv Digital census pattern parsing
    - Pattern: `rX.pXXXXX` (r followed by digits, dot, p followed by digits)
    - Set leverantor_name to "Arkiv Digital", kalltyp_name "Folkräkning"
    - Store full matched string as arkivreferens
    - _Requirements: 7.3_

  - [ ] 4.5 Write property test for Arkiv Digital census reference parsing
    - **Property 10: Arkiv Digital census reference parsing**
    - **Validates: Requirements 7.3**

  - [ ] 4.6 Implement Rötter.se reference parsing
    - Pattern: contains "Sveriges dödbok webb" (case-insensitive) → Leverantör "Rötter.se", Källtyp "Sveriges Dödbok Webb"
    - Pattern: "Sveriges dödbok webb - {record_id}" → extract trimmed record_id as arkivreferens
    - Pattern: `SDB{digit}_{digits}` → Källtyp "Sveriges Dödbok Webb", full match as arkivreferens
    - Multi-line: parse each line independently, return list of ParsedReference results
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [ ] 4.7 Write property test for Rötter.se Sveriges Dödbok reference parsing
    - **Property 12: Rötter.se Sveriges Dödbok reference parsing**
    - **Validates: Requirements 8.1, 8.2**

  - [ ] 4.8 Write property test for Rötter.se SDB identifier parsing
    - **Property 13: Rötter.se SDB identifier parsing**
    - **Validates: Requirements 8.3**

  - [ ] 4.9 Write property test for multi-line reference parsing creates separate sources
    - **Property 14: Multi-line reference parsing creates separate sources**
    - **Validates: Requirements 8.4**

  - [ ] 4.10 Write property test for non-matching strings produce no source
    - **Property 11: Non-matching strings produce no source**
    - **Validates: Requirements 7.5, 8.5**

- [ ] 5. Source title formatting and utilities
  - [ ] 5.1 Implement source title formatting function
    - Function `format_source_title(structured_ref: dict) -> str`
    - Format: "{parish} {series}:{volume} Sida: {page}" when all present
    - Omit "Sida: {page}" when page is empty
    - Omit missing segments and their separators
    - Post-process: trim leading/trailing whitespace, collapse multiple consecutive spaces to single space
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ] 5.2 Write property test for source title formatting
    - **Property 7: Source title formatting from structured reference**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**

  - [ ] 5.3 Implement media filename conflict resolution
    - Function `resolve_filename_conflict(target_name: str, existing_names: set[str]) -> str`
    - Append `_{n}` before extension where n is smallest positive integer producing unique name
    - Preserve original file extension
    - _Requirements: 4.3_

  - [ ] 5.4 Write property test for filename conflict resolution
    - **Property 6: Filename conflict resolution**
    - **Validates: Requirements 4.3**

  - [ ] 5.5 Implement usage statistics calculation
    - Function to compute event count (events referencing source via date.source_refs or place.source_refs) and person count (distinct participant person_ids across those events)
    - _Requirements: 6.1_

  - [ ] 5.6 Write property test for usage statistics calculation
    - **Property 8: Usage statistics calculation**
    - **Validates: Requirements 6.1**

  - [ ] 5.7 Implement direct link generation logic
    - Function `generate_direct_link(source: Source, kalltyper: list[Kalltyp]) -> Optional[str]`
    - Return root_url + arkivreferens if Källtyp has root_url and source has arkivreferens
    - Return None otherwise
    - _Requirements: 10.1, 10.3_

  - [ ] 5.8 Write property test for direct link generation correctness
    - **Property 17: Direct link generation correctness**
    - **Validates: Requirements 10.1, 10.3**

  - [ ] 5.9 Implement event-type-specific aspect mapping
    - Define `EVENT_SOURCE_ASPECTS` dict mapping event types to aspect lists
    - Define `ASPECT_LABELS` dict mapping aspect keys to Swedish display labels
    - Function `get_aspects_for_event_type(event_type: str) -> list[str]`
    - _Requirements: 9.1_

  - [ ] 5.10 Write property test for event-type-specific aspect mapping
    - **Property 15: Event-type-specific aspect mapping**
    - **Validates: Requirements 9.1**

- [ ] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Standard Leverantörer initialization
  - [ ] 7.1 Define STANDARD_PROVIDERS constant and implement initialization in ProjectService
    - Define `STANDARD_PROVIDERS` data structure with all predefined Leverantörer, Källtyper, and Root_URLs as specified
    - Implement initialization function called during `ProjectService.create_project()`
    - Generate UUIDs for each Leverantör and Källtyp at creation time
    - Ensure initialization only runs on new project creation, NOT when opening existing projects
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

  - [ ] 7.2 Write unit tests for standard initialization
    - Verify exact provider names and order after project creation
    - Verify exact Källtyp names and order for each Leverantör
    - Verify Root_URL is set for "Sveriges Dödbok Webb"
    - Verify opening existing project does not re-initialize
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

- [ ] 8. ProviderEditor UI
  - [ ] 8.1 Create ui/editors/provider_editor.py with ProviderEditor widget
    - Split-panel layout: Leverantör list (top-left), Källtyp sub-list (bottom-left), edit form (right)
    - Buttons "Lägg till", "Ta bort", "Redigera" for Leverantörer
    - Buttons "Lägg till", "Ta bort", "Redigera" for Källtyper
    - Input fields for name, comment, root_url with validation feedback
    - Disable "Ta bort"/"Redigera" when no item is selected
    - Disable "Ta bort" for referenced entities with informational message
    - Cascade delete confirmation prompt for Leverantör with associated Källtyper
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [ ] 8.2 Write unit tests for ProviderEditor UI interactions
    - Test dialog opens with correct layout
    - Test buttons enable/disable states
    - Test edit and cancel workflows
    - Test validation error display
    - _Requirements: 1.1, 1.5, 2.3_

- [ ] 9. SourceEditor extensions
  - [ ] 9.1 Add media attachment functionality to SourceEditor
    - Add "Lägg till media" button
    - Open file chooser filtered to image types (.jpg, .jpeg, .png, .tif, .tiff, .bmp, .gif, .webp)
    - Copy file to project media directory using filename conflict resolution
    - Create media record with type "photo", relative path, and title from source title
    - Append media ID to source's media_ids list
    - Handle file copy failure with error message
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ] 9.2 Add usage statistics display to Source_List
    - Display person count and event count inline with each source list item
    - Show "0" for sources with no referencing events
    - Add detail button/click handler to show usage detail dialog
    - Usage detail dialog lists distinct persons with grouped events
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ] 9.3 Add direct link display and click handling to SourceEditor
    - Display clickable QLabel with generated URL when conditions are met (Källtyp has root_url, source has arkivreferens)
    - Open URL via QDesktopServices.openUrl() on click
    - Show error indicator if link generation fails
    - Hide link when conditions are not met
    - _Requirements: 10.1, 10.2, 10.3_

  - [ ] 9.4 Integrate reference parser into SourceEditor paste/import workflow
    - Call `parse_reference()` when text is pasted into reference input
    - Auto-populate Leverantör, Källtyp, title, referenstext, and arkivreferens from ParsedReference
    - Handle GEDCOM import with "ArkivDigital:" prefix stripping
    - Format title using `format_source_title()` for search result sources
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 7.1, 7.2, 7.3, 7.4, 8.1, 8.2, 8.3, 8.4_

- [ ] 10. EventEditor extensions
  - [ ] 10.1 Add aspect checkboxes to EventEditor source linking
    - Display checkboxes for aspects relevant to event type using EVENT_SOURCE_ASPECTS mapping
    - Use Swedish labels from ASPECT_LABELS
    - Initial state: all checkboxes unselected when source is first linked
    - Persist selected aspects with SourceRef on save
    - Allow saving with no aspects selected
    - _Requirements: 9.1, 9.2, 9.3_

  - [ ] 10.2 Add "Öppna källa" button to EventEditor
    - Display button labeled "Öppna källa" when a linked source is selected in the sources table
    - Open SourceEditor with the linked source pre-selected on button click
    - _Requirements: 9.4_

- [ ] 11. Menu integration
  - [ ] 11.1 Add "Käll-leverantörer" menu item to Redigera menu
    - Add QAction "Käll-leverantörer..." positioned after "Källöversättningar" in the Redigera menu
    - Connect to `app.show_provider_editor()` method
    - Open ProviderEditor as modal dialog
    - Enable only when a project is open, disable when no project is open
    - _Requirements: 11.1, 11.2, 11.3_

- [ ] 12. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 13. Final integration and wiring
  - [ ] 13.1 Wire ProviderEditor into Application class
    - Add `show_provider_editor()` method to Application
    - Instantiate ProviderEditor with current project_data
    - Handle dialog close and data persistence
    - _Requirements: 11.2_

  - [ ] 13.2 Ensure persistence of Leverantör/Källtyp data
    - Verify serialization of `leverantorer` and `kalltyper` lists in project save/load
    - Ensure backward compatibility with existing project files (missing fields get defaults)
    - Verify SourceRef.aspects field serialization in event data
    - _Requirements: 3.7, 9.3_

  - [ ] 13.3 Write integration tests for full workflow
    - Test GEDCOM import with ArkivDigital sources → parse → Source creation
    - Test save/load project with new Leverantör/Källtyp entities
    - Test QDesktopServices.openUrl called with correct URL (mocked)
    - _Requirements: 7.4, 10.2_

- [ ] 14. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using Hypothesis (already configured in project)
- Unit tests validate specific UI interactions, initialization constants, and edge cases
- The project already uses PySide6 and Hypothesis; no new frameworks needed
- Swedish labels and messages are used throughout to match the application's language

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["1.4", "2.1", "2.3", "5.9"] },
    { "id": 2, "tasks": ["2.2", "2.4", "2.5", "4.1", "5.1", "5.3", "5.5", "5.7", "5.10"] },
    { "id": 3, "tasks": ["2.6", "2.7", "2.8", "4.2", "4.4", "4.6", "5.2", "5.4", "5.6", "5.8"] },
    { "id": 4, "tasks": ["4.3", "4.5", "4.7", "4.8", "4.9", "4.10", "7.1"] },
    { "id": 5, "tasks": ["7.2", "8.1"] },
    { "id": 6, "tasks": ["8.2", "9.1", "9.2", "9.3", "9.4"] },
    { "id": 7, "tasks": ["10.1", "10.2", "11.1"] },
    { "id": 8, "tasks": ["13.1", "13.2"] },
    { "id": 9, "tasks": ["13.3"] }
  ]
}
```
