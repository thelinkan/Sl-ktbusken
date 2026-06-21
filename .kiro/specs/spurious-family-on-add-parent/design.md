# Spurious Family on Add Parent — Bugfix Design

## Overview

When adding a parent via `handle_placeholder_click` (triggered by placeholder clicks or the context menu), a new Family is created with the child listed in `children` but without any `parent_child_links`. This causes the descendants view and family view to display ghost parent-child relationships because they determine children solely by checking the `children` array of families where a person is a partner — without verifying that a `ParentChildLink` actually connects the parent to the child.

The fix addresses three related defects:
1. **Creation bug**: Add missing `parent_child_links` when creating families in `handle_placeholder_click`
2. **Display bug**: Update `_find_children` in `descendants_view.py` (and the equivalent logic in `family_view.py`) to require valid `parent_child_links`
3. **Targeting bug**: Verify `_handle_context_add_relative` correctly passes the target person as the child

## Glossary

- **Bug_Condition (C)**: A parent is added via `handle_placeholder_click` with `family_id=""` (no existing family), creating a Family without `parent_child_links`
- **Property (P)**: When a parent is added, the new Family SHALL contain a `ParentChildLink(child_id=child, parent_id=parent, parentage_type="biological")`; and views SHALL only display children that have valid `parent_child_links`
- **Preservation**: Existing behavior for adding children, partners, and parents to existing families must remain unchanged; `ParentService.add_parent` path continues working correctly
- **handle_placeholder_click**: The function in `slaktbusken/app.py` (~line 340) that creates persons and links them to families when a placeholder box or context menu is used
- **_find_children**: The function in `slaktbusken/ui/views/descendants_view.py` (~line 303) that locates all children of a person by scanning families
- **ParentChildLink**: Dataclass in `slaktbusken/model/family.py` representing a parent-child relationship with `child_id`, `parent_id`, and `parentage_type`
- **ParentService.add_parent**: The correct reference implementation in `slaktbusken/services/parent_service.py` that properly creates `parent_child_links`

## Bug Details

### Bug Condition

The bug manifests when a user adds a parent (father or mother) through the placeholder click path with no existing family. The `handle_placeholder_click` function creates a `Family` with `children=[active_id]` but with an empty `parent_child_links` list. Subsequently, the display functions (`_find_children` in `descendants_view.py` and the child-rendering logic in `family_view.py`) treat any person in a family's `children` array as a child of every partner in that family, regardless of whether a `ParentChildLink` exists.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type PlaceholderClickInput
  OUTPUT: boolean
  
  RETURN input.role IN ['father', 'mother']
         AND input.family_id = ''
         AND input.active_id IS NOT NULL
END FUNCTION
```

A secondary bug condition exists in the display layer:
```
FUNCTION isDisplayBugCondition(family, person_id)
  INPUT: family of type Family, person_id of type str
  OUTPUT: boolean
  
  RETURN person_id IN [p.person_id FOR p IN family.partners]
         AND family.children IS NOT EMPTY
         AND NOT EXISTS link IN family.parent_child_links
             WHERE link.parent_id = person_id
                   AND link.child_id IN family.children
END FUNCTION
```

### Examples

- **Example 1**: User right-clicks on "Anna" and selects "Ny far". A new person "Erik" is created. A Family is created with `partners=[FamilyPartner(person_id="Erik", role="father")]` and `children=["Anna"]` but `parent_child_links=[]`. The descendants view now shows "Anna" as a child of "Erik" even though no `ParentChildLink` exists.

- **Example 2**: User clicks the father placeholder above "Karl" in the family view. A new person "Lars" is created. Same defect — no `ParentChildLink`. Both the family view and descendants view show "Karl" as a descendant of "Lars" without proper linkage.

- **Example 3**: User adds a parent via the person editor's "Lägg till förälder" (which uses `ParentService.add_parent`). This correctly creates a `ParentChildLink(child_id="Karl", parent_id="Lars", parentage_type="biological")`. No bug here — this is the reference implementation.

- **Edge case**: If `active_id` is `None` (no active person), the family is created with `children=[]` — no children are incorrectly shown because the list is empty. This case is unaffected.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- `ParentService.add_parent` must continue to create proper Family records with both `children` and `parent_child_links` entries
- Adding a child via `handle_placeholder_click` (role="child") must continue to add the child to the family's `children` list correctly
- Adding a partner via `handle_placeholder_click` (role="partner") must continue to create a family with both partners
- Adding a parent to an existing family (non-empty `family_id`) must continue to add the parent as a partner to that family
- Views must continue to render children that have valid `parent_child_links` correctly
- Mouse clicks, editor dialogs, and all other UI interactions remain unchanged

**Scope:**
All inputs where `role` is NOT "father"/"mother" OR where `family_id` is NOT empty should be completely unaffected by this fix. Specifically:
- `role="child"` placeholder clicks
- `role="partner"` placeholder clicks
- `role="father"/"mother"` with a non-empty `family_id` (adding to existing family)
- All `ParentService` operations

## Hypothesized Root Cause

Based on the code analysis, the root causes are:

1. **Missing `parent_child_links` in family creation** (`app.py`, `handle_placeholder_click`):
   The code at the `else` branch (no existing `family_id`) creates:
   ```python
   new_family = Family(
       id=fam_id,
       partners=[FamilyPartner(person_id=saved.id, role=partner_role)],
       children=[active_id] if active_id else [],
   )
   ```
   This omits `parent_child_links`. The correct pattern (from `ParentService.add_parent`) is:
   ```python
   Family(
       id=new_family_id,
       partners=[FamilyPartner(person_id=parent_id, role=role)],
       children=[child_id],
       parent_child_links=[ParentChildLink(child_id=child_id, parent_id=parent_id, parentage_type="biological")],
   )
   ```

2. **Naive child lookup in `_find_children`** (`descendants_view.py`):
   The function checks if a person is a partner in a family, then returns ALL children from that family's `children` list without verifying `parent_child_links`:
   ```python
   def _find_children(project_data, person_id):
       children = []
       for family in project_data.families:
           is_partner = any(partner.person_id == person_id for partner in family.partners)
           if is_partner:
               for child_id in family.children:
                   if child_id not in children:
                       children.append(child_id)
       return children
   ```
   This should filter by `parent_child_links` existence.

3. **Same pattern in `family_view.py`** (line ~380):
   The family view directly iterates `family.children` to render child boxes below each spouse without checking `parent_child_links`.

4. **Context menu targeting** (`_handle_context_add_relative`):
   Sets `panel._active_person_id = person_id` before calling `handle_placeholder_click`. The function then reads `active_id = self.main_window.diagram_panel.active_person_id`. This should work correctly since `_active_person_id` is set immediately before the call. However, the original `active_person_id` should be restored after the operation (which the code already does).

## Correctness Properties

Property 1: Bug Condition - Family Creation Includes ParentChildLink

_For any_ input where a parent (father or mother) is added via `handle_placeholder_click` with an empty `family_id` and a non-null `active_id`, the newly created Family SHALL contain a `ParentChildLink` with `child_id=active_id`, `parent_id=saved_person_id`, and `parentage_type="biological"`.

**Validates: Requirements 2.1, 2.3**

Property 2: Preservation - Non-Parent Placeholder Operations Unchanged

_For any_ input where the role is "child" or "partner", OR where `family_id` is non-empty, the fixed code SHALL produce the same Family structure as the original code, preserving all existing functionality for non-parent-creation operations.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

**File**: `slaktbusken/app.py`

**Function**: `handle_placeholder_click`

**Specific Changes**:
1. **Add `ParentChildLink` import**: Import `ParentChildLink` from `slaktbusken.model.family` (already importing `Family` and `FamilyPartner` from the same module)

2. **Add `parent_child_links` to new family creation**: In the `else` branch of the `if family_id:` check within `role in ("father", "mother")`, add:
   ```python
   new_family = Family(
       id=fam_id,
       partners=[FamilyPartner(person_id=saved.id, role=partner_role)],
       children=[active_id] if active_id else [],
       parent_child_links=[
           ParentChildLink(child_id=active_id, parent_id=saved.id, parentage_type="biological")
       ] if active_id else [],
   )
   ```

**File**: `slaktbusken/ui/views/descendants_view.py`

**Function**: `_find_children`

**Specific Changes**:
3. **Filter children by `parent_child_links`**: Change `_find_children` to only return children that have a `ParentChildLink` connecting them to the specified parent:
   ```python
   def _find_children(project_data, person_id):
       children = []
       for family in project_data.families:
           is_partner = any(
               partner.person_id == person_id for partner in family.partners
           )
           if is_partner:
               for child_id in family.children:
                   has_link = any(
                       link.child_id == child_id and link.parent_id == person_id
                       for link in family.parent_child_links
                   )
                   if has_link and child_id not in children:
                       children.append(child_id)
       return children
   ```

**File**: `slaktbusken/ui/views/family_view.py`

**Function**: `render` (Step 4 — children rendering below spouse)

**Specific Changes**:
4. **Filter children in family view**: Where the code iterates `family.children` to render child boxes, add a filter to only include children with valid `parent_child_links` for the sibling (the person whose children are being shown):
   ```python
   children_ids = [
       cid for cid in family.children
       if any(
           link.child_id == cid and link.parent_id == box.person_id
           for link in family.parent_child_links
       )
   ]
   ```

5. **Verify context menu targeting**: Confirm that `_handle_context_add_relative` correctly sets and restores `_active_person_id`. Based on code analysis, this is already handled correctly — the active person is set before `handle_placeholder_click` and restored afterward.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis.

**Test Plan**: Create unit-level tests that simulate calling `handle_placeholder_click` logic (or directly constructing families the same way) and verify that `parent_child_links` is populated. Also test `_find_children` with families that have children but no links.

**Test Cases**:
1. **Creation Test**: Create a Family the same way `handle_placeholder_click` does (with role="father", empty family_id). Assert `parent_child_links` is non-empty. (Will fail on unfixed code)
2. **Display Test**: Create a Family with `children=["child1"]` but empty `parent_child_links`. Call `_find_children` for a partner. Assert it returns empty list. (Will fail on unfixed code — it returns ["child1"])
3. **Combined Test**: Simulate the full flow: create family without links, then check `_find_children`. Assert no ghost children appear. (Will fail on unfixed code)

**Expected Counterexamples**:
- `_find_children` returns children that have no `ParentChildLink` connecting them to the parent
- New families created via placeholder path have `parent_child_links == []`

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  family := create_family_via_placeholder_fixed(input)
  ASSERT len(family.parent_child_links) > 0
  ASSERT family.parent_child_links[0].child_id = input.active_id
  ASSERT family.parent_child_links[0].parent_id = input.saved_person_id
  ASSERT family.parent_child_links[0].parentage_type = "biological"
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT handle_placeholder_click_original(input) = handle_placeholder_click_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many family configurations automatically
- It catches edge cases with various combinations of roles and family_ids
- It provides strong guarantees that child/partner creation paths are unchanged

**Test Plan**: Observe behavior on UNFIXED code for non-parent-creation cases (child, partner, existing family_id), then write property-based tests capturing that behavior.

**Test Cases**:
1. **Child Addition Preservation**: Verify adding a child (role="child") continues to append to `family.children` correctly
2. **Partner Addition Preservation**: Verify adding a partner (role="partner") creates a family with both partners
3. **Existing Family Preservation**: Verify adding a parent to an existing family still appends as partner
4. **Display Preservation**: Verify `_find_children` still returns children that DO have valid `parent_child_links`

### Unit Tests

- Test `handle_placeholder_click` creates `ParentChildLink` for father/mother with empty family_id
- Test `_find_children` only returns children with valid links
- Test family view child rendering only shows linked children
- Test edge cases: no active_id, empty children list, multiple families

### Property-Based Tests

- Generate random family structures and verify `_find_children` only returns children with valid `parent_child_links`
- Generate random placeholder click inputs and verify the creation/preservation boundary
- Generate random project data and verify descendants view consistency

### Integration Tests

- Test full flow: add parent via context menu, verify correct family structure
- Test descendants view shows correct tree after parent addition
- Test family view renders correctly after parent addition via placeholder
