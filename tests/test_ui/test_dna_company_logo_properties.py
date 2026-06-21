"""Property-based tests for DNA company logo chooser.

Feature: dna-company-logo

Tests correctness properties for the logo path logic and MediaItem creation.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from hypothesis import assume, given, settings, HealthCheck
from hypothesis import strategies as st

from slaktbusken.model.media import MediaItem
from slaktbusken.ui.editors.dna_editor import (
    _compute_relative_path,
    _create_logo_media_item,
    _find_media_by_path,
    _is_inside_logo_folder,
    _unique_filename,
    LOGO_EXTENSIONS,
    LOGO_PREVIEW_SIZE,
)


# Strategy: generate a valid filename stem (non-empty, no path separators or dots)
_filename_stem_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "S"),
        blacklist_characters="/\\.\x00",
    ),
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip() == s and len(s.strip()) > 0)

# Strategy: pick a random supported extension
_extension_strategy = st.sampled_from(LOGO_EXTENSIONS)


@st.composite
def _logo_filename_strategy(draw: st.DrawFn) -> str:
    """Generate a random filename with a supported logo extension."""
    stem = draw(_filename_stem_strategy)
    ext = draw(_extension_strategy)
    return f"{stem}.{ext}"


# Windows reserved device names — cannot be used as file/directory names
_WINDOWS_RESERVED_NAMES = frozenset(
    name.upper()
    for name in (
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{i}" for i in range(10)),
        *(f"LPT{i}" for i in range(10)),
    )
)

# Strategy for safe filename characters (no path separators, no null bytes)
_safe_filename_chars = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "S"),
        blacklist_characters="\\/:\x00*?\"<>|",
    ),
    min_size=1,
    max_size=20,
).filter(lambda s: s.strip() not in ("", ".", "..") and s.split(".")[0].upper() not in _WINDOWS_RESERVED_NAMES)

# Strategy for directory segment names
_dir_segment = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        blacklist_characters="\\/:\x00*?\"<>|",
    ),
    min_size=1,
    max_size=10,
).filter(lambda s: s.strip() not in ("", ".", "..") and s.upper() not in _WINDOWS_RESERVED_NAMES)


# ---------------------------------------------------------------------------
# Strategies for Property 1: Path classification correctness
# ---------------------------------------------------------------------------

# ASCII-safe path segments for path classification tests — avoids Unicode
# case-folding asymmetries (e.g. µ→Μ→μ) that don't reflect real filesystem usage.
_ascii_path_segment_p1 = st.text(
    alphabet=st.sampled_from(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    ),
    min_size=1,
    max_size=15,
)


@st.composite
def _logo_folder_path(draw: st.DrawFn) -> Path:
    """Generate a random absolute logo folder path."""
    segments = draw(st.lists(_ascii_path_segment_p1, min_size=1, max_size=4))
    if sys.platform == "win32":
        root = "C:\\"
    else:
        root = "/"
    return Path(root).joinpath(*segments)


@st.composite
def _file_inside_folder(draw: st.DrawFn, folder: Path) -> Path:
    """Generate a file path that is inside the given folder at random depth."""
    extra_segments = draw(st.lists(_ascii_path_segment_p1, min_size=1, max_size=4))
    extension = draw(st.sampled_from([".png", ".jpg", ".jpeg", ".gif", ".svg"]))
    filename = draw(_ascii_path_segment_p1) + extension
    return folder.joinpath(*extra_segments, filename)


@st.composite
def _file_outside_folder(draw: st.DrawFn, folder: Path) -> Path:
    """Generate a file path that is NOT inside the given folder."""
    parent = folder.parent
    # Generate a segment that differs from the folder name
    different_segment = draw(_ascii_path_segment_p1)
    assume(different_segment.lower() != folder.name.lower())

    extra_segments = draw(st.lists(_ascii_path_segment_p1, min_size=0, max_size=3))
    extension = draw(st.sampled_from([".png", ".jpg", ".jpeg", ".gif", ".svg"]))
    filename = draw(_ascii_path_segment_p1) + extension
    return parent.joinpath(different_segment, *extra_segments, filename)


# ---------------------------------------------------------------------------
# Feature: dna-company-logo, Property 1: Path classification correctness
# ---------------------------------------------------------------------------


class TestPathClassificationCorrectness:
    """Feature: dna-company-logo, Property 1: Path classification correctness

    For any absolute file path and any project logo folder path, the
    "is inside logo folder" check SHALL return True if and only if the
    file path starts with (is relative to) the logo folder path,
    regardless of case on Windows.

    **Validates: Requirements 2.1, 3.1**
    """

    @given(data=st.data())
    @settings(max_examples=100)
    def test_file_inside_logo_folder_returns_true(self, data: st.DataObject) -> None:
        """A file located inside the logo folder SHALL be classified as inside.

        # Feature: dna-company-logo, Property 1: Path classification correctness
        **Validates: Requirements 2.1, 3.1**
        """
        folder = data.draw(_logo_folder_path(), label="logo_folder")
        file_path = data.draw(_file_inside_folder(folder), label="file_path")

        result = _is_inside_logo_folder(file_path, folder)

        assert result is True, (
            f"Expected _is_inside_logo_folder to return True for file "
            f"'{file_path}' inside folder '{folder}', but got False."
        )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_file_outside_logo_folder_returns_false(self, data: st.DataObject) -> None:
        """A file NOT located inside the logo folder SHALL be classified as outside.

        # Feature: dna-company-logo, Property 1: Path classification correctness
        **Validates: Requirements 2.1, 3.1**
        """
        folder = data.draw(_logo_folder_path(), label="logo_folder")
        file_path = data.draw(_file_outside_folder(folder), label="file_path")

        result = _is_inside_logo_folder(file_path, folder)

        assert result is False, (
            f"Expected _is_inside_logo_folder to return False for file "
            f"'{file_path}' outside folder '{folder}', but got True."
        )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_case_variations_match_on_windows(self, data: st.DataObject) -> None:
        """Case variations in file paths SHALL still be classified correctly
        (case-insensitive comparison).

        # Feature: dna-company-logo, Property 1: Path classification correctness
        **Validates: Requirements 2.1, 3.1**
        """
        folder = data.draw(_logo_folder_path(), label="logo_folder")
        file_path = data.draw(_file_inside_folder(folder), label="file_path")

        # Apply random case transformation to the file path string
        file_str = str(file_path)
        case_choice = data.draw(
            st.sampled_from(["upper", "lower", "swapcase"]),
            label="case_transform",
        )
        if case_choice == "upper":
            transformed = file_str.upper()
        elif case_choice == "lower":
            transformed = file_str.lower()
        else:
            transformed = file_str.swapcase()

        transformed_path = Path(transformed)

        result = _is_inside_logo_folder(transformed_path, folder)

        assert result is True, (
            f"Expected _is_inside_logo_folder to return True for case-varied "
            f"path '{transformed_path}' inside folder '{folder}', but got False. "
            f"Case transformation: {case_choice}"
        )


# ---------------------------------------------------------------------------
# Feature: dna-company-logo, Property 3: MediaItem field correctness
# ---------------------------------------------------------------------------


class TestMediaItemFieldCorrectness:
    """Feature: dna-company-logo, Property 3: MediaItem field correctness

    For any valid image filename (with a supported extension), creating a
    MediaItem for that file SHALL produce an item with type == "logo",
    file equal to the forward-slash relative path, and title equal to
    the filename stem (without the final extension).

    **Validates: Requirements 2.2, 3.5**
    """

    @given(filename=_logo_filename_strategy())
    @settings(max_examples=100)
    def test_media_item_type_is_logo(self, filename: str) -> None:
        """The created MediaItem SHALL always have type == 'logo'.

        # Feature: dna-company-logo, Property 3: MediaItem field correctness
        **Validates: Requirements 2.2, 3.5**
        """
        rel_path = f"media/logo/{filename}"
        item = _create_logo_media_item(rel_path, filename)

        assert item.type == "logo", (
            f"Expected item.type == 'logo', got '{item.type}' "
            f"for filename '{filename}'"
        )

    @given(filename=_logo_filename_strategy())
    @settings(max_examples=100)
    def test_media_item_file_equals_rel_path(self, filename: str) -> None:
        """The created MediaItem SHALL have file equal to the provided rel_path.

        # Feature: dna-company-logo, Property 3: MediaItem field correctness
        **Validates: Requirements 2.2, 3.5**
        """
        rel_path = f"media/logo/{filename}"
        item = _create_logo_media_item(rel_path, filename)

        assert item.file == rel_path, (
            f"Expected item.file == '{rel_path}', got '{item.file}' "
            f"for filename '{filename}'"
        )

    @given(filename=_logo_filename_strategy())
    @settings(max_examples=100)
    def test_media_item_title_equals_filename_stem(self, filename: str) -> None:
        """The created MediaItem SHALL have title equal to Path(filename).stem.

        # Feature: dna-company-logo, Property 3: MediaItem field correctness
        **Validates: Requirements 2.2, 3.5**
        """
        rel_path = f"media/logo/{filename}"
        item = _create_logo_media_item(rel_path, filename)

        expected_title = Path(filename).stem
        assert item.title == expected_title, (
            f"Expected item.title == '{expected_title}', got '{item.title}' "
            f"for filename '{filename}'"
        )

    @given(filename=_logo_filename_strategy())
    @settings(max_examples=100)
    def test_media_item_id_is_valid_uuid4(self, filename: str) -> None:
        """The created MediaItem SHALL have an id that is a valid UUID4 string.

        # Feature: dna-company-logo, Property 3: MediaItem field correctness
        **Validates: Requirements 2.2, 3.5**
        """
        rel_path = f"media/logo/{filename}"
        item = _create_logo_media_item(rel_path, filename)

        # Validate that the id is a valid UUID4
        parsed = uuid.UUID(item.id)
        assert parsed.version == 4, (
            f"Expected item.id to be a valid UUID4, got version {parsed.version} "
            f"for id '{item.id}'"
        )


# ---------------------------------------------------------------------------
# Feature: dna-company-logo, Property 2: Relative path uses forward slashes
# ---------------------------------------------------------------------------


class TestRelativePathForwardSlashes:
    """Feature: dna-company-logo, Property 2: Relative path uses forward slashes

    For any absolute file path located within the project folder, computing
    the relative path SHALL produce a string that contains no backslash
    characters and is equal to the OS-relative path with separators replaced
    by forward slashes.

    **Validates: Requirements 2.1**
    """

    @given(
        dir_segments=st.lists(_dir_segment, min_size=1, max_size=4),
        filename=_safe_filename_chars,
    )
    @settings(max_examples=100)
    def test_relative_path_never_contains_backslash(
        self, dir_segments: list[str], filename: str
    ) -> None:
        """The computed relative path SHALL never contain backslash characters.

        # Feature: dna-company-logo, Property 2: Relative path uses forward slashes
        **Validates: Requirements 2.1**
        """
        import tempfile
        import shutil

        tmp_dir = Path(tempfile.mkdtemp())
        try:
            # Build a nested directory structure
            project_folder = tmp_dir / "project"
            nested = project_folder
            for seg in dir_segments:
                nested = nested / seg
            nested.mkdir(parents=True, exist_ok=True)

            # Create the file
            file_path = nested / filename
            file_path.touch()

            # Compute the relative path
            result = _compute_relative_path(file_path, project_folder)

            # Assert no backslash in result
            assert "\\" not in result, (
                f"Relative path contains backslash: {result!r}"
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @given(
        dir_segments=st.lists(_dir_segment, min_size=1, max_size=4),
        filename=_safe_filename_chars,
    )
    @settings(max_examples=100)
    def test_relative_path_equals_os_relpath_with_forward_slashes(
        self, dir_segments: list[str], filename: str
    ) -> None:
        """The computed relative path SHALL equal os.path.relpath with
        separators replaced by forward slashes.

        # Feature: dna-company-logo, Property 2: Relative path uses forward slashes
        **Validates: Requirements 2.1**
        """
        import tempfile
        import shutil

        tmp_dir = Path(tempfile.mkdtemp())
        try:
            # Build a nested directory structure
            project_folder = tmp_dir / "project"
            nested = project_folder
            for seg in dir_segments:
                nested = nested / seg
            nested.mkdir(parents=True, exist_ok=True)

            # Create the file
            file_path = nested / filename
            file_path.touch()

            # Compute the relative path using the function under test
            result = _compute_relative_path(file_path, project_folder)

            # Compute expected via os.path.relpath with forward slashes
            expected = os.path.relpath(
                str(file_path.resolve()), str(project_folder.resolve())
            ).replace("\\", "/")

            assert result == expected, (
                f"Expected {expected!r} but got {result!r}"
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Strategies for Property 5: Unique filename suffix generation
# ---------------------------------------------------------------------------

# Strategy for safe filename stems (letters, digits, underscore, hyphen only)
_safe_stem_strategy = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789_-"),
    min_size=1,
    max_size=20,
)

# Strategy for common file extensions used in unique filename tests
_unique_ext_strategy = st.sampled_from(
    [".png", ".jpg", ".jpeg", ".gif", ".svg", ".bmp", ".webp"]
)

# Strategy for conflict count (0 to 20)
_conflict_count_strategy = st.integers(min_value=0, max_value=20)


# ---------------------------------------------------------------------------
# Feature: dna-company-logo, Property 5: Unique filename suffix generation
# ---------------------------------------------------------------------------


class TestUniqueFilenameSuffixGeneration:
    """Feature: dna-company-logo, Property 5: Unique filename suffix generation

    Test that `_unique_filename` returns a path that does not exist in the
    folder and has correct suffix numbering for any random filename and
    0-20 pre-existing conflicts.

    Since Hypothesis doesn't support function-scoped fixtures (tmp_path) well,
    each test creates a unique subdirectory per invocation to avoid state leaking
    between generated inputs.

    **Validates: Requirements 3.4**
    """

    _call_counter: int = 0

    def _make_unique_dir(self, tmp_path: Path) -> Path:
        """Create a unique subdirectory inside tmp_path for each invocation."""
        TestUniqueFilenameSuffixGeneration._call_counter += 1
        subdir = tmp_path / f"run_{TestUniqueFilenameSuffixGeneration._call_counter}"
        subdir.mkdir(parents=True, exist_ok=True)
        return subdir

    @given(
        stem=_safe_stem_strategy,
        ext=_unique_ext_strategy,
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_no_conflicts_returns_original_path(
        self, stem: str, ext: str, tmp_path: Path
    ) -> None:
        """If no conflicts exist, returned path equals folder / name.

        # Feature: dna-company-logo, Property 5: Unique filename suffix generation
        **Validates: Requirements 3.4**
        """
        folder = self._make_unique_dir(tmp_path)
        name = f"{stem}{ext}"
        # No pre-existing files - should return original name
        result = _unique_filename(folder, name)
        assert result == folder / name

    @given(
        stem=_safe_stem_strategy,
        ext=_unique_ext_strategy,
        conflict_count=st.integers(min_value=1, max_value=20),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_with_conflicts_returned_path_does_not_exist(
        self, stem: str, ext: str, conflict_count: int, tmp_path: Path
    ) -> None:
        """If N conflicts exist (original + _1 through _N-1), the returned
        path does not exist on the filesystem.

        # Feature: dna-company-logo, Property 5: Unique filename suffix generation
        **Validates: Requirements 3.4**
        """
        folder = self._make_unique_dir(tmp_path)
        name = f"{stem}{ext}"

        # Create the original file
        (folder / name).touch()

        # Create conflict files _1 through _(conflict_count - 1)
        for i in range(1, conflict_count):
            (folder / f"{stem}_{i}{ext}").touch()

        result = _unique_filename(folder, name)
        assert not result.exists(), (
            f"Expected unique filename but {result} already exists "
            f"(conflict_count={conflict_count})"
        )

    @given(
        stem=_safe_stem_strategy,
        ext=_unique_ext_strategy,
        conflict_count=_conflict_count_strategy,
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_returned_path_has_correct_extension(
        self, stem: str, ext: str, conflict_count: int, tmp_path: Path
    ) -> None:
        """The returned path always has the correct extension matching the
        original filename.

        # Feature: dna-company-logo, Property 5: Unique filename suffix generation
        **Validates: Requirements 3.4**
        """
        folder = self._make_unique_dir(tmp_path)
        name = f"{stem}{ext}"

        # Create conflict files if needed
        if conflict_count > 0:
            (folder / name).touch()
            for i in range(1, conflict_count):
                (folder / f"{stem}_{i}{ext}").touch()

        result = _unique_filename(folder, name)
        assert result.suffix == ext, (
            f"Expected extension '{ext}' but got '{result.suffix}' "
            f"for result path '{result}'"
        )

    @given(
        stem=_safe_stem_strategy,
        ext=_unique_ext_strategy,
        conflict_count=_conflict_count_strategy,
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_returned_path_is_inside_target_folder(
        self, stem: str, ext: str, conflict_count: int, tmp_path: Path
    ) -> None:
        """The returned path is always inside the target folder.

        # Feature: dna-company-logo, Property 5: Unique filename suffix generation
        **Validates: Requirements 3.4**
        """
        folder = self._make_unique_dir(tmp_path)
        name = f"{stem}{ext}"

        # Create conflict files if needed
        if conflict_count > 0:
            (folder / name).touch()
            for i in range(1, conflict_count):
                (folder / f"{stem}_{i}{ext}").touch()

        result = _unique_filename(folder, name)
        assert result.parent == folder, (
            f"Expected returned path parent to be '{folder}' "
            f"but got '{result.parent}'"
        )


# ---------------------------------------------------------------------------
# Strategies for Property 4: Case-insensitive path deduplication
# ---------------------------------------------------------------------------

# ASCII-only path characters (letters and digits) - reflects real filesystem
# paths where case-insensitive comparison with .lower() is reliable
_ascii_path_char = st.sampled_from(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
)

_ascii_path_segment = st.text(alphabet=_ascii_path_char, min_size=1, max_size=12)


@st.composite
def _ascii_relative_path_strategy(draw: st.DrawFn) -> str:
    """Generate a relative file path with forward slashes and ASCII chars."""
    segments = draw(st.lists(_ascii_path_segment, min_size=1, max_size=4))
    ext = draw(st.sampled_from([".png", ".jpg", ".jpeg", ".gif", ".svg"]))
    return "/".join(segments) + ext


@st.composite
def _media_item_with_ascii_path(draw: st.DrawFn) -> MediaItem:
    """Generate a minimal MediaItem with an ASCII file path."""
    mid = draw(st.integers(min_value=1, max_value=9999).map(lambda n: f"media_{n}"))
    file_path = draw(_ascii_relative_path_strategy())
    title = draw(st.text(alphabet=_ascii_path_char, min_size=1, max_size=20))
    return MediaItem(id=mid, type="logo", file=file_path, title=title)


def _randomize_char_case(draw: st.DrawFn, s: str) -> str:
    """Randomly change the case of each ASCII letter in *s*."""
    chars = []
    for ch in s:
        if ch.isascii() and ch.isalpha():
            make_upper = draw(st.booleans())
            chars.append(ch.upper() if make_upper else ch.lower())
        else:
            chars.append(ch)
    return "".join(chars)


# ---------------------------------------------------------------------------
# Feature: dna-company-logo, Property 4: Case-insensitive path deduplication
# ---------------------------------------------------------------------------


class TestCaseInsensitivePathDeduplication:
    """Feature: dna-company-logo, Property 4: Case-insensitive path deduplication

    For any list of existing MediaItems and any new relative file path,
    if there exists a MediaItem whose file field matches the new path
    case-insensitively, then _find_media_by_path SHALL return that existing
    MediaItem. If no match exists, it SHALL return None.

    **Validates: Requirements 2.3, 3.6, 4.2**
    """

    @given(
        media_list=st.lists(_media_item_with_ascii_path(), min_size=1, max_size=10),
        data=st.data(),
    )
    @settings(max_examples=100)
    def test_finds_existing_item_with_case_variation(
        self,
        media_list: list[MediaItem],
        data: st.DataObject,
    ) -> None:
        """Given a media list containing an item with path P, searching with
        a random case variation of P returns that item.

        # Feature: dna-company-logo, Property 4: Case-insensitive path deduplication
        **Validates: Requirements 2.3, 3.6, 4.2**
        """
        # Pick one item from the list to target
        target_index = data.draw(
            st.integers(min_value=0, max_value=len(media_list) - 1),
            label="target_index",
        )
        target_item = media_list[target_index]

        # Generate a case-varied version of the target's file path
        varied_path = _randomize_char_case(data.draw, target_item.file)

        # The function should find the target (or another item with same
        # lower-cased path, which is also correct)
        result = _find_media_by_path(media_list, varied_path)

        assert result is not None, (
            f"Expected to find a MediaItem for path '{varied_path}' "
            f"(variation of '{target_item.file}') but got None."
        )
        # The returned item's file should match case-insensitively
        assert result.file.lower() == varied_path.lower(), (
            f"Returned item file '{result.file}' does not match "
            f"search path '{varied_path}' case-insensitively."
        )

    @given(
        media_list=st.lists(_media_item_with_ascii_path(), min_size=0, max_size=10),
        search_path=_ascii_relative_path_strategy(),
    )
    @settings(max_examples=100)
    def test_returns_none_when_no_case_insensitive_match(
        self,
        media_list: list[MediaItem],
        search_path: str,
    ) -> None:
        """Given a media list, searching with a path that doesn't match any
        item (even case-insensitively) returns None.

        # Feature: dna-company-logo, Property 4: Case-insensitive path deduplication
        **Validates: Requirements 2.3, 3.6, 4.2**
        """
        # Ensure the search_path doesn't accidentally match any item
        # by appending a unique suffix that won't appear in generated paths
        non_matching_path = search_path + "__NOMATCH__"

        result = _find_media_by_path(media_list, non_matching_path)

        assert result is None, (
            f"Expected None for path '{non_matching_path}' but got "
            f"MediaItem(id='{result.id}', file='{result.file}')."
        )


# ---------------------------------------------------------------------------
# Strategies for Property 6: Aspect-ratio-preserving scale
# ---------------------------------------------------------------------------


@st.composite
def _image_dimensions(draw: st.DrawFn) -> tuple[int, int]:
    """Generate random image dimensions (width, height) from 1 to 5000."""
    w = draw(st.integers(min_value=1, max_value=5000))
    h = draw(st.integers(min_value=1, max_value=5000))
    return (w, h)


def _compute_scaled_size(w: int, h: int, box: int) -> tuple[int, int]:
    """Compute the scaled dimensions to fit within a box while preserving aspect ratio.

    This mirrors the logic Qt uses with Qt.KeepAspectRatio:
    - If both dimensions already fit, return unchanged.
    - Otherwise, scale down so the larger dimension becomes `box`, and the
      other dimension is proportionally reduced (rounded to nearest int, min 1).
    """
    if w <= box and h <= box:
        return (w, h)
    if w >= h:
        new_w = box
        new_h = max(1, round(h * box / w))
    else:
        new_h = box
        new_w = max(1, round(w * box / h))
    return (new_w, new_h)


# ---------------------------------------------------------------------------
# Feature: dna-company-logo, Property 6: Aspect-ratio-preserving scale
# ---------------------------------------------------------------------------


class TestAspectRatioPreservingScale:
    """Feature: dna-company-logo, Property 6: Aspect-ratio-preserving scale

    For any image with positive width W and height H, scaling to fit within a
    64×64 bounding box SHALL produce dimensions (w, h) such that:
    - w <= 64 and h <= 64
    - max(w, h) == 64 (unless the original is already smaller in both dimensions)
    - w/h is approximately equal to W/H (within rounding tolerance of ±1 pixel)

    **Validates: Requirements 5.1**
    """

    @given(dims=_image_dimensions())
    @settings(max_examples=200)
    def test_scaled_dimensions_fit_within_bounding_box(
        self, dims: tuple[int, int]
    ) -> None:
        """Scaled dimensions SHALL fit within 64×64.

        # Feature: dna-company-logo, Property 6: Aspect-ratio-preserving scale
        **Validates: Requirements 5.1**
        """
        w, h = dims
        box = LOGO_PREVIEW_SIZE  # 64

        new_w, new_h = _compute_scaled_size(w, h, box)

        assert new_w <= box, (
            f"Scaled width {new_w} exceeds bounding box {box} "
            f"for original ({w}, {h})"
        )
        assert new_h <= box, (
            f"Scaled height {new_h} exceeds bounding box {box} "
            f"for original ({w}, {h})"
        )

    @given(dims=_image_dimensions())
    @settings(max_examples=200)
    def test_at_least_one_dimension_equals_box_when_larger(
        self, dims: tuple[int, int]
    ) -> None:
        """At least one scaled dimension SHALL equal 64 when the original
        exceeds the bounding box in at least one dimension.

        # Feature: dna-company-logo, Property 6: Aspect-ratio-preserving scale
        **Validates: Requirements 5.1**
        """
        w, h = dims
        box = LOGO_PREVIEW_SIZE  # 64

        new_w, new_h = _compute_scaled_size(w, h, box)

        if w > box or h > box:
            assert max(new_w, new_h) == box, (
                f"Expected max({new_w}, {new_h}) == {box} for original "
                f"({w}, {h}) which exceeds the bounding box"
            )
        else:
            # If original fits within box, dimensions remain unchanged
            assert (new_w, new_h) == (w, h), (
                f"Expected unchanged ({w}, {h}) but got ({new_w}, {new_h}) "
                f"for original that fits within {box}×{box}"
            )

    @given(dims=_image_dimensions())
    @settings(max_examples=200)
    def test_aspect_ratio_preserved_within_tolerance(
        self, dims: tuple[int, int]
    ) -> None:
        """The aspect ratio SHALL be preserved within ±1 pixel rounding tolerance.

        Uses cross-multiplication to avoid floating-point division:
        |new_w * h - new_h * w| <= max(w, h)

        # Feature: dna-company-logo, Property 6: Aspect-ratio-preserving scale
        **Validates: Requirements 5.1**
        """
        w, h = dims
        box = LOGO_PREVIEW_SIZE  # 64

        new_w, new_h = _compute_scaled_size(w, h, box)

        # Cross-multiplication check avoids floating-point issues
        # The tolerance is max(w, h) which accounts for the rounding of 1 pixel
        # in the scaled dimensions
        cross_diff = abs(new_w * h - new_h * w)
        tolerance = max(w, h)

        assert cross_diff <= tolerance, (
            f"Aspect ratio not preserved: original ({w}, {h}) -> "
            f"scaled ({new_w}, {new_h}). "
            f"|{new_w}*{h} - {new_h}*{w}| = {cross_diff} > {tolerance}"
        )

# ---------------------------------------------------------------------------
# Strategies for Property 7: Logo resolution chain
# ---------------------------------------------------------------------------

from slaktbusken.model.dna import DnaMatch, DnaProfile, DnaCompany
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.ui.editors.dna_editor import _resolve_logo_file_path, _LOGO_FILE_MISSING


# Strategy: random ID strings (simple uuid-like identifiers)
_id_strategy = st.uuids().map(str)


@st.composite
def _complete_chain_data(draw: st.DrawFn) -> tuple[DnaMatch, ProjectData, str]:
    """Generate a complete resolution chain: match → profile → company → media.

    Returns (DnaMatch, ProjectData, relative_file_path).
    The caller is responsible for creating the actual file on disk.
    """
    # Generate unique IDs for each entity
    profile_id = draw(_id_strategy)
    company_id = draw(_id_strategy)
    media_id = draw(_id_strategy)
    match_id = draw(_id_strategy)
    person_id = draw(_id_strategy)

    # Generate a relative file path (simple, safe characters)
    rel_file = draw(
        st.text(
            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789"),
            min_size=1,
            max_size=12,
        ).map(lambda s: f"media/logo/{s}.png")
    )

    # Build the chain entities
    match = DnaMatch(
        id=match_id,
        profile1_id=draw(_id_strategy),
        profile2_id=profile_id,
    )
    profile = DnaProfile(
        id=profile_id,
        person_id=person_id,
        company_id=company_id,
        test_type="autosomal",
    )
    company = DnaCompany(
        id=company_id,
        name="TestCompany",
        logo_media_id=media_id,
    )
    media_item = MediaItem(
        id=media_id,
        type="logo",
        file=rel_file,
        title="logo",
    )

    project_data = ProjectData(
        project=ProjectMetadata(title="Test"),
        dna_profiles=[profile],
        dna_companies=[company],
        media=[media_item],
    )

    return match, project_data, rel_file


# ---------------------------------------------------------------------------
# Feature: dna-company-logo, Property 7: Logo resolution chain
# ---------------------------------------------------------------------------


class TestLogoResolutionChain:
    """Feature: dna-company-logo, Property 7: Logo resolution chain

    Test that the resolution function returns the correct file path when all
    chain links are valid, and None when any link is missing.

    **Validates: Requirements 6.1, 6.2, 6.3**
    """

    @given(data=st.data())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_returns_path_when_all_links_valid(
        self, data: st.DataObject, tmp_path: Path
    ) -> None:
        """When the full chain is valid and the file exists on disk, returns a Path.

        # Feature: dna-company-logo, Property 7: Logo resolution chain
        **Validates: Requirements 6.1, 6.2, 6.3**
        """
        match, project_data, rel_file = data.draw(
            _complete_chain_data(), label="chain"
        )

        # Create the file on disk
        abs_file = tmp_path / rel_file
        abs_file.parent.mkdir(parents=True, exist_ok=True)
        abs_file.touch()

        result = _resolve_logo_file_path(match, project_data, tmp_path)

        assert isinstance(result, Path), (
            f"Expected a Path when all chain links are valid and file exists, "
            f"got {type(result).__name__}: {result!r}"
        )
        assert result == abs_file

    @given(
        match_id=_id_strategy,
        profile1_id=_id_strategy,
        profile2_id=_id_strategy,
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_returns_none_when_profile_missing(
        self, match_id: str, profile1_id: str, profile2_id: str, tmp_path: Path
    ) -> None:
        """When no DnaProfile matches profile2_id, returns None.

        # Feature: dna-company-logo, Property 7: Logo resolution chain
        **Validates: Requirements 6.1, 6.2, 6.3**
        """
        match = DnaMatch(id=match_id, profile1_id=profile1_id, profile2_id=profile2_id)
        # Empty project data — no profiles at all
        project_data = ProjectData(project=ProjectMetadata(title="Test"))

        result = _resolve_logo_file_path(match, project_data, tmp_path)

        assert result is None, (
            f"Expected None when profile is missing, got {result!r}"
        )

    @given(data=st.data())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_returns_none_when_company_missing(
        self, data: st.DataObject, tmp_path: Path
    ) -> None:
        """When the DnaProfile exists but no DnaCompany matches, returns None.

        # Feature: dna-company-logo, Property 7: Logo resolution chain
        **Validates: Requirements 6.1, 6.2, 6.3**
        """
        profile_id = data.draw(_id_strategy, label="profile_id")
        company_id = data.draw(_id_strategy, label="company_id")
        match_id = data.draw(_id_strategy, label="match_id")

        match = DnaMatch(
            id=match_id,
            profile1_id=data.draw(_id_strategy),
            profile2_id=profile_id,
        )
        profile = DnaProfile(
            id=profile_id,
            person_id=data.draw(_id_strategy),
            company_id=company_id,
            test_type="autosomal",
        )
        # Project has the profile but NO companies
        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_profiles=[profile],
        )

        result = _resolve_logo_file_path(match, project_data, tmp_path)

        assert result is None, (
            f"Expected None when company is missing, got {result!r}"
        )

    @given(data=st.data())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_returns_none_when_logo_media_id_none(
        self, data: st.DataObject, tmp_path: Path
    ) -> None:
        """When the DnaCompany exists but logo_media_id is None, returns None.

        # Feature: dna-company-logo, Property 7: Logo resolution chain
        **Validates: Requirements 6.1, 6.2, 6.3**
        """
        profile_id = data.draw(_id_strategy, label="profile_id")
        company_id = data.draw(_id_strategy, label="company_id")
        match_id = data.draw(_id_strategy, label="match_id")

        match = DnaMatch(
            id=match_id,
            profile1_id=data.draw(_id_strategy),
            profile2_id=profile_id,
        )
        profile = DnaProfile(
            id=profile_id,
            person_id=data.draw(_id_strategy),
            company_id=company_id,
            test_type="autosomal",
        )
        company = DnaCompany(
            id=company_id,
            name="TestCo",
            logo_media_id=None,  # No logo assigned
        )
        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_profiles=[profile],
            dna_companies=[company],
        )

        result = _resolve_logo_file_path(match, project_data, tmp_path)

        assert result is None, (
            f"Expected None when logo_media_id is None, got {result!r}"
        )

    @given(data=st.data())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_returns_none_when_media_item_missing(
        self, data: st.DataObject, tmp_path: Path
    ) -> None:
        """When logo_media_id is set but no MediaItem matches, returns None.

        # Feature: dna-company-logo, Property 7: Logo resolution chain
        **Validates: Requirements 6.1, 6.2, 6.3**
        """
        profile_id = data.draw(_id_strategy, label="profile_id")
        company_id = data.draw(_id_strategy, label="company_id")
        media_id = data.draw(_id_strategy, label="media_id")
        match_id = data.draw(_id_strategy, label="match_id")

        match = DnaMatch(
            id=match_id,
            profile1_id=data.draw(_id_strategy),
            profile2_id=profile_id,
        )
        profile = DnaProfile(
            id=profile_id,
            person_id=data.draw(_id_strategy),
            company_id=company_id,
            test_type="autosomal",
        )
        company = DnaCompany(
            id=company_id,
            name="TestCo",
            logo_media_id=media_id,
        )
        # Project has company with logo_media_id but NO media items
        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_profiles=[profile],
            dna_companies=[company],
        )

        result = _resolve_logo_file_path(match, project_data, tmp_path)

        assert result is None, (
            f"Expected None when media item is missing, got {result!r}"
        )

    @given(data=st.data())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_returns_missing_sentinel_when_file_absent(
        self, data: st.DataObject, tmp_path: Path
    ) -> None:
        """When the full chain resolves but the file doesn't exist, returns sentinel.

        # Feature: dna-company-logo, Property 7: Logo resolution chain
        **Validates: Requirements 6.1, 6.2, 6.3**
        """
        match, project_data, rel_file = data.draw(
            _complete_chain_data(), label="chain"
        )

        # Do NOT create the file on disk — it should be absent
        result = _resolve_logo_file_path(match, project_data, tmp_path)

        assert result == _LOGO_FILE_MISSING, (
            f"Expected _LOGO_FILE_MISSING sentinel when file is absent, "
            f"got {result!r}"
        )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_returns_none_when_project_folder_none(
        self, data: st.DataObject
    ) -> None:
        """When project_folder is None, returns None regardless of chain state.

        # Feature: dna-company-logo, Property 7: Logo resolution chain
        **Validates: Requirements 6.1, 6.2, 6.3**
        """
        match, project_data, _ = data.draw(_complete_chain_data(), label="chain")

        result = _resolve_logo_file_path(match, project_data, None)

        assert result is None, (
            f"Expected None when project_folder is None, got {result!r}"
        )
