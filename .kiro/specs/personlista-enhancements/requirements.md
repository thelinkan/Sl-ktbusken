# Requirements Document

## Introduction

This feature enhances the Personlista (person list panel) in Släktbusken with additional columns, improved filtering, visual indicators for ancestry/descendancy and multiple names, DNA company icons, reduced space usage, and bidirectional selection synchronization with the diagram panel.

## Glossary

- **Person_List_Panel**: The left panel (`PersonListPanel`) displaying a filterable, sorted list of all persons in the project.
- **Diagram_Panel**: The right panel (`DiagramPanel`) displaying family tree views (family, ancestry, descendants).
- **Main_Person**: The person designated as the main person in the project settings (`project.main_person_id`).
- **Active_Person**: The person currently centred in the Diagram_Panel.
- **Ancestor_Dot**: A coloured dot indicator placed between the gender icon and name, denoting that the person is an ancestor of the Main_Person.
- **Descendant_Dot**: A coloured dot indicator placed between the gender icon and name, denoting that the person is a descendant of the Main_Person.
- **Column_Header**: A header row above the person list entries displaying labels for each visible column.
- **DNA_Company_Icon**: A small icon (16×16 pixels) representing a DNA testing company, resolved from the company's logo media file.
- **PersonDisplayInfo**: The pre-computed display data structure for a person in the list.
- **Filter_Dialog**: The non-modal dialog for entering filter criteria on the person list.
- **Multiple_Names_Indicator**: A visual marker on a person list entry indicating that the person has more than one Name record (e.g. birth name and married name).
- **Splitter**: The horizontal QSplitter dividing Person_List_Panel (left) and Diagram_Panel (right).

## Requirements

### Requirement 1: Additional Columns

**User Story:** As a genealogist, I want to see Titel, Yrke, Kluster, and DNA company columns in the person list, so that I can quickly identify key attributes without opening the person editor.

#### Acceptance Criteria

1. THE Person_List_Panel SHALL display the following columns for each person entry: gender icon, ancestry/descendancy dot, name, birth–death years, Titel, Yrke, Kluster, and DNA company.
2. THE Person_List_Panel SHALL display a Column_Header row above the person entries with labels for each visible column.
3. THE Person_List_Panel SHALL populate the Titel column with the person's `title` field value, displaying an empty cell when no title is set.
4. THE Person_List_Panel SHALL populate the Yrke column with the person's `occupation` field value, displaying an empty cell when no occupation is set.
5. THE Person_List_Panel SHALL populate the Kluster column with a comma-separated list of DNA cluster names the person belongs to, displaying an empty cell when the person belongs to no clusters.
6. THE Person_List_Panel SHALL populate the DNA company column with icons for each company that has a DnaProfile for the person, displaying an empty cell when the person has no profiles.
7. WHEN a column value exceeds the available column width, THE Person_List_Panel SHALL truncate the displayed text with an ellipsis and display the full value in a tooltip on mouse hover.

### Requirement 2: Column Visibility Settings

**User Story:** As a genealogist, I want to configure which columns are visible in the person list, so that I can focus on the information relevant to my current research task.

#### Acceptance Criteria

1. THE Person_List_Panel SHALL provide a Column_Header context menu (triggered by right-clicking the Column_Header) listing each configurable column (Titel, Yrke, Kluster, and DNA company) with a checkbox indicating its current visibility state.
2. THE Person_List_Panel SHALL default all configurable columns to visible when no persisted visibility settings exist.
3. WHEN the user toggles a column's checkbox in the Column_Header context menu, THE Person_List_Panel SHALL show or hide the affected column without requiring additional user action.
4. THE Person_List_Panel SHALL persist column visibility settings between application sessions via the application settings service, saving the visibility state whenever a column is toggled.
5. THE Person_List_Panel SHALL always display the gender icon, ancestry/descendancy dot, name, and birth–death years columns (these are not configurable and do not appear in the visibility context menu).
6. WHEN the application starts, THE Person_List_Panel SHALL restore column visibility settings from the application settings service.
7. IF persisted column visibility settings are missing or cannot be read, THEN THE Person_List_Panel SHALL fall back to the default state (all configurable columns visible).

### Requirement 3: DNA Company Icons Column

**User Story:** As a genealogist, I want to see icons for each DNA company where a person has a test profile, so that I can quickly identify which companies have tested that person.

#### Acceptance Criteria

1. THE Person_List_Panel SHALL display one DNA_Company_Icon (16×16 pixels) for each distinct DNA company that has a DnaProfile associated with the person.
2. WHEN a person has profiles at multiple DNA companies, THE Person_List_Panel SHALL display the icons side-by-side in the DNA company column, ordered by company name alphabetically, up to a maximum of 5 visible icons; if there are more than 5 distinct companies, only the first 5 alphabetically SHALL be displayed.
3. THE Person_List_Panel SHALL resolve DNA_Company_Icons from the company's `logo_media_id` field, using the project folder path to locate the image file.
4. IF a DNA company has no `logo_media_id` or the logo file cannot be resolved, THEN THE Person_List_Panel SHALL display a generic placeholder icon (16×16 pixels) for that company.
5. WHEN a person has no DNA profiles, THE Person_List_Panel SHALL display an empty cell in the DNA company column.
6. WHEN the user hovers the mouse over a DNA_Company_Icon, THE Person_List_Panel SHALL display a tooltip showing the DNA company name.

### Requirement 4: Ancestor and Descendant Dot Indicators

**User Story:** As a genealogist, I want to see coloured dots next to persons who are ancestors or descendants of the main person, so that I can visually identify lineage relationships in the person list.

#### Acceptance Criteria

1. WHEN a person is an ancestor of the Main_Person, THE Person_List_Panel SHALL display an Ancestor_Dot (a filled circle of 8 pixels diameter) between the gender icon and the name.
2. WHEN a person is a descendant of the Main_Person, THE Person_List_Panel SHALL display a Descendant_Dot (a filled circle of 8 pixels diameter) between the gender icon and the name.
3. WHEN a person is both an ancestor and a descendant of the Main_Person (e.g. through pedigree collapse), THE Person_List_Panel SHALL display the Ancestor_Dot followed by the Descendant_Dot (left to right) between the gender icon and the name.
4. WHEN a person is neither an ancestor nor a descendant of the Main_Person, THE Person_List_Panel SHALL display no dot in the indicator position.
5. THE Person_List_Panel SHALL render the Ancestor_Dot in the same colour as the ancestor diagram frame (`_ANCESTOR_BORDER_COLOR`, #C0392B red) and the Descendant_Dot in the same colour as the descendant diagram frame (`_DESCENDANT_BORDER_COLOR`, #27AE60 green), matching the existing `PersonBoxItem` border colours so that the visual language is consistent across the application.
6. WHEN the Main_Person is not set in the project, THE Person_List_Panel SHALL display no dots for any person.
7. THE Person_List_Panel SHALL compute ancestor and descendant sets by traversing family relationships from the Main_Person through parent-child links, terminating gracefully when a cycle is detected (a person already visited during traversal).
8. WHEN the Main_Person is the person being displayed, THE Person_List_Panel SHALL display no dot for that person (the Main_Person is neither counted as their own ancestor nor their own descendant).
9. WHEN the Main_Person setting changes, THE Person_List_Panel SHALL recompute the ancestor and descendant sets and update all dot indicators within 2 seconds for projects containing up to 50,000 persons.

### Requirement 5: Cluster Filter

**User Story:** As a genealogist, I want to filter the person list by cluster membership, so that I can focus on persons belonging to a specific DNA cluster.

#### Acceptance Criteria

1. THE Filter_Dialog SHALL provide a cluster filter text field with a case-insensitive substring-matching autocomplete populated from all DNA cluster names present in the current project.
2. WHEN a cluster filter value is entered and the filter is applied, THE Person_List_Panel SHALL display only persons who are members of at least one cluster whose name contains the filter value as a case-insensitive substring, combined with any other active filter criteria using AND logic.
3. WHEN the cluster filter field is cleared and the filter is applied, THE Person_List_Panel SHALL remove the cluster restriction from the filter criteria and display persons matching the remaining active criteria.
4. WHEN the project contains no DNA clusters, THE Filter_Dialog SHALL display the cluster filter field with an empty autocomplete list and accept no valid completions.

### Requirement 6: Name Filter Across All Name Versions

**User Story:** As a genealogist, I want the name filter to search across all name versions (birth name, married name, name changes), so that I can find a person regardless of which name I remember.

#### Acceptance Criteria

1. WHEN a given name filter is entered, THE Person_List_Panel SHALL match against the given name of every Name record belonging to the person, not only the first (primary) name, ignoring any asterisk markers in the given name during comparison.
2. WHEN a surname filter is entered, THE Person_List_Panel SHALL match against the surname of every Name record belonging to the person, not only the first (primary) name.
3. THE Person_List_Panel SHALL treat the name filter as a case-insensitive substring match applied to each name version independently.
4. WHEN any one of the person's name versions matches the filter, THE Person_List_Panel SHALL include that person in the filtered results.
5. WHEN both a given name filter and a surname filter are active, THE Person_List_Panel SHALL include a person if any Name record satisfies the given name filter AND any Name record satisfies the surname filter (the filters are evaluated independently across all name records).

### Requirement 7: Multiple Names Indicator

**User Story:** As a genealogist, I want to see a visual marker on persons who have multiple names (birth, married, changed), and view all names on hover, so that I can identify and inspect name variations without opening the editor.

#### Acceptance Criteria

1. WHEN a person has more than one Name record, THE Person_List_Panel SHALL display a Multiple_Names_Indicator immediately to the right of the person's displayed name text.
2. WHEN the user hovers the mouse over the Multiple_Names_Indicator, THE Person_List_Panel SHALL display a tooltip listing all Name records for that person in their stored order, showing one line per name in the format "type: given surname", omitting any component (given or surname) that is empty.
3. WHEN a person has exactly one Name record, THE Person_List_Panel SHALL not display the Multiple_Names_Indicator.
4. THE Multiple_Names_Indicator SHALL be a distinct visual symbol that does not duplicate the shape or colour of the Ancestor_Dot, Descendant_Dot, or DNA_Company_Icon.
5. WHEN the user moves the mouse away from the Multiple_Names_Indicator, THE Person_List_Panel SHALL hide the tooltip.

### Requirement 8: Reduced Person List Width

**User Story:** As a genealogist, I want the person list to take up less horizontal space so that the diagram panel has more room for displaying family trees.

#### Acceptance Criteria

1. THE Splitter SHALL set the initial width of the Person_List_Panel to 250 pixels at application startup, regardless of window size.
2. THE Person_List_Panel SHALL have a minimum width of 250 pixels that the Splitter enforces during manual resizing.
3. THE Splitter SHALL allow the user to manually resize the boundary between Person_List_Panel and Diagram_Panel by dragging, up to a maximum Person_List_Panel width of 50% of the current window width.
4. WHEN the Person_List_Panel width is less than 350 pixels, THE Person_List_Panel SHALL switch to compact column layout by displaying column headers truncated to a maximum of 4 characters followed by an ellipsis and reducing cell horizontal padding to 2 pixels.
5. WHEN the Person_List_Panel width is 350 pixels or greater, THE Person_List_Panel SHALL display full column header labels and use default cell horizontal padding of 6 pixels.

### Requirement 9: Bidirectional Selection Synchronization

**User Story:** As a genealogist, I want the person list to highlight the person that is currently active in the diagram, so that I always know which person the diagram is focused on.

#### Acceptance Criteria

1. WHEN the Diagram_Panel emits a person_activated signal (triggered by the A-key shortcut), THE Person_List_Panel SHALL set the corresponding person entry as the current selected item and scroll the list so that the item is visible within the viewport.
2. WHEN the Person_List_Panel selects a person entry in response to a diagram synchronization call, THE Person_List_Panel SHALL apply the selection without emitting the person_selected signal (to avoid circular signal loops between the panels).
3. IF the activated person is not present in the current filtered view of the Person_List_Panel, THEN THE Person_List_Panel SHALL switch the toggle to the unfiltered view (updating the toggle button state to reflect "Visa filtrerade") and then select the person entry.
4. WHEN a person is single-clicked in the Person_List_Panel, THE Person_List_Panel SHALL emit the person_selected signal to navigate the Diagram_Panel to that person (existing behaviour preserved).
5. IF the activated person_id does not match any entry in the full unfiltered person list, THEN THE Person_List_Panel SHALL clear the current selection and not change the view.
