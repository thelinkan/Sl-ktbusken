# Requirements Document

## Introduction

This feature adds the ability to delete a person from the Släktbusken genealogy project. Deletion is a destructive operation that cascades through the data model: events exclusive to the person are removed, shared events (like marriages) are removed, family references are cleaned up, and media is preserved. The user receives warnings before proceeding when the deletion affects shared events or would disconnect part of the family tree.

## Glossary

- **Delete_Service**: The service responsible for computing deletion consequences and executing person removal from ProjectData.
- **Person**: A person record in the project data (id, sex, names, profile_media_id, notes, title, occupation).
- **Event**: An event involving one or more participants, linked via Participant entries.
- **Family**: A grouping of partners and children, referencing persons and events.
- **Exclusive_Event**: An event where all participants reference only the person being deleted.
- **Shared_Event**: An event where participants include the person being deleted AND at least one other person.
- **Family_Event**: An event referenced by a Family's event_ids list (e.g., wedding, divorce).
- **MediaItem**: A media item (image, document, recording) that may reference persons.
- **Main_Person**: The person designated as main_person_id in ProjectMetadata.
- **Tree_Connectivity**: The property that all persons in the project are reachable from the main person via family relationships.
- **Detached_Section**: A group of persons that would become unreachable from the Main_Person after deletion.
- **Confirmation_Dialog**: A PySide6 dialog presenting warnings and requiring explicit user confirmation before proceeding.

## Requirements

### Requirement 1: Delete Person Action

**User Story:** As a user, I want to initiate deletion of a person from the project, so that I can remove incorrect or unwanted entries.

#### Acceptance Criteria

1. WHEN the user requests deletion of a Person, THE Delete_Service SHALL identify all Exclusive_Events (events where the Person is the only participant), Shared_Events (events where the Person is one of two or more participants), and Family_Events (events referenced by a Family's event_ids list where the Person is a partner in that Family).
2. WHEN the user confirms deletion, THE Delete_Service SHALL remove the Person from the ProjectData persons list, delete all Exclusive_Events from the ProjectData events list, remove the Person's Participant entry from each Shared_Event's participants list, remove the Person's person_id from all Family partners lists, children lists, and ParentChildLink entries referencing the Person, and remove the Person's profile_media_id association.
3. WHEN the user cancels deletion via the Confirmation_Dialog, THE Delete_Service SHALL make no modifications to the ProjectData and return the user to the previous view state.
4. IF the user requests deletion of the Person whose id matches ProjectData.project.main_person_id, THEN THE Delete_Service SHALL prevent the deletion and display the error message "Huvudpersonen kan inte tas bort."
5. WHEN the user confirms deletion, THE Delete_Service SHALL remove any Family from the ProjectData families list that has zero partners and zero children remaining after the Person's removal.
6. WHEN the user requests deletion of a Person, THE Delete_Service SHALL present a Confirmation_Dialog displaying the Person's primary name and the counts of Exclusive_Events to be deleted, Shared_Events to be modified, and Family associations to be updated, before proceeding with deletion.

### Requirement 2: Exclusive Event Deletion

**User Story:** As a user, I want events that only involve the deleted person to be automatically removed, so that orphaned events do not remain in the data.

#### Acceptance Criteria

1. WHEN a Person is deleted, THE Delete_Service SHALL remove all Exclusive_Events from the ProjectData events list.
2. WHEN an Exclusive_Event is removed, THE Delete_Service SHALL remove the event ID from any Family event_ids list that references the removed event.
3. THE Delete_Service SHALL identify an event as an Exclusive_Event when all entries in the event's participants list have person_id equal to the deleted Person's id.
4. IF an event has an empty participants list, THEN THE Delete_Service SHALL treat it as an Exclusive_Event and remove it during deletion.

### Requirement 3: Shared Event Deletion

**User Story:** As a user, I want shared events like marriages to be deleted when a participant is removed, so that multi-person events do not remain in an invalid state with a missing participant.

#### Acceptance Criteria

1. WHEN a Person is deleted, THE Delete_Service SHALL remove all Events from the ProjectData events list where the Person's id matches a Participant.person_id AND the Event's id appears in any Family's event_ids list.
2. WHEN an Event is removed from the ProjectData events list due to criterion 1, THE Delete_Service SHALL remove that Event's id from every Family's event_ids list that contains it.
3. WHEN a Person is deleted, THE Delete_Service SHALL remove the Participant entry matching the Person's id from every remaining Event in the ProjectData events list that has 2 or more participants including the deleted Person and whose id does not appear in any Family's event_ids list.
4. IF removing a Participant entry from an Event per criterion 3 would leave the Event with zero remaining participants, THEN THE Delete_Service SHALL remove that Event from the ProjectData events list instead of leaving it empty.

### Requirement 4: Family Cleanup

**User Story:** As a user, I want family records to be cleaned up when a person is deleted, so that no broken references remain in the data.

#### Acceptance Criteria

1. WHEN a Person is deleted, THE Delete_Service SHALL remove the Person from the partners list of all Family records where the Person appears as a FamilyPartner.
2. WHEN a Person is deleted, THE Delete_Service SHALL remove the Person's id from the children list of all Family records where the Person appears as a child.
3. WHEN a Person is deleted, THE Delete_Service SHALL remove all ParentChildLink entries from Family records where child_id or parent_id equals the deleted Person's id.
4. IF a Family has zero partners and zero children after criteria 1–3 have been applied, THEN THE Delete_Service SHALL remove that Family from the ProjectData families list.
5. IF a Family is removed from the ProjectData families list due to being empty, THEN THE Delete_Service SHALL retain the Event records referenced by the removed Family's event_ids in the ProjectData events list.

### Requirement 5: Media Preservation

**User Story:** As a user, I want media items to remain intact when a person is deleted, so that historical documents and photos are never lost.

#### Acceptance Criteria

1. WHEN a Person is deleted, THE Delete_Service SHALL not remove any MediaItem from the ProjectData media list.
2. WHEN a Person is deleted, THE Delete_Service SHALL remove all occurrences of the Person's id from the mentioned_person_ids list of every MediaItem that references the deleted Person.
3. WHEN a Person is deleted, THE Delete_Service SHALL remove all LinkedEntity entries from MediaItem records where entity_type is "person" and entity_id equals the deleted Person's id.
4. WHEN a Person is deleted, THE Delete_Service SHALL remove all Annotation entries from MediaItem records where entity_type is "person" and entity_id equals the deleted Person's id.
5. WHEN a Person is deleted, THE Delete_Service SHALL not modify the mentioned_names list of any MediaItem.

### Requirement 6: Shared Event Warning

**User Story:** As a user, I want to be warned before deleting a person who participates in shared events, so that I can make an informed decision about data loss.

#### Acceptance Criteria

1. WHEN the user requests deletion of a Person who is a participant in one or more Family_Events, THE Confirmation_Dialog SHALL display a Swedish-language warning listing each affected Family_Event by its type and date value (or "inget datum" when the event has no date).
2. WHEN the user requests deletion of a Person who is a participant in one or more Shared_Events, THE Confirmation_Dialog SHALL display a Swedish-language warning listing each affected Shared_Event by its type and date value (or "inget datum" when the event has no date).
3. IF the Person is not a participant in any Family_Events or Shared_Events, THEN THE System SHALL proceed with deletion using a generic confirmation prompt without displaying event warnings.
4. THE Confirmation_Dialog SHALL display at most 10 affected events in the warning list, and IF more than 10 events are affected, THEN THE Confirmation_Dialog SHALL indicate the total count of remaining events not shown.
5. WHEN the user clicks the "Ta bort" button in the Confirmation_Dialog, THE System SHALL proceed with the deletion operation.
6. WHEN the user clicks the "Avbryt" button in the Confirmation_Dialog, THE System SHALL close the dialog and preserve the Person record and all event associations unchanged.

### Requirement 7: Tree Disconnection Warning

**User Story:** As a user, I want to be warned if deleting a person would create a detached section of the family tree, so that I can avoid accidentally fragmenting my research.

#### Acceptance Criteria

1. WHEN the user requests deletion of a Person, THE Delete_Service SHALL compute whether removing the Person would create a Detached_Section unreachable from the Main_Person by traversing Family partner links and ParentChildLink parent-child links, and SHALL return the result within 2 seconds for projects containing up to 50 000 persons.
2. WHEN deletion would create a Detached_Section, THE Confirmation_Dialog SHALL display a Swedish-language warning identifying the number of persons that would become disconnected and SHALL present the user with a confirm button to proceed with deletion and a cancel button to abort the operation.
3. IF the user selects cancel in the disconnection Confirmation_Dialog, THEN THE Delete_Service SHALL abort the deletion and preserve the Person and all associated Family links unchanged.
4. WHEN deletion would NOT create a Detached_Section, THE Delete_Service SHALL proceed with deletion without displaying a disconnection warning.
5. WHILE no Main_Person is set in ProjectMetadata, THE Delete_Service SHALL skip the Tree_Connectivity check and not display a disconnection warning.
6. IF the user requests deletion of the Person currently set as Main_Person in ProjectMetadata, THEN THE Delete_Service SHALL skip the Tree_Connectivity check and not display a disconnection warning.

### Requirement 8: Data Integrity After Deletion

**User Story:** As a user, I want the project data to remain consistent after a deletion, so that no dangling references cause errors.

#### Acceptance Criteria

1. WHEN a Person is deleted, THE Delete_Service SHALL ensure no Event in ProjectData contains a Participant with person_id equal to the deleted Person's id.
2. WHEN a Person is deleted, THE Delete_Service SHALL ensure no Family in ProjectData contains a FamilyPartner with person_id equal to the deleted Person's id.
3. WHEN a Person is deleted, THE Delete_Service SHALL ensure no Family in ProjectData contains the deleted Person's id in its children list.
4. WHEN a Person is deleted, THE Delete_Service SHALL ensure no Family in ProjectData contains a ParentChildLink where child_id or parent_id equals the deleted Person's id.
5. WHEN a Person is deleted, THE Delete_Service SHALL mark the project as dirty (unsaved changes) by setting the ProjectService dirty flag.
6. FOR ALL valid ProjectData states, deleting a Person and then serializing and deserializing the ProjectData SHALL produce an equivalent ProjectData object (round-trip integrity).
