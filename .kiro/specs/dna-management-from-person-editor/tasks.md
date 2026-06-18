# Implementation Plan: DNA Management from Person Editor

## Overview

This plan implements DNA profile and match creation directly from the Person Editor's "DNA & Kluster" tab. Two new dialog classes (`DnaProfileDialog`, `DnaMatchDialog`) are created in the existing dialogs module, and the `PersonEditor` is extended with buttons and handlers following the established patterns (cluster buttons, event dialog).

## Tasks

- [x] 1. Create DnaProfileDialog
  - [x] 1.1 Create `slaktbusken/ui/dialogs/dna_profile_dialog.py` with the `DnaProfileDialog` class
    - Subclass `QDialog` with form fields: company (QComboBox), test type (QComboBox), kit name (QLineEdit, max 100), kit ID (QLineEdit, max 50), notes (QPlainTextEdit, max 2000)
    - Populate company dropdown from `ProjectData.dna_companies`
    - Populate test type dropdown with autosomal, Y-DNA, mtDNA
    - Implement `_validate()` returning error list (company required, test type required)
    - On OK click: validate, show errors in status label if invalid, construct `DnaProfile` with `uuid4()` ID and accept if valid
    - If no companies exist, show info message and disable OK button
    - Expose `created_profile` property returning the `DnaProfile` or `None`
    - _Requirements: 2.1, 2.2, 2.3, 2.6_

  - [x] 1.2 Write property test for profile creation round-trip
    - **Property 1: Profile creation round-trip**
    - Generate random valid company ID, test type, kit name, kit ID, notes
    - Verify resulting `DnaProfile` has correct `person_id`, `company_id`, `test_type`, and optional fields
    - **Validates: Requirements 2.3, 2.4**

  - [x] 1.3 Write property test for profile validation rejects incomplete forms
    - **Property 2: Profile validation rejects incomplete forms**
    - Generate random optional field values with missing company OR missing test type
    - Verify `_validate()` returns at least one error and `created_profile` is `None`
    - **Validates: Requirements 2.2**

- [x] 2. Create DnaMatchDialog
  - [x] 2.1 Create `slaktbusken/ui/dialogs/dna_match_dialog.py` with the `DnaMatchDialog` class
    - Subclass `QDialog` with form fields: profile 1 (QComboBox, current person's profiles), profile 2 (QComboBox, all other profiles), shared cM (QDoubleSpinBox, 0.01–10000.00), shared % (QDoubleSpinBox, 0.01–100.00), segment count (QSpinBox, 1–100000), largest segment cM (QDoubleSpinBox, 0.01–10000.00), match source (QLineEdit, max 200, default "internal"), notes (QPlainTextEdit, max 2000)
    - Pre-select profile 1 if person has exactly one profile; disable dropdown in that case
    - Implement `_validate()` returning error list (both profiles required, profiles must differ, shared cM required)
    - On OK click: validate, show errors in status label if invalid, construct `DnaMatch` with `uuid4()` ID and accept if valid
    - If no other profiles exist, show info message and disable OK button
    - Expose `created_match` property returning the `DnaMatch` or `None`
    - _Requirements: 4.1, 4.2, 4.3, 4.6, 4.7, 4.8_

  - [x] 2.2 Write property test for match creation round-trip
    - **Property 3: Match creation round-trip**
    - Generate random valid two distinct profile IDs, shared cM, and optional fields
    - Verify resulting `DnaMatch` has correct `profile1_id`, `profile2_id`, `shared_cm`, and optional fields
    - **Validates: Requirements 4.3, 4.4**

  - [x] 2.3 Write property test for match validation rejects invalid forms
    - **Property 4: Match validation rejects invalid forms**
    - Generate form states with missing profile 1, missing profile 2, zero shared cM, or same profile for both
    - Verify `_validate()` returns at least one error and `created_match` is `None`
    - **Validates: Requirements 4.6, 4.7**

- [x] 3. Checkpoint - Validate dialog implementations
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Extend PersonEditor with DNA buttons and handlers
  - [x] 4.1 Add `_setup_dna_profile_button()` to `PersonEditor` in `slaktbusken/ui/editors/person_editor.py`
    - Add "Lägg till profil" button below the DNA profiles list in the DNA tab
    - Connect button click to `_on_add_dna_profile()`
    - Hide button when no person is loaded, show when person is loaded
    - _Requirements: 1.1, 1.3, 1.4_

  - [x] 4.2 Add `_setup_dna_match_button()` to `PersonEditor`
    - Add "Lägg till matchning" button below the DNA matches list in the DNA tab
    - Connect button click to `_on_add_dna_match()`
    - Hide button when no person is loaded, show when person is loaded
    - Disable button with tooltip "En DNA-profil krävs för att skapa matchningar" when person has no DNA profiles
    - _Requirements: 3.1, 3.3, 3.4_

  - [x] 4.3 Implement `_on_add_dna_profile()` handler in `PersonEditor`
    - Open `DnaProfileDialog` as modal
    - On dialog accept: append `created_profile` to `ProjectData.dna_profiles`, call `_refresh_dna_profiles()`, call `_refresh_dna_matches()`, call `_update_dna_button_states()`
    - On dialog reject: no changes to `ProjectData`
    - _Requirements: 1.2, 2.4, 2.5, 2.7, 5.1_

  - [x] 4.4 Implement `_on_add_dna_match()` handler in `PersonEditor`
    - Open `DnaMatchDialog` as modal
    - On dialog accept: append `created_match` to `ProjectData.dna_matches`, call `_refresh_dna_matches()`
    - On dialog reject: no changes to `ProjectData`
    - _Requirements: 3.2, 4.4, 4.5, 4.9, 5.2_

  - [x] 4.5 Implement `_update_dna_button_states()` in `PersonEditor`
    - Enable match button if current person has at least one profile in `ProjectData.dna_profiles`
    - Disable match button with tooltip when person has no profiles
    - Call this method from person load, profile creation handler, and initial setup
    - _Requirements: 3.4, 5.3_

  - [x] 4.6 Write property test for cancel preserves project data
    - **Property 5: Cancel preserves project data**
    - Generate random `ProjectData` state, simulate opening and canceling each dialog
    - Verify `ProjectData.dna_profiles` and `ProjectData.dna_matches` are unchanged
    - **Validates: Requirements 2.7, 4.9**

  - [x] 4.7 Write property test for match button enabled invariant
    - **Property 7: Match button enabled invariant**
    - Generate random person/profile combinations in `ProjectData`
    - Verify button is enabled iff person has at least one `DnaProfile`
    - Verify tooltip is empty when enabled, "En DNA-profil krävs för att skapa matchningar" when disabled
    - **Validates: Requirements 3.4, 5.3**

- [x] 5. Checkpoint - Validate PersonEditor integration
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Wire dialogs into module exports and verify list refresh
  - [x] 6.1 Register dialog exports in `slaktbusken/ui/dialogs/__init__.py`
    - Add `DnaProfileDialog` and `DnaMatchDialog` to module exports
    - Ensure imports in `person_editor.py` reference the dialogs module correctly
    - _Requirements: 1.2, 3.2_

  - [x] 6.2 Call `_setup_dna_profile_button()` and `_setup_dna_match_button()` from PersonEditor initialization
    - Integrate button setup into the DNA tab construction flow (alongside existing `_setup_cluster_buttons()`)
    - Ensure buttons appear in correct layout position
    - _Requirements: 1.1, 3.1_

  - [x] 6.3 Write property test for UI list consistency after creation
    - **Property 6: UI list consistency after creation**
    - Generate random valid profile/match creation inputs
    - After creation, verify profiles list item count equals `DnaProfile` entries for current person
    - Verify matches list item count equals `DnaMatch` entries referencing any of current person's profile IDs
    - **Validates: Requirements 2.5, 4.5, 5.1, 5.2**

- [x] 7. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- All dialog text and messages are in Swedish, consistent with the rest of the application
- New dialog files go in `slaktbusken/ui/dialogs/`, following the existing pattern
- Property test files go in `tests/test_ui/`, following existing naming like `test_dna_cluster_membership_property.py`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "2.2", "2.3"] },
    { "id": 2, "tasks": ["4.1", "4.2", "6.1"] },
    { "id": 3, "tasks": ["4.3", "4.4", "4.5", "6.2"] },
    { "id": 4, "tasks": ["4.6", "4.7", "6.3"] }
  ]
}
```
