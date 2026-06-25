# Requirements Document

## Introduction

This document specifies enhancements to the Place Editor (Platsredigerare) in Släktbusken. The enhancements add support for external IDs (used in GEDCOM exports), alternative names for places, visual indicators for places missing a parent in the place list, and type-based filtering of the place list.

## Glossary

- **Place_Editor**: The Platsredigerare widget providing a split-panel interface with a filterable place list on the left and a detail form on the right.
- **Place_Model**: The Place dataclass containing place data (id, type, name, parent_place_id, latitude, longitude, notes).
- **External_ID**: A key-value pair associating a place with an identifier in an external system. The key identifies the external system (e.g. `_PARISH_AID` for Arkiv Digital) and the value holds the identifier string.
- **Alternative_Name**: An additional name for a place, used when a place is known by more than one name (e.g. a county letter for a county, or an informal name for a farm).
- **Parent_Place**: The hierarchically superior place to which a given place belongs, as defined by the place-type hierarchy.
- **Place_List**: The QListWidget in the left panel of the Place_Editor displaying all places matching the current filter.
- **Type_Filter**: A filter control allowing the user to restrict the Place_List to show only places of a selected type.
- **Red_Dot_Indicator**: A small red dot rendered at the end of a place name in the Place_List, signalling that the place has no Parent_Place assigned.

## Requirements

### Requirement 1: External IDs Data Storage

**User Story:** As a genealogist, I want to associate one or more external IDs with a place, so that I can export correct references when generating GEDCOM files (e.g. `_PARISH_AID` for Arkiv Digital).

#### Acceptance Criteria

1. THE Place_Model SHALL store zero or more External_ID entries, where each entry consists of a key string (1–100 characters) and a value string (1–500 characters).
2. WHEN an External_ID entry is added, THE Place_Model SHALL preserve the key and value exactly as entered by the user, including case and any non-whitespace characters.
3. THE Place_Model SHALL allow multiple External_ID entries with distinct keys for the same place.
4. IF a user attempts to add an External_ID with a key that already exists on the place, THEN THE Place_Editor SHALL display a validation error message indicating that the key is already in use and not add the entry.
5. IF a user attempts to add an External_ID with an empty or whitespace-only key or value, THEN THE Place_Editor SHALL display a validation error message indicating the field that is missing and not add the entry.
6. WHEN the user removes an External_ID entry from a place, THE Place_Editor SHALL delete that entry from the Place_Model and no longer include it in subsequent GEDCOM exports.

### Requirement 2: External IDs Form UI

**User Story:** As a genealogist, I want a dedicated section in the place detail form where I can add, edit, and remove external IDs, so that I can manage GEDCOM export identifiers without leaving the editor.

#### Acceptance Criteria

1. THE Place_Editor SHALL display a labeled section "Externa ID:n" in the detail form for managing External_ID entries.
2. WHEN the user clicks an add button in the External_ID section, THE Place_Editor SHALL present input fields for entering a key (maximum 100 characters) and a value (maximum 200 characters).
3. WHEN the user confirms an External_ID entry with a non-empty key and non-empty value, THE Place_Editor SHALL add the entry to the current place.
4. WHEN the user selects an existing External_ID entry and clicks a remove button, THE Place_Editor SHALL remove that entry from the current place.
5. WHEN a place is loaded into the detail form, THE Place_Editor SHALL display all existing External_ID entries for that place, showing each entry's key and value as distinct readable fields.
6. IF a user attempts to confirm an External_ID entry with an empty key or empty value, THEN THE Place_Editor SHALL display a validation error and retain the input fields for correction.
7. WHEN the user selects an existing External_ID entry and activates an edit action, THE Place_Editor SHALL present the entry's key and value in editable input fields, and upon confirmation with valid non-empty values, THE Place_Editor SHALL update that entry in the current place.

### Requirement 3: Alternative Name Data Storage

**User Story:** As a genealogist, I want to store one or more alternative names for a place, so that I can record informal names, county letters, or other aliases alongside the official name.

#### Acceptance Criteria

1. THE Place_Model SHALL store zero or more Alternative_Name strings for each place, each between 1 and 200 characters in length.
2. WHEN an Alternative_Name is added, THE Place_Model SHALL preserve the text exactly as entered by the user, including original casing, spacing, and special characters.
3. IF a user attempts to add an Alternative_Name that is identical (case-sensitive, exact character match) to an existing Alternative_Name on the same place, THEN THE Place_Editor SHALL display a validation error indicating the name already exists and not add the duplicate entry.
4. IF a user attempts to add an Alternative_Name that is empty or contains only whitespace characters, THEN THE Place_Editor SHALL display a validation error indicating that the name must contain at least one non-whitespace character.
5. WHEN the user removes an Alternative_Name from a place, THE Place_Editor SHALL delete that entry from the place's list of Alternative_Names and preserve all remaining entries in their original order.

### Requirement 4: Alternative Name Form UI

**User Story:** As a genealogist, I want a field labeled "Alternativnamn" in the place detail form where I can add and remove alternative names, so that I can manage place aliases visually.

#### Acceptance Criteria

1. THE Place_Editor SHALL display a labeled section "Alternativnamn:" in the detail form for managing Alternative_Name entries.
2. WHEN the user clicks an add button in the Alternative_Name section, THE Place_Editor SHALL present a text input field for entering a name.
3. WHEN the user confirms an Alternative_Name entry with a non-empty, non-whitespace-only string of 1 to 200 characters, THE Place_Editor SHALL add the trimmed entry to the current place.
4. WHEN the user selects an existing Alternative_Name entry and clicks a remove button, THE Place_Editor SHALL remove that entry from the current place.
5. WHEN a place is loaded into the detail form, THE Place_Editor SHALL display all existing Alternative_Name entries for that place as a list.
6. IF a user attempts to confirm an Alternative_Name entry with an empty or whitespace-only string, or a string exceeding 200 characters, THEN THE Place_Editor SHALL display a validation error indicating the reason and retain the input field for correction.

### Requirement 5: Red Dot Indicator for Places Without Parent

**User Story:** As a genealogist, I want to quickly identify places that are missing a parent place assignment, so that I can correct incomplete hierarchy data.

#### Acceptance Criteria

1. WHEN a place of any type other than "country" has no Parent_Place assigned, THE Place_List SHALL display a Red_Dot_Indicator at the end of that place's name.
2. WHEN a place of type "country" has no Parent_Place assigned, THE Place_List SHALL display the name without a Red_Dot_Indicator.
3. WHEN a place has a Parent_Place assigned, THE Place_List SHALL display the name without a Red_Dot_Indicator.
4. WHEN a place's Parent_Place assignment changes from empty to a valid parent, THE Place_List SHALL remove the Red_Dot_Indicator for that place when the Place_List is next repopulated or refreshed.
5. WHEN a place's Parent_Place assignment changes from a valid parent to empty (parent removed), THE Place_List SHALL display the Red_Dot_Indicator for that place when the Place_List is next repopulated or refreshed.
6. THE Red_Dot_Indicator SHALL be rendered as a solid red circle of no more than 8px diameter, positioned 4px after the last character of the place name text, vertically centered with the text baseline.

### Requirement 6: Filter by Place Type

**User Story:** As a genealogist, I want to filter the place list by type in addition to text search, so that I can quickly find all places of a specific type (e.g. all parishes or all farms).

#### Acceptance Criteria

1. THE Place_Editor SHALL display a Type_Filter control in the left panel, positioned between the text filter and the Place_List.
2. THE Type_Filter SHALL include an option for each place type (Land, Län, Socken, Kyrka, Kyrkogård, By, Gård, Skola) plus an "Alla" option that shows all types.
3. WHEN the user selects a specific type in the Type_Filter, THE Place_List SHALL display only places matching both the selected type and the current text filter, sorted alphabetically by place name.
4. WHEN the user selects "Alla" in the Type_Filter, THE Place_List SHALL display all places matching the current text filter regardless of type.
5. WHEN the Place_Editor is opened, THE Type_Filter SHALL default to "Alla".
6. WHEN the Type_Filter selection changes, THE Place_List SHALL update within 200 milliseconds to reflect the new filter combination.
7. IF no places match the combination of the selected type and the current text filter, THEN THE Place_List SHALL display an empty list with no error message.
