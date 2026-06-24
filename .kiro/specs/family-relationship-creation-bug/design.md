# Family Relationship Creation Bugfix Design

## Overview

When adding parents sequentially to a child (e.g., first a father, then a mother) via the context menu or diagram placeholder, the system creates separate single-parent families instead of placing both parents in the same family. The fix will modify `handle_placeholder_click` in `app.py` so that when `family_id` is empty and the role is "father" or "mother", it first searches for an existing family where the child is already a member — matching the behavior already implemented in `ParentService.add_parent`.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug — adding a parent (role="father"/"mother") when `family_id` is empty AND the child already exists as a child in an existing family
- **Property (P)**: The desired behavior — the new parent should be added as a partner to the existing family rather than creating a new family
- **Preservation**: Existing behaviors that must remain unchanged — first parent addition (no existing family), valid `family_id` additions, child additions, partner additions, and person editor flow
- **handle_placeholder_click**: The method in `slaktbusken/app.py` that handles adding new persons via diagram placeholders and context menu
- **ParentService.add_parent**: The method in `slaktbusken/services/parent_service.py` that correctly searches for existing families before creating new ones
- **Family**: A data structure grouping partners, children, and parent_child_links
- **FamilyPartner**: A partner entry within a Family containing person_id and role
- **ParentChildLink**: A link describing parentage (child_id, parent_id, parentage_type)

## Bug Details

### Bug Condition

The bug manifests when a parent is added to a child via a path where `family_id` is empty (context menu always passes `""`, or diagram placeholder with no existing parent family) and the child already exists as a child in another family. The `handle_placeholder_click` function unconditionally creates a new family in its `else` branch (when `family_id` is empty) without checking whether the child already belongs to an existing family.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type {role: string, family_id: string, active_id: string, project_data: ProjectData}
  OUTPUT: boolean
  
  RETURN input.role IN ['father', 'mother']
         AND input.family_id == ''
         AND input.active_id != ''
         AND EXISTS family IN input.project_data.families
             WHERE input.active_id IN family.children
END FUNCTION
```

### Examples

- **Adding a mother after a father (context menu)**: Person "P1" already has a family with father "P2" (family_1: partners=[P2], children=[P1]). User right-clicks P1 and adds mother "P3" → BUG: creates family_2 with partners=[P3], children=[P1] instead of adding P3 to family_1
- **Adding a father after a mother (context menu)**: Person "P1" already has a family with mother "P3" (family_1: partners=[P3], children=[P1]). User right-clicks P1 and adds father "P2" → BUG: creates family_2 with partners=[P2], children=[P1] instead of adding P2 to family_1
- **Adding a father when child has no existing parent family**: Person "P1" has no family where they are a child. User adds father "P2" → CORRECT: creates new family (no bug condition, since no existing family contains P1 as child)
- **Adding a parent via placeholder with valid family_id**: Diagram provides family_id="family_1". User adds mother "P3" → CORRECT: code enters the `if family_id:` branch and adds to existing family (no bug condition)

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Adding a parent to a child that has NO existing family where they are a child must continue to create a new family (first parent addition)
- Adding a parent via a diagram placeholder with a valid non-empty `family_id` must continue to add the parent to the specified family
- Adding a child (role="child") to a family or creating a new family must work exactly as before
- Adding a partner (role="partner") must continue to create a new partner family
- The person editor's `ParentService.add_parent` flow must remain unchanged
- The UI refresh sequence after saving must remain unchanged

**Scope:**
All inputs that do NOT involve adding a parent (role="father"/"mother") with an empty `family_id` while the child already exists in another family should be completely unaffected by this fix. This includes:
- All "child" role operations
- All "partner" role operations
- Parent additions with non-empty `family_id`
- Parent additions where the child has no existing family (first parent)

## Hypothesized Root Cause

Based on the bug description and code analysis, the root cause is clear:

1. **Missing family lookup in the `else` branch**: When `family_id` is empty and role is "father"/"mother", `handle_placeholder_click` unconditionally creates a new family. It never searches `data.families` for an existing family where `active_id` is already in `family.children`.

2. **Context menu always passes empty `family_id`**: The `_handle_context_add_relative` method always calls `handle_placeholder_click(role, "", target_person_id=person_id)`, so the second parent addition always hits the `else` branch.

3. **Contrast with correct implementation**: `ParentService.add_parent` iterates over all families, collects candidates where `child_id in family.children`, and either adds the parent to a candidate family or creates a new one only if no candidate exists.

4. **No deduplication logic**: Unlike `ParentService.add_parent`, `handle_placeholder_click` has no logic to detect that the child is already in a family and merge the new parent into it.

## Correctness Properties

Property 1: Bug Condition - Sequential Parent Addition Uses Existing Family

_For any_ input where a parent (role="father" or "mother") is added with an empty `family_id` and the child (`active_id`) already exists as a child in an existing family, the fixed `handle_placeholder_click` SHALL find that existing family, add the new parent as a partner, and create a `ParentChildLink` in that same family — rather than creating a new separate family.

**Validates: Requirements 2.1, 2.2**

Property 2: Preservation - Non-Bug-Condition Behavior Unchanged

_For any_ input where the bug condition does NOT hold (role is not "father"/"mother", or `family_id` is non-empty, or no existing family contains the child), the fixed `handle_placeholder_click` SHALL produce the same data structure modifications as the original function, preserving first-parent creation, valid-family_id additions, child additions, and partner additions.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `slaktbusken/app.py`

**Function**: `handle_placeholder_click`

**Specific Changes**:

1. **Add family lookup before creating a new family**: In the `else` branch (when `family_id` is empty and role is "father"/"mother"), search `data.families` for an existing family where `active_id` is in `family.children`.

2. **If existing family found — add parent to it**: Append a `FamilyPartner` with the new parent's ID and role to the existing family's `partners` list. Append a `ParentChildLink(child_id=active_id, parent_id=saved.id, parentage_type="biological")` to the existing family's `parent_child_links`.

3. **If no existing family found — create a new family (existing behavior)**: Keep the current new-family creation logic as a fallback for the first parent addition (when no family yet contains the child).

4. **Update context menu comment**: Update the comment in `_handle_context_add_relative` that says "handle_placeholder_click will create a new family" to reflect the new search-first behavior.

5. **Match ParentService pattern**: The lookup logic should mirror `ParentService.add_parent` — iterate families, check if `active_id in family.children`, and use the first matching family.

**Pseudocode for the fix:**
```
# In the else branch for role in ("father", "mother") with empty family_id:

# NEW: Search for existing family where child is already a member
existing_family = None
for f in data.families:
    if active_id in f.children:
        existing_family = f
        break

if existing_family:
    # Add new parent to existing family
    existing_family.partners.append(
        FamilyPartner(person_id=saved.id, role=partner_role)
    )
    existing_family.parent_child_links.append(
        ParentChildLink(child_id=active_id, parent_id=saved.id, parentage_type="biological")
    )
else:
    # No existing family — create new one (first parent addition)
    fam_id = id_gen.generate("family")
    new_family = Family(
        id=fam_id,
        partners=[FamilyPartner(person_id=saved.id, role=partner_role)],
        children=[active_id] if active_id else [],
        parent_child_links=[
            ParentChildLink(child_id=active_id, parent_id=saved.id, parentage_type="biological")
        ] if active_id else [],
    )
    data.families.append(new_family)
```

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Simulate the data-level operations that `handle_placeholder_click` performs when adding a second parent via the context menu. Run these tests on the UNFIXED code to observe that two separate families are created.

**Test Cases**:
1. **Second parent via context menu**: Simulate adding a father to a child that already has a mother-family → assert both parents end up in same family (will fail on unfixed code)
2. **Second parent via empty family_id placeholder**: Simulate adding a mother to a child that already has a father-family → assert single family result (will fail on unfixed code)
3. **Both parents added sequentially**: Add father then mother via context menu → assert single family with 2 partners and 2 parent_child_links (will fail on unfixed code)
4. **Multiple children scenario**: Child already in a family with sibling and one parent → add second parent → assert parent added to same family (will fail on unfixed code)

**Expected Counterexamples**:
- Two separate families created (family_N with father+child, family_M with mother+child) instead of one family with both parents
- Possible cause: the `else` branch unconditionally creates a new family without searching existing families

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := handle_placeholder_click_fixed(input)
  ASSERT exactly_one_family_contains_child(result, input.active_id)
  ASSERT that_family_has_both_parents_as_partners(result, input.active_id)
  ASSERT parent_child_links_exist_for_both_parents(result, input.active_id)
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
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for non-bug-condition inputs (child additions, partner additions, first parent additions, valid family_id parent additions), then write property-based tests capturing that behavior.

**Test Cases**:
1. **First parent preservation**: Verify that when no family contains the child, a new family is still created correctly — observe on unfixed code, then write PBT to verify after fix
2. **Valid family_id parent addition preservation**: Verify that when `family_id` is non-empty, the parent is added to the specified family — observe on unfixed code, then write PBT to verify after fix
3. **Child role preservation**: Verify that adding a child (role="child") continues to work identically — observe on unfixed code, then write PBT to verify after fix
4. **Partner role preservation**: Verify that adding a partner (role="partner") continues to create a new partner family — observe on unfixed code, then write PBT to verify after fix

### Unit Tests

- Test adding a second parent when child already has a family (bug condition) — expect single family
- Test adding first parent when no family exists (non-bug condition) — expect new family created
- Test adding parent with valid `family_id` — expect parent added to specified family
- Test edge case: child in multiple families (e.g., biological + adoptive) — verify correct family is chosen

### Property-Based Tests

- Generate random family configurations where a child exists in a family, then add a parent with empty `family_id` → verify single family contains both parents
- Generate random family configurations where no family contains the child, then add a parent → verify new family created (preservation)
- Generate random non-parent role inputs (child, partner) → verify behavior matches original (preservation)

### Integration Tests

- Full flow: create person, add father via context menu, then add mother via context menu → verify single family in project data
- Full flow: add parent via diagram placeholder (non-empty family_id) → verify added to correct family
- Full flow: add parent via person editor → verify ParentService path still works correctly
