# Implementation Plan: Deleted PersonBoxItem Crash Bugfix

## Overview

This plan fixes the `RuntimeError: Internal C++ object (PersonBoxItem) already deleted` that occurs when the active person is changed in the diagram view. The fix uses a three-layer defense strategy: (1) QSignalBlocker to suppress `selectionChanged` during `scene.clear()` and rebuild, (2) clearing `_person_boxes` before `scene.clear()` as defense in depth, and (3) `shiboken6.isValid()` guards in `deselect_all()` and `handle_click()` across all three view renderers.

The workflow follows the bug condition methodology: write exploration and preservation tests BEFORE the fix, implement the fix, then verify both test classes pass.

## Tasks

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - RuntimeError on scene clear with stale PersonBoxItem references
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the RuntimeError when `_refresh_diagram()` is called while `_person_boxes` holds stale references
  - **Scoped PBT Approach**: Scope the property to the concrete failing case: call `set_active_person()` on a DiagramPanel that has already rendered a diagram with at least one person box
  - Test that calling `_refresh_diagram()` after an initial render does NOT raise `RuntimeError` (from Bug Condition in design: `isBugCondition(input)` where `input.triggers_scene_clear == True AND view._person_boxes is not empty`)
  - Use Hypothesis to generate random person IDs and verify no RuntimeError is raised during active person change
  - Simulate the flow: render diagram with person A → change active person to person B → assert no RuntimeError
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS with `RuntimeError: Internal C++ object (PersonBoxItem) already deleted` (this confirms the bug exists)
  - Document counterexamples found: `_refresh_diagram()` calls `scene.clear()` → `selectionChanged` fires → `deselect_all()` accesses stale `_person_boxes` → RuntimeError
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Selection and deselect behavior unchanged for valid person boxes
  - **IMPORTANT**: Follow observation-first methodology
  - **IMPORTANT**: Write these tests BEFORE implementing the fix
  - Observe on UNFIXED code: clicking a person box selects it and deselects others
  - Observe on UNFIXED code: `deselect_all()` on a view with valid (non-deleted) boxes deselects all without error
  - Observe on UNFIXED code: `handle_click(person_id)` selects the matching box and deselects others
  - Observe on UNFIXED code: switching views renders correctly without visual artifacts
  - Write property-based tests using Hypothesis:
    - For all valid (non-deleted) person box lists, `deselect_all()` sets all boxes to unselected state
    - For all valid person box lists and any person_id, `handle_click(person_id)` selects exactly the matching box
    - For all view types (FamilyView, AncestryView, DescendantsView), selection/deselection on valid boxes works identically
  - These tests cover the non-bug-condition cases: interactions with currently-rendered, valid person boxes (where `isBugCondition` returns false)
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 3. Fix for RuntimeError on stale PersonBoxItem access after scene.clear()

  - [x] 3.1 Add QSignalBlocker to suppress selectionChanged during scene clear and rebuild
    - In `slaktbusken/ui/diagram_panel.py`, wrap the `scene.clear()` and render calls in `_refresh_diagram()` with `QSignalBlocker(self._scene)`
    - Import `QSignalBlocker` from `PySide6.QtCore`
    - This prevents `_on_scene_selection_changed()` from firing while the scene is in a transitional state
    - _Bug_Condition: isBugCondition(input) where scene.selectionChanged fires during clear while _person_boxes holds stale refs_
    - _Expected_Behavior: No RuntimeError raised; selectionChanged suppressed during rebuild cycle_
    - _Preservation: After QSignalBlocker scope exits, selectionChanged resumes normal operation for valid items_
    - _Requirements: 2.1, 2.2, 3.1, 3.2, 3.3, 3.4_

  - [x] 3.2 Clear _person_boxes before scene.clear() as defense in depth
    - In `_refresh_diagram()`, before calling `self._scene.clear()`, explicitly clear all view renderers' `_person_boxes` lists:
      - `self._family_view._person_boxes = []`
      - `self._ancestry_view._person_boxes = []`
      - `self._descendants_view._person_boxes = []`
    - This ensures that even if the signal fires unexpectedly, `deselect_all()` iterates an empty list
    - _Bug_Condition: Even if QSignalBlocker fails or is bypassed, empty _person_boxes prevents stale access_
    - _Expected_Behavior: deselect_all() on empty list is a no-op_
    - _Preservation: _person_boxes will be repopulated by the subsequent render() call_
    - _Requirements: 2.1, 2.2_

  - [x] 3.3 Add shiboken6.isValid() guard in deselect_all() across all three view renderers
    - In `FamilyView.deselect_all()`, `AncestryView.deselect_all()`, and `DescendantsView.deselect_all()`:
      - Import `shiboken6`
      - Before calling `box.set_selected(False)`, check `shiboken6.isValid(box)`
      - Skip boxes where the underlying C++ object has been deleted
    - This is defense-in-depth: protects against any code path that might invoke deselect_all() with stale references
    - _Bug_Condition: Guards against RuntimeError even if _person_boxes is not cleared and signal is not blocked_
    - _Expected_Behavior: No RuntimeError; invalid boxes silently skipped_
    - _Preservation: Valid boxes are still deselected normally_
    - _Requirements: 2.1, 2.2, 3.4_

  - [x] 3.4 Add shiboken6.isValid() guard in handle_click() across all three view renderers
    - In `FamilyView.handle_click()`, `AncestryView.handle_click()`, and `DescendantsView.handle_click()`:
      - Before calling `box.set_selected(...)`, check `shiboken6.isValid(box)`
      - Skip boxes where the underlying C++ object has been deleted
    - Consistent with the deselect_all() guard for complete defense-in-depth coverage
    - _Bug_Condition: Guards handle_click() against same class of stale reference errors_
    - _Expected_Behavior: No RuntimeError; invalid boxes silently skipped_
    - _Preservation: Valid boxes still correctly selected/deselected on click_
    - _Requirements: 2.1, 2.2, 3.1_

  - [x] 3.5 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - No RuntimeError on scene clear
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior (no RuntimeError on active person change)
    - When this test passes, it confirms the bug is fixed: `_refresh_diagram()` no longer raises RuntimeError
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2_

  - [x] 3.6 Verify preservation tests still pass
    - **Property 2: Preservation** - Selection behavior unchanged for valid items
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm that clicking person boxes, deselect_all() on valid boxes, handle_click(), and view switching all behave identically to pre-fix behavior

- [x] 4. Checkpoint - Ensure all tests pass
  - Run the full test suite to confirm no regressions
  - Verify bug condition exploration test passes (Property 1)
  - Verify preservation property tests pass (Property 2)
  - Verify no RuntimeError appears in any test output
  - Ensure all tests pass, ask the user if questions arise

## Notes

- The primary fix (QSignalBlocker) prevents the problematic signal chain from ever reaching the handler during rebuild
- Defense-in-depth layers (clearing _person_boxes, shiboken6.isValid() guards) protect against edge cases and future code paths
- All three view renderers (FamilyView, AncestryView, DescendantsView) share the same deselect_all()/handle_click() pattern and need identical fixes
- Property-based tests use Hypothesis to generate random person/box configurations for stronger coverage guarantees
- Test files should be placed in `tests/test_ui/` following existing naming conventions

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1", "2"] },
    { "id": 1, "tasks": ["3.1", "3.2"] },
    { "id": 2, "tasks": ["3.3", "3.4"] },
    { "id": 3, "tasks": ["3.5", "3.6"] },
    { "id": 4, "tasks": ["4"] }
  ]
}
```
