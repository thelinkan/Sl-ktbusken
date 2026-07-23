# Requirements Document

## Introduction

This document specifies a map view feature for Släktbusken, a Swedish genealogy desktop application built with PySide6. The feature allows users to visualize events geographically by placing one marker per place on an interactive map. Users can access the map from two entry points: a person-specific view (via right-click context menu) showing places where that person has events, and a project-wide view (via a top-level "Karta" menu) showing all places in the project that have events. Clicking a marker reveals the events at that place with linked participants, and from there users can navigate to persons in the application.

## Glossary

- **Map_Dialog**: A modal QDialog containing an interactive map rendered via Leaflet.js inside a QWebEngineView, with a sidebar or popup showing event details for selected markers.
- **Map_Bridge**: A QObject exposed via QWebChannel that enables JavaScript-to-Python communication (e.g., marker click → navigate to person).
- **Place_Marker**: A single map marker representing one Place that has coordinates and at least one linked event. One marker per place regardless of number of events.
- **Event_Card**: A visual element (within a marker popup or sidebar) showing an event's type, date, and participant names at a given place.
- **Karta_Menu**: A new top-level menu in the menu bar, positioned between "Verktyg" and "Rapporter", initially containing one action "Alla händelser".

## Requirements

### Requirement 1: Karta Menu in Menu Bar

**User Story:** As a user, I want a "Karta" menu in the menu bar, so that I can access project-wide map views from a dedicated location that can be expanded with more options later.

#### Acceptance Criteria

1. THE application menu bar SHALL display a top-level menu labeled "&Karta" positioned between the "Verktyg" menu and the "Rapporter" menu
2. THE Karta_Menu SHALL contain one action labeled "Alla händelser" that opens the project-wide Map_Dialog
3. IF no project is loaded, THEN THE "Alla händelser" action SHALL be disabled
4. THE Karta_Menu structure SHALL support future addition of submenu items without requiring architectural changes

### Requirement 2: Person Context Menu — "Visa på karta"

**User Story:** As a user, I want to right-click a person and choose "Visa på karta", so that I can see all places where that person has events displayed on a map.

#### Acceptance Criteria

1. THE person context menu (ContextMenuBuilder) SHALL include an action labeled "Visa på karta" positioned after "Filtrera på DNA-träffar" and before the separator preceding "Ta bort person"
2. WHEN "Visa på karta" is activated, THE application SHALL open a Map_Dialog filtered to show only places where the right-clicked person participates in at least one event
3. IF the person has no events linked to places with coordinates (latitude and longitude both non-null), THEN THE application SHALL display an informational message "Personen har inga händelser kopplade till platser med koordinater." and SHALL NOT open the Map_Dialog
4. THE "Visa på karta" action SHALL emit a context menu action with type "show_on_map" and the person's ID

### Requirement 3: Project-Wide Map — Alla händelser

**User Story:** As a user, I want to view all places in my project that have events on a single map, so that I can get a geographic overview of where events in my research have occurred.

#### Acceptance Criteria

1. WHEN "Alla händelser" is activated from the Karta_Menu, THE application SHALL open a Map_Dialog showing one Place_Marker for every place in the project that has at least one event linked to it AND has non-null latitude and longitude values
2. IF no places in the project have both events linked to them and valid coordinates, THEN THE application SHALL display an informational message "Inga platser med koordinater och händelser hittades i projektet." and SHALL NOT open the Map_Dialog
3. THE Map_Dialog SHALL display markers for all qualifying places regardless of how many events or persons are associated with each place

### Requirement 4: Map Dialog — Interactive Map Display

**User Story:** As a user, I want the map to be interactive with zoom, pan, and clickable markers, so that I can explore the geographic distribution of events comfortably.

#### Acceptance Criteria

1. THE Map_Dialog SHALL display an interactive map rendered using Leaflet.js inside a QWebEngineView widget
2. THE map SHALL use OpenStreetMap tile layers as the base map with appropriate attribution displayed in the map corner
3. WHEN the Map_Dialog is opened, THE map SHALL automatically fit its view bounds to encompass all displayed markers with appropriate padding
4. IF only one marker exists, THEN THE map SHALL center on that marker at zoom level 10
5. THE map SHALL support standard interactions: mouse wheel zoom, click-and-drag pan, and zoom controls (+/− buttons)
6. EACH Place_Marker SHALL display the place name as a tooltip on hover

### Requirement 5: One Marker Per Place — Event Grouping

**User Story:** As a user, I want one marker per place that expands to show all events at that location, so that the map remains readable even when many events happen at the same place (e.g., a church).

#### Acceptance Criteria

1. THE map SHALL display exactly one Place_Marker per unique place, regardless of how many events are linked to that place
2. WHEN a Place_Marker is clicked, THE map SHALL display a popup or sidebar listing all events at that place as Event_Cards
3. EACH Event_Card SHALL display: the event type (translated to Swedish display name), the event date (if available), and the names of all participants (given name + surname from first Name entry)
4. IF an event has no date, THEN THE Event_Card SHALL display the event type and participants without a date line
5. IF a participant's person record cannot be resolved, THEN THE Event_Card SHALL display "(okänd)" as the participant name
6. THE Event_Cards within a popup SHALL be ordered chronologically by event date where dates are available, with undated events appearing last

### Requirement 6: Navigation from Map to Person

**User Story:** As a user, I want to click a person's name in a map popup and navigate to that person in the application, so that I can quickly access detailed information about people involved in events at a location.

#### Acceptance Criteria

1. EACH participant name displayed in an Event_Card SHALL be rendered as a clickable link
2. WHEN a participant name link is clicked, THE Map_Bridge SHALL invoke a Python callback that navigates the application to the clicked person (equivalent to "Gör aktuell" — setting the person as active in the diagram panel)
3. AFTER navigation is triggered, THE Map_Dialog SHALL close automatically
4. IF the person cannot be found in the project data at the time of click (e.g., deleted since dialog opened), THEN THE application SHALL display a brief warning and keep the Map_Dialog open

### Requirement 7: Map Dialog — Window Properties

**User Story:** As a user, I want the map dialog to be appropriately sized and titled, so that I can work with it comfortably.

#### Acceptance Criteria

1. THE Map_Dialog SHALL have a minimum size of 900×700 pixels
2. WHEN opened from a person context menu, THE Map_Dialog title SHALL be "Karta — {person name}" where person name is the given name and surname from the first Name entry
3. WHEN opened from Karta_Menu → Alla händelser, THE Map_Dialog title SHALL be "Karta — Alla händelser"
4. THE Map_Dialog SHALL be modal (blocks interaction with the main window while open)

### Requirement 8: Place Editor — "Visa på karta" Button

**User Story:** As a user, I want a "Visa på karta" button next to the coordinate checkbox in the Place Editor, so that I can quickly preview a place's location on a map when I have coordinates entered.

#### Acceptance Criteria

1. THE Platsredigerare (Place Editor) SHALL display a button labeled "Visa på karta" positioned beside the "Ange koordinater" checkbox
2. THE "Visa på karta" button SHALL be enabled only when the coordinates checkbox is checked (i.e., the place has coordinates active)
3. WHEN the coordinates checkbox is unchecked, THE "Visa på karta" button SHALL be disabled (grayed out)
4. WHEN the "Visa på karta" button is clicked, THE application SHALL open a Map_Dialog showing a single marker at the latitude and longitude currently entered in the coordinate spin boxes
5. THE Map_Dialog title SHALL be "Karta — {place name}" where place name is the current value of the name field in the editor
6. THE single marker popup SHALL display the place name only (no event listing, since this is a location preview)
7. WHEN the coordinates checkbox state changes, THE "Visa på karta" button enabled state SHALL update immediately to match

### Requirement 8b: Place Editor — Map Icon in Place List and Parent Combo

**User Story:** As a user, I want to see the map icon on places that have coordinates in both the place list and the "Överordnad plats" dropdown, so that I can quickly identify which places are mapped.

#### Acceptance Criteria

1. EACH place item in the Platsredigerare left-hand place list that has both non-null latitude and non-null longitude SHALL display the map icon (from IconRegistry.get_map_icon()) as a decoration on the list item
2. EACH place item that does NOT have coordinates (latitude or longitude is null) SHALL NOT display the map icon
3. WHEN a place's coordinates are added or removed (via save), THE place list SHALL update the map icon visibility for that item accordingly
4. EACH item in the "Överordnad plats" (parent place) combo box that has both non-null latitude and non-null longitude SHALL display the map icon to the left of the place name
5. EACH item in the "Överordnad plats" combo box that does NOT have coordinates SHALL NOT display the map icon

### Requirement 8c: Place Editor — Paste Coordinates with Period Decimal Separator

**User Story:** As a user, I want to paste latitude and longitude values from Arkiv Digital (which use period as decimal separator and may have more than 6 decimal places) into the coordinate fields, so that I don't have to manually convert the format.

#### Acceptance Criteria

1. WHEN the user pastes text into the latitude or longitude spin box, THE application SHALL accept values using period (`.`) as decimal separator and automatically convert them to the spin box's internal format
2. WHEN the user pastes text into the latitude or longitude spin box, THE application SHALL accept values with more than 6 decimal places and round to 6 decimal places (the spin box precision)
3. THE pasted value "61.828333333" SHALL be accepted and converted to 61,828333 (6 decimal places, comma separator) in the spin box
4. IF the pasted text cannot be interpreted as a valid number, THEN THE spin box SHALL reject the paste and retain its previous value
5. THE spin boxes SHALL continue to accept normal keyboard input with comma as decimal separator (existing behavior preserved)
6. THE paste handling SHALL also accept values that already use comma as decimal separator (e.g., "61,828333")

### Requirement 9: Map Icon in Icon Registry

**User Story:** As a developer, I want a reusable map icon available in the icon registry, so that map-related features can consistently use the same visual indicator across the application.

#### Acceptance Criteria

1. THE project SHALL include a map marker SVG icon file at `slaktbusken/ui/icons/misc/map_marker.svg`
2. THE icon SHALL visually represent a map/location marker (pin shape) and be legible at 14×14 and 16×16 pixel sizes
3. THE IconRegistry class SHALL provide a `get_map_icon()` method that returns a 14×14 QPixmap of the map marker icon
4. THE icon SHALL be cached after first load, consistent with existing icon registry caching behavior

### Requirement 10: Event List in Person Editor — Place Name and Map Icon

**User Story:** As a user, I want to see the place name after the date in the event list of "Redigera Person", and a map icon if that place has coordinates, so that I can quickly see where events occurred and identify which places are mappable.

#### Acceptance Criteria

1. EACH event item in the person editor events list SHALL display the place name after the date, in the format "{type} — {date} — {place_name}" when both date and place are available
2. IF an event has a place but no date, THEN THE display format SHALL be "{type} — {place_name}"
3. IF an event has a date but no place, THEN THE display format SHALL remain "{type} — {date}"
4. IF an event has neither date nor place, THEN THE display format SHALL be "{type}"
5. THE place name SHALL be resolved by looking up the event's PlaceRef.place_id in the project's places list
6. IF the place_id cannot be resolved to a place record, THEN THE event item SHALL omit the place name (treat as if no place)
7. IF the resolved place has non-null latitude AND non-null longitude, THEN THE event item SHALL display the map icon (from IconRegistry.get_map_icon()) after the text as a decoration
8. IF the resolved place does not have coordinates (latitude or longitude is null), THEN THE event item SHALL NOT display the map icon

### Requirement 11: Technology Stack and Licensing

**User Story:** As a developer, I want the map feature to use MIT/BSD-compatible dependencies with no API keys required, so that the project remains freely distributable under its MIT license.

#### Acceptance Criteria

1. THE map rendering SHALL use Leaflet.js (BSD-2-Clause license) loaded from a CDN or bundled locally
2. THE map tiles SHALL use OpenStreetMap (ODbL license) with proper attribution text visible on the map
3. THE map embedding SHALL use QWebEngineView and QWebChannel from PySide6 (already a project dependency)
4. THE feature SHALL add "PySide6-WebEngine>=6.6.0" to project dependencies
5. THE feature SHALL NOT require any API keys, paid services, or user registration to function
6. ALL JavaScript and CSS needed for the map SHALL be either loaded from CDN or bundled as static assets within the project

