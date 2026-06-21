# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Family Creation Missing ParentChildLink
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists in both family creation and child display
  - **Scoped PBT Approach**: Scope the property to the concrete failing cases:
    - Create a Family the same way `handle_placeholder_click` does (role="father" or "mother", empty `family_id`, non-null `active_id`) and assert `parent_child_links` is non-empty with correct `child_id`, `parent_id`, and `parentage_type="biological"`
    - Create a Family with `children=["child1"]` but empty `parent_child_links`, call `_find_children` for a partner, and assert it returns an empty list (not ghost children)
  - **Bug Condition** (from design): `isBugCondition(input)` where `input.role IN ['father', 'mother'] AND input.family_id = '' AND input.active_id IS NOT NULL`
  - **Display Bug Condition**: `isDisplayBugCondition(family, person_id)` where person is a partner, `family.children` is non-empty, but no `parent_child_links` connect that parent to those children
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct — it proves the bug exists)
  - Document counterexamples: e.g., `handle_placeholder_click(role="father", family_id="", active_id="person1")` creates Family with `parent_child_links=[]`; `_find_children` returns `["person1"]` despite no link existing
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Non-Parent Placeholder Operations Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Observe behavior on UNFIXED code for non-buggy inputs:
    - Observe: `handle_placeholder_click(role="child", ...)` adds new person to `family.children` correctly
    - Observe: `handle_placeholder_click(role="partner", ...)` creates family with both partners
    - Observe: `handle_placeholder_click(role="father", family_id="existing_fam", ...)` adds parent as partner to existing family
    - Observe: `_find_children` returns children that DO have valid `parent_child_links` connecting them to the parent
  - Write property-based tests capturing observed behavior:
    - For all inputs where role is "child" or "partner": family structure matches original behavior
    - For all inputs where `family_id` is non-empty: parent added as partner without duplicates
    - For all families where children have valid `parent_child_links`: `_find_children` returns those children correctly
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3. Fix spurious family on add parent

  - [x] 3.1 Fix `handle_placeholder_click` to include ParentChildLink
    - Add `ParentChildLink` import from `slaktbusken.model.family`
    - In the `else` branch (no existing `family_id`) within `role in ("father", "mother")`, add `parent_child_links` to the new Family:
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
    - _Bug_Condition: isBugCondition(input) where input.role IN ['father','mother'] AND input.family_id = '' AND input.active_id IS NOT NULL_
    - _Expected_Behavior: new Family SHALL contain ParentChildLink(child_id=active_id, parent_id=saved.id, parentage_type="biological")_
    - _Preservation: role="child", role="partner", and non-empty family_id paths remain unchanged_
    - _Requirements: 2.1, 2.3_

  - [x] 3.2 Fix `_find_children` in `descendants_view.py`
    - Update the function to only return children that have a valid `parent_child_links` connecting them to the specified parent:
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
    - _Bug_Condition: isDisplayBugCondition — person is partner, children exist, but no parent_child_links connect them_
    - _Expected_Behavior: _find_children SHALL only return children with valid ParentChildLink_
    - _Requirements: 2.2_

  - [x] 3.3 Fix child rendering in `family_view.py`
    - Update the family view's child rendering to filter by `parent_child_links`:
      ```python
      children_ids = [
          cid for cid in family.children
          if any(
              link.child_id == cid and link.parent_id == box.person_id
              for link in family.parent_child_links
          )
      ]
      ```
    - _Bug_Condition: Same display bug — children rendered without link validation_
    - _Expected_Behavior: Family view SHALL only render children with valid ParentChildLink for the displayed parent_
    - _Requirements: 2.2_

  - [x] 3.4 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Family Creation Includes ParentChildLink
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.5 Verify preservation tests still pass
    - **Property 2: Preservation** - Non-Parent Placeholder Operations Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all preservation tests still pass after fix (no regressions)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 4. Checkpoint - Ensure all tests pass
  - Run the full test suite to ensure no regressions
  - Verify bug condition test passes (bug is fixed)
  - Verify preservation tests pass (no regressions)
  - Ensure all other existing tests in the project still pass
  - Ask the user if questions arise
