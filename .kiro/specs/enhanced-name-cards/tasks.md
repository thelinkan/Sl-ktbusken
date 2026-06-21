# Implementation Plan: Enhanced Name Cards

## Overview

Extend the `PersonBoxItem` widget and supporting layers to render richer person cards with: wider layout (240px), multiple-names indicator, DNA company logos, main person orange border, profile photo thumbnail, birth/death place fields, cause of death, and DNA cluster names. All changes target the rendering layer (`person_box.py`), configuration (`PersonBoxConfig`), view renderers, and icon registry.

## Tasks

- [ ] 1. Update PersonBoxConfig and card width constant
  - [ ] 1.1 Add new config fields and update box width
    - Add `cause_of_death: bool = False` and `clusters: bool = False` fields to the `PersonBoxConfig` dataclass in `slaktbusken/persistence/settings_io.py`
    - Update `_BOX_WIDTH` constant from 180.0 to 240.0 in `slaktbusken/ui/widgets/person_box.py`
    - Add all new constants: `_MAIN_PERSON_BORDER_COLOR`, `_PHOTO_SIZE`, `_PHOTO_GAP`, `_DNA_LOGO_SIZE`, `_MULTIPLE_NAMES_ICON_SIZE`, `_MAX_DNA_LOGOS`, `_MAX_CLUSTERS`, `_CAUSE_OF_DEATH_MAX_LEN`
    - _Requirements: 8.1, 8.4, 6.3, 7.5_

  - [ ] 1.2 Write unit tests for PersonBoxConfig new fields
    - Verify `cause_of_death` defaults to False
    - Verify `clusters` defaults to False
    - Verify `_BOX_WIDTH` is 240.0
    - _Requirements: 6.3, 7.5, 8.1_

- [ ] 2. Implement multiple names indicator
  - [ ] 2.1 Add multiple names icon to IconRegistry
    - Create SVG asset at `icons/misc/multiple_names.svg`
    - Add `get_multiple_names_icon() -> QPixmap` method to `IconRegistry` returning a 14×14 pixmap
    - _Requirements: 1.1, 1.2_

  - [ ] 2.2 Implement `_paint_multiple_names_icon` in PersonBoxItem
    - Draw the 14×14 icon at coordinates (`_PADDING / 2`, `_PADDING / 2`) when `display_data["has_multiple_names"]` is True
    - Ensure the icon does not overlap the name text line or gender icon
    - Do not draw anything when `has_multiple_names` is False
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ] 2.3 Write property test for multiple names indicator (Property 1)
    - **Property 1: Multiple names indicator biconditional**
    - Generate persons with varying name counts (1, 2, 10+)
    - Verify indicator is drawn iff `len(names) > 1`
    - **Validates: Requirements 1.1, 1.3**

  - [ ] 2.4 Write property test for config-independence (Property 2)
    - **Property 2: Multiple names indicator is config-independent**
    - Generate all combinations of PersonBoxConfig toggles with persons having multiple names
    - Verify indicator is always rendered regardless of config state
    - **Validates: Requirements 1.4**

- [ ] 3. Implement main person orange border
  - [ ] 3.1 Implement border color priority logic in PersonBoxItem
    - Add `is_main_person` check to the border color selection logic in `paint()`
    - Implement priority chain: selected (blue, 2.5px) > main person (orange, 2.5px) > ancestor (red, 2.0px) > descendant (green, 2.0px) > default (gray, 1.0px)
    - Use `_MAIN_PERSON_BORDER_COLOR = QColor(0xF3, 0x9C, 0x12)` for the orange border
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ] 3.2 Write property test for border color precedence (Property 6)
    - **Property 6: Border color precedence chain**
    - Generate all boolean combinations of (is_selected, is_main_person, is_ancestor, is_descendant)
    - Verify the correct border color and width is applied per the priority chain
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4**

- [ ] 4. Implement profile photo display
  - [ ] 4.1 Implement `_paint_profile_photo` in PersonBoxItem
    - Draw the 40×40 thumbnail on the left side with top edge at 8.0px from card top
    - Scale source image to fit 40×40 preserving aspect ratio, centered within the area
    - When `profile_photo` is not None, offset all text content by 48px to the right
    - When `profile_photo` is None, do not reserve space and use normal left padding
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.6_

  - [ ] 4.2 Write property test for text x-offset (Property 7)
    - **Property 7: Photo presence determines text x-offset**
    - Generate combinations of photo enabled/disabled and photo present/None
    - Verify text starts at correct x position in each case
    - **Validates: Requirements 4.1, 4.2, 4.3**

  - [ ] 4.3 Write property test for photo scaling (Property 8)
    - **Property 8: Photo scaling preserves aspect ratio within bounds**
    - Generate random image dimensions (w, h) where w > 0 and h > 0
    - Verify scaled dimensions satisfy: sw ≤ 40, sh ≤ 40, and sw/sh ≈ w/h
    - **Validates: Requirements 4.6**

- [ ] 5. Checkpoint - Verify core visual elements
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Implement birth/death place display
  - [ ] 6.1 Add place line rendering in PersonBoxItem paint logic
    - Render birth_place on the line immediately following birth_date, prefixed with a place label
    - Render death_place on the line immediately following death_date, prefixed with a place label
    - Omit place lines when data is None or empty string without reserving vertical space
    - Truncate place text with ellipsis using `QFontMetrics.elidedText()` when exceeding available width
    - _Requirements: 5.1, 5.2, 5.3, 5.5_

  - [ ] 6.2 Write property test for place line ordering (Property 9)
    - **Property 9: Place lines appear in correct order relative to date lines**
    - Generate persons with various combinations of birth/death date and place
    - Verify birth_place immediately follows birth_date; death_place immediately follows death_date
    - **Validates: Requirements 5.1, 5.2, 5.3**

  - [ ] 6.3 Write property test for place text truncation (Property 10)
    - **Property 10: Place text truncation at available width**
    - Generate place strings of varying lengths including very long strings (>500 chars)
    - Verify truncated text ends with "…" and fits within content area
    - **Validates: Requirements 5.5**

- [ ] 7. Implement cause of death display
  - [ ] 7.1 Add cause of death line rendering in PersonBoxItem
    - When config `cause_of_death` is enabled and value is non-empty, display the text
    - Truncate to 50 characters + "…" if original exceeds 50 characters
    - Do not display when config is disabled or value is empty/None
    - _Requirements: 6.1, 6.2, 6.4_

  - [ ] 7.2 Write property test for cause of death display and truncation (Property 11)
    - **Property 11: Cause of death display and truncation**
    - Generate cause_of_death strings of varying lengths (0, 1, 50, 51, 500+) and config toggle states
    - Verify correct display/hide behavior and truncation logic
    - **Validates: Requirements 6.1, 6.2, 6.4**

- [ ] 8. Implement DNA company logos
  - [ ] 8.1 Add DNA company logo loading to IconRegistry
    - Implement `get_dna_company_logo(media_id, media_loader) -> QPixmap | None` method
    - Scale loaded logos to 16×16 pixels
    - Return None if media cannot be loaded
    - _Requirements: 2.3, 2.4_

  - [ ] 8.2 Implement `_paint_dna_logos` in PersonBoxItem
    - Draw up to 5 company logos (16×16) horizontally in the bottom-right corner
    - Order logos alphabetically by company name, left to right
    - For companies without a logo, render first 2 characters as text placeholder at 16×16
    - Only render when `dna_info` config toggle is enabled
    - Do not render anything when no DNA profiles exist
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ] 8.3 Write property test for DNA logo count (Property 3)
    - **Property 3: DNA logo count matches profile count gated by config**
    - Generate persons with 0, 1, 5, 6, 10 DNA profiles and varying dna_info toggle
    - Verify rendered logo count equals min(N, 5) when enabled, 0 when disabled
    - **Validates: Requirements 2.1, 2.5, 2.6**

  - [ ] 8.4 Write property test for DNA logo ordering (Property 4)
    - **Property 4: DNA logos are ordered alphabetically**
    - Generate sets of DNA companies with random names
    - Verify logos are rendered left-to-right in alphabetical order by company name
    - **Validates: Requirements 2.2**

  - [ ] 8.5 Write property test for DNA text placeholder (Property 5)
    - **Property 5: DNA company text placeholder uses first 2 characters**
    - Generate DNA companies with no logo_media_id and various name strings
    - Verify text placeholder is exactly the first 2 characters of company name
    - **Validates: Requirements 2.4**

- [ ] 9. Implement cluster display
  - [ ] 9.1 Implement `_paint_cluster_lines` in PersonBoxItem
    - Display cluster names as separate text entries in alphabetical order
    - Render each cluster name in its `color` when set, or default label color when None
    - Show maximum 5 cluster names; append overflow indicator with remaining count when > 5
    - Only render when `clusters` config toggle is enabled
    - Do not render anything when person belongs to no clusters
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [ ] 9.2 Write property test for cluster sorting and cap (Property 12)
    - **Property 12: Cluster display sorted and capped**
    - Generate persons belonging to 0, 1, 5, 6, 20 clusters with config enabled
    - Verify alphabetical order and min(N, 5) display count
    - **Validates: Requirements 7.1, 7.4**

  - [ ] 9.3 Write property test for cluster text color (Property 13)
    - **Property 13: Cluster text color matches cluster color property**
    - Generate clusters with and without color property set
    - Verify text color is cluster color when set, default when None
    - **Validates: Requirements 7.2, 7.3**

  - [ ] 9.4 Write property test for cluster overflow indicator (Property 14)
    - **Property 14: Cluster overflow indicator**
    - Generate persons with more than 5 clusters
    - Verify exactly 5 names displayed plus indicator showing remaining count (N - 5)
    - **Validates: Requirements 7.6**

- [ ] 10. Checkpoint - Verify all field rendering
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. Update view renderers to build extended display_data
  - [ ] 11.1 Update FamilyView display_data construction
    - Add `is_main_person` by comparing person ID to `project.project.main_person_id`
    - Add `has_multiple_names` by checking `len(person.names) > 1`
    - Load profile photo via media loader, scale to 40×40 preserving aspect ratio
    - Build `dna_companies` list from DnaProfile records, resolve logos, sort alphabetically
    - Build `clusters` list from DnaCluster records where person is a member, sort alphabetically, cap at 5 with overflow
    - Extract `cause_of_death` from death Event
    - Populate `birth_place` and `death_place` from birth/death events
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.1, 5.2, 6.1, 7.1, 8.4_

  - [ ] 11.2 Update AncestryView display_data construction
    - Apply the same display_data extensions as FamilyView (same fields, same logic)
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.1, 5.2, 6.1, 7.1, 8.4_

  - [ ] 11.3 Update DescendantsView display_data construction
    - Apply the same display_data extensions as FamilyView (same fields, same logic)
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.1, 5.2, 6.1, 7.1, 8.4_

  - [ ] 11.4 Write integration tests for view renderer display_data
    - Create ProjectData with persons having DNA profiles, clusters, events, and media
    - Verify each view renderer produces correct display_data dictionary structure
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.1, 6.1, 7.1_

- [ ] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design (Properties 1–14)
- Unit tests validate specific examples and edge cases
- The project uses Python with PyQt/PySide and Hypothesis for property-based testing
- All rendering changes are in `PersonBoxItem.paint()` sub-methods
- View renderers (Family, Ancestry, Descendants) prepare display_data identically

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "3.1"] },
    { "id": 2, "tasks": ["2.2", "3.2", "4.1"] },
    { "id": 3, "tasks": ["2.3", "2.4", "4.2", "4.3"] },
    { "id": 4, "tasks": ["6.1", "7.1", "8.1"] },
    { "id": 5, "tasks": ["6.2", "6.3", "7.2", "8.2"] },
    { "id": 6, "tasks": ["8.3", "8.4", "8.5", "9.1"] },
    { "id": 7, "tasks": ["9.2", "9.3", "9.4"] },
    { "id": 8, "tasks": ["11.1"] },
    { "id": 9, "tasks": ["11.2", "11.3"] },
    { "id": 10, "tasks": ["11.4"] }
  ]
}
```
