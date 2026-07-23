# Implementation Plan: Map View

## Overview

This plan implements the map view feature for Släktbusken. The implementation proceeds from the pure data service, through the UI components (dialog, bridge, template), to integration with existing menus and context menus. Python and JavaScript (Leaflet.js) are the implementation languages.

## Tasks

- [ ] 1. Pure logic — Map data service
  - [ ] 1.1 Implement map_data_service.py
    - Create `slaktbusken/services/map_data_service.py`
    - Define `MapParticipant`, `MapEvent`, and `MapMarker` dataclasses
    - Implement `build_markers_for_person(data, person_id)` — filter events by person, group by place, resolve names
    - Implement `build_markers_all_events(data)` — group all events by place, resolve names
    - Implement `markers_to_json(markers)` — serialize to JSON for HTML injection
    - Implement event type → Swedish display name mapping
    - Implement chronological event sorting within each marker (dated first, undated last)
    - Handle unresolvable participants with "(okänd)" fallback
    - Only include places with non-null latitude and longitude
    - _Requirements: 2.2, 2.3, 3.1, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ] 1.2 Write property tests for map data service
    - **Property 1: One marker per place invariant**
    - **Property 2: All qualifying events are represented**
    - **Property 3: Person filter correctness**
    - **Property 4: Markers only include places with coordinates**
    - **Property 5: Event chronological ordering**
    - _Validates: Requirements 2.2, 2.3, 3.1, 5.1, 5.6_

- [ ] 2. Checkpoint — Data service
  - Ensure all property tests and unit tests pass.

- [ ] 3. UI components — Map dialog and bridge
  - [ ] 3.1 Create map HTML template
    - Create `slaktbusken/ui/static/map_template.html`
    - Include Leaflet.js and CSS from CDN (with integrity hashes)
    - Create map div and initialization script
    - Read marker data from `window.MARKER_DATA` variable
    - Create one Leaflet marker per place with place name as tooltip
    - Build popup HTML for each marker: list of Event_Cards with type, date, clickable participant names
    - Implement `bridge.navigateToPerson(personId)` call on participant name click via QWebChannel
    - Fit map bounds to all markers (or center on single marker at zoom 10)
    - Display OpenStreetMap attribution
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.2, 5.3, 6.1, 8.1, 8.2, 8.6_

  - [ ] 3.2 Implement MapBridge (QWebChannel bridge)
    - Create `MapBridge` class in `slaktbusken/ui/dialogs/map_dialog.py`
    - Expose `navigateToPerson(person_id)` slot callable from JavaScript
    - Emit `navigate_to_person` signal with person_id
    - _Requirements: 6.1, 6.2_

  - [ ] 3.3 Implement MapDialog
    - Create `slaktbusken/ui/dialogs/map_dialog.py`
    - Set minimum size 900×700
    - Accept `markers` list and `title` string
    - Set up QWebEngineView with QWebChannel
    - Register MapBridge instance on the channel
    - Inject marker JSON into the HTML template (replace placeholder or set window variable)
    - Load the HTML into QWebEngineView
    - Connect bridge signal to `person_navigation_requested` signal
    - Set dialog as modal
    - _Requirements: 4.1, 6.2, 6.3, 7.1, 7.2, 7.3, 7.4_

- [ ] 4. Checkpoint — Dialog renders
  - Verify that MapDialog can be instantiated and renders a map with test markers.

- [ ] 5. Integration — Menus, context menu, and person editor
  - [ ] 5.1 Create map marker SVG icon and add to IconRegistry
    - Create `slaktbusken/ui/icons/misc/map_marker.svg` — a location pin icon legible at 14×14
    - Add `get_map_icon()` method to `IconRegistry` returning a 14×14 QPixmap
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [ ] 5.2 Enhance person editor events list with place name and map icon
    - Modify `_refresh_events_list()` in `slaktbusken/ui/editors/person_editor.py`
    - Build a `places_by_id` lookup dict from `self._project_data.places`
    - Resolve `event.place.place_id` to place name for each event
    - Append place name to display string after date (format: "— {place_name}")
    - If resolved place has latitude and longitude, display map icon on the item
    - Use a custom item delegate or trailing icon approach for the map icon
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8_

  - [ ] 5.3 Add "Visa på karta" to context menu
    - Modify `slaktbusken/ui/context_menu_builder.py`
    - Add action "Visa på karta" with data `("show_on_map", person_id)` after "Filtrera på DNA-träffar"
    - _Requirements: 2.1, 2.4_

  - [ ] 5.4 Add Karta menu to menu bar
    - Modify `slaktbusken/ui/main_window.py`
    - Add `action_map_all_events` QAction in `_setup_actions()`
    - Add `self.menu_map = menu_bar.addMenu("&Karta")` between Verktyg and Rapporter in `_setup_menu_bar()`
    - Add "Alla händelser" action to the Karta menu
    - Connect action to `self._app.show_all_events_map`
    - Disable action when no project is loaded (update in project state change handler)
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ] 5.5 Add "Visa på karta" button to Place Editor
    - Modify `slaktbusken/ui/editors/place_editor.py`
    - Add QPushButton "Visa på karta" beside the coordinates checkbox
    - Set initial enabled state to match coordinates checkbox state
    - Connect `coordinates_check.toggled` to button's `setEnabled`
    - Implement `_on_show_place_on_map()` handler: read lat/lng from spin boxes, open MapDialog with single marker
    - Use place name from the name field as marker label and dialog title
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [ ] 5.6 Show map icon on places with coordinates in Place Editor list and parent combo
    - Modify `slaktbusken/ui/editors/place_editor.py`
    - In the place list population logic, check if each place has non-null latitude and longitude
    - If yes, set the map icon (from `icon_registry.get_map_icon()`) as the item's icon/decoration
    - In the parent place combo population logic, use `combo.addItem(QIcon(icon_registry.get_map_icon()), display, place_id)` for places with coordinates
    - Update icon state when a place is saved with coordinates added or removed
    - _Requirements: 8b.1, 8b.2, 8b.3, 8b.4, 8b.5_

  - [ ] 5.7 Implement CoordinateSpinBox with paste support for period decimals
    - Create `CoordinateSpinBox` subclass of `QDoubleSpinBox` (in `slaktbusken/ui/widgets/` or inline in place_editor)
    - Override `keyPressEvent` to intercept Ctrl+V / Paste
    - Normalize pasted text: strip whitespace, replace comma with period, parse as float
    - Round to spin box's decimal count (6), validate range, call `setValue`
    - Reject invalid paste silently (retain current value)
    - Replace `latitude_spin` and `longitude_spin` in place editor with CoordinateSpinBox instances (programmatic promotion at runtime)
    - _Requirements: 8c.1, 8c.2, 8c.3, 8c.4, 8c.5, 8c.6_

  - [ ] 5.8 Implement app.py handler methods
    - Add `show_person_map(person_id)` method to Application
    - Add `show_all_events_map()` method to Application
    - Add `_handle_map_navigation(person_id)` method to Application
    - Handle "show_on_map" action type in `_handle_context_menu_action()`
    - Show info messages when no qualifying markers exist
    - Close dialog and navigate to person on bridge signal
    - Show warning if person not found on navigation attempt
    - _Requirements: 2.2, 2.3, 3.1, 3.2, 6.2, 6.3, 6.4_

  - [ ] 5.9 Add PySide6-WebEngine dependency
    - Update `pyproject.toml` to add `"PySide6-WebEngine>=6.6.0"` to dependencies
    - _Requirements: 11.3, 11.4_

- [ ] 6. Checkpoint — Full integration
  - Verify end-to-end: right-click person → "Visa på karta" → map opens with correct markers.
  - Verify: Karta menu → Alla händelser → map opens with all qualifying places.
  - Verify: click participant name in popup → dialog closes → person becomes active.
  - Verify: Place Editor → check coordinates → "Visa på karta" → map shows single marker at entered coordinates.
  - Ensure all tests pass.

## Notes

- The map requires internet connectivity for tile loading (OpenStreetMap) and Leaflet CDN. Consider bundling Leaflet.js locally for offline use in a future iteration.
- Event type display name mapping should be kept in sync with any existing translation mappings in the project.
- The QWebEngineView widget requires `PySide6-WebEngine` which is a separate wheel from the core `PySide6` package.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["3.1", "3.2", "3.3"] },
    { "id": 3, "tasks": ["5.1", "5.7"] },
    { "id": 4, "tasks": ["5.2", "5.3", "5.4", "5.5", "5.6", "5.8", "5.9"] }
  ]
}
```

