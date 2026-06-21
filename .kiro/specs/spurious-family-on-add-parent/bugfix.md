# Bugfix Requirements Document

## Introduction

When a user adds a parent to a person via the context menu ("Ny far"/"Ny mor") or by clicking a placeholder box in the diagram, the `handle_placeholder_click` function creates a new Family record with the target child in the `children` array but **without** any `parent_child_links`. This causes the family tree view and descendants view to display incorrect parent-child relationships — showing the new parent as having extra children they are not actually linked to. The person editor (which uses `ParentService.add_parent`) correctly creates both `children` entries and `parent_child_links`, so the bug only manifests through the placeholder/context-menu path.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a user adds a parent (father or mother) via `handle_placeholder_click` with no existing `family_id` THEN the system creates a Family with `children=[active_id]` but with an empty `parent_child_links` list

1.2 WHEN the descendants view or family view iterates families to find children of the newly added parent THEN the system includes children from the `children` array of families that have no corresponding `parent_child_links`, causing ghost parent-child relationships to appear

1.3 WHEN `_handle_context_add_relative` is used to add a parent to a specific person (not the main active person) THEN the system uses `active_id` from `panel.active_person_id` which may differ from the intended target person, potentially adding the wrong person as a child in the new family

### Expected Behavior (Correct)

2.1 WHEN a user adds a parent (father or mother) via `handle_placeholder_click` with no existing `family_id` THEN the system SHALL create a Family with both `children=[child_id]` and a corresponding `parent_child_links` entry linking the child to the new parent with parentage_type "biological"

2.2 WHEN the descendants view or family view displays children of a person THEN the system SHALL only show children that have a valid `parent_child_links` entry connecting them to that parent, not merely based on presence in a `children` array

2.3 WHEN `_handle_context_add_relative` adds a parent for a specific target person THEN the system SHALL ensure the target person (not the diagram's main active person) is correctly recorded as the child in the new family

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a parent is added via the person editor using `ParentService.add_parent` THEN the system SHALL CONTINUE TO create proper Family records with both `children` and `parent_child_links` entries

3.2 WHEN a child is added via `handle_placeholder_click` (role="child") THEN the system SHALL CONTINUE TO add the new person to the family's `children` list correctly

3.3 WHEN a partner is added via `handle_placeholder_click` (role="partner") THEN the system SHALL CONTINUE TO create a new family with both partners listed

3.4 WHEN a parent is added to an existing family (non-empty `family_id`) THEN the system SHALL CONTINUE TO add the parent as a partner to that existing family without creating duplicates

3.5 WHEN the family view or descendants view displays children with valid `parent_child_links` THEN the system SHALL CONTINUE TO render those parent-child relationships correctly
