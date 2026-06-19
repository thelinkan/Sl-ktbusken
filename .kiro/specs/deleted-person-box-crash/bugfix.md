# Bugfix Requirements Document

## Introduction

A `RuntimeError: Internal C++ object (PersonBoxItem) already deleted` is raised the first time the active person is changed in the diagram view. The error appears in the console/log but does not hard-crash the application — the diagram still renders correctly afterward. The error does not recur on subsequent active person changes. The root cause is that `FamilyView` (and other view renderers) hold stale Python references to `PersonBoxItem` objects whose underlying C++ objects have been destroyed by `QGraphicsScene.clear()`. When the `selectionChanged` signal fires during the scene rebuild, `deselect_all()` iterates these stale references and calls `set_selected(False)` → `update()` on a deleted C++ object.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the active person is changed for the first time and `_refresh_diagram()` clears the scene THEN the system raises a `RuntimeError: Internal C++ object (PersonBoxItem) already deleted` because `deselect_all()` calls `set_selected(False)` on stale PersonBoxItem references still held in `_person_boxes`

1.2 WHEN `_on_scene_selection_changed()` is invoked during or after a scene clear THEN the system attempts to call methods on destroyed C++ objects through the view's stale `_person_boxes` list, producing the RuntimeError in the log output

### Expected Behavior (Correct)

2.1 WHEN the active person is changed and `_refresh_diagram()` clears the scene THEN the system SHALL NOT raise a RuntimeError and stale PersonBoxItem references SHALL NOT be accessed after their C++ objects are destroyed

2.2 WHEN `_on_scene_selection_changed()` is invoked during or after a scene clear THEN the system SHALL safely avoid calling methods on destroyed PersonBoxItem objects (no error in log output)

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a user clicks a person box in the diagram THEN the system SHALL CONTINUE TO visually select that person box and deselect all others

3.2 WHEN a user navigates between views (Family, Ancestry, Descendants) THEN the system SHALL CONTINUE TO render the correct diagram without visual artifacts

3.3 WHEN a user double-clicks a person box THEN the system SHALL CONTINUE TO emit the `person_double_clicked` signal and open the editor

3.4 WHEN `deselect_all()` is called on a view with valid (non-deleted) person boxes THEN the system SHALL CONTINUE TO deselect all boxes without error
