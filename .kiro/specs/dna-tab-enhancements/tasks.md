# Implementation Plan: DNA Tab Enhancements

## Overview

This plan implements the DNA tab enhancements for the Person Editor in Släktbusken. The work is organized into logical groups: icon integration, edit capabilities for profiles/matches, same-company filtering, triangulation section with person validation, cluster tab extraction, and property-based tests. Each task builds incrementally on the previous ones, and the implementation uses Python with PySide6.

## Tasks

- [x] 1. Add company logo icons to DNA profiles and matches lists
  - [x] 1.1 Add icons to the DNA profiles list in PersonEditor
    - In `_refresh_dna_profiles` (person_editor.py), set `iconSize` on the profiles list widget to `QSize(24, 24)`
    - For each profile item, call `resolve_profile_logo_icon(profile, project_data, project_folder)` and set the returned QIcon on the QListWidgetItem
    - Import `resolve_profile_logo_icon` from `slaktbusken.ui.editors.dna_editor`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 1.2 Add icons to the DNA matches list in PersonEditor
    - In `_refresh_dna_matches` (person_editor.py), set `iconSize` on the matches list widget to `QSize(24, 24)`
    - For each match item, call `resolve_company_logo_icon(match, project_data, project_folder)` and set the returned QIcon on the QListWidgetItem
    - Import `resolve_company_logo_icon` from `slaktbusken.ui.editors.dna_editor`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 1.3 Write property tests for icon resolution (Properties 1 and 2)
    - **Property 1: Profile icon resolution correctness** — For any DnaProfile, `resolve_profile_logo_icon` returns a QIcon without raising exceptions; returns empty QIcon when company/media cannot resolve; returns distinct missing-file icon when path resolves but file absent
    - **Property 2: Match icon resolution correctness** — For any DnaMatch, `resolve_company_logo_icon` returns correct icon type based on profile2→company→logo chain state
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 2.5**

- [x] 2. Implement edit mode for DnaProfileDialog
  - [x] 2.1 Add edit mode to DnaProfileDialog
    - Add optional `existing_profile: Optional[DnaProfile] = None` parameter to `__init__`
    - When `existing_profile` is provided: set window title to "Redigera DNA-profil", pre-populate company, test type, kit name, kit ID, and notes fields
    - Add `edited_profile` property that returns the updated profile (preserving original `id` and `person_id`)
    - On accept in edit mode: build profile with original ID/person_id instead of generating new uuid4
    - _Requirements: 3.2, 3.4, 3.5_

  - [x] 2.2 Add edit button and double-click handler for DNA profiles in PersonEditor
    - Add "Redigera" QPushButton next to the existing "Lägg till DNA-profil" button in `_setup_dna_profile_button`
    - Connect button click to new `_on_edit_dna_profile` method
    - Connect `itemDoubleClicked` signal on the profiles list to `_on_edit_dna_profile`
    - In `_on_edit_dna_profile`: get selected profile, open DnaProfileDialog with `existing_profile=selected`, on accept update ProjectData and refresh lists
    - Update `_update_dna_button_states` to enable/disable the edit button based on profiles list selection
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.6, 3.7_

  - [x] 2.3 Write property tests for profile edit (Properties 3–7 for profiles)
    - **Property 3: Edit button enabled state tracks selection** — Verify edit button enabled iff profile list has selection
    - **Property 4: Cancel preserves original data** — Open edit dialog, cancel, verify profile unchanged in ProjectData
    - **Property 5: Edit preserves identity and updates fields** — Save edit preserves profile.id and person_id, updates other fields
    - **Property 6: Edit dialog pre-population matches entity data** — All dialog fields match the existing_profile attributes
    - **Property 7: Invalid edits are rejected without data modification** — Invalid inputs keep dialog open, original data unchanged
    - **Validates: Requirements 3.1, 3.2, 3.4, 3.5, 3.7**

- [x] 3. Implement edit mode for DnaMatchDialog with same-company filtering
  - [x] 3.1 Add same-company profile filtering to DnaMatchDialog
    - Connect `_combo_profile1.currentIndexChanged` to a new `_on_profile1_changed` method
    - In `_on_profile1_changed`: get selected profile's `company_id`, clear and repopulate `_combo_profile2` with only profiles having matching `company_id` (excluding profile1 itself)
    - Disable `_combo_profile2` when no profile1 is selected; reset to placeholder on profile1 change
    - Show info label and disable OK when filter yields zero profile2 options
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 3.2 Add edit mode to DnaMatchDialog
    - Add optional `existing_match: Optional[DnaMatch] = None` parameter to `__init__`
    - When `existing_match` is provided: set window title to "Redigera DNA-matchning", pre-select profile1, trigger filtering, pre-select profile2, populate shared_cm, shared_percentage, segment_count, largest_segment_cm, match_source, and notes
    - Add `edited_match` property that returns the updated match (preserving original `id`)
    - On accept in edit mode: build match with original ID instead of uuid4
    - _Requirements: 4.2, 4.4, 4.7, 5.4_

  - [x] 3.3 Add edit button and double-click handler for DNA matches in PersonEditor
    - Add "Redigera" QPushButton next to the existing "Lägg till DNA-matchning" button in `_setup_dna_match_button`
    - Connect button click to new `_on_edit_dna_match` method
    - Connect `itemDoubleClicked` signal on the matches list to `_on_edit_dna_match`
    - In `_on_edit_dna_match`: get selected match, open DnaMatchDialog with `existing_match=selected`, on accept update ProjectData and refresh matches list
    - Update `_update_dna_button_states` to enable/disable the match edit button based on matches list selection
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [x] 3.4 Write property tests for match edit and same-company filtering (Properties 3–8)
    - **Property 3: Edit button enabled state tracks selection** — Verify match edit button enabled iff matches list has selection
    - **Property 4: Cancel preserves original data** — Open edit dialog for match, cancel, verify match unchanged
    - **Property 5: Edit preserves identity and updates fields** — Save edit preserves match.id, updates other fields
    - **Property 6: Edit dialog pre-population matches entity data** — All dialog fields match the existing_match attributes
    - **Property 7: Invalid edits are rejected without data modification** — Invalid inputs rejected, original data preserved
    - **Property 8: Same-company profile filtering invariant** — Every item in profile2 dropdown has same company_id as profile1; profile1 not in profile2 list
    - **Validates: Requirements 4.1, 4.2, 4.4, 4.6, 4.7, 5.1, 5.2, 5.3**

- [x] 4. Checkpoint - Ensure profiles and matches edits work correctly
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement triangulation section in DNA tab
  - [x] 5.1 Add triangulation list and buttons to the DNA tab in PersonEditor
    - Add "Trianguleringar" QLabel, QListWidget, "Lägg till triangulering" button, and "Redigera" button below the matches section
    - Set `iconSize` on the triangulation list to `QSize(24, 24)`
    - Implement `_refresh_triangulations` to collect all DnaTriangulation records whose `profile_ids` intersects the active person's profile IDs
    - Format each item as `"Kromosom {chromosome}: {overlap_start}–{overlap_end} ({N} profiler)"` with company logo icon
    - Call `_refresh_triangulations` during `_load_person`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 5.2 Create DnaTriangulationDialog with person validation logic
    - Create new file `slaktbusken/ui/dialogs/dna_triangulation_dialog.py`
    - Implement `DnaTriangulationDialog(project_data, person_id, existing_triangulation=None, parent=None)`
    - UI fields: company dropdown (QComboBox), chromosome dropdown (values "1"–"22", "X", "Y", "MT"), overlap_start (QSpinBox 0–300000000), overlap_end (QSpinBox 0–300000000), person selection list (QListWidget multi-select)
    - Validation: company required, chromosome required, overlap_start < overlap_end, at least 2 eligible persons selected
    - Implement `get_eligible_triangulation_persons(active_person_id, selected_person_ids, company_id, project_data)` as a module-level pure function
    - Implement `has_dna_match(person_a_id, person_b_id, project_data)` as a module-level pure function checking bidirectional match existence
    - Connect person selection changes to re-filter eligible candidates
    - When company is selected, restrict candidates to those with a profile in that company
    - Show info and disable save when fewer than 2 eligible persons exist
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [x] 5.3 Wire triangulation add/edit in PersonEditor
    - Connect "Lägg till triangulering" button to `_on_add_triangulation` which opens `DnaTriangulationDialog` in create mode
    - Connect "Redigera" button and `itemDoubleClicked` to `_on_edit_triangulation` which opens dialog with `existing_triangulation`
    - On accept: create/update `DnaTriangulation` in ProjectData and refresh list
    - Update button enabled states: edit button enabled only when a triangulation is selected
    - _Requirements: 7.1, 7.2, 7.5, 7.6, 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 5.4 Write property tests for triangulation (Properties 9–14)
    - **Property 9: Triangulation list contains exactly relevant triangulations** — List shows a triangulation iff its profile_ids intersects active person's profile IDs
    - **Property 10: Triangulation display format correctness** — Display text exactly matches `"Kromosom {chromosome}: {overlap_start}–{overlap_end} ({N} profiler)"`
    - **Property 11: Triangulation overlap validation** — Dialog accepts save iff start < end
    - **Property 12: Triangulation person mutual-match filtering** — Candidate eligible iff match with active person AND every already-selected person
    - **Property 13: Match existence is bidirectional** — `has_dna_match(A, B)` == `has_dna_match(B, A)`
    - **Property 14: Triangulation company-restricted person filtering** — Candidate eligible only if they have a profile in the selected company
    - **Validates: Requirements 6.2, 6.3, 7.4, 9.1, 9.2, 9.4, 9.5, 9.6**

- [x] 6. Move cluster section to its own tab
  - [x] 6.1 Extract cluster widgets from DNA tab into a new Kluster tab
    - In PersonEditor, create a new "Kluster" tab widget after the DNA tab (tab index 4)
    - Move cluster label ("Klustermedlemskap:"), cluster list widget, "Lägg till kluster" button, and "Ta bort" button to the new tab
    - Rename the DNA tab text from "DNA & Kluster" to "DNA"
    - Set the Kluster tab text to "Kluster"
    - Preserve all existing cluster functionality (add, remove, info message when no clusters exist)
    - Remove all cluster-related widgets from the DNA tab layout
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_

  - [x] 6.2 Write unit tests for tab structure
    - Verify tab order is (Namn, Händelser, Foton, DNA, Kluster)
    - Verify DNA tab text is "DNA" and Kluster tab text is "Kluster"
    - Verify cluster widgets are in the Kluster tab and not in the DNA tab
    - Verify add/remove cluster functionality works in the new tab location
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

- [x] 7. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The implementation language is Python with PySide6, matching the existing codebase
- Existing Hypothesis strategies in `tests/conftest.py` (`dna_profile_strategy`, `dna_match_strategy`, `dna_triangulation_strategy`, `dna_company_strategy`, `project_data_strategy`) should be reused for property tests
- All UI text is in Swedish to match the application locale

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "2.1", "6.1"] },
    { "id": 1, "tasks": ["2.2", "3.1", "1.3", "6.2"] },
    { "id": 2, "tasks": ["3.2", "5.1"] },
    { "id": 3, "tasks": ["3.3", "5.2", "2.3"] },
    { "id": 4, "tasks": ["3.4", "5.3"] },
    { "id": 5, "tasks": ["5.4"] }
  ]
}
```
