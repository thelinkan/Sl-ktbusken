"""Tests for RelationshipDialog person search (substring matching).

Verifies that the person search combo boxes in the relationship dialog
use substring matching (MatchContains) so that typing any part of a
person's name returns matching results.

Validates: Requirements 15.1
"""

from __future__ import annotations

import pytest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCompleter

from slaktbusken.model.person import Name, Person
from slaktbusken.model.family import Family
from slaktbusken.model.project import ProjectData
from slaktbusken.ui.dialogs.relationship_dialog import RelationshipDialog


def _make_person(person_id: str, given: str, surname: str) -> Person:
    """Create a minimal person with one name."""
    return Person(
        id=person_id,
        sex="M",
        names=[Name(type="birth", given=given, surname=surname)],
    )


@pytest.fixture
def sample_project_data() -> ProjectData:
    """Create a ProjectData with several persons for testing."""
    persons = [
        _make_person("p1", "Erik Gustav", "Andersson"),
        _make_person("p2", "Anna Maria", "Lindström"),
        _make_person("p3", "Karl Johan", "Bergström"),
        _make_person("p4", "Sofia", "Zetterberg"),
    ]
    return ProjectData(
        persons=persons,
        families=[],
        events=[],
        sources=[],
        places=[],
    )


class TestRelationshipDialogPersonSearch:
    """Verify that the relationship dialog combo box completers use substring matching."""

    def test_completer_filter_mode_is_match_contains(
        self, sample_project_data: ProjectData, qtbot
    ) -> None:
        """The combo box completers must use MatchContains filter mode."""
        dialog = RelationshipDialog(sample_project_data)
        qtbot.addWidget(dialog)

        for combo in (dialog._combo_a, dialog._combo_b):
            completer = combo.completer()
            assert completer is not None, "Completer should be set on combo box"
            assert completer.filterMode() == Qt.MatchFlag.MatchContains

    def test_completer_is_case_insensitive(
        self, sample_project_data: ProjectData, qtbot
    ) -> None:
        """The combo box completers must be case insensitive."""
        dialog = RelationshipDialog(sample_project_data)
        qtbot.addWidget(dialog)

        for combo in (dialog._combo_a, dialog._combo_b):
            completer = combo.completer()
            assert completer is not None
            assert completer.caseSensitivity() == Qt.CaseSensitivity.CaseInsensitive

    def test_search_by_surname_substring(
        self, sample_project_data: ProjectData, qtbot
    ) -> None:
        """Typing a surname substring should produce matching completions."""
        dialog = RelationshipDialog(sample_project_data)
        qtbot.addWidget(dialog)

        completer = dialog._combo_a.completer()
        assert completer is not None

        # Search for "ström" which is a substring in "Lindström" and "Bergström"
        model = completer.completionModel()
        completer.setCompletionPrefix("ström")
        count = completer.completionCount()
        assert count == 2, f"Expected 2 matches for 'ström', got {count}"

    def test_search_by_given_name_substring(
        self, sample_project_data: ProjectData, qtbot
    ) -> None:
        """Typing a given name substring should produce matching completions."""
        dialog = RelationshipDialog(sample_project_data)
        qtbot.addWidget(dialog)

        completer = dialog._combo_a.completer()
        assert completer is not None

        # Search for "Maria" which is in "Anna Maria Lindström"
        completer.setCompletionPrefix("Maria")
        count = completer.completionCount()
        assert count == 1, f"Expected 1 match for 'Maria', got {count}"

    def test_search_by_partial_middle_name(
        self, sample_project_data: ProjectData, qtbot
    ) -> None:
        """Typing a middle/second name should produce matching completions."""
        dialog = RelationshipDialog(sample_project_data)
        qtbot.addWidget(dialog)

        completer = dialog._combo_a.completer()
        assert completer is not None

        # Search for "Johan" which is in "Karl Johan Bergström"
        completer.setCompletionPrefix("Johan")
        count = completer.completionCount()
        assert count == 1, f"Expected 1 match for 'Johan', got {count}"

    def test_search_case_insensitive(
        self, sample_project_data: ProjectData, qtbot
    ) -> None:
        """Search should be case-insensitive."""
        dialog = RelationshipDialog(sample_project_data)
        qtbot.addWidget(dialog)

        completer = dialog._combo_a.completer()
        assert completer is not None

        # Search for "sofia" (lowercase) which should match "Sofia Zetterberg"
        completer.setCompletionPrefix("sofia")
        count = completer.completionCount()
        assert count == 1, f"Expected 1 match for 'sofia', got {count}"
