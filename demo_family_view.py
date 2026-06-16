"""Demo script to preview the Family View with fake genealogy data.

Run with: python demo_family_view.py
"""

import sys

from PySide6.QtWidgets import QApplication

from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef
from slaktbusken.model.family import Family, FamilyPartner
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.ui.diagram_panel import DiagramPanel
from slaktbusken.ui.main_window import ViewType


def create_demo_data() -> ProjectData:
    """Create a realistic Swedish family for demo purposes."""
    # --- Persons ---
    grandfather = Person(
        id="p0", sex="M",
        names=[Name(type="birth", given="Gustaf", surname="Andersson")],
        occupation="Lantbrukare",
    )
    grandmother = Person(
        id="p00", sex="F",
        names=[Name(type="birth", given="Kristina", surname="Nilsdotter")],
    )
    father = Person(
        id="p1", sex="M",
        names=[Name(type="birth", given="Erik", surname="Gustafsson")],
        occupation="Skomakare",
    )
    mother = Person(
        id="p2", sex="F",
        names=[Name(type="birth", given="Anna", surname="Karlsdotter")],
    )
    active = Person(
        id="p3", sex="M",
        names=[Name(type="birth", given="Karl", surname="Eriksson")],
        occupation="Snickare",
    )
    sibling1 = Person(
        id="p4", sex="F",
        names=[Name(type="birth", given="Lisa", surname="Eriksdotter")],
    )
    sibling2 = Person(
        id="p7", sex="M",
        names=[Name(type="birth", given="Johan", surname="Eriksson")],
    )
    partner = Person(
        id="p5", sex="F",
        names=[
            Name(type="birth", given="Maria", surname="Johansdotter"),
            Name(type="married", given="Maria", surname="Eriksson"),
        ],
    )
    child1 = Person(
        id="p6", sex="M",
        names=[Name(type="birth", given="Sven", surname="Karlsson")],
    )
    child2 = Person(
        id="p8", sex="F",
        names=[Name(type="birth", given="Brita", surname="Karlsdotter")],
    )

    persons = [grandfather, grandmother, father, mother, active,
               sibling1, sibling2, partner, child1, child2]

    # --- Places ---
    sweden = Place(id="pl1", type="country", name="Sverige")
    county = Place(id="pl2", type="county", name="Gävleborgs län", parent_place_id="pl1")
    parish = Place(id="pl3", type="parish", name="Ljusdal", parent_place_id="pl2")

    places = [sweden, county, parish]

    # --- Events ---
    events = [
        Event(
            id="e1", type="birth",
            participants=[Participant(person_id="p3", role="subject")],
            date=DateValue(value="1855-03-14", precision="day"),
            place=PlaceRef(place_id="pl3"),
        ),
        Event(
            id="e2", type="death",
            participants=[Participant(person_id="p3", role="subject")],
            date=DateValue(value="1923-11-02", precision="day"),
            place=PlaceRef(place_id="pl3"),
        ),
        Event(
            id="e3", type="birth",
            participants=[Participant(person_id="p1", role="subject")],
            date=DateValue(value="1825-07-20", precision="day"),
            place=PlaceRef(place_id="pl3"),
        ),
        Event(
            id="e4", type="death",
            participants=[Participant(person_id="p1", role="subject")],
            date=DateValue(value="1890-01-05", precision="day"),
        ),
        Event(
            id="e5", type="birth",
            participants=[Participant(person_id="p2", role="subject")],
            date=DateValue(value="1830-09-18", precision="day"),
        ),
        Event(
            id="e6", type="birth",
            participants=[Participant(person_id="p5", role="subject")],
            date=DateValue(value="1860-06-22", precision="day"),
        ),
        Event(
            id="e7", type="birth",
            participants=[Participant(person_id="p6", role="subject")],
            date=DateValue(value="1882-02-10", precision="day"),
            place=PlaceRef(place_id="pl3"),
        ),
        Event(
            id="e8", type="birth",
            participants=[Participant(person_id="p8", role="subject")],
            date=DateValue(value="1885-08-30", precision="day"),
            place=PlaceRef(place_id="pl3"),
        ),
        Event(
            id="e9", type="birth",
            participants=[Participant(person_id="p4", role="subject")],
            date=DateValue(value="1858-12-01", precision="day"),
        ),
        Event(
            id="e10", type="birth",
            participants=[Participant(person_id="p7", role="subject")],
            date=DateValue(value="1862-04-15", precision="day"),
        ),
        Event(
            id="e11", type="marriage",
            participants=[
                Participant(person_id="p3", role="husband"),
                Participant(person_id="p5", role="wife"),
            ],
            date=DateValue(value="1880-06-12", precision="day"),
            place=PlaceRef(place_id="pl3"),
        ),
    ]

    # --- Families ---
    # Grandparent family (father is a child here)
    grandparent_family = Family(
        id="f0",
        partners=[
            FamilyPartner(person_id="p0", role="father"),
            FamilyPartner(person_id="p00", role="mother"),
        ],
        children=["p1"],
    )

    # Parent family
    parent_family = Family(
        id="f1",
        partners=[
            FamilyPartner(person_id="p1", role="father"),
            FamilyPartner(person_id="p2", role="mother"),
        ],
        children=["p3", "p4", "p7"],
    )

    # Active person's own family
    own_family = Family(
        id="f2",
        partners=[
            FamilyPartner(person_id="p3", role="father"),
            FamilyPartner(person_id="p5", role="mother"),
        ],
        children=["p6", "p8"],
    )

    families = [grandparent_family, parent_family, own_family]

    return ProjectData(
        project=ProjectMetadata(title="Demo Släktträd", main_person_id="p3"),
        persons=persons,
        families=families,
        events=events,
        places=places,
    )


def main() -> None:
    """Launch a standalone window showing the Family View with demo data."""
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("Släktbusken – Demo")

    # Create the diagram panel
    panel = DiagramPanel()
    panel.setWindowTitle("Släktbusken – Familjevy (demo)")
    panel.resize(1100, 700)

    # Load demo data
    data = create_demo_data()
    config = PersonBoxConfig(
        name=True,
        birth_date=True,
        birth_place=True,
        death_date=True,
        death_place=False,
        marriage_date=True,
        occupation=True,
    )

    panel.set_project_data(data)
    panel.set_person_box_config(config)
    panel.switch_view(ViewType.FAMILY)
    panel.set_active_person("p3")

    panel.show()

    # Fit the scene in view after showing
    panel.view.resetTransform()
    panel.view.fitInView(panel.scene.sceneRect().adjusted(-50, -50, 50, 50))

    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
