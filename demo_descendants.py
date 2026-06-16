"""Demo script for the Descendants View — 5 generations.

Shows a family tree starting with 'Erik Johansson' as the root,
branching out through 5 generations of descendants. Launches a
PySide6 window displaying the descendants diagram.

Usage:
    python demo_descendants.py
"""

import sys

from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from slaktbusken.model.family import Family, FamilyPartner
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.ui.diagram_panel import DiagramPanel


def build_demo_data() -> tuple[ProjectData, str]:
    """Build a 5-generation family tree for demo purposes.

    Returns:
        Tuple of (ProjectData, active_person_id).
    """
    persons: list[Person] = []
    families: list[Family] = []

    def make_person(pid: str, given: str, surname: str, sex: str) -> Person:
        p = Person(
            id=pid,
            sex=sex,
            names=[Name(type="birth", given=given, surname=surname)],
        )
        persons.append(p)
        return p

    # --- Generation 0: Root ---
    root = make_person("p1", "Erik", "Johansson", "M")

    # --- Generation 1: Erik's children (3 children) ---
    anna = make_person("p2", "Anna", "Eriksdotter", "F")
    lars = make_person("p3", "Lars", "Eriksson", "M")
    karin = make_person("p4", "Karin", "Eriksdotter", "F")

    families.append(Family(
        id="f1",
        partners=[FamilyPartner(person_id="p1", role="father")],
        children=["p2", "p3", "p4"],
    ))

    # --- Generation 2: Anna's children (2) ---
    gustav = make_person("p5", "Gustav", "Andersson", "M")
    maria = make_person("p6", "Maria", "Andersson", "F")

    families.append(Family(
        id="f2",
        partners=[FamilyPartner(person_id="p2", role="mother")],
        children=["p5", "p6"],
    ))

    # --- Generation 2: Lars' children (3) ---
    olof = make_person("p7", "Olof", "Larsson", "M")
    brita = make_person("p8", "Brita", "Larsdotter", "F")
    per = make_person("p9", "Per", "Larsson", "M")

    families.append(Family(
        id="f3",
        partners=[FamilyPartner(person_id="p3", role="father")],
        children=["p7", "p8", "p9"],
    ))

    # --- Generation 2: Karin's children (1) ---
    sven = make_person("p10", "Sven", "Nilsson", "M")

    families.append(Family(
        id="f4",
        partners=[FamilyPartner(person_id="p4", role="mother")],
        children=["p10"],
    ))

    # --- Generation 3: Gustav's children (2) ---
    make_person("p11", "Johan", "Gustavsson", "M")
    make_person("p12", "Eva", "Gustavsdotter", "F")

    families.append(Family(
        id="f5",
        partners=[FamilyPartner(person_id="p5", role="father")],
        children=["p11", "p12"],
    ))

    # --- Generation 3: Maria's child (1) ---
    make_person("p13", "Karl", "Pettersson", "M")

    families.append(Family(
        id="f6",
        partners=[FamilyPartner(person_id="p6", role="mother")],
        children=["p13"],
    ))

    # --- Generation 3: Olof's children (2) ---
    make_person("p14", "Anders", "Olofsson", "M")
    make_person("p15", "Stina", "Olofsdotter", "F")

    families.append(Family(
        id="f7",
        partners=[FamilyPartner(person_id="p7", role="father")],
        children=["p14", "p15"],
    ))

    # --- Generation 3: Per's children (1) ---
    make_person("p16", "Nils", "Persson", "M")

    families.append(Family(
        id="f8",
        partners=[FamilyPartner(person_id="p9", role="father")],
        children=["p16"],
    ))

    # --- Generation 3: Sven's children (2) ---
    make_person("p17", "Erik", "Svensson", "M")
    make_person("p18", "Maja", "Svensdotter", "F")

    families.append(Family(
        id="f9",
        partners=[FamilyPartner(person_id="p10", role="father")],
        children=["p17", "p18"],
    ))

    # --- Generation 4: Johan's children (2) ---
    make_person("p19", "Axel", "Johansson", "M")
    make_person("p20", "Elsa", "Johansdotter", "F")

    families.append(Family(
        id="f10",
        partners=[FamilyPartner(person_id="p11", role="father")],
        children=["p19", "p20"],
    ))

    # --- Generation 4: Anders' child (1) ---
    make_person("p21", "Gunnar", "Andersson", "M")

    families.append(Family(
        id="f11",
        partners=[FamilyPartner(person_id="p14", role="father")],
        children=["p21"],
    ))

    # --- Generation 4: Erik Svensson's children (3) ---
    make_person("p22", "Ingrid", "Eriksdotter", "F")
    make_person("p23", "Bengt", "Eriksson", "M")
    make_person("p24", "Sigrid", "Eriksdotter", "F")

    families.append(Family(
        id="f12",
        partners=[FamilyPartner(person_id="p17", role="father")],
        children=["p22", "p23", "p24"],
    ))

    # --- Generation 4: Karl's children (1) ---
    make_person("p25", "Helga", "Karlsdotter", "F")

    families.append(Family(
        id="f13",
        partners=[FamilyPartner(person_id="p13", role="father")],
        children=["p25"],
    ))

    # --- Generation 5: Axel's child (1) ---
    make_person("p26", "Stig", "Axelsson", "M")

    families.append(Family(
        id="f14",
        partners=[FamilyPartner(person_id="p19", role="father")],
        children=["p26"],
    ))

    # --- Generation 5: Ingrid's children (2) ---
    make_person("p27", "Lena", "Bergström", "F")
    make_person("p28", "Torbjörn", "Bergström", "M")

    families.append(Family(
        id="f15",
        partners=[FamilyPartner(person_id="p22", role="mother")],
        children=["p27", "p28"],
    ))

    project_data = ProjectData(
        project=ProjectMetadata(title="Demo — Ättlingar 5 generationer"),
        persons=persons,
        families=families,
    )

    return project_data, root.id


class DemoWindow(QMainWindow):
    """Simple window wrapping a DiagramPanel for the demo."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Släktbusken — Ättlingsvy (5 generationer)")
        self.resize(1400, 900)

        # Build data
        project_data, active_person_id = build_demo_data()

        # Config: show name + birth/death dates
        config = PersonBoxConfig(
            name=True,
            birth_date=True,
            death_date=True,
        )

        # Create diagram panel
        self._panel = DiagramPanel()
        self._panel.set_project_data(project_data)
        self._panel.set_person_box_config(config)

        # Switch to descendants view with depth 5
        from slaktbusken.ui.main_window import ViewType
        from slaktbusken.persistence.settings_io import DiagramSettings

        settings = DiagramSettings(descendants_depth=5)
        self._panel.set_diagram_settings(settings)
        self._panel.switch_view(ViewType.DESCENDANTS)
        self._panel.set_active_person(active_person_id)

        # Set as central widget
        self.setCentralWidget(self._panel)


def main() -> None:
    """Launch the demo window."""
    app = QApplication(sys.argv)
    window = DemoWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
