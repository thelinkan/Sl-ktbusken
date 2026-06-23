# Bugfix Requirements Document

## Introduction

When saving a person in the "Redigera Person" dialog, the active person in the diagram unexpectedly changes to the first person in the person list. This happens because `person_list_panel.refresh()` clears and repopulates the tree widget, which triggers Qt's `currentItemChanged` signal. That signal is connected to `set_active_person` on the diagram panel, causing the active person to jump to whoever ends up selected first in the rebuilt list.

The correct behavior is: saving an existing person (or a new person affiliated with the current view) should never change the active person. Only saving a brand-new person with no affiliation to the current view should make that new person active.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN an existing person is saved via the "Redigera Person" dialog THEN the system changes the active person in the diagram to the first person in the person list

1.2 WHEN a new person affiliated with persons in the current view is saved THEN the system changes the active person in the diagram to the first person in the person list

1.3 WHEN a new person with no affiliation to the current view is saved THEN the system changes the active person in the diagram to the first person in the person list (instead of making the new person active)

### Expected Behavior (Correct)

2.1 WHEN an existing person is saved via the "Redigera Person" dialog THEN the system SHALL preserve the currently active person in the diagram unchanged

2.2 WHEN a new person affiliated with persons in the current view is saved THEN the system SHALL preserve the currently active person in the diagram unchanged

2.3 WHEN a new person with no affiliation to the current view is saved THEN the system SHALL make the newly saved person the active person in the diagram

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a user single-clicks a person in the person list (outside of a refresh cycle) THEN the system SHALL CONTINUE TO emit `person_selected` and update the active person in the diagram

3.2 WHEN the diagram panel activates a person via `select_person_from_diagram()` THEN the system SHALL CONTINUE TO select the person in the list without emitting `person_selected` (existing guard behavior)

3.3 WHEN the person list is refreshed after import or other data changes (not person-save) THEN the system SHALL CONTINUE TO not change the active person in the diagram

3.4 WHEN a user double-clicks a person in the person list THEN the system SHALL CONTINUE TO open the person editor for that person
