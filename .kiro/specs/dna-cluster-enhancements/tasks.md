# Implementation Plan: DNA Cluster Enhancements

## Overview

This plan implements enhancements to the DNA and cluster section of Släktbusken, a PySide6-based Swedish genealogy desktop application. The implementation proceeds from data model changes, through pure logic modules, to UI changes, new dialogs, and integration wiring. Python is the implementation language throughout.

## Tasks

- [ ] 1. Data model extensions and project infrastructure
  - [ ] 1.1 Extend DnaCompany, DnaProfile, and DnaMatch data models
    - Add `url: str = ""` field to `DnaCompany` (max 2048 chars)
    - Add `"combined"` to valid test_type values in `DnaProfile`
    - Add `y_haplogroup: str = ""` and `mt_haplogroup: str = ""` fields to `DnaProfile` (max 50 chars each)
    - Add `raw_data_file: Optional[str] = None` field to `DnaProfile`
    - Remove `admin_status` field from `DnaProfile`
    - Add `segment_file: Optional[str] = None` field to `DnaMatch` (max 255 chars)
    - Update serialization/deserialization logic for new/removed fields
    - _Requirements: 1.1, 1.6, 3.6, 4.5, 4.6, 11.6, 14.2_

  - [ ] 1.2 Implement dna/ subfolder file management utilities
    - Create utility functions to resolve `dna/` subfolder path relative to the project file
    - Implement `ensure_dna_folder_exists()` to create the subfolder if missing
    - Implement `write_dna_file(filename, data)` and `read_dna_file(filename)` for JSON I/O
    - Implement `delete_dna_file(filename)` for cleanup on match deletion
    - _Requirements: 14.6, 14.7, 11.9_

  - [ ] 1.3 Write property tests for haplogroup preservation and max length enforcement
    - **Property 1: Haplogroup preservation across test type changes**
    - **Property 2: Haplogroup max length enforcement**
    - **Validates: Requirements 1.7, 1.8**

  - [ ] 1.4 Write property test for segment data preservation round-trip
    - **Property 4: Segment data preservation round-trip**
    - **Validates: Requirements 5.3, 5.4**

- [ ] 2. Pure logic modules — parsing and formatting
  - [ ] 2.1 Implement relationship_lookup.py
    - Create `slaktbusken/services/relationship_lookup.py`
    - Define `RelationshipProbability` dataclass
    - Implement `get_relationship_probabilities(shared_cm)` function
    - Embed Shared cM Project v4.0 probability data as static lookup dictionary
    - _Requirements: 10.3, 10.4, 10.6, 10.7_

  - [ ] 2.2 Write property test for relationship probability consistency
    - **Property 6: Relationship probability consistency**
    - **Validates: Requirements 10.4, 10.6**

  - [ ] 2.3 Implement dna_raw_parser.py
    - Create `slaktbusken/services/dna_raw_parser.py`
    - Define `RawSnpRecord` and `ParseResult` dataclasses
    - Implement `detect_format(file_path)` for AncestryDNA and MyHeritage detection
    - Implement `parse_ancestrydna(file_path)` for tab-delimited files with # comments
    - Implement `parse_myheritage(file_path)` for CSV with quoted fields and ## headers
    - Implement `parse_raw_dna_file(file_path)` auto-detect wrapper
    - Handle 100 MB file size limit check
    - _Requirements: 11.2, 11.3, 11.4, 11.5, 11.12_

  - [ ] 2.4 Write property tests for raw DNA parsing
    - **Property 7: Raw DNA parsing produces valid records**
    - **Property 8: Raw DNA parse completeness**
    - **Validates: Requirements 11.2, 11.3, 11.5**

  - [ ] 2.5 Implement dna_match_csv_parser.py
    - Create `slaktbusken/services/dna_match_csv_parser.py`
    - Define `MatchSegmentRecord` and `MatchCsvParseResult` dataclasses
    - Implement `parse_match_csv(text)` for MyHeritage match CSV format
    - Handle header row detection, column validation, row skipping for invalid data
    - Extract match_name from the "Match Name" column
    - _Requirements: 13.1, 13.2, 13.7, 13.9_

  - [ ] 2.6 Write property tests for match CSV parsing
    - **Property 10: Match CSV parsing produces valid segments**
    - **Property 11: Match CSV parse completeness**
    - **Validates: Requirements 13.2, 13.9**

  - [ ] 2.7 Implement chromosome_data.py
    - Create `slaktbusken/services/chromosome_data.py`
    - Define `CHROMOSOME_LENGTHS` constant dictionary (GRCh37/hg19)
    - Implement `segment_relative_position(start, chrom)` function
    - Implement `segment_relative_width(start, end, chrom)` function
    - _Requirements: 15.3, 15.5, 15.6_

  - [ ] 2.8 Write property test for chromosome segment calculations
    - **Property 13: Chromosome segment position and width calculation**
    - **Validates: Requirements 15.3, 15.5, 15.6**

  - [ ] 2.9 Implement triangulation_format.py
    - Create `slaktbusken/services/triangulation_format.py`
    - Implement `format_triangulation_entry(triangulation, project_data)` function
    - Handle resolution chain: profile_id → DnaProfile → person_id → Person → name
    - Fall back to "(okänd)" for unresolvable names
    - _Requirements: 2.1, 2.2_

  - [ ] 2.10 Write property test for triangulation formatting
    - **Property 3: Triangulation format with unresolvable fallback**
    - **Validates: Requirements 2.1, 2.2**

  - [ ] 2.11 Implement match segment serialization/deserialization
    - Create functions to serialize `list[MatchSegmentRecord]` to JSON and deserialize back
    - Integrate with dna/ subfolder file utilities from task 1.2
    - _Requirements: 14.1, 14.3, 14.4_

  - [ ] 2.12 Write property test for match segment serialization round-trip
    - **Property 12: Match segment serialization round-trip**
    - **Validates: Requirements 14.3, 14.4**

- [ ] 3. Checkpoint — Data model and pure logic
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. UI changes — DNA Editor tabs and forms
  - [ ] 4.1 Remove Segment tab and reorder tabs in DnaEditor
    - Remove the Segment tab widget from the DnaEditor
    - Reorder remaining tabs: Företag, Profiler, Matchningar, Kluster, Triangulering
    - Verify tab indices (Kluster at index 3, Triangulering at index 4)
    - _Requirements: 5.1, 5.2, 6.1, 6.2, 6.3_

  - [ ] 4.2 Update DNA Profile form — test type, haplogroups, person display
    - Add "combined" to TEST_TYPES combo box
    - Add conditional haplogroup fields (y_haplogroup visible for y-dna/combined, mt_haplogroup visible for mtdna/combined, hidden for autosomal)
    - Set maxLength(50) on haplogroup fields
    - Replace editable person_id with read-only name label
    - Add Person_Search_Widget for admin_person_id
    - Remove admin_status combo box
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 1.8, 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ] 4.3 Update DNA Company form — URL field and logo chooser
    - Add URL QLineEdit with maxLength(2048)
    - Hide logo_media_id text field and label
    - Add "Välj logo..." button that opens QFileDialog filtered to image files
    - Add 64×64 logo preview (scaled maintaining aspect ratio)
    - Handle missing logo placeholder display
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.7_

  - [ ] 4.4 Redesign triangulation tab — list display and detail view
    - Update triangulation list entries to use `format_triangulation_entry()`
    - Add ellipsis truncation with full-text tooltip for long entries
    - Replace detail form with read-only labels (Företag, Delad cM, Antal segment, Största segment, Anteckningar, profiles list)
    - Add "Redigera" button that opens DnaTriangulationDialog in edit mode
    - Refresh detail view on dialog accept, no-op on cancel
    - _Requirements: 2.1, 2.2, 2.3, 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ] 4.5 Redesign cluster tab — split panel layout
    - Replace existing cluster tab content with horizontal splitter (30%/70%)
    - Left panel: scrollable QListWidget of clusters
    - Right panel upper: scrollable QListWidget of persons in selected cluster
    - Right panel lower: QTextEdit "Anteckningar" for cluster notes (min 3 lines height)
    - Handle cluster selection change: update persons + notes within 500ms
    - Auto-persist notes on cluster switch
    - Show empty state when no cluster selected (disabled notes area)
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [ ] 4.6 Implement cluster context menu with DNA match filter
    - Add context menu on person right-click with "Filtrera på DNA-träffar" action
    - Disable action if person has no DnaProfile
    - Implement filter logic: show only persons with DnaMatch linking their profile to the right-clicked person's profiles
    - Add "Visa filtrerade" toggle button to control filter state
    - Reset filter on cluster change
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [ ] 4.7 Write property test for cluster DNA match filter correctness
    - **Property 5: Cluster DNA match filter correctness**
    - **Validates: Requirements 9.3, 9.4**

- [ ] 5. Checkpoint — UI tab and form changes
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. New dialogs — Relationship graph, DNA viewer, Chromosome browser
  - [ ] 6.1 Create Person_Search_Widget
    - Create `slaktbusken/ui/widgets/person_search_widget.py`
    - Implement QWidget with QLineEdit + QCompleter for person search by name
    - Emit signal on person selection/deselection
    - Support clearing selection (null value)
    - _Requirements: 4.3, 4.4_

  - [ ] 6.2 Implement RelationshipGraphDialog
    - Create `slaktbusken/ui/dialogs/relationship_graph_dialog.py`
    - Render horizontal bar chart with relationship types (Y-axis) and probabilities (X-axis)
    - Use QPainter or matplotlib FigureCanvasQTAgg for bar chart rendering
    - Display attribution text for The Shared cM Project by Blaine T. Bettinger
    - Show "no data" message for 0 cM or out-of-range values
    - _Requirements: 10.1, 10.2, 10.3, 10.5, 10.6, 10.7_

  - [ ] 6.3 Implement DnaViewerDialog with virtual scrolling
    - Create `slaktbusken/ui/dialogs/dna_viewer_dialog.py`
    - Create custom QAbstractTableModel for lazy data loading (up to 1M rows)
    - Implement table with columns: rsID, Kromosom, Position, Alleler
    - Add search field (maxLength 100) for case-insensitive substring filtering
    - Add chromosome filter dropdown ("Alla" + individual chromosomes from data)
    - Combine both filters, update within 500ms
    - Handle missing data file with error message
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

  - [ ] 6.4 Write property test for DNA viewer filter correctness
    - **Property 9: DNA viewer combined filter correctness**
    - **Validates: Requirements 12.3, 12.5**

  - [ ] 6.5 Implement ChromosomeBrowserDialog
    - Create `slaktbusken/ui/dialogs/chromosome_browser_dialog.py`
    - Render 22 autosomal chromosome bars + optional X bar using QPainter
    - Scale bar widths proportionally to GRCh37/hg19 lengths
    - Draw colored segment rectangles at correct positions using chromosome_data.py
    - Show inline cM label when segment ≥40px wide, tooltip always
    - Show summary header: match person name, total shared cM, total segments
    - Handle "(okänd)" fallback for unresolvable person names
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7, 15.8, 15.9, 15.10, 15.11, 15.12_

  - [ ] 6.6 Write property test for chromosome browser total cM
    - **Property 14: Chromosome browser total cM equals segment sum**
    - **Validates: Requirements 15.11**

- [ ] 7. Checkpoint — Dialogs and widgets
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Data import workflows and integration
  - [ ] 8.1 Integrate raw DNA import into DnaProfileDialog
    - Add import control (button + file dialog) to the profile edit dialog
    - Filter file dialog to TXT/CSV
    - Show progress indicator during parsing
    - Store parsed data as JSON in dna/ subfolder with filename `raw_{profile_id}.json`
    - Update `DnaProfile.raw_data_file` field on success
    - Handle reuse of existing raw data files for same person's profiles
    - Handle replace/remove existing file association
    - Enforce 100 MB file size limit
    - Display appropriate error messages for unrecognized format or partial failures
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.7, 11.8, 11.9, 11.12_

  - [ ] 8.2 Add "DNA-visare" button to person editor DNA section
    - Show "DNA-visare" button next to "Redigera" for profiles with raw_data_file set
    - Hide button when raw_data_file is None
    - Connect button click to open DnaViewerDialog with loaded data
    - _Requirements: 11.10, 11.11, 12.1_

  - [ ] 8.3 Integrate match CSV paste into DnaMatchDialog
    - Add "Klistra in matchdata" text area to the match dialog (between Anteckningar and Välj profiler)
    - Parse pasted MyHeritage match CSV data on text change/button click
    - Show segment preview table (chromosome, start, end, cM) and total shared cM
    - Suggest Profile 2 based on match name person search
    - Handle "no matching person" warning with user confirmation
    - Store segments in dna/ subfolder as `match_segments_{match_id}.json`
    - Handle replace confirmation for existing segment data
    - Show error for unrecognized format with expected column format
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8, 13.9_

  - [ ] 8.4 Write property test for person name matching for CSV match import
    - **Property 15: Person name matching for CSV match import**
    - **Validates: Requirements 13.4**

  - [ ] 8.5 Wire Relationship_Graph button in person editor DNA matches section
    - Add "Relationsdiagram" button to person editor DNA matches section
    - Disable when no match selected
    - Open RelationshipGraphDialog with selected match's shared_cm value on click
    - _Requirements: 10.1, 10.2_

  - [ ] 8.6 Wire Chromosome_Browser button for match segment viewing
    - Add "Kromosomvy" button to match detail view
    - Disable when match has no segment data loaded
    - Open ChromosomeBrowserDialog with loaded segments on click
    - _Requirements: 15.1, 15.2_

  - [ ] 8.7 Implement match deletion with segment file cleanup
    - When a DnaMatch with a non-null segment_file is deleted, delete the segment file from dna/
    - Handle missing segment file gracefully (log warning, continue deletion)
    - _Requirements: 14.8_

  - [ ] 8.8 Handle missing segment file on project load
    - When loading a DnaMatch with segment_file reference, attempt to read the file
    - If file missing/unreadable: log warning, load match without segments, show visual warning indicator
    - _Requirements: 14.5_

- [ ] 9. Final checkpoint — Full integration
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The implementation language is Python (PySide6) throughout
- Pure logic modules (tasks 2.x) have no Qt dependencies and are independently testable
- External DNA files are stored in a `dna/` subfolder to keep the main project JSON small

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4", "2.1", "2.3", "2.5", "2.7", "2.9"] },
    { "id": 2, "tasks": ["2.2", "2.4", "2.6", "2.8", "2.10", "2.11"] },
    { "id": 3, "tasks": ["2.12", "4.1", "6.1"] },
    { "id": 4, "tasks": ["4.2", "4.3", "4.4", "4.5"] },
    { "id": 5, "tasks": ["4.6", "4.7", "6.2", "6.3", "6.5"] },
    { "id": 6, "tasks": ["6.4", "6.6", "8.1", "8.5", "8.6", "8.7", "8.8"] },
    { "id": 7, "tasks": ["8.2", "8.3"] },
    { "id": 8, "tasks": ["8.4"] }
  ]
}
```
