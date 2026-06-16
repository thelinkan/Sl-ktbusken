"""Familjevy — renderar familjeträdsdiagrammet.

Visar den aktiva personen med föräldrar, syskon, partner och barn
i en överskådlig diagramvy. Hanterar klick, dubbelklick och
tangentbordsinteraktion (A-tangenten) för navigation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QGraphicsScene

from slaktbusken.model.family import Family, FamilyPartner
from slaktbusken.model.person import Person
from slaktbusken.model.project import ProjectData
from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.ui.widgets.connection_line import ConnectionLineItem, ConnectionType
from slaktbusken.ui.widgets.person_box import PersonBoxItem
from slaktbusken.ui.widgets.placeholder_box import PlaceholderBoxItem, PlaceholderRole

if TYPE_CHECKING:
    from slaktbusken.model.event import Event

logger = logging.getLogger(__name__)

# Layout constants
_BOX_WIDTH = 180.0
_BOX_HEIGHT = 50.0
_H_SPACING = 30.0  # Horizontal spacing between boxes
_V_SPACING = 80.0  # Vertical spacing between rows
_SIBLING_SPACING = 20.0  # Spacing between sibling boxes


class FamilyView:
    """Renderar familjediagrammet i en QGraphicsScene.

    Visar den aktiva personen centralt med föräldrar ovanför,
    syskon bredvid, partner till höger/vänster och barn nedanför.
    Hanterar interaktion via klick, dubbelklick och tangentbord.

    Attributes:
        selected_person_id: ID för den visuellt markerade personen.
    """

    def __init__(self) -> None:
        """Initialisera FamilyView."""
        self.selected_person_id: Optional[str] = None
        self._person_boxes: list[PersonBoxItem] = []
        self._placeholder_boxes: list[PlaceholderBoxItem] = []

    def render(
        self,
        scene: QGraphicsScene,
        project_data: ProjectData,
        active_person_id: str,
        config: PersonBoxConfig,
    ) -> None:
        """Rendera familjediagrammet i scenen.

        Populerar scenen med personrutor, platshållare och
        förbindelselinjer för den aktiva personens familj.

        Args:
            scene: QGraphicsScene att populera.
            project_data: Projektdata med personer, familjer och händelser.
            active_person_id: ID för den aktiva personen.
            config: Konfiguration för personrutornas innehåll.
        """
        self._person_boxes = []
        self._placeholder_boxes = []

        person = _find_person(project_data, active_person_id)
        if person is None:
            logger.warning("Aktiv person %s hittades inte.", active_person_id)
            return

        # Find the family where active person is a child (parent family)
        parent_family = _find_parent_family(project_data, active_person_id)

        # Find all families where active person is a partner
        partner_families = _find_partner_families(project_data, active_person_id)

        # --- Layout calculations ---
        # Row 0: Parents (top)
        # Row 1: Active person + siblings (middle)
        # Row 2: Partners beside active person + children (bottom)

        # Middle row: active person and siblings
        siblings: list[str] = []
        if parent_family:
            siblings = [
                cid for cid in parent_family.children if cid != active_person_id
            ]

        # Calculate middle row positioning
        middle_persons = [active_person_id] + siblings
        middle_count = len(middle_persons)
        middle_total_width = (
            middle_count * _BOX_WIDTH + (middle_count - 1) * _SIBLING_SPACING
        )
        middle_start_x = -middle_total_width / 2.0
        middle_y = 0.0

        # Place active person and siblings
        active_box: Optional[PersonBoxItem] = None
        active_x = middle_start_x
        for i, pid in enumerate(middle_persons):
            x = middle_start_x + i * (_BOX_WIDTH + _SIBLING_SPACING)
            p = _find_person(project_data, pid)
            if p is None:
                continue
            display_data = _build_display_data(p, project_data)
            box = PersonBoxItem(pid, display_data, config)
            box.setPos(x, middle_y)
            scene.addItem(box)
            self._person_boxes.append(box)
            if pid == active_person_id:
                active_box = box
                active_x = x

        # --- Parents row (above) ---
        parent_y = middle_y - _V_SPACING - _BOX_HEIGHT
        father_x = active_x - (_BOX_WIDTH + _H_SPACING) / 2.0
        mother_x = active_x + (_BOX_WIDTH + _H_SPACING) / 2.0

        father_id: Optional[str] = None
        mother_id: Optional[str] = None

        if parent_family:
            for partner in parent_family.partners:
                if partner.role == "father":
                    father_id = partner.person_id
                elif partner.role == "mother":
                    mother_id = partner.person_id

        # Father box or placeholder
        father_center_bottom: Optional[QPointF] = None
        if father_id:
            p = _find_person(project_data, father_id)
            if p:
                display_data = _build_display_data(p, project_data)
                box = PersonBoxItem(father_id, display_data, config)
                box.setPos(father_x, parent_y)
                scene.addItem(box)
                self._person_boxes.append(box)
                father_center_bottom = QPointF(
                    father_x + _BOX_WIDTH / 2.0, parent_y + _BOX_HEIGHT
                )
        else:
            placeholder = PlaceholderBoxItem(
                PlaceholderRole.FATHER,
                family_id=parent_family.id if parent_family else None,
            )
            placeholder.setPos(father_x, parent_y)
            scene.addItem(placeholder)
            self._placeholder_boxes.append(placeholder)
            father_center_bottom = QPointF(
                father_x + _BOX_WIDTH / 2.0, parent_y + _BOX_HEIGHT
            )

        # Mother box or placeholder
        mother_center_bottom: Optional[QPointF] = None
        if mother_id:
            p = _find_person(project_data, mother_id)
            if p:
                display_data = _build_display_data(p, project_data)
                box = PersonBoxItem(mother_id, display_data, config)
                box.setPos(mother_x, parent_y)
                scene.addItem(box)
                self._person_boxes.append(box)
                mother_center_bottom = QPointF(
                    mother_x + _BOX_WIDTH / 2.0, parent_y + _BOX_HEIGHT
                )
        else:
            placeholder = PlaceholderBoxItem(
                PlaceholderRole.MOTHER,
                family_id=parent_family.id if parent_family else None,
            )
            placeholder.setPos(mother_x, parent_y)
            scene.addItem(placeholder)
            self._placeholder_boxes.append(placeholder)
            mother_center_bottom = QPointF(
                mother_x + _BOX_WIDTH / 2.0, parent_y + _BOX_HEIGHT
            )

        # Partner connection between parents
        if father_center_bottom and mother_center_bottom:
            partner_line_y = parent_y + _BOX_HEIGHT / 2.0
            start_pt = QPointF(father_x + _BOX_WIDTH, partner_line_y)
            end_pt = QPointF(mother_x, partner_line_y)
            line = ConnectionLineItem(start_pt, end_pt, ConnectionType.PARTNER)
            scene.addItem(line)

        # Connection from parents down to active person
        active_top_center = QPointF(
            active_x + _BOX_WIDTH / 2.0, middle_y
        )
        if father_center_bottom:
            line = ConnectionLineItem(
                father_center_bottom, active_top_center, ConnectionType.PARENT_CHILD
            )
            scene.addItem(line)
        if mother_center_bottom:
            line = ConnectionLineItem(
                mother_center_bottom, active_top_center, ConnectionType.PARENT_CHILD
            )
            scene.addItem(line)

        # Connections to siblings
        for i, pid in enumerate(siblings):
            sib_x = middle_start_x + (i + 1) * (_BOX_WIDTH + _SIBLING_SPACING)
            sib_top_center = QPointF(sib_x + _BOX_WIDTH / 2.0, middle_y)
            if father_center_bottom:
                line = ConnectionLineItem(
                    father_center_bottom, sib_top_center, ConnectionType.PARENT_CHILD
                )
                scene.addItem(line)
            if mother_center_bottom:
                line = ConnectionLineItem(
                    mother_center_bottom, sib_top_center, ConnectionType.PARENT_CHILD
                )
                scene.addItem(line)

        # --- Partners and children (below) ---
        partner_y = middle_y + _BOX_HEIGHT + _V_SPACING
        children_y = partner_y + _BOX_HEIGHT + _V_SPACING

        partner_offset_x = active_x + _BOX_WIDTH + _H_SPACING * 2

        for fam_idx, family in enumerate(partner_families):
            # Find partner(s) in this family (not active person)
            other_partners = [
                fp for fp in family.partners if fp.person_id != active_person_id
            ]

            # Place partner boxes
            for p_idx, fp in enumerate(other_partners):
                px = partner_offset_x + (fam_idx + p_idx) * (_BOX_WIDTH + _H_SPACING)
                p = _find_person(project_data, fp.person_id)
                if p:
                    display_data = _build_display_data(p, project_data)
                    box = PersonBoxItem(fp.person_id, display_data, config)
                    box.setPos(px, middle_y)
                    scene.addItem(box)
                    self._person_boxes.append(box)

                    # Partner connection line
                    active_right = QPointF(
                        active_x + _BOX_WIDTH, middle_y + _BOX_HEIGHT / 2.0
                    )
                    partner_left = QPointF(px, middle_y + _BOX_HEIGHT / 2.0)
                    line = ConnectionLineItem(
                        active_right, partner_left, ConnectionType.PARTNER
                    )
                    scene.addItem(line)

            # Children of this family
            children_ids = family.children
            child_count = len(children_ids)
            # Also add a placeholder for adding new child
            total_child_slots = child_count + 1  # +1 for placeholder

            # Center children below active person and partner area
            child_area_x = active_x
            for c_idx, child_id in enumerate(children_ids):
                cx = child_area_x + (
                    (fam_idx * (total_child_slots)) + c_idx
                ) * (_BOX_WIDTH + _SIBLING_SPACING)
                cp = _find_person(project_data, child_id)
                if cp:
                    display_data = _build_display_data(cp, project_data)
                    box = PersonBoxItem(child_id, display_data, config)
                    box.setPos(cx, children_y)
                    scene.addItem(box)
                    self._person_boxes.append(box)

                    # Connection from active person to child
                    active_bottom_center = QPointF(
                        active_x + _BOX_WIDTH / 2.0, middle_y + _BOX_HEIGHT
                    )
                    child_top_center = QPointF(cx + _BOX_WIDTH / 2.0, children_y)
                    line = ConnectionLineItem(
                        active_bottom_center,
                        child_top_center,
                        ConnectionType.PARENT_CHILD,
                    )
                    scene.addItem(line)

            # Placeholder for new child
            placeholder_cx = child_area_x + (
                (fam_idx * (total_child_slots)) + child_count
            ) * (_BOX_WIDTH + _SIBLING_SPACING)
            placeholder = PlaceholderBoxItem(
                PlaceholderRole.CHILD, family_id=family.id
            )
            placeholder.setPos(placeholder_cx, children_y)
            scene.addItem(placeholder)
            self._placeholder_boxes.append(placeholder)

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

    def get_placeholder_boxes(self) -> list[PlaceholderBoxItem]:
        """Returnera alla platshållarrutor i diagrammet.

        Returns:
            Lista med PlaceholderBoxItem-instanser.
        """
        return list(self._placeholder_boxes)


# ---------------------------------------------------------------------------
# Helper functions
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


def _find_parent_family(
    project_data: ProjectData, person_id: str
) -> Optional[Family]:
    """Hitta familjen där personen är ett barn.

    Args:
        project_data: Projektdata att söka i.
        person_id: ID för barnet.

    Returns:
        Den familj där personen förekommer som barn, eller None.
    """
    for family in project_data.families:
        if person_id in family.children:
            return family
    return None


def _find_partner_families(
    project_data: ProjectData, person_id: str
) -> list[Family]:
    """Hitta alla familjer där personen är partner.

    Args:
        project_data: Projektdata att söka i.
        person_id: ID för partnern.

    Returns:
        Lista med familjer där personen ingår som partner.
    """
    families: list[Family] = []
    for family in project_data.families:
        for partner in family.partners:
            if partner.person_id == person_id:
                families.append(family)
                break
    return families


def _build_display_data(
    person: Person, project_data: ProjectData
) -> dict[str, Optional[str]]:
    """Bygg display_data-dictionary för en person.

    Extraherar namn, födelse-/dödsdatum och -plats från personens
    händelser för att visa i personrutan.

    Args:
        person: Personobjektet.
        project_data: Projektdata för att hämta händelser och platser.

    Returns:
        Dictionary med nycklar som matchar PersonBoxConfig-fält.
    """
    data: dict[str, Optional[str]] = {
        "name": _get_display_name(person),
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

    # Find birth and death events for this person
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

    Använder det första namnet i listan (typ "birth" prioriteras).

    Args:
        person: Personobjektet.

    Returns:
        Formaterat namn som "Förnamn Efternamn", eller "(okänd)".
    """
    if not person.names:
        return "(okänd)"

    # Prefer birth name
    name = person.names[0]
    for n in person.names:
        if n.type == "birth":
            name = n
            break

    parts = []
    if name.given:
        parts.append(name.given)
    if name.surname:
        parts.append(name.surname)
    return " ".join(parts) if parts else "(okänd)"


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
