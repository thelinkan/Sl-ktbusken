# Implementation Plan: Redigera Person Media

## Overview

This implementation extends Släktbusken's PersonEditor with parent relationship management, name-event linking, a dedicated photo tab with type categorization and person lists, file management, event-specific media for death/funeral events, and data model preparation for future image annotation. The plan builds incrementally: data model changes first, then service layer, then UI integration.

## Tasks

- [x] 1. Data model updates and serialization
  - [x] 1.1 Add `mentioned_names` and `annotations` fields to MediaItem and create Annotation dataclass
    - Add `mentioned_names: list[str] = field(default_factory=list)` to `MediaItem`
    - Create `Annotation` dataclass with fields: x, y, width, height, entity_type, entity_id (all floats 0.0–1.0 for coordinates, strings for entity refs)
    - Add `annotations: list[Annotation] = field(default_factory=list)` to `MediaItem`
    - _Requirements: 6.1, 5.3_

  - [x] 1.2 Update serialization layer for new fields
    - Register `(MediaItem, "annotations"): Annotation` in `_NESTED_LIST_TYPES`
    - Ensure `mentioned_names` serializes as list of strings (handled by existing logic)
    - Implement "omit when empty" for annotations field in serialization output
    - _Requirements: 6.3, 6.4_

  - [x] 1.3 Update validators with new parentage type and media types
    - Add `"donation"` to `_VALID_PARENTAGE_TYPES` set
    - Add death event media types (`"dödruna"`, `"dödsannons"`, `"bouppteckning"`, `"dödsbevis"`) and funeral event media types (`"begravningsprogram"`, `"minnesord"`) to `_VALID_MEDIA_TYPES`
    - Add validation for annotations count (max 100 per MediaItem)
    - Add title length validation (1–200 characters)
    - _Requirements: 1.3, 6.5, 9.7_

  - [x] 1.4 Write property test for Annotation serialization round-trip
    - **Property 14: Annotation serialization round-trip**
    - **Validates: Requirements 6.3, 6.4**

  - [x] 1.5 Write property test for Annotation count validation
    - **Property 15: Annotation count validation**
    - **Validates: Requirements 6.5**

  - [x] 1.6 Write property test for title length validation
    - **Property 18: Title length validation**
    - **Validates: Requirements 9.7**

- [x] 2. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Implement ParentService
  - [x] 3.1 Create ParentService class with core logic
    - Create `slaktbusken/services/parent_service.py`
    - Implement `ParentInfo` dataclass
    - Implement `get_parents_for_person` to retrieve all parent links for a person
    - Implement `validate_add` checking duplicate and max-parent constraints
    - Implement `add_parent` with Family lookup/creation logic
    - Implement `update_parentage_type` to change an existing link's type
    - Implement `remove_parent` to remove a ParentChildLink from the Family
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11_

  - [x] 3.2 Write property test for parent relationship creation
    - **Property 1: Parent relationship creation produces correct structures**
    - **Validates: Requirements 1.4, 1.5, 1.6**

  - [x] 3.3 Write property test for parentage type update
    - **Property 2: Parentage type update changes only the type field**
    - **Validates: Requirements 1.7**

  - [x] 3.4 Write property test for parent removal preserving other links
    - **Property 3: Parent relationship removal preserves other links**
    - **Validates: Requirements 1.8**

  - [x] 3.5 Write property test for maximum two parents per parentage type
    - **Property 4: Maximum two parents per parentage type validation**
    - **Validates: Requirements 1.9**

  - [x] 3.6 Write property test for duplicate parent detection
    - **Property 5: Duplicate parent relationship detection**
    - **Validates: Requirements 1.11**

- [x] 4. Implement PhotoService
  - [x] 4.1 Create PhotoService class with file and title logic
    - Create `slaktbusken/services/photo_service.py`
    - Implement `ALLOWED_EXTENSIONS` and `FOTO_TYPES` constants
    - Implement `validate_file_extension` to check file extensions
    - Implement `compute_target_path` to determine if copy needed and compute relative path
    - Implement `resolve_filename_conflict` to generate unique filenames with numeric suffix
    - Implement `format_title` and `parse_title` for `[Foto_Typ] title` formatting/parsing
    - Implement `get_photos_for_person` returning filtered and sorted MediaItems
    - Implement `sync_linked_entities` to synchronize Linked_Entity records with mentioned_person_ids
    - _Requirements: 3.2, 3.4, 3.5, 3.6, 3.8, 4.1, 4.2, 4.5, 5.5, 5.6_

  - [x] 4.2 Write property test for Foto_Typ title format round-trip
    - **Property 9: Foto_Typ title format round-trip**
    - **Validates: Requirements 3.4, 3.5, 3.6, 9.2, 9.3**

  - [x] 4.3 Write property test for file extension validation
    - **Property 10: File extension validation**
    - **Validates: Requirements 3.8**

  - [x] 4.4 Write property test for relative path computation
    - **Property 11: Relative path computation**
    - **Validates: Requirements 4.1, 4.2**

  - [x] 4.5 Write property test for filename deduplication
    - **Property 12: Filename deduplication produces unique names**
    - **Validates: Requirements 4.5**

  - [x] 4.6 Write property test for photo list filtering and ordering
    - **Property 8: Photo list filtering and ordering**
    - **Validates: Requirements 3.2**

  - [x] 4.7 Write property test for mentioned persons synchronization
    - **Property 13: Mentioned persons synchronization with Linked_Entity**
    - **Validates: Requirements 5.2, 5.4, 5.5, 5.6, 9.4, 9.5**

- [x] 5. Implement EventMediaService
  - [x] 5.1 Create EventMediaService class
    - Create `slaktbusken/services/event_media_service.py`
    - Implement `DEATH_MEDIA_TYPES` and `FUNERAL_MEDIA_TYPES` constants
    - Implement `get_media_types_for_event` mapping event type to allowed media types
    - Implement `add_media_to_event` creating Linked_Entity and updating event's media_ids
    - Implement `remove_media_from_event` unlinking without deleting MediaItem
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 8.1, 8.2, 8.3, 8.4_

  - [x] 5.2 Write property test for event media linking
    - **Property 16: Event media linking creates correct structures**
    - **Validates: Requirements 7.3, 8.3**

  - [x] 5.3 Write property test for event media unlinking
    - **Property 17: Event media unlinking preserves MediaItem**
    - **Validates: Requirements 7.4, 8.4**

- [x] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement name-event linking logic
  - [x] 7.1 Add event filtering and name-event association helpers
    - Add helper function to filter events where person is participant
    - Add logic to set/clear event_id on Name records
    - Handle orphaned event_id references gracefully (event no longer exists)
    - _Requirements: 2.1, 2.2, 2.4, 2.5, 2.7_

  - [x] 7.2 Write property test for event filter
    - **Property 6: Event filter returns only events with person as participant**
    - **Validates: Requirements 2.5**

  - [x] 7.3 Write property test for name event_id association round-trip
    - **Property 7: Name event_id association round-trip**
    - **Validates: Requirements 2.2, 2.4**

- [x] 8. Implement FotoTab UI widget
  - [x] 8.1 Create FotoTab widget with photo list display
    - Create `slaktbusken/widgets/foto_tab.py`
    - Implement QWidget subclass with photo list (QListWidget or QTableWidget)
    - Display photos filtered and ordered by PhotoService, showing Foto_Typ label and title separately
    - Show empty state message when no photos linked
    - _Requirements: 3.1, 3.2, 3.5, 3.7_

  - [x] 8.2 Implement photo addition flow in FotoTab
    - Add "Lägg till foto" button opening file dialog with extension filter
    - Integrate PhotoService for file validation, path computation, and copy
    - Show file conflict dialog (overwrite / rename / cancel) when needed
    - Create Foto_Mapp directory if it doesn't exist
    - Create MediaItem with correct type, file path, and formatted title
    - Handle I/O errors with error dialog
    - _Requirements: 3.3, 3.8, 3.9, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

  - [x] 8.3 Implement photo metadata editing in FotoTab
    - Show editable fields (title, Foto_Typ dropdown) when photo selected
    - Validate title length (1–200 chars) before save
    - Update MediaItem title with new `[Foto_Typ] title` format on save
    - Display status bar messages for validation errors
    - _Requirements: 9.1, 9.2, 9.3, 9.7, 9.8_

  - [x] 8.4 Implement person list management in FotoTab
    - Display mentioned persons (database-linked by name, free-text entries as plain text)
    - Add searchable dropdown for selecting existing persons from the database
    - Add free-text input for non-database persons (max 200 chars)
    - Implement add/remove for both person types with duplicate detection
    - Sync mentioned_person_ids with Linked_Entity on save via PhotoService
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 9.4, 9.5, 9.6_

- [x] 9. Integrate parent relationship section into PersonEditor
  - [x] 9.1 Add parent relationship section to PersonEditor
    - Add "Föräldrar" section to the first tab of PersonEditor
    - Display current parents with name and Swedish parentage type label
    - Add "Lägg till förälder" button with searchable person dropdown and parentage type selection
    - Add edit (change parentage type) and remove buttons per parent row
    - Wire add/edit/remove actions to ParentService methods
    - Show validation error messages in status bar
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11_

- [x] 10. Integrate name-event linking UI into PersonEditor
  - [x] 10.1 Add event association control to names table
    - Add event_id dropdown column/control to names table for non-birth name types
    - Populate dropdown with events where person is participant (using helper from 7.1)
    - Display event type and date for linked events
    - Handle orphaned event_id (show warning, allow clearing)
    - Disable control and show info when no events available
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

- [x] 11. Integrate FotoTab into PersonEditor
  - [x] 11.1 Add FotoTab as a new tab in PersonEditor
    - Instantiate PhotoService with project_data and foto_mapp path
    - Create FotoTab widget and add it as "Foton" tab in the tabbed interface
    - Wire FotoTab save signals to PersonEditor's save flow
    - _Requirements: 3.1_

- [x] 12. Integrate event media section into EventEditor
  - [x] 12.1 Add media section to EventEditor for death and funeral events
    - Add conditional media section (visible only for event types "death" and "funeral")
    - Use EventMediaService to determine allowed media types per event type
    - Implement file selection and title input for adding media
    - Display linked media items showing type and title
    - Implement remove action (unlink only, preserve MediaItem)
    - Disable save when file or title missing, show indication of missing fields
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

- [x] 13. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The implementation language is Python (PySide6/Qt), matching the existing codebase
- Service layer tasks (3, 4, 5, 7) are pure logic with no UI dependencies, making them independently testable
- UI tasks (8, 9, 10, 11, 12) build on the services and can be done after service logic is solid

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["1.4", "1.5", "1.6"] },
    { "id": 2, "tasks": ["3.1", "4.1", "5.1", "7.1"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.4", "3.5", "3.6", "4.2", "4.3", "4.4", "4.5", "4.6", "4.7", "5.2", "5.3", "7.2", "7.3"] },
    { "id": 4, "tasks": ["8.1", "9.1", "10.1"] },
    { "id": 5, "tasks": ["8.2", "8.3", "8.4", "11.1", "12.1"] }
  ]
}
```
