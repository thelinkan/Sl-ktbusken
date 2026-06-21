"""Property-based tests for PersonBoxItem cluster sorting and cap.

Feature: enhanced-name-cards, Property 12: Cluster display sorted and capped

Validates: Requirements 7.1, 7.4
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from PySide6.QtCore import QRectF, Qt
from PySide6.QtWidgets import QApplication

from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.ui.widgets.person_box import (
    PersonBoxItem,
    _MAX_CLUSTERS,
)


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# Strategy for generating cluster names: non-empty strings of letter characters
_cluster_name_st = st.text(
    min_size=1,
    max_size=20,
    alphabet=st.characters(whitelist_categories=("L",)),
)


def _build_cluster_list(num_clusters: int, names: list[str]) -> list[dict]:
    """Build a cluster list from generated names."""
    return [{"name": name, "color": None} for name in names[:num_clusters]]


class TestClusterSortingAndCapProperty:
    """Feature: enhanced-name-cards, Property 12: Cluster display sorted and capped

    Generate persons belonging to 0, 1, 5, 6, 20 clusters with config enabled.
    Verify alphabetical order and min(N, 5) display count.

    **Validates: Requirements 7.1, 7.4**
    """

    @given(
        num_clusters=st.sampled_from([0, 1, 5, 6, 20]),
        cluster_names=st.lists(
            _cluster_name_st,
            min_size=20,
            max_size=20,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_cluster_display_sorted_and_capped(
        self,
        num_clusters: int,
        cluster_names: list[str],
    ) -> None:
        """Property 12: Cluster display sorted and capped.

        When clusters config is enabled, cluster names are rendered in
        alphabetical order and at most 5 are displayed. When N=0, no
        cluster text is rendered.

        Feature: enhanced-name-cards, Property 12: Cluster display sorted and capped
        **Validates: Requirements 7.1, 7.4**
        """
        # Build clusters list with the requested number of entries
        clusters = _build_cluster_list(num_clusters, cluster_names)

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

        # Extract drawText calls that use QRectF (cluster lines use this pattern)
        # _paint_cluster_lines calls: painter.drawText(QRectF(...), Qt.AlignmentFlag.AlignLeft, text)
        draw_text_calls = [
            c for c in painter.method_calls if c[0] == "drawText"
        ]

        # Filter for drawText calls with 3 positional args (QRectF, alignment, text)
        # These are cluster lines and the name line (also uses QRectF form)
        rect_draw_text_calls = [
            c for c in draw_text_calls
            if len(c[1]) == 3 and isinstance(c[1][0], QRectF)
        ]

        # The name line is the first QRectF-based drawText call.
        # Cluster lines come after the standard text lines.
        # Identify cluster text by excluding the name line and standard field lines.
        # Standard lines (name, dates, etc.) are drawn in the main loop;
        # cluster lines are drawn by _paint_cluster_lines after the main loop.
        #
        # Strategy: the expected cluster names are the sorted visible subset.
        # We can identify cluster drawText calls by matching their text against
        # the expected sorted cluster names (or "+N more" overflow text).
        expected_sorted = sorted(
            [c["name"] for c in clusters], key=lambda s: s
        )
        expected_visible = expected_sorted[: min(num_clusters, _MAX_CLUSTERS)]

        # Collect all rendered text from QRectF-based drawText calls
        all_rendered_texts = [c[1][2] for c in rect_draw_text_calls]

        if num_clusters == 0:
            # No cluster text should be rendered
            # Verify none of the cluster names appear (trivially true with empty list)
            # Just verify no "+N more" overflow indicator
            overflow_texts = [
                t for t in all_rendered_texts if t.startswith("+") and "more" in t
            ]
            assert overflow_texts == [], (
                f"Expected no cluster text with 0 clusters, but found overflow: {overflow_texts}"
            )
        else:
            # Find the cluster names in the rendered text.
            # Cluster names may be elided (truncated with "…") by QFontMetrics,
            # but since our mock doesn't truly elide, the text should match.
            # However, QFontMetrics.elidedText on a mock returns whatever the mock
            # returns. We need to ensure the mock's elidedText returns the input.
            #
            # Since painter is a MagicMock, painter.font() returns a MagicMock,
            # and QFontMetrics(mock_font) would fail. The actual code creates its
            # own QFont and QFontMetrics, so elision works on real metrics.
            # The elided text should be the full text for short names (≤20 chars)
            # within a 240px box.
            #
            # We identify cluster lines by looking for text that matches expected
            # cluster names. With our generated names (1-20 letter chars), they
            # should fit within the box width without elision.

            # Collect texts that match expected visible cluster names
            rendered_cluster_names = [
                t for t in all_rendered_texts if t in expected_visible
            ]

            # Verify count: should be min(N, 5)
            expected_count = min(num_clusters, _MAX_CLUSTERS)
            assert len(rendered_cluster_names) == expected_count, (
                f"With {num_clusters} clusters: expected {expected_count} "
                f"cluster names rendered, got {len(rendered_cluster_names)}. "
                f"Expected visible: {expected_visible}, "
                f"Found in render: {rendered_cluster_names}"
            )

            # Verify alphabetical order: rendered cluster names should already
            # be in sorted order (matching expected_visible which is sorted)
            assert rendered_cluster_names == expected_visible, (
                f"Cluster names not in alphabetical order. "
                f"Expected: {expected_visible}, got: {rendered_cluster_names}"
            )
