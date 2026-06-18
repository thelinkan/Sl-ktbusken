# Requirements Document

## Introduction

This specification covers UI enhancements to the existing Släktbusken genealogy desktop application (Python/PySide6). The enhancements improve visual identification of entities, streamline navigation via recent projects and context menus, provide user feedback during long operations, and allow DNA cluster management from the person editor. All enhancements build on the existing menu structure, person editor, diagram views, and DNA editor.

## Glossary

- **Släktbusken**: The genealogy desktop application (the system under development)
- **Diagram_Panel**: The right panel in the UI displaying family, ancestry, or descendants views
- **Person_List_Panel**: The left panel in the UI displaying a filterable list of persons
- **Edit_Window**: A modal or tabbed window for editing person data, events, photos, and DNA information
- **Main_Person**: The designated central person in the genealogy project
- **Person_Box**: A visual rectangle in diagram views representing a person, showing configurable content fields
- **Event_Icon**: A small graphical symbol representing an event type (birth, death, marriage, etc.)
- **Gender_Icon**: A small graphical symbol representing a person's sex value (M, F, X, U)
- **Direct_Ancestor**: A person connected to the Main_Person through an unbroken chain of parent links going upward (parent, grandparent, great-grandparent, etc.)
- **Direct_Descendant**: A person connected to the Main_Person through an unbroken chain of child links going downward (child, grandchild, great-grandchild, etc.)
- **Recent_Projects_List**: An ordered list of previously opened project file paths stored in application settings
- **Context_Menu**: A right-click popup menu offering actions relevant to the clicked entity
- **Progress_Overlay**: A visual indicator displayed during long-running operations showing that the application is busy
- **DNA_Cluster**: A named grouping of DNA profiles, existing as a separate entity
- **DNA_Profile**: A DNA test linked to a person and a company

## Requirements

### Requirement 1: Event Type Icons

**User Story:** As a researcher, I want distinct icons for each event type, so that I can quickly identify event types in lists and person boxes without reading text labels.

#### Acceptance Criteria

1. THE Släktbusken SHALL provide a distinct icon for each of the following event types: birth, baptism, death, burial, cremation, marriage, divorce, divorce_filed, engagement, emigration, immigration, census, confirmation, first_communion, adoption, blessing, graduation, retirement, will, name_change, gender_correction, custom_individual_event, and custom_family_event
2. WHEN an event is displayed in an event list within the Edit_Window, THE Släktbusken SHALL display the corresponding Event_Icon to the left of the event type text
3. WHEN a Person_Box displays event information (birth date, death date), THE Släktbusken SHALL display the corresponding Event_Icon adjacent to the event data
4. THE Släktbusken SHALL render Event_Icons at a consistent size of 16x16 pixels in lists and 12x12 pixels in Person_Boxes, scaled proportionally with the diagram zoom level
5. IF an event type has no assigned icon (custom events without a recognized type), THEN THE Släktbusken SHALL display a generic event icon as fallback

### Requirement 2: Gender Icons

**User Story:** As a researcher, I want distinct icons for each gender value, so that I can visually identify a person's sex at a glance in diagrams and lists.

#### Acceptance Criteria

1. THE Släktbusken SHALL provide a distinct icon for each sex value: M (male, blue), F (female, red), X (other, green), and U (unknown, yellow)
2. WHEN a Person_Box is rendered in any diagram view, THE Släktbusken SHALL display the Gender_Icon corresponding to the person's sex value in the top-right corner of the Person_Box
3. WHEN a person is displayed in the Person_List_Panel, THE Släktbusken SHALL display the Gender_Icon to the left of the person's name
4. THE Släktbusken SHALL render Gender_Icons at a consistent size of 16x16 pixels in the Person_List_Panel and 14x14 pixels in Person_Boxes, scaled proportionally with the diagram zoom level

### Requirement 3: Direct Ancestor Visual Marking

**User Story:** As a researcher, I want direct ancestors of the main person visually marked in diagrams, so that I can easily trace the lineage path.

#### Acceptance Criteria

1. WHEN a diagram view is rendered, THE Diagram_Panel SHALL compute which persons are Direct_Ancestors of the Main_Person by traversing parent links upward from the Main_Person
2. WHEN a person is identified as a Direct_Ancestor of the Main_Person, THE Diagram_Panel SHALL render that person's Person_Box with a red border (2 pixels wide) to distinguish it from non-ancestor persons
3. WHEN the Main_Person changes, THE Diagram_Panel SHALL recompute and update the Direct_Ancestor markings within 1 second for projects with up to 10,000 persons
4. THE Diagram_Panel SHALL NOT mark the Main_Person itself with the ancestor border, as the Main_Person is neither an ancestor nor a descendant of itself

### Requirement 4: Direct Descendant Visual Marking

**User Story:** As a researcher, I want direct descendants of the main person visually marked in diagrams, so that I can see the descendant lineage at a glance.

#### Acceptance Criteria

1. WHEN a diagram view is rendered, THE Diagram_Panel SHALL compute which persons are Direct_Descendants of the Main_Person by traversing child links downward from the Main_Person
2. WHEN a person is identified as a Direct_Descendant of the Main_Person, THE Diagram_Panel SHALL render that person's Person_Box with a green border (2 pixels wide) to distinguish it from non-descendant persons
3. WHEN the Main_Person changes, THE Diagram_Panel SHALL recompute and update the Direct_Descendant markings within 1 second for projects with up to 10,000 persons
4. IF a person is both a Direct_Ancestor and a Direct_Descendant of the Main_Person (circular reference in data), THEN THE Diagram_Panel SHALL display the ancestor marking (red border) taking precedence over the descendant marking (green border) and log a warning indicating a data inconsistency

### Requirement 5: Recently Opened Projects

**User Story:** As a researcher, I want quick access to recently opened projects from the file menu, so that I can resume work without navigating the file system each time.

#### Acceptance Criteria

1. WHEN the user opens or creates a project, THE Släktbusken SHALL add that project's file path to the top of the Recent_Projects_List, removing any duplicate entry of the same path
2. THE Släktbusken SHALL store the Recent_Projects_List in the application-level settings file, persisting across application sessions
3. THE Släktbusken SHALL display the Recent_Projects_List as a submenu under the Arkiv menu, showing up to 10 most recently opened projects with their project name and file path
4. WHEN the user clicks an entry in the Recent_Projects_List submenu, THE Släktbusken SHALL open that project, following the same procedure as the regular open-project action
5. IF a project file in the Recent_Projects_List no longer exists at the stored path, THEN THE Släktbusken SHALL display that entry as disabled (greyed out) in the submenu and display a tooltip indicating the file was not found
6. THE Släktbusken SHALL limit the Recent_Projects_List to a maximum of 10 entries, removing the oldest entry when a new one would exceed the limit

### Requirement 6: Default Project and Auto-Open

**User Story:** As a researcher, I want to set a default project that opens automatically when the application starts, so that I can begin working immediately without manual navigation.

#### Acceptance Criteria

1. WHEN the user opens the settings dialog, THE Släktbusken SHALL provide an option to set the currently open project as the default project
2. THE Släktbusken SHALL store the default project file path in the application-level settings file
3. WHEN the application starts and a default project is configured, THE Släktbusken SHALL automatically open that project without user interaction
4. IF the default project file no longer exists at the stored path when the application starts, THEN THE Släktbusken SHALL display a Swedish-language notification indicating that the default project could not be found, clear the default project setting, and continue to the normal empty state
5. WHEN the user opens the settings dialog, THE Släktbusken SHALL provide an option to clear the default project setting

### Requirement 7: Person Context Menu

**User Story:** As a researcher, I want a right-click context menu on persons in diagrams and the person list, so that I can quickly access common person-related actions.

#### Acceptance Criteria

1. WHEN the user right-clicks a person in the Diagram_Panel (any view), THE Släktbusken SHALL display a Context_Menu with the following actions in order: Gör aktuell, Redigera person, Ny partner, Ny pappa, Ny mamma, Nytt barn, Visa släktskap med huvudpersonen
2. WHEN the user right-clicks a person in the Person_List_Panel, THE Släktbusken SHALL display the same Context_Menu with the same actions in the same order
3. WHEN the user selects "Gör aktuell" from the Context_Menu, THE Släktbusken SHALL set the right-clicked person as the active person in the Diagram_Panel
4. WHEN the user selects "Redigera person" from the Context_Menu, THE Släktbusken SHALL open the Edit_Window for the right-clicked person
5. WHEN the user selects "Ny partner" from the Context_Menu, THE Släktbusken SHALL open a dialog to create a new person or select an existing person to add as a partner to the right-clicked person
6. WHEN the user selects "Ny pappa" from the Context_Menu, THE Släktbusken SHALL open a dialog to create a new person or select an existing person to add as the father of the right-clicked person
7. WHEN the user selects "Ny mamma" from the Context_Menu, THE Släktbusken SHALL open a dialog to create a new person or select an existing person to add as the mother of the right-clicked person
8. WHEN the user selects "Nytt barn" from the Context_Menu, THE Släktbusken SHALL open a dialog to create a new person or select an existing person to add as a child of the right-clicked person
9. WHEN the user selects "Visa släktskap med huvudpersonen" from the Context_Menu, THE Släktbusken SHALL invoke the Relationship_Calculator with the right-clicked person and the Main_Person as the two selected persons and display the result
10. IF the right-clicked person is the Main_Person and the user selects "Visa släktskap med huvudpersonen", THEN THE Släktbusken SHALL display a Swedish-language message indicating that the selected person is already the main person

### Requirement 8: Progress Indicators for Long Operations

**User Story:** As a researcher, I want visual feedback when the application is performing a long operation, so that I know the program is working and that I should wait.

#### Acceptance Criteria

1. WHEN the user initiates a file load operation, THE Släktbusken SHALL display a Progress_Overlay with a Swedish-language message "Laddar projekt..." and an animated progress indicator
2. WHEN the user initiates a file save operation, THE Släktbusken SHALL display a Progress_Overlay with a Swedish-language message "Sparar projekt..." and an animated progress indicator
3. WHEN the user initiates a GEDCOM import operation, THE Släktbusken SHALL display a Progress_Overlay with a Swedish-language message "Importerar GEDCOM..." and an animated progress indicator
4. WHEN the user initiates a GEDCOM export operation, THE Släktbusken SHALL display a Progress_Overlay with a Swedish-language message "Exporterar GEDCOM..." and an animated progress indicator
5. WHILE a Progress_Overlay is displayed, THE Släktbusken SHALL disable all user input to the main window (mouse clicks and keyboard input), preventing interaction until the operation completes
6. WHEN the long-running operation completes (success or failure), THE Släktbusken SHALL remove the Progress_Overlay and re-enable user input within 100 milliseconds of completion
7. THE Progress_Overlay SHALL be displayed centered over the main window and visually obscure the underlying content with a semi-transparent backdrop

### Requirement 9: DNA Cluster Management from Person Editor

**User Story:** As a researcher, I want to manage DNA cluster memberships directly from the person editor's DNA tab, so that I can organize genetic groupings without switching to the separate DNA editor.

#### Acceptance Criteria

1. WHEN the user opens the DNA tab of the Edit_Window for a person who has at least one DNA_Profile, THE Släktbusken SHALL display a "Klustermedlemskap" section listing all DNA_Clusters the person's profiles belong to, showing cluster name and associated company
2. WHEN the user clicks "Lägg till kluster" in the Klustermedlemskap section, THE Släktbusken SHALL display a selection dialog listing all available DNA_Clusters from the project, allowing the user to select one or more clusters to add the person's profile to
3. WHEN the user selects a cluster in the Klustermedlemskap section and clicks "Ta bort", THE Släktbusken SHALL remove the person's DNA_Profile from that DNA_Cluster
4. WHEN the user adds or removes a cluster membership in the Edit_Window, THE Släktbusken SHALL update the DNA_Cluster entity's member list accordingly so that the change is reflected in the DNA editor as well
5. IF the person has multiple DNA_Profiles, THEN THE Släktbusken SHALL allow the user to select which profile to associate with the cluster when adding a membership
6. IF there are no DNA_Clusters defined in the project, THEN THE Släktbusken SHALL display a message in the Klustermedlemskap section indicating that no clusters exist and suggesting the user create clusters in the DNA editor
