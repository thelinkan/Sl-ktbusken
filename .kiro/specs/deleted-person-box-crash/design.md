# Deleted PersonBoxItem Crash Bugfix Design

## Overview

When the active person is changed in the diagram view, `DiagramPanel._refresh_diagram()` calls `QGraphicsScene.clear()`, which destroys all C++ `QGraphicsItem` objects in the scene. However, the view renderers (`FamilyView`, `AncestryView`, `DescendantsView`) retain Python references to those `PersonBoxItem` instances in their `_person_boxes` lists. The `selectionChanged` signal fires during or immediately after `scene.clear()` (because clearing deselects items), which triggers `_on_scene_selection_changed()` → `deselect_all()` → iterates the stale `_person_boxes` list → calls `set_selected(False)` → `self.update()` on a deleted C++ object, raising `RuntimeError`.

The fix will ensure that stale references are never accessed after `scene.clear()`. The primary strategy is to clear `_person_boxes` lists **before** calling `scene.clear()`, or to guard `deselect_all()` against deleted objects, or to block the `selectionChanged` signal during the clear/rebuild cycle.

## Glossary

- **Bug_Condition (C)**: The `selectionChanged` signal fires after `scene.clear()` while `_person_boxes` still references destroyed C++ objects
- **Property (P)**: No `RuntimeError` is raised; stale references are not accessed after their underlying C++ objects are destroyed
- **Preservation**: Existing click-to-select, double-click-to-edit, view switching, and visual selection behavior must remain unchanged
- **PersonBoxItem**: A `QGraphicsItem` subclass in `slaktbusken/ui/widgets/person_box.py` that displays a person's information in the diagram
- **_person_boxes**: A `list[PersonBoxItem]` maintained by each view renderer (`FamilyView`, `AncestryView`, `DescendantsView`) tracking all person box items currently in the scene
- **deselect_all()**: Method on each view renderer that iterates `_person_boxes` and calls `set_selected(False)` on each item
- **_refresh_diagram()**: Method on `DiagramPanel` that calls `scene.clear()` and then re-renders the diagram via the active view renderer
- **_on_scene_selection_changed()**: Slot connected to `QGraphicsScene.selectionChanged` that calls `deselect_all()` on all view renderers when no items are selected

## Bug Details

### Bug Condition

The bug manifests when the active person is changed (or any action that triggers `_refresh_diagram()`). The `QGraphicsScene.clear()` call destroys C++ objects, but the `selectionChanged` signal fires during or after the clear. The `_on_scene_selection_changed()` handler then calls `deselect_all()` on view renderers that still hold references to the destroyed objects in `_person_boxes`.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type DiagramRefreshEvent
  OUTPUT: boolean
  
  RETURN input.triggers_scene_clear == True
         AND view._person_boxes is not empty (references from previous render)
         AND scene.selectionChanged signal fires during or after clear
         AND deselect_all() is called on stale _person_boxes references
END FUNCTION
```

### Examples

- User changes active person from Person A to Person B → `_refresh_diagram()` → `scene.clear()` destroys PersonBoxItem C++ objects → `selectionChanged` fires → `deselect_all()` calls `set_selected(False)` on destroyed objects → **RuntimeError**
- User switches from Family view to Ancestry view → `_refresh_diagram()` → same chain → **RuntimeError**
- User updates person box config (show/hide fields) → `_refresh_diagram()` → same chain → **RuntimeError**
- Second and subsequent active person changes do NOT trigger the error because `_person_boxes` was cleared by the first `render()` call before `scene.clear()` on the next cycle (the crash only occurs the first time because the initial `_person_boxes` references haven't been refreshed yet)

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Clicking a person box in the diagram SHALL continue to visually select that box and deselect all others
- Double-clicking a person box SHALL continue to emit `person_double_clicked` and open the editor
- Switching between Family, Ancestry, and Descendants views SHALL continue to render correctly
- `deselect_all()` called on a view with valid (non-deleted) person boxes SHALL continue to deselect all boxes without error
- The `selectionChanged` signal SHALL continue to propagate selection state for valid items

**Scope:**
All inputs that do NOT involve `_refresh_diagram()` clearing the scene while stale `_person_boxes` exist should be completely unaffected by this fix. This includes:
- Mouse click selection on currently-rendered person boxes
- Keyboard (A-key) activation of selected person
- Double-click editing
- Right-click context menu
- Zoom/pan interactions

## Hypothesized Root Cause

Based on the bug description and code analysis, the root cause is:

1. **Missing reference invalidation before scene.clear()**: `_refresh_diagram()` calls `self._scene.clear()` at line ~423 of `diagram_panel.py` without first clearing the `_person_boxes` lists on the view renderers. The view's `render()` method does `self._person_boxes = []` at the start, but `scene.clear()` happens BEFORE `render()` is called.

2. **selectionChanged signal fires during scene.clear()**: When `QGraphicsScene.clear()` removes items, Qt deselects them first, which emits `selectionChanged`. This signal is connected to `_on_scene_selection_changed()`, which calls `deselect_all()` on all three view renderers.

3. **deselect_all() has no guard against deleted C++ objects**: The method unconditionally iterates `_person_boxes` and calls `box.set_selected(False)`, which calls `self.update()` — a method on the underlying C++ `QGraphicsItem` that has already been destroyed.

4. **Timing**: The bug only occurs on the FIRST refresh because initially `_person_boxes` is populated from a previous `render()` call and hasn't been cleared yet. On subsequent refreshes, the `render()` call from the previous refresh already reset `_person_boxes = []`, so by the time `scene.clear()` fires next, the list is already empty (since the new render call clears it first at the top of `render()`).

## Correctness Properties

Property 1: Bug Condition - No RuntimeError on scene clear

_For any_ diagram refresh event where `_refresh_diagram()` is called (active person change, view switch, config update), the system SHALL NOT raise a `RuntimeError` when the `selectionChanged` signal fires during or after `scene.clear()`, regardless of whether `_person_boxes` previously held references to now-destroyed items.

**Validates: Requirements 2.1, 2.2**

Property 2: Preservation - Selection behavior unchanged for valid items

_For any_ user interaction (mouse click, keyboard) on currently-rendered, valid person boxes in the scene, the system SHALL produce the same selection/deselection behavior as the original code, preserving visual selection highlighting, `person_selected` signal emission, and `deselect_all()` functionality on non-deleted items.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `slaktbusken/ui/diagram_panel.py`

**Function**: `_refresh_diagram()`

**Specific Changes**:

1. **Block selectionChanged during clear/rebuild**: Use `QSignalBlocker` (or manually disconnect/reconnect) on `self._scene` to suppress the `selectionChanged` signal during `scene.clear()` and the subsequent `render()` call. This prevents `_on_scene_selection_changed()` from being invoked while the scene is in a transitional state.

   ```python
   from PySide6.QtCore import QSignalBlocker
   
   with QSignalBlocker(self._scene):
       self._scene.setSceneRect(QRectF())
       self._scene.clear()
       # ... render calls ...
   ```

2. **Clear _person_boxes before scene.clear() (defense in depth)**: Before calling `scene.clear()`, explicitly clear the view renderers' `_person_boxes` lists so that even if the signal fires, `deselect_all()` iterates an empty list:

   ```python
   self._family_view._person_boxes = []
   self._ancestry_view._person_boxes = []
   self._descendants_view._person_boxes = []
   ```

3. **Add sip.isdeleted() guard in deselect_all() (defense in depth)**: In each view's `deselect_all()` method, add a safety check using `sip.isdeleted()` (PySide6 equivalent: check if the object's C++ wrapper is still valid) before calling methods on each box:

   ```python
   import shiboken6
   
   def deselect_all(self) -> None:
       self.selected_person_id = None
       for box in self._person_boxes:
           try:
               if shiboken6.isValid(box):
                   box.set_selected(False)
           except RuntimeError:
               pass
   ```

4. **Same guard in handle_click()**: Apply the same validity check in `handle_click()` for consistency:

   ```python
   def handle_click(self, person_id: str) -> None:
       self.selected_person_id = person_id
       for box in self._person_boxes:
           if shiboken6.isValid(box):
               box.set_selected(box.person_id == person_id)
   ```

5. **Apply to all three views**: The same fix pattern must be applied to `FamilyView`, `AncestryView`, and `DescendantsView` since all three share the same `deselect_all()` and `handle_click()` pattern.

**Recommended approach**: Use `QSignalBlocker` as the primary fix (option 1) since it cleanly prevents the problematic signal from reaching the handler during the rebuild cycle. Add the `shiboken6.isValid()` guard (option 3/4) as defense-in-depth to protect against any other code paths that might call methods on stale references.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that simulate the active person change flow by calling `set_active_person()` on a `DiagramPanel` that has already rendered a diagram. Monitor for `RuntimeError` exceptions. Run these tests on the UNFIXED code to observe failures and understand the root cause.

**Test Cases**:
1. **First Active Person Change**: Set up DiagramPanel with initial person, then change to a different person (will raise RuntimeError on unfixed code)
2. **View Switch After Render**: Render in Family view, then switch to Ancestry view (will raise RuntimeError on unfixed code)
3. **Config Change After Render**: Render diagram, then change PersonBoxConfig (will raise RuntimeError on unfixed code)
4. **Multiple Rapid Changes**: Change active person multiple times in quick succession (may raise RuntimeError on unfixed code)

**Expected Counterexamples**:
- `RuntimeError: Internal C++ object (PersonBoxItem) already deleted` raised in `deselect_all()` or `handle_click()`
- Root cause confirmed: `selectionChanged` fires after `scene.clear()` and `_person_boxes` still holds stale references

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := _refresh_diagram_fixed(input)
  ASSERT no RuntimeError raised
  ASSERT diagram renders correctly after refresh
  ASSERT _person_boxes contains only valid references
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT click_selection_original(input) = click_selection_fixed(input)
  ASSERT double_click_original(input) = double_click_fixed(input)
  ASSERT view_rendering_original(input) = view_rendering_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain (random person configurations, random click sequences)
- It catches edge cases that manual unit tests might miss (e.g., empty person lists, single-person diagrams)
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for mouse clicks and normal selection, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Click Selection Preservation**: Verify clicking person boxes continues to select them visually and emit signals after fix
2. **Deselect All Preservation**: Verify `deselect_all()` on valid (non-deleted) boxes works identically
3. **View Switching Preservation**: Verify switching views still renders correct diagrams
4. **Double-Click Preservation**: Verify double-click continues to emit `person_double_clicked`

### Unit Tests

- Test that `_refresh_diagram()` does not raise RuntimeError when called repeatedly
- Test that `deselect_all()` safely handles empty `_person_boxes` list
- Test that `deselect_all()` safely handles list with deleted C++ objects (using `shiboken6.isValid()`)
- Test that `handle_click()` safely handles list with deleted C++ objects
- Test that signal blocker prevents `_on_scene_selection_changed` during `scene.clear()`

### Property-Based Tests

- Generate random sequences of active person changes and verify no RuntimeError is raised
- Generate random person configurations (varying numbers of family members) and verify selection works correctly after refresh
- Generate random interleaving of clicks and active person changes to verify preservation of selection behavior

### Integration Tests

- Test full flow: load project → render diagram → change active person → verify no error and diagram updates
- Test view switching: render in each view type, switch between them, verify no error
- Test rapid navigation: change active person multiple times quickly, verify stability
