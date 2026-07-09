"""Property tests for ProjectSettings paper size persistence (Property 9).

Feature: report-menu, Property 9: Paper size persistence round-trip

**Validates: Requirements 5.6**
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.persistence.settings_io import (
    ProjectSettings,
    VALID_PAPER_SIZES,
    read_settings,
    write_settings,
)


class TestPropertyPaperSizeRoundTrip:
    """Property 9: Paper size persistence round-trip.

    # Feature: report-menu, Property 9: Paper size persistence round-trip

    For any valid paper size string from the set {"A4", "A3", "A5"},
    writing it to project settings and reading it back SHALL yield
    the identical string.
    """

    @given(paper_size=st.sampled_from(list(VALID_PAPER_SIZES)))
    @settings(max_examples=100)
    def test_valid_paper_size_round_trip(self, paper_size: str) -> None:
        """For any valid paper size, write then read yields the identical string.

        # Feature: report-menu, Property 9: Paper size persistence round-trip
        **Validates: Requirements 5.6**
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings_path = Path(tmp_dir) / "settings.json"

            # Create settings with the generated paper size
            original = ProjectSettings(report_paper_size=paper_size)

            # Write to a temp file
            write_settings(original, settings_path)

            # Read back
            loaded = read_settings(settings_path)

            # The paper size must be identical
            assert loaded.report_paper_size == paper_size

    @given(
        invalid_size=st.text(min_size=1, max_size=20).filter(
            lambda s: s not in VALID_PAPER_SIZES
        )
    )
    @settings(max_examples=100)
    def test_invalid_paper_size_falls_back_to_a4(
        self, invalid_size: str
    ) -> None:
        """For any invalid paper size value, deserialization falls back to A4.

        # Feature: report-menu, Property 9: Paper size persistence round-trip
        **Validates: Requirements 5.6**
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings_path = Path(tmp_dir) / "settings.json"

            # Write raw JSON with an invalid paper size
            data = {"report_paper_size": invalid_size}
            settings_path.write_text(
                json.dumps(data, indent=2) + "\n", encoding="utf-8"
            )

            # Read back — should fall back to "A4"
            loaded = read_settings(settings_path)

            assert loaded.report_paper_size == "A4"
