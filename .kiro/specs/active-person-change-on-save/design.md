# Active Person Change on Save Bugfix Design

## Overview

When saving a person via the "Redigera Person" dialog, the active person in the diagram unexpectedly changes. The root cause is that `person_list_panel.refresh()` calls `_apply_current_view()` → `_update_list_widget()` which calls `_tree_widget.clear()`. Clearing the tree triggers Qt's `currentItemChanged` signal (from a selected item to `None`, and then to the first repopulated item), and since `_on_item_clicked` emits `person_selected` which is connected to `diagram_panel.set_active_person`, the active person jumps.

The fix will introduce a guard flag (`_refreshing`) in `PersonListPanel` that suppresses `person_selected` emission during refresh cycles initiated by save operations, analogous to the existing `_syncing_from_diagram` guard.

## Glossary

- **Bug_Condition (C)**: The condition where `person_list_panel.refresh()` triggers `currentItemChanged` during a programmatic list rebuild (not a user click), causing an unintended `person_selected` emission
- **Property (P)**: After saving a person, the active person in the diagram remains unchanged (for existing/affiliated persons) or becomes the new person (for unaffiliated new persons)
- **Preservation**: Normal user click-to-select behavior in the person list must continue to emit `person_selected` and update the active person in the diagram
- **`PersonListPanel.refresh()`**: Method in `slaktbusken/ui/person_list_panel.py` that rebuilds the display list and tree widget from current project data
- **`_on_item_clicked`**: Slot connected to `currentItemChanged` that emits `person_selected` signal
- **`_syncing_from_diagram`**: Existing guard flag that prevents `person_selected` emission when selection is driven by `select_person_from_diagram()`
- **`_refreshing`**: Proposed new guard flag that prevents `person_selected` emission during `refresh()` cycles

## Bug Details

### Bug Condition

The bug manifests when a person is saved via the "Redigera Person" dialog and `person_list_panel.refresh()` is called to update the list. The `refresh()` method calls `_apply_current_view()` → `_update_list_widget()` → `_tree_widget.clear()`, which triggers Qt's `currentItemChanged` signal. Since `_on_item_clicked` does not guard against refresh-driven selection changes, it emits `person_selected` with an unintended person ID.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type SavePersonEvent
  OUTPUT: boolean
  
  RETURN input.trigger == "person_save_dialog"
         AND personListPanel.refresh() is called
         AND currentItemChanged signal fires during refresh
         AND _on_item_clicked emits person_selected with wrong person_id
         AND diagram active person changes unexpectedly
END FUNCTION
```

### Examples

- **Save existing person**: User edits "Anna Svensson" (active person), clicks Save. After refresh, the tree rebuilds and "Erik Johansson" (first in sorted list) becomes active instead of "Anna Svensson".
- **Save new affiliated person**: User adds a child "Karl Svensson" to the current family view. After save, the active person jumps to the first person in the list instead of staying on the previously active person.
- **Save new unaffiliated person**: User creates "Lisa Nilsson" with no family connections. After save, the active person should become "Lisa Nilsson" but instead jumps to the first person in the list.
- **Normal click (non-bug)**: User clicks "Per Andersson" in the person list. The active person correctly changes to "Per Andersson".

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Single-clicking a person in the person list must continue to emit `person_selected` and update the active person in the diagram
- Double-clicking a person must continue to open the person editor
- `select_person_from_diagram()` must continue to select without emitting `person_selected` (existing `_syncing_from_diagram` guard)
- Refreshing the person list after import or other non-save data changes must continue current behavior
- Context menu actions must continue to work as before

**Scope:**
All inputs that do NOT involve a `refresh()` call triggered by a person-save operation should be completely unaffected by this fix. This includes:
- Manual user clicks on person list items
- Diagram-driven selection sync
- Double-click to edit
- Context menu interactions
- Keyboard navigation in the list

## Hypothesized Root Cause

Based on the bug description and code analysis, the root cause is:

1. **Missing guard flag in `_on_item_clicked`**: The `_on_item_clicked` handler checks `_syncing_from_diagram` but has no guard for refresh-driven `currentItemChanged` signals. When `_tree_widget.clear()` is called inside `_update_list_widget()`, Qt emits `currentItemChanged(None, previousItem)` and then potentially `currentItemChanged(firstItem, None)` as items are repopulated, causing unintended `person_selected` emissions.

2. **Signal fires during `clear()` and repopulation**: `_tree_widget.clear()` destroys all items, which deselects the current item and fires `currentItemChanged`. When new items are added and one gets auto-selected, another `currentItemChanged` fires.

3. **No distinction between user-initiated and programmatic selection**: The current code treats all `currentItemChanged` signals equally (except the `_syncing_from_diagram` case), so programmatic changes from `refresh()` are indistinguishable from user clicks.

## Correctness Properties

Property 1: Bug Condition - Save Preserves Active Person

_For any_ save operation where an existing person or a new affiliated person is saved via the "Redigera Person" dialog, the `person_selected` signal SHALL NOT be emitted during the subsequent `refresh()` call, ensuring the diagram's active person remains unchanged.

**Validates: Requirements 2.1, 2.2**

Property 2: Bug Condition - New Unaffiliated Person Becomes Active

_For any_ save operation where a new person with no affiliation to the current view is saved, the system SHALL make that new person the active person via an explicit `set_active_person(saved.id)` call after the refresh completes.

**Validates: Requirements 2.3**

Property 3: Preservation - Click-to-Select Behavior

_For any_ user-initiated single-click on a person in the person list (outside of a refresh cycle and outside of diagram sync), the `person_selected` signal SHALL be emitted with the clicked person's ID, preserving normal selection behavior.

**Validates: Requirements 3.1, 3.4**

Property 4: Preservation - Diagram Sync Behavior

_For any_ diagram-driven person activation (via `select_person_from_diagram`), the person list SHALL select the person without emitting `person_selected`, preserving the existing `_syncing_from_diagram` guard behavior.

**Validates: Requirements 3.2**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `slaktbusken/ui/person_list_panel.py`

**Class**: `PersonListPanel`

**Specific Changes**:

1. **Add `_refreshing` instance variable**: Initialize `self._refreshing = False` in `__init__` alongside the existing `self._syncing_from_diagram = False`.

2. **Guard `refresh()` method**: Wrap the body of `refresh()` with `self._refreshing = True` / `self._refreshing = False` (using try/finally):
   ```python
   def refresh(self) -> None:
       self._refreshing = True
       try:
           # existing refresh logic...
       finally:
           self._refreshing = False
   ```

3. **Update `_on_item_clicked` guard**: Add `self._refreshing` check alongside the existing `_syncing_from_diagram` check:
   ```python
   def _on_item_clicked(self, current, previous):
       if self._syncing_from_diagram or self._refreshing:
           return
       if current is not None:
           person_id = current.data(0, Qt.ItemDataRole.UserRole)
           if person_id:
               self.person_selected.emit(person_id)
   ```

4. **Verify `add_standalone_person` still works**: The existing `panel.set_active_person(saved.id)` call in `app.py` already explicitly sets the new person as active AFTER `refresh()`, so it will continue to work correctly since the guard only suppresses the signal during refresh, not the explicit `set_active_person` call.

5. **No changes needed in `app.py`**: The existing flow in `open_person_editor` (edit existing) does not call `set_active_person` after refresh, which is correct — the active person should not change. The `add_standalone_person` method already calls `set_active_person(saved.id)` after refresh for new unaffiliated persons.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that call `refresh()` on a `PersonListPanel` with an active selection and assert that `person_selected` is NOT emitted. Run these tests on the UNFIXED code to observe failures and confirm the signal leaks during refresh.

**Test Cases**:
1. **Refresh with active selection**: Set person B as current item, call `refresh()`, assert `person_selected` was emitted (will fail on unfixed code — it WILL emit, confirming bug)
2. **Refresh changes active person**: Set person B active in diagram, call `refresh()`, check if diagram's active person changed (will demonstrate the bug)
3. **Clear triggers signal**: Call `_tree_widget.clear()` with an item selected, verify `currentItemChanged` fires (confirms mechanism)

**Expected Counterexamples**:
- `person_selected` signal is emitted during `refresh()` with an ID that differs from the previously active person
- Possible causes: `_tree_widget.clear()` triggers `currentItemChanged`, no guard flag prevents emission

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  active_before := diagram_panel.active_person_id
  personListPanel.refresh()
  active_after := diagram_panel.active_person_id
  ASSERT active_before == active_after
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT personListPanel_original._on_item_clicked(input) == personListPanel_fixed._on_item_clicked(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many random person list states and click sequences to verify normal selection works
- It catches edge cases like clicking during rapid state changes
- It provides strong guarantees that click-to-select behavior is unchanged across all non-refresh scenarios

**Test Plan**: Observe behavior on UNFIXED code for normal clicks and diagram sync, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Click Preservation**: Verify clicking any person in the list emits `person_selected` with correct ID after fix
2. **Diagram Sync Preservation**: Verify `select_person_from_diagram()` still suppresses signal after fix
3. **Double-click Preservation**: Verify double-click still opens editor after fix
4. **Context Menu Preservation**: Verify context menu actions still work after fix

### Unit Tests

- Test that `_refreshing` flag is set during `refresh()` and cleared after
- Test that `_on_item_clicked` does not emit when `_refreshing` is True
- Test that `_on_item_clicked` emits normally when `_refreshing` is False
- Test that `_syncing_from_diagram` guard still works alongside new guard
- Test that `add_standalone_person` correctly sets new person as active after refresh

### Property-Based Tests

- Generate random person lists and verify that `refresh()` never causes `person_selected` emission
- Generate random click sequences on person lists and verify `person_selected` emits the correct person ID each time
- Generate random interleaving of refresh and click operations to verify guards work correctly under all orderings

### Integration Tests

- Test full save-existing-person flow: open editor, save, verify active person unchanged
- Test full add-unaffiliated-person flow: create person, save, verify new person becomes active
- Test that rapid save-then-click sequences work correctly
- Test that diagram sync after a save still works correctly
