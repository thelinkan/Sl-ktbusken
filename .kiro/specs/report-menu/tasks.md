# Implementation Plan: Report Menu (Rapporter)

## Overview

This plan implements the "Rapporter" top-level menu for Släktbusken with five report categories, three fully implemented reports (Ansedel, Geographic Consistency, Media Consistency), a Report Preview window with paper size selection, pagination, printing, and PDF export. The implementation follows a bottom-up approach: content model first, then report logic, then pagination/rendering, then UI integration.

## Tasks

- [x] 1. Set up report content model and project settings extension
  - [x] 1.1 Create the report content data model
    - Create `slaktbusken/reports/__init__.py` and `slaktbusken/reports/content.py`
    - Define `ReportBlock`, `HeadingBlock`, `ParagraphBlock`, `ListBlock`, `ImageBlock`, `EmptyStateBlock`, and `ReportContent` dataclasses
    - _Requirements: 6.3_

  - [x] 1.2 Extend ProjectSettings with report_paper_size field
    - Add `report_paper_size: str = "A4"` field to `ProjectSettings` in `slaktbusken/persistence/settings_io.py`
    - Update `_deserialize_settings` to read the new field with `"A4"` as fallback for unrecognized values
    - Update `_serialize_settings` to include the new field
    - _Requirements: 5.2, 5.6_

  - [x] 1.3 Write property test for paper size persistence round-trip
    - **Property 9: Paper size persistence round-trip**
    - **Validates: Requirements 5.6**

- [x] 2. Implement Geographic Consistency report logic
  - [x] 2.1 Create geographic consistency module
    - Create `slaktbusken/reports/geographic.py`
    - Implement `GeoIssue` dataclass and `check_geographic_consistency(places)` function
    - Implement hierarchy checks: county→country, parish→county, sub-types→parish
    - Implement parish missing coordinates check
    - Implement `generate_geographic_report(data: ProjectData) -> ReportContent`
    - Include four labeled sections and Swedish "inga problem" messages when no issues found
    - Handle empty places list with Swedish "inga platser att kontrollera" message
    - Handle circular parent references by treating cycle as "ancestor not found"
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

  - [x] 2.2 Write property test for geographic hierarchy violation detection
    - **Property 2: Geographic hierarchy violation detection**
    - **Validates: Requirements 3.2, 3.3, 3.4**

  - [x] 2.3 Write property test for parish missing coordinates detection
    - **Property 3: Parish missing coordinates detection**
    - **Validates: Requirements 3.5**

  - [x] 2.4 Write property test for report section structure (geographic)
    - **Property 8: Report section structure** (geographic variant)
    - **Validates: Requirements 3.6**

- [x] 3. Implement Media Consistency report logic
  - [x] 3.1 Create media consistency module
    - Create `slaktbusken/reports/media_consistency.py`
    - Implement `MediaIssue` dataclass and `check_media_consistency(data, project_folder)` function
    - Implement four checks: orphaned media, unlinked files, missing files, duplicate references
    - Implement `generate_media_report(data: ProjectData, project_folder: Path) -> ReportContent`
    - Include four labeled sections and Swedish "inga problem" messages when no issues found
    - Handle inaccessible media subfolder with warning in results
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [x] 3.2 Write property test for orphaned media detection
    - **Property 4: Orphaned media detection**
    - **Validates: Requirements 4.2**

  - [x] 3.3 Write property test for unlinked file detection
    - **Property 5: Unlinked file detection**
    - **Validates: Requirements 4.3**

  - [x] 3.4 Write property test for missing file detection
    - **Property 6: Missing file detection**
    - **Validates: Requirements 4.4**

  - [x] 3.5 Write property test for duplicate media file detection
    - **Property 7: Duplicate media file detection**
    - **Validates: Requirements 4.5**

  - [x] 3.6 Write property test for report section structure (media)
    - **Property 8: Report section structure** (media variant)
    - **Validates: Requirements 4.6**

- [x] 4. Implement Ansedel report logic
  - [x] 4.1 Create ansedel report module
    - Create `slaktbusken/reports/ansedel.py`
    - Implement `generate_ansedel(data, person_id, project_folder) -> ReportContent`
    - Include person names, sex, title, occupation, and profile photo (as ImageBlock)
    - Include all linked events with type, date, and place
    - Include parents, partners, and children sections with names and relationship roles
    - Display Swedish "inga uppgifter" messages for empty relationship sections
    - Handle missing profile photo file gracefully (skip image, log warning)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 4.2 Write property test for Ansedel content completeness
    - **Property 1: Ansedel content completeness**
    - **Validates: Requirements 2.2, 2.3, 2.4**

- [x] 5. Implement Report Generator Service
  - [x] 5.1 Create report generator service
    - Create `slaktbusken/reports/generator.py`
    - Implement `ReportGeneratorService` class with methods: `generate_ansedel`, `generate_geographic_consistency`, `generate_media_consistency`
    - Each method delegates to the corresponding report module
    - _Requirements: 2.1, 3.1, 4.1_

- [ ] 6. Checkpoint - Verify report logic
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement Report Paginator
  - [x] 7.1 Create paginator with paper size support and line breaking
    - Create `slaktbusken/reports/paginator.py`
    - Implement `PageLayout`, `RenderedElement`, `RenderedPage` dataclasses
    - Define `PAPER_SIZES` dictionary with A4, A3, A5 dimensions
    - Implement `ReportPaginator.paginate(content, paper_size) -> list[RenderedPage]`
    - Implement line breaking at word/hyphen boundaries only
    - Implement page overflow: continue content on next page
    - Preserve block ordering across pages
    - Implement section-keep-together: heading must have at least one content line on same page
    - Implement image page-fit: move image to next page if it doesn't fit; scale down if larger than printable area while preserving aspect ratio
    - Ensure caption stays on same page as its image
    - Add page number and total page count to each RenderedPage
    - Handle corrupt/unreadable images with placeholder text "Bilden kunde inte laddas"
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3, 7.4_

  - [x] 7.2 Write property test for line breaking at word boundaries
    - **Property 10: Line breaking at word boundaries**
    - **Validates: Requirements 6.1**

  - [x] 7.3 Write property test for block ordering preserved across pages
    - **Property 11: Block ordering preserved across pages**
    - **Validates: Requirements 6.3**

  - [x] 7.4 Write property test for section heading never orphaned
    - **Property 12: Section heading never orphaned**
    - **Validates: Requirements 6.4**

  - [x] 7.5 Write property test for page numbering correctness
    - **Property 13: Page numbering correctness**
    - **Validates: Requirements 6.5**

  - [x] 7.6 Write property test for image fits single page
    - **Property 14: Image fits single page**
    - **Validates: Requirements 7.1, 7.2**

  - [x] 7.7 Write property test for image scaling preserves aspect ratio
    - **Property 15: Image scaling preserves aspect ratio**
    - **Validates: Requirements 7.3**

  - [x] 7.8 Write property test for caption on same page as image
    - **Property 16: Caption on same page as image**
    - **Validates: Requirements 7.4**

- [ ] 8. Checkpoint - Verify paginator
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement Report Preview window
  - [x] 9.1 Create Report Preview dialog
    - Create `slaktbusken/ui/dialogs/report_preview.py`
    - Implement `ReportPreviewDialog(QDialog)` with paper size combo box (A4, A3, A5)
    - Render paginated pages using QPainter on a scrollable widget
    - Add "Skriv ut" (Print) button that opens QPrintDialog and prints all pages
    - Add "Exportera PDF" (Export PDF) button that opens file dialog and writes PDF via QPrinter
    - On paper size change: re-paginate and re-render within 2 seconds, persist new size to settings
    - Show page number / total on each rendered page
    - Handle PDF export write failures with Swedish error dialog showing OS error details
    - Handle print dialog cancellation gracefully (no action)
    - Fall back to A4 if stored paper size is unrecognized
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 2.6_

  - [x] 9.2 Write unit tests for Report Preview dialog
    - Test paper size selection updates pagination
    - Test default paper size is A4 for new project
    - Test unrecognized paper size falls back to A4
    - _Requirements: 5.1, 5.2, 5.3, 5.6_

- [x] 10. Implement Report Menu and wire to application
  - [x] 10.1 Create Report Menu builder
    - Create `slaktbusken/ui/report_menu.py`
    - Implement `ReportMenuBuilder.build(menu_bar, app) -> QMenu`
    - Add "Rapporter" top-level menu with five submenus: Standardrapporter, DNA-rapporter, Konsistensrapporter, Forskningsrapporter, Exportkontroller
    - Add all menu items in correct categories per Requirements 1.2–1.6
    - Connect "Ansedel", "Geografisk konsistens", "Mediakonsistens" to generation callbacks
    - Disable all Placeholder_Report items with Swedish tooltip "Rapporten är inte implementerad ännu"
    - When no project is open: disable all items (including implemented ones) without placeholder tooltip
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 8.1, 8.2, 8.3_

  - [x] 10.2 Integrate Report Menu into MainWindow
    - Modify `slaktbusken/ui/main_window.py` to use `ReportMenuBuilder` to add the Rapporter menu
    - Wire report generation callbacks: trigger ReportGeneratorService, then open ReportPreviewDialog
    - For Ansedel: check active person exists, show Swedish error if not ("En person måste vara vald i diagrammet")
    - Update menu enabled state when project opens/closes
    - _Requirements: 1.7, 1.10, 2.1, 2.6, 2.7_

  - [x] 10.3 Write unit tests for Report Menu structure
    - Verify all 5 categories exist with correct labels
    - Verify all items are in correct submenus with correct labels
    - Verify placeholder items are disabled with tooltip
    - Verify implemented items are enabled when project is open
    - Verify all items disabled when no project is open
    - Verify implemented items have no placeholder tooltip when disabled due to no project
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 1.9, 1.10, 1.11_

- [ ] 11. Final checkpoint - Full integration
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The project uses Hypothesis for property-based testing with strategies defined in `tests/conftest.py`
- All report logic modules are pure functions producing `ReportContent`, keeping them testable without Qt dependencies
- The existing `ReportService` in `slaktbusken/services/report_service.py` handles GEDCOM import/export formatting — the new report system lives in `slaktbusken/reports/`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "2.1", "3.1", "4.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "3.2", "3.3", "3.4", "3.5", "3.6", "4.2", "5.1"] },
    { "id": 3, "tasks": ["7.1"] },
    { "id": 4, "tasks": ["7.2", "7.3", "7.4", "7.5", "7.6", "7.7", "7.8"] },
    { "id": 5, "tasks": ["9.1"] },
    { "id": 6, "tasks": ["9.2", "10.1"] },
    { "id": 7, "tasks": ["10.2"] },
    { "id": 8, "tasks": ["10.3"] }
  ]
}
```
