"""Property-based tests for PersonBoxItem cluster text color rendering.

Feature: enhanced-name-cards, Property 13: Cluster text color matches cluster color property

Validates: Requirements 7.2, 7.3
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QApplication

from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.ui.widgets.person_box import PersonBoxItem, _LABEL_COLOR


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# Strategy for cluster color: either None or a valid hex color string
_color_strategy = st.one_of(
    st.none(),
    st.sampled_from(["#FF0000", "#00FF00", "#0000FF", "#AABBCC", "#123456"]),
)

# Strategy for a single cluster dict
_cluster_strategy = st.fixed_dictionaries(
    {"name": st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz"),
     "color": _color_strategy}
)


class TestClusterTextColorProperty:
    """Feature: enhanced-name-cards, Property 13: Cluster text color matches cluster color property

    For any displayed cluster, the text color is the cluster's color
    value when set, or the default label color when color is None.

    **Validates: Requirements 7.2, 7.3**
    """

    @given(
        clusters=st.lists(_cluster_strategy, min_size=1, max_size=5),
    )
    @settings(max_examples=100, deadline=None)
    def test_cluster_text_color_matches_cluster_color_property(
        self,
        clusters: list[dict],
    ) -> None:
        """Property 13: Cluster text color matches cluster color property.

        When a cluster has a valid color string, the text is rendered
        with that color. When color is None, the default _LABEL_COLOR
        is used.

        Feature: enhanced-name-cards, Property 13: Cluster text color matches cluster color property
        **Validates: Requirements 7.2, 7.3**
        """
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

        # Extract all setPen calls made during painting
        set_pen_calls = [
            call for call in painter.method_calls if call[0] == "setPen"
        ]

        # The clusters are sorted alphabetically by name before rendering
        sorted_clusters = sorted(clusters, key=lambda c: c.get("name", ""))

        # For each cluster, _paint_cluster_lines calls setPen with the
        # cluster's color (or _LABEL_COLOR) immediately before drawText.
        # We need to find the setPen calls that correspond to cluster rendering.
        #
        # Strategy: find drawText calls and pair each with the preceding setPen.
        # Cluster drawText calls happen after the standard text lines.
        # We identify them by looking at all calls in sequence.
        all_calls = painter.method_calls

        # Find pairs of (setPen, drawText) in the cluster painting region.
        # The cluster painting happens at the end. We look for the sequence
        # of setPen -> drawText pairs that correspond to cluster lines.
        # Count how many drawText calls there are total; the last N belong to clusters.
        draw_text_indices = [
            i for i, call in enumerate(all_calls) if call[0] == "drawText"
        ]

        num_clusters = len(sorted_clusters)

        # The last num_clusters drawText calls are the cluster text renders
        cluster_draw_text_indices = draw_text_indices[-num_clusters:]

        # For each cluster drawText, find the immediately preceding setPen call
        for cluster_idx, dt_idx in enumerate(cluster_draw_text_indices):
            # Search backwards from dt_idx for the nearest setPen
            pen_idx = None
            for j in range(dt_idx - 1, -1, -1):
                if all_calls[j][0] == "setPen":
                    pen_idx = j
                    break

            assert pen_idx is not None, (
                f"No setPen found before drawText for cluster index {cluster_idx}"
            )

            # Extract the QPen from the setPen call
            pen_call_args = all_calls[pen_idx][1]  # positional args
            actual_pen: QPen = pen_call_args[0]

            # Determine expected color
            cluster = sorted_clusters[cluster_idx]
            color_str = cluster.get("color")
            if color_str:
                expected_color = QColor(color_str)
                if not expected_color.isValid():
                    expected_color = _LABEL_COLOR
            else:
                expected_color = _LABEL_COLOR

            actual_color = actual_pen.color()

            assert actual_color == expected_color, (
                f"Cluster '{cluster.get('name')}' with color={color_str!r}: "
                f"expected text color {expected_color.name()}, "
                f"got {actual_color.name()}"
            )
