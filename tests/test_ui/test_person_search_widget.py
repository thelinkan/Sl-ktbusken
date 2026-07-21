"""Unit tests for PersonSearchWidget.

Verifies that:
- The widget initializes with no selection.
- set_persons() populates the completer with person names.
- Selecting from the completer emits person_selected with the correct person_id.
- Clearing the text emits person_cleared.
- set_selected_person() pre-populates the widget.
- clear_selection() resets the widget state.

Covers Requirements 4.3, 4.4.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.model.person import Name, Person
from slaktbusken.ui.widgets.person_search_widget import PersonSearchWidget


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def sample_persons() -> list[Person]:
    """Return a list of sample persons for testing."""
    return [
        Person(
            id="p1",
            sex="M",
            names=[Name(type="birth", given="Erik", surname="Andersson")],
        ),
        Person(
            id="p2",
            sex="F",
            names=[Name(type="birth", given="Anna", surname="Svensson")],
        ),
        Person(
            id="p3",
            sex="M",
            names=[Name(type="birth", given="Karl", surname="Johansson")],
        ),
    ]


@pytest.fixture()
def widget(qapp) -> PersonSearchWidget:
    """Return a PersonSearchWidget instance."""
    return PersonSearchWidget()


class TestInitialState:
    """Tests for widget initial state."""

    def test_no_initial_selection(self, widget: PersonSearchWidget):
        """Widget starts with no selected person."""
        assert widget.selected_person_id() is None

    def test_line_edit_has_placeholder(self, widget: PersonSearchWidget):
        """The line edit shows placeholder text."""
        assert widget._line_edit.placeholderText() == "Sök person..."

    def test_line_edit_is_empty(self, widget: PersonSearchWidget):
        """The line edit starts empty."""
        assert widget._line_edit.text() == ""


class TestSetPersons:
    """Tests for set_persons() method."""

    def test_populates_completer(
        self, widget: PersonSearchWidget, sample_persons: list[Person]
    ):
        """set_persons() populates the completer model with person names."""
        widget.set_persons(sample_persons)
        model = widget._completer.model()
        names = [model.data(model.index(i, 0)) for i in range(model.rowCount())]
        assert "Erik Andersson" in names
        assert "Anna Svensson" in names
        assert "Karl Johansson" in names

    def test_handles_empty_list(self, widget: PersonSearchWidget):
        """set_persons() with an empty list clears the completer model."""
        widget.set_persons([])
        model = widget._completer.model()
        assert model.rowCount() == 0

    def test_handles_person_without_names(self, widget: PersonSearchWidget):
        """set_persons() handles persons with no name entries."""
        person = Person(id="p_noname", sex="U", names=[])
        widget.set_persons([person])
        model = widget._completer.model()
        names = [model.data(model.index(i, 0)) for i in range(model.rowCount())]
        assert "(Person p_noname)" in names


class TestSetSelectedPerson:
    """Tests for set_selected_person() method."""

    def test_prepopulates_text(
        self, widget: PersonSearchWidget, sample_persons: list[Person]
    ):
        """set_selected_person() sets the line edit text to the person's name."""
        widget.set_selected_person("p2", sample_persons)
        assert widget._line_edit.text() == "Anna Svensson"

    def test_sets_selected_id(
        self, widget: PersonSearchWidget, sample_persons: list[Person]
    ):
        """set_selected_person() sets the internal selected person ID."""
        widget.set_selected_person("p1", sample_persons)
        assert widget.selected_person_id() == "p1"

    def test_none_person_id_clears(
        self, widget: PersonSearchWidget, sample_persons: list[Person]
    ):
        """set_selected_person(None, ...) clears the selection."""
        widget.set_selected_person("p1", sample_persons)
        widget.set_selected_person(None, sample_persons)
        assert widget.selected_person_id() is None
        assert widget._line_edit.text() == ""

    def test_unknown_id_clears(
        self, widget: PersonSearchWidget, sample_persons: list[Person]
    ):
        """set_selected_person() with an unknown ID leaves selection as None."""
        widget.set_selected_person("nonexistent", sample_persons)
        assert widget.selected_person_id() is None


class TestClearSelection:
    """Tests for clear_selection() method."""

    def test_clears_text(
        self, widget: PersonSearchWidget, sample_persons: list[Person]
    ):
        """clear_selection() empties the line edit."""
        widget.set_selected_person("p1", sample_persons)
        widget.clear_selection()
        assert widget._line_edit.text() == ""

    def test_clears_person_id(
        self, widget: PersonSearchWidget, sample_persons: list[Person]
    ):
        """clear_selection() sets selected_person_id to None."""
        widget.set_selected_person("p1", sample_persons)
        widget.clear_selection()
        assert widget.selected_person_id() is None

    def test_emits_person_cleared(
        self, widget: PersonSearchWidget, sample_persons: list[Person], qtbot
    ):
        """clear_selection() emits the person_cleared signal."""
        widget.set_selected_person("p1", sample_persons)
        with qtbot.waitSignal(widget.person_cleared, timeout=1000):
            widget.clear_selection()

    def test_no_signal_when_already_cleared(
        self, widget: PersonSearchWidget, qtbot
    ):
        """clear_selection() does not emit person_cleared if already empty."""
        signals = []
        widget.person_cleared.connect(lambda: signals.append(True))
        widget.clear_selection()
        assert signals == []


class TestPersonSelection:
    """Tests for person selection via completer activation."""

    def test_emits_person_selected(
        self, widget: PersonSearchWidget, sample_persons: list[Person], qtbot
    ):
        """Activating a completer item emits person_selected with person_id."""
        widget.set_persons(sample_persons)
        with qtbot.waitSignal(widget.person_selected, timeout=1000) as sig:
            widget._on_completer_activated("Erik Andersson")
        assert sig.args == ["p1"]

    def test_sets_selected_person_id(
        self, widget: PersonSearchWidget, sample_persons: list[Person]
    ):
        """Activating a completer item updates selected_person_id."""
        widget.set_persons(sample_persons)
        widget._on_completer_activated("Anna Svensson")
        assert widget.selected_person_id() == "p2"


class TestTextCleared:
    """Tests for clearing text manually."""

    def test_clearing_text_emits_person_cleared(
        self, widget: PersonSearchWidget, sample_persons: list[Person], qtbot
    ):
        """Manually clearing the text emits person_cleared when a person was selected."""
        widget.set_persons(sample_persons)
        widget._on_completer_activated("Erik Andersson")
        with qtbot.waitSignal(widget.person_cleared, timeout=1000):
            widget._line_edit.clear()

    def test_clearing_text_resets_person_id(
        self, widget: PersonSearchWidget, sample_persons: list[Person]
    ):
        """Manually clearing the text sets selected_person_id to None."""
        widget.set_persons(sample_persons)
        widget._on_completer_activated("Erik Andersson")
        widget._line_edit.clear()
        assert widget.selected_person_id() is None
