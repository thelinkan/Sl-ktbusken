# Requirements Document

## Introduction

This feature implements the Swedish genealogy convention of marking a person's primary given name (tilltalsnamn) with an asterisk (*) in the stored given-name string. The asterisk is a data-entry convention used in programs like Genline and Disgen to indicate which of a person's given names they actually go by. For example, "Kent Torbjörn*" means the person is addressed as "Torbjörn".

The feature encompasses parsing the asterisk from the stored string, determining the tilltalsnamn, rendering it with visual emphasis (underline) instead of showing the raw asterisk, and ensuring search/filter operations work transparently without asterisk interference.

## Glossary

- **Tilltalsnamn**: The primary given name a person is addressed by in everyday life. In Swedish naming tradition, this is often not the first given name.
- **Given_Name_String**: The raw given-name field stored in a Name dataclass (e.g., "Kent Torbjörn*").
- **Asterisk_Marker**: The `*` character appended immediately after a name part to mark it as the tilltalsnamn.
- **Name_Parser**: The module responsible for extracting the tilltalsnamn and clean name parts from a Given_Name_String.
- **Person_Box**: The QGraphicsItem widget that renders a person's information in the diagram view.
- **Person_List_Panel**: The panel that shows a filterable, sorted list of all persons.

## Requirements

### Requirement 1: Parse Tilltalsnamn from Given Name String

**User Story:** As a genealogist, I want the application to detect which given name is marked with an asterisk, so that it can identify the tilltalsnamn without me having to enter it separately.

#### Acceptance Criteria

1. WHEN a Given_Name_String contains exactly one name part followed by an Asterisk_Marker, THE Name_Parser SHALL return that name part as the tilltalsnamn and its zero-based index within the list of name parts.
2. WHEN a Given_Name_String contains no Asterisk_Marker, THE Name_Parser SHALL return a result indicating no tilltalsnamn is present (null/None tilltalsnamn value).
3. WHEN a Given_Name_String contains multiple whitespace-separated name parts with exactly one Asterisk_Marker, THE Name_Parser SHALL identify the marked name part as the tilltalsnamn regardless of whether it appears at the first, middle, or last position.
4. THE Name_Parser SHALL treat the Asterisk_Marker as the `*` character placed immediately after a name part with no intervening whitespace (e.g., "Torbjörn*"), and SHALL treat a `*` character appearing in any other position within a name part as a literal character rather than a marker.
5. THE Name_Parser SHALL produce a clean display string with the Asterisk_Marker removed and all original whitespace between name parts preserved (e.g., "Kent Torbjörn*" becomes "Kent Torbjörn").
6. THE Name_Parser SHALL satisfy the round-trip property: for any valid Given_Name_String (containing zero or one Asterisk_Marker), parsing to extract the tilltalsnamn and clean name parts, then formatting back to a marked string, SHALL produce a string equal to the original input.
7. IF a Given_Name_String contains more than one Asterisk_Marker, THEN THE Name_Parser SHALL reject the input and return an error indication specifying that only one tilltalsnamn marker is permitted.

### Requirement 2: Underline Tilltalsnamn in Person Box

**User Story:** As a genealogist, I want the tilltalsnamn to be visually underlined in the person box on the diagram, so that I can see at a glance which name the person goes by.

#### Acceptance Criteria

1. WHEN a person's Given_Name_String contains an Asterisk_Marker, THE Person_Box SHALL render the tilltalsnamn with an underline text decoration on the name line.
2. WHEN a person's Given_Name_String contains no Asterisk_Marker, THE Person_Box SHALL render all given names without underline decoration.
3. THE Person_Box SHALL display the given name without the raw Asterisk_Marker character visible.
4. THE Person_Box SHALL render all given name parts in the same order as they appear in the Given_Name_String, with only the tilltalsnamn part underlined and remaining parts displayed without underline on the same text line.
5. IF a person's Given_Name_String contains more than one Asterisk_Marker, THEN THE Person_Box SHALL underline only the first marked name part and render the remaining name parts without underline.

### Requirement 3: Underline Tilltalsnamn in Person List Panel

**User Story:** As a genealogist, I want the tilltalsnamn underlined in the person list as well, so that the visual convention is consistent across the application.

#### Acceptance Criteria

1. WHEN a person's Given_Name_String contains an Asterisk_Marker, THE Person_List_Panel SHALL render the tilltalsnamn with an underline decoration in the list entry.
2. WHEN a person's Given_Name_String contains no Asterisk_Marker, THE Person_List_Panel SHALL render all given names without underline decoration.
3. THE Person_List_Panel SHALL display names without the raw Asterisk_Marker character visible.
4. WHEN a person's Given_Name_String contains an Asterisk_Marker, THE Person_List_Panel SHALL render non-tilltalsnamn parts of the given name without underline, adjacent to the underlined tilltalsnamn.

### Requirement 4: Search and Filter Ignore Asterisk

**User Story:** As a genealogist, I want to search for a person by their given name without needing to type the asterisk, so that the marker convention does not interfere with finding people.

#### Acceptance Criteria

1. WHEN a user enters a search term in the given-name filter, THE Person_List_Panel SHALL match against the given name with the Asterisk_Marker removed, using case-insensitive substring matching.
2. WHEN a user searches for "Torbjörn" and a person has Given_Name_String "Kent Torbjörn*", THE Person_List_Panel SHALL include that person in the results.
3. WHEN a user searches for "Kent" and a person has Given_Name_String "Kent Torbjörn*", THE Person_List_Panel SHALL include that person in the results.
4. THE Person_List_Panel SHALL sort persons alphabetically using the clean given name (Asterisk_Marker removed) so that sort order is unaffected by the marker.
5. IF a user enters an asterisk character in the search term, THE Person_List_Panel SHALL treat it as a literal character for matching purposes, not as a tilltalsnamn marker.

### Requirement 5: Preserve Asterisk in Stored Data and Editor

**User Story:** As a genealogist, I want the asterisk to remain in the stored data and be visible in the name editor, so that I can see and modify which name is marked as tilltalsnamn.

#### Acceptance Criteria

1. THE Person_Editor SHALL display the Given_Name_String including the Asterisk_Marker in the given-name input field, limited to a maximum of 100 characters.
2. WHEN a user saves a person with an Asterisk_Marker in the given-name field, THE Person_Editor SHALL preserve the Asterisk_Marker in the stored Name object at the same position within the Given_Name_String.
3. WHEN a user adds or moves the Asterisk_Marker to a different name part and saves, THE Person_Editor SHALL store the updated Given_Name_String with the new marker position.
4. IF a user enters more than one Asterisk_Marker in a single Given_Name_String, THEN THE Person_Editor SHALL display a validation error indicating that only one tilltalsnamn can be marked and SHALL prevent saving the Person record until the duplicate marker is removed.
5. IF a user enters an Asterisk_Marker that is not placed immediately after a name part (e.g., a standalone "*", a leading "*", or an asterisk preceded by whitespace), THEN THE Person_Editor SHALL display a validation error indicating that the marker must be placed directly after a name part and SHALL prevent saving until corrected.
