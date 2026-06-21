"""Property-based tests for PersonBoxItem cluster overflow indicator.

Feature: enhanced-name-cards, Property 14: Cluster overflow indicator

Validates: Requirements 7.6
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from PySide6.QtWidgets import QApplication

from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.ui.widgets.person_box import PersonBoxItem


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestClusterOverflowIndicatorProperty:
    """Feature: enhanced-name-cards, Property 14: Cluster overflow indicator

    For any Person belonging to more than 5 clusters with config enabled,
    exactly 5 cluster names are displayed plus an indicator showing the
    count of remaining clusters (N - 5).

    **Validates: Requirements 7.6**
    """

    @given(
        num_clusters=st.integers(min_value=6, max_value=30),
    )
    @settings(max_examples=100, deadline=None)
    def test_cluster_overflow_shows_exactly_5_names_plus_indicator(
        self,
        num_clusters: int,
    ) -> None:
        """Property 14: Cluster overflow indicator.

        When a person belongs to more than 5 clusters, exactly 5 cluster
        names are rendered plus an overflow indicator "+{N-5} more".

        Feature: enhanced-name-cards, Property 14: Cluster overflow indicator
        **Validates: Requirements 7.6**
        """
        # Build cluster list with N entries, each with a unique name and no color
        cluster_names = [f"Cluster_{i:03d}" for i in range(num_clusters)]
        clusters = [{"name": name, "color": None} for name in cluster_names]

        display_data: dict = {
            "name": "Test Person",
            "clusters": clusters,
        }
        config = PersonBoxConfig(name=True, clusters=True)
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

        # Get all drawText calls
        draw_text_calls = [c for c in painter.method_calls if c[0] == "drawText"]
        # Extract text strings (third positional arg in drawText(rect, alignment, text))
        all_texts = [c[1][2] for c in draw_text_calls if len(c[1]) >= 3]

        # Find the overflow indicator
        overflow_count = num_clusters - 5
        overflow_text = f"+{overflow_count} more"
        assert overflow_text in all_texts, (
            f"With {num_clusters} clusters: expected overflow indicator "
            f"'{overflow_text}' in rendered texts, got: {all_texts}"
        )

        # Count cluster name entries (should be exactly 5)
        sorted_names = sorted(cluster_names)[:5]
        cluster_texts = [t for t in all_texts if t in sorted_names]
        assert len(cluster_texts) == 5, (
            f"With {num_clusters} clusters: expected exactly 5 cluster names "
            f"rendered, got {len(cluster_texts)}. "
            f"Expected names: {sorted_names}, all texts: {all_texts}"
        )
