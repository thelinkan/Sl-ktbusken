# Requirements Document

## Introduction

This feature enhances the DNA match list in the DNA Editor to display both persons involved in each match (resolved from the two profiles' person references) before the cM value. Additionally, a filter mechanism is added so users can filter the match list by a specific person, showing all matches where that person appears as either profile 1 or profile 2. The UI text is in Swedish.

## Glossary

- **DNA_Editor**: The tabbed editor widget for DNA-related records (`DnaEditor`), containing the matches tab where match entries are listed.
- **Match_List**: The `QListWidget` in the DNA_Editor matches tab that displays all DNA match entries.
- **DNA_Match**: A DNA match record (`DnaMatch` dataclass) linking two profiles via `profile1_id` and `profile2_id`, with fields such as `shared_cm` and `segment_count`.
- **DNA_Profile**: A DNA test profile (`DnaProfile` dataclass) with a `person_id` field linking to a Person record.
- **Person**: A person record (`Person` dataclass) with a `names` list containing Name entries with `given` and `surname` fields.
- **Person_Display_Name**: A formatted string showing a person's name as "Förnamn Efternamn" derived from the first entry in the Person's names list.
- **Match_Filter**: A UI control (text input or combo box) in the matches tab that allows filtering the Match_List by a specific person.
- **Project_Data**: The in-memory data store (`ProjectData`) containing all project entities including persons, DNA profiles, and DNA matches.

## Requirements

### Requirement 1: Display Both Persons in Match List Entries

**User Story:** As a genealogist, I want to see both persons' names in each DNA match list entry, so that I can immediately identify who is matched with whom without clicking on each entry.

#### Acceptance Criteria

1. WHEN the Match_List displays a DNA_Match entry, THE Match_List SHALL format each entry as "{Person1_Name} – {Person2_Name}: {shared_cm} cM ({segment_count} segment)" where Person1_Name is the Person_Display_Name resolved from profile1_id, Person2_Name is the Person_Display_Name resolved from profile2_id, shared_cm is displayed with up to one decimal place (trailing ".0" preserved, no trailing zeros beyond the first decimal), and the separator between names is an en-dash (U+2013) surrounded by spaces.
2. WHEN resolving Person_Display_Name for a DNA_Match entry, THE DNA_Editor SHALL follow the chain DNA_Match → profile_id → DNA_Profile → person_id → Person → first entry in names list → "given surname" (concatenated with a single space, trimmed of leading and trailing whitespace).
3. IF a DNA_Profile referenced by a DNA_Match cannot be found in Project_Data, THEN THE Match_List SHALL display the profile ID string as a fallback in place of the Person_Display_Name.
4. IF a Person referenced by a DNA_Profile cannot be found in Project_Data, THEN THE Match_List SHALL display the person_id string as a fallback in place of the Person_Display_Name.
5. IF a Person's names list is empty OR the first name entry has both given and surname fields empty, THEN THE Match_List SHALL display "(okänd)" as the Person_Display_Name.

### Requirement 2: Person Filter for Match List

**User Story:** As a genealogist, I want to filter the DNA match list by a specific person, so that I can quickly find all matches involving a particular individual regardless of whether they are person A or person B in the match.

#### Acceptance Criteria

1. THE DNA_Editor matches tab SHALL display a Match_Filter control above the Match_List.
2. THE Match_Filter SHALL provide a text input field with placeholder text "Filtrera på person..." that allows the user to type a search string.
3. WHEN the user types or modifies text in the Match_Filter, THE Match_List SHALL update on each keystroke to display only DNA_Match entries where the filter text matches (case-insensitively) a substring of either the Person_Display_Name resolved from profile1_id or the Person_Display_Name resolved from profile2_id (including fallback display names such as profile IDs, person_ids, or "(okänd)").
4. WHEN the Match_Filter text is empty, THE Match_List SHALL display all DNA_Match entries without filtering.
5. WHEN the user clears the Match_Filter text, THE Match_List SHALL restore the full unfiltered list of DNA_Match entries.
6. WHEN the active filter results in zero matching DNA_Match entries, THE Match_List SHALL display an empty list (no items visible).

### Requirement 3: Filter Updates on Data Changes

**User Story:** As a genealogist, I want the filtered match list to stay consistent when matches are added or removed, so that the display always reflects the current data state.

#### Acceptance Criteria

1. WHILE a filter is active in the Match_Filter, WHEN a DNA_Match is added to Project_Data, THE Match_List SHALL re-apply the current filter and include the new match only if the filter text matches (case-insensitively) a substring of either resolved Person_Display_Name of the new match.
2. WHILE a filter is active in the Match_Filter, WHEN a DNA_Match is removed from Project_Data, THE Match_List SHALL re-apply the current filter and no longer display the removed match.
3. WHEN the Match_List is refreshed due to a data change, THE DNA_Editor SHALL preserve the current Match_Filter text value without modification.
4. WHILE no filter is active in the Match_Filter, WHEN a DNA_Match is added to or removed from Project_Data, THE Match_List SHALL refresh to display all current DNA_Match entries from Project_Data.
5. WHILE a filter is active in the Match_Filter, WHEN a DNA_Match in Project_Data is modified such that its resolved Person_Display_Names change, THE Match_List SHALL re-apply the current filter to reflect the updated names.
