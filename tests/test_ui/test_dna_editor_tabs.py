"""Unit tests for DnaEditor tab structure.

Verifies that the Segment tab has been removed and remaining tabs are in
the correct order: Företag, Profiler, Matchningar, Kluster, Triangulering.

Validates: Requirements 5.1, 5.2, 6.1, 6.2, 6.3
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.ui.editors.dna_editor import DnaEditor


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def editor(qtbot) -> DnaEditor:
    """Create a DnaEditor instance for testing."""
    project_data = ProjectData(project=ProjectMetadata(title="Test"))
    ed = DnaEditor(project_data=project_data, project_path=None)
    qtbot.addWidget(ed)
    return ed


class TestSegmentTabRemoved:
    """Tests verifying the Segment tab is not displayed."""

    def test_no_segment_tab_label(self, editor: DnaEditor):
        """DnaEditor SHALL NOT display a tab with the label 'Segment'."""
        tw = editor._ui.tab_widget
        tab_labels = [tw.tabText(i) for i in range(tw.count())]
        assert "Segment" not in tab_labels


class TestTabCount:
    """Tests verifying exactly 5 tabs are displayed."""

    def test_tab_count_is_five(self, editor: DnaEditor):
        """DnaEditor SHALL display exactly 5 tabs."""
        assert editor._ui.tab_widget.count() == 5


class TestTabOrder:
    """Tests verifying the tab order is correct."""

    def test_tab_order(self, editor: DnaEditor):
        """Tabs SHALL be: Företag, Profiler, Matchningar, Kluster, Triangulering."""
        tw = editor._ui.tab_widget
        expected = ["Företag", "Profiler", "Matchningar", "Kluster", "Triangulering"]
        actual = [tw.tabText(i) for i in range(tw.count())]
        assert actual == expected

    def test_kluster_at_index_3(self, editor: DnaEditor):
        """Kluster tab SHALL be at index 3."""
        tw = editor._ui.tab_widget
        assert tw.indexOf(editor._ui.clusters_tab) == 3

    def test_triangulering_at_index_4(self, editor: DnaEditor):
        """Triangulering tab SHALL be at index 4."""
        tw = editor._ui.tab_widget
        assert tw.indexOf(editor._ui.triangulations_tab) == 4
