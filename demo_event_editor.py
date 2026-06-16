"""Demo script for the Event Editor widget.

Launches a standalone window showing the EventEditor with sample project
data pre-populated (persons, places, sources, media) so you can interact
with all features: type selection, participants, date/place, source
references, and media linking.

Run with:
    python demo_event_editor.py
"""

import sys

from PySide6.QtWidgets import QApplication

from slaktbusken.model.event import (
    DateValue,
    Event,
    Participant,
    PlaceRef,
    SourceRef,
)
from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.source import Source, StructuredReference
from slaktbusken.ui.editors.event_editor import EventEditor


def create_sample_project_data() -> ProjectData:
    """Build sample project data with persons, places, sources, and media."""
    persons = [
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
            names=[Name(type="birth", given="Karl", surname="Johansson")],
        ),
        Person(
            id="person_4",
            sex="F",
            names=[Name(type="birth", given="Maria", surname="Eriksson")],
        ),
        Person(
            id="person_5",
            sex="M",
            names=[Name(type="birth", given="Olof", surname="Nilsson")],
        ),
    ]

    places = [
        Place(id="place_1", type="country", name="Sverige"),
        Place(
            id="place_2",
            type="county",
            name="Gävleborgs län",
            parent_place_id="place_1",
        ),
        Place(
            id="place_3",
            type="parish",
            name="Ljusdal",
            parent_place_id="place_2",
        ),
        Place(
            id="place_4",
            type="church",
            name="Ljusdals kyrka",
            parent_place_id="place_3",
        ),
        Place(
            id="place_5",
            type="cemetery",
            name="Ljusdals kyrkogård",
            parent_place_id="place_3",
        ),
    ]

    sources = [
        Source(
            id="source_1",
            provider="ArkivDigital",
            source_type="church_book",
            title="Ljusdal AI:23d (1883-1887)",
            reference_text="Ljusdal (X) AI:23d (1883-1887) Bild: 23 Sida: 915",
            structured_reference=StructuredReference(
                fields={
                    "parish": "Ljusdal",
                    "county_code": "X",
                    "series": "AI",
                    "volume": "23d",
                    "years": "1883-1887",
                    "image": "23",
                    "page": "915",
                }
            ),
        ),
        Source(
            id="source_2",
            provider="ArkivDigital",
            source_type="church_book",
            title="Ljusdal CI:12 (1880-1894)",
            reference_text="Ljusdal (X) CI:12 (1880-1894) Bild: 45",
        ),
        Source(
            id="source_3",
            provider="Riksarkivet",
            source_type="census",
            title="Folkräkning 1890 — Ljusdal",
        ),
    ]

    media = [
        MediaItem(
            id="media_1",
            type="source_image",
            file="source-image/ljusdal_ai23d_b23.jpg",
            title="Husförhörslängd Ljusdal 1883 sid 915",
            linked_entities=[
                LinkedEntity(entity_type="source", entity_id="source_1", role="source_scan")
            ],
        ),
        MediaItem(
            id="media_2",
            type="photo",
            file="photos/erik_andersson_1890.jpg",
            title="Erik Andersson porträtt ca 1890",
            linked_entities=[
                LinkedEntity(entity_type="person", entity_id="person_1", role="portrait")
            ],
        ),
        MediaItem(
            id="media_3",
            type="death_notice",
            file="death-notice/anna_svensson_1945.jpg",
            title="Dödsannons Anna Svensson 1945",
            linked_entities=[
                LinkedEntity(entity_type="person", entity_id="person_2", role="evidence")
            ],
        ),
    ]

    return ProjectData(
        project=ProjectMetadata(title="Demo-projekt", main_person_id="person_1"),
        persons=persons,
        places=places,
        sources=sources,
        media=media,
    )


def demo_new_event() -> None:
    """Launch the editor in 'create new event' mode."""
    app = QApplication(sys.argv)

    project_data = create_sample_project_data()

    # Create a blank event editor (new event mode)
    editor = EventEditor(project_data=project_data)
    editor.setWindowTitle("Demo: Ny händelse")
    editor.resize(780, 700)
    editor.show()

    app.exec()

    # Print result after window closes
    if editor.saved_event:
        event = editor.saved_event
        print("\n=== Sparad händelse ===")
        print(f"  ID:   {event.id}")
        print(f"  Typ:  {event.type}")
        if event.custom_type_name:
            print(f"  Eget typnamn: {event.custom_type_name}")
        if event.cause_of_death:
            print(f"  Dödsorsak: {event.cause_of_death}")
        print(f"  Deltagare ({len(event.participants)}):")
        for p in event.participants:
            print(f"    - {p.person_id} ({p.role})")
        if event.date:
            print(f"  Datum: {event.date.value} (precision: {event.date.precision})")
            if event.date.source_refs:
                print(f"  Källhänvisningar ({len(event.date.source_refs)}):")
                for sr in event.date.source_refs:
                    print(f"    - {sr.source_id} [{sr.quality}] {sr.note}")
        if event.place:
            print(f"  Plats: {event.place.place_id}")
        if event.media_ids:
            print(f"  Media: {event.media_ids}")
    else:
        print("\nIngen händelse sparades (avbrutet).")


def demo_edit_existing_event() -> None:
    """Launch the editor pre-filled with an existing event."""
    app = QApplication(sys.argv)

    project_data = create_sample_project_data()

    # Create a sample existing event to edit
    existing_event = Event(
        id="event_42",
        type="birth",
        participants=[
            Participant(person_id="person_1", role="huvudperson"),
            Participant(person_id="person_2", role="moder"),
        ],
        date=DateValue(
            value="1885-03-14",
            precision="day",
            source_refs=[
                SourceRef(source_id="source_2", quality="primary", note="Födelsebok"),
            ],
        ),
        place=PlaceRef(place_id="place_3"),
        media_ids=["media_1"],
    )

    editor = EventEditor(project_data=project_data, event=existing_event)
    editor.setWindowTitle("Demo: Redigera befintlig händelse")
    editor.resize(780, 700)
    editor.show()

    app.exec()

    if editor.saved_event:
        event = editor.saved_event
        print("\n=== Uppdaterad händelse ===")
        print(f"  ID:   {event.id}")
        print(f"  Typ:  {event.type}")
        print(f"  Deltagare: {len(event.participants)}")
        if event.date:
            print(f"  Datum: {event.date.value} ({event.date.precision})")
            print(f"  Källor: {len(event.date.source_refs)}")
    else:
        print("\nIngen ändring sparades (avbrutet).")


if __name__ == "__main__":
    print("Släktbusken — Event Editor Demo")
    print("=" * 40)
    print()
    print("  1. Ny händelse (tomt formulär)")
    print("  2. Redigera befintlig händelse (förifyllt)")
    print()

    choice = input("Välj (1 eller 2): ").strip()

    if choice == "2":
        demo_edit_existing_event()
    else:
        demo_new_event()
