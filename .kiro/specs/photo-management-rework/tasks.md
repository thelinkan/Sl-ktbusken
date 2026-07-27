# Implementation Plan: Photo Management Rework

## Overview

Rework photo management in Släktbusken by replacing inline editing in FotoTab with a dedicated `EditPhotoDialog`, adding reusable `PhotoSectionWidget` for PlaceEditor/EventEditor, and implementing `PhotoTaggingService` and `PhotoDateValidator` as service-layer components. Implementation proceeds bottom-up: data model changes → services → UI components → integration/wiring.

## Tasks

- [x] 1. Extend data model and create service-layer components
  - [x] 1.1 Add `photo_date` and `notes` fields to MediaItem dataclass
    - Add `photo_date: Optional[dict] = None` and `notes: str = ""` to `slaktbusken/model/media.py`
    - Update serialization in `slaktbusken/persistence/serialization.py` to handle the new fields
    - _Requirements: 4.9, 4.10, 6.3_

  - [x] 1.2 Create `PhotoDateValidator` service
    - Create `slaktbusken/services/photo_date_validator.py` with `PhotoDate` dataclass and `PhotoDateValidator` class
    - Implement `validate()` for flexible precision rules (all-empty, year-only, year+month, full date)
    - Implement `to_storage_format()` and `from_storage_format()` for round-trip conversion
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10_

  - [x] 1.3 Write property test for title validation
    - **Property 1: Title validation accepts valid lengths and rejects invalid**
    - **Validates: Requirements 3.4**

  - [x] 1.4 Write property test for photo date validation correctness
    - **Property 2: Photo date validation correctness**
    - **Validates: Requirements 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8**

  - [x] 1.5 Write property test for photo date storage round-trip
    - **Property 3: Photo date storage round-trip**
    - **Validates: Requirements 4.9, 4.10**

  - [x] 1.6 Create `PhotoTaggingService`
    - Create `slaktbusken/services/photo_tagging_service.py`
    - Implement `get_available_events()` filtering by person participants, excluding already linked
    - Implement `get_available_places()` excluding already linked places
    - Implement `add_event_tag()`, `remove_event_tag()`, `add_place_tag()`, `remove_place_tag()`
    - Implement `get_event_tags()`, `get_place_tags()`, `get_photos_for_place()`, `get_photos_for_event()`
    - _Requirements: 7.3, 7.4, 7.5, 7.6, 7.7, 8.3, 8.4, 8.5, 9.1_

  - [x] 1.7 Write property test for event filtering by linked persons
    - **Property 4: Event filtering by linked persons**
    - **Validates: Requirements 7.4, 7.5**

  - [x] 1.8 Write property test for tag add/remove preserves non-target entities
    - **Property 5: Tag add/remove preserves non-target linked entities**
    - **Validates: Requirements 7.6, 7.7, 8.4, 8.5**

  - [x] 1.9 Write property test for place availability filtering
    - **Property 6: Place availability filtering excludes already linked**
    - **Validates: Requirements 8.3**

  - [x] 1.10 Write property test for photos-for-entity filtering
    - **Property 7: Photos-for-entity filtering**
    - **Validates: Requirements 9.1**

- [x] 2. Checkpoint - Ensure all service-layer tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Build the EditPhotoDialog UI
  - [x] 3.1 Create `EditPhotoDialog` skeleton with sections layout
    - Create `slaktbusken/ui/dialogs/edit_photo_dialog.py`
    - Implement modal QDialog with QScrollArea containing vertical sections in order: "Titel och typ", "Fotodatum", "Personer på fotot", "Händelser", "Platser", "Anteckningar"
    - Add "Spara" and "Avbryt" footer buttons
    - _Requirements: 1.1, 1.2, 1.5_

  - [x] 3.2 Implement "Titel och typ" section in EditPhotoDialog
    - Add QLineEdit for title and QComboBox with photo type options (Porträtt, Gruppfoto, Familjefoto, etc.)
    - Implement title parsing from `[Fototyp] Titel` format on load and composing on save
    - Implement title validation (1–200 chars, not empty/whitespace)
    - No separate "Spara ändringar" button in this section
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 3.3 Implement "Fotodatum" section in EditPhotoDialog
    - Add year (QSpinBox 1–9999), month (QSpinBox 1–12), day (QSpinBox 1–31) input fields allowing empty
    - Integrate `PhotoDateValidator` for inline validation messages
    - Load/save photo date using `PhotoDateValidator.from_storage_format()` / `to_storage_format()`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10_

  - [x] 3.4 Implement "Personer på fotot" section in EditPhotoDialog
    - Add person list with "Lägg till person" and "Ta bort" buttons (left-to-right order)
    - Reuse existing `PersonListWidget` or equivalent pattern for person selection dialog
    - Implement duplicate detection with user message
    - Disable "Ta bort" when no person selected
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8_

  - [x] 3.5 Implement "Händelser" section in EditPhotoDialog
    - Add event list with "Lägg till" and "Ta bort" buttons
    - Implement event selection dialog filtered by persons linked to photo (via `PhotoTaggingService.get_available_events()`)
    - Show empty list when no persons are linked
    - Disable "Ta bort" when no event selected
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

  - [x] 3.6 Implement "Platser" section in EditPhotoDialog
    - Add place list with "Lägg till" and "Ta bort" buttons
    - Implement place selection dialog filtered by `PhotoTaggingService.get_available_places()`
    - Disable "Ta bort" when no place selected
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 3.7 Implement "Anteckningar" section in EditPhotoDialog
    - Add QPlainTextEdit with minimum 3 visible rows and max 2000 character limit
    - Load existing notes on open, save notes content on save
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 3.8 Implement save/cancel logic and validation flow in EditPhotoDialog
    - "Spara" validates all sections; on failure, dialog stays open with error at relevant section
    - "Avbryt" and window close (X) discard changes without modifying MediaItem
    - On successful save, update MediaItem and close dialog
    - _Requirements: 1.3, 1.4, 1.5_

- [x] 4. Checkpoint - Verify EditPhotoDialog functions correctly
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Simplify FotoTab and wire to EditPhotoDialog
  - [x] 5.1 Remove inline editing from FotoTab
    - Remove `_edit_group` (QGroupBox with title/type fields and "Spara ändringar" button)
    - Remove `_person_list_group` (QGroupBox with person list and "Spara personlista" button)
    - Remove `_on_save_metadata()`, `_on_save_persons()`, `flush_pending_person_list()` methods
    - _Requirements: 11.1, 11.2, 11.3_

  - [x] 5.2 Add "Redigera foto" button and update FotoTab button layout
    - Set button order: "Lägg till foto" | "Redigera foto" | "Ta bort foto"
    - "Lägg till foto" always enabled; "Redigera foto" and "Ta bort foto" enabled only when photo selected
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 5.3 Wire FotoTab buttons and double-click to EditPhotoDialog
    - "Redigera foto" click opens EditPhotoDialog with selected MediaItem
    - Double-click on photo row opens EditPhotoDialog
    - Refresh photo list after dialog closes with saved changes
    - _Requirements: 2.5, 11.4, 11.5_

  - [x] 5.4 Write unit tests for FotoTab button states and layout
    - Test button enable/disable based on selection
    - Test that inline editing sections are removed
    - Test double-click opens dialog
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 11.1, 11.2, 11.3, 11.4, 11.5_

- [x] 6. Build PhotoSectionWidget and integrate into PlaceEditor
  - [x] 6.1 Create `PhotoSectionWidget` reusable widget
    - Create `slaktbusken/ui/widgets/photo_section_widget.py`
    - Implement photo list with configurable buttons (view/edit/add/remove)
    - Emit signals: `photo_added`, `photo_edited`
    - Implement `refresh()` to reload from project data
    - _Requirements: 9.1, 9.2, 9.3_

  - [x] 6.2 Integrate PhotoSectionWidget into PlaceEditor
    - Add "Foton" section to PlaceEditor using `PhotoSectionWidget(entity_type="place", entity_id=place.id)`
    - Configure buttons: "Visa foto", "Redigera foto", "Lägg till foto"
    - "Visa foto" opens modal image viewer; "Redigera foto" opens EditPhotoDialog
    - "Lägg till foto" opens file dialog (PNG, JPG, JPEG, BMP, GIF, TIFF), creates MediaItem + LinkedEntity
    - Disable "Visa foto" and "Redigera foto" when no photo selected
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_

  - [x] 6.3 Write property test for new photo creation with linked entity
    - **Property 8: New photo creation produces correct MediaItem and LinkedEntity**
    - **Validates: Requirements 9.6, 10.4**

- [x] 7. Split EventEditor media into "Foton" and "Annan media"
  - [x] 7.1 Replace single "Händelsemedia" section with two sections in EventEditor
    - Add "Foton" section using `PhotoSectionWidget(entity_type="event", entity_id=event.id)` with buttons "Lägg till foto", "Redigera foto", "Ta bort foto"
    - Add "Annan media" section with existing non-photo media logic, buttons "Lägg till media", "Ta bort media"
    - Disable "Redigera foto" and "Ta bort foto" when no photo selected
    - Disable "Ta bort media" when no media object selected
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_

  - [x] 7.2 Write property test for non-photo media type invariant
    - **Property 9: Non-photo media type invariant**
    - **Validates: Requirements 10.7**

- [x] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- All property tests go in `tests/test_services/test_photo_management_rework_properties.py`
- UI tests go in `tests/test_ui/test_edit_photo_dialog.py` and `tests/test_ui/test_foto_tab.py`
- Integration tests go in `tests/test_integration/test_photo_management_integration.py`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4", "1.5", "1.6"] },
    { "id": 2, "tasks": ["1.7", "1.8", "1.9", "1.10"] },
    { "id": 3, "tasks": ["3.1"] },
    { "id": 4, "tasks": ["3.2", "3.3", "3.4", "3.7"] },
    { "id": 5, "tasks": ["3.5", "3.6", "3.8"] },
    { "id": 6, "tasks": ["5.1"] },
    { "id": 7, "tasks": ["5.2", "6.1"] },
    { "id": 8, "tasks": ["5.3", "5.4", "6.2", "6.3"] },
    { "id": 9, "tasks": ["7.1", "7.2"] }
  ]
}
```
