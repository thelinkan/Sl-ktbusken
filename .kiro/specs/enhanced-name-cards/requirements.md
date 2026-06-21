# Requirements Document

## Introduction

Enhanced name cards for the diagram views in Släktbusken. The goal is to improve the visual richness and information density of person boxes in the QGraphicsScene-based graphs. Key enhancements include: marking persons with multiple names, displaying DNA test company logos, distinguishing the main/active person with a unique border color, showing a profile photo, displaying additional data fields (birth/death place, cause of death, clusters), and widening the card to accommodate the added content.

## Glossary

- **Name_Card**: The `PersonBoxItem` QGraphicsItem rendered in the diagram scene, displaying a person's configured fields inside a bordered rectangle.
- **Person**: A person record in the project data model, identified by a unique ID and containing names, events, and metadata.
- **Multiple_Names**: A Person who has more than one Name entry in their names list (e.g., birth name and married name).
- **DNA_Company**: A DNA testing company record containing an ID, name, and optional logo media reference.
- **DNA_Profile**: A DNA test profile/kit belonging to a Person, linked to a specific DNA_Company.
- **DNA_Cluster**: A named grouping of DNA matches and persons, with an optional color and associated company and person IDs.
- **Main_Person**: The person designated as `main_person_id` in the project metadata — the focal/root person of the genealogy project.
- **Active_Person**: The person currently selected/focused in the diagram view (the one whose family tree is being explored).
- **Profile_Photo**: A media image linked to a Person via `profile_media_id`, displayed as a thumbnail in the Name_Card.
- **Cause_of_Death**: The `cause_of_death` field on a death Event associated with a Person.
- **PersonBoxConfig**: The settings dataclass controlling which fields are visible on Name_Cards, stored in project settings.

## Requirements

### Requirement 1: Multiple Names Indicator

**User Story:** As a genealogist, I want to see a visual indicator on persons who have more than one name entry, so that I can quickly identify people with name changes (e.g., maiden name, married name, adopted name).

#### Acceptance Criteria

1. WHEN a Person has more than one Name entry in the names list, THE Name_Card SHALL display a small icon indicator (distinct from the gender icon) in the top-left area of the card, positioned at coordinates (_PADDING / 2, _PADDING / 2) with a size of 14×14 pixels.
2. THE indicator SHALL be rendered as a recognizable "multiple names" icon (e.g., a stacked-names or alias symbol) and SHALL NOT overlap the name text line or gender icon.
3. WHEN a Person has exactly one Name entry, THE Name_Card SHALL NOT display the multiple names indicator.
4. THE multiple names indicator SHALL always be visible when applicable, regardless of PersonBoxConfig toggle states (it is not toggleable).

### Requirement 2: DNA Company Logos

**User Story:** As a genealogist, I want to see logos of DNA testing companies where a person has a test, so that I can quickly identify which companies have tested a person without opening the editor.

#### Acceptance Criteria

1. WHEN DNA_Profile records exist for a Person AND the PersonBoxConfig dna_info field is enabled, THE Name_Card SHALL display the logo of each associated DNA_Company as a 16×16 pixel icon, arranged horizontally in the bottom-right corner of the card, up to a maximum of 5 logos.
2. WHEN multiple DNA_Company logos are displayed, THE Name_Card SHALL order them alphabetically by company name from left to right.
3. WHEN a DNA_Company has a logo_media_id set, THE Name_Card SHALL render the company logo scaled to 16×16 pixels.
4. IF a DNA_Company has no logo_media_id, THEN THE Name_Card SHALL display the first 2 characters of the company name as a text-based placeholder icon at 16×16 pixels.
5. IF no DNA_Profile records exist for a Person, THEN THE Name_Card SHALL NOT display any DNA company logos or placeholder icons.
6. THE PersonBoxConfig SHALL include a toggle for DNA company logo visibility (reusing the existing dna_info toggle, default False).

### Requirement 3: Main Person Border Color

**User Story:** As a genealogist, I want the main/root person of my project to be visually distinct from ancestors and descendants, so that I can always identify the focal person of the tree at a glance.

#### Acceptance Criteria

1. WHEN the displayed Person is the Main_Person of the project (identified by main_person_id in project metadata), THE Name_Card SHALL render its border in orange (QColor(0xF3, 0x9C, 0x12)) with a border width of 2.5, distinct from the ancestor border color (red), the descendant border color (green), the default border color (gray), and the selected border color (blue).
2. IF the Main_Person is also classified as an ancestor or descendant, THEN THE Name_Card SHALL display the Main_Person border color (orange, width 2.5) instead of the ancestor or descendant border color.
3. WHEN the Main_Person is selected, THE Name_Card SHALL display the selected border color (blue, width 2.5), overriding the Main_Person border color.
4. WHEN the displayed Person is NOT the Main_Person, THE Name_Card SHALL use the existing border color rules (ancestor red with width 2.0, descendant green with width 2.0, default gray with width 1.0, selected blue with width 2.5).

### Requirement 4: Profile Photo Display

**User Story:** As a genealogist, I want to see a person's profile photo directly on the name card, so that I can visually recognize individuals in the diagram.

#### Acceptance Criteria

1. WHEN a Person has a profile_media_id set AND the PersonBoxConfig photo field is enabled, THE Name_Card SHALL display the profile photo as a square thumbnail of 40×40 pixels, positioned on the left side of the card with its top edge aligned to the top padding (8.0 pixels from the card top).
2. WHEN the PersonBoxConfig photo field is enabled AND a Person has a profile_media_id set, THE Name_Card SHALL offset all text content to the right by 48 pixels (40 pixel photo width plus 8 pixel gap) to avoid overlapping the photo area.
3. WHEN a Person has no profile_media_id AND the PersonBoxConfig photo field is enabled, THE Name_Card SHALL NOT reserve space for the photo, and text content SHALL start at the normal left padding (8.0 pixels).
4. IF a Person has a profile_media_id set AND the PersonBoxConfig photo field is enabled AND the referenced media cannot be loaded, THEN THE Name_Card SHALL render the card without the photo and SHALL NOT reserve space for the photo area.
5. THE PersonBoxConfig SHALL include a toggle for profile photo visibility (using the existing photo field, default False).
6. WHEN the profile photo is displayed, THE Name_Card SHALL scale the source image to fit within the 40×40 pixel area while preserving aspect ratio, centering the result within that area.

### Requirement 5: Birth and Death Place Display

**User Story:** As a genealogist, I want to see birth place and death place on the name card, so that I can quickly see geographical information about a person.

#### Acceptance Criteria

1. WHEN the PersonBoxConfig birth_place field is enabled AND the Person has a non-empty birth place value, THE Name_Card SHALL display the birth place on the line immediately following the birth date line, prefixed with a place label.
2. WHEN the PersonBoxConfig death_place field is enabled AND the Person has a non-empty death place value, THE Name_Card SHALL display the death place on the line immediately following the death date line, prefixed with a place label.
3. IF a place field is enabled but the Person has no corresponding place data (None or empty string), THEN THE Name_Card SHALL omit that place line entirely without reserving vertical space for it.
4. THE PersonBoxConfig SHALL include toggles for birth_place and death_place visibility (using the existing boolean fields, defaulting to False).
5. IF the place text exceeds the available horizontal width of the Name_Card content area, THEN THE Name_Card SHALL truncate the text with an ellipsis so that it does not overflow the box boundary.

### Requirement 6: Cause of Death Display

**User Story:** As a genealogist, I want to see the cause of death on the name card, so that I can note important medical or historical information at a glance.

#### Acceptance Criteria

1. WHEN the PersonBoxConfig cause_of_death field is enabled AND the Person has a death event with a non-empty cause_of_death value, THE Name_Card SHALL display the cause of death text, truncated to a maximum of 50 characters with an ellipsis ("…") appended if the original text exceeds 50 characters.
2. WHEN the PersonBoxConfig cause_of_death field is enabled AND the Person has no death event or the cause_of_death is empty, THE Name_Card SHALL NOT display a line for the cause of death field.
3. THE PersonBoxConfig SHALL include a boolean field named cause_of_death that controls visibility of the cause of death on the Name_Card, defaulting to False.
4. WHEN the PersonBoxConfig cause_of_death field is disabled, THE Name_Card SHALL NOT display the cause of death regardless of whether the Person has a cause_of_death value.

### Requirement 7: Cluster Display

**User Story:** As a genealogist, I want to see which DNA clusters a person belongs to on the name card, so that I can identify cluster groupings visually in the diagram.

#### Acceptance Criteria

1. WHEN the PersonBoxConfig clusters field is enabled AND the Person belongs to one or more DNA_Cluster records, THE Name_Card SHALL display each cluster name as a separate text entry on the card, listed in alphabetical order by cluster name, showing a maximum of 5 cluster names.
2. WHEN a DNA_Cluster has a color property set to a valid color string, THE Name_Card SHALL render the cluster name text in that color.
3. IF a DNA_Cluster has no color property set (None), THEN THE Name_Card SHALL render the cluster name using the default label text color.
4. WHEN the PersonBoxConfig clusters field is enabled AND the Person belongs to no DNA_Cluster records, THE Name_Card SHALL NOT display an empty cluster line or placeholder.
5. THE PersonBoxConfig SHALL include a boolean field named clusters that controls visibility of cluster information on the Name_Card, defaulting to False.
6. IF the Person belongs to more than 5 DNA_Cluster records AND the PersonBoxConfig clusters field is enabled, THEN THE Name_Card SHALL display only the first 5 cluster names in alphabetical order and append an indicator showing the count of remaining clusters.

### Requirement 8: Wider Name Card

**User Story:** As a genealogist, I want name cards to be wider, so that long names fit without truncation and there is space for the profile photo alongside the text content.

#### Acceptance Criteria

1. THE Name_Card SHALL have a default width of 240 pixels (increased from the current 180 pixels) to accommodate the profile photo area and longer name text.
2. WHEN the PersonBoxConfig photo field is enabled AND a Person has a profile_media_id, THE Name_Card SHALL allocate 48 pixels (40px photo + 8px gap) on the left for the photo thumbnail, leaving 184 pixels for text content.
3. WHEN the PersonBoxConfig photo field is disabled OR the Person has no profile_media_id, THE Name_Card SHALL use the full 240-pixel width minus padding for text content.
4. THE Name_Card width change SHALL apply uniformly across all diagram views (Family, Ancestry, Descendants).
