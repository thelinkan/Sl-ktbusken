# Bugfix Requirements Document

## Introduction

When adding parents to a person sequentially (e.g., first a father, then a mother), the system can create separate single-parent families instead of placing both parents in the same family with the child. This results in a broken family view where both parents cannot be displayed together as a couple with their child.

The root cause is in `handle_placeholder_click`: when `family_id` is empty and the role is "father" or "mother", it unconditionally creates a new family rather than first searching for an existing family where the child is already a member. This happens in two known paths:

1. **Context menu path** (`_handle_context_add_relative`): Always passes `family_id=""`, so adding a second parent always creates a separate family.
2. **Diagram placeholder path**: When the child has no existing parent family (first parent addition), the placeholder has `family_id=None`. This is correct for the first parent, but if a subsequent addition also encounters an empty `family_id` (e.g., due to edge cases in diagram rendering or the sequence of operations), a duplicate family is created.

By contrast, the person editor's `ParentService.add_parent` correctly searches for an existing family containing the child before creating a new one. The fix should bring `handle_placeholder_click` in line with this behavior.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a parent is added to a child via a path where `family_id` is empty (context menu or first-time diagram placeholder) and the child already exists as a child in another family THEN the system creates a NEW separate single-parent family instead of adding the new parent to the existing family

1.2 WHEN both parents have been added sequentially via context menu (which always passes `family_id=""`) THEN the resulting data contains two separate families (e.g., family_12 with father+child, family_13 with mother+child) and possibly a third marriage-only family, making it impossible for the family view to display both parents together with their child

### Expected Behavior (Correct)

2.1 WHEN a parent is added to a child (role="father" or "mother") and `family_id` is empty but the child already exists as a child in an existing family THEN the system SHALL find that existing family, add the new parent as a partner, and create a parent_child_link in that same family

2.2 WHEN both parents have been added sequentially (regardless of whether `family_id` was provided or empty) THEN the resulting data SHALL contain a single family with both parents as partners, the child in the children list, and parent_child_links for both parents to the child

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a parent is added to a child that has NO existing family where they are a child (first parent added) THEN the system SHALL CONTINUE TO create a new family with the parent as partner and the child in the children list

3.2 WHEN a parent is added via the diagram placeholder click (with a valid non-empty `family_id`) THEN the system SHALL CONTINUE TO add the parent to the specified existing family

3.3 WHEN a child is added to a family via the placeholder or context menu THEN the system SHALL CONTINUE TO create the child relationship correctly

3.4 WHEN a partner is added via the placeholder or context menu THEN the system SHALL CONTINUE TO create a new partner family correctly

3.5 WHEN a parent is added via the person editor ("Redigera person" → "Lägg till förälder") THEN the system SHALL CONTINUE TO use ParentService.add_parent which already correctly finds existing families
