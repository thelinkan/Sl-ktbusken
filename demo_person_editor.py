"""Demo script for the Person Editor.

Launches the PersonEditor widget with sample data including events,
media, DNA profiles, matches, and clusters — showing both the
'edit existing person' and 'create new person' modes.

Usage:
    python demo_person_editor.py
"""

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from slaktbusken.model.dna import DnaCluster, DnaCompany, DnaMatch, DnaProfile
from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef
from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.ui.editors.person_editor import PersonEditor


def create_sample_project() -> tuple[ProjectData, Person]:
    """Build a sample project with linked data for the demo."""

    # Sample persons
    person = Person(
        id="person_1",
        sex="M",
        names=[
            Name(type="birth", given="Erik", surname="Johansson"),
            Name(type="married", given="Erik", surname="Eriksson"),
        ],
        notes="Bonde i Ljusdal. Känd för sitt skogsbruk.",
        title="Hemmansägare",
        occupation="Bonde",
        profile_media_id="media_1",
    )

    wife = Person(
        id="person_2",
        sex="F",
        names=[Name(type="birth", given="Anna", surname="Svensson")],
    )

    # Events
    events = [
        Event(
            id="event_1",
            type="birth",
            participants=[Participant(person_id="person_1", role="barn")],
            date=DateValue(value="1845-03-12", precision="day"),
            place=PlaceRef(place_id="place_1"),
        ),
        Event(
            id="event_2",
            type="baptism",
            participants=[Participant(person_id="person_1", role="barn")],
            date=DateValue(value="1845-03-15", precision="day"),
        ),
        Event(
            id="event_3",
            type="marriage",
            participants=[
                Participant(person_id="person_1", role="man"),
                Participant(person_id="person_2", role="hustru"),
            ],
            date=DateValue(value="1870-06-24", precision="day"),
        ),
        Event(
            id="event_4",
            type="death",
            participants=[Participant(person_id="person_1", role="avliden")],
            date=DateValue(value="1920-11-02", precision="day"),
            cause_of_death="Lunginflammation",
        ),
    ]

    # Media
    media = [
        MediaItem(
            id="media_1",
            type="photo",
            file="photos/erik_portrait.jpg",
            title="Erik Eriksson — porträtt ca 1890",
            linked_entities=[
                LinkedEntity(entity_type="person", entity_id="person_1", role="portrait"),
            ],
        ),
        MediaItem(
            id="media_2",
            type="photo",
            file="photos/erik_family.jpg",
            title="Familjen Eriksson — 1895",
            linked_entities=[
                LinkedEntity(entity_type="person", entity_id="person_1", role="subject"),
                LinkedEntity(entity_type="person", entity_id="person_2", role="subject"),
            ],
        ),
    ]

    # DNA
    dna_company = DnaCompany(id="dnacompany_1", name="MyHeritage DNA")
    dna_profiles = [
        DnaProfile(
            id="dnaprofile_1",
            person_id="person_1",
            company_id="dnacompany_1",
            test_type="autosomal",
            kit_name="Eriks kit",
            kit_id="MH-12345",
            admin_status="self",
        ),
    ]
    dna_matches = [
        DnaMatch(
            id="dnamatch_1",
            profile1_id="dnaprofile_1",
            profile2_id="dnaprofile_99",
            shared_cm=250.5,
            shared_percentage=3.5,
            segment_count=12,
            largest_segment_cm=45.2,
            match_source="external",
        ),
        DnaMatch(
            id="dnamatch_2",
            profile1_id="dnaprofile_1",
            profile2_id="dnaprofile_98",
            shared_cm=78.3,
            shared_percentage=1.1,
            segment_count=4,
            largest_segment_cm=32.1,
            match_source="external",
        ),
    ]
    dna_clusters = [
        DnaCluster(
            id="dnacluster_1",
            name="Hälsingland-kluster",
            notes="Gemensamt DNA-segment på kromosom 7",
            person_ids=["person_1", "person_3", "person_4"],
            color="#4488CC",
        ),
        DnaCluster(
            id="dnacluster_2",
            name="Västernorrland-kluster",
            person_ids=["person_1", "person_5"],
            color="#CC8844",
        ),
    ]

    project_data = ProjectData(
        project=ProjectMetadata(title="Demo-projekt", main_person_id="person_1"),
        persons=[person, wife],
        events=events,
        media=media,
        dna_companies=[dna_company],
        dna_profiles=dna_profiles,
        dna_matches=dna_matches,
        dna_clusters=dna_clusters,
    )

    return project_data, person


def main():
    """Run the Person Editor demo."""
    app = QApplication(sys.argv)

    project_data, sample_person = create_sample_project()

    # Show the editor with an existing person
    editor = PersonEditor(project_data, person=sample_person)
    editor.setWindowTitle("Personredigerare — Demo (Erik Eriksson)")
    editor.resize(750, 600)
    editor.show()

    exit_code = app.exec()

    # Show result after close
    if editor.saved_person:
        print("\n✓ Person sparad:")
        p = editor.saved_person
        print(f"  ID:    {p.id}")
        print(f"  Kön:   {p.sex}")
        print(f"  Titel: {p.title}")
        print(f"  Yrke:  {p.occupation}")
        print(f"  Namn:  {len(p.names)} st")
        for n in p.names:
            print(f"    - {n.type}: {n.given} {n.surname}")
        print(f"  Anteckningar: {p.notes[:50]}..." if len(p.notes) > 50 else f"  Anteckningar: {p.notes}")
        print(f"  Profilbild:   {p.profile_media_id}")
    else:
        print("\n✗ Redigering avbruten (ingen person sparad)")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
