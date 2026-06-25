# Implementation Plan: Place Editor Enhancements

## Overview

This plan implements four enhancements to the Place Editor: External IDs (key-value pairs for GEDCOM exports), Alternative Names (additional name strings per place), a Red Dot Indicator for places missing a parent, and a Type Filter combo box. The implementation follows a model-first approach, adding data fields and validation before extending the UI.

## Tasks

- [x] 1. Extend the Place model with ExternalId and alternative_names
  - [x] 1.1 Add `ExternalId` dataclass and new fields to `Place` in `slaktbusken/model/place.py`
    - Create `ExternalId` dataclass with `key: str` and `value: str` fields
    - Add `external_ids: list[ExternalId] = field(default_factory=list)` to `Place`
    - Add `alternative_names: list[str] = field(default_factory=list)` to `Place`
    - _Requirements: 1.1, 3.1_

  - [x] 1.2 Add validation functions in `slaktbusken/model/validators.py`
    - Implement `validate_external_id(ext_id)` — key 1–100 chars, value 1–500 chars, no whitespace-only
    - Implement `validate_alternative_name(name)` — 1–200 chars, not whitespace-only
    - Implement `validate_place_external_ids(place)` — no duplicate keys, each entry valid
    - Implement `validate_place_alternative_names(place)` — no duplicates (case-sensitive exact match), each valid
    - Integrate new validators into existing `validate_place()` function
    - _Requirements: 1.4, 1.5, 3.3, 3.4_

  - [x] 1.3 Write property tests for External ID model logic
    - **Property 1: External ID round-trip preservation**
    - **Property 2: External ID duplicate key rejection**
    - **Property 3: External ID whitespace-only rejection**
    - **Validates: Requirements 1.2, 1.3, 1.4, 1.5**

  - [x] 1.4 Write property tests for Alternative Name model logic
    - **Property 6: Alternative Name round-trip with trimming**
    - **Property 7: Alternative Name duplicate rejection**
    - **Property 8: Alternative Name invalid input rejection**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4**

- [x] 2. Implement External ID and Alternative Name management logic
  - [x] 2.1 Add helper methods for External ID operations on Place
    - Implement `add_external_id(place, ext_id)` — validates and appends, returns errors or None
    - Implement `remove_external_id(place, key)` — removes entry by key
    - Implement `edit_external_id(place, old_key, new_ext_id)` — validates and updates entry
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 2.3, 2.4, 2.7_

  - [x] 2.2 Add helper methods for Alternative Name operations on Place
    - Implement `add_alternative_name(place, name)` — validates, trims, and appends, returns errors or None
    - Implement `remove_alternative_name(place, index)` — removes entry preserving order of remaining items
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.3, 4.4_

  - [x] 2.3 Write property tests for External ID removal and edit
    - **Property 4: External ID removal preserves remaining entries**
    - **Property 5: External ID edit updates entry**
    - **Validates: Requirements 1.6, 2.4, 2.7**

  - [x] 2.4 Write property tests for Alternative Name removal
    - **Property 9: Alternative Name removal preserves order**
    - **Validates: Requirements 3.5, 4.4**

- [x] 3. Checkpoint - Ensure all model tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement Red Dot Indicator logic and delegate
  - [x] 4.1 Implement `needs_red_dot(place)` helper function
    - Add function to `slaktbusken/model/place.py` (or a shared utils module)
    - Returns `True` if `place.type != "country"` and `place.parent_place_id is None`
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 4.2 Create `PlaceListItemDelegate` in `slaktbusken/ui/editors/place_editor.py`
    - Subclass `QStyledItemDelegate`
    - Override `paint()` to render a solid red circle (≤8px diameter, 4px after text, vertically centered)
    - Use item data (store place reference or parent_place_id + type via `Qt.UserRole`) to determine if dot is needed
    - _Requirements: 5.1, 5.2, 5.3, 5.6_

  - [x] 4.3 Write property test for Red Dot logic
    - **Property 10: Red dot indicator correctness**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

- [ ] 5. Implement Type Filter in the left panel
  - [~] 5.1 Add `QComboBox` type filter to `PlaceEditor` left panel
    - Insert between `filter_input` and `place_list` in the layout
    - Populate with options: "Alla", "Land", "Län", "Socken", "Kyrka", "Kyrkogård", "By", "Gård", "Skola"
    - Default selection: "Alla"
    - _Requirements: 6.1, 6.2, 6.5_

  - [~] 5.2 Implement combined filter logic in `_refresh_place_list`
    - Update `_refresh_place_list` (or add `_matches_filters`) to apply both text filter and type filter
    - When type is "Alla", show all types; otherwise show only matching type
    - Sort results alphabetically by place name
    - Display empty list (no error) when no matches found
    - Connect type filter `currentIndexChanged` signal to trigger refresh
    - _Requirements: 6.3, 6.4, 6.6, 6.7_

  - [~] 5.3 Write property test for Type Filter logic
    - **Property 11: Type filter displays correct sorted subset**
    - **Validates: Requirements 6.3, 6.4**

- [~] 6. Checkpoint - Ensure model and filter logic tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Implement External ID UI section in the detail form
  - [~] 7.1 Add "Externa ID:n" `QGroupBox` section to the right panel
    - Add a `QListWidget` to display existing external IDs (showing key and value)
    - Add "Lägg till", "Redigera", and "Ta bort" buttons
    - _Requirements: 2.1, 2.5_

  - [~] 7.2 Implement Add External ID interaction
    - On "Lägg till" click, show key/value input fields (inline or dialog)
    - Enforce max 100 characters for key, max 200 characters for value
    - On confirm, validate and add entry; on validation error, show error message and retain inputs
    - _Requirements: 2.2, 2.3, 2.6_

  - [~] 7.3 Implement Edit and Remove External ID interaction
    - On "Redigera" click, populate input fields with selected entry's key/value for editing
    - On confirm, validate and update the entry; on duplicate key error, show message
    - On "Ta bort" click, remove selected entry from the place
    - _Requirements: 2.4, 2.7_

  - [~] 7.4 Wire External ID section to `_load_place_to_form` and `_on_save`
    - When a place is loaded, populate the External ID list from `place.external_ids`
    - When saving, collect External ID entries from the UI and persist on the place model
    - _Requirements: 2.5, 1.6_

- [ ] 8. Implement Alternative Name UI section in the detail form
  - [~] 8.1 Add "Alternativnamn:" `QGroupBox` section to the right panel
    - Add a `QListWidget` to display existing alternative names
    - Add "Lägg till" and "Ta bort" buttons
    - _Requirements: 4.1, 4.5_

  - [~] 8.2 Implement Add and Remove Alternative Name interaction
    - On "Lägg till" click, show text input field
    - Enforce max 200 characters; on confirm, validate (non-empty, not whitespace-only, no duplicate), trim, and add
    - On validation error, show error message and retain input for correction
    - On "Ta bort" click, remove selected entry from the place
    - _Requirements: 4.2, 4.3, 4.4, 4.6_

  - [~] 8.3 Wire Alternative Name section to `_load_place_to_form` and `_on_save`
    - When a place is loaded, populate the Alternative Names list from `place.alternative_names`
    - When saving, collect Alternative Name entries from the UI and persist on the place model
    - _Requirements: 4.5, 3.5_

- [ ] 9. Wire Red Dot Indicator into the Place List
  - [~] 9.1 Set `PlaceListItemDelegate` on the place `QListWidget`
    - Assign the delegate in `PlaceEditor.__init__`
    - Store place type and parent_place_id as item data (Qt.UserRole) when populating the list
    - Ensure the delegate reads this data to decide red dot rendering
    - _Requirements: 5.1, 5.2, 5.3, 5.6_

  - [~] 9.2 Ensure red dot updates on parent assignment changes
    - After save, refresh the place list so red dot reflects the current parent_place_id state
    - _Requirements: 5.4, 5.5_

- [ ] 10. Serialization backward compatibility
  - [~] 10.1 Verify serialization/deserialization of new fields
    - Confirm that the existing `_serialize_dataclass` handles `ExternalId` and `list[str]` correctly
    - Confirm that old JSON files without `external_ids`/`alternative_names` deserialize with empty list defaults
    - Add or update deserialization logic if needed (e.g., reconstruct `ExternalId` from dict)
    - _Requirements: 1.1, 3.1_

  - [~] 10.2 Write integration test for serialization round-trip
    - Test that a Place with external_ids and alternative_names serializes to JSON and deserializes identically
    - Test backward compatibility: old JSON without new fields loads with empty defaults
    - _Requirements: 1.1, 3.1_

- [~] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The project uses Hypothesis for property-based testing (already a dependency)
- All UI labels use Swedish ("Externa ID:n", "Alternativnamn:", "Lägg till", "Ta bort", "Redigera")
- The existing `_update_status` pattern is used for inline validation error display

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "4.1"] },
    { "id": 2, "tasks": ["1.3", "1.4", "2.1", "2.2", "4.2", "4.3"] },
    { "id": 3, "tasks": ["2.3", "2.4", "5.1"] },
    { "id": 4, "tasks": ["5.2", "5.3"] },
    { "id": 5, "tasks": ["7.1", "8.1", "9.1"] },
    { "id": 6, "tasks": ["7.2", "7.3", "8.2", "9.2"] },
    { "id": 7, "tasks": ["7.4", "8.3", "10.1"] },
    { "id": 8, "tasks": ["10.2"] }
  ]
}
```
