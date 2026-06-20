"""Unit tests for DNA match display UI integration.

Feature: dna-match-list-enhancement

Validates: Requirements 2.2
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.model.dna import DnaMatch
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.ui.editors.dna_editor import DnaEditor
from slaktbusken.ui.dna_match_display import format_match_entry


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestMatchFilterWidgetIntegration:
    """Unit tests for the match filter QLineEdit widget integration."""

    def test_placeholder_text(self, qtbot):
        """Filter input SHALL have placeholder text 'Filtrera på person…'."""
        project_data = ProjectData(project=ProjectMetadata(title="Test"))
        editor = DnaEditor(project_data=project_data, project_path=None)
        qtbot.addWidget(editor)

        assert editor._ui.match_filter_input.placeholderText() == "Filtrera p\u00e5 person\u2026"

    def test_filter_input_positioned_above_list(self, qtbot):
        """Filter input SHALL be positioned above the matches list in the layout."""
        project_data = ProjectData(project=ProjectMetadata(title="Test"))
        editor = DnaEditor(project_data=project_data, project_path=None)
        qtbot.addWidget(editor)

        layout = editor._ui.matches_left_layout
        filter_index = layout.indexOf(editor._ui.match_filter_input)
        list_index = layout.indexOf(editor._ui.matches_list)

        assert filter_index < list_index, (
            f"Filter input (index {filter_index}) should be before list (index {list_index})"
        )


class TestSharedCmFormatting:
    """Unit tests for shared_cm decimal formatting edge cases."""

    @pytest.mark.parametrize(
        "shared_cm,expected_str",
        [
            (7.0, "7.0 cM"),
            (15.333, "15.3 cM"),
            (100.0, "100.0 cM"),
        ],
    )
    def test_cm_formatting(self, shared_cm, expected_str):
        """shared_cm SHALL be formatted to one decimal place."""
        match = DnaMatch(
            id="test_match",
            profile1_id="p1",
            profile2_id="p2",
            shared_cm=shared_cm,
            shared_percentage=0.0,
            segment_count=5,
            largest_segment_cm=10.0,
            match_source="internal",
            notes="",
        )
        project_data = ProjectData(project=ProjectMetadata(title="Test"))
        result = format_match_entry(match, project_data)
        assert expected_str in result, f"Expected '{expected_str}' in '{result}'"
