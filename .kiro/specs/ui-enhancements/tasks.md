# Implementation Plan: UI Enhancements

## Overview

This plan implements nine UI enhancements for the Släktbusken genealogy application: event type icons, gender icons, lineage visual marking, recent projects, default project auto-open, person context menu, progress indicators, and DNA cluster management from the person editor. Tasks are ordered to build foundational services first (icons, settings, lineage), then integrate into existing UI components, and finally wire everything together.

## Tasks

- [ ] 1. Create IconRegistry and SVG icon assets
  - [ ] 1.1 Create SVG icon files for all event types and gender values
    - Create directory `slaktbusken/ui/icons/events/` with SVG files for all 23 event types plus `generic_event.svg` fallback
    - Create directory `slaktbusken/ui/icons/gender/` with SVG files: `male.svg` (blue), `female.svg` (red), `other.svg` (green), `unknown.svg` (yellow)
    - Each icon should be a simple, recognizable symbol at a native size suitable for 12–16px rendering
    - _Requirements: 1.1, 2.1_

  - [ ] 1.2 Implement the IconRegistry class
    - Create `slaktbusken/ui/icons/__init__.py` and `slaktbusken/ui/icons/icon_registry.py`
    - Implement singleton `IconRegistry` with `get_event_icon(event_type: str) -> QPixmap`, `get_gender_icon(sex: str) -> QPixmap`, `get_event_icon_path(event_type: str) -> Path`, `get_gender_icon_path(sex: str) -> Path`
    - Implement fallback logic: unrecognized event types return `generic_event.svg`; invalid sex values return `unknown.svg`
    - Cache loaded pixmaps for performance
    - _Requirements: 1.1, 1.5, 2.1_

  - [ ] 1.3 Write property tests for IconRegistry (Property 1 & 2)
    - **Property 1: Event icon registry completeness** — For every event type in the defined set, verify `get_event_icon()` returns a valid non-null QPixmap distinct from the fallback
    - **Property 2: Event icon fallback for unrecognized types** — For arbitrary strings not in the recognized set, verify `get_event_icon()` returns the generic fallback icon without raising
    - **Validates: Requirements 1.1, 1.5**

  - [ ] 1.4 Write unit tests for IconRegistry
    - Test all 23 event types return distinct non-null icons
    - Test all 4 gender values return distinct non-null icons
    - Test invalid sex value ('Z') returns unknown icon
    - Test caching behavior (same pixmap returned on repeated calls)
    - _Requirements: 1.1, 1.5, 2.1_

- [ ] 2. Implement LineageComputer service
  - [ ] 2.1 Create LineageComputer class
    - Create `slaktbusken/services/lineage_computer.py`
    - Implement `LineageComputer.__init__(self, project_data: ProjectData)`
    - Implement `get_ancestors(person_id: str) -> set[str]` using BFS upward through Family objects (collecting partners of families where person is a child)
    - Implement `get_descendants(person_id: str) -> set[str]` using BFS downward through Family objects (collecting children of families where person is a partner)
    - Include cycle detection via visited set to handle circular references gracefully
    - Ensure the main person is NOT included in either returned set
    - _Requirements: 3.1, 3.4, 4.1, 4.4_

  - [ ] 2.2 Write property tests for LineageComputer (Properties 3, 4, 5)
    - **Property 3: Ancestor computation correctness** — Generate random family graphs, verify ancestor set matches naive recursive traversal of parent links
    - **Property 4: Descendant computation correctness** — Same graph generation, verify descendant set matches naive recursive traversal of child links
    - **Property 5: Main person excluded from lineage sets** — For any graph and person P, verify P not in `get_ancestors(P)` and P not in `get_descendants(P)`
    - **Validates: Requirements 3.1, 3.4, 4.1**

  - [ ] 2.3 Write unit tests for LineageComputer
    - Test with a hand-crafted 3-generation linear tree (grandparent → parent → child)
    - Test with sibling branches (two children, each with descendants)
    - Test with circular reference (person is both ancestor and descendant) — verify no infinite loop
    - Test with isolated person (no families) — returns empty sets
    - _Requirements: 3.1, 4.1, 3.4_

- [ ] 3. Implement AppSettingsService and persistence
  - [ ] 3.1 Create AppSettingsService and AppSettings data model
    - Create `slaktbusken/persistence/app_settings_io.py`
    - Implement `AppSettings` dataclass with `recent_projects: list[str]` (max 10, MRU order) and `default_project_path: Optional[str]`
    - Implement `AppSettingsService` with `load()`, `save()`, `add_recent_project(path)`, `set_default_project(path)`, `get_recent_projects()`, `get_default_project()`
    - Settings file location: `~/.slaktbusken/app_settings.json`
    - Handle missing/corrupt file gracefully (create fresh defaults)
    - Handle non-writable directory gracefully (log warning, continue)
    - _Requirements: 5.1, 5.2, 5.6, 6.1, 6.2_

  - [ ] 3.2 Write property tests for AppSettingsService (Properties 7, 8)
    - **Property 7: Recent projects list invariants** — Generate random sequences of `add_recent_project(path)` calls, verify: MRU at index 0, no duplicates, length ≤ 10
    - **Property 8: AppSettings serialization round-trip** — Generate random AppSettings instances (0–10 paths, optional default), verify JSON round-trip produces equivalent instance
    - **Validates: Requirements 5.1, 5.6, 5.2**

  - [ ] 3.3 Write unit tests for AppSettingsService
    - Test file creation on first save
    - Test load with known JSON content
    - Test add_recent_project moves existing entry to top
    - Test add_recent_project evicts oldest when at 10
    - Test set_default_project and get_default_project
    - Test load with missing file returns defaults
    - Test load with corrupt JSON returns defaults
    - _Requirements: 5.1, 5.2, 5.6, 6.2_

- [ ] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Implement ProgressOverlay widget
  - [ ] 5.1 Create ProgressOverlay widget
    - Create `slaktbusken/ui/widgets/progress_overlay.py`
    - Implement `ProgressOverlay(QWidget)` parented to MainWindow
    - Implement `show_with_message(message: str)` — show semi-transparent dark backdrop, centered spinner animation, and message text
    - Implement `hide()` — remove overlay and re-enable input
    - Override `resizeEvent` to match parent window size
    - Block all mouse/keyboard events while visible by covering entire window area
    - _Requirements: 8.1, 8.5, 8.6, 8.7_

  - [ ] 5.2 Write unit tests for ProgressOverlay
    - Test show/hide state transitions (visibility, enabled state)
    - Test message text is set correctly
    - Test overlay resizes with parent
    - _Requirements: 8.5, 8.6, 8.7_

- [ ] 6. Implement ContextMenuBuilder
  - [ ] 6.1 Create ContextMenuBuilder class
    - Create `slaktbusken/ui/context_menu_builder.py`
    - Implement `build_person_menu(person_id, main_person_id, parent_widget) -> QMenu`
    - Add actions in order: Gör aktuell, Redigera person, Ny partner, Ny pappa, Ny mamma, Nytt barn, Visa släktskap med huvudpersonen
    - Handle edge case: if clicked person is main person and "Visa släktskap" selected, show info message
    - _Requirements: 7.1, 7.2, 7.10_

  - [ ] 6.2 Write unit tests for ContextMenuBuilder
    - Test menu contains exactly 7 actions in correct order
    - Test action text matches Swedish labels
    - _Requirements: 7.1, 7.2_

- [ ] 7. Integrate icons and lineage marking into PersonBoxItem
  - [ ] 7.1 Extend PersonBoxItem to accept and render gender icon
    - Modify `slaktbusken/ui/widgets/person_box.py` to accept `sex: str` parameter
    - In `paint()`, draw Gender_Icon in top-right corner (14×14 px) using `IconRegistry.get_gender_icon(sex)`
    - _Requirements: 2.2, 2.4_

  - [ ] 7.2 Extend PersonBoxItem to render event icons
    - In `paint()`, draw Event_Icons (12×12 px) adjacent to birth/death date lines using `IconRegistry.get_event_icon(type)`
    - _Requirements: 1.3, 1.4_

  - [ ] 7.3 Extend PersonBoxItem to render lineage border colors
    - Accept `is_ancestor: bool` and `is_descendant: bool` parameters
    - Override border color: red (#C0392B, 2px) if `is_ancestor`, green (#27AE60, 2px) if `is_descendant`, normal otherwise
    - Ancestor takes precedence if both are True
    - _Requirements: 3.2, 4.2, 4.4_

  - [ ] 7.4 Write property test for border precedence (Property 6)
    - **Property 6: Ancestor border precedence** — Generate random boolean pairs (is_ancestor, is_descendant), verify when both True the border color is always ancestor red
    - **Validates: Requirements 4.4**

- [ ] 8. Integrate lineage and icons into DiagramPanel
  - [ ] 8.1 Integrate LineageComputer into DiagramPanel refresh
    - Modify `slaktbusken/ui/diagram_panel.py` to instantiate `LineageComputer` and compute ancestor/descendant sets in `_refresh_diagram()`
    - Pass `is_ancestor`, `is_descendant`, and `sex` to each `PersonBoxItem` constructor
    - Recompute when `main_person_id` changes
    - _Requirements: 3.1, 3.3, 4.1, 4.3_

  - [ ] 8.2 Add context menu handling to DiagramPanel
    - Add right-click event handling via `contextMenuEvent` on person box items
    - Use `ContextMenuBuilder.build_person_menu()` to show the menu
    - Connect actions: "Gör aktuell" → set active person, "Redigera person" → open editor, "Ny partner/pappa/mamma/barn" → invoke respective dialogs, "Visa släktskap" → invoke Relationship_Calculator
    - _Requirements: 7.1, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9_

- [ ] 9. Integrate gender icons and context menu into PersonListPanel
  - [ ] 9.1 Add gender icon to PersonListPanel items
    - Modify `slaktbusken/ui/person_list_panel.py` to display Gender_Icon (16×16 px) to the left of person name using a custom item delegate or decoration
    - _Requirements: 2.3_

  - [ ] 9.2 Add context menu handling to PersonListPanel
    - Add right-click event handling on person list items
    - Use `ContextMenuBuilder.build_person_menu()` to show the same context menu
    - Connect same actions as DiagramPanel
    - _Requirements: 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9_

- [ ] 10. Integrate event icons into Edit_Window event list
  - [ ] 10.1 Add event icons to event list in Edit_Window
    - Modify the event list display in the person editor to show Event_Icon (16×16 px) to the left of event type text
    - _Requirements: 1.2_

- [ ] 11. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Integrate recent projects and default project into MainWindow
  - [ ] 12.1 Add "Senaste projekt" submenu to Arkiv menu
    - Modify `slaktbusken/ui/main_window.py` to add a "Senaste projekt" submenu under the Arkiv menu
    - Populate submenu entries from `AppSettingsService.get_recent_projects()` showing project name and path
    - Connect each entry to open the corresponding project
    - Display disabled entries with tooltip "Filen hittades inte" for missing files
    - _Requirements: 5.3, 5.4, 5.5_

  - [ ] 12.2 Update project open/create to record recent projects
    - On project open or create, call `AppSettingsService.add_recent_project(path)`
    - Refresh the "Senaste projekt" submenu after each update
    - _Requirements: 5.1_

  - [ ] 12.3 Implement default project auto-open on startup
    - On application startup, check `AppSettingsService.get_default_project()`
    - If set and file exists, auto-open the project
    - If set but file missing, show Swedish notification, clear setting, continue to empty state
    - _Requirements: 6.3, 6.4_

  - [ ] 12.4 Add default project settings to settings dialog
    - Add "Standardprojekt" section to settings dialog with "Ange som standard" button (sets current project as default) and "Rensa standard" button (clears default)
    - _Requirements: 6.1, 6.5_

- [ ] 13. Integrate ProgressOverlay into long operations
  - [ ] 13.1 Wire ProgressOverlay into MainWindow and Application
    - Instantiate `ProgressOverlay` as child of `MainWindow`
    - Before file load: show overlay with "Laddar projekt..."
    - Before file save: show overlay with "Sparar projekt..."
    - Before GEDCOM import: show overlay with "Importerar GEDCOM..."
    - Before GEDCOM export: show overlay with "Exporterar GEDCOM..."
    - On completion (success or failure): hide overlay, re-enable input
    - Wrap operations in try/except to ensure overlay is hidden even on error
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

- [ ] 14. Implement DNA cluster management in person editor
  - [ ] 14.1 Add Klustermedlemskap section to DNA tab in Edit_Window
    - Add a "Klustermedlemskap" section to the DNA tab when the person has at least one DNA_Profile
    - Display a list of DNA_Clusters the person's profiles belong to, showing cluster name and associated company
    - If no clusters exist in project, show message suggesting user create them in DNA editor
    - _Requirements: 9.1, 9.6_

  - [ ] 14.2 Implement add/remove cluster membership actions
    - Add "Lägg till kluster" button that opens a selection dialog listing available DNA_Clusters
    - Allow multi-select in the add dialog
    - If person has multiple profiles, prompt user to select which profile to associate
    - Add "Ta bort" button to remove selected cluster membership
    - Update DNA_Cluster entity's member list on add/remove so changes reflect in DNA editor
    - _Requirements: 9.2, 9.3, 9.4, 9.5_

  - [ ] 14.3 Write property test for DNA cluster membership (Property 9)
    - **Property 9: DNA cluster membership consistency** — Generate random DnaCluster with random person_ids, verify add operation makes `person_id in cluster.person_ids` True, remove operation makes it False with length decreased by 1
    - **Validates: Requirements 9.3, 9.4**

- [ ] 15. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The implementation language is Python with PySide6, matching the existing codebase
- SVG icons are used for crisp rendering at any zoom level
- All new modules follow existing project structure conventions (services in `slaktbusken/services/`, UI in `slaktbusken/ui/`, persistence in `slaktbusken/persistence/`)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "3.1", "5.1"] },
    { "id": 1, "tasks": ["1.2", "3.2", "3.3", "5.2"] },
    { "id": 2, "tasks": ["1.3", "1.4", "2.1", "6.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "6.2", "7.1"] },
    { "id": 4, "tasks": ["7.2", "7.3", "7.4"] },
    { "id": 5, "tasks": ["8.1", "8.2", "9.1", "9.2", "10.1"] },
    { "id": 6, "tasks": ["12.1", "12.2", "12.3", "12.4", "13.1", "14.1"] },
    { "id": 7, "tasks": ["14.2", "14.3"] }
  ]
}
```
