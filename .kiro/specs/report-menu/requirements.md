# Requirements Document

## Introduction

This feature adds a "Rapporter" (Reports) menu to Släktbusken, the Swedish-language genealogy desktop application built with Python and PySide6 that stores all project data in a gzipped App_JSON file within a Project_Folder. The Report_Menu exposes the complete planned report catalogue, organized into five categories: Standardrapporter, DNA-rapporter, Konsistensrapporter, Forskningsrapporter, and Exportkontroller.

In this iteration, three reports are fully implemented: the Ansedel_Report (a standard person/family report), the Geographic_Consistency_Report, and the Media_Consistency_Report. All remaining report entries appear in the Report_Menu as disabled Placeholder_Report items for future implementation. Generated reports support user-selectable Paper_Size, text pagination with sensible line and page breaks, and images that always render entirely within a single page.

## Glossary

- **Släktbusken**: The genealogy desktop application (the system under development; see the main application requirements for full data model details)
- **Project_Folder**: The folder structure containing a project's App_JSON file, settings, translation files, and media subfolders
- **App_JSON**: The application's internal gzipped JSON data format storing all genealogy data, including persons, families, events, places, sources, media, and DNA records
- **Person**: An individual genealogy record with names, sex, events, and a profile_media_id reference to a Media_Item
- **Place**: A geographical location record with a type (country, county, parish, church, cemetery, village, farm, or school), a parent_place_id forming a hierarchy, and optional latitude/longitude coordinates
- **Media_Item**: A record describing a file (photo, document, etc.) with a unique ID, a file field storing its relative path within the Project_Folder's media subfolders, and linked_entities describing which persons, events, sources, or places reference it
- **DNA_Company**: A DNA testing company record that may reference a Media_Item via a logo_media_id field
- **Diagram_Panel**: The panel in the main window that displays the currently active person in Family, Ancestry, or Descendants view
- **Report_Menu**: The top-level "Rapporter" menu in the application menu bar exposing all report categories and report items
- **Report_Category**: One of the five submenu groupings under the Report_Menu: Standardrapporter, DNA-rapporter, Konsistensrapporter, Forskningsrapporter, Exportkontroller
- **Ansedel_Report**: An implemented Standardrapporter report presenting a single Person's names, life events, parents, partners, and children as a printable document
- **Geographic_Consistency_Report**: An implemented Konsistensrapporter report that identifies Place hierarchy and coordinate data problems
- **Media_Consistency_Report**: An implemented Konsistensrapporter report that identifies orphaned, missing, and duplicate Media_Item file references
- **Placeholder_Report**: A report listed in the Report_Menu that is not yet implemented in this iteration
- **Report_Generator**: The module responsible for producing paginated, printable output from generated report content
- **Paper_Size**: A named physical page format (e.g., A4, A3, A5) selectable for generated report output
- **Report_Preview**: The on-screen window displaying the generated pages of a report before printing or exporting

## Requirements

### Requirement 1: Report Menu Structure and Navigation

**User Story:** As a researcher, I want a Reports menu with the full catalogue of planned reports organized by category, so that I can find and access both available and upcoming reports from one place.

#### Acceptance Criteria

1. THE Släktbusken SHALL provide a top-level Report_Menu labeled "Rapporter" in the main menu bar, containing five Report_Category submenus labeled "Standardrapporter", "DNA-rapporter", "Konsistensrapporter", "Forskningsrapporter", and "Exportkontroller"
2. THE Report_Menu SHALL list "Ansedel", "Antavla", and "Ättlingarapport" within the "Standardrapporter" Report_Category
3. THE Report_Menu SHALL list "DNA-matchlista", "Klusterrapport", and "Trianguleringsrapport" within the "DNA-rapporter" Report_Category
4. THE Report_Menu SHALL list "Geografisk konsistens", "Personkonsistens", "Familjekonsistens", "Mediakonsistens", and "Källkonsistens" within the "Konsistensrapporter" Report_Category
5. THE Report_Menu SHALL list "Öppna forskningsfrågor" and "Personer med saknade källor" within the "Forskningsrapporter" Report_Category
6. THE Report_Menu SHALL list "ArkivDigital-export" and "GEDCOM-export" within the "Exportkontroller" Report_Category
7. WHEN the user clicks the "Ansedel", "Geografisk konsistens", or "Mediakonsistens" menu item, THE Släktbusken SHALL start generation of the corresponding report
8. THE Report_Menu SHALL display each Placeholder_Report menu item in a disabled state
9. WHEN the user hovers the pointer over a disabled Placeholder_Report menu item, THE Släktbusken SHALL display a Swedish-language tooltip stating that the report is not yet implemented
10. IF no project is open, THEN THE Släktbusken SHALL display every Report_Menu item, including "Ansedel", "Geografisk konsistens", and "Mediakonsistens", in a disabled state
11. WHEN the user hovers the pointer over a disabled "Ansedel", "Geografisk konsistens", or "Mediakonsistens" menu item while no project is open, THE Släktbusken SHALL NOT display the Placeholder_Report tooltip defined in Acceptance Criterion 9

### Requirement 2: Ansedel Report Generation

**User Story:** As a researcher, I want to generate a standard Ansedel report for a person, so that I have a printable summary of that person's family and life events.

#### Acceptance Criteria

1. WHEN the user selects "Ansedel" from the Report_Menu, THE Släktbusken SHALL generate the Ansedel_Report for the active person shown in the Diagram_Panel
2. THE Ansedel_Report SHALL include the selected Person's names, sex, title, occupation, and profile photo where a profile_media_id is set on that Person
3. THE Ansedel_Report SHALL include, for each event linked to the selected Person, the event type, date, and place
4. THE Ansedel_Report SHALL include the selected Person's parents, partners, and children, showing each related person's name and relationship role
5. WHEN the selected Person has no recorded parents, no recorded partners, or no recorded children, THE Ansedel_Report SHALL display an explicit Swedish-language statement that no such data exists for that section rather than omitting the section
6. THE Släktbusken SHALL display the generated Ansedel_Report in a Report_Preview window before the report is printed or exported
7. IF no project is open or no active person is set in the Diagram_Panel, THEN THE Släktbusken SHALL display a Swedish-language message stating that a person must be selected and SHALL cancel Ansedel_Report generation

### Requirement 3: Geographic Consistency Report

**User Story:** As a researcher, I want a report that flags problems in the place hierarchy and missing coordinates, so that I can find and fix data quality issues in my geographic data.

#### Acceptance Criteria

1. WHEN the user selects "Geografisk konsistens" from the Report_Menu, THE Släktbusken SHALL generate the Geographic_Consistency_Report for all Place records in the open project
2. THE Geographic_Consistency_Report SHALL list every Place of type county whose parent_place_id ancestor chain does not include a Place of type country
3. THE Geographic_Consistency_Report SHALL list every Place of type parish whose parent_place_id ancestor chain does not include a Place of type county
4. THE Geographic_Consistency_Report SHALL list every Place of type church, cemetery, village, farm, or school whose parent_place_id ancestor chain does not include a Place of type parish
5. THE Geographic_Consistency_Report SHALL list every Place of type parish that has an unset latitude, an unset longitude, or both unset
6. THE Geographic_Consistency_Report SHALL present the results of the four checks defined in Acceptance Criteria 2 through 5 under four separately labeled sections, each listing the affected Place records by name and ID
7. WHEN one of the four checks defined in Acceptance Criteria 2 through 5 finds no matching Place records, THE Geographic_Consistency_Report SHALL display a Swedish-language statement that no issues were found for that section
8. IF the open project contains no Place records, THEN THE Geographic_Consistency_Report SHALL display a Swedish-language message stating that there are no places to check

### Requirement 4: Media Consistency Report

**User Story:** As a researcher, I want a report that flags unused, missing, and duplicate media files, so that I can keep my media library clean and complete.

#### Acceptance Criteria

1. WHEN the user selects "Mediakonsistens" from the Report_Menu, THE Släktbusken SHALL generate the Media_Consistency_Report for the open project
2. THE Media_Consistency_Report SHALL list every Media_Item that has no linked_entities entry, is not referenced by any Person's profile_media_id field, is not referenced in any Event's media_ids field, is not referenced in any Source's media_ids field, and is not referenced by any DNA_Company's logo_media_id field
3. THE Media_Consistency_Report SHALL list every file present within the Project_Folder's media subfolders whose relative path does not match the file field of any Media_Item
4. THE Media_Consistency_Report SHALL list every Media_Item whose file field does not correspond to an existing file within the Project_Folder's media subfolders
5. THE Media_Consistency_Report SHALL list every group of two or more Media_Item records that share an identical file field value
6. THE Media_Consistency_Report SHALL present the results of the four checks defined in Acceptance Criteria 2 through 5 under four separately labeled sections, each listing the affected Media_Item records by ID, title, or file path
7. WHEN the Media_Consistency_Report generates successfully and one of the four checks defined in Acceptance Criteria 2 through 5 finds no matching issues, THE Media_Consistency_Report SHALL display a Swedish-language statement that no issues were found for that section

### Requirement 5: Report Output, Paper Size, and Printing

**User Story:** As a researcher, I want to choose a paper size and print or export any generated report, so that the output fits my preferred paper format and can be shared or archived.

#### Acceptance Criteria

1. THE Släktbusken SHALL provide a Paper_Size selection control in the Report_Preview window offering at minimum A4, A3, and A5 formats
2. WHEN a report is generated, THE Släktbusken SHALL apply A4 as the default Paper_Size
3. WHEN the user changes the Paper_Size in the Report_Preview window, THE Report_Generator SHALL re-paginate the report content for the newly selected Paper_Size within 2 seconds
4. THE Släktbusken SHALL allow the user to print a generated report to any printer available on the operating system
5. THE Släktbusken SHALL allow the user to export a generated report to a PDF file at a location chosen by the user
6. THE Släktbusken SHALL persist the most recently selected Paper_Size in the project settings file, offering that Paper_Size as the default the next time a report is generated

### Requirement 6: Report Text Pagination and Line Breaking

**User Story:** As a researcher, I want report text to wrap and paginate cleanly, so that reports remain legible without broken words or awkwardly split sections.

#### Acceptance Criteria

1. THE Report_Generator SHALL break report text lines only at whitespace or hyphen boundaries, keeping every word intact on a single line
2. WHEN the content assigned to the current page fills the available page area, THE Report_Generator SHALL continue rendering the remaining content starting at the top of a new page
3. THE Report_Generator SHALL preserve the original paragraph, list, and section ordering of report content across page breaks
4. WHEN a labeled section of a report (such as an Ansedel_Report relationship section or a Geographic_Consistency_Report check section) does not fit entirely within the remaining space on the current page, or when the remaining space on the current page is insufficient to display the section heading together with at least one line of its content, THE Report_Generator SHALL begin that section at the top of the next page rather than separating its heading from its first line of content
5. THE Report_Generator SHALL display the current page number and the total page count on every page of a generated report

### Requirement 7: Image Page-Fit Handling

**User Story:** As a researcher, I want embedded images in reports to never be cut across a page break, so that photos remain fully visible and readable.

#### Acceptance Criteria

1. THE Report_Generator SHALL render every embedded image, including a Person's profile photo in the Ansedel_Report, entirely within the bounds of a single page
2. WHEN an embedded image does not fit within the remaining vertical space on the current page, THE Report_Generator SHALL move that entire image to the top of the next page
3. IF an embedded image is larger than the printable area of the selected Paper_Size, THEN THE Report_Generator SHALL scale the image down proportionally until the image fits within the printable area while preserving the image's aspect ratio
4. THE Report_Generator SHALL place any caption text describing an embedded image on the same page as that image

### Requirement 8: Placeholder Reports for Future Implementation

**User Story:** As a researcher, I want to see the full planned reports catalogue even before every report is implemented, so that I understand what capabilities are coming without being able to trigger unfinished features.

#### Acceptance Criteria

1. THE Släktbusken SHALL treat "Antavla", "Ättlingarapport", "DNA-matchlista", "Klusterrapport", "Trianguleringsrapport", "Personkonsistens", "Familjekonsistens", "Källkonsistens", "Öppna forskningsfrågor", "Personer med saknade källor", "ArkivDigital-export", and "GEDCOM-export" as Placeholder_Report entries in this iteration
2. THE Report_Menu SHALL disable each Placeholder_Report menu item so that the item cannot be activated by mouse click or keyboard
3. THE Report_Menu SHALL display each Placeholder_Report menu item in the same category position shown in Requirement 1, regardless of its disabled state
