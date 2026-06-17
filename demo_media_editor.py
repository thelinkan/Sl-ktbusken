"""Demo script for the MediaEditor widget.

Launches the media editor with sample data so you can interact with it
standalone, without running the full Släktbusken application.

Usage:
    python demo_media_editor.py
"""

import sys

from PySide6.QtWidgets import QApplication

from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.person import Person, Name
from slaktbusken.model.event import Event, Participant
from slaktbusken.model.source import Source, StructuredReference
from slaktbusken.model.place import Place
from slaktbusken.ui.editors.media_editor import MediaEditor


def create_sample_data() -> ProjectData:
    """Create sample project data with a few entities to link media to."""
    data = ProjectData(
        project=ProjectMetadata(title="Demo-projekt"),
        persons=[
            Person(
                id="person_1",
                sex="M",
                names=[Name(type="birth", given="Erik", surname="Andersson")],
            ),
            Person(
                id="person_2",
                sex="F",
                names=[Name(type="birth", given="Anna", surname="Svensson")],
            ),
            Person(
                id="person_3",
                sex="M",
                names=[Name(type="birth", given="Lars", surname="Eriksson")],
            ),
        ],
        events=[
            Event(
                id="event_1",
                type="birth",
                participants=[Participant(person_id="person_1", role="subject")],
            ),
            Event(
                id="event_2",
                type="marriage",
                participants=[
                    Participant(person_id="person_1", role="husband"),
                    Participant(person_id="person_2", role="wife"),
                ],
            ),
        ],
        sources=[
            Source(
                id="source_1",
                provider="ArkivDigital",
                source_type="church_book",
                title="Ljusdal AI:23d (1883-1887)",
                reference_text="Ljusdal (X) AI:23d (1883-1887) Bild: 23 Sida: 915",
                structured_reference=StructuredReference(fields={
                    "parish": "Ljusdal",
                    "county_code": "X",
                    "series": "AI",
                    "volume": "23d",
                    "years": "1883-1887",
                    "image": "23",
                    "page": "915",
                }),
            ),
        ],
        places=[
            Place(id="place_1", type="parish", name="Ljusdal"),
            Place(id="place_2", type="county", name="Gävleborgs län"),
        ],
        media=[
            # An existing photo (file won't exist on disk -> shows missing indicator)
            MediaItem(
                id="media_1",
                type="photo",
                file="media/photos/erik_andersson_1890.jpg",
                title="Erik Andersson porträtt 1890",
                linked_entities=[
                    LinkedEntity(entity_type="person", entity_id="person_1", role="porträtt"),
                ],
                mentioned_person_ids=["person_1"],
            ),
            # An existing source image
            MediaItem(
                id="media_2",
                type="source_image",
                file="media/source-image/ljusdal_ai23d_bild23.png",
                title="Ljusdal AI:23d Bild 23",
                linked_entities=[
                    LinkedEntity(entity_type="source", entity_id="source_1", role="källskanning"),
                    LinkedEntity(entity_type="person", entity_id="person_1", role="omnämnd"),
                ],
                transcription="Erik Andersson, f. 1855, hustru Anna Svensson f. 1860",
            ),
            # A death notice
            MediaItem(
                id="media_3",
                type="death_notice",
                file="media/death-notice/anna_svensson_dn.pdf",
                title="Dödsannons Anna Svensson",
                linked_entities=[
                    LinkedEntity(entity_type="person", entity_id="person_2", role="ämne"),
                ],
                publication={"newspaper": "Ljusdals-Posten", "date": "1932-05-15", "page": "4"},
                transcription="Vår kära mor Anna Svensson har stilla insomnat...",
                mentioned_person_ids=["person_1", "person_3"],
            ),
        ],
    )
    return data


def main() -> None:
    """Launch the media editor demo."""
    app = QApplication(sys.argv)

    project_data = create_sample_data()

    # Open editor with the sample data (no pre-selected item -> starts fresh)
    editor = MediaEditor(project_data=project_data)
    editor.setWindowTitle("Mediaredigerare — Demo")
    editor.resize(1100, 750)
    editor.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
