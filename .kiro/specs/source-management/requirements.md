# Requirements Document

## Introduction

This feature extends the source management capabilities in Släktbusken, a Swedish genealogy application built with PySide6. It introduces a structured Leverantör (Provider) and Källtyp (Source Type) management system, improves the source creation and editing workflow, enhances the source list with usage statistics, adds comprehensive reference format parsing for common Swedish genealogy archives, and enables detailed event-source linking with aspect tracking.

## Glossary

- **Leverantör**: A source provider (e.g., Arkiv Digital, Rötter.se) that offers genealogical records
- **Källtyp**: A source type category belonging to a specific Leverantör (e.g., Husförhörslängd, Folkräkning)
- **Source_Editor**: The existing source editor widget that displays and edits Source records
- **Provider_Editor**: The new editor dialog for managing Leverantörer and their Källtyper
- **Reference_Parser**: The module responsible for parsing pasted or imported reference strings into structured source data
- **Source_List**: The list panel in the Source_Editor showing all sources in the project
- **Event_Editor**: The existing event editor dialog for editing event details and source links
- **Arkivreferens**: An archive reference identifier linking to a specific record in a provider's system
- **Root_URL**: A base URL for a Källtyp that, combined with an Arkivreferens, forms a clickable link to the online record
- **Project_Data**: The central data model containing all persons, events, sources, and families

## Requirements

### Requirement 1: Leverantör CRUD Operations

**User Story:** As a genealogist, I want to manage a list of source providers (Leverantörer), so that I can categorize my sources by their origin.

#### Acceptance Criteria

1. WHEN the user selects "Käll-leverantörer" from the Redigera menu, THE Provider_Editor SHALL open a dialog displaying all Leverantörer in a list with buttons "Lägg till", "Ta bort", and "Redigera"
2. WHEN the user confirms the input by any means, THE Provider_Editor SHALL validate that the name field is not empty or whitespace-only, and create a new Leverantör with the provided name (maximum 100 characters) and comment (maximum 500 characters)
3. IF the user confirms the input and the name field is empty or contains only whitespace, THEN THE Provider_Editor SHALL keep the input visible and indicate that the name field is required
4. WHEN the user clicks "Redigera" with a Leverantör selected, THE Provider_Editor SHALL allow modification of the name and comment fields, applying the same validation as for creation
5. IF the user clicks "Ta bort" or "Redigera" with no Leverantör selected, THEN THE Provider_Editor SHALL keep the buttons disabled or take no action
6. WHILE a Leverantör is referenced by one or more Sources, THE Provider_Editor SHALL continuously disable the "Ta bort" button for that Leverantör and display a message indicating the Leverantör is in use
7. WHEN the user clicks "Ta bort" with a Leverantör selected that is not referenced by any Source, THE Provider_Editor SHALL proceed with deletion checks for associated Källtyper
8. IF no Sources reference the selected Leverantör and the Leverantör has associated Källtyper, THEN THE Provider_Editor SHALL display a confirmation prompt indicating that associated Källtyper will also be removed, and upon user confirmation delete the Leverantör and all its associated Källtyper
9. IF no Sources reference the selected Leverantör and the Leverantör has no associated Källtyper, THEN THE Provider_Editor SHALL delete the Leverantör immediately

### Requirement 2: Källtyp CRUD Operations

**User Story:** As a genealogist, I want to manage source types (Källtyper) for each provider, so that I can classify sources by their record type within a provider.

#### Acceptance Criteria

1. WHEN a Leverantör is selected in the Provider_Editor, THE Provider_Editor SHALL display the Källtyper belonging to that Leverantör in a sub-list below the Leverantör list
2. WHEN the user clicks "Lägg till" for Källtyper, THE Provider_Editor SHALL display input fields for name (required, 1 to 100 characters), comment (optional, up to 500 characters), and Root_URL (optional, up to 2048 characters), and create a new Källtyp associated with the selected Leverantör upon the user confirming the input
3. IF the user cancels the add or edit operation for a Källtyp, THEN THE Provider_Editor SHALL discard any unsaved input and return to the Källtyp sub-list without modifying data
4. WHEN the user clicks "Redigera" for a Källtyp, THE Provider_Editor SHALL allow modification of the name, comment, and Root_URL fields with the same validation constraints as creation
5. WHILE a Källtyp is referenced by one or more Sources, THE Provider_Editor SHALL continuously disable the "Ta bort" button for that Källtyp and display a message indicating the Källtyp is in use
6. WHEN the user clicks "Ta bort" for a Källtyp that is not referenced by any Source, THE Provider_Editor SHALL delete the Källtyp and remove it from the sub-list
7. IF the user attempts to create or rename a Källtyp with a name that already exists within the same Leverantör, THEN THE Provider_Editor SHALL prevent the operation and display a message indicating the name is already in use

### Requirement 3: Standard Leverantörer Initialization

**User Story:** As a genealogist, I want a predefined set of providers and source types available by default, so that I can start categorizing sources immediately without manual setup.

#### Acceptance Criteria

1. WHEN a new project is created, THE Project_Data SHALL include the following standard Leverantörer in this order: "Arkiv Digital", "Nationell arkivdatabas", "Rötter.se", "Skatteverket", "Övrigt"
2. WHEN a new project is created, THE Project_Data SHALL include the following Källtyper for "Arkiv Digital" in this order: Husförhörslängd, Församlingsbok, Mantalslängd, Folkräkning, Inflyttningslängd, Utflyttningslängd, In- och Utflyttningslängd, Födelse- och dopbok, Lysnings- och vigselbok, Död- och begravningsbok, Generalmönstringsrullor, Bouppteckningar, Konfirmationsbok, Övrigt
3. WHEN a new project is created, THE Project_Data SHALL include the same Källtyper in the same order for "Nationell arkivdatabas" as for "Arkiv Digital"
4. WHEN a new project is created, THE Project_Data SHALL include the following Källtyper for "Rötter.se" in this order: Sveriges Dödbok Webb (Root_URL: "https://www.rotter.se/abonnemang/sveriges-dodbok-webb/post/"), Sveriges Dödbok (sticka/dvd), Övrigt
5. WHEN a new project is created, THE Project_Data SHALL include the following Källtyper for "Skatteverket" in this order: Personbild (6401), Övrigt
6. WHEN a new project is created, THE Project_Data SHALL include the following Källtyper for "Övrigt" in this order: Dödsannons, Tidningsartikel, Övrig databas, Övrigt
7. WHEN a new project is created, THE Project_Data SHALL treat the standard Leverantörer and Källtyper as user-editable entries subject to the same CRUD rules defined in Requirements 1 and 2
8. IF an existing project is opened, THEN THE Project_Data SHALL NOT re-initialize or overwrite existing Leverantörer and Källtyper with the standard set

### Requirement 4: Source Creation Media Attachment

**User Story:** As a genealogist, I want to attach media files to a source, so that I can link scanned documents or images directly to the source record.

#### Acceptance Criteria

1. WHEN the user clicks "Lägg till media" in the Source_Editor, THE Source_Editor SHALL open a file chooser dialog filtered to image file types (.jpg, .jpeg, .png, .tif, .tiff, .bmp, .gif, .webp) and document file types (.pdf, .docx, .rtf, .odt)
2. IF the user cancels the file chooser dialog, THEN THE Source_Editor SHALL take no action and return to the previous state
3. WHEN the user selects a file, THE Source_Editor SHALL copy the file to the project folder media directory, resolving filename conflicts by appending a numeric suffix (_1, _2, etc.) before the extension
4. IF the file copy operation fails, THEN THE Source_Editor SHALL display an error message indicating the failure reason and SHALL NOT create a media record
5. WHEN the file is copied successfully, THE Source_Editor SHALL create a media record with type "photo" for image files or type "document" for document files (.pdf, .docx, .rtf, .odt), the copied file path relative to the media directory, and a title derived from the source title, and SHALL append the media ID to the source's media_ids list

### Requirement 5: Source Title Format from Search

**User Story:** As a genealogist, I want sources created from archive searches to include the page number in the title, so that I can distinguish between different pages in the same volume.

#### Acceptance Criteria

1. WHEN a source is created from a search result that contains parish, series, volume, and page fields in its structured_reference, THE Source_Editor SHALL format the title as "{parish} {series}:{volume} Sida: {page}" (e.g., "Ljusdal AI:17 Sida: 32")
2. WHEN a source is created from a search result where the page field is absent or empty in the structured_reference, THE Source_Editor SHALL format the title as "{parish} {series}:{volume}"
3. IF a source is created from a search result where the parish, series, or volume field is absent or empty in the structured_reference, THEN THE Source_Editor SHALL omit the missing segment and any associated separator from the title while preserving the remaining segments in order
4. WHEN the Source_Editor formats a title from a search result, THE Source_Editor SHALL trim leading and trailing whitespace and collapse multiple consecutive spaces into a single space in the resulting title

### Requirement 6: Source List Usage Statistics

**User Story:** As a genealogist, I want to see how many persons and events reference each source, so that I can assess source importance and identify unused sources.

#### Acceptance Criteria

1. THE Source_List SHALL display, for each source in the list, a person count and an event count derived from all events whose date.source_refs or place.source_refs contain the source ID, where the person count is the number of distinct participants across those events, and the event count is the total number of matching events
2. THE Source_List SHALL display both usage counts inline with each source list item so that they are visible without horizontal scrolling at the default panel width
3. WHEN a source has zero referencing events, THE Source_List SHALL display "0" for both person and event counts so that the user can identify unused sources
4. WHEN the user clicks the usage count or a dedicated detail button for a source, THE Source_List SHALL open a dialog listing all distinct persons referencing the source, identified by display name, with each person's referencing events shown grouped beneath that person's name

### Requirement 7: Arkiv Digital Reference Parsing

**User Story:** As a genealogist, I want pasted Arkiv Digital reference strings to be automatically parsed into structured source fields, so that I can quickly register sources from clipboard data.

#### Acceptance Criteria

1. WHEN a reference string matching the pattern "{parish} ({county_code}) {series}:{volume} ({years}) Bild {image} / sid {page} (AID: {aid_ref}, NAD: {nad_ref})" is pasted, THE Reference_Parser SHALL create a source with Leverantör "Arkiv Digital", Källtyp derived from the series code using the CHURCH_BOOK_SERIES_LABELS mapping (or "Övrigt" if series is unrecognized), title formatted as "{parish} {series}:{volume} Sida: {page}", Referenstext set to the full pasted string, and store both AID and NAD values in the structured_reference fields as "aid_ref" and "nad_ref"
2. WHEN a reference string matching the pattern "{description} ({year}) Bild {image} / sid {page} (AID: {aid_ref})" without NAD is pasted, THE Reference_Parser SHALL create a source with Leverantör "Arkiv Digital", title formatted as "{description} Sida: {page}", Referenstext set to the full pasted string, and store the AID value in the structured_reference fields as "aid_ref"
3. WHEN a reference string matching the pattern "rX.pXXXXX" (where X is one or more digits) is pasted, THE Reference_Parser SHALL create a source with Leverantör "Arkiv Digital", Källtyp "Folkräkning", title set to the pasted string, and store the rX.pXXXXX string in the structured_reference fields as "aid_ref"
4. WHEN an Arkiv Digital GEDCOM import is performed containing a source with an "ArkivDigital:" prefix or ArkivDigital metadata, THE Reference_Parser SHALL populate Title and Referenstext by stripping the "ArkivDigital:" prefix and applying the same pattern-matching and field-extraction logic as criteria 1 and 2
5. IF a pasted string does not match any of the Arkiv Digital reference patterns defined in criteria 1, 2, or 3, THEN THE Reference_Parser SHALL not create a source and SHALL leave the clipboard content unmodified

### Requirement 8: Rötter.se Reference Parsing

**User Story:** As a genealogist, I want pasted Rötter.se reference strings to be automatically parsed, so that I can register Sveriges Dödbok sources efficiently.

#### Acceptance Criteria

1. WHEN a reference string containing "Sveriges dödbok webb" (case-insensitive) is pasted into the reference input field, THE Reference_Parser SHALL create a source with Leverantör "Rötter.se" and Källtyp "Sveriges Dödbok Webb"
2. WHEN a reference string matching "Sveriges dödbok webb - {record_id}" (case-insensitive) is pasted, THE Reference_Parser SHALL store the record_id portion (all characters after the " - " separator, trimmed of leading and trailing whitespace) as Arkivreferens
3. WHEN a reference string matching the pattern "SDB" followed by a version digit and an underscore and one or more digits (e.g., "SDB7_12345") is pasted, THE Reference_Parser SHALL create a source with Leverantör "Rötter.se", Källtyp "Sveriges Dödbok Webb", and store the full matched identifier as Arkivreferens
4. WHEN a Sveriges Dödbok reference string contains multiple person entries separated by newline characters, THE Reference_Parser SHALL create a separate source entry for each line that contains a valid Sveriges Dödbok reference
5. IF a pasted reference string does not match any recognized Rötter.se pattern, THEN THE Reference_Parser SHALL not create a source and SHALL leave the input unchanged for manual handling

### Requirement 9: Event Source Aspect Linking

**User Story:** As a genealogist, I want to specify which aspects of an event a source supports, so that I can track exactly what each source proves.

#### Acceptance Criteria

1. WHEN a source is linked to an event in the Event_Editor, THE Event_Editor SHALL display a set of checkboxes representing the aspects relevant to the event type: for birth events the aspects are date, place, parents, and witnesses; for death events the aspects are date, place, and cause of death; for marriage events the aspects are date, place, and spouse; for all other event types the aspects are date and place
2. WHEN a source is first linked to an event, THE Event_Editor SHALL display all aspect checkboxes in an unselected state
3. WHEN the user saves the event, THE Event_Editor SHALL persist the selected aspects with the corresponding source reference, and SHALL allow saving with no aspects selected
4. WHEN the user selects a linked source in the sources table, THE Event_Editor SHALL display a button labeled "Öppna källa" that opens the Source_Editor with the linked source pre-selected

### Requirement 10: Source Direct Link Generation

**User Story:** As a genealogist, I want to open the online record directly from the source view, so that I can quickly verify or review the original document.

#### Acceptance Criteria

1. WHILE a source has a Källtyp with a defined Root_URL and a stored Arkivreferens for that Källtyp's Leverantör, THE Source_Editor SHALL display a clickable link for each matching Arkivreferens, composed of Root_URL concatenated with the Arkivreferens value, showing the full URL as the link text; IF the link generation or display fails due to a technical issue, THEN THE Source_Editor SHALL show an error indicator or placeholder where the link would appear
2. WHEN the user clicks the generated link, THE Source_Editor SHALL open the URL in the system default web browser
3. IF a source has no Källtyp assigned, or the assigned Källtyp has no Root_URL defined, or the source has no stored Arkivreferens, THEN THE Source_Editor SHALL not display any direct link for that source

### Requirement 11: Menu Integration

**User Story:** As a genealogist, I want the provider editor accessible from the Redigera menu, so that I can manage providers alongside other editing functions.

#### Acceptance Criteria

1. THE Main_Window SHALL display a menu item "Käll-leverantörer" in the Redigera menu, positioned immediately after "Källöversättningar", and the menu item SHALL be enabled by default unless explicitly disabled by other criteria
2. WHEN the user selects "Käll-leverantörer", THE Main_Window SHALL open the Provider_Editor as a modal dialog
3. IF no project is currently open, THEN THE Main_Window SHALL disable the "Käll-leverantörer" menu item; WHEN a project is opened, THE Main_Window SHALL enable the "Käll-leverantörer" menu item
