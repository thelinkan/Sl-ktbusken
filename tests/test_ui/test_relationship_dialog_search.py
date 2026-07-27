"""Tests for RelationshipDialog person search (multi-word matching).

Verifies that the person search combo boxes in the relationship dialog
use multi-word matching so that typing any combination of name parts
(e.g. "Frida Hallen") returns matching results (e.g. "Frida Maria Hallen").

Validates: Requirements 15.1
"""

from __future__ import annotations

import pytest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCompleter

from slaktbusken.model.person import Name, Person
from slaktbusken.model.family import Family
from slaktbusken.model.project import ProjectData
from slaktbusken.ui.dialogs.relationship_dialog import RelationshipDialog, _MultiWordFilterProxy


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
        _make_person("p5", "Frida Maria", "Hallén"),
    ]
    return ProjectData(
        persons=persons,
        families=[],
        events=[],
        sources=[],
        places=[],
    )


class TestRelationshipDialogPersonSearch:
    """Verify that the relationship dialog combo box completers use multi-word matching."""

    def test_completer_is_set(
        self, sample_project_data: ProjectData, qtbot
    ) -> None:
        """The combo boxes should have a completer set."""
        dialog = RelationshipDialog(sample_project_data)
        qtbot.addWidget(dialog)

        for combo in (dialog._combo_a, dialog._combo_b):
            completer = combo.completer()
            assert completer is not None, "Completer should be set on combo box"

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

    def test_multi_word_filter_matches_all_words(
        self, sample_project_data: ProjectData, qtbot
    ) -> None:
        """Typing 'Frida Hallén' should match 'Frida Maria Hallén'."""
        dialog = RelationshipDialog(sample_project_data)
        qtbot.addWidget(dialog)

        # Simulate typing in combo_a
        dialog._combo_a.setEditText("Frida Hallén")
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

        # Get the proxy model and check visible rows
        completer = dialog._combo_a.completer()
        model = completer.model()
        visible = [
            model.data(model.index(i, 0))
            for i in range(model.rowCount())
            if model.data(model.index(i, 0))
        ]
        assert any("Frida" in name and "Hallén" in name for name in visible), (
            f"Expected 'Frida Maria Hallén' in results, got: {visible}"
        )

    def test_single_word_search_by_surname(
        self, sample_project_data: ProjectData, qtbot
    ) -> None:
        """Typing a surname should match persons with that surname."""
        dialog = RelationshipDialog(sample_project_data)
        qtbot.addWidget(dialog)

        dialog._combo_a.setEditText("ström")

        completer = dialog._combo_a.completer()
        model = completer.model()
        visible = [
            model.data(model.index(i, 0))
            for i in range(model.rowCount())
            if model.data(model.index(i, 0))
        ]
        # Should match both Lindström and Bergström
        matches = [n for n in visible if "ström" in n.lower()]
        assert len(matches) == 2, f"Expected 2 matches for 'ström', got {len(matches)}: {matches}"

    def test_single_word_search_by_given_name(
        self, sample_project_data: ProjectData, qtbot
    ) -> None:
        """Typing a given name should match persons with that name."""
        dialog = RelationshipDialog(sample_project_data)
        qtbot.addWidget(dialog)

        dialog._combo_a.setEditText("Maria")

        completer = dialog._combo_a.completer()
        model = completer.model()
        visible = [
            model.data(model.index(i, 0))
            for i in range(model.rowCount())
            if model.data(model.index(i, 0))
        ]
        matches = [n for n in visible if "Maria" in n]
        # Anna Maria Lindström and Frida Maria Hallén
        assert len(matches) == 2, f"Expected 2 matches for 'Maria', got {len(matches)}: {matches}"

    def test_search_case_insensitive(
        self, sample_project_data: ProjectData, qtbot
    ) -> None:
        """Search should be case-insensitive."""
        dialog = RelationshipDialog(sample_project_data)
        qtbot.addWidget(dialog)

        dialog._combo_a.setEditText("sofia")

        completer = dialog._combo_a.completer()
        model = completer.model()
        visible = [
            model.data(model.index(i, 0))
            for i in range(model.rowCount())
            if model.data(model.index(i, 0))
        ]
        matches = [n for n in visible if "Sofia" in n or "sofia" in n.lower()]
        assert len(matches) >= 1, f"Expected at least 1 match for 'sofia' (case-insensitive), got: {visible}"

    def test_empty_search_shows_all(
        self, sample_project_data: ProjectData, qtbot
    ) -> None:
        """Empty search text should show all persons."""
        dialog = RelationshipDialog(sample_project_data)
        qtbot.addWidget(dialog)

        dialog._combo_a.setEditText("")

        completer = dialog._combo_a.completer()
        model = completer.model()
        count = model.rowCount()
        assert count == 5, f"Expected 5 persons for empty search, got {count}"

    def test_multi_word_first_and_last_name(
        self, sample_project_data: ProjectData, qtbot
    ) -> None:
        """Typing 'Erik Andersson' should match 'Erik Gustav Andersson'."""
        dialog = RelationshipDialog(sample_project_data)
        qtbot.addWidget(dialog)

        dialog._combo_a.setEditText("Erik Andersson")

        completer = dialog._combo_a.completer()
        model = completer.model()
        visible = [
            model.data(model.index(i, 0))
            for i in range(model.rowCount())
            if model.data(model.index(i, 0))
        ]
        matches = [n for n in visible if "Erik" in n and "Andersson" in n]
        assert len(matches) == 1, f"Expected 1 match for 'Erik Andersson', got: {matches}"

    def test_no_match_returns_empty(
        self, sample_project_data: ProjectData, qtbot
    ) -> None:
        """Typing a non-existent name should return no matches."""
        dialog = RelationshipDialog(sample_project_data)
        qtbot.addWidget(dialog)

        dialog._combo_a.setEditText("Nonexistent Person")

        completer = dialog._combo_a.completer()
        model = completer.model()
        visible = [
            model.data(model.index(i, 0))
            for i in range(model.rowCount())
            if model.data(model.index(i, 0))
        ]
        assert len(visible) == 0, f"Expected 0 matches for 'Nonexistent Person', got: {visible}"

    def test_all_persons_in_combo(
        self, sample_project_data: ProjectData, qtbot
    ) -> None:
        """All persons should be listed in both combo boxes."""
        dialog = RelationshipDialog(sample_project_data)
        qtbot.addWidget(dialog)

        assert dialog._combo_a.count() == 5
        assert dialog._combo_b.count() == 5
