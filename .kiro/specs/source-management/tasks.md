# Implementation Plan: Source Management

## Overview

This plan implements the source management feature in incremental steps, starting with data model extensions, then core logic/services, then UI components, and finally wiring everything together. Each task builds on previous work to ensure no orphaned code. The implementation uses Python with PySide6 following existing project patterns.

## Tasks

- [x] 1. Data model extensions
  - [x] 1.1 Add Leverantor and Kalltyp dataclasses to model/source.py
    - Create `Leverantor` dataclass with fields: id (str), name (str), comment (str, default "")
    - Create `Kalltyp` dataclass with fields: id (str), leverantor_id (str), name (str), comment (str, default ""), root_url (str, default "")
    - Add fields to `Source` dataclass: leverantor_id (str, default ""), kalltyp_id (str, default ""), arkivreferens (str, default "")
    - _Requirements: 1.1, 2.1, 10.1_

  - [x] 1.2 Extend SourceRef with aspects field in model/event.py
    - Add `aspects: list[str] = field(default_factory=list)` to `SourceRef` dataclass
    - Ensure serialization/deserialization handles the new field (backward-compatible with existing data lacking the field)
    - _Requirements: 9.1, 9.3_

  - [x] 1.3 Extend ProjectData with leverantorer and kalltyper lists in model/project.py
    - Add `leverantorer: list[Leverantor] = field(default_factory=list)` to `ProjectData`
    - Add `kalltyper: list[Kalltyp] = field(default_factory=list)` to `ProjectData`
    - Ensure import of Leverantor and Kalltyp in the module
    - _Requirements: 1.1, 2.1, 3.1_

  - [x] 1.4 Write property test for SourceRef aspects serialization round-trip
    - **Property 16: Aspect persistence round-trip**
    - **Validates: Requirements 9.3**

- [x] 2. Validation and core logic
  - [x] 2.1 Implement name validation function
    - Create a validation module or extend existing validation with `validate_name(value: str, max_length: int = 100) -> tuple[bool, str]`
    - Accept if stripped value is non-empty and ≤ max_length characters
    - Reject empty/whitespace-only strings with "Namn krävs."
    - Reject strings > max_length with "Namn får vara högst {max_length} tecken."
    - Also implement comment validation (max 500 chars) and root_url validation (max 2048 chars)
    - _Requirements: 1.2, 1.3, 2.2_

  - [x] 2.2 Write property test for name validation
    - **Property 1: Name validation for Leverantör and Källtyp**
    - **Validates: Requirements 1.2, 1.3, 2.2**

  - [x] 2.3 Implement Källtyp name uniqueness check
    - Function `is_kalltyp_name_unique(leverantor_id: str, name: str, kalltyper: list[Kalltyp], exclude_id: str = "") -> bool`
    - Case-sensitive comparison within same Leverantör
    - _Requirements: 2.7_

  - [x] 2.4 Write property test for Källtyp name uniqueness within Leverantör
    - **Property 5: Källtyp name uniqueness within Leverantör**
    - **Validates: Requirements 2.7**

  - [x] 2.5 Implement deletion logic with reference checks
    - Function to check if a Leverantör is referenced by any Source (via `leverantor_id`)
    - Function to check if a Källtyp is referenced by any Source (via `kalltyp_id`)
    - Function for cascade delete of unreferenced Leverantör (removes Leverantör + all its Källtyper)
    - _Requirements: 1.6, 1.7, 1.8, 1.9, 2.5, 2.6_

  - [x] 2.6 Write property test for referenced entities cannot be deleted
    - **Property 2: Referenced entities cannot be deleted**
    - **Validates: Requirements 1.6, 2.5**

  - [x] 2.7 Write property test for cascade delete removes all associated Källtyper
    - **Property 3: Cascade delete removes all associated Källtyper**
    - **Validates: Requirements 1.8**

  - [x] 2.8 Write property test for Källtyp filtering by Leverantör
    - **Property 4: Källtyp filtering by Leverantör**
    - **Validates: Requirements 2.1**

- [ ] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Reference parsing module
  - [x] 4.1 Create parsing/reference_parser.py with ParsedReference dataclass and entry point
    - Define `ParsedReference` dataclass with fields: leverantor_name, kalltyp_name, title, reference_text, structured_fields, arkivreferens
    - Implement `parse_reference(text: str) -> Optional[ParsedReference]` that delegates to sub-parsers
    - Define `CHURCH_BOOK_SERIES_LABELS` mapping from series codes to Källtyp names
    - _Requirements: 7.1, 7.5, 8.5_

  - [x] 4.2 Implement Arkiv Digital full and short reference patterns
    - Full pattern: `{parish} ({county_code}) {series}:{volume} ({years}) Bild {image} / sid {page} (AID: {aid_ref}, NAD: {nad_ref})`
    - Short pattern: `{description} ({year}) Bild {image} / sid {page} (AID: {aid_ref})`
    - Set leverantor_name to "Arkiv Digital", derive kalltyp_name from series via mapping
    - Format title as "{parish} {series}:{volume} Sida: {page}"
    - Store AID and NAD in structured_fields
    - _Requirements: 7.1, 7.2_

  - [x] 4.3 Write property test for Arkiv Digital church book reference parsing round-trip
    - **Property 9: Arkiv Digital church book reference parsing round-trip**
    - **Validates: Requirements 7.1, 7.2**

  - [x] 4.4 Implement Arkiv Digital census pattern parsing
    - Pattern: `rX.pXXXXX` (r followed by digits, dot, p followed by digits)
    - Set leverantor_name to "Arkiv Digital", kalltyp_name "Folkräkning"
    - Store full matched string as arkivreferens
    - _Requirements: 7.3_

  - [x] 4.5 Write property test for Arkiv Digital census reference parsing
    - **Property 10: Arkiv Digital census reference parsing**
    - **Validates: Requirements 7.3**

  - [x] 4.6 Implement Rötter.se reference parsing
    - Pattern: contains "Sveriges dödbok webb" (case-insensitive) → Leverantör "Rötter.se", Källtyp "Sveriges Dödbok Webb"
    - Pattern: "Sveriges dödbok webb - {record_id}" → extract trimmed record_id as arkivreferens
    - Pattern: `SDB{digit}_{digits}` → Källtyp "Sveriges Dödbok Webb", full match as arkivreferens
    - Multi-line: parse each line independently, return list of ParsedReference results
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [x] 4.7 Write property test for Rötter.se Sveriges Dödbok reference parsing
    - **Property 12: Rötter.se Sveriges Dödbok reference parsing**
    - **Validates: Requirements 8.1, 8.2**

  - [x] 4.8 Write property test for Rötter.se SDB identifier parsing
    - **Property 13: Rötter.se SDB identifier parsing**
    - **Validates: Requirements 8.3**

  - [x] 4.9 Write property test for multi-line reference parsing creates separate sources
    - **Property 14: Multi-line reference parsing creates separate sources**
    - **Validates: Requirements 8.4**

  - [x] 4.10 Write property test for non-matching strings produce no source
    - **Property 11: Non-matching strings produce no source**
    - **Validates: Requirements 7.5, 8.5**

- [x] 5. Source title formatting and utilities
  - [x] 5.1 Implement source title formatting function
    - Function `format_source_title(structured_ref: dict) -> str`
    - Format: "{parish} {series}:{volume} Sida: {page}" when all present
    - Omit "Sida: {page}" when page is empty
    - Omit missing segments and their separators
    - Post-process: trim leading/trailing whitespace, collapse multiple consecutive spaces to single space
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 5.2 Write property test for source title formatting
    - **Property 7: Source title formatting from structured reference**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**

  - [x] 5.3 Implement media filename conflict resolution
    - Function `resolve_filename_conflict(target_name: str, existing_names: set[str]) -> str`
    - Append `_{n}` before extension where n is smallest positive integer producing unique name
    - Preserve original file extension
    - _Requirements: 4.3_

  - [x] 5.4 Write property test for filename conflict resolution
    - **Property 6: Filename conflict resolution**
    - **Validates: Requirements 4.3**

  - [x] 5.5 Implement usage statistics calculation
    - Function to compute event count (events referencing source via date.source_refs or place.source_refs) and person count (distinct participant person_ids across those events)
    - _Requirements: 6.1_

  - [x] 5.6 Write property test for usage statistics calculation
    - **Property 8: Usage statistics calculation**
    - **Validates: Requirements 6.1**

  - [x] 5.7 Implement direct link generation logic
    - Function `generate_direct_link(source: Source, kalltyper: list[Kalltyp]) -> Optional[str]`
    - Return root_url + arkivreferens if Källtyp has root_url and source has arkivreferens
    - Return None otherwise
    - _Requirements: 10.1, 10.3_

  - [x] 5.8 Write property test for direct link generation correctness
    - **Property 17: Direct link generation correctness**
    - **Validates: Requirements 10.1, 10.3**

  - [x] 5.9 Implement event-type-specific aspect mapping
    - Define `EVENT_SOURCE_ASPECTS` dict mapping event types to aspect lists
    - Define `ASPECT_LABELS` dict mapping aspect keys to Swedish display labels
    - Function `get_aspects_for_event_type(event_type: str) -> list[str]`
    - _Requirements: 9.1_

  - [x] 5.10 Write property test for event-type-specific aspect mapping
    - **Property 15: Event-type-specific aspect mapping**
    - **Validates: Requirements 9.1**

- [ ] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Standard Leverantörer initialization
  - [x] 7.1 Define STANDARD_PROVIDERS constant and implement initialization in ProjectService
    - Define `STANDARD_PROVIDERS` data structure with all predefined Leverantörer, Källtyper, and Root_URLs as specified
    - Implement initialization function called during `ProjectService.create_project()`
    - Generate UUIDs for each Leverantör and Källtyp at creation time
    - Ensure initialization only runs on new project creation, NOT when opening existing projects
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

  - [x] 7.2 Write unit tests for standard initialization
    - Verify exact provider names and order after project creation
    - Verify exact Källtyp names and order for each Leverantör
    - Verify Root_URL is set for "Sveriges Dödbok Webb"
    - Verify opening existing project does not re-initialize
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

- [x] 8. ProviderEditor UI
  - [x] 8.1 Create ui/editors/provider_editor.py with ProviderEditor widget
    - Split-panel layout: Leverantör list (top-left), Källtyp sub-list (bottom-left), edit form (right)
    - Buttons "Lägg till", "Ta bort", "Redigera" for Leverantörer
    - Buttons "Lägg till", "Ta bort", "Redigera" for Källtyper
    - Input fields for name, comment, root_url with validation feedback
    - Disable "Ta bort"/"Redigera" when no item is selected
    - Disable "Ta bort" for referenced entities with informational message
    - Cascade delete confirmation prompt for Leverantör with associated Källtyper
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [x] 8.2 Write unit tests for ProviderEditor UI interactions
    - Test dialog opens with correct layout
    - Test buttons enable/disable states
    - Test edit and cancel workflows
    - Test validation error display
    - _Requirements: 1.1, 1.5, 2.3_

- [x] 9. SourceEditor extensions
  - [x] 9.1 Add media attachment functionality to SourceEditor
    - Add "Lägg till media" button
    - Open file chooser filtered to image types (.jpg, .jpeg, .png, .tif, .tiff, .bmp, .gif, .webp) and document types (.pdf, .docx, .rtf, .odt)
    - Copy file to project media directory using filename conflict resolution
    - Create media record with type "photo" for images or "document" for document files, relative path, and title from source title
    - Append media ID to source's media_ids list
    - Handle file copy failure with error message
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 9.2 Add usage statistics display to Source_List
    - Display person count and event count inline with each source list item
    - Show "0" for sources with no referencing events
    - Add detail button/click handler to show usage detail dialog
    - Usage detail dialog lists distinct persons with grouped events
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 9.3 Add direct link display and click handling to SourceEditor
    - Display clickable QLabel with generated URL when conditions are met (Källtyp has root_url, source has arkivreferens)
    - Open URL via QDesktopServices.openUrl() on click
    - Show error indicator if link generation fails
    - Hide link when conditions are not met
    - _Requirements: 10.1, 10.2, 10.3_

  - [x] 9.4 Integrate reference parser into SourceEditor paste/import workflow
    - Call `parse_reference()` when text is pasted into reference input
    - Auto-populate Leverantör, Källtyp, title, referenstext, and arkivreferens from ParsedReference
    - Handle GEDCOM import with "ArkivDigital:" prefix stripping
    - Format title using `format_source_title()` for search result sources
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 7.1, 7.2, 7.3, 7.4, 8.1, 8.2, 8.3, 8.4_

- [x] 10. EventEditor extensions
  - [x] 10.1 Add aspect checkboxes to EventEditor source linking
    - Display checkboxes for aspects relevant to event type using EVENT_SOURCE_ASPECTS mapping
    - Use Swedish labels from ASPECT_LABELS
    - Initial state: all checkboxes unselected when source is first linked
    - Persist selected aspects with SourceRef on save
    - Allow saving with no aspects selected
    - _Requirements: 9.1, 9.2, 9.3_

  - [x] 10.2 Add "Öppna källa" button to EventEditor
    - Display button labeled "Öppna källa" when a linked source is selected in the sources table
    - Open SourceEditor with the linked source pre-selected on button click
    - _Requirements: 9.4_

- [x] 11. Menu integration
  - [x] 11.1 Add "Käll-leverantörer" menu item to Redigera menu
    - Add QAction "Käll-leverantörer..." positioned after "Källöversättningar" in the Redigera menu
    - Connect to `app.show_provider_editor()` method
    - Open ProviderEditor as modal dialog
    - Enable only when a project is open, disable when no project is open
    - _Requirements: 11.1, 11.2, 11.3_

- [ ] 12. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 13. Final integration and wiring
  - [x] 13.1 Wire ProviderEditor into Application class
    - Add `show_provider_editor()` method to Application
    - Instantiate ProviderEditor with current project_data
    - Handle dialog close and data persistence
    - _Requirements: 11.2_

  - [x] 13.2 Ensure persistence of Leverantör/Källtyp data
    - Verify serialization of `leverantorer` and `kalltyper` lists in project save/load
    - Ensure backward compatibility with existing project files (missing fields get defaults)
    - Verify SourceRef.aspects field serialization in event data
    - _Requirements: 3.7, 9.3_

  - [x] 13.3 Write integration tests for full workflow
    - Test GEDCOM import with ArkivDigital sources → parse → Source creation
    - Test save/load project with new Leverantör/Källtyp entities
    - Test QDesktopServices.openUrl called with correct URL (mocked)
    - _Requirements: 7.4, 10.2_

- [ ] 14. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. Bugfix: SDB reference recognition in GEDCOM import
  - [x] 15.1 Fix GEDCOM import to detect SDB patterns and assign Leverantör/Källtyp
    - In `gedcom/translation/source_translation.py`, detect sources with SDB patterns (SDB{digit}_{digits}) or "Sveriges dödbok webb" text
    - Assign leverantor_id matching "Rötter.se" and kalltyp_id matching "Sveriges Dödbok Webb" to the created Source
    - Store the SDB identifier as arkivreferens on the Source
    - _Requirements: 14.1, 14.2_

  - [x] 15.2 Write tests for SDB detection in GEDCOM import
    - Test that a GEDCOM source with "SDB7_12345" in text gets Leverantör "Rötter.se" and Källtyp "Sveriges Dödbok Webb"
    - Test that a GEDCOM source with "Sveriges dödbok webb" in text is correctly recognized
    - _Requirements: 14.1, 14.2_

- [x] 16. Bugfix: Arkiv Digital variant pattern parsing
  - [x] 16.1 Add "Bild:" colon pattern support to reference parser
    - Add regex pattern for `{parish} ({county_code}) {series}:{volume} ({years}) Bild: {image} Sida: {page}`
    - This pattern uses "Bild:" (with colon) and "Sida:" instead of "Bild {N} / sid {N}"
    - Parse identically to the existing full pattern
    - _Requirements: 15.1_

  - [x] 16.2 Add Församlingsbok series code mapping
    - Add "AIIa", "AIIb", and other AII-variant series codes to CHURCH_BOOK_SERIES_LABELS mapping as "Församlingsbok"
    - _Requirements: 15.3_

  - [x] 16.3 Fix GEDCOM import title and reference_text handling
    - When importing ArkivDigital sources: title = formatted title (e.g., "Karlstads stadsförsamling (S) AIIa:7 Sida: 21"), reference_text = full original text (after prefix stripping), provider_ref = empty string
    - Ensure this matches the behavior when pasting (no search match found)
    - _Requirements: 15.2_

  - [x] 16.4 Write tests for variant pattern parsing
    - Test "Ed (S) C:6 (1861-1889) Bild 140 (AID: v5976.b140, NAD: SE/VA/13090)" is parsed as Arkiv Digital, Födelse- och dopbok
    - Test "Karlstads stadsförsamling (S) AIIa:7 (1906-1910) Bild: 350 Sida: 21" is parsed with Källtyp "Församlingsbok"
    - Test title formatting produces correct output for variant patterns
    - _Requirements: 15.1, 15.2, 15.3_

- [x] 17. Bugfix: Leverantör/Källtyp dropdown menus in Source Editor
  - [x] 17.1 Replace provider_input text field with Leverantör QComboBox
    - Replace `provider_input` QLineEdit with a QComboBox populated from `project_data.leverantorer`
    - Add empty first entry (no selection)
    - Store selected leverantor_id when selection changes
    - Pre-select when loading existing source
    - _Requirements: 12.1, 12.4, 12.5_

  - [x] 17.2 Add Källtyp QComboBox filtered by selected Leverantör
    - Add `kalltyp_combo` QComboBox below leverantör combo
    - Populate with Källtyper for the currently selected Leverantör
    - Update contents when Leverantör selection changes
    - Store selected kalltyp_id when selection changes
    - Pre-select when loading existing source
    - _Requirements: 12.2, 12.3, 12.4, 12.5_

  - [x] 17.3 Wire parse/import to select dropdowns instead of setting text
    - When `_apply_parsed_reference` is called, select the matching Leverantör in the dropdown (by name lookup)
    - Trigger Källtyp dropdown update, then select matching Källtyp
    - Remove the old `provider_input.setText()` call
    - _Requirements: 12.6_

  - [x] 17.4 Update _on_save to read from dropdowns
    - Read leverantor_id and kalltyp_id from combo box selections instead of pending fields
    - Ensure the source is saved with correct FK references
    - _Requirements: 12.4_

  - [x] 17.5 Write tests for dropdown behavior
    - Test combo is populated with all Leverantörer
    - Test Källtyp combo updates when Leverantör changes
    - Test save stores correct IDs
    - Test load pre-selects correct items
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

- [x] 18. Bugfix: Arkivreferenser two-column table with multi-provider support
  - [x] 18.1 Redesign Arkivreferenser section as two-column table
    - Replace current single-field arkivreferens with a QTableWidget (columns: "Leverantör", "Referens")
    - Add buttons "Lägg till", "Ta bort", "Redigera" for managing rows
    - Display existing arkivreferenser when loading a source
    - _Requirements: 13.1, 13.4_

  - [x] 18.2 Extend Source data model for multiple arkivreferenser
    - Add `arkivreferenser: list[ArkivReferens]` field to Source (where ArkivReferens has leverantor_name and reference_value)
    - Maintain backward compatibility with existing single `arkivreferens` field
    - Update serialization to handle both old and new format
    - _Requirements: 13.5_

  - [x] 18.3 Update reference parser to produce multiple arkivreferenser
    - When AID and NAD are both present: produce two entries (Arkiv Digital → AID value, Nationell Arkivdatabas → NAD value)
    - When only AID is present: produce one entry (Arkiv Digital → AID value)
    - Update ParsedReference dataclass to carry a list of arkivreferenser
    - _Requirements: 13.2, 13.3_

  - [x] 18.4 Wire arkivreferenser table to save/load
    - On save: persist all rows from the table into the source's arkivreferenser list
    - On load: populate table rows from source's arkivreferenser
    - On parse: populate table from parsed reference arkivreferenser
    - _Requirements: 13.5_

  - [x] 18.5 Write tests for multi-provider arkivreferenser
    - Test "Ed (S) AI:16 (1866-1870) Bild 53 / sid 46 (AID: v10726.b53.s46, NAD: SE/VA/13090)" produces 2 arkivreferens entries
    - Test AID-only reference produces 1 entry
    - Test round-trip persistence of multiple arkivreferenser
    - _Requirements: 13.2, 13.3, 13.5_

- [x] 19. Bugfix: Media viewing in Source Editor
  - [x] 19.1 Add "Visa" button to Länkade media section
    - Add a "Visa" (or "Öppna") button next to the existing remove button
    - When clicked, open the selected media file with the system default application
    - Use QDesktopServices.openUrl with file:// protocol and the full path (project_folder / media.file)
    - Disable button when no media item is selected
    - _Requirements: 16.1, 16.2_

  - [x] 19.2 Write test for media open action
    - Test that clicking "Visa" calls QDesktopServices.openUrl with correct file:// URL (mocked)
    - Test button is disabled when no item is selected
    - _Requirements: 16.1, 16.2_

- [x] 20. Bugfix: Media attachment project folder detection
  - [x] 20.1 Ensure project_folder is always passed to SourceEditor
    - Audit all call sites that instantiate SourceEditor and ensure `project_folder` is passed from the project service
    - In `app.py show_source_editor()`: pass `self.project_service.project_path.parent` as project_folder
    - In EventEditor source creation dialog: pass project_folder
    - _Requirements: 17.1, 17.2_

  - [x] 20.2 Write test for project_folder propagation
    - Test that SourceEditor receives a non-None project_folder when opened from the app with a project loaded
    - _Requirements: 17.1_

- [ ] 21. Checkpoint - Ensure all bugfix tests pass
  - Ensure all tests pass after bugfix tasks, ask the user if questions arise.

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
    { "id": 9, "tasks": ["13.3"] },
    { "id": 10, "tasks": ["15.1", "16.1", "16.2", "16.3", "18.2", "20.1"] },
    { "id": 11, "tasks": ["15.2", "16.4", "17.1", "18.3", "19.1", "20.2"] },
    { "id": 12, "tasks": ["17.2", "18.1"] },
    { "id": 13, "tasks": ["17.3", "17.4", "18.4"] },
    { "id": 14, "tasks": ["17.5", "18.5", "19.2"] }
  ]
}
```
