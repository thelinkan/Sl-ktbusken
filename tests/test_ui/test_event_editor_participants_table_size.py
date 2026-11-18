"""Unit tests for EventEditor participants table sizing.

Verifies that the participants table is tall enough to show several
participants at once (e.g. a foster child plus both foster parents) without
scrolling, replacing the old hard 100px maximum-height cap that only showed a
single data row.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.model.event import Event, Participant
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.ui.editors.event_editor import EventEditor


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def project_data() -> ProjectData:
    """Return project data with a single person."""
    pd = ProjectData()
    pd.persons.append(
        Person(
            id="p1",
            sex="male",
            names=[Name(type="birth", given="Erik", surname="Svensson")],
        )
    )
    return pd


def test_participants_table_min_height_exceeds_old_cap(project_data: ProjectData) -> None:
    """The participants table should be taller than the old 100px cap."""
    event = Event(
        id="evt1",
        type="foster_home",
        participants=[Participant(person_id="p1", role="fosterbarn")],
    )
    editor = EventEditor(project_data, event=event)
    table = editor._ui.participants_table

    assert table.minimumHeight() > 100


def test_participants_table_fits_three_rows(project_data: ProjectData) -> None:
    """Minimum height must fit at least 3 data rows plus the header.

    A foster placement has a child plus up to two foster parents, so three
    participant rows must be visible at once without scrolling, and the
    maximum height must not force the table below that.
    """
    event = Event(
        id="evt1",
        type="foster_home",
        participants=[Participant(person_id="p1", role="fosterbarn")],
    )
    editor = EventEditor(project_data, event=event)
    table = editor._ui.participants_table

    row_height = table.verticalHeader().defaultSectionSize()
    header_height = table.horizontalHeader().height()
    frame = 2 * table.frameWidth()
    needed_for_three_rows = row_height * 3 + header_height + frame

    assert table.minimumHeight() >= needed_for_three_rows
    # A maximum height, if set, must still allow three data rows.
    assert table.maximumHeight() >= needed_for_three_rows
