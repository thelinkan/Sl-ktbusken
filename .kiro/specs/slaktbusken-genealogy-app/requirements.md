# Requirements Document

## Introduction

Släktbusken is a genealogy desktop application built in Python with PySide6, focused on the Swedish genealogical research context. The application stores tree data in a gzipped JSON format, supports GEDCOM import/export with translation layers, provides DNA match management, relationship calculation, and interactive diagram views. A future read-only web application will share the same data format for presenting research to authenticated users.

## Glossary

- **Släktbusken**: The genealogy desktop application (the system under development)
- **Project_Folder**: The folder structure containing the main data file, settings, translation files, and media for one genealogy project
- **App_JSON**: The application's internal gzipped JSON data format (.json.gz) storing all genealogy data
- **GEDCOM**: A standard file format for exchanging genealogical data between programs
- **Translation_File**: JSON files that map GEDCOM identifiers to App_JSON identifiers for sources, places, and persons/relationships
- **Person**: An individual in the genealogy tree with names, sex, events, media, and DNA data
- **Family**: A relationship unit consisting of partners and children, with linked events
- **Event**: An occurrence (birth, death, marriage, etc.) with participants, date, place, sources, and media
- **Place**: A geographical location in a hierarchical structure (country > county > parish > church/cemetery)
- **Source**: Documentary evidence supporting genealogical facts, with provider, type, and structured references
- **Church_Book_Series**: The series code identifying the type of Swedish church record (e.g., AI for Husförhörslängd, CI for Födelseboken, FI for Död- och begravningsbok). These codes vary slightly between parishes and time periods and are stored as free text.
- **Media_Item**: A file (photo, source image, death notice, grave photo, logo, document) linked to entities
- **DNA_Company**: A DNA testing company with name, notes, and logo
- **DNA_Profile**: A DNA test linked to a person and a company, with kit details and admin info
- **DNA_Match**: A match between two DNA profiles with shared cM, percentage, segment count, and largest segment
- **DNA_Segment**: Chromosome segment data with start/end position, cM, and SNP count
- **DNA_Cluster**: A named grouping of DNA profiles, existing as a separate entity
- **DNA_Triangulation**: Overlapping segment data across multiple profiles
- **Relationship_Calculator**: A module that computes genealogical and legal relationships between two persons
- **GEDCOM_Importer**: The module responsible for importing GEDCOM files and converting them to App_JSON using Translation_Files
- **GEDCOM_Exporter**: The module responsible for exporting App_JSON data to GEDCOM format with stable IDs
- **Person_List_Panel**: The left panel in the UI displaying a filterable list of persons
- **Diagram_Panel**: The right panel in the UI displaying family, ancestry, or descendants views
- **Edit_Window**: A modal or tabbed window for editing person data, events, photos, and DNA information
- **Main_Person**: The designated central person in the genealogy project
- **ParentChildLink**: A record linking a specific parent to a specific child within a Family, with a parentage_type indicating the nature of the relationship (biological, legal, adoptive, foster, step, or unknown_donor)

## Requirements

### Requirement 1: Project Folder Creation

**User Story:** As a researcher, I want to create a new genealogy project with the correct folder structure, so that I can begin entering or importing data.

#### Acceptance Criteria

1. WHEN the user creates a new project, THE Släktbusken SHALL prompt the user for a project name (1–100 characters) and a file system location, then create a Project_Folder at that location containing: an App_JSON file with empty sections for all top-level data arrays, a settings file, a translation subfolder (with empty sources.json, places.json, and persons.json files), and a media subfolder with category subfolders (source-image, photos, death-notice, obituary, funeral-program, grave-photo, map, logo, document)
2. WHEN the user creates a new project, THE Släktbusken SHALL store the project name in the App_JSON project metadata section
3. WHEN the user creates a new project, THE Släktbusken SHALL set the format identifier to "släktbuske-file", version to "0.1", created_by to "Släktbuske", and language to "sv-SE" in the App_JSON metadata
4. IF the Project_Folder cannot be created due to a file system error (permission denied, disk full, or invalid path), THEN THE Släktbusken SHALL display a Swedish-language error message indicating the failure reason and not leave a partially created folder structure

### Requirement 2: App-JSON Data Format

**User Story:** As a researcher, I want a comprehensive data format that stores all genealogy and DNA data, so that no information is lost between sessions.

#### Acceptance Criteria

1. THE App_JSON SHALL contain top-level sections for: format identifier, version, project metadata, persons, families, events, places, sources, media, dna_companies, dna_profiles, dna_matches, dna_segments, dna_clusters, dna_triangulations, and research_notes
2. THE App_JSON SHALL store project metadata with fields for: title (max 200 characters), main_person_id, created_by, and language code
3. THE App_JSON SHALL store Person records with fields for: unique ID, sex (one of: M, F, X, U), multiple names (each with type, given name, surname), profile media ID, notes, optional title (maximum 100 characters), and optional occupation (maximum 100 characters)
4. THE App_JSON SHALL store Family records with fields for: unique ID, list of partners (each with person_id and role), ordered list of children (as person IDs), list of parent_child_links (each with child_id, parent_id or null, and parentage_type), and linked event IDs
5. THE App_JSON SHALL store Event records with fields for: unique ID, type, list of participants (each with person_id and role), date (with value, precision, and source references), place (with place_id and source references), and media IDs
6. THE App_JSON SHALL store Place records in a hierarchical structure with fields for: unique ID, type (country, county, parish, church, cemetery), name, parent_place_id, coordinates (latitude, longitude), and notes
7. THE App_JSON SHALL store Source records with fields for: unique ID, provider, source_type, title, reference_text, provider_ref, short_note, free_note, structured_reference (type-specific fields), and media IDs
8. THE App_JSON SHALL store Media_Item records with fields for: unique ID, type, file path, title, linked_entities (each with entity_type, entity_id, and role), and optional type-specific fields (publication info, transcription, mentioned person IDs)
9. WHEN a source reference is attached to a fact, THE App_JSON SHALL store the source_id, quality level (one of: primary, secondary, questionable), and an optional note within the source_ref structure
10. THE App_JSON SHALL support multiple source references for a single fact (date, place, or other attributed datum)
11. THE App_JSON SHALL support linking one Source to multiple facts across different events and persons
12. THE App_JSON SHALL store Research_Note records with fields for: unique ID, title, text, and a list of linked_entities (each with entity_type and entity_id)

### Requirement 3: File Persistence

**User Story:** As a researcher, I want my data saved in a compressed format, so that file sizes remain manageable for large family trees.

#### Acceptance Criteria

1. WHEN the user saves the project, THE Släktbusken SHALL serialize the App_JSON data as UTF-8 JSON and write it to a gzip-compressed file with the .json.gz extension
2. WHEN saving, THE Släktbusken SHALL first write the new data to a temporary file, then atomically replace the existing file, ensuring that a crash during save does not corrupt the previous version
3. WHEN the user opens an existing project, THE Släktbusken SHALL decompress and parse the .json.gz file into the internal data model
4. IF the .json.gz file is corrupted or unreadable (invalid gzip header, JSON parse error, or missing required top-level sections), THEN THE Släktbusken SHALL display a Swedish-language error message identifying the specific problem and preserve any existing backup file without overwriting it

### Requirement 4: GEDCOM Import

**User Story:** As a researcher, I want to import GEDCOM files from other genealogy programs, so that I can migrate existing research into Släktbusken.

#### Acceptance Criteria

1. WHEN a GEDCOM file is imported and no Translation_Files exist in the project's translation subfolder, THE GEDCOM_Importer SHALL create Translation_Files for sources, places, and persons/relationships mapping GEDCOM IDs to App_JSON IDs
2. WHEN a GEDCOM file is imported and Translation_Files already exist in the project's translation subfolder, THE GEDCOM_Importer SHALL use the existing Translation_Files to match GEDCOM IDs to their previously assigned App_JSON IDs, updating existing records and adding only entities not present in the Translation_Files
3. WHEN the first GEDCOM import is performed, THE Släktbusken SHALL prompt the user to select the Main_Person for the project from the list of imported persons
4. WHEN a GEDCOM file contains sources, THE GEDCOM_Importer SHALL translate them into the App_JSON structured source format using the source Translation_File
5. WHEN a GEDCOM file contains places, THE GEDCOM_Importer SHALL translate them into the hierarchical place structure using the place Translation_File
6. WHEN a GEDCOM file contains persons, families, and events, THE GEDCOM_Importer SHALL translate them into the corresponding App_JSON person, family, and event records using the persons/relationships Translation_File
7. IF the selected file is not a valid GEDCOM file or cannot be parsed, THEN THE GEDCOM_Importer SHALL display a Swedish-language error message indicating the parsing failure and abort the import without modifying the existing App_JSON or Translation_Files
8. IF a GEDCOM file contains records of unsupported GEDCOM record types or malformed data, THEN THE GEDCOM_Importer SHALL log a warning in Swedish identifying each skipped record by its GEDCOM line number and tag, and continue processing the remaining valid data

### Requirement 5: GEDCOM Export

**User Story:** As a researcher, I want to export my data to GEDCOM format, so that I can share research with users of other genealogy programs.

#### Acceptance Criteria

1. WHEN the user exports to GEDCOM, THE GEDCOM_Exporter SHALL produce a GEDCOM 5.5.1-compliant file encoded in UTF-8, containing all persons, families, events, sources, and places from the project
2. THE GEDCOM_Exporter SHALL generate stable GEDCOM IDs derived from the App_JSON person and family IDs, ensuring that repeated exports of unchanged data produce identical GEDCOM IDs for the same entities
3. WHEN an event references a place_id, THE GEDCOM_Exporter SHALL resolve the Place hierarchy and write the full place name as comma-separated inline text ordered from most specific to least specific (e.g., "Ljusdals kyrka, Ljusdal, Gävleborgs län, Sverige")
4. WHEN an event or fact references a source_id, THE GEDCOM_Exporter SHALL resolve the Source record and write an inline GEDCOM source citation using the source's reference_text if present, or a concatenation of the structured_reference fields formatted according to GEDCOM 5.5.1 source citation conventions
5. WHEN a GEDCOM field requires data composed from multiple App_JSON fields (e.g., structured_reference fields combined into a single citation string), THE GEDCOM_Exporter SHALL concatenate those fields into a single string following the order and formatting defined by GEDCOM 5.5.1
6. IF a data element in App_JSON has no GEDCOM equivalent, THEN THE GEDCOM_Exporter SHALL omit that element and present a Swedish-language summary to the user after export completion listing all omitted element types and their count
7. WHEN the export completes without omitted elements, THE GEDCOM_Exporter SHALL present a Swedish-language confirmation indicating the number of persons, families, and sources exported

### Requirement 6: Translation File Editing

**User Story:** As a researcher, I want to edit source and place translation mappings, so that future GEDCOM imports produce correct App_JSON data.

#### Acceptance Criteria

1. WHEN the user opens the source translation editor, THE Släktbusken SHALL display a searchable list of GEDCOM source identifiers showing, for each entry, the GEDCOM identifier and the mapped App_JSON source title
2. WHEN the user modifies a source translation mapping and saves, THE Släktbusken SHALL validate that the target App_JSON source record exists, then persist the change to the source Translation_File in JSON format
3. WHEN the user opens the place translation editor, THE Släktbusken SHALL display a searchable list of GEDCOM place strings showing, for each entry, the GEDCOM place string and the mapped App_JSON place name with its hierarchy
4. WHEN the user modifies a place translation mapping and saves, THE Släktbusken SHALL validate that the target App_JSON place record exists, then persist the change to the place Translation_File in JSON format
5. WHEN the user adds a new mapping entry in either translation editor, THE Släktbusken SHALL allow the user to specify a GEDCOM identifier and select a target App_JSON record, then persist the new entry to the corresponding Translation_File
6. IF the source or place Translation_File cannot be saved due to a file system error, THEN THE Släktbusken SHALL display a Swedish-language error message indicating the failure reason and retain the unsaved changes in the editor

### Requirement 7: Person Management

**User Story:** As a researcher, I want to add, view, and edit person records with multiple names and detailed attributes, so that I can accurately represent individuals in the tree.

#### Acceptance Criteria

1. THE Släktbusken SHALL display a Person record with all associated names, sex, profile photo, notes, linked events, linked families, and DNA information (profiles, matches, and cluster memberships)
2. WHEN the user edits a Person via the Edit_Window, THE Släktbusken SHALL provide tabs for: Names (given, surname, birth surname, title, occupation), Events, Photos, and DNA & Clusters
3. WHEN the user adds a name entry to a Person, THE Släktbusken SHALL store the name with a type (birth, married, adopted, or other), given name, surname fields (each up to 100 characters), and an optional event_id linking the name to the event (e.g., marriage or name_change) that caused the name to take effect
4. WHEN the user selects a profile photo for a Person, THE Släktbusken SHALL store the selected Media_Item ID as the profile_media_id on the Person record
5. WHEN the user creates a new Person, THE Släktbusken SHALL assign a unique stable ID, require a sex value (M, F, X, or U for unknown), and store at least one name entry before the record is saved
6. IF the user attempts to save a Person record with no name entries, THEN THE Släktbusken SHALL display an error message indicating that at least one name entry is required and prevent the save
7. WHEN the user enters a title or occupation for a Person, THE Släktbusken SHALL store each as an optional free-text field of up to 100 characters on the Person record, independent of the Person's name entries.

### Requirement 8: Family Management

**User Story:** As a researcher, I want to create and edit family units with partners and children with per-parent relationship types, so that I can accurately represent biological, legal, adoptive, and foster parentage including complex scenarios like IVF with known or unknown donors.

#### Acceptance Criteria

1. THE Släktbusken SHALL support Family records with two or more partners, each having a specified role (father, mother, husband, wife, partner)
2. THE Släktbusken SHALL support same-sex partnerships by allowing any combination of partner roles
3. WHEN a child is added to a Family, THE Släktbusken SHALL store a ParentChildLink for each partner in the family, where each link contains: the child's person_id, the partner's person_id, and a parentage_type (one of: biological, legal, adoptive, foster, step, unknown_donor)
4. THE Släktbusken SHALL allow different parentage_types for the same child across different partners within a single Family (e.g., one partner as biological and another as legal for the same child)
5. THE Släktbusken SHALL support a Person belonging to multiple families to represent adoption, foster care, and biological parentage
6. IF the user attempts to add a person_id as a partner or child that does not reference an existing Person record, THEN THE Släktbusken SHALL reject the operation and display an error message indicating the missing reference
7. THE Släktbusken SHALL prevent adding the same person_id as a child to the same family more than once
8. WHEN a partner's parentage_type for a child is set to unknown_donor, THE Släktbusken SHALL NOT require a person_id for that partner, allowing representation of anonymous donors without creating a placeholder Person record
9. THE Släktbusken SHALL maintain the order in which children were added to the family
10. THE Relationship_Calculator SHALL use parentage_type to distinguish biological relationships from legal/adoptive/foster relationships when computing kinship paths

### Requirement 9: Event Management

**User Story:** As a researcher, I want to record life events with dates, places, sources, and participants, so that I can document the full history of individuals and families.

#### Acceptance Criteria

1. THE Släktbusken SHALL support individual event types: adoption, baptism, birth, blessing, burial, census, confirmation, cremation, death, emigration, first_communion, gender_correction, graduation, immigration, name_change, retirement, will, and custom_individual_event
2. THE Släktbusken SHALL support family event types: divorce, divorce_filed, engagement, marriage, and custom_family_event
3. WHEN a custom_individual_event or custom_family_event is created, THE Släktbusken SHALL require the user to supply a custom type name (1–100 characters)
4. WHEN an event is created, THE Släktbusken SHALL require a type and at least one participant, and allow optional date, place, sources, media, and type-specific fields
5. WHEN a death event is created, THE Släktbusken SHALL provide a field for cause of death
6. WHEN a family event is created, THE Släktbusken SHALL link all partners of the associated Family as participants
7. THE Släktbusken SHALL store dates in ISO 8601 format (YYYY-MM-DD, YYYY-MM, or YYYY) with a precision field (day, month, year, approximate), and one or more source references
8. THE Släktbusken SHALL store each source reference on a fact with a source_id, quality level (primary, secondary, or tertiary), and optional note

### Requirement 10: Hierarchical Place Management

**User Story:** As a researcher, I want to organize places hierarchically (country > county > parish > church/cemetery), so that I can filter and navigate by geographic level.

#### Acceptance Criteria

1. THE Släktbusken SHALL store places with a parent_place_id forming a hierarchy: country > county > parish > church/cemetery, where each place type can only have a parent of the next higher level (e.g., a parish must have a county as parent)
2. WHEN the user filters events by parish, THE Släktbusken SHALL include events at sub-places (church, cemetery) belonging to that parish
3. WHEN the user creates a place, THE Släktbusken SHALL require a type (country, county, parish, church, cemetery), name (1–200 characters), and optional parent_place_id, coordinates (latitude -90 to 90, longitude -180 to 180), and notes
4. THE Släktbusken SHALL provide a place list editor for viewing, adding, and modifying place records
5. IF the user attempts to delete a place that is referenced by one or more events, THEN THE Släktbusken SHALL display a warning listing the referencing events and require confirmation before deletion

### Requirement 11: Source Management

**User Story:** As a researcher, I want structured source records with provider-specific references, so that I can properly cite and verify my research.

#### Acceptance Criteria

1. THE Släktbusken SHALL store Source records with provider, source_type (one of: church_book, database, death_notice, newspaper, photograph, census, other), title, reference_text, provider_ref, short_note, free_note, structured_reference, and linked media
2. THE Släktbusken SHALL support structured_reference fields specific to source type: for church_book (parish, county_code, series, volume, years, image, page); for database (database_name, record_id); for death_notice (newspaper, publication_date, page); for newspaper (newspaper, date, page, article_title)
3. WHEN a church_book source is stored, THE series field SHALL be free text representing the Swedish church book series code (e.g., "AI" for Husförhörslängd, "CI" for Födelseboken, "FI" for Död- och begravningsbok, "B" for Inflyttningslängd, "C" for Utflyttningslängd, "E" for Lysnings- och vigselbok, "D" for Konfirmationsbok), and the reference_text SHALL store the full human-readable citation string (e.g., "Ljusdal (X) AI:23d (1883-1887) Bild: 23 Sida: 915"), while provider_ref SHALL store any provider-specific shortcut identifier (e.g., "v136004.b88")
4. WHEN the user creates or edits a source, THE Släktbusken SHALL provide a source editor with fields appropriate to the selected source_type, displaying only the structured_reference fields relevant to that type
5. THE Släktbusken SHALL provide a source list editor for viewing, searching (by title or provider), and managing all source records
6. IF the user attempts to delete a source that is referenced by one or more source_refs in events, THEN THE Släktbusken SHALL display a warning listing the referencing events and require confirmation before deletion
7. WHEN a source is imported from GEDCOM and the source text begins with "ArkivDigital:" or contains a reference structure matching the ArkivDigital pattern (parish, county code, series, volume, years, image), THE GEDCOM_Importer SHALL create or link an "ArkivDigital" Repository record and attach it to the Source via a repository_ref

### Requirement 12: Media Management

**User Story:** As a researcher, I want to attach photos, source images, death notices, and other files to persons, events, and sources, so that I have visual evidence linked to my data.

#### Acceptance Criteria

1. THE Släktbusken SHALL store Media_Item records as first-class entities with unique IDs, independent of the entities they reference
2. THE Släktbusken SHALL support media types: photo, source_image, death_notice, obituary, funeral_program, grave_photo, map, logo, and document
3. WHEN a Media_Item is linked to an entity, THE Släktbusken SHALL store the link as a linked_entity entry with entity_type (person, event, source, or place), entity_id, and a role describing the relationship (e.g., portrait, source_scan, evidence, subject, grave, location)
4. THE Släktbusken SHALL allow a single Media_Item to be linked to multiple persons, events, sources, or places
5. WHEN the user views a Media_Item, THE Släktbusken SHALL display the media file together with its title, linked entities, and any type-specific fields (publication info for death notices, transcription text, mentioned person IDs)
6. WHEN the user adds a new Media_Item, THE Släktbusken SHALL prompt for file selection, media type, title, and at least one linked entity before saving the record
7. THE Släktbusken SHALL provide a media list editor for viewing, adding, editing metadata, and deleting media records across all media types
8. IF a Media_Item references a file that cannot be found at its stored path, THEN THE Släktbusken SHALL display a missing-file indicator in place of the media content and retain the Media_Item record with its metadata

### Requirement 13: DNA Company and Profile Management

**User Story:** As a researcher, I want to register DNA companies, tests, and matches, so that I can track genetic connections in my research.

#### Acceptance Criteria

1. THE Släktbusken SHALL store DNA_Company records with: unique ID, name (maximum 200 characters), notes, and logo (via media_id referencing an existing Media_Item of type logo)
2. THE Släktbusken SHALL store DNA_Profile records with: unique ID, person_id (referencing an existing Person), company_id (referencing an existing DNA_Company), test_type (one of: autosomal, y-dna, mtdna), kit_name (maximum 200 characters), kit_id (maximum 100 characters), admin_person_id (referencing an existing Person), admin_status (one of: self, managed_by_user, self_managed), and notes
3. THE Släktbusken SHALL allow a Person to have multiple DNA_Profiles at the same company and across different companies
4. THE Släktbusken SHALL store DNA_Match records with: unique ID, two profile IDs (each referencing an existing DNA_Profile), shared_cM (0.0 to 7400.0), shared_percentage (0.00 to 100.00), segment_count (0 to 10000), largest_segment_cM (0.0 to 300.0), and match_source (internal: both profiles exist in the project; external: one profile represents a match not registered as a Person in the project)
5. WHEN the user edits DNA information for a Person, THE Släktbusken SHALL display all profiles, matches, and cluster memberships associated with that Person
6. IF the user attempts to create a DNA_Profile with a person_id or company_id that does not reference an existing record, THEN THE Släktbusken SHALL reject the operation and display an error message indicating the missing reference

### Requirement 14: DNA Segment, Cluster, and Triangulation Management

**User Story:** As a researcher, I want to record DNA segments, group matches into clusters, and document triangulations, so that I can analyze genetic inheritance patterns.

#### Acceptance Criteria

1. THE Släktbusken SHALL store DNA_Segment records with: unique ID, match_id, chromosome (1–22, X, or Y), start_position, end_position, cM (value greater than zero), and snp_count (zero or greater), where start_position is strictly less than end_position
2. THE Släktbusken SHALL store DNA_Cluster records as separate entities with: unique ID, name (1–200 characters), notes, a list of associated company IDs, a list of member person IDs, a list of linked dna_match IDs, and an optional display color
3. THE Släktbusken SHALL allow a Person (via their DNA_Profile) to belong to multiple DNA_Clusters simultaneously
4. THE Släktbusken SHALL store DNA_Triangulation records with: unique ID, company_id, chromosome, overlap_start, overlap_end, a list of at least two segment IDs whose position ranges share a non-zero overlap on the same chromosome, a list of at least three profile IDs, an optional cluster_id, and notes
5. WHEN the user edits a DNA_Cluster, THE Släktbusken SHALL provide an interface to add or remove member profiles, edit the cluster name and notes, and associate or disassociate DNA matches with the cluster
6. IF the user attempts to add a profile ID to a DNA_Cluster that does not reference an existing DNA_Profile, THEN THE Släktbusken SHALL reject the addition and display an error message indicating the profile could not be found

### Requirement 15: Relationship Calculator

**User Story:** As a researcher, I want to calculate and visualize the relationship between any two persons, so that I can understand how individuals are connected.

#### Acceptance Criteria

1. WHEN the user selects two persons, THE Relationship_Calculator SHALL compute the genealogical relationship (by blood) between them by traversing parent-child links up to a maximum of 30 generations in each direction
2. WHEN the user selects two persons, THE Relationship_Calculator SHALL compute relationships via spouses, adoptions, and foster care in addition to blood relations
3. THE Relationship_Calculator SHALL provide an option to display only genealogical relationships or both genealogical and legal relationships
4. THE Relationship_Calculator SHALL provide an option to display only the closest relationship (fewest generational steps between the two persons) or all possible relationship paths up to a maximum of 50 paths
5. WHEN a relationship is calculated, THE Släktbusken SHALL display the result as both a Swedish-language text description (using standard Swedish kinship terms) and a graphical path diagram showing each person as a node and each parent-child or partner link as a connecting edge
6. THE Släktbusken SHALL allow the user to print the relationship graph
7. IF no relationship path is found between the two selected persons within the configured scope, THEN THE Relationship_Calculator SHALL display a Swedish-language message indicating that no relationship was found

### Requirement 16: Person List Panel

**User Story:** As a researcher, I want a filterable list of all persons in the left panel, so that I can quickly find and select individuals.

#### Acceptance Criteria

1. THE Person_List_Panel SHALL display a list of all persons in the project, showing for each person their first name entry (given name and surname) from the person's names list, along with birth year and death year where available
2. THE Person_List_Panel SHALL display the list sorted alphabetically by surname, then by given name
3. THE Person_List_Panel SHALL support filtering by a text field that performs case-insensitive substring matching against person names, and by optional birth year, death year, and parish fields that filter by exact match on year values and parish place name respectively
4. WHEN the user types in a filter field, THE Person_List_Panel SHALL update the displayed list within 200 milliseconds to show only persons matching all active filter criteria
5. IF no persons match the active filter criteria, THEN THE Person_List_Panel SHALL display a message indicating that no persons matched the filter
6. WHEN the user clicks a person in the Person_List_Panel, THE Släktbusken SHALL set that person as the active person in the Diagram_Panel
7. WHEN the user double-clicks a person in the Person_List_Panel, THE Släktbusken SHALL open the Edit_Window for that person

### Requirement 17: Diagram Panel - Family View

**User Story:** As a researcher, I want a family view showing a person with their parents, siblings, partners, and children, so that I can see immediate family context.

#### Acceptance Criteria

1. WHEN the Family View is active, THE Diagram_Panel SHALL display the active person with their parents, siblings, all partner(s) from each Family the active person belongs to as a partner, and the children of each such Family
2. THE Diagram_Panel SHALL render the Family View as a zoomable diagram supporting zoom levels from 25% to 400%
3. WHEN the active person has no registered mother, THE Diagram_Panel SHALL display a placeholder box in the mother position allowing the user to add a mother
4. WHEN the active person has no registered father, THE Diagram_Panel SHALL display a placeholder box in the father position allowing the user to add a father
5. THE Diagram_Panel SHALL display a placeholder box in the children area of each Family the active person belongs to as a partner, allowing the user to add a new child to that specific Family
6. WHEN the user clicks a placeholder box, THE Släktbusken SHALL open a dialog to create a new person or link an existing person in that role
7. WHEN the user clicks a person in the Family View diagram, THE Diagram_Panel SHALL visually indicate that person as selected
8. WHEN a person is selected in the Family View diagram and the user presses the 'A' key, THE Släktbusken SHALL set that person as the active person and refresh the Family View around them
9. WHEN the user double-clicks a person in the Family View diagram, THE Släktbusken SHALL open the Edit_Window for that person
10. THE Släktbusken SHALL allow the user to print the Family View diagram

### Requirement 18: Diagram Panel - Ancestry View

**User Story:** As a researcher, I want an ancestry view showing ancestors to a configurable depth, so that I can explore the lineage of a person.

#### Acceptance Criteria

1. WHEN the Ancestry View is active, THE Diagram_Panel SHALL display ancestors of the active person up to the configured depth (parents, grandparents, etc.)
2. THE Diagram_Panel SHALL allow the user to configure the number of ancestor generations displayed between 1 and 10, with a default of 4 generations
3. THE Diagram_Panel SHALL render the Ancestry View as a zoomable diagram supporting zoom levels from 25% to 400%
4. WHEN an ancestor at an intermediate level has a missing parent, THE Diagram_Panel SHALL display an empty placeholder in that position and continue rendering any known ancestors at deeper levels
5. WHEN the user clicks a person in the Ancestry View diagram, THE Diagram_Panel SHALL visually indicate that person as selected
6. WHEN a person is selected in the Ancestry View diagram and the user presses the 'A' key, THE Släktbusken SHALL set that person as the active person and refresh the Ancestry View around them
7. WHEN the user double-clicks a person in the Ancestry View diagram, THE Släktbusken SHALL open the Edit_Window for that person
8. THE Släktbusken SHALL allow the user to print the Ancestry View diagram

### Requirement 19: Diagram Panel - Descendants View

**User Story:** As a researcher, I want a descendants view showing descendants to a configurable depth, so that I can explore the offspring of a person.

#### Acceptance Criteria

1. WHEN the Descendants View is active, THE Diagram_Panel SHALL display descendants of the active person up to the configured depth (children, grandchildren, etc.)
2. THE Diagram_Panel SHALL allow the user to configure the number of descendant generations displayed between 1 and 10, with a default of 4 generations
3. THE Diagram_Panel SHALL render the Descendants View as a zoomable diagram supporting zoom levels from 25% to 400%
4. IF the active person has no descendants, THEN THE Diagram_Panel SHALL display a message indicating that no descendants were found
5. WHEN the user clicks a person in the Descendants View diagram, THE Diagram_Panel SHALL visually indicate that person as selected
6. WHEN a person is selected in the Descendants View diagram and the user presses the 'A' key, THE Släktbusken SHALL set that person as the active person and refresh the Descendants View around them
7. WHEN the user double-clicks a person in the Descendants View diagram, THE Släktbusken SHALL open the Edit_Window for that person
8. THE Släktbusken SHALL allow the user to print the Descendants View diagram

### Requirement 20: Configurable Person Box Content

**User Story:** As a researcher, I want to configure what information is shown in person boxes in diagrams, so that I can focus on relevant details.

#### Acceptance Criteria

1. THE Släktbusken SHALL provide a person box configuration interface where the user can independently enable or disable each of the following content fields: name, birth date, death date, birth place, death place, occupation, age at death, cause of death, profile photo, DNA cluster memberships, and DNA match indicators with company logos
2. WHEN a new project is created, THE Släktbusken SHALL enable name, birth date, and death date as the default person box content fields
3. WHEN the user changes the person box configuration, THE Diagram_Panel SHALL re-render all visible person boxes in the active diagram view (Family View, Ancestry View, or Descendants View) with the updated content selection within 2 seconds
4. IF a content field is enabled but the person has no data for that field, THEN THE Diagram_Panel SHALL omit that field from the person box without displaying a placeholder or error
5. THE Släktbusken SHALL persist the person box configuration in the project settings file so that the configuration is restored when the project is reopened

### Requirement 21: Swedish Language Interface

**User Story:** As a Swedish-speaking researcher, I want the entire application interface in Swedish, so that I can work in my native language.

#### Acceptance Criteria

1. THE Släktbusken SHALL display all user interface elements (menus, buttons, labels, dialogs, tooltips, and error messages) in Swedish, excluding user-entered content such as names, notes, and free-text fields
2. THE Släktbusken SHALL display all system-generated messages and notifications in Swedish, including confirmation prompts, progress indicators, and validation feedback
3. THE Släktbusken SHALL use Swedish genealogical terminology for source types (e.g., "husförhörslängd", "födelsebok", "vigselbok"), place types (e.g., "församling", "socken", "kyrkogård"), event types (e.g., "dop", "begravning", "vigsel"), and relationship labels (e.g., "far", "mor", "make", "maka")
4. THE Släktbusken SHALL format displayed dates according to Swedish convention (YYYY-MM-DD) and format displayed numbers using comma as decimal separator and space as thousands separator

### Requirement 22: Testing with Pytest

**User Story:** As a developer, I want all application logic covered by pytest tests, so that I can verify correctness and prevent regressions.

#### Acceptance Criteria

1. THE Släktbusken SHALL have its test suite implemented using the pytest framework
2. THE Släktbusken SHALL include tests for data model serialization and deserialization verifying that a round-trip (load → save → load) produces byte-identical JSON content before gzip compression
3. THE Släktbusken SHALL include tests for GEDCOM import verifying that all imported persons, families, events, sources, and places are present in the resulting App_JSON with correct field mappings
4. THE Släktbusken SHALL include tests for GEDCOM export verifying that the output file is parseable as valid GEDCOM 5.5.1 and contains the expected number of INDI, FAM, and SOUR records
5. THE Släktbusken SHALL include tests for the Relationship_Calculator verifying correct path computation for known relationship scenarios (parent-child, sibling, uncle/aunt, cousin, in-law)
6. THE Släktbusken SHALL include tests for error-handling paths including corrupted files, invalid GEDCOM input, and missing references

### Requirement 23: Repositories Support

**User Story:** As a researcher, I want to reference external repositories (archives, libraries) from my sources, so that I can document where original records are held.

#### Acceptance Criteria

1. THE App_JSON SHALL store Repository records within the top-level "repositories" section, with fields for: unique ID, name, type (archive, digital_archive, library, museum, other), address (optional), phone (list), email (list), web (list of URLs), notes, and external_ids (list)
2. WHEN a Source references a Repository, THE Source record SHALL contain a repository_refs list where each entry includes repository_id, call_number, source_type, and optional fields (image_number, page_number, media_type, media_name, notes)
3. THE Släktbusken SHALL provide a repository list editor for viewing, adding, and editing repository records
4. IF the user attempts to delete a repository that is referenced by one or more sources, THEN THE Släktbusken SHALL display a warning listing the referencing sources and require confirmation before deletion

### Requirement 24: Stable Entity Identifiers

**User Story:** As a researcher, I want stable identifiers for all entities, so that GEDCOM exports remain consistent and references between entities remain intact.

#### Acceptance Criteria

1. THE Släktbusken SHALL assign a globally unique ID to each entity (persons, families, events, places, sources, media, DNA records) at creation time, using a type-specific prefix followed by an unpadded integer suffix with no digit limit (e.g., "person_1", "family_42", "event_3001") such that no two entities share the same ID regardless of entity type
2. THE Släktbusken SHALL never reassign or modify an entity's ID after initial creation, preserving IDs unchanged across save/load cycles and all application operations
3. IF an entity is deleted, THEN THE Släktbusken SHALL not reuse that entity's ID for any newly created entity
4. WHEN the GEDCOM_Exporter generates GEDCOM IDs, THE GEDCOM_Exporter SHALL derive them deterministically from the App_JSON entity IDs, so that exporting the same App_JSON data produces identical GEDCOM IDs and identical GEDCOM output

### Requirement 25: Future Web App Compatibility

**User Story:** As a developer, I want the desktop application's data design to support a future read-only web application, so that no redesign is needed when the web app is developed.

#### Acceptance Criteria

1. THE App_JSON format SHALL use a self-contained structure where all entity references (person_id, family_id, event_id, place_id, source_id, media_id) resolve to entities within the same file, requiring no external data source or running application to interpret the data
2. THE App_JSON format SHALL store all media file paths as relative paths from the Project_Folder root using forward-slash separators regardless of the host operating system
3. THE Släktbusken SHALL NOT store UI state (window geometry, panel sizes, zoom levels, sort orders, selection state, active person, diagram configuration, or theme preferences) within the App_JSON file, keeping all such data in the separate project settings file
4. THE Project_Folder structure SHALL use only relative internal references, enabling the folder to be served from any location accessible to a web application via a configurable base path

### Requirement 26: Application Base Structure

**User Story:** As a developer, I want a well-organized Python application folder structure, so that the codebase is maintainable and extensible.

#### Acceptance Criteria

1. THE Släktbusken source code SHALL be organized as a Python package containing an `__init__.py` file at the package root, with separate sub-modules or sub-packages for: data model, GEDCOM import/export, UI views, relationship calculation, DNA management, and file persistence
2. THE Släktbusken SHALL include a pyproject.toml specifying at minimum PySide6 and pytest as dependencies with pinned or minimum version constraints
3. THE Släktbusken SHALL include a test directory with test modules named using the `test_*.py` convention, organized to mirror the source module structure so that each source module has a corresponding test module discoverable by pytest without additional configuration
4. THE Släktbusken SHALL provide an entry point that allows launching the application via `python -m <package_name>` using a `__main__.py` module in the package root

### Requirement 27: Data Format Versioning and Migration

**User Story:** As a researcher, I want the application to handle format upgrades transparently when I open a project saved with an older version, so that I never lose data or have to manually convert files.

#### Acceptance Criteria

1. THE App_JSON SHALL place the format_version field as the first key in the top-level JSON object, so that it can be read without fully parsing the remainder of the file
2. WHEN the user opens a project file, THE Släktbusken SHALL read the format_version before full deserialization and compare it to the application's current format version
3. IF the file's format_version is older than the application's current format version, THEN THE Släktbusken SHALL apply sequential migration steps (from the file's version to the current version) to transform the data to the current schema before loading it into the data model
4. WHEN a migration is applied, THE Släktbusken SHALL create a backup copy of the original file (appending the old version number to the filename, e.g., "project_v0.1.json.gz") before overwriting the file with the migrated data
5. IF the file's format_version is newer than the application's current format version, THEN THE Släktbusken SHALL display a Swedish-language error message indicating that the file was created with a newer version of Släktbusken and cannot be opened, and shall not modify the file
6. THE Släktbusken SHALL maintain a migration registry mapping each historical format version to a migration function that transforms data from that version to the next version, enabling chained upgrades (e.g., 0.1 → 0.2 → 0.3)
7. WHEN saving a project, THE Släktbusken SHALL always write the current application format version as the format_version in the output file
