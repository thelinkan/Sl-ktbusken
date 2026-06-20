# Requirements Document

## Introduction

This feature enhances the DNA tab in the "Redigera Person" (Edit Person) window of Släktbusken. The enhancements include adding icons to the DNA profile and match sections, adding edit capabilities for DNA profiles and matches, enforcing same-company profile filtering when adding/editing matches, adding a triangulation section with add/edit capabilities and person validation logic, and moving the cluster section to its own tab to make room for triangulation.

## Glossary

- **Person_Editor**: The modal dialog for editing a person record, containing multiple tabs (Namn, Händelser, Foton, DNA, Kluster).
- **DNA_Tab**: The tab within the Person_Editor that displays the person's DNA profiles, DNA matches, and triangulations.
- **Cluster_Tab**: A new separate tab within the Person_Editor dedicated to cluster membership management, moved from the DNA tab.
- **DNA_Profile**: A DNA test profile (`DnaProfile` dataclass) belonging to a person, associated with a company and test type.
- **DNA_Match**: A DNA match record (`DnaMatch` dataclass) linking two DNA profiles via `profile1_id` and `profile2_id`.
- **DNA_Triangulation**: A triangulated overlap of segments across multiple profiles (`DnaTriangulation` dataclass) with company, chromosome, overlap range, segment IDs, and profile IDs.
- **DNA_Company**: A DNA testing company (`DnaCompany` dataclass) with an ID, name, and optional logo.
- **DNA_Cluster**: A grouping of DNA matches and persons into a cluster (`DnaCluster` dataclass).
- **Project_Data**: The in-memory data store (`ProjectData`) containing all project entities.
- **Active_Person**: The person currently being edited in the Person_Editor.
- **Company_Logo_Icon**: A small icon (24x24) resolved from a DNA_Company's `logo_media_id` field, displayed inline in list items.
- **Profile_Dialog**: The modal dialog (`DnaProfileDialog`) used for creating or editing a DNA_Profile.
- **Match_Dialog**: The modal dialog (`DnaMatchDialog`) used for creating or editing a DNA_Match.
- **Triangulation_Section**: The UI section within the DNA_Tab that displays triangulations involving the Active_Person.
- **Same_Company_Constraint**: The rule that both profiles in a DNA_Match must belong to the same DNA_Company.
- **Triangulation_Person_Constraint**: The rule that a triangulation can only combine two persons who both have matches with the Active_Person and with each other.

## Requirements

### Requirement 1: Icons in DNA Profiles Section

**User Story:** As a genealogist, I want to see company logos next to each DNA profile entry in the DNA tab, so that I can quickly identify which testing company each profile belongs to.

#### Acceptance Criteria

1. WHEN the DNA_Tab displays a DNA_Profile entry in the profiles list, THE Person_Editor SHALL display the Company_Logo_Icon as a 24×24 pixel icon to the left of the profile text.
2. IF the DNA_Company associated with a DNA_Profile has no `logo_media_id` or the company cannot be resolved, THEN THE Person_Editor SHALL display an empty icon (no visible graphic) for that profile entry.
3. IF the logo file path resolves from the DNA_Company but the file does not exist on disk, THEN THE Person_Editor SHALL display a distinct "missing file" indicator icon for that profile entry.
4. THE Person_Editor SHALL resolve the Company_Logo_Icon using the existing `resolve_profile_logo_icon` function from the DNA editor module, passing the DNA_Profile, project data, and project folder path.
5. WHEN the DNA_Tab profiles list is displayed, THE Person_Editor SHALL set the list widget icon size to 24×24 pixels so that all profile icons render at uniform dimensions.

### Requirement 2: Icons in DNA Matches Section

**User Story:** As a genealogist, I want to see company logos next to each DNA match entry in the DNA tab, so that I can quickly identify which company the match originates from.

#### Acceptance Criteria

1. WHEN the DNA_Tab displays a DNA_Match entry in the matches list, THE Person_Editor SHALL display the Company_Logo_Icon as a 24×24 pixel icon to the left of the match text, scaled with preserved aspect ratio using smooth transformation.
2. THE Person_Editor SHALL determine the company for a DNA_Match by resolving the company_id from the DnaProfile referenced by the match's profile2_id, then locating the DnaCompany with that company_id.
3. IF the DNA_Company associated with a DNA_Match has no `logo_media_id`, or the referenced MediaItem cannot be found, or the project folder is not set, THEN THE Person_Editor SHALL display an empty placeholder icon (QIcon with no pixmap) for that match entry.
4. IF the logo file path resolves through the chain (DnaCompany → MediaItem → file) but the file does not exist on disk, THEN THE Person_Editor SHALL display a distinct missing-file indicator icon (visually differentiated from the empty placeholder) for that match entry.
5. IF the resolved logo image file cannot be loaded (unsupported format or corrupt), THEN THE Person_Editor SHALL display the empty placeholder icon for that match entry.

### Requirement 3: Edit DNA Profile

**User Story:** As a genealogist, I want to edit an existing DNA profile from the DNA tab, so that I can correct or update profile information without having to delete and recreate it.

#### Acceptance Criteria

1. WHILE no DNA_Profile is selected in the profiles list, THE DNA_Tab SHALL display the "Redigera" (Edit) button in a disabled state, and SHALL enable the button when a profile is selected.
2. WHEN the user clicks the edit button with a DNA_Profile selected, THE Person_Editor SHALL open the Profile_Dialog pre-populated with the selected profile's current company, test type, kit name, kit ID, and notes values.
3. WHEN the user double-clicks a DNA_Profile entry in the profiles list, THE Person_Editor SHALL open the Profile_Dialog pre-populated with the selected profile's current company, test type, kit name, kit ID, and notes values.
4. WHEN the user saves changes in the Profile_Dialog during an edit operation, THE Person_Editor SHALL validate the input using the same rules as profile creation (company required, test type required, notes no longer than 2000 characters) and update the existing DNA_Profile in Project_Data with the modified values while preserving the original profile ID and person ID.
5. IF validation fails when saving edits in the Profile_Dialog, THEN THE Profile_Dialog SHALL display the validation error messages and remain open without modifying the existing DNA_Profile.
6. WHEN the user saves changes in the Profile_Dialog during an edit operation, THE Person_Editor SHALL refresh the profiles list and the matches list to reflect updated profile information.
7. WHEN the user cancels the Profile_Dialog during an edit operation, THE Person_Editor SHALL preserve the original DNA_Profile data without modification.

### Requirement 4: Edit DNA Match

**User Story:** As a genealogist, I want to edit an existing DNA match from the DNA tab, so that I can correct match data (cM values, segment counts) without deleting and recreating.

#### Acceptance Criteria

1. THE DNA_Tab SHALL provide an "Redigera" (Edit) button for the DNA matches section that is enabled when a match is selected in the list and disabled when no match is selected.
2. WHEN the user clicks the edit button with a DNA_Match selected, THE Person_Editor SHALL open the Match_Dialog pre-populated with the selected match's profile1_id, profile2_id, shared_cm, shared_percentage, segment_count, largest_segment_cm, match_source, and notes values.
3. WHEN the user double-clicks a DNA_Match entry in the matches list, THE Person_Editor SHALL open the Match_Dialog pre-populated with the selected match's profile1_id, profile2_id, shared_cm, shared_percentage, segment_count, largest_segment_cm, match_source, and notes values.
4. WHEN the user saves changes in the Match_Dialog during an edit operation, THE Person_Editor SHALL update the existing DNA_Match in Project_Data with the modified values while preserving the original match ID.
5. WHEN the user saves changes in the Match_Dialog during an edit operation, THE Person_Editor SHALL refresh the matches list to reflect updated match information.
6. WHEN the user cancels the Match_Dialog during an edit operation, THE Person_Editor SHALL preserve the original DNA_Match data without modification.
7. WHEN the Match_Dialog is in edit mode, THE Match_Dialog SHALL enforce the same validation rules as creation mode: shared_cm must be greater than 0, profile 1 and profile 2 must be different profiles, and notes must not exceed 2000 characters.

### Requirement 5: Same-Company Profile Filtering for Matches

**User Story:** As a genealogist, I want the match dialog to only show profiles from the same company as my selected profile, so that I cannot accidentally create matches between tests from different companies (which is scientifically invalid).

#### Acceptance Criteria

1. WHEN the user selects a value in the Profile 1 dropdown of the Match_Dialog, THE Match_Dialog SHALL filter the Profile 2 dropdown to display only DNA_Profiles that belong to the same DNA_Company as the selected Profile 1, excluding the selected Profile 1 itself.
2. WHEN the user changes the Profile 1 selection in the Match_Dialog, THE Match_Dialog SHALL re-filter the Profile 2 dropdown and reset the Profile 2 selection to the placeholder.
3. WHILE no Profile 1 is selected in the Match_Dialog, THE Match_Dialog SHALL disable the Profile 2 dropdown and display a placeholder indicating that Profile 1 must be selected first.
4. WHEN editing an existing DNA_Match, THE Match_Dialog SHALL pre-select Profile 1 and filter Profile 2 to show only same-company profiles, with the existing Profile 2 pre-selected.
5. THE Match_Dialog SHALL determine "same company" by comparing the `company_id` field of the DNA_Profile records.
6. IF the same-company filter results in zero available profiles for Profile 2, THEN THE Match_Dialog SHALL display an informational message indicating no matchable profiles exist for the selected company and SHALL disable the OK button.

### Requirement 6: Triangulation Section in DNA Tab

**User Story:** As a genealogist, I want to see triangulations involving the active person in the DNA tab, so that I can view confirmed shared ancestor segments.

#### Acceptance Criteria

1. THE DNA_Tab SHALL display a "Trianguleringar" label and a list widget below the DNA matches section.
2. WHEN the DNA_Tab loads for a person, THE Person_Editor SHALL collect all DnaProfile IDs belonging to the Active_Person and populate the triangulation list with every DNA_Triangulation record whose profile_ids list contains at least one of those profile IDs.
3. WHEN the triangulation list displays a DNA_Triangulation entry, THE Person_Editor SHALL format each entry as "Kromosom {chromosome}: {overlap_start}–{overlap_end} ({N} profiler)" where N is the count of profile_ids in that triangulation.
4. WHEN the triangulation list displays a DNA_Triangulation entry, THE Person_Editor SHALL display the Company_Logo_Icon for the triangulation's company_id to the left of the entry text, falling back to a default placeholder icon if the logo cannot be resolved.
5. IF no triangulations exist for the Active_Person, THEN THE DNA_Tab SHALL display an empty triangulation list with no placeholder message.

### Requirement 7: Add Triangulation

**User Story:** As a genealogist, I want to add a new triangulation from the DNA tab, so that I can record confirmed shared segments between three or more matching persons.

#### Acceptance Criteria

1. THE DNA_Tab SHALL provide a "Lägg till triangulering" (Add triangulation) button below the triangulation list.
2. WHEN the user clicks the add triangulation button, THE Person_Editor SHALL open a triangulation dialog for creating a new DNA_Triangulation.
3. THE triangulation dialog SHALL require the user to select a DNA_Company, a chromosome, and specify overlap start and end positions.
4. THE triangulation dialog SHALL validate that overlap_start is less than overlap_end before allowing save.
5. WHEN the user saves the triangulation dialog, THE Person_Editor SHALL create a new DNA_Triangulation in Project_Data and refresh the triangulation list.
6. WHEN the user cancels the triangulation dialog, THE Person_Editor SHALL discard the new triangulation without modifying Project_Data.

### Requirement 8: Edit Triangulation

**User Story:** As a genealogist, I want to edit an existing triangulation from the DNA tab, so that I can update or correct triangulation data.

#### Acceptance Criteria

1. THE DNA_Tab SHALL provide an "Redigera" (Edit) button for the triangulation section that is enabled when a triangulation is selected and disabled when no triangulation is selected.
2. WHEN the user clicks the edit button with a DNA_Triangulation selected, THE Person_Editor SHALL open the triangulation dialog pre-populated with the selected triangulation's data.
3. WHEN the user double-clicks a triangulation entry in the list, THE Person_Editor SHALL open the triangulation dialog pre-populated with the selected triangulation's data.
4. WHEN the user saves changes in the triangulation dialog during an edit operation, THE Person_Editor SHALL update the existing DNA_Triangulation in Project_Data and refresh the triangulation list.
5. WHEN the user cancels the triangulation dialog during an edit operation, THE Person_Editor SHALL preserve the original DNA_Triangulation data without modification.

### Requirement 9: Triangulation Person Validation

**User Story:** As a genealogist, I want the triangulation dialog to only allow selecting persons who have mutual DNA matches with the active person and each other, so that triangulations are scientifically valid.

#### Acceptance Criteria

1. WHEN presenting person selection in the triangulation dialog, THE Person_Editor SHALL only offer persons where both of the following conditions are met: (a) a DNA_Match exists between a profile of the Active_Person and a profile of the candidate person, and (b) for each already-selected person in the triangulation, a DNA_Match exists between a profile of that selected person and a profile of the candidate person.
2. WHEN the user selects any person in the triangulation dialog, THE Person_Editor SHALL re-filter the remaining person options to only show persons who have DNA_Matches with both the Active_Person and every already-selected person.
3. IF fewer than two eligible persons exist for triangulation with the Active_Person, THEN THE triangulation dialog SHALL disable the save button and display an informational message indicating that at least two mutually matching persons are required.
4. THE Person_Editor SHALL determine match existence by checking if any DNA_Match record links a profile of person A with a profile of person B, regardless of profile1_id/profile2_id order.
5. WHEN the user removes a previously-selected person from the triangulation, THE Person_Editor SHALL re-filter the candidate list to reflect the updated set of selected persons, potentially making previously-excluded persons available again.
6. WHEN a company is selected for the triangulation, THE Person_Editor SHALL further restrict person candidates to those having at least one DNA_Profile belonging to the selected DNA_Company.

### Requirement 10: Move Cluster Section to Own Tab

**User Story:** As a genealogist, I want the cluster membership section in its own tab, so that the DNA tab is not overcrowded and triangulation fits naturally alongside profiles and matches.

#### Acceptance Criteria

1. THE Person_Editor SHALL display cluster membership in a separate "Kluster" tab instead of within the DNA_Tab.
2. THE Cluster_Tab SHALL contain the cluster membership label ("Klustermedlemskap:"), the clusters list widget, and the add/remove cluster buttons ("Lägg till kluster" and "Ta bort") with the same layout and behavior as the current DNA_Tab implementation.
3. WHEN the Person_Editor loads, THE Cluster_Tab SHALL appear as the tab immediately following the DNA_Tab (tab index 4 in the order: Namn, Händelser, Foton, DNA, Kluster).
4. THE DNA_Tab tab text SHALL read "DNA" instead of "DNA & Kluster".
5. THE Cluster_Tab tab text SHALL be "Kluster".
6. THE Cluster_Tab SHALL preserve all existing cluster management functionality including adding a person to clusters via a multi-select dialog, removing a person from clusters with selection validation, and displaying the informational message "Inga kluster finns i projektet" when the project contains no clusters.
7. THE DNA_Tab SHALL retain only the DNA profiles label and list, the DNA matches label and list, the triangulations label and list, and their associated action buttons, with no cluster-related widgets remaining.
