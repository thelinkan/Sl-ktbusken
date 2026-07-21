# Requirements Document

## Introduction

This document specifies enhancements to the DNA and cluster section of Släktbusken, a Swedish genealogy desktop application built with PySide6. The changes span the DNA Window (Företag, Profiluppgifter, Segment, Kluster, Triangulering tabs), the person editor DNA matches section, and the underlying data model. Key improvements include combined Y-DNA/mtDNA test support with haplogroups, redesigned cluster and triangulation views, a relationship probability graph based on the Shared cM Project, and various UI refinements.

## Glossary

- **DNA_Editor**: The main DNA and cluster management window accessible from the Redigera menu, containing tabs for companies, profiles, matches, segments, clusters, and triangulations.
- **DNA_Company**: A DNA testing company entity (Företag tab) with name, logo, description, and URL.
- **DNA_Profile**: A DNA test profile/kit belonging to a person, with test type, haplogroup data, company reference, and kit identifiers.
- **DNA_Match**: A DNA match record between two profiles with shared cM, segment count, and related data.
- **DNA_Cluster**: A grouping of persons and DNA matches with associated notes.
- **DNA_Triangulation**: A triangulated DNA relationship between three or more profiles including company, shared cM, segment count, largest segment, notes, and profile list.
- **Triangulation_Detail_View**: The read-only information panel showing triangulation details in the DNA_Editor triangulation tab.
- **Cluster_Panel**: The redesigned cluster tab with a left cluster list, right person list, and bottom notes section.
- **Relationship_Graph**: A dialog displaying a graph of possible relationships for a given shared cM value, based on The Shared cM Project data.
- **Shared_cM_Project**: Research data by Blaine T. Bettinger mapping centimorgan values to relationship probabilities (version 4.0, March 2020).
- **Person_Search_Widget**: A widget allowing search and selection of a person from the project database by name.
- **DNA_Raw_Data**: Raw genotype data file containing SNP data (rsID, chromosome, position, alleles) imported from DNA testing companies.
- **DNA_Viewer**: A dialog showing a searchable/filterable table of raw DNA genotype data for a specific profile.
- **Chromosome_Browser**: A visual diagram displaying all autosomal chromosomes as horizontal bars with colored regions indicating shared DNA match segments and their relative sizes.

## Requirements

### Requirement 1: Combined Y-DNA/mtDNA Test Type

**User Story:** As a genealogist, I want to register a combined Y-DNA/mtDNA test, so that I can represent DNA kits that include both paternal and maternal line testing.

#### Acceptance Criteria

1. THE DNA_Profile SHALL support a test type value of "combined" in addition to "autosomal", "y-dna", and "mtdna"
2. WHEN the test type "combined" is selected, THE DNA_Editor profile form SHALL display input fields for both a Y-DNA haplogroup (max 50 characters) and an mtDNA haplogroup (max 50 characters)
3. WHEN the test type "y-dna" is selected, THE DNA_Editor profile form SHALL display an input field for a Y-DNA haplogroup only (max 50 characters)
4. WHEN the test type "mtdna" is selected, THE DNA_Editor profile form SHALL display an input field for an mtDNA haplogroup only (max 50 characters)
5. WHEN the test type "autosomal" is selected, THE DNA_Editor profile form SHALL hide all haplogroup input fields
6. THE DNA_Profile data model SHALL include optional fields for y_haplogroup (string, max 50 characters) and mt_haplogroup (string, max 50 characters)
7. WHEN the test type is changed to a value that does not include a given haplogroup field, THE DNA_Editor profile form SHALL preserve any previously entered haplogroup value in the data model without clearing it
8. IF the user enters a haplogroup value exceeding 50 characters, THEN THE DNA_Editor profile form SHALL prevent input beyond the 50-character limit

### Requirement 2: Triangulation List Display Enhancement

**User Story:** As a genealogist, I want to see which persons are included in a triangulation directly in the list, so that I can quickly identify triangulation groups without opening each one.

#### Acceptance Criteria

1. THE DNA_Editor triangulation list SHALL display each entry in the format "{company} ({x} profiler): {person1}, {person2}, ..." where x is the number of profiles, company is resolved from the triangulation's company_id, and each person name is resolved by following profile_id → DnaProfile.person_id → Person.names[0] displayed as "{given} {surname}"
2. IF a profile_id in a triangulation cannot be resolved to a person name because the profile, person, or person name is missing, THEN THE DNA_Editor triangulation list SHALL display that profile's position using the text "(okänd)" as a placeholder in the comma-separated name list
3. WHEN the combined text of a triangulation list entry exceeds the visible width of the list widget, THE DNA_Editor triangulation list SHALL truncate the displayed text with an ellipsis character ("…") at the end, preserving the full text accessible via tooltip

### Requirement 3: DNA Company - Logo and URL Enhancements

**User Story:** As a genealogist, I want to manage company logos visually and store company URLs, so that I can better organize my DNA testing company information.

#### Acceptance Criteria

1. THE DNA_Editor company form SHALL hide the Logo media-ID text field and its label from the user interface
2. WHILE the user is creating or editing a company, THE DNA_Editor company form SHALL display a logo chooser button labeled "Välj logo..." that opens a file dialog filtered to image files (png, jpg, jpeg, gif, svg, bmp, webp) for selecting a logo image
3. WHEN the user selects a logo image via the file dialog, THE DNA_Editor company form SHALL display a preview of the selected logo image scaled to 64×64 pixels while maintaining aspect ratio
4. IF no logo is assigned to the company or the logo file cannot be found on disk, THEN THE DNA_Editor company form SHALL display a distinct placeholder in the 64×64 preview area indicating the missing state
5. IF the user cancels the file dialog without selecting a file, THEN THE DNA_Editor company form SHALL retain the previously assigned logo unchanged
6. THE DNA_Company data model SHALL include a URL field storing a text value with a maximum length of 2048 characters
7. THE DNA_Editor company form SHALL display an editable URL text field with a maximum input length of 2048 characters

### Requirement 4: DNA Profile - Person Display and Admin Simplification

**User Story:** As a genealogist, I want the profile form to show the person name instead of an internal ID and to have a searchable admin person field, so that the interface is more user-friendly.

#### Acceptance Criteria

1. WHEN a DNA profile is loaded in the DNA_Editor profile form, THE DNA_Editor profile form SHALL display the person's name (given name followed by surname from the first PersonName entry) as a read-only label in place of the editable person_id text field
2. IF the person_id references a person not found in the project data, THEN THE DNA_Editor profile form SHALL display the raw person_id string as the read-only label
3. THE DNA_Editor profile form SHALL provide a Person_Search_Widget for the admin_person_id field that allows searching for a person by name and displays the selected person's name
4. IF the user clears the Person_Search_Widget selection for admin_person_id, THEN THE DNA_Editor profile form SHALL store a null value for admin_person_id
5. THE DNA_Editor profile form SHALL remove the admin_status field from the user interface
6. THE DNA_Profile data model SHALL remove the admin_status field

### Requirement 5: Remove Segment Tab

**User Story:** As a genealogist, I want the segment tab removed from the DNA window, so that the interface is simplified (segment data remains in the data model for internal use).

#### Acceptance Criteria

1. THE DNA_Editor SHALL NOT display a tab with the label "Segment" in its tab widget
2. THE DNA_Editor SHALL display exactly 5 tabs in the following order: Företag, Profiler, Matchningar, Kluster, Triangulering
3. WHEN a project file containing dna_segments data is loaded, THE DNA_Editor SHALL preserve all existing DnaSegment entries in the ProjectData.dna_segments list without modification
4. WHEN a project is saved, THE DNA_Editor SHALL persist the ProjectData.dna_segments list to the project file, retaining all segment records that were present at load time

### Requirement 6: Swap Kluster and Triangulering Tab Positions

**User Story:** As a genealogist, I want the Kluster tab placed before the Triangulering tab, so that the workflow order matches how I use the DNA window.

#### Acceptance Criteria

1. THE DNA_Editor tab order SHALL be: Företag, Profiler, Matchningar, Kluster, Triangulering
2. WHEN the DNA_Editor is opened, THE tab widget SHALL display tabs in the order specified above with Kluster at index 3 and Triangulering at index 4
3. IF the user has not manually reordered tabs, THEN THE DNA_Editor SHALL present the Kluster tab at index 3 and the Triangulering tab at index 4

### Requirement 7: Triangulation Detail View Redesign

**User Story:** As a genealogist, I want the triangulation details section to show only read-only information with an edit button that opens the same editing dialog as in Redigera Person, so that editing is consistent across the application.

#### Acceptance Criteria

1. THE Triangulation_Detail_View SHALL display the following fields as read-only labels when a triangulation is selected: Företag (company name), Delad cM (shared cM formatted to 2 decimal places), Antal segment (segment count), Största segment (largest segment cM formatted to 2 decimal places), Anteckningar (notes), and a list of profiles included in the triangulation showing each profile's display name
2. THE Triangulation_Detail_View SHALL provide a "Redigera" (Edit) button that is enabled only when a triangulation is selected in the triangulations list
3. WHEN the "Redigera" button is clicked, THE DNA_Editor SHALL open the DnaTriangulationDialog in edit mode, pre-populated with the currently selected triangulation's data, using the same dialog instance as used from the person editor (Redigera person)
4. WHEN the edit dialog is closed with saved changes (accepted), THE Triangulation_Detail_View SHALL update the corresponding triangulation in project data and refresh its displayed fields to reflect the saved values
5. IF the edit dialog is cancelled, THEN THE Triangulation_Detail_View SHALL retain its previously displayed data without modification to project data

### Requirement 8: Cluster Tab Redesign - Split Panel Layout

**User Story:** As a genealogist, I want the cluster tab to show a list of clusters on the left, and on the right a list of persons in the selected cluster with a notes section below, so that I can work with clusters more efficiently.

#### Acceptance Criteria

1. THE Cluster_Panel SHALL split horizontally into a left section occupying approximately 30% of the panel width showing a scrollable list of clusters, and a right section occupying the remaining width
2. THE Cluster_Panel right section SHALL display a scrollable list of persons belonging to the selected cluster in the upper area, showing at minimum each person's name
3. THE Cluster_Panel right section SHALL display an "Anteckningar" (notes) multi-line text area in the lower area, with a minimum height of 3 visible text lines
4. WHEN a cluster is selected in the left list, THE Cluster_Panel right section SHALL update to show that cluster's persons and notes within 500 milliseconds
5. THE DNA_Cluster notes field SHALL be persisted as part of the cluster data in the project file
6. IF no cluster is selected in the left list, THEN THE Cluster_Panel right section SHALL display an empty persons list and a disabled notes text area
7. WHEN the user edits the notes text area and selects a different cluster, THE Cluster_Panel SHALL persist the edited notes content for the previously selected cluster before displaying the newly selected cluster's data

### Requirement 9: Cluster Context Menu - Filter on DNA Matches

**User Story:** As a genealogist, I want to right-click a person in the cluster person list and filter on DNA matches for that person, so that I can quickly see which other cluster members share DNA with a specific person.

#### Acceptance Criteria

1. WHEN a person in the Cluster_Panel person list is right-clicked, THE Cluster_Panel SHALL display a context menu with the option "Filtrera på DNA-träffar" (Filter on DNA matches)
2. IF the right-clicked person does not have at least one DnaProfile registered in the project, THEN THE context menu option "Filtrera på DNA-träffar" SHALL be disabled (grayed out)
3. WHEN "Filtrera på DNA-träffar" is activated for a person, THE Cluster_Panel SHALL switch the "Visa filtrerade" toggle to checked state and display only persons within the current cluster that have at least one DnaMatch linking a profile of the right-clicked person with a profile of the displayed person
4. IF "Filtrera på DNA-träffar" is activated and no other persons in the current cluster have a DnaMatch with the right-clicked person, THEN THE Cluster_Panel SHALL display an empty person list with no items
5. WHEN the "Visa filtrerade" toggle button is unchecked, THE Cluster_Panel SHALL exit the filtered mode and display all persons in the currently selected cluster
6. WHEN the user selects a different cluster while the "Visa filtrerade" mode is active, THE Cluster_Panel SHALL exit the filtered mode, uncheck the toggle, and display all persons in the newly selected cluster

### Requirement 10: Relationship Probability Graph

**User Story:** As a genealogist, I want to see a graph of possible relationships based on shared cM when viewing a DNA match, so that I can estimate how I am related to a match.

#### Acceptance Criteria

1. THE person editor DNA matches section SHALL provide a button labeled "Relationsdiagram" to display the Relationship_Graph for the selected match
2. IF no DNA match is selected in the person editor DNA matches list, THEN THE application SHALL disable the Relationship_Graph button
3. WHEN the Relationship_Graph button is clicked, THE application SHALL open a modal dialog showing a bar chart of possible relationships and their probabilities based on the shared cM value (ranging from 1 to 3,500 cM) of the selected match
4. THE Relationship_Graph SHALL use data from The Shared cM Project (version 4.0, March 2020) to map cM values to relationship probabilities
5. THE Relationship_Graph dialog SHALL display attribution text crediting The Shared cM Project by Blaine T. Bettinger
6. THE Relationship_Graph SHALL display relationship type names on the vertical axis and probability percentages (0–100%) on the horizontal axis, showing only relationships with a probability greater than 0% for the given cM value
7. IF the selected match has a shared cM value of 0 or has no probability data in The Shared cM Project dataset, THEN THE application SHALL display the dialog with an informational message indicating that no relationship probabilities are available for the given cM value

### Requirement 11: Raw DNA Data Import

**User Story:** As a genealogist, I want to import raw DNA data files from testing companies and associate them with DNA profiles, so that I can store and access my genotype data within the application.

#### Acceptance Criteria

1. WHEN the user opens the "Redigera DNA-profil" (Edit DNA Profile) dialog, THE dialog SHALL provide an import control allowing the user to add a raw DNA data file by selecting it from disk via a file dialog filtered to supported formats (TXT, CSV), and IF the profile already has a raw data file associated, THEN the import control SHALL also provide an option to remove or replace the existing association
2. WHEN the user selects a valid AncestryDNA file (tab-delimited with columns rsid, chromosome, position, allele1, allele2 and comment header lines starting with #), THE application SHALL parse the file, display a progress indicator during processing, and store the genotype data in JSON format in the `dna/` subfolder relative to the project file using a unique filename based on the DNA_Profile identifier
3. WHEN the user selects a valid MyHeritage file (CSV with quoted fields, columns RSID, CHROMOSOME, POSITION, RESULT and comment/header lines starting with # or ##), THE application SHALL parse the file, display a progress indicator during processing, and store the genotype data in JSON format in the `dna/` subfolder relative to the project file using a unique filename based on the DNA_Profile identifier
4. IF the selected file does not match any supported format (AncestryDNA or MyHeritage), THEN THE application SHALL display an error message indicating that the file format is not recognized and list the supported formats (AncestryDNA tab-delimited TXT, MyHeritage CSV)
5. IF the selected file matches a supported format structure but contains unparseable data rows, THEN THE application SHALL skip invalid rows, complete the import with valid rows, and display a warning message indicating the number of rows that could not be parsed
6. THE DNA_Profile data model SHALL include an optional reference field (file path or identifier) pointing to the stored DNA_Raw_Data file in the `dna/` subfolder
7. WHEN a raw data file has already been imported for another DNA_Profile belonging to the same person, THE "Redigera DNA-profil" dialog SHALL display a selectable list of existing raw data files for that person with an option to reuse (link) one instead of importing a new file
8. WHEN the user chooses to reuse an existing raw data file, THE DNA_Profile SHALL store the same file reference as the other profile without duplicating the stored data
9. THE application SHALL store raw DNA data files separately from the main project JSON file to avoid excessive file size growth (raw data files are approximately 20 MB each)
10. WHILE the DNA section of "Redigera person" (Edit Person) displays a DNA profile that has a raw data file associated, THE section SHALL display a "DNA-visare" button to the right of the "Redigera" button for that profile
11. IF a DNA profile does not have a raw data file associated, THEN THE "DNA-visare" button SHALL NOT be displayed for that profile
12. IF the user selects a file larger than 100 MB, THEN THE application SHALL reject the import and display an error message indicating the maximum supported file size is 100 MB

### Requirement 12: DNA Data Viewer

**User Story:** As a genealogist, I want to view my raw DNA data in a searchable table, so that I can look up specific SNPs and genotype information.

#### Acceptance Criteria

1. WHEN the "DNA-visare" button is clicked for a DNA profile, THE application SHALL open the DNA_Viewer dialog displaying all raw genotype data rows associated with that profile with no filters applied
2. THE DNA_Viewer SHALL display the data in a table with columns: rsID, Kromosom (Chromosome), Position, Alleler (Alleles)
3. THE DNA_Viewer SHALL provide a text search field (maximum 100 characters) that filters displayed rows to those where rsID, chromosome, or position contains the search text as a case-insensitive substring match
4. THE DNA_Viewer SHALL provide a chromosome filter dropdown listing an "Alla" (All) option followed by individual chromosome values present in the loaded data set (e.g., 1–22, X, Y, MT), with "Alla" selected by default
5. WHEN the search field text or chromosome filter selection is updated, THE DNA_Viewer SHALL display only rows that satisfy both the search text match AND the selected chromosome filter, updating the table within 500 milliseconds
6. THE DNA_Viewer SHALL support displaying data sets of up to 1,000,000 SNP rows while keeping the UI thread responsive to user input within 200 milliseconds, using virtual scrolling or pagination
7. IF the raw data file referenced by the profile cannot be found or read, THEN THE DNA_Viewer SHALL display an error message indicating that the data file is missing or unreadable and SHALL NOT display the data table

### Requirement 13: DNA Match Data Import via Paste

**User Story:** As a genealogist, I want to paste CSV match data from MyHeritage into the DNA match editor, so that I can quickly import chromosome segment data for a match.

#### Acceptance Criteria

1. THE "Ny DNA-matchning" and "Redigera DNA-matchning" (New/Edit DNA Match) dialogs SHALL provide a text area labeled "Klistra in matchdata" (Paste match data) positioned between the Anteckningar (notes) section and the Välj profiler (Choose profiles) section, where the user can paste CSV-formatted match data
2. WHEN the user pastes MyHeritage match format data (CSV with header row "Name,Match Name,Chromosome,Start Location,End Location,Start RSID,End RSID,Centimorgans,SNPs"), THE application SHALL skip the header row and parse each subsequent data row into a DnaSegment record with chromosome, start position, end position, start rsID, end rsID, centimorgan value, and SNP count
3. WHEN match data is successfully parsed, THE application SHALL display a preview table of the parsed segments (chromosome, start, end, cM) and the total shared cM before the user confirms the import
4. IF the "Profil 2" field in the match dialog is not filled and the pasted data contains a match person name (column "Match Name"), THEN THE application SHALL search for persons in the project whose name matches the match name (case-insensitive substring on given name and surname) and suggest a DNA_Profile belonging to a matching person (excluding Profil 1)
5. IF no matching person or profile is found for the match name in the pasted data, THEN THE application SHALL display a warning dialog stating that no matching person was found and ask the user whether the match should be created anyway with Profil 2 unset
6. WHEN the user confirms the import, THE application SHALL store the match segment data in a separate JSON file in the `dna/` subfolder and reference the file from the DnaMatch record in the main project data
7. IF the pasted text cannot be parsed as valid CSV match data (missing required columns or no valid data rows), THEN THE application SHALL display an error message indicating the paste format is not recognized and show the expected column format
8. IF the DnaMatch already has segment data from a previous import, THEN THE application SHALL ask the user whether to replace the existing segment data or cancel the new paste operation
9. WHEN parsing data rows, IF a row contains non-numeric values in the Centimorgans or SNPs columns, THEN THE application SHALL skip that row and include it in a count of skipped rows displayed to the user after parsing

### Requirement 14: DNA Match Data Storage

**User Story:** As a genealogist, I want match segment data stored separately from my main project file, so that the project file remains manageable in size.

#### Acceptance Criteria

1. THE application SHALL store DNA match segment data (imported via paste or other means) in a separate JSON file within the `dna/` subfolder relative to the project file, using the naming convention `match_segments_{match_id}.json` where `{match_id}` is the DnaMatch record's unique identifier
2. THE DnaMatch data model SHALL include an optional string field `segment_file` containing the filename of the external match segment data file in the `dna/` subfolder (maximum 255 characters)
3. WHEN match segment data is saved, THE application SHALL write the data in JSON format containing an array of segment records with fields: chromosome (string), start_position (integer), end_position (integer), start_rsid (string), end_rsid (string), centimorgans (float), and snp_count (integer)
4. WHEN a DnaMatch with a non-null `segment_file` reference is loaded, THE application SHALL read the referenced segment file from the `dna/` subfolder and populate the segment list in memory
5. IF the referenced match segment file cannot be found or read during project load, THEN THE application SHALL log a warning and load the DnaMatch record without segment data, marking the DnaMatch in the matches list with a visual indicator (such as a warning icon or text label) visible to the user in any view displaying that match
6. THE application SHALL store all DNA-related auxiliary files (raw data and match segments) in the `dna/` subfolder to maintain a consistent project directory structure
7. WHEN the application saves match segment data and the `dna/` subfolder does not exist relative to the project file, THE application SHALL create the `dna/` subfolder before writing the segment file
8. WHEN a DnaMatch that has an associated segment file is deleted from the project, THE application SHALL delete the corresponding segment file from the `dna/` subfolder

### Requirement 15: Chromosome Match Visualization

**User Story:** As a genealogist, I want to see a visual chromosome browser showing where DNA matches occur across all autosomal chromosomes, so that I can understand the size and location of shared segments at a glance.

#### Acceptance Criteria

1. WHEN the user views match segment data for a specific DnaMatch that has segment data loaded, THE application SHALL provide a "Kromosomvy" (Chromosome view) button that opens the Chromosome_Browser dialog
2. IF the selected DnaMatch does not have segment data loaded (segment_file is null or the file could not be read), THEN THE "Kromosomvy" button SHALL be disabled
3. THE Chromosome_Browser SHALL display all 22 autosomal chromosomes as horizontal bars arranged vertically and labeled with their chromosome number (1–22), with each bar's rendered width proportional to the chromosome's base-pair length using the GRCh37/hg19 reference genome chromosome lengths
4. WHERE the X chromosome is included in the segment data, THE Chromosome_Browser SHALL display an additional horizontal bar labeled "X" below chromosome 22, scaled proportionally using the GRCh37/hg19 reference length for chromosome X
5. WHEN match segments exist for a chromosome, THE Chromosome_Browser SHALL highlight the matching regions on that chromosome's bar using a visually distinct color fill that contrasts with the neutral chromosome background color, with each colored segment's horizontal position calculated as (start_position / chromosome_length) and width calculated as ((end_position - start_position) / chromosome_length) relative to the chromosome bar width
6. THE Chromosome_Browser SHALL scale each highlighted segment's width proportionally to the segment's base-pair span relative to the total length of that chromosome, so that larger matches appear visually larger
7. WHEN a highlighted match segment is wide enough to contain text (at least 40 pixels rendered width), THE Chromosome_Browser SHALL display the centimorgan value (formatted to 1 decimal place) as a label within the highlighted segment
8. IF a highlighted match segment is narrower than 40 pixels rendered width, THEN THE Chromosome_Browser SHALL omit the inline centimorgan label for that segment, with the value still accessible via tooltip
9. WHEN the user hovers over a highlighted match segment, THE Chromosome_Browser SHALL display a tooltip showing the chromosome number, start position, end position, centimorgan value, and SNP count for that segment
10. IF a DnaMatch has no segments on a given chromosome, THEN THE Chromosome_Browser SHALL display that chromosome's bar in a neutral background color without any highlighted regions
11. THE Chromosome_Browser dialog SHALL display a summary header showing the match person name (resolved from Profil 2's profile_id → DnaProfile.person_id → Person first name and surname), total shared cM (formatted to 2 decimal places), and total number of segments
12. IF the Profil 2 person name cannot be resolved (profile, person, or name is missing), THEN THE Chromosome_Browser summary header SHALL display "(okänd)" as the match person name
