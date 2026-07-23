# Requirements Document

## Introduction

This feature extends the Släktbusken place hierarchy with continent as a universal top-level type and introduces country-specific region levels. Instead of a fixed global set of intermediate place types (county, parish), each country defines its own administrative subdivision levels. The Place Editor dropdown adapts dynamically to show only relevant types based on which countries exist in the project. This makes the hierarchy both consistent (continent → country → regions → local types) and clutter-free.

## Glossary

- **Place_Model**: The `Place` dataclass representing a geographic location in the Släktbusken project.
- **Region_Level**: A named administrative subdivision specific to a country, defined by a key, a display label, and an order position.
- **Place_Editor**: The PySide6 editor panel used to create and edit Place entities.
- **Type_Dropdown**: The dropdown widget in Place_Editor that lets the user select the type of a place.
- **Red_Dot_Indicator**: A visual marker shown on places that have incomplete data (specifically, missing parent assignment).
- **Universal_Place_Type**: A place type that applies regardless of country context and can be placed at any level below country: church, cemetery, farm, school, locality (ort). These are "leaf-level" types with flexible parent assignment.
- **Project**: The root container (`ProjectData`) holding all entities including places.
- **Country_Presets**: Bundled region level definitions for common countries that ship with the application.

## Requirements

### Requirement 1: Continent as Top-Level Place Type

**User Story:** As a genealogist, I want continents as root-level places in the hierarchy, so that the geographic tree has a consistent top-level entry point above countries.

#### Acceptance Criteria

1. THE Place_Model SHALL support "continent" as a valid place type, accepted without validation errors when assigned to the type field of a Place.
2. WHEN a place has type "continent", THE Place_Model SHALL allow parent_place_id to be None without triggering validation errors.
3. WHEN a place has type "continent" and parent_place_id is not None, THE Place_Model SHALL reject the place with a validation error indicating that continents cannot have a parent place.
4. WHEN a place has type "country" and parent_place_id is None, THE Place_Model SHALL reject the place with a validation error indicating that a country must reference a continent as its parent.
5. WHEN a place has type "country" and parent_place_id references a place whose type is not "continent", THE Place_Model SHALL reject the place with a validation error indicating that a country's parent must be of type "continent".
6. WHEN a place has type "country" and parent_place_id references a place of type "continent", THE Place_Model SHALL accept the parent assignment without validation errors.
7. THE Place_Editor SHALL list "continent" in the Type_Dropdown as the first item, before "country" and all other place types.

### Requirement 2: Country-Specific Region Levels

**User Story:** As a genealogist working with multiple countries, I want each country to define its own administrative subdivision levels, so that I can model correct hierarchies for Sverige (Län → Socken), USA (State → County → City), and others without conflicting types.

#### Acceptance Criteria

1. THE Place_Model SHALL include a `region_levels` field on places of type "country", containing an ordered list of at most 10 Region_Level definitions.
2. WHEN a Region_Level is defined, THE Place_Model SHALL store a key (1 to 50 characters), a label (1 to 100 characters), and an order position (a positive integer starting from 1) for each entry.
3. WHEN a place of type "country" has region_levels defined, THE Place_Model SHALL enforce that region level keys are unique within that country and reject the operation with a validation error indicating the duplicate key if violated.
4. WHEN a place of type "country" has region_levels defined, THE Place_Model SHALL enforce that order positions are consecutive integers starting at 1 (no gaps) and unique within that country, rejecting the operation with a validation error indicating the invalid order if violated.
5. WHILE a place is not of type "country", THE Place_Model SHALL ignore the region_levels field (treat it as empty).
6. IF a Region_Level key or label is empty or exceeds its maximum length, THEN THE Place_Model SHALL reject the operation with a validation error indicating the invalid field.

### Requirement 3: Contextual Type Dropdown

**User Story:** As a genealogist, I want the place type dropdown to show only relevant types based on the countries in my project, so that I am not confused by region types from countries I have not added.

#### Acceptance Criteria

1. THE Type_Dropdown SHALL always include "continent" and "country" as available options.
2. THE Type_Dropdown SHALL always include all Universal_Place_Types (church, cemetery, farm, school, locality/ort) as available options.
3. WHEN one or more countries with region_levels exist in the Project, THE Type_Dropdown SHALL include all region level labels collected from those countries.
4. WHEN no countries with region_levels exist in the Project, THE Type_Dropdown SHALL show only "continent", "country", and Universal_Place_Types.
5. WHEN a country is removed from the Project, THE Type_Dropdown SHALL no longer include region level labels that are exclusive to that removed country.
6. THE Universal_Place_Types (church, cemetery, farm, school) SHALL be allowed as children of any region level or of locality (ort), giving the researcher flexibility to place them wherever appropriate in the hierarchy.
7. THE "locality" (Ort) Universal_Place_Type SHALL be allowed as a child of any region level, making it usable as a general-purpose settlement type at any depth below country.

### Requirement 4: Imprecise Geographic Knowledge

**User Story:** As a genealogist, I want to link events to continents or countries even when I lack precise location details, so that I can honestly represent what a historical source tells me (e.g., "emigrated to Nordamerika").

#### Acceptance Criteria

1. THE Place_Model SHALL allow events to reference a place of any type, including "continent" and "country", via PlaceRef without restricting which place types are valid targets.
2. THE Place_Model SHALL allow latitude and longitude to remain None for places of any type, including "continent" and "country", without triggering validation errors.
3. WHEN a place of type "continent" or "country" is selected for an event, THE Place_Editor SHALL save the assignment without requiring coordinates or selection of a more specific child place.
4. WHEN a place of type "continent" or "country" with latitude and longitude set to None is referenced by an event, THE Red_Dot_Indicator SHALL NOT flag the event or the place as incomplete due to missing coordinates.

### Requirement 5: Red Dot Indicator Update

**User Story:** As a genealogist, I want the red dot indicator to correctly reflect missing parent assignments in the new hierarchy, so that continents (which are root-level by definition) do not show false warnings.

#### Acceptance Criteria

1. WHEN a place has type "continent" and parent_place_id is None, THE Red_Dot_Indicator SHALL not flag the place.
2. WHEN a place has type "country" and parent_place_id is None, THE Red_Dot_Indicator SHALL flag the place.
3. WHEN a place has any type other than "continent" and parent_place_id is None, THE Red_Dot_Indicator SHALL flag the place.
4. WHEN a place has parent_place_id set to a non-None value, THE Red_Dot_Indicator SHALL not flag the place regardless of its type.
5. WHEN a place's parent_place_id changes from None to a non-None value, THE Red_Dot_Indicator SHALL remove the flag after the place list is refreshed.
6. WHEN a place's parent_place_id changes from a non-None value to None and the place type is not "continent", THE Red_Dot_Indicator SHALL display the flag after the place list is refreshed.

### Requirement 6: Country Presets

**User Story:** As a genealogist, I want presets for common countries (Sverige, USA, Tyskland, Norge, Danmark, Finland, England), so that I can quickly add a country with its correct region levels without manual configuration.

#### Acceptance Criteria

1. THE Place_Editor SHALL offer preset region level definitions for Sverige, USA, Tyskland, Norge, Danmark, Finland, and England.
2. WHEN the user selects a country preset, THE Place_Editor SHALL populate the region_levels field with the predefined definitions for that country.
3. WHEN the user selects a country preset, THE Place_Editor SHALL allow the user to modify the populated region_levels before saving.
4. THE Country_Presets SHALL define the following region levels:
   - Sverige: Län (order 1), Socken (order 2)
   - USA: Delstat (order 1), County (order 2)
   - Tyskland: Förbundsland (order 1), Kreis (order 2)
   - Norge: Fylke (order 1), Kommune (order 2)
   - Danmark: Region (order 1), Kommune (order 2)
   - Finland: Landskap (order 1), Kommun (order 2)
   - England: County (order 1), Parish (order 2)

### Requirement 8: Region Level Custom Fields

**User Story:** As a genealogist, I want to register extra metadata on places of a specific region type (e.g., "Länsbokstav" for Swedish Län, or state abbreviation for US states), so that I can use standard archival codes in my research.

#### Acceptance Criteria

1. EACH Region_Level definition SHALL optionally include a list of custom field definitions, each with a field key (1 to 50 characters) and a display label (1 to 100 characters).
2. WHEN a place has a type matching a Region_Level that defines custom fields, THE Place_Editor SHALL display input fields for those custom fields in the place form.
3. THE Place_Model SHALL store custom field values as key-value pairs on places whose type matches a Region_Level with custom fields defined.
4. THE Country_Presets for Sverige SHALL include a custom field "code" with label "Länsbokstav" on the Län region level.
5. WHEN a custom field value is entered, THE Place_Model SHALL accept values of 1 to 20 characters.
6. WHEN a custom field value is left empty, THE Place_Model SHALL accept the place without validation errors (custom fields are optional).

### Requirement 9: Region Level Serialization

**User Story:** As a developer, I want region level definitions to be correctly serialized and deserialized from the project file, so that no data is lost between save and load cycles.

#### Acceptance Criteria

1. WHEN a project is saved, THE Place_Model SHALL serialize region_levels as part of the place data for countries.
2. WHEN a project is loaded, THE Place_Model SHALL deserialize region_levels back into structured Region_Level objects.
3. FOR ALL valid Place objects with region_levels, saving then loading SHALL produce an equivalent object (round-trip property).
