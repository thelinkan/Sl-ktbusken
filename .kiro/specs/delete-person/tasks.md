# Implementation Plan: Delete Person

## Overview

Implement person deletion with cascading cleanup for the Släktbusken genealogy application. The implementation follows a bottom-up approach: pure analysis functions first, then the deletion executor, then the service orchestration layer, and finally the confirmation dialog UI. This ensures each layer can be tested independently before integration.

## Tasks

- [ ] 1. Implement core deletion logic and analysis functions
  - [ ] 1.1 Create the DeleteService module with DeletionConsequences dataclass and event classification
    - Create `slaktbusken/services/delete_service.py`
    - Define `DeletionConsequences` dataclass with fields: person_name, exclusive_events, family_events, non_family_shared_events, affected_families, would_disconnect, disconnected_person_count
    - Implement `classify_events(person_id, data)` pure function that partitions events into exclusive, family, and non-family shared categories
    - Implement `find_affected_families(person_id, data)` pure function
    - _Requirements: 1.1, 2.3, 2.4_

  - [ ] 1.2 Write property test for event classification (Property 7)
    - **Property 7: Event Classification Is Exhaustive and Correct**
    - Generate ProjectData with a person having various event configurations
    - Assert the three categories are mutually exclusive and collectively exhaustive for all events involving the person
    - Assert exclusive events have only the target person as participant
    - Assert family events appear in at least one Family.event_ids
    - Assert non-family shared events have 2+ participants and do not appear in any Family.event_ids
    - Create `tests/test_services/test_delete_service_properties.py`
    - **Validates: Requirements 1.1, 2.3, 2.4**

  - [ ] 1.3 Implement tree connectivity checker
    - Implement `compute_disconnection(person_id, data)` pure function in `delete_service.py`
    - Use BFS from main_person_id on the relationship graph excluding the target person
    - Return (would_disconnect, disconnected_person_count)
    - Skip check when main_person_id is None or equals person_id
    - _Requirements: 7.1, 7.5, 7.6_

  - [ ] 1.4 Write property test for tree disconnection detection (Property 8)
    - **Property 8: Tree Disconnection Detection Correctness**
    - Generate connected ProjectData graphs with a main person set
    - Assert disconnection returns true iff removing the target makes at least one remaining person unreachable from main_person_id
    - **Validates: Requirements 7.1**

- [ ] 2. Implement deletion executor
  - [ ] 2.1 Implement `execute_person_deletion(person_id, data)` function
    - Add to `slaktbusken/services/delete_service.py`
    - Follow the 11-step mutation order specified in the design document
    - Remove exclusive events, family events, clean event_ids from families, remove participant entries from shared events, remove zero-participant events, clean family partners/children/links, remove empty families, clean media references, remove person from persons list
    - _Requirements: 1.2, 1.5, 2.1, 2.2, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ] 2.2 Write property test for no dangling references (Property 1)
    - **Property 1: No Dangling Person References After Deletion**
    - Generate valid ProjectData with a deletable person
    - Execute deletion and assert no remaining event, family, or link references the deleted person
    - **Validates: Requirements 1.2, 2.1, 3.1, 3.3, 4.1, 4.2, 4.3, 8.1, 8.2, 8.3, 8.4**

  - [ ] 2.3 Write property test for media integrity (Property 2)
    - **Property 2: Media Integrity After Deletion**
    - Generate ProjectData with media items referencing the deletable person
    - Assert media list length unchanged, person id removed from mentioned_person_ids/linked_entities/annotations, mentioned_names unchanged
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

  - [ ] 2.4 Write property test for no empty families (Property 3)
    - **Property 3: No Empty Families After Deletion**
    - Assert no remaining family has both empty partners and empty children after deletion
    - **Validates: Requirements 1.5, 4.4**

  - [ ] 2.5 Write property test for events from removed families (Property 4)
    - **Property 4: Events From Removed Families Are Preserved**
    - Assert events referenced by removed families still exist in ProjectData.events unless independently classified as exclusive/family events of the deleted person
    - **Validates: Requirements 4.5**

  - [ ] 2.6 Write property test for deleted person removal (Property 10)
    - **Property 10: Deleted Person Is Removed From Persons List**
    - Assert person not in ProjectData.persons after deletion and persons list length decreased by exactly one
    - **Validates: Requirements 1.2**

- [ ] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Implement DeleteService class and main person guard
  - [ ] 4.1 Implement the `DeleteService` class with `can_delete`, `compute_consequences`, and `execute_deletion` methods
    - Create `DeleteService` class in `slaktbusken/services/delete_service.py`
    - Implement `can_delete(person_id)` returning (False, "Huvudpersonen kan inte tas bort.") when person is main person
    - Implement `compute_consequences(person_id)` orchestrating classify_events, find_affected_families, and compute_disconnection
    - Implement `execute_deletion(person_id)` calling `execute_person_deletion` and marking project dirty
    - Wire to existing `ProjectService` for data access and dirty flag
    - _Requirements: 1.2, 1.4, 8.5_

  - [ ] 4.2 Write property test for main person guard (Property 5)
    - **Property 5: Main Person Cannot Be Deleted**
    - Assert can_delete returns False when person_id equals main_person_id, and no data is modified
    - **Validates: Requirements 1.4**

  - [ ] 4.3 Write property test for round-trip integrity (Property 6)
    - **Property 6: Round-Trip Integrity After Deletion**
    - Execute deletion, serialize to JSON, deserialize, assert equivalence
    - **Validates: Requirements 8.6**

  - [ ] 4.4 Write unit tests for DeleteService
    - Test cancel preserves state (Req 1.3, 6.6)
    - Test main person error message content (Req 1.4)
    - Test dirty flag set after successful deletion (Req 8.5)
    - Test connectivity check skipped when no main person set (Req 7.5)
    - Test connectivity check skipped for main person target (Req 7.6)
    - Create `tests/test_services/test_delete_service.py`
    - _Requirements: 1.3, 1.4, 7.5, 7.6, 8.5_

- [ ] 5. Implement confirmation dialog UI
  - [ ] 5.1 Implement `build_warning_lines` pure function and `DeletePersonDialog`
    - Create `slaktbusken/ui/dialogs/delete_person_dialog.py`
    - Implement `build_warning_lines(consequences, max_events=10)` returning Swedish-language warning lines
    - Cap event listing at 10 items, appending "...och N till" for overflow
    - Implement `DeletePersonDialog(QDialog)` with warning text display, "Ta bort" button, and "Avbryt" button
    - Display person name, event counts, family associations, and disconnection warning when applicable
    - _Requirements: 1.6, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.2, 7.3_

  - [ ] 5.2 Write property test for warning list cap (Property 9)
    - **Property 9: Warning List Caps At 10 Events**
    - Generate DeletionConsequences with varying event counts
    - Assert at most 10 events listed and overflow count indicated when N > 10
    - **Validates: Requirements 6.4**

  - [ ] 5.3 Write unit tests for warning text formatting
    - Test Swedish text output for various event configurations
    - Test "inget datum" for events without dates
    - Test overflow message format
    - Test empty event list produces generic confirmation
    - _Requirements: 6.1, 6.2, 6.3, 6.5_

- [ ] 6. Wire delete action into existing UI
  - [ ] 6.1 Integrate DeleteService and dialog into context menu and person editor
    - Add delete action to the person context menu (right-click in tree/list views)
    - Wire the action to call `DeleteService.can_delete()`, then `compute_consequences()`, then show `DeletePersonDialog`
    - On confirm, call `DeleteService.execute_deletion()`
    - Register `DeleteService` in the application's service initialization
    - Update `slaktbusken/services/__init__.py` to export DeleteService
    - _Requirements: 1.1, 1.2, 1.3, 1.6, 6.5, 6.6, 7.2, 7.3, 7.4_

  - [ ] 6.2 Write integration tests for end-to-end deletion flow
    - Test full deletion flow with realistic family tree data
    - Test deletion of a person with multiple family memberships
    - Test deletion that triggers empty family removal
    - Test deletion that disconnects tree section
    - Create `tests/test_services/test_delete_service_integration.py`
    - _Requirements: 1.2, 4.4, 7.1_

- [ ] 7. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The project already uses Hypothesis with strategies in `tests/conftest.py` — follow established patterns
- Implementation language is Python with PySide6 for UI components

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["1.4", "2.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "2.4", "2.5", "2.6"] },
    { "id": 4, "tasks": ["4.1"] },
    { "id": 5, "tasks": ["4.2", "4.3", "4.4", "5.1"] },
    { "id": 6, "tasks": ["5.2", "5.3", "6.1"] },
    { "id": 7, "tasks": ["6.2"] }
  ]
}
```
