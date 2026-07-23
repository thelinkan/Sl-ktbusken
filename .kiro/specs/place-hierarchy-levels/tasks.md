# Implementation Plan: Place Hierarchy Levels

## Overview

This plan implements the extended place hierarchy with continent as a top-level type and country-specific region levels. Implementation proceeds bottom-up: data model first (dataclasses, validation), then persistence (serialization), then presets, and finally UI integration. Property-based tests validate correctness properties from the design at each layer.

## Tasks

- [x] 1. Extend the Place model with RegionLevel, CustomFieldDef, and new fields
  - [x] 1.1 Add `CustomFieldDef` and `RegionLevel` dataclasses to `slaktbusken/model/place.py`
    - Define `CustomFieldDef` with fields: `key` (str), `label` (str)
    - Define `RegionLevel` with fields: `key` (str), `label` (str), `order` (int), `custom_fields` (list[CustomFieldDef])
    - Add `region_levels: list[RegionLevel]` and `custom_field_values: dict[str, str]` fields to the `Place` dataclass
    - Update `needs_red_dot()` to return `place.type != "continent" and place.parent_place_id is None`
    - _Requirements: 1.1, 2.1, 2.2, 5.1, 5.2, 5.3, 5.4, 8.1, 8.3_

  - [x] 1.2 Write property test for red dot indicator (Property 1)
    - **Property 1: Red dot indicator equivalence**
    - Test that for any place of any type with any parent_place_id value, `needs_red_dot(place)` returns True iff `place.type != "continent"` and `place.parent_place_id is None`
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**

- [ ] 2. Implement validation logic for continent and country hierarchy
  - [ ] 2.1 Extend `validate_place()` and `_validate_place_hierarchy()` in `slaktbusken/model/validators.py`
    - Add "continent" to `_VALID_PLACE_TYPES` and `_PLACE_TYPE_SWEDISH`
    - Add continent rule: must NOT have a parent (error: "En kontinent får inte ha en överordnad plats.")
    - Change country rule: must have a parent of type "continent" (errors for missing parent and wrong parent type)
    - Remove old rigid hierarchy for county/parish/church/cemetery/village/farm/school
    - Add dynamic region-level hierarchy validation: region-level places require correct parent by order
    - Allow universal types (church, cemetery, farm, school) as children of any region level or locality
    - Allow locality (ort) as a child of any region level
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 3.6, 3.7_

  - [ ] 2.2 Write property test for continent hierarchy enforcement (Property 2)
    - **Property 2: Continent hierarchy enforcement**
    - Test that a continent is rejected iff parent_place_id is not None; accepted when None
    - **Validates: Requirements 1.2, 1.3**

  - [ ] 2.3 Write property test for country parent must be continent (Property 3)
    - **Property 3: Country parent must be continent**
    - Test that a country is rejected when parent is None or non-continent; accepted when parent is continent
    - **Validates: Requirements 1.4, 1.5, 1.6**

  - [ ] 2.4 Write property test for universal types and locality (Property 8)
    - **Property 8: Universal types and locality valid as children of any region level**
    - Test that church, cemetery, farm, school, and locality are accepted as children of any valid region level type
    - **Validates: Requirements 3.6, 3.7**

- [ ] 3. Implement region level validation
  - [ ] 3.1 Add `validate_region_levels()` function to `slaktbusken/model/validators.py`
    - Validate key length (1–50 chars), label length (1–100 chars)
    - Validate keys unique within country
    - Validate order values consecutive from 1, max 10 entries
    - Return Swedish error messages matching the design
    - Call from `validate_place()` only when `place.type == "country"`
    - Ignore region_levels on non-country places
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ] 3.2 Add `validate_custom_field_values()` function to `slaktbusken/model/validators.py`
    - Validate custom field values: accept 1–20 chars or empty, reject >20 chars
    - Validate keys match a CustomFieldDef key from the country's region level
    - Call from `validate_place()` for places whose type matches a region level with custom fields
    - _Requirements: 8.5, 8.6_

  - [ ] 3.3 Write property test for region level validation (Property 4)
    - **Property 4: Region level validation**
    - Test that validation passes iff keys are 1-50 chars, labels 1-100 chars, keys unique, order consecutive from 1, max 10 entries
    - **Validates: Requirements 2.2, 2.3, 2.4, 2.6**

  - [ ] 3.4 Write property test for region levels ignored on non-country places (Property 5)
    - **Property 5: Region levels ignored on non-country places**
    - Test that for any non-country place, region_levels does not produce validation errors
    - **Validates: Requirements 2.5**

  - [ ] 3.5 Write property test for custom field value length validation (Property 10)
    - **Property 10: Custom field value length validation**
    - Test that values 1-20 chars accepted, >20 chars rejected, empty accepted
    - **Validates: Requirements 8.5, 8.6**

  - [ ] 3.6 Write property test for coordinates may be None (Property 9)
    - **Property 9: Coordinates may be None for any place type**
    - Test that any place (including continent and country) with None lat/lon passes validation
    - **Validates: Requirements 4.2**

- [ ] 4. Checkpoint - Ensure all model validation tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Update serialization for RegionLevel and CustomFieldDef
  - [ ] 5.1 Register new nested types in `slaktbusken/persistence/serialization.py`
    - Import `RegionLevel` and `CustomFieldDef` from `slaktbusken.model.place`
    - Add `(Place, "region_levels"): RegionLevel` to `_NESTED_LIST_TYPES`
    - Add `(RegionLevel, "custom_fields"): CustomFieldDef` to `_DEEP_NESTED_LIST_TYPES`
    - _Requirements: 9.1, 9.2_

  - [ ] 5.2 Write property test for serialization round-trip (Property 11)
    - **Property 11: Serialization round-trip preserves Place data**
    - Extend `conftest.py` with `region_level_strategy()`, `custom_field_def_strategy()`, and update `place_strategy()` to include region_levels and custom_field_values
    - Test that serialize → deserialize produces equivalent Place objects (including region_levels and custom_field_values)
    - **Validates: Requirements 9.1, 9.2, 9.3**

- [ ] 6. Create country presets module
  - [ ] 6.1 Create `slaktbusken/data/country_presets.py`
    - Implement `get_preset(country_name: str) -> list[RegionLevel]` returning predefined levels
    - Implement `available_presets() -> list[str]` returning country names
    - Define presets for: Sverige (Län, Socken), USA (Delstat, County), Tyskland (Förbundsland, Kreis), Norge (Fylke, Kommune), Danmark (Region, Kommune), Finland (Landskap, Kommun), England (County, Parish)
    - Include custom field "code" with label "Länsbokstav" on Sverige's Län level
    - _Requirements: 6.1, 6.4, 8.4_

  - [ ] 6.2 Write unit tests for country presets
    - Verify all 7 presets exist and return correct region level data
    - Verify Sverige Län includes the "code"/"Länsbokstav" custom field
    - Verify order values are consecutive from 1 in each preset
    - _Requirements: 6.1, 6.4, 8.4_

- [ ] 7. Checkpoint - Ensure model and persistence tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Update Place Editor UI for new hierarchy
  - [ ] 8.1 Implement `build_type_options()` in `slaktbusken/ui/editors/place_editor.py`
    - Build Type_Dropdown options: always include "Kontinent", "Land", universal types
    - Collect all unique region level labels from countries in the project
    - Place "Kontinent" first in the dropdown list
    - Remove region labels exclusive to removed countries
    - _Requirements: 1.7, 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ] 8.2 Write property test for type dropdown contents (Property 6)
    - **Property 6: Type dropdown contains all active region labels**
    - Test that the dropdown contains exactly: continent, country, universals, plus all unique region labels from project countries
    - **Validates: Requirements 3.3, 3.4**

  - [ ] 8.3 Write property test for removing country removes exclusive labels (Property 7)
    - **Property 7: Removing a country removes exclusive labels from dropdown**
    - Test that removing a country removes labels not shared by remaining countries
    - **Validates: Requirements 3.5**

  - [ ] 8.4 Add preset selection UI and custom field inputs in Place_Editor
    - Show preset dropdown when editing a country place (populated from `available_presets()`)
    - On preset selection, populate region_levels in the form (user can modify before save)
    - Show custom field inputs when place type matches a region level with custom fields defined
    - _Requirements: 6.2, 6.3, 8.2_

- [ ] 9. Wire integration and final validation
  - [ ] 9.1 Update `conftest.py` Hypothesis strategies for new place types
    - Add "continent" to `_PLACE_TYPES` list
    - Add `region_level_strategy()` and `custom_field_def_strategy()` composite strategies
    - Update `place_strategy()` to conditionally generate region_levels for country-type places and custom_field_values for region-level places
    - _Requirements: 2.1, 8.1_

  - [ ] 9.2 Ensure PlaceRef allows continent and country references without restriction
    - Verify no PlaceRef validation limits which place types can be referenced by events
    - Verify red dot is not triggered by missing coordinates on continent/country
    - _Requirements: 4.1, 4.3, 4.4_

  - [ ] 9.3 Write integration tests for save/load cycle with hierarchy
    - Test end-to-end: create project with continents, countries with region_levels, region places with custom_field_values → save → load → verify equivalence
    - _Requirements: 9.1, 9.2, 9.3_

- [ ] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The project uses Python with Hypothesis for property-based testing and pytest as the test runner
- Existing patterns in `conftest.py` provide strategies for all domain dataclasses — extend these with new types

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "5.1", "6.1", "9.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "3.1", "3.2", "6.2"] },
    { "id": 3, "tasks": ["3.3", "3.4", "3.5", "3.6", "5.2"] },
    { "id": 4, "tasks": ["8.1", "9.2"] },
    { "id": 5, "tasks": ["8.2", "8.3", "8.4"] },
    { "id": 6, "tasks": ["9.3"] }
  ]
}
```
