"""Property-based tests for filename conflict resolution.

Feature: source-management, Property 6: Filename conflict resolution

Validates: Requirements 4.3
"""

from __future__ import annotations

import os

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.services.media_utils import resolve_filename_conflict


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Filenames with common extensions
filename_with_ext = st.from_regex(r"[a-z]{1,10}\.(jpg|png|pdf)", fullmatch=True)

# Filenames without extension
filename_without_ext = st.from_regex(r"[a-z]{1,10}", fullmatch=True)

# Combined filename strategy
filename_st = st.one_of(filename_with_ext, filename_without_ext)


def existing_names_for(target: str) -> st.SearchStrategy[set[str]]:
    """Build a set of existing filenames that includes the target and some conflicts.

    Generates sets containing the target name and optionally some sequential
    conflict names ({stem}_{n}{ext}) to exercise the resolution logic.
    """
    stem, ext = os.path.splitext(target)
    # Generate a consecutive range of conflicts: target, stem_1.ext, stem_2.ext, ...
    max_conflicts = st.integers(min_value=0, max_value=10)
    return max_conflicts.map(
        lambda n: {target} | {f"{stem}_{i}{ext}" for i in range(1, n + 1)}
    )


# ---------------------------------------------------------------------------
# Property 6: Filename conflict resolution
# ---------------------------------------------------------------------------


class TestFilenameConflictResolutionProperty:
    """Feature: source-management, Property 6: Filename conflict resolution

    For any target filename and set of existing filenames in the media directory,
    the conflict resolution function SHALL produce a filename that does not exist
    in the directory, follows the pattern `{stem}_{n}{ext}` where n is the smallest
    positive integer producing a unique name, and preserves the original file extension.

    **Validates: Requirements 4.3**
    """

    @given(target=filename_st)
    @settings(max_examples=100)
    def test_no_conflict_returns_unchanged(self, target: str) -> None:
        """When target_name is NOT in existing_names, result equals target_name."""
        # Use an empty set or a set that doesn't contain target
        other_names = {f"other_{i}.txt" for i in range(3)}
        result = resolve_filename_conflict(target, other_names)
        assert result == target

    @given(data=st.data())
    @settings(max_examples=100)
    def test_result_never_in_existing_names(self, data: st.DataObject) -> None:
        """Result is never in existing_names (uniqueness guarantee)."""
        target = data.draw(filename_st, label="target")
        existing = data.draw(existing_names_for(target), label="existing")
        result = resolve_filename_conflict(target, existing)
        assert result not in existing

    @given(data=st.data())
    @settings(max_examples=100)
    def test_conflict_follows_pattern(self, data: st.DataObject) -> None:
        """When target IS in existing_names, result follows {stem}_{n}{ext} pattern."""
        target = data.draw(filename_st, label="target")
        existing = data.draw(existing_names_for(target), label="existing")

        result = resolve_filename_conflict(target, existing)

        if target in existing:
            stem, ext = os.path.splitext(target)
            # Result must start with stem_ and end with ext
            assert result.startswith(f"{stem}_")
            assert result.endswith(ext)
            # The middle part (between stem_ and ext) must be a positive integer
            middle = result[len(f"{stem}_"):]
            if ext:
                middle = middle[: -len(ext)]
            assert middle.isdigit()
            assert int(middle) >= 1

    @given(data=st.data())
    @settings(max_examples=100)
    def test_extension_preserved(self, data: st.DataObject) -> None:
        """The extension is preserved (same extension as target_name)."""
        target = data.draw(filename_st, label="target")
        existing = data.draw(existing_names_for(target), label="existing")

        result = resolve_filename_conflict(target, existing)

        _, target_ext = os.path.splitext(target)
        _, result_ext = os.path.splitext(result)
        assert result_ext == target_ext

    @given(data=st.data())
    @settings(max_examples=100)
    def test_smallest_positive_integer(self, data: st.DataObject) -> None:
        """n is the smallest positive integer producing a unique name.

        For the chosen n, all {stem}_{k}{ext} with 1 <= k < n must be in existing_names.
        """
        target = data.draw(filename_st, label="target")
        existing = data.draw(existing_names_for(target), label="existing")

        result = resolve_filename_conflict(target, existing)

        if target in existing:
            stem, ext = os.path.splitext(target)
            # Extract n from the result
            middle = result[len(f"{stem}_"):]
            if ext:
                middle = middle[: -len(ext)]
            n = int(middle)

            # All predecessors {stem}_{k}{ext} for 1 <= k < n must be in existing
            for k in range(1, n):
                predecessor = f"{stem}_{k}{ext}"
                assert predecessor in existing, (
                    f"Expected {predecessor} in existing_names for n={n} to be minimal"
                )
