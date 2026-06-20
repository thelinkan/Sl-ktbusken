# Implementation Plan: Personlista Enhancements

## Overview

This plan implements enhancements to the `PersonListPanel` in stages: first extending the data model and pure logic (testable without Qt), then building the UI layer (column headers, dot indicators, DNA icons, multiple-names indicator), then adding filtering improvements, column visibility settings, reduced width/compact mode, and finally bidirectional selection synchronization with the `DiagramPanel`.

## Tasks

- [-] 1. Extend data model and display info construction
  - [x] 1.1 Extend `PersonDisplayInfo` dataclass with new fields
    - Add `occupation: str`, `cluster_names_display: str`, `dna_company_ids: list[str]`, `name_count: int`, `all_names: list[tuple[str, str, str]]`, `is_ancestor: bool`, `is_descendant: bool` fields
    - Ensure defaults for backward compatibility
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 4.1, 4.2, 7.1, 7.2_

  - [x] 1.2 Update `build_person_display_list()` to populate new fields
    - Accept new parameters: `dna_profiles`, `dna_companies`, `ancestor_ids`, `descendant_ids`
    - Populate `occupation` from `Person.occupation` (empty string if None)
    - Populate `cluster_names_display` as comma-separated sorted cluster names
    - Populate `dna_company_ids` with distinct company IDs (sorted by name, max 5)
    - Populate `name_count` and `all_names` from all Name records
    - Set `is_ancestor`/`is_descendant` from provided sets (False for main person itself)
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 3.1, 3.2, 4.1, 4.2, 4.8, 7.1, 7.2_

  - [~] 1.3 Write property tests for display info construction
    - **Property 1: Person field propagation to display info**
    - **Property 2: Cluster names display construction**
    - **Property 3: DNA company ID collection**
    - **Property 4: Lineage flag correctness**
    - **Property 10: Name count and all_names accuracy**
    - **Validates: Requirements 1.3, 1.4, 1.5, 1.6, 3.1, 3.2, 4.1, 4.2, 4.8, 7.1, 7.2**

- [x] 2. Implement column visibility settings
  - [x] 2.1 Create `ColumnVisibility` dataclass and extend `AppSettings`
    - Add `ColumnVisibility` dataclass with `titel`, `yrke`, `kluster`, `dna_company` boolean fields (all default True)
    - Add `column_visibility` field to `AppSettings`
    - Ensure JSON serialization/deserialization handles the new field
    - Handle missing/corrupt settings gracefully (fall back to all-visible defaults)
    - _Requirements: 2.2, 2.4, 2.6, 2.7_

  - [x] 2.2 Write property test for column visibility round-trip persistence
    - **Property 5: Column visibility round-trip persistence**
    - **Validates: Requirements 2.4**

- [~] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement name filtering across all name versions
  - [x] 4.1 Update `filter_persons()` to support multi-name filtering
    - Accept `all_persons_names: dict[str, list[Name]]` parameter
    - Given name filter: match against all Name records' given field, stripping asterisk markers
    - Surname filter: match against all Name records' surname field
    - Case-insensitive substring matching for both
    - Combined given+surname: person included if any Name satisfies given AND any Name satisfies surname (independently)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 4.2 Update `filter_persons()` to support cluster filter
    - Filter persons by cluster membership using case-insensitive substring match on cluster names
    - Combine with other filter criteria using AND logic
    - Empty cluster filter removes the cluster restriction
    - _Requirements: 5.2, 5.3_

  - [x] 4.3 Write property tests for name and cluster filtering
    - **Property 6: Multi-name given name filter**
    - **Property 7: Multi-name surname filter**
    - **Property 8: Combined given and surname filter independence**
    - **Property 9: Cluster filter AND logic**
    - **Validates: Requirements 5.2, 5.3, 6.1, 6.2, 6.3, 6.4, 6.5**

- [~] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement column header and visibility UI
  - [x] 6.1 Build column header widget for `PersonListPanel`
    - Create `_build_column_header()` method returning a QWidget with labels for each column
    - Column layout: gender icon (16px), dot (16px), name (flexible), Titel (60px min), Yrke (80px min), Kluster (80px min), DNA company (90px min)
    - Always-visible columns: gender icon, dot, name, birth–death years
    - Configurable columns: Titel, Yrke, Kluster, DNA company
    - _Requirements: 1.1, 1.2, 2.5_

  - [x] 6.2 Implement column header context menu for visibility toggling
    - Add `_show_column_visibility_menu()` triggered by right-clicking the column header
    - Menu lists configurable columns with checkboxes indicating visibility state
    - Toggle shows/hides column immediately
    - Persist changes via `AppSettingsService`
    - Restore saved visibility on startup
    - _Requirements: 2.1, 2.3, 2.4, 2.6_

- [x] 7. Implement row rendering with new columns and indicators
  - [x] 7.1 Implement ancestry/descendancy dot indicators in row widget
    - Display Ancestor_Dot (8px, #C0392B red) when `is_ancestor` is True
    - Display Descendant_Dot (8px, #27AE60 green) when `is_descendant` is True
    - Both dots shown (ancestor left, descendant right) when both are True
    - No dots when neither flag is set
    - Positioned between gender icon and name
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 7.2 Implement lineage computation and caching
    - Add `_compute_lineage_sets()` to `PersonListPanel` that computes ancestor/descendant sets from `main_person_id`
    - Cache sets on the panel instance
    - Recompute when `main_person_id` changes
    - No dots when main person not set
    - Handle cycles gracefully (terminate BFS on revisited person)
    - _Requirements: 4.6, 4.7, 4.9_

  - [x] 7.3 Implement DNA company icons in row widget
    - Resolve icons from `DnaCompany.logo_media_id` → `MediaItem.file` → project folder path
    - Scale to 16×16 pixels
    - Display side-by-side, max 5 icons sorted alphabetically by company name
    - Show placeholder icon (16×16) when logo not found or `logo_media_id` is None
    - Show tooltip with company name on hover
    - Empty cell when person has no DNA profiles
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x] 7.4 Implement Titel, Yrke, Kluster columns in row widget
    - Display `title` field in Titel column (empty cell when None/empty)
    - Display `occupation` field in Yrke column (empty cell when None/empty)
    - Display `cluster_names_display` in Kluster column (empty cell when no clusters)
    - Truncate with ellipsis when text exceeds column width
    - Show full value in tooltip on hover
    - Respect column visibility settings (hide/show based on `ColumnVisibility`)
    - _Requirements: 1.3, 1.4, 1.5, 1.7_

  - [x] 7.5 Implement multiple names indicator
    - Display indicator (e.g., "²") immediately to the right of name text when `name_count > 1`
    - Show tooltip on hover listing all names: one line per name as "type: given surname" (omit empty components)
    - No indicator when person has exactly one Name record
    - Visually distinct from dots and DNA icons (no circle/square shape)
    - Hide tooltip on mouse leave
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 7.6 Write property test for multiple names tooltip format
    - **Property 11: Multiple names tooltip format**
    - **Validates: Requirements 7.2**

- [ ] 8. Implement cluster filter in Filter Dialog
  - [~] 8.1 Add cluster filter field to `FilterDialog`
    - Add text field with case-insensitive substring-matching autocomplete
    - Populate autocomplete from all DNA cluster names in the project
    - Show empty autocomplete list when project has no clusters
    - Clearing the field removes the cluster restriction
    - _Requirements: 5.1, 5.3, 5.4_

- [~] 9. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Implement reduced width and compact mode
  - [~] 10.1 Configure splitter for reduced `PersonListPanel` width
    - Set initial splitter sizes to [250, remaining] at startup
    - Set minimum width of `PersonListPanel` to 250px
    - Allow manual resize up to max 50% of window width
    - _Requirements: 8.1, 8.2, 8.3_

  - [~] 10.2 Implement compact column layout mode
    - When panel width < 350px: truncate column headers to max 4 chars + ellipsis, reduce cell padding to 2px
    - When panel width ≥ 350px: full headers, default padding 6px
    - Respond to resize events to switch modes dynamically
    - _Requirements: 8.4, 8.5_

  - [~] 10.3 Write property test for compact mode threshold
    - **Property 12: Compact mode threshold**
    - **Validates: Requirements 8.4, 8.5**

- [ ] 11. Implement bidirectional selection synchronization
  - [~] 11.1 Implement `select_person_from_diagram()` method
    - Select and scroll to person without emitting `person_selected` signal
    - Use signal blocking or guard flag to prevent circular loops
    - If person not in filtered view: switch to unfiltered view, update toggle button state, then select
    - If person_id not found in full list: clear selection, do not change view
    - _Requirements: 9.1, 9.2, 9.3, 9.5_

  - [~] 11.2 Wire `DiagramPanel.person_activated` signal to `PersonListPanel`
    - Connect signal in `MainWindow._setup_central_widget()` or equivalent
    - Preserve existing single-click → `person_selected` behavior
    - _Requirements: 9.1, 9.4_

  - [~] 11.3 Write property tests for bidirectional sync
    - **Property 13: Diagram sync does not emit person_selected**
    - **Property 14: Diagram sync switches to unfiltered view when person not in filter**
    - **Validates: Requirements 9.2, 9.3**

- [~] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The project uses PySide6, Hypothesis (≥6.90.0), and pytest
- Pure logic functions (`build_person_display_list`, `filter_persons`, `ColumnVisibility` serialization) can be tested without Qt
- Property test file: `tests/test_ui/test_personlista_enhancements_properties.py`
- Unit test file: `tests/test_ui/test_personlista_enhancements_unit.py`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1"] },
    { "id": 1, "tasks": ["1.2", "2.2"] },
    { "id": 2, "tasks": ["1.3", "4.1", "4.2"] },
    { "id": 3, "tasks": ["4.3", "6.1"] },
    { "id": 4, "tasks": ["6.2", "7.1", "7.2", "7.3", "7.4", "7.5", "8.1"] },
    { "id": 5, "tasks": ["7.6", "10.1", "10.2"] },
    { "id": 6, "tasks": ["10.3", "11.1"] },
    { "id": 7, "tasks": ["11.2", "11.3"] }
  ]
}
```
