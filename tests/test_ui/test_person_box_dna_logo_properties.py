"""Property-based tests for PersonBoxItem DNA logo rendering.

Feature: enhanced-name-cards, Property 3: DNA logo count matches profile count gated by config

Validates: Requirements 2.1, 2.5, 2.6
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from PySide6.QtWidgets import QApplication

from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.ui.widgets.person_box import (
    PersonBoxItem,
    _MAX_DNA_LOGOS,
)


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestDnaLogoCountProperty:
    """Feature: enhanced-name-cards, Property 3: DNA logo count matches profile count gated by config

    Generate persons with 0, 1, 2, 5, 6, 10 DNA profiles and varying
    dna_info toggle. Verify rendered logo count equals min(N, 5) when
    enabled, 0 when disabled.

    **Validates: Requirements 2.1, 2.5, 2.6**
    """

    @given(
        num_profiles=st.sampled_from([0, 1, 2, 5, 6, 10]),
        dna_info_enabled=st.booleans(),
    )
    @settings(max_examples=100, deadline=None)
    def test_dna_logo_count_matches_profile_count_gated_by_config(
        self,
        num_profiles: int,
        dna_info_enabled: bool,
    ) -> None:
        """Property 3: DNA logo count matches profile count gated by config.

        When dna_info is True, the number of logos rendered equals
        min(N, 5). When dna_info is False, zero logos are rendered.

        Feature: enhanced-name-cards, Property 3: DNA logo count matches profile count gated by config
        **Validates: Requirements 2.1, 2.5, 2.6**
        """
        # Build dna_companies list with N entries (logo=None triggers placeholders)
        dna_companies = [
            {"name": f"Company{i:02d}", "logo": None}
            for i in range(num_profiles)
        ]

        display_data: dict = {
            "name": "Test Person",
            "dna_companies": dna_companies,
        }
        config = PersonBoxConfig(name=True, dna_info=dna_info_enabled)
        item = PersonBoxItem(
            person_id="person_1",
            display_data=display_data,
            config=config,
        )

        # Use a mock painter to capture draw calls
        painter = MagicMock()
        option = MagicMock()

        with patch(
            "slaktbusken.ui.widgets.person_box.icon_registry"
        ) as mock_registry:
            mock_pixmap = MagicMock()
            mock_pixmap.isNull.return_value = True
            mock_registry.get_gender_icon.return_value = mock_pixmap
            mock_registry.get_multiple_names_icon.return_value = mock_pixmap
            item.paint(painter, option, None)

        # Count drawRoundedRect calls. The first one is the card border.
        # Each DNA placeholder also calls drawRoundedRect (for the gray background).
        draw_rounded_rect_calls = [
            c for c in painter.method_calls if c[0] == "drawRoundedRect"
        ]

        # The card border accounts for exactly 1 drawRoundedRect call
        logo_rect_count = len(draw_rounded_rect_calls) - 1

        # Determine expected logo count
        if dna_info_enabled:
            expected_count = min(num_profiles, _MAX_DNA_LOGOS)
        else:
            expected_count = 0

        assert logo_rect_count == expected_count, (
            f"With num_profiles={num_profiles}, dna_info={dna_info_enabled}: "
            f"expected {expected_count} DNA logo placeholders, "
            f"got {logo_rect_count}"
        )
