"""Descendants view — renderar ättlingsdiagrammet.

Visar den aktiva personens ättlingar upp till ett konfigurerbart djup
(1-10, standard 4) i ett trädmönster. Aktiv person placeras till vänster
(generation 0), barn förgrenar sig åt höger (generation 1), barnbarn
längre åt höger (generation 2), osv.

Layout (vänster till höger):
    Gen 0: Aktiv person (centrerad vertikalt)
    Gen 1: Barn (fördelade vertikalt)
    Gen 2: Barnbarn
    ...upp till konfigurerat djup

Till skillnad från anordiagrammet (binärt träd) kan varje person ha
ett godtyckligt antal barn, vilket ger en trädstruktur med variabel
förgreningsfaktor.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QGraphicsScene, QGraphicsTextItem

from slaktbusken.model.family import Family
from slaktbusken.model.name_parser import ParsedGivenName, parse_given_name
from slaktbusken.model.person import Person
from slaktbusken.model.project import ProjectData
from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.ui.widgets.connection_line import ConnectionLineItem, ConnectionType
from slaktbusken.ui.widgets.person_box import PersonBoxItem, _BOX_WIDTH

logger = logging.getLogger(__name__)

# Layout-konstanter
_H_GAP = 60.0  # Horisontellt avstånd mellan generationskolumner
_V_GAP = 20.0  # Minimalt vertikalt avstånd mellan rutor
_BOX_HEIGHT_ESTIMATE = 70.0  # Uppskattad ruthöjd för layoutberäkning


class DescendantsView:
    """Renderar ättlingsdiagrammet i en QGraphicsScene.

    Visar den aktiva personens ättlingar i ett trädmönster med
    konfigurerat djup (1-10). Aktiv person till vänster, ättlingar
    förgrenar sig åt höger med ökande generationer.

    Attributes:
        selected_person_id: ID för den visuellt markerade personen.
    """

    def __init__(self) -> None:
        """Initialisera DescendantsView."""
        self.selected_person_id: Optional[str] = None
        self._person_boxes: list[PersonBoxItem] = []

    def render(
        self,
        scene: QGraphicsScene,
        project_data: ProjectData,
        active_person_id: str,
        config: PersonBoxConfig,
        depth: int = 4,
    ) -> None:
        """Rendera ättlingsdiagrammet i scenen.

        Args:
            scene: QGraphicsScene att populera.
            project_data: Projektdata med personer, familjer och händelser.
            active_person_id: ID för den aktiva personen.
            config: Konfiguration för personrutornas innehåll.
            depth: Antal generationer att visa (1-10, standard 4).
        """
        self._person_boxes = []

        # Begränsa djup till giltigt intervall
        depth = max(1, min(10, depth))

        person = _find_person(project_data, active_person_id)
        if person is None:
            logger.warning("Aktiv person %s hittades inte.", active_person_id)
            return

        # Samla in ättlingar
        descendants_by_gen = collect_descendants(project_data, active_person_id, depth)

        # Kontrollera om inga ättlingar hittades (inga barn alls)
        has_descendants = any(
            len(persons) > 0 for gen, persons in descendants_by_gen.items() if gen > 0
        )

        if not has_descendants:
            # Visa meddelande om inga ättlingar
            msg = QGraphicsTextItem("Inga ättlingar hittades")
            msg.setDefaultTextColor(msg.defaultTextColor())
            scene.addItem(msg)

            # Rendera ändå aktiv person
            display_data = _build_display_data(person, project_data)
            box = PersonBoxItem(active_person_id, display_data, config)
            box.setPos(0, 0)
            scene.addItem(box)
            self._person_boxes.append(box)
            box.setFlag(box.GraphicsItemFlag.ItemIsSelectable, True)

            msg.setPos(0, _BOX_HEIGHT_ESTIMATE + 20)
            return

        # Bygg layoutträd: beräkna antal ättlingar per generation
        # för att bestämma vertikala positioner
        # Vi behöver bygga ett träd med position-data
        tree = _build_layout_tree(project_data, active_person_id, depth)

        # Beräkna vertikal storlek för varje nod (antal löv under den)
        _compute_subtree_sizes(tree)

        # Tilldela vertikala positioner
        _assign_positions(tree, y_offset=0.0)

        # Rendera alla noder
        self._render_tree(scene, project_data, config, tree)

        # Rita anslutningslinjer
        self._render_connections(scene, tree)

    def _render_tree(
        self,
        scene: QGraphicsScene,
        project_data: ProjectData,
        config: PersonBoxConfig,
        node: _TreeNode,
    ) -> None:
        """Rendera alla noder i trädet rekursivt.

        Args:
            scene: Scenen att rendera i.
            project_data: Projektdata.
            config: PersonBoxConfig.
            node: Rotnoden att börja rendera från.
        """
        person = _find_person(project_data, node.person_id)
        if person is not None:
            display_data = _build_display_data(person, project_data)
            box = PersonBoxItem(node.person_id, display_data, config)
            box.setPos(node.x, node.y)
            scene.addItem(box)
            self._person_boxes.append(box)
            box.setFlag(box.GraphicsItemFlag.ItemIsSelectable, True)

        for child_node in node.children:
            self._render_tree(scene, project_data, config, child_node)

    def _render_connections(
        self,
        scene: QGraphicsScene,
        node: _TreeNode,
    ) -> None:
        """Rita anslutningslinjer mellan förälder och barn i trädet.

        Använder ortogonal routing: horisontell från förälder →
        vertikal midpunkt → horisontell till barn.

        Args:
            scene: Scenen att rita i.
            node: Aktuell nod att rita linjer från.
        """
        if not node.children:
            return

        # Förälderns mitt-höger
        parent_right_x = node.x + _BOX_WIDTH
        parent_mid_y = node.y + _BOX_HEIGHT_ESTIMATE / 2.0

        # Midpunkt X för vertikala segmentet
        mid_x = parent_right_x + _H_GAP / 2.0

        for child_node in node.children:
            child_left_x = child_node.x
            child_mid_y = child_node.y + _BOX_HEIGHT_ESTIMATE / 2.0

            # Segment 1: horisontell från förälder till midpunkt
            scene.addItem(ConnectionLineItem(
                QPointF(parent_right_x, parent_mid_y),
                QPointF(mid_x, parent_mid_y),
                ConnectionType.PARENT_CHILD,
            ))

            # Segment 2: vertikal från förälder-y till barn-y vid midpunkt
            scene.addItem(ConnectionLineItem(
                QPointF(mid_x, parent_mid_y),
                QPointF(mid_x, child_mid_y),
                ConnectionType.PARENT_CHILD,
            ))

            # Segment 3: horisontell från midpunkt till barn
            scene.addItem(ConnectionLineItem(
                QPointF(mid_x, child_mid_y),
                QPointF(child_left_x, child_mid_y),
                ConnectionType.PARENT_CHILD,
            ))

            # Rekursivt för barnets barn
            self._render_connections(scene, child_node)

    def handle_click(self, person_id: str) -> None:
        """Hantera klick på en personruta — markera visuellt.

        Avmarkerar alla andra rutor och markerar den klickade.

        Args:
            person_id: ID för den klickade personen.
        """
        self.selected_person_id = person_id
        for box in self._person_boxes:
            box.set_selected(box.person_id == person_id)

    def deselect_all(self) -> None:
        """Avmarkera alla personrutor."""
        self.selected_person_id = None
        for box in self._person_boxes:
            box.set_selected(False)

    def get_person_boxes(self) -> list[PersonBoxItem]:
        """Returnera alla personrutor i diagrammet.

        Returns:
            Lista med PersonBoxItem-instanser.
        """
        return list(self._person_boxes)


# ---------------------------------------------------------------------------
# Intern trädstruktur för layout
# ---------------------------------------------------------------------------


class _TreeNode:
    """Intern nod för layoutberäkning.

    Attributes:
        person_id: Personens ID.
        generation: Generationsnummer (0 = aktiv person).
        children: Lista med barnnoder.
        subtree_size: Antal löv i delträdet (för vertikal placering).
        x: Beräknad X-position.
        y: Beräknad Y-position.
    """

    __slots__ = ("person_id", "generation", "children", "subtree_size", "x", "y")

    def __init__(self, person_id: str, generation: int) -> None:
        """Skapa en trädnod.

        Args:
            person_id: Personens ID.
            generation: Generationsnummer.
        """
        self.person_id = person_id
        self.generation = generation
        self.children: list[_TreeNode] = []
        self.subtree_size: int = 1
        self.x: float = 0.0
        self.y: float = 0.0


def _build_layout_tree(
    project_data: ProjectData,
    person_id: str,
    depth: int,
) -> _TreeNode:
    """Bygg ett layoutträd för ättlingsdiagrammet.

    Traverserar ättlingar BFS och bygger ett träd med noder.
    Hanterar att en person kan förekomma i flera familjer som
    partner.

    Args:
        project_data: Projektdata.
        person_id: Startpersonens ID.
        depth: Maximalt djup att traversera.

    Returns:
        Rotnoden i layoutträdet.
    """
    root = _TreeNode(person_id, 0)
    visited: set[str] = {person_id}

    # BFS med nod-referens
    queue: list[_TreeNode] = [root]

    while queue:
        node = queue.pop(0)
        if node.generation >= depth:
            continue

        # Hitta alla barn till denna person
        children_ids = _find_children(project_data, node.person_id)

        for child_id in children_ids:
            if child_id in visited:
                continue  # Undvik cykler
            visited.add(child_id)
            child_node = _TreeNode(child_id, node.generation + 1)
            node.children.append(child_node)
            queue.append(child_node)

    return root


def _compute_subtree_sizes(node: _TreeNode) -> int:
    """Beräkna storleken på delträdet för vertikal layoutplanering.

    Storleken är antalet löv i delträdet (minst 1 för noden själv).

    Args:
        node: Noden att beräkna storlek för.

    Returns:
        Antal löv i delträdet.
    """
    if not node.children:
        node.subtree_size = 1
        return 1

    total = 0
    for child in node.children:
        total += _compute_subtree_sizes(child)
    node.subtree_size = total
    return total


def _assign_positions(node: _TreeNode, y_offset: float) -> None:
    """Tilldela X- och Y-positioner till alla noder i trädet.

    X bestäms av generationen, Y bestäms av delträdsstorlek.

    Args:
        node: Noden att tilldela positioner för.
        y_offset: Vertikalt startoffset.
    """
    # X-position baserat på generation
    node.x = node.generation * (_BOX_WIDTH + _H_GAP)

    if not node.children:
        # Löv: centrera i sin tilldelade plats
        node.y = y_offset
        return

    # Fördela barn vertikalt baserat på deras delträdsstorlek
    current_y = y_offset
    for child in node.children:
        child_height = child.subtree_size * (_BOX_HEIGHT_ESTIMATE + _V_GAP)
        _assign_positions(child, current_y)
        current_y += child_height

    # Centrera föräldern vertikalt mellan sina barns spann
    first_child_y = node.children[0].y
    last_child_y = node.children[-1].y
    node.y = (first_child_y + last_child_y) / 2.0


# ---------------------------------------------------------------------------
# Ren datainsamling för property-based testing
# ---------------------------------------------------------------------------


def collect_descendants(
    project_data: ProjectData,
    person_id: str,
    depth: int,
) -> dict[int, set[str]]:
    """Samla in ättlingar för en person upp till angivet djup.

    Returnerar en dictionary från generationsnummer till mängden av
    person-ID:n vid den generationen. Generation 0 innehåller
    startpersonen, generation 1 innehåller barn, osv.

    Denna funktion är den rena datainsamlingslogiken som testats
    via property-based tests (Property 13).

    Args:
        project_data: Projektdata med familjer och personer.
        person_id: ID för startpersonen.
        depth: Antal generationer att samla in (1-10).

    Returns:
        Dictionary med generationsnummer -> mängd av person-ID:n.
    """
    depth = max(1, min(10, depth))

    result: dict[int, set[str]] = {0: {person_id}}
    visited: set[str] = {person_id}

    # BFS: (person_id, generation)
    queue: list[tuple[str, int]] = [(person_id, 0)]

    while queue:
        pid, gen = queue.pop(0)
        if gen >= depth:
            continue

        next_gen = gen + 1
        if next_gen not in result:
            result[next_gen] = set()

        children_ids = _find_children(project_data, pid)
        for child_id in children_ids:
            if child_id in visited:
                continue  # Undvik cykler/dubbletter
            visited.add(child_id)
            result[next_gen].add(child_id)
            queue.append((child_id, next_gen))

    return result


# ---------------------------------------------------------------------------
# Hjälpfunktioner
# ---------------------------------------------------------------------------


def _find_person(project_data: ProjectData, person_id: str) -> Optional[Person]:
    """Hitta en person via ID i projektdata.

    Args:
        project_data: Projektdata att söka i.
        person_id: ID att söka efter.

    Returns:
        Person-instansen eller None om ej hittad.
    """
    for p in project_data.persons:
        if p.id == person_id:
            return p
    return None


def _find_children(project_data: ProjectData, person_id: str) -> list[str]:
    """Hitta alla barn till en person.

    Söker genom alla familjer där personen är en partner och
    samlar ihop barnens ID:n.

    Args:
        project_data: Projektdata att söka i.
        person_id: ID för föräldern.

    Returns:
        Lista med barn-ID:n (kan vara tom).
    """
    children: list[str] = []
    for family in project_data.families:
        is_partner = any(
            partner.person_id == person_id for partner in family.partners
        )
        if is_partner:
            for child_id in family.children:
                if child_id not in children:
                    children.append(child_id)
    return children


def _build_display_data(
    person: Person, project_data: ProjectData
) -> dict:
    """Bygg display_data-dictionary för en person.

    Extraherar namn, födelse-/dödsdatum och -plats från personens
    händelser.

    Args:
        person: Personobjektet.
        project_data: Projektdata för att hämta händelser och platser.

    Returns:
        Dictionary med nycklar som matchar PersonBoxConfig-fält.
    """
    display_name, name_parsed = _get_display_name_and_parsed(person)
    data: dict = {
        "name": display_name,
        "name_parsed": name_parsed,
        "birth_date": None,
        "birth_place": None,
        "death_date": None,
        "death_place": None,
        "marriage_date": None,
        "marriage_place": None,
        "occupation": person.occupation,
        "dna_info": None,
        "notes": person.notes if person.notes else None,
    }

    for event in project_data.events:
        is_participant = any(
            p.person_id == person.id for p in event.participants
        )
        if not is_participant:
            continue

        if event.type == "birth":
            if event.date:
                data["birth_date"] = event.date.value
            if event.place:
                place = _find_place(project_data, event.place.place_id)
                if place:
                    data["birth_place"] = place.name
        elif event.type == "death":
            if event.date:
                data["death_date"] = event.date.value
            if event.place:
                place = _find_place(project_data, event.place.place_id)
                if place:
                    data["death_place"] = place.name
        elif event.type == "marriage":
            if event.date:
                data["marriage_date"] = event.date.value
            if event.place:
                place = _find_place(project_data, event.place.place_id)
                if place:
                    data["marriage_place"] = place.name

    return data


def _get_display_name(person: Person) -> str:
    """Formatera personens visningsnamn.

    Args:
        person: Personobjektet.

    Returns:
        Formaterat namn som "Förnamn Efternamn", eller "(okänd)".
    """
    display_name, _ = _get_display_name_and_parsed(person)
    return display_name


def _get_display_name_and_parsed(
    person: Person,
) -> tuple[str, Optional[ParsedGivenName]]:
    """Formatera personens visningsnamn och returnera parsed given name.

    Använder det första namnet i listan (typ "birth" prioriteras).
    Anropar parse_given_name() för att ta bort asterisk-markör och
    identifiera tilltalsnamn.

    Args:
        person: Personobjektet.

    Returns:
        Tuple med (visningsnamn, ParsedGivenName eller None).
    """
    if not person.names:
        return "(okänd)", None

    name = person.names[0]
    for n in person.names:
        if n.type == "birth":
            name = n
            break

    parsed: Optional[ParsedGivenName] = None
    given_display = name.given

    if name.given:
        try:
            parsed = parse_given_name(name.given)
            given_display = parsed.display_string
        except (ValueError, Exception):
            # Fall back to raw string without underline on parse failure
            given_display = name.given.replace("*", "")
            parsed = None

    parts = []
    if given_display:
        parts.append(given_display)
    if name.surname:
        parts.append(name.surname)
    display_name = " ".join(parts) if parts else "(okänd)"
    return display_name, parsed


def _find_place(project_data: ProjectData, place_id: str):
    """Hitta en plats via ID.

    Args:
        project_data: Projektdata att söka i.
        place_id: Plats-ID.

    Returns:
        Place-objektet eller None.
    """
    for place in project_data.places:
        if place.id == place_id:
            return place
    return None
