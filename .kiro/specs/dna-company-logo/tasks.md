# Implementation Plan: DNA Company Logo Chooser

## Overview

This plan implements a visual logo chooser for DNA companies in the `DnaEditor`. The implementation proceeds incrementally: first adding pure helper functions with property tests, then building the UI components, and finally wiring everything together with the match list icon display.

## Tasks

- [x] 1. Add constants and helper functions for logo path logic
  - [x] 1.1 Create logo constants and pure helper functions
    - Add `LOGO_EXTENSIONS`, `LOGO_FILE_FILTER`, `LOGO_PREVIEW_SIZE`, `LOGO_ICON_SIZE` constants to `slaktbusken/ui/editors/dna_editor.py` (or a shared constants module if one exists)
    - Implement `_is_inside_logo_folder(file_path: Path, logo_folder: Path) -> bool` — case-insensitive check whether a path is under the logo folder
    - Implement `_compute_relative_path(file_path: Path, project_folder: Path) -> str` — returns forward-slash relative path
    - Implement `_unique_filename(folder: Path, name: str) -> Path` — generates a unique filename with numeric suffix if conflicts exist
    - Implement `_find_media_by_path(media_list: list[MediaItem], rel_path: str) -> MediaItem | None` — case-insensitive search
    - Implement `_create_logo_media_item(rel_path: str, filename: str) -> MediaItem` — creates a MediaItem with type="logo", correct file and title fields
    - _Requirements: 2.1, 2.2, 2.3, 3.4, 3.5, 3.6_

  - [x] 1.2 Write property test: Path classification correctness (Property 1)
    - **Property 1: Path classification correctness**
    - Test that `_is_inside_logo_folder` returns True iff the file path starts with the logo folder path (case-insensitive on Windows)
    - Use Hypothesis strategies for random path segments and nesting depths
    - **Validates: Requirements 2.1, 3.1**

  - [x] 1.3 Write property test: Relative path uses forward slashes (Property 2)
    - **Property 2: Relative path uses forward slashes**
    - Test that `_compute_relative_path` never produces backslash characters and equals the OS-relative path with separators replaced
    - Use Hypothesis strategies for random filenames with various characters
    - **Validates: Requirements 2.1**

  - [x] 1.4 Write property test: MediaItem field correctness (Property 3)
    - **Property 3: MediaItem field correctness**
    - Test that `_create_logo_media_item` produces items with `type == "logo"`, correct `file`, and `title` equal to the filename stem
    - Use Hypothesis strategies for random filenames with supported extensions
    - **Validates: Requirements 2.2, 3.5**

  - [x] 1.5 Write property test: Case-insensitive path deduplication (Property 4)
    - **Property 4: Case-insensitive path deduplication**
    - Test that `_find_media_by_path` returns an existing MediaItem when paths match case-insensitively, and None otherwise
    - Use Hypothesis strategies for random media lists and random case variations
    - **Validates: Requirements 2.3, 3.6, 4.2**

  - [x] 1.6 Write property test: Unique filename suffix generation (Property 5)
    - **Property 5: Unique filename suffix generation**
    - Test that `_unique_filename` returns a path that does not exist in the folder and has correct suffix numbering
    - Use Hypothesis strategies with `tmp_path` for random filenames and 0–20 pre-existing conflicts
    - **Validates: Requirements 3.4**

- [x] 2. Implement file copy logic and logo folder management
  - [x] 2.1 Implement `_copy_to_logo_folder` method
    - Add method to `DnaEditor` (or as a standalone utility function) that copies an external file to `media/logo/`
    - Handle logo folder creation if missing (Req 3.2)
    - Use `_unique_filename` for name conflicts (Req 3.4)
    - Preserve original filename when no conflict (Req 3.3)
    - Catch `OSError` and return `None` on failure (Req 3.7)
    - Log errors using existing logger
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.7_

  - [x] 2.2 Write unit tests for file copy logic
    - Test successful copy to new folder
    - Test folder creation when missing
    - Test unique filename generation on conflict
    - Test error handling returns None and logs
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.7_

- [x] 3. Checkpoint - Ensure helper logic is solid
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Add UI components to DnaEditor company form
  - [x] 4.1 Modify `DnaEditor.__init__` to accept `project_path` parameter
    - Add `project_path: Path | None = None` parameter to constructor
    - Store as `self._project_path`
    - Compute and store `self._project_folder` and `self._logo_folder` from project_path
    - _Requirements: 1.1, 1.6_

  - [x] 4.2 Add "Välj logo..." button and 64×64 preview label to company form
    - Create `_logo_choose_button = QPushButton("Välj logo...")` — disabled by default
    - Create `_logo_preview_label = QLabel()` with fixed 64×64 size policy
    - Insert widgets into the generated company form layout adjacent to the media-ID field
    - Connect `_logo_choose_button.clicked` to `_on_choose_logo`
    - Disable button when `project_path` is None
    - _Requirements: 1.1, 1.2, 5.3_

  - [x] 4.3 Implement `_update_logo_preview` method
    - Resolve current company's logo_media_id → MediaItem → file path → absolute path
    - Load image with `QPixmap`, scale to 64×64 preserving aspect ratio (`Qt.KeepAspectRatio`, `Qt.SmoothTransformation`)
    - Show empty placeholder when no logo assigned
    - Show distinct "missing image" indicator when file not found on disk
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 4.4 Write property test: Aspect-ratio-preserving scale (Property 6)
    - **Property 6: Aspect-ratio-preserving scale**
    - Test that scaling any (W, H) image to fit 64×64 preserves aspect ratio within ±1 pixel tolerance
    - Use Hypothesis strategies for random width/height pairs from 1–5000
    - **Validates: Requirements 5.1**

  - [x] 4.5 Hook company selection changes to update preview and button state
    - Connect `companies_list.currentItemChanged` to also call `_update_logo_preview`
    - Enable/disable `_logo_choose_button` based on whether a company is selected and project_path is available
    - _Requirements: 1.2, 5.2_

- [x] 5. Implement the logo chooser orchestration
  - [x] 5.1 Implement `_on_choose_logo` method
    - Ensure logo folder exists (create if needed) — Req 1.6
    - Open `QFileDialog.getOpenFileName` with `LOGO_FILE_FILTER`, initial dir = logo folder — Req 1.3, 1.4, 1.5
    - If user cancels, return without changes — Req 4.5
    - Determine if selected file is inside logo folder (`_is_inside_logo_folder`) — Req 2.1
    - If outside: call `_copy_to_logo_folder`, abort on error — Req 3.1, 3.7
    - Compute relative path (`_compute_relative_path`) — Req 2.1
    - Search for existing MediaItem (`_find_media_by_path`) — Req 2.3, 3.6, 4.2
    - If no existing item: create new MediaItem and append to `project_data.media` — Req 2.2, 3.5, 4.1
    - Set `company.logo_media_id` to the MediaItem ID — Req 2.4, 4.1, 4.4
    - Update text field display — Req 4.3
    - Update logo preview — Req 5.2
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 2.4, 3.1, 3.5, 3.6, 3.7, 4.1, 4.2, 4.3, 4.4, 4.5, 5.2_

  - [x] 5.2 Write unit tests for logo chooser orchestration
    - Test file dialog opens with correct filter and initial directory
    - Test cancel preserves state
    - Test selecting file in logo folder (no copy)
    - Test selecting external file triggers copy
    - Test deduplication reuses existing MediaItem
    - Test overwrite of existing logo_media_id
    - Test error on copy failure shows QMessageBox
    - _Requirements: 1.3, 1.4, 1.5, 2.1, 3.1, 4.3, 4.4, 4.5_

- [x] 6. Checkpoint - Ensure company form and chooser work
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Update DnaEditor instantiation in app.py
  - [x] 7.1 Pass `project_path` to DnaEditor in app.py
    - Locate the DnaEditor instantiation in `app.py`
    - Add `project_path=self.project_service.project_path` to the constructor call
    - _Requirements: 1.1_

- [x] 8. Add logo icons to DNA match list
  - [x] 8.1 Implement `resolve_company_logo_icon` helper function
    - Create a helper function (module-level or utility) that resolves the chain: DnaMatch → profile2 → company → logo_media_id → MediaItem → file → disk path → QIcon
    - Return scaled QIcon (24×24) or default placeholder when any link is missing
    - Return distinct "missing file" placeholder when file path resolves but file doesn't exist on disk
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 8.2 Write property test: Logo resolution chain (Property 7)
    - **Property 7: Logo resolution chain**
    - Test that the resolution function returns the correct file path when all chain links are valid, and None when any link is missing
    - Use Hypothesis strategies for random project data with varying chain completeness
    - **Validates: Requirements 6.1, 6.2, 6.3**

  - [x] 8.3 Integrate logo icons into match list display
    - Modify `DnaEditor._refresh_matches_list()` (or `DnaMatchDialog`) to call `resolve_company_logo_icon` for each match entry
    - Set the resolved QIcon on each list item at 24×24
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 8.4 Write unit tests for match list logo display
    - Test icon shown when logo exists
    - Test placeholder when no logo assigned
    - Test missing-file placeholder when file absent from disk
    - _Requirements: 6.1, 6.2, 6.3_

- [x] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- All tests use pytest with Hypothesis (already configured in the project)
- Test file for property tests: `tests/test_ui/test_dna_company_logo_properties.py`
- Test file for unit tests: `tests/test_ui/test_dna_company_logo.py`
- UI text is in Swedish, matching the existing application locale

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "1.5", "1.6", "2.1"] },
    { "id": 2, "tasks": ["2.2", "4.1"] },
    { "id": 3, "tasks": ["4.2", "4.3", "4.5"] },
    { "id": 4, "tasks": ["4.4", "5.1", "7.1"] },
    { "id": 5, "tasks": ["5.2", "8.1"] },
    { "id": 6, "tasks": ["8.2", "8.3"] },
    { "id": 7, "tasks": ["8.4"] }
  ]
}
```
