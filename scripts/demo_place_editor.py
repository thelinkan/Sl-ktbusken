"""Demo script to visually inspect the Place Editor.

Run with:  python scripts/demo_place_editor.py
"""

import sys

from PySide6.QtWidgets import QApplication

from slaktbusken.model.place import Place
from slaktbusken.model.event import Event, Participant, PlaceRef, DateValue
from slaktbusken.model.project import ProjectData, ProjectMetadata


def build_sample_data() -> ProjectData:
    """Create sample project data with places and events for demo."""
    places = [
        Place(id="place_1", type="country", name="Sverige"),
        Place(id="place_2", type="county", name="Gävleborgs län", parent_place_id="place_1"),
        Place(id="place_3", type="parish", name="Ljusdal", parent_place_id="place_2"),
        Place(id="place_4", type="church", name="Ljusdals kyrka", parent_place_id="place_3"),
        Place(id="place_5", type="cemetery", name="Ljusdals kyrkogård", parent_place_id="place_3"),
        Place(id="place_6", type="county", name="Stockholms län", parent_place_id="place_1"),
        Place(id="place_7", type="parish", name="Stockholm", parent_place_id="place_6"),
        Place(
            id="place_8",
            type="church",
            name="Storkyrkan",
            parent_place_id="place_7",
            latitude=59.3258,
            longitude=18.0706,
            notes="Stockholms domkyrka",
        ),
    ]

    events = [
        Event(
            id="event_1",
            type="birth",
            participants=[Participant(person_id="person_1", role="subject")],
            date=DateValue(value="1850-03-15", precision="day"),
            place=PlaceRef(place_id="place_4"),
        ),
        Event(
            id="event_2",
            type="death",
            participants=[Participant(person_id="person_1", role="subject")],
            date=DateValue(value="1920-11-02", precision="day"),
            place=PlaceRef(place_id="place_5"),
        ),
        Event(
            id="event_3",
            type="marriage",
            participants=[
                Participant(person_id="person_1", role="husband"),
                Participant(person_id="person_2", role="wife"),
            ],
            date=DateValue(value="1875-06-21", precision="day"),
            place=PlaceRef(place_id="place_8"),
        ),
    ]

    return ProjectData(
        project=ProjectMetadata(title="Demo-projekt"),
        places=places,
        events=events,
    )


def main() -> None:
    """Launch the Place Editor with sample data."""
    app = QApplication(sys.argv)
    project_data = build_sample_data()

    from slaktbusken.ui.editors.place_editor import PlaceEditor

    editor = PlaceEditor(project_data=project_data)
    editor.setWindowTitle("Demo — Platsredigerare")
    editor.resize(1000, 650)
    editor.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
