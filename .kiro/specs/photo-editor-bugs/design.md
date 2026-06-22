# Photo Editor Bugs — Bugfix Design

## Overview

Five bugs exist in `FotoTab`, `PersonEditor`, and `PersonListWidget` related to photo management in the "Redigera Person" dialog:

1. **Person list not persisted on save** — `PersonEditor._on_save()` does not flush pending FotoTab person-list changes before emitting `save_requested`, so edits to "Personer i bilden" are silently lost unless the user manually clicks "Spara personlista" first.
2. **No way to delete/unlink a photo** — The FotoTab UI has an "Lägg till foto" button but no corresponding "Ta bort foto" button, leaving users with no way to remove a photo from a person.
3. **Person not auto-added to photo's person list** — `FotoTab._on_add_photo()` creates a `LinkedEntity` for the person but does not add the person's ID to `mentioned_person_ids`, so the person doesn't appear in "Personer i bilden" for the newly added photo.
4. **Cannot distinguish persons with same name in person search** — `_person_display_name()` in `PersonListWidget` returns only "given surname" with no year info. When multiple persons share a name, the user cannot tell them apart in the combo box.
5. **Tilltalsnamn marker (*) breaks person search** — The `*` character in given names (marking the calling name) is included in the display text, causing QCompleter to fail matching when the user types the name without `*`.

The fix strategy is minimal and localized: flush pending changes in `_on_save`, add a delete button with proper unlinking logic, append the person to `mentioned_person_ids` during photo creation, enhance `_person_display_name()` with birth/death years, and strip `*` from display text.

## Glossary

- **Bug_Condition (C)**: The set of conditions under which each bug manifests — pending unsaved person-list edits at save time, desire to unlink a photo, a freshly added photo missing its owner in `mentioned_person_ids`, duplicate names without disambiguation, or `*` in display text breaking search
- **Property (P)**: The desired correct behavior — automatic persistence, UI affordance for deletion, auto-inclusion of person in mentions, year-disambiguated display names, and `*`-free search text
- **Preservation**: Existing behaviors (mouse clicks, metadata editing, profile photo selection, explicit "Spara personlista", non-starred name display, single-name-variant persons) that must remain unchanged
- **FotoTab**: Widget in `slaktbusken/ui/widgets/foto_tab.py` managing photos linked to a person
- **PersonEditor**: Dialog in `slaktbusken/ui/editors/person_editor.py` that edits a Person and contains FotoTab
- **PersonListWidget**: Widget in `slaktbusken/ui/widgets/person_list_widget.py` managing "Personer i bilden" with a searchable combo box
- **MediaItem**: Dataclass in `slaktbusken/model/media.py` representing a photo with `linked_entities`, `mentioned_person_ids`, and `mentioned_names`
- **LinkedEntity**: Dataclass linking a MediaItem to an entity (person, event, etc.)
- **PhotoService**: Service in `slaktbusken/services/photo_service.py` with photo business logic including `sync_linked_entities`
- **`_person_display_name()`**: Module-level helper in `person_list_widget.py` that formats a Person's name for display in the combo box and QCompleter
- **Tilltalsnamn**: Swedish concept — the name a person is commonly called by, marked with `*` after the given name (e.g., "Karl Erik*" means "Erik" is the calling name)
- **`get_person_birth_death_years()`**: Utility in `slaktbusken/ui/person_list_panel.py` that extracts birth/death years from a Person's events

## Bug Details

### Bug Condition

The bugs manifest in five distinct scenarios within the photo management and person search workflow. Each has a separate trigger condition but bugs 4 and 5 share the same affected function (`_person_display_name`).

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type UserAction
  OUTPUT: boolean

  // Bug 1: Pending person-list changes lost on save
  IF input.action == "save_person"
     AND fotoTab.save_persons_btn.isEnabled()  // pending unsaved changes exist
     AND input.did_not_click_save_persons_first
  THEN RETURN TRUE

  // Bug 2: No delete affordance
  IF input.action == "wants_to_unlink_photo"
     AND input.photo_is_selected
  THEN RETURN TRUE  // No button exists to perform this

  // Bug 3: Person not in mentioned_person_ids after add
  IF input.action == "add_photo_to_person"
     AND person.id NOT IN new_media_item.mentioned_person_ids
  THEN RETURN TRUE

  // Bug 4: Duplicate names without disambiguation
  IF input.action == "search_person_in_combo"
     AND EXISTS person1, person2 IN project_data.persons
       WHERE person1.id != person2.id
       AND _person_display_name(person1) == _person_display_name(person2)
  THEN RETURN TRUE

  // Bug 5: Tilltalsnamn marker breaks search
  IF input.action == "search_person_in_combo"
     AND input.person.names[0].given CONTAINS "*"
     AND input.search_text == name_without_star
     AND QCompleter fails to match
  THEN RETURN TRUE

  RETURN FALSE
END FUNCTION
```

### Examples

- **Bug 1**: User selects a photo, adds "Erik Andersson" to "Personer i bilden", then clicks "Spara" on the person editor → `mentioned_person_ids` remains unchanged (Erik not added)
- **Bug 2**: User accidentally adds the wrong photo to a person → no button or menu exists to remove it
- **Bug 3**: User adds a photo to "Anna Svensson" → photo's `mentioned_person_ids` is `[]` instead of `["anna-id"]`, so Anna doesn't appear in "Personer i bilden"
- **Bug 4**: Project has two persons named "Erik Andersson" (one born 1845, one born 1902). Combo box shows both as "Erik Andersson" — user cannot tell which is which
- **Bug 5**: Person with given name "Karl Erik*" appears in combo box as "Karl Erik* Andersson". User types "Erik Andersson" → QCompleter finds no match because stored text is "Karl Erik* Andersson"
- **Edge case (Bug 1)**: User modifies person list, clicks "Spara personlista", then modifies it again and clicks "Spara" → second modification is lost
- **Edge case (Bug 4)**: Person has no birth or death events → display shows name only, no empty parentheses
- **Edge case (Bug 5)**: Person with given name "Erik" (no star) → display unchanged, "Erik Andersson" still works

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Adding a new photo via "Lägg till foto" must continue to copy the file to Foto_Mapp, create a MediaItem with a LinkedEntity, and display it in the photo table
- Editing photo metadata (title, Foto_Typ) and clicking "Spara ändringar" must continue to update the MediaItem title in `[Foto_Typ] title` format
- Clicking "Spara personlista" explicitly must continue to persist person list changes immediately
- Selecting a photo in the table must continue to display the metadata editing panel, person list section, and image preview
- Setting a profile photo via "Välj som profilbild" must continue to store the media ID as `profile_media_id` on the Person
- Non-photo tabs (names, events, DNA, parents) must remain completely unaffected
- Persons whose names do NOT contain `*` must continue to display and search correctly as before
- Persons with only one name variant and no birth/death data must display without parenthetical year info (no empty parentheses)
- Selecting a person from the combo box and clicking "Lägg till" must continue to add the person to the list and emit `persons_changed`

**Scope:**
All inputs that do NOT involve:
- Saving with pending person-list changes
- Deleting/unlinking a photo
- The auto-addition of person to `mentioned_person_ids` on photo add
- Person name display in the PersonListWidget combo box

should be completely unaffected by these fixes.

## Hypothesized Root Cause

Based on analysis of the source code:

1. **Bug 1 — Missing flush in `_on_save`**: `PersonEditor._on_save()` (line 1818) collects person data and emits `save_requested` but never calls `self._foto_tab._on_save_persons()` or any equivalent flush method. The `_save_persons_btn.isEnabled()` state indicates pending changes, but nothing checks or acts on it before save.

2. **Bug 2 — Missing UI element and handler**: `FotoTab._setup_ui()` creates only an "Lägg till foto" button. There is no "Ta bort foto" button, no delete handler method, and no logic to remove a `LinkedEntity` from a `MediaItem` (and potentially remove the entire `MediaItem` if no linked entities remain).

3. **Bug 3 — Missing `mentioned_person_ids` assignment**: `FotoTab._on_add_photo()` (line 470) creates a new `MediaItem` with `linked_entities=[LinkedEntity(entity_type="person", entity_id=self._person.id)]` but does not set `mentioned_person_ids=[self._person.id]`. The field defaults to an empty list.

4. **Bug 4 — `_person_display_name()` lacks year disambiguation**: The function at line 33 in `person_list_widget.py` returns only `f"{name.given} {name.surname}".strip()`. It has no access to events and does not include birth/death years. The `SelectMainPersonDialog` already implements this pattern using `get_person_birth_death_years()` from `person_list_panel.py`, but `PersonListWidget` does not use it.

5. **Bug 5 — `_person_display_name()` does not strip `*`**: The function directly uses `name.given` which may contain a trailing `*` (tilltalsnamn marker). This `*` is part of the data model convention but is not a displayable character. Since the combo box text is fed to QCompleter, the `*` causes match failures when the user types the name naturally.

## Correctness Properties

Property 1: Bug Condition — Person list changes persisted on save

_For any_ state where the user has modified the person list in FotoTab (i.e., `_save_persons_btn.isEnabled() == True`) and then triggers `PersonEditor._on_save()`, the system SHALL flush those pending changes to the MediaItem's `mentioned_person_ids`, `mentioned_names`, and `linked_entities` before completing the save.

**Validates: Requirements 2.1**

Property 2: Bug Condition — Delete/unlink photo affordance exists

_For any_ state where a photo is selected in FotoTab, the system SHALL provide a "Ta bort foto" button that, when clicked, removes the `LinkedEntity` linking the photo to the current person from the MediaItem, and if no `linked_entities` remain, removes the entire MediaItem from `project_data.media`.

**Validates: Requirements 2.2**

Property 3: Bug Condition — Person auto-added to mentioned_person_ids on photo add

_For any_ invocation of "Lägg till foto" that successfully creates a new MediaItem, the system SHALL include the current person's ID in `mentioned_person_ids` on the newly created MediaItem.

**Validates: Requirements 2.3**

Property 4: Bug Condition — Person display includes birth/death years for disambiguation

_For any_ person displayed in the PersonListWidget combo box who has at least one birth or death year available in the project events, the system SHALL format the display text as "given surname (birth_year–death_year)" using "?" for unknown years, e.g., "Erik Andersson (1845–1901)" or "Erik Andersson (?–1901)".

**Validates: Requirements 2.4**

Property 5: Bug Condition — Tilltalsnamn marker stripped from display text

_For any_ person whose given name contains a `*` character (tilltalsnamn marker), the system SHALL strip all `*` characters from the display text and search text in the combo box, so that searching for the name without `*` matches the person correctly.

**Validates: Requirements 2.5**

Property 6: Preservation — Existing photo add behavior unchanged

_For any_ photo addition flow, the system SHALL continue to copy the file to Foto_Mapp, create a MediaItem with a LinkedEntity linking it to the current person, and display it in the photo table, exactly as before.

**Validates: Requirements 3.1, 3.6**

Property 7: Preservation — Metadata editing unchanged

_For any_ metadata edit via "Spara ändringar", the system SHALL continue to update the MediaItem title in `[Foto_Typ] title` format, preserving existing behavior.

**Validates: Requirements 3.2**

Property 8: Preservation — Explicit person list save unchanged

_For any_ explicit click on "Spara personlista", the system SHALL continue to persist person list changes to the MediaItem immediately, exactly as before.

**Validates: Requirements 3.3**

Property 9: Preservation — Non-starred names display unchanged

_For any_ person whose name does NOT contain a `*` marker, the system SHALL continue to display and match that person in the combo box exactly as before (with the addition of year info if available).

**Validates: Requirements 3.7, 3.8**

Property 10: Preservation — No empty parentheses for persons without year data

_For any_ person who has no birth year AND no death year available in project events, the system SHALL display the name without any parenthetical year information (no "(–)" or "(? –?)" shown).

**Validates: Requirements 3.9**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `slaktbusken/ui/editors/person_editor.py`

**Function**: `_on_save`

**Specific Changes**:
1. **Flush pending FotoTab person-list changes**: Before building the `Person` object and emitting `save_requested`, check if `self._foto_tab` exists and if its `_save_persons_btn` is enabled. If so, call `self._foto_tab._on_save_persons()` to persist pending changes.

---

**File**: `slaktbusken/ui/widgets/foto_tab.py`

**Function**: `_setup_ui` (new button) + new method `_on_delete_photo`

**Specific Changes**:
2. **Add "Ta bort foto" button**: Add a QPushButton "Ta bort foto" in the button area (next to "Lägg till foto"), initially disabled. Enable it when a photo is selected, disable it when no photo is selected.
3. **Implement `_on_delete_photo` handler**: When clicked, show a confirmation dialog. If confirmed, remove the `LinkedEntity` with `entity_id == self._person.id` from the selected MediaItem. If the MediaItem has no remaining `linked_entities`, remove it from `self._project_data.media` entirely. Also remove the person from `mentioned_person_ids` if present. Refresh the table.
4. **Wire up selection state**: In `_on_photo_selected`, enable/disable the "Ta bort foto" button based on whether a photo is selected.

---

**File**: `slaktbusken/ui/widgets/foto_tab.py`

**Function**: `_on_add_photo`

**Specific Changes**:
5. **Add person to `mentioned_person_ids`**: After creating the `MediaItem` (before appending to `project_data.media`), set `mentioned_person_ids=[self._person.id]` on the new MediaItem.

---

**File**: `slaktbusken/ui/widgets/foto_tab.py`

**New public method**: `flush_pending_person_list`

**Specific Changes**:
6. **Expose a public flush method**: Add a method `flush_pending_person_list()` that calls `_on_save_persons()` only if there are pending changes (button enabled). This provides a clean API for `PersonEditor` to call rather than reaching into private state.

---

**File**: `slaktbusken/ui/widgets/person_list_widget.py`

**Function**: `_person_display_name` (module-level helper)

**Specific Changes**:
7. **Strip tilltalsnamn marker**: Remove all `*` characters from `name.given` before building the display string. Change from `name.given` to `name.given.replace("*", "")`.
8. **Add birth/death year disambiguation**: Accept `events: list[Event]` as a parameter (or pass project_data events). Use `get_person_birth_death_years(person, events)` to obtain years. If at least one year is non-empty, append ` (birth–death)` to the display text, using `"?"` for unknown years. If both are empty, display name only (no parentheses).

---

**File**: `slaktbusken/ui/widgets/person_list_widget.py`

**Class**: `PersonListWidget`

**Specific Changes**:
9. **Pass events to `_person_display_name()`**: Update the function signature to accept `person` and `events` parameters. Update all call sites within the class (`_populate_person_combo`, `_refresh_list`) to pass `self._project_data.events` (the events list from project data).
10. **Update QCompleter data**: Since the display text now includes years and excludes `*`, the QCompleter strings will automatically reflect the corrected names. The `MatchContains` filter mode ensures typing partial names (e.g., "Erik") still matches "Erik Andersson (1845–1901)".

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bugs on unfixed code, then verify the fixes work correctly and preserve existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bugs BEFORE implementing the fix. Confirm or refute the root cause analysis.

**Test Plan**: Write tests that simulate each bug scenario and assert the expected outcome. Run on UNFIXED code to observe failures.

**Test Cases**:
1. **Pending person-list lost on save**: Modify person list in FotoTab, call `PersonEditor._on_save()`, assert `mentioned_person_ids` was NOT updated (will demonstrate bug 1 on unfixed code)
2. **No delete button exists**: Assert that FotoTab has no "Ta bort foto" button or `_on_delete_photo` method (will demonstrate bug 2)
3. **Person missing from mentioned_person_ids**: Call `_on_add_photo` flow, assert that `mentioned_person_ids` on the new MediaItem is empty (will demonstrate bug 3)
4. **Duplicate names indistinguishable**: Create two persons with name "Erik Andersson" (one born 1845, one born 1902), call `_person_display_name()` for both, assert both return the same string (will demonstrate bug 4)
5. **Star in display text**: Create a person with given name "Karl Erik*", call `_person_display_name()`, assert the result contains `*` (will demonstrate bug 5)

**Expected Counterexamples**:
- `PersonEditor._on_save()` does not call any FotoTab flush method
- No QPushButton with text "Ta bort foto" in FotoTab widget hierarchy
- New MediaItem's `mentioned_person_ids == []` after add
- `_person_display_name(person_a) == _person_display_name(person_b)` for two different "Erik Andersson" persons
- `_person_display_name(person_with_star)` returns "Karl Erik* Andersson" instead of "Karl Erik Andersson (…)"

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed functions produce the expected behavior.

**Pseudocode:**
```
// Bug 1
FOR ALL state WHERE pending_person_list_changes AND save_triggered DO
  result := PersonEditor_fixed._on_save(state)
  ASSERT media_item.mentioned_person_ids == expected_ids
END FOR

// Bug 2
FOR ALL state WHERE photo_selected AND delete_clicked DO
  result := FotoTab_fixed._on_delete_photo(state)
  ASSERT linked_entity_removed(media_item, person_id)
  IF no_linked_entities_remain THEN ASSERT media_item_removed(project_data)
END FOR

// Bug 3
FOR ALL photo_add_input DO
  media_item := FotoTab_fixed._on_add_photo(photo_add_input)
  ASSERT person.id IN media_item.mentioned_person_ids
END FOR

// Bug 4
FOR ALL person WHERE has_birth_or_death_year DO
  display := _person_display_name_fixed(person, events)
  ASSERT display CONTAINS "(" AND display CONTAINS "–"
  ASSERT display CONTAINS birth_year OR display CONTAINS "?"
END FOR

// Bug 5
FOR ALL person WHERE person.names[0].given CONTAINS "*" DO
  display := _person_display_name_fixed(person, events)
  ASSERT "*" NOT IN display
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed functions produce the same result as the original functions.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT original_behavior(input) == fixed_behavior(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code for metadata editing, explicit person list saves, photo selection, profile photo setting, and non-starred name display. Then write property-based tests capturing that behavior.

**Test Cases**:
1. **Metadata save preservation**: Verify that "Spara ändringar" continues to format title as `[Foto_Typ] title`
2. **Explicit person save preservation**: Verify that "Spara personlista" continues to sync `mentioned_person_ids` and `linked_entities`
3. **Photo selection preservation**: Verify that selecting a photo continues to populate editing panel and show preview
4. **Profile photo preservation**: Verify that "Välj som profilbild" continues to set `profile_media_id`
5. **Photo add file handling preservation**: Verify that adding a photo still copies to Foto_Mapp and creates LinkedEntity
6. **Non-starred name preservation**: Verify that persons without `*` in their name continue to display and match correctly
7. **No-year person preservation**: Verify that persons with no birth/death data display without parentheses

### Unit Tests

- Test `PersonEditor._on_save()` flushes pending FotoTab changes when `_save_persons_btn` is enabled
- Test `PersonEditor._on_save()` does NOT call flush when no pending changes exist
- Test `FotoTab._on_delete_photo()` removes LinkedEntity for current person
- Test `FotoTab._on_delete_photo()` removes entire MediaItem when no linked entities remain
- Test `FotoTab._on_delete_photo()` preserves MediaItem when other linked entities exist
- Test `FotoTab._on_add_photo()` includes person ID in `mentioned_person_ids`
- Test "Ta bort foto" button is disabled when no photo selected, enabled when photo selected
- Test `_person_display_name()` strips `*` from given name ("Karl Erik*" → "Karl Erik")
- Test `_person_display_name()` appends "(1845–1901)" when both years available
- Test `_person_display_name()` appends "(?–1901)" when only death year available
- Test `_person_display_name()` appends "(1845–?)" when only birth year available
- Test `_person_display_name()` shows no parentheses when neither year available
- Test `_person_display_name()` handles person with no names → returns "(Person {id})"
- Test QCompleter matches "Erik Andersson" against a person stored as "Karl Erik*" with surname "Andersson"

### Property-Based Tests

- Generate random `MediaItem` states with varying `linked_entities` and verify delete removes only the current person's link
- Generate random person IDs and verify `_on_add_photo` always includes the person in `mentioned_person_ids`
- Generate random sequences of person-list edits and saves to verify flush always captures pending state
- Generate random `MediaItem` configurations and verify `sync_linked_entities` is idempotent for non-buggy inputs
- Generate random person names (with and without `*`, with various year combinations) and verify `_person_display_name()` never contains `*` in output
- Generate random person names with known birth/death years and verify display format matches "given surname (birth–death)" pattern
- Generate random person names with no years and verify no parentheses appear in output

### Integration Tests

- Full flow: edit person list → save person → verify MediaItem updated
- Full flow: add photo → verify person in `mentioned_person_ids` → edit person list → add more persons → save → verify all persisted
- Full flow: add photo → delete photo → verify MediaItem removed (no other links)
- Full flow: add photo linked to multiple persons → delete from one person → verify MediaItem preserved with remaining links
- Full flow: open person search combo with duplicate names → verify years shown for disambiguation
- Full flow: type partial name in combo box for person with `*` → verify QCompleter matches correctly
- Full flow: search for "Erik" when persons include "Karl Erik* Andersson (1845–1901)" → verify match found
