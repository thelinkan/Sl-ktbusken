# Requirements Document

## Introduction

Denna feature utökar vyn "Redigera Person" i Släktbusken med stöd för hantering av föräldrarelationer (biologiska, foster-, adoptiv- och donationsföräldrar), koppling av namnändringar till händelser, en dedikerad fototab med typkategorisering och personlista, samt möjlighet att lägga till händelsespecifik media (dödsrelaterade och begravningsrelaterade dokument). Designen ska förbereda för framtida bildannotering (klick-till-tagg med koordinater) utan att implementera den funktionaliteten nu.

## Glossary

- **Person_Editor**: Dialogrutan (`PersonEditor`) för att redigera en persons uppgifter, öppnad från diagrammet eller personlistan.
- **Foto_Tab**: En flik i Person_Editor dedikerad till hantering av personfoton och relaterad metadata.
- **Foto_Mapp**: Den konfigurerade projektmappen för fotofiler, belägen i projektmappens undermapp `media/photos`.
- **Foto_Typ**: En kategorisering av ett foto, en av: Porträtt, Gruppfoto, Familjefoto, Bröllopsfoto, Konfirmationsfoto, Dopfoto, Skolfoto, Militärfoto, Arbetsfoto, Begravningsfoto, Gravfoto, Övrigt foto.
- **MediaItem**: Datamodellen (`MediaItem`) som representerar en mediafil med typ, sökväg, titel och länkade entiteter.
- **Linked_Entity**: En koppling från en MediaItem till en annan entitet (person, händelse, källa, plats).
- **Mentioned_Person**: En person som syns i ett foto, antingen kopplad via person-ID eller som fritext-namn.
- **ParentChildLink**: Datamodellen (`ParentChildLink`) som beskriver relationstypen mellan ett barn och en förälder (biologisk, foster, adoptiv, donation).
- **Family**: Datamodellen (`Family`) som grupperar partners och barn, med tillhörande ParentChildLink-poster.
- **Event**: Datamodellen (`Event`) som representerar en händelse med typ, deltagare, datum och plats.
- **Händelse_Media**: Media kopplad till en specifik händelse via händelsens `media_ids`-fält.
- **Annotation_Metadata**: Ett framtida tillägg till MediaItem som ska stödja koordinatbaserad bildannotering (inte implementerat i denna feature).

## Requirements

### Requirement 1: Hantera föräldrarelationer för befintliga personer

**User Story:** Som släktforskare vill jag kunna ändra och lägga till biologiska föräldrar samt foster-, adoptiv- och donationsföräldrar för en befintlig person, så att jag korrekt kan registrera komplexa familjeförhållanden.

#### Acceptance Criteria

1. THE Person_Editor SHALL provide a parent relationship section that displays all current parent relationships for the person being edited, showing each parent's name and parentage type.
2. WHEN the user adds a parent relationship, THE Person_Editor SHALL allow selection of an existing person from the project as the parent via a searchable dropdown.
3. WHEN the user adds a parent relationship, THE Person_Editor SHALL allow selection of parentage type from the values: biological, foster, adoptive, donation.
4. WHEN the user saves a new parent relationship, THE Person_Editor SHALL create a ParentChildLink record with the selected parent_id, the edited person's id as child_id, and the chosen parentage_type.
5. WHEN the user saves a new parent relationship and no Family exists containing the edited person as a child with the selected parent as a partner, THE Person_Editor SHALL create a new Family with the parent as partner and the edited person as child, and add the ParentChildLink to that Family.
6. WHEN the user saves a new parent relationship and a Family already exists containing the edited person as a child, THE Person_Editor SHALL add the parent as a partner to that existing Family and add the ParentChildLink to the Family's parent_child_links list. If multiple such Families exist, the system SHALL use the Family whose parentage_type matches the new link.
7. WHEN the user changes the parentage type of an existing parent relationship, THE Person_Editor SHALL update the corresponding ParentChildLink record's parentage_type field.
8. WHEN the user removes a parent relationship, THE Person_Editor SHALL remove the corresponding ParentChildLink record from the Family.
9. THE Person_Editor SHALL allow a person to have a maximum of two parents per parentage type (one father-role and one mother-role), where role is determined by the parent person's sex field. IF the user attempts to add a third parent of the same parentage type, THEN THE Person_Editor SHALL display a validation error and prevent saving.
10. THE Person_Editor SHALL display the parentage type in Swedish: biologisk, fosterförälder, adoptivförälder, donationsförälder.
11. IF the user attempts to add a parent who is already linked to the person with the same parentage type, THEN THE Person_Editor SHALL reject the addition and display a message indicating that the parent relationship already exists.

### Requirement 2: Koppling av namnändring till händelse

**User Story:** Som släktforskare vill jag kunna koppla en namnändring till en händelse (t.ex. vigsel eller namnbyte), så att jag kan spåra varför och när en person bytte namn.

#### Acceptance Criteria

1. WHEN the user adds or edits a Name record of type other than "birth", THE Person_Editor SHALL allow selection of an existing Event linked to the person to associate with the name change.
2. WHEN the user associates a Name record with an Event, THE Person_Editor SHALL store the Event's id in the Name record's event_id field, replacing any previously stored event_id value.
3. WHEN the user views the names table, THE Person_Editor SHALL display the linked event's type and date value alongside each Name record that has an event_id set, or display an indication that the linked event is missing if the event_id references a non-existent Event.
4. WHEN the user clears the event association from a Name record, THE Person_Editor SHALL set the Name record's event_id to None.
5. THE Person_Editor SHALL only offer events where the edited person is listed as a participant for linking to a name change.
6. IF no events exist where the edited person is a participant, THEN THE Person_Editor SHALL disable the event association control and display an informational message indicating that no events are available.
7. IF a Name record's event_id references an Event that no longer exists in the project, THEN THE Person_Editor SHALL display the Name record without event details and allow the user to clear or replace the orphaned event association.

### Requirement 3: Foto-tab med typkategorisering

**User Story:** Som släktforskare vill jag ha en dedikerad flik för att hantera foton av en person med möjlighet att välja fototyp, så att jag kan organisera bildmaterialet efter kategori.

#### Acceptance Criteria

1. THE Person_Editor SHALL display a dedicated Foto_Tab for managing photos of the person being edited, visible regardless of whether the person currently has linked photos.
2. THE Foto_Tab SHALL display a list of all MediaItem records of type "photo" that are linked to the person via a Linked_Entity with entity_type "person" and entity_id matching the person's id, ordered by title alphabetically.
3. WHEN the user adds a new photo, THE Foto_Tab SHALL require selection of Foto_Typ from the values: Porträtt, Gruppfoto, Familjefoto, Bröllopsfoto, Konfirmationsfoto, Dopfoto, Skolfoto, Militärfoto, Arbetsfoto, Begravningsfoto, Gravfoto, Övrigt foto, with "Övrigt foto" as the default selection.
4. WHEN the user adds a new photo, THE Foto_Tab SHALL store the selected Foto_Typ as a sub-type classification in the MediaItem's title field prefix using the format "[Foto_Typ] title", where title is the user-provided title (1 to 200 characters).
5. THE Foto_Tab SHALL display each photo's Foto_Typ as a visible label alongside the photo title (without the bracket prefix) in the list.
6. WHEN the user edits a photo's metadata, THE Foto_Tab SHALL allow changing the Foto_Typ and title, and update the MediaItem's title field to reflect the new "[Foto_Typ] title" format upon save.
7. IF the person has no linked photos, THEN THE Foto_Tab SHALL display an empty state message indicating that no photos are linked and providing the option to add a photo.
8. WHEN the user adds a new photo, THE Foto_Tab SHALL only accept image files with extensions: .jpg, .jpeg, .png, .tif, .tiff, .bmp, .gif, .webp.
9. IF the user attempts to add a file with an unsupported extension, THEN THE Foto_Tab SHALL reject the file and display an error message indicating the accepted file formats.

### Requirement 4: Filhantering för foton

**User Story:** Som släktforskare vill jag att foton som läggs till från annan plats än fotomappen automatiskt kopieras dit, så att projektets mediafiler förblir samlade.

#### Acceptance Criteria

1. WHEN the user selects a photo file located outside the Foto_Mapp, THE Foto_Tab SHALL copy the file to the Foto_Mapp and store the relative path within Foto_Mapp in the MediaItem's file field.
2. WHEN the user selects a photo file already located within the Foto_Mapp, THE Foto_Tab SHALL store the relative path directly without copying.
3. IF a file with the same name already exists in Foto_Mapp when copying, THEN THE Foto_Tab SHALL display a confirmation dialog asking the user whether to overwrite the existing file, rename the new file with a numeric suffix, or cancel the operation.
4. WHEN the user chooses to overwrite in the file conflict dialog, THE Foto_Tab SHALL replace the existing file with the new file and store the same relative path in the MediaItem's file field.
5. WHEN the user chooses to rename in the file conflict dialog, THE Foto_Tab SHALL append a numeric suffix (e.g., "_1", "_2") to the filename before the extension, incrementing until a unique name is found.
6. WHEN the user chooses to cancel in the file conflict dialog, THE Foto_Tab SHALL abort the photo addition without modifying any files or data.
7. THE Foto_Tab SHALL create the Foto_Mapp directory if it does not exist when the first photo is added to the project.
8. IF the file copy operation fails due to an I/O error (e.g., insufficient disk space, permission denied), THEN THE Foto_Tab SHALL display an error message describing the failure and SHALL NOT create a MediaItem record.

### Requirement 5: Personlista på foton

**User Story:** Som släktforskare vill jag kunna ange vilka personer som syns på ett foto, inklusive personer som inte finns i databasen, så att jag kan dokumentera vilka som är med på bilden.

#### Acceptance Criteria

1. THE Foto_Tab SHALL display a list of all persons present in the selected photo, showing each linked person's name in the format "given surname" (from the first entry in the person's names list) and displaying plain text for non-database persons.
2. WHEN the user adds a person present in the photo who exists in the database, THE Foto_Tab SHALL add the person's id to the MediaItem's mentioned_person_ids list, provided that person_id is not already present in the list.
3. WHEN the user adds a person present in the photo who does not exist in the database, THE Foto_Tab SHALL allow entering the person's name as free text (maximum 200 characters) and store it in a mentioned_names list field (list of strings) on the MediaItem.
4. WHEN the user removes a person from the photo's person list, THE Foto_Tab SHALL remove the corresponding entry from mentioned_person_ids or the mentioned_names list field.
5. WHEN a photo has persons in its mentioned_person_ids list, THE photo SHALL appear in each of those persons' Foto_Tab lists (linked via Linked_Entity with entity_type "person").
6. WHEN the user saves a photo with mentioned_person_ids, THE Foto_Tab SHALL ensure a Linked_Entity with entity_type "person" exists on the MediaItem for each mentioned person_id, creating any missing links and removing any Linked_Entity records for person_ids no longer in the mentioned_person_ids list.
7. THE Foto_Tab SHALL provide a searchable dropdown for selecting existing persons from the database, displaying persons by their first name entry in the format "given surname" and filtering results as the user types with at least 1 character entered.
8. IF the user attempts to add a person who is already present in the photo's person list (either by person_id or by identical free-text name), THEN THE Foto_Tab SHALL reject the addition and display a message indicating that the person is already listed on the photo.

### Requirement 6: Förberedelse för bildannotering

**User Story:** Som släktforskare vill jag att fotodatamodellen är förberedd för framtida bildannotering (klick-till-tagg med koordinater), så att denna funktion kan läggas till utan datamodellsändringar.

#### Acceptance Criteria

1. THE MediaItem data model SHALL include an optional annotations field (defaulting to an empty list) capable of storing annotation records where each record contains: x-coordinate (float, 0.0 to 1.0 representing fraction of image width), y-coordinate (float, 0.0 to 1.0 representing fraction of image height), width (float, 0.0 to 1.0), height (float, 0.0 to 1.0), and a linked entity reference consisting of an entity_type (string) and entity_id (string).
2. THE Foto_Tab SHALL not expose any user interface for creating or editing annotations in this feature version.
3. THE serialization layer SHALL persist the annotations field when present and load it back correctly such that serializing and then deserializing a MediaItem with an annotations list produces a MediaItem whose annotations list has the same number of records with identical field values.
4. WHEN a MediaItem has no annotations, THE serialization layer SHALL omit the annotations field from the serialized output.
5. THE MediaItem data model SHALL support a maximum of 100 annotation records per MediaItem.

### Requirement 7: Händelsemedia för dödshändelser

**User Story:** Som släktforskare vill jag kunna lägga till dödsrelaterade dokument (dödruna, dödsannons, bouppteckning, dödsbevis) till en dödshändelse, så att jag kan samla relevanta dokument till händelsen.

#### Acceptance Criteria

1. WHEN the user edits an Event of type "death", THE Event editor SHALL display a media section allowing addition of media items.
2. WHEN adding media to a death Event, THE Event editor SHALL offer the media type options: dödruna, dödsannons, bouppteckning, dödsbevis.
3. WHEN the user adds a media item to a death Event, THE Event editor SHALL require the user to select a file and provide a title (maximum 200 characters), create a MediaItem record with the selected type, file path, and title, add a Linked_Entity with entity_type "event" and entity_id matching the Event's id to the MediaItem's linked_entities list, and add the MediaItem's id to the Event's media_ids list.
4. WHEN the user removes a media item from a death Event, THE Event editor SHALL remove the MediaItem's id from the Event's media_ids list and remove the Linked_Entity linking the media to the Event, but SHALL NOT delete the MediaItem record itself.
5. THE Event editor SHALL display all currently linked media items for the death Event, showing each item's type and title.
6. IF the user attempts to add a media item without selecting a file or without providing a title, THEN THE Event editor SHALL disable the save action and indicate which required fields are missing.

### Requirement 8: Händelsemedia för begravningshändelser

**User Story:** Som släktforskare vill jag kunna lägga till begravningsrelaterade dokument (begravningsprogram, minnesord) till en begravningshändelse, så att jag kan samla relevanta dokument till händelsen.

#### Acceptance Criteria

1. WHEN the user edits an Event of type "funeral", THE Event editor SHALL display a media section allowing addition of media items.
2. WHEN adding media to a funeral Event, THE Event editor SHALL offer the media type options: begravningsprogram, minnesord.
3. WHEN the user adds a media item to a funeral Event, THE Event editor SHALL require the user to select a file and provide a title (maximum 200 characters), create a MediaItem record with the selected type, file path, and title, add a Linked_Entity with entity_type "event" and entity_id matching the Event's id to the MediaItem's linked_entities list, and add the MediaItem's id to the Event's media_ids list.
4. WHEN the user removes a media item from a funeral Event, THE Event editor SHALL remove the MediaItem's id from the Event's media_ids list and remove the Linked_Entity linking the media to the Event, but SHALL NOT delete the MediaItem record itself.
5. THE Event editor SHALL display all currently linked media items for the funeral Event, showing each item's type and title.
6. IF the user attempts to add a media item without selecting a file or without providing a title, THEN THE Event editor SHALL disable the save action and indicate which required fields are missing.

### Requirement 9: Redigering av fotometadata

**User Story:** Som släktforskare vill jag kunna redigera metadata för ett foto (titel, typ, personlista), så att jag kan korrigera och uppdatera information om bilden efter att den lagts till.

#### Acceptance Criteria

1. WHEN the user selects a photo in the Foto_Tab list, THE Foto_Tab SHALL display the photo's current metadata (title, Foto_Typ, mentioned persons including both database-linked persons and free-text names) in editable form fields.
2. WHEN the user changes the title of a photo and saves, THE Foto_Tab SHALL update the MediaItem's title field using the format "[Foto_Typ] new_title", preserving the current Foto_Typ prefix while replacing the title portion, and the title portion SHALL be between 1 and 200 characters.
3. WHEN the user changes the Foto_Typ of a photo and saves, THE Foto_Tab SHALL update the MediaItem's title field by replacing the existing Foto_Typ prefix with the newly selected value while preserving the title portion, using the format "[new_Foto_Typ] existing_title".
4. WHEN the user adds a person from the database to a photo's person list and saves, THE Foto_Tab SHALL add the person's id to the MediaItem's mentioned_person_ids list and create a Linked_Entity with entity_type "person" and entity_id matching that person's id on the MediaItem.
5. WHEN linked persons are removed from a photo's person list and the user saves, THE Foto_Tab SHALL remove those person ids from mentioned_person_ids and remove the corresponding Linked_Entity records with entity_type "person" from the MediaItem, so the photo no longer appears in those persons' Foto_Tab lists.
6. WHEN the user adds or removes a free-text (non-database) person from the photo's person list and saves, THE Foto_Tab SHALL update the MediaItem's mentioned_names field to reflect the change.
7. IF the title portion is empty or exceeds 200 characters when the user attempts to save, THEN THE Foto_Tab SHALL display a validation error message indicating the title length constraint and SHALL NOT persist the change.
8. IF a save operation fails due to a data persistence error, THEN THE Foto_Tab SHALL display an error message indicating the save failed and SHALL retain the user's unsaved edits in the form fields.
