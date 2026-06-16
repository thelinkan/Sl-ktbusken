"""Demo script for the Ancestry View.

Builds a 5-generation family tree and displays it in the AncestryView
diagram using PySide6. Includes a deliberate gap (missing maternal
grandmother) to demonstrate that deeper known ancestors still render.

Run:
    python demo_ancestry.py
"""

import sys

from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef
from slaktbusken.model.family import Family, FamilyPartner
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.ui.diagram_panel import DiagramPanel, ZoomableGraphicsView
from slaktbusken.ui.views.ancestry_view import AncestryView

from PySide6.QtWidgets import QGraphicsScene


def build_demo_data() -> tuple[ProjectData, str]:
    """Build a 5-generation family tree with realistic Swedish names.

    Generation 0: Erik Lindström (active person)
    Generation 1: Karl Lindström (father), Anna Berggren (mother)
    Generation 2: Gustaf Lindström (paternal grandfather), Maria Svensson (paternal grandmother)
                  Johan Berggren (maternal grandfather), [UNKNOWN] (maternal grandmother - gap!)
    Generation 3: Olof Lindström (pat. great-grandfather), Kristina Holm (pat. great-grandmother)
                  Anders Svensson (pat. great-grandfather), Brita Nilsson (pat. great-grandmother)
                  Per Berggren (mat. great-grandfather), Stina Eriksson (mat. great-grandmother)
    Generation 4: Lars Lindström (pat. 2x-great-grandfather), Margareta Dahl (pat. 2x-great-grandmother)
    """

    persons = [
        # Gen 0
        Person(id="p1", sex="M", names=[Name(type="birth", given="Erik", surname="Lindström")]),
        # Gen 1
        Person(id="p2", sex="M", names=[Name(type="birth", given="Karl", surname="Lindström")]),
        Person(id="p3", sex="F", names=[Name(type="birth", given="Anna", surname="Berggren")]),
        # Gen 2
        Person(id="p4", sex="M", names=[Name(type="birth", given="Gustaf", surname="Lindström")]),
        Person(id="p5", sex="F", names=[Name(type="birth", given="Maria", surname="Svensson")]),
        Person(id="p6", sex="M", names=[Name(type="birth", given="Johan", surname="Berggren")]),
        # p7 would be maternal grandmother — deliberately missing (gap)
        # Gen 3
        Person(id="p8", sex="M", names=[Name(type="birth", given="Olof", surname="Lindström")]),
        Person(id="p9", sex="F", names=[Name(type="birth", given="Kristina", surname="Holm")]),
        Person(id="p10", sex="M", names=[Name(type="birth", given="Anders", surname="Svensson")]),
        Person(id="p11", sex="F", names=[Name(type="birth", given="Brita", surname="Nilsson")]),
        Person(id="p12", sex="M", names=[Name(type="birth", given="Per", surname="Berggren")]),
        Person(id="p13", sex="F", names=[Name(type="birth", given="Stina", surname="Eriksson")]),
        # Gen 4 (only on paternal line)
        Person(id="p14", sex="M", names=[Name(type="birth", given="Lars", surname="Lindström")]),
        Person(id="p15", sex="F", names=[Name(type="birth", given="Margareta", surname="Dahl")]),
    ]

    families = [
        # Erik's parents: Karl + Anna
        Family(id="f1", partners=[
            FamilyPartner(person_id="p2", role="father"),
            FamilyPartner(person_id="p3", role="mother"),
        ], children=["p1"]),
        # Karl's parents: Gustaf + Maria
        Family(id="f2", partners=[
            FamilyPartner(person_id="p4", role="father"),
            FamilyPartner(person_id="p5", role="mother"),
        ], children=["p2"]),
        # Anna's parents: Johan + [unknown] — only father known
        Family(id="f3", partners=[
            FamilyPartner(person_id="p6", role="father"),
        ], children=["p3"]),
        # Gustaf's parents: Olof + Kristina
        Family(id="f4", partners=[
            FamilyPartner(person_id="p8", role="father"),
            FamilyPartner(person_id="p9", role="mother"),
        ], children=["p4"]),
        # Maria's parents: Anders + Brita
        Family(id="f5", partners=[
            FamilyPartner(person_id="p10", role="father"),
            FamilyPartner(person_id="p11", role="mother"),
        ], children=["p5"]),
        # Johan's parents: Per + Stina
        Family(id="f6", partners=[
            FamilyPartner(person_id="p12", role="father"),
            FamilyPartner(person_id="p13", role="mother"),
        ], children=["p6"]),
        # Olof's parents: Lars + Margareta (gen 4)
        Family(id="f7", partners=[
            FamilyPartner(person_id="p14", role="father"),
            FamilyPartner(person_id="p15", role="mother"),
        ], children=["p8"]),
    ]

    # Some events for richer display
    places = [
        Place(id="pl1", type="parish", name="Ljusdal"),
        Place(id="pl2", type="parish", name="Hudiksvall"),
    ]

    events = [
        Event(id="e1", type="birth", participants=[Participant(person_id="p1", role="child")],
              date=DateValue(value="1985-03-15", precision="day"),
              place=PlaceRef(place_id="pl1")),
        Event(id="e2", type="birth", participants=[Participant(person_id="p2", role="child")],
              date=DateValue(value="1955-07-20", precision="day"),
              place=PlaceRef(place_id="pl1")),
        Event(id="e3", type="birth", participants=[Participant(person_id="p3", role="child")],
              date=DateValue(value="1958-11-02", precision="day"),
              place=PlaceRef(place_id="pl2")),
        Event(id="e4", type="birth", participants=[Participant(person_id="p4", role="child")],
              date=DateValue(value="1925-04-10", precision="day")),
        Event(id="e5", type="death", participants=[Participant(person_id="p8", role="principal")],
              date=DateValue(value="1960-12-01", precision="day")),
        Event(id="e6", type="birth", participants=[Participant(person_id="p14", role="child")],
              date=DateValue(value="1850", precision="year")),
    ]

    project_data = ProjectData(
        project=ProjectMetadata(title="Demo Ancestry", main_person_id="p1"),
        persons=persons,
        families=families,
        places=places,
        events=events,
    )

    return project_data, "p1"


def main():
    app = QApplication(sys.argv)

    project_data, active_id = build_demo_data()

    # Config showing name + birth/death dates + birth place
    config = PersonBoxConfig(
        name=True,
        birth_date=True,
        birth_place=True,
        death_date=True,
        death_place=False,
        marriage_date=False,
        marriage_place=False,
        occupation=False,
        photo=False,
        dna_info=False,
        notes=False,
    )

    # Create a window with the ancestry view
    window = QMainWindow()
    window.setWindowTitle("Släktbusken — Anorvy (Demo, 5 generationer)")
    window.resize(1400, 800)

    scene = QGraphicsScene()
    view = ZoomableGraphicsView(scene)

    central = QWidget()
    layout = QVBoxLayout(central)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(view)
    window.setCentralWidget(central)

    # Render the ancestry view with depth 5
    ancestry_view = AncestryView()
    ancestry_view.render(scene, project_data, active_id, config, depth=5)

    print(f"Rendered {len(ancestry_view.get_person_boxes())} person boxes")
    print(f"Rendered {len(ancestry_view.get_placeholder_boxes())} placeholder boxes")
    print()
    print("Tree structure:")
    print("  Gen 0: Erik Lindström")
    print("  Gen 1: Karl Lindström (far), Anna Berggren (mor)")
    print("  Gen 2: Gustaf Lindström, Maria Svensson, Johan Berggren, [SAKNAS - mormor]")
    print("  Gen 3: Olof Lindström, Kristina Holm, Anders Svensson, Brita Nilsson,")
    print("          Per Berggren, Stina Eriksson")
    print("  Gen 4: Lars Lindström, Margareta Dahl (only on Olof's line)")
    print()
    print("Note the gap at Gen 2 (maternal grandmother unknown).")
    print("Johan Berggren's parents (Gen 3) are still rendered despite the gap.")
    print()
    print("Controls:")
    print("  Mouse wheel = zoom (25%–400%)")
    print("  Drag = pan")
    print("  Click = select person box")

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
