"""Familjevy — renderar familjeträdsdiagrammet.

Visar den aktiva personen med föräldrar, syskon, partner och barn
i en överskådlig diagramvy. Hanterar klick, dubbelklick och
tangentbordsinteraktion (A-tangenten) för navigation.

Layout (uppifrån och ned):
    Row 0: Far ——— Mor  (horisontell partnerlinje, centrerad ovanför syskonlinjen)
           |
    Row 1: Horisontell syskonlinje med vertikala droppar ned till varje syskon
           Aktiv person | Syskon1 | Syskon2 ...
    Row 2: Under varje syskon: Make/Maka (vertikal koppling)
    Row 3+: Under make/maka: Barn (staplade vertikalt)
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QGraphicsScene

from slaktbusken.model.family import Family
from slaktbusken.model.name_parser import ParsedGivenName, parse_given_name
from slaktbusken.model.person import Person
from slaktbusken.model.project import ProjectData
from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.ui.widgets.connection_line import ConnectionLineItem, ConnectionType
from slaktbusken.ui.widgets.person_box import PersonBoxItem, _BOX_WIDTH
from slaktbusken.ui.widgets.placeholder_box import PlaceholderBoxItem, PlaceholderRole

logger = logging.getLogger(__name__)

# Layout constants
_H_GAP = 40.0  # Horizontal gap between sibling columns
_V_GAP = 50.0  # Vertical gap between rows
_PARENT_GAP = 50.0  # Horizontal gap between father and mother boxes
_CHILD_V_GAP = 20.0  # Vertical gap between stacked children
_BAR_DROP = 25.0  # Distance from parent bottom / sibling top to the bar
_PLACEHOLDER_HEIGHT = 50.0  # Fixed height of placeholder boxes


class FamilyView:
    """Renderar familjediagrammet i en QGraphicsScene.

    Layout:
        - Föräldrar centrerade ovanför syskonlinjen med partnerlinje.
        - Horisontell syskonlinje med vertikala droppar till varje syskon.
        - Under varje syskon (inklusive aktiva personen): make/maka och barn.

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

        # Siblings from parent family
        siblings: list[str] = []
        if parent_family:
            siblings = [
                cid for cid in parent_family.children if cid != active_person_id
            ]

        # ===================================================================
        # STEP 1: Create all sibling boxes to know their actual heights.
        # The sibling row includes active person first, then siblings.
        # ===================================================================
        all_sibling_ids = [active_person_id] + siblings
        sibling_boxes: list[PersonBoxItem] = []
        for pid in all_sibling_ids:
            p = _find_person(project_data, pid)
            if p is None:
                continue
            display_data = _build_display_data(p, project_data)
            box = PersonBoxItem(pid, display_data, config)
            sibling_boxes.append(box)

        if not sibling_boxes:
            return

        sibling_count = len(sibling_boxes)

        # Compute sibling row width and positions
        siblings_total_width = (
            sibling_count * _BOX_WIDTH + (sibling_count - 1) * _H_GAP
        )
        siblings_start_x = -siblings_total_width / 2.0
        siblings_y = 0.0  # Reference row

        # Place sibling boxes in the scene
        sibling_positions: list[tuple[float, float]] = []  # (x, y) for each
        active_x = 0.0
        max_sibling_height = 0.0

        for i, box in enumerate(sibling_boxes):
            x = siblings_start_x + i * (_BOX_WIDTH + _H_GAP)
            box.setPos(x, siblings_y)
            scene.addItem(box)
            self._person_boxes.append(box)
            sibling_positions.append((x, siblings_y))
            if box.person_id == active_person_id:
                active_x = x
            if box.box_height > max_sibling_height:
                max_sibling_height = box.box_height

        # ===================================================================
        # STEP 2: Parents — centered above the sibling bar
        # ===================================================================
        # The sibling bar will be centered over the sibling row.
        # Parents connect at the center of the bar.
        bar_center_x = siblings_start_x + (siblings_total_width / 2.0)

        # Parent boxes: father to the left of center, mother to the right
        father_x = bar_center_x - _PARENT_GAP / 2.0 - _BOX_WIDTH
        mother_x = bar_center_x + _PARENT_GAP / 2.0

        father_id: Optional[str] = None
        mother_id: Optional[str] = None

        if parent_family:
            for partner in parent_family.partners:
                if partner.role in ("father", "husband"):
                    father_id = partner.person_id
                elif partner.role in ("mother", "wife"):
                    mother_id = partner.person_id
                elif partner.role == "partner":
                    # Same-sex or gender-neutral: assign to first empty slot
                    if father_id is None:
                        father_id = partner.person_id
                    elif mother_id is None:
                        mother_id = partner.person_id

        # Create parent boxes to determine their heights
        father_box: Optional[PersonBoxItem] = None
        mother_box: Optional[PersonBoxItem] = None
        father_height = _PLACEHOLDER_HEIGHT
        mother_height = _PLACEHOLDER_HEIGHT

        # The bar is at a fixed distance above the sibling row
        bar_y = siblings_y - _BAR_DROP

        # Parents are above the bar
        # We need to know parent height first, so create the boxes:
        if father_id:
            p = _find_person(project_data, father_id)
            if p:
                display_data = _build_display_data(p, project_data)
                father_box = PersonBoxItem(father_id, display_data, config)
                father_height = father_box.box_height

        if mother_id:
            p = _find_person(project_data, mother_id)
            if p:
                display_data = _build_display_data(p, project_data)
                mother_box = PersonBoxItem(mother_id, display_data, config)
                mother_height = mother_box.box_height

        max_parent_height = max(father_height, mother_height)
        parents_y = bar_y - _BAR_DROP - max_parent_height

        # Place father
        if father_box:
            father_box.setPos(father_x, parents_y)
            scene.addItem(father_box)
            self._person_boxes.append(father_box)
        else:
            placeholder = PlaceholderBoxItem(
                PlaceholderRole.FATHER,
                family_id=parent_family.id if parent_family else None,
            )
            placeholder.setPos(father_x, parents_y)
            scene.addItem(placeholder)
            self._placeholder_boxes.append(placeholder)

        # Place mother
        if mother_box:
            mother_box.setPos(mother_x, parents_y)
            scene.addItem(mother_box)
            self._person_boxes.append(mother_box)
        else:
            placeholder = PlaceholderBoxItem(
                PlaceholderRole.MOTHER,
                family_id=parent_family.id if parent_family else None,
            )
            placeholder.setPos(mother_x, parents_y)
            scene.addItem(placeholder)
            self._placeholder_boxes.append(placeholder)

        # ===================================================================
        # STEP 3: Connection lines — parents to sibling bar
        # ===================================================================
        # Horizontal partner line between father and mother (at their vertical center)
        partner_line_y = parents_y + max_parent_height / 2.0
        father_right = QPointF(father_x + _BOX_WIDTH, partner_line_y)
        mother_left = QPointF(mother_x, partner_line_y)
        scene.addItem(
            ConnectionLineItem(father_right, mother_left, ConnectionType.PARTNER)
        )

        # Vertical drop from the midpoint of the partner line down to the bar
        partner_mid_x = (father_x + _BOX_WIDTH + mother_x) / 2.0
        scene.addItem(ConnectionLineItem(
            QPointF(partner_mid_x, partner_line_y),
            QPointF(bar_center_x, bar_y),
            ConnectionType.PARENT_CHILD,
        ))

        # Horizontal sibling bar
        leftmost_center_x = siblings_start_x + _BOX_WIDTH / 2.0
        rightmost_center_x = (
            siblings_start_x + (sibling_count - 1) * (_BOX_WIDTH + _H_GAP)
            + _BOX_WIDTH / 2.0
        )

        if sibling_count > 1:
            scene.addItem(ConnectionLineItem(
                QPointF(leftmost_center_x, bar_y),
                QPointF(rightmost_center_x, bar_y),
                ConnectionType.PARENT_CHILD,
            ))
        else:
            # Single child — just ensure bar_center connects to that child
            pass

        # Vertical drops from bar to each sibling's actual top
        for i, box in enumerate(sibling_boxes):
            sib_center_x = (
                siblings_start_x + i * (_BOX_WIDTH + _H_GAP) + _BOX_WIDTH / 2.0
            )
            scene.addItem(ConnectionLineItem(
                QPointF(sib_center_x, bar_y),
                QPointF(sib_center_x, siblings_y),
                ConnectionType.PARENT_CHILD,
            ))

        # ===================================================================
        # STEP 4: Spouse(s) and children below each sibling
        #
        # Layout: a vertical "spine" on the left side of the sibling box
        # connects downward. Each spouse branches off to the right from
        # this spine, with children stacking below each spouse.
        #
        #   ┌────────────────┐
        #   │  Sibling       │
        #   ├────────────────┘
        #   │  (spine runs down left edge)
        #   │
        #   ├──┌────────────────┐
        #   │  │  Spouse 1      │
        #   │  └───────┬────────┘
        #   │          │ children stacked
        #   │          │
        #   ├──┌────────────────┐
        #   │  │  Spouse 2      │
        #      └───────┬────────┘
        #              │ children stacked
        # ===================================================================
        _SPINE_OFFSET = 15.0  # how far left of the box the spine runs
        _SPINE_TO_BOX = 15.0  # horizontal segment from spine to spouse box left edge
        _SPOUSE_INDENT = _SPINE_OFFSET + _SPINE_TO_BOX  # total indent for spouse/children

        for i, box in enumerate(sibling_boxes):
            sib_x = sibling_positions[i][0]
            sib_height = box.box_height
            is_active = box.person_id == active_person_id

            # Find partner families for this sibling
            sib_partner_families = _find_partner_families(
                project_data, box.person_id
            )

            if not sib_partner_families and not is_active:
                continue

            # Spine X is to the left of the sibling box
            spine_x = sib_x - _SPINE_OFFSET

            # Spine starts at the vertical center of the sibling box
            spine_start_y = siblings_y + sib_height / 2.0

            # Horizontal connector from sibling left edge to spine (at mid-height)
            scene.addItem(ConnectionLineItem(
                QPointF(sib_x, spine_start_y),
                QPointF(spine_x, spine_start_y),
                ConnectionType.PARTNER,
            ))

            # Current Y cursor — first spouse placed below the sibling box bottom
            cur_y = siblings_y + sib_height + _CHILD_V_GAP

            # Track the lowest point the spine reaches
            spine_end_y = cur_y

            for fam_idx, family in enumerate(sib_partner_families):
                other_partners = [
                    fp for fp in family.partners
                    if fp.person_id != box.person_id
                ]

                # Spouse box is indented to the right of the spine
                spouse_x = sib_x
                spouse_mid_y = cur_y  # will be set after placing

                # Place spouse box
                spouse_box_item: Optional[PersonBoxItem] = None
                for fp in other_partners:
                    sp = _find_person(project_data, fp.person_id)
                    if sp:
                        display_data = _build_display_data(sp, project_data)
                        spouse_box_item = PersonBoxItem(
                            fp.person_id, display_data, config
                        )
                        spouse_box_item.setPos(spouse_x, cur_y)
                        scene.addItem(spouse_box_item)
                        self._person_boxes.append(spouse_box_item)

                # If no spouse was found, show a placeholder for the missing parent
                if spouse_box_item is None:
                    # Determine placeholder role based on the current person's role
                    current_partner = next(
                        (fp for fp in family.partners if fp.person_id == box.person_id),
                        None,
                    )
                    if current_partner and current_partner.role in ("mother", "wife"):
                        ph_role = PlaceholderRole.FATHER
                    elif current_partner and current_partner.role in ("father", "husband"):
                        ph_role = PlaceholderRole.MOTHER
                    else:
                        # Fallback: check person's sex
                        current_person = _find_person(project_data, box.person_id)
                        if current_person and current_person.sex in ("F", "female"):
                            ph_role = PlaceholderRole.FATHER
                        elif current_person and current_person.sex in ("M", "male"):
                            ph_role = PlaceholderRole.MOTHER
                        else:
                            ph_role = PlaceholderRole.PARTNER

                    spouse_placeholder = PlaceholderBoxItem(
                        ph_role, family_id=family.id
                    )
                    spouse_placeholder.setPos(spouse_x, cur_y)
                    scene.addItem(spouse_placeholder)
                    self._placeholder_boxes.append(spouse_placeholder)

                # Determine spouse box height
                if spouse_box_item:
                    sp_height = spouse_box_item.box_height
                else:
                    sp_height = _PLACEHOLDER_HEIGHT

                # Horizontal connector from spine to spouse left edge (at spouse mid-height)
                spouse_mid_y = cur_y + sp_height / 2.0
                scene.addItem(ConnectionLineItem(
                    QPointF(spine_x, spouse_mid_y),
                    QPointF(spouse_x, spouse_mid_y),
                    ConnectionType.PARTNER,
                ))

                spine_end_y = spouse_mid_y

                # Move below spouse
                cur_y += sp_height + _CHILD_V_GAP

                # --- Children below spouse, stacked vertically ---
                children_ids = family.children
                child_center_x = spouse_x + _BOX_WIDTH / 2.0

                for c_idx, child_id in enumerate(children_ids):
                    cp = _find_person(project_data, child_id)
                    if cp:
                        display_data = _build_display_data(cp, project_data)
                        child_box = PersonBoxItem(child_id, display_data, config)
                        child_box.setPos(spouse_x, cur_y)
                        scene.addItem(child_box)
                        self._person_boxes.append(child_box)

                        # Vertical line from above to child top
                        scene.addItem(ConnectionLineItem(
                            QPointF(child_center_x, cur_y - _CHILD_V_GAP),
                            QPointF(child_center_x, cur_y),
                            ConnectionType.PARENT_CHILD,
                        ))

                        cur_y += child_box.box_height + _CHILD_V_GAP

                # Placeholder for adding new child
                placeholder = PlaceholderBoxItem(
                    PlaceholderRole.CHILD, family_id=family.id
                )
                placeholder.setPos(spouse_x, cur_y)
                scene.addItem(placeholder)
                self._placeholder_boxes.append(placeholder)

                # Line to placeholder from above
                scene.addItem(ConnectionLineItem(
                    QPointF(child_center_x, cur_y - _CHILD_V_GAP),
                    QPointF(child_center_x, cur_y),
                    ConnectionType.PARENT_CHILD,
                ))

                cur_y += _PLACEHOLDER_HEIGHT + _CHILD_V_GAP

            # "Lägg till partner" placeholder for the active person
            if is_active:
                partner_placeholder = PlaceholderBoxItem(
                    PlaceholderRole.PARTNER,
                    family_id=None,
                )
                partner_placeholder.setPos(sib_x, cur_y)
                scene.addItem(partner_placeholder)
                self._placeholder_boxes.append(partner_placeholder)

                # Connector from spine to partner placeholder
                partner_ph_mid_y = cur_y + _PLACEHOLDER_HEIGHT / 2.0
                scene.addItem(ConnectionLineItem(
                    QPointF(spine_x, partner_ph_mid_y),
                    QPointF(sib_x, partner_ph_mid_y),
                    ConnectionType.PARTNER,
                ))

                spine_end_y = partner_ph_mid_y
                cur_y += _PLACEHOLDER_HEIGHT + _CHILD_V_GAP

            # Draw the vertical spine line from sibling bottom to last spouse connector
            scene.addItem(ConnectionLineItem(
                QPointF(spine_x, spine_start_y),
                QPointF(spine_x, spine_end_y),
                ConnectionType.PARTNER,
            ))

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
) -> dict:
    """Bygg display_data-dictionary för en person.

    Extraherar namn, födelse-/dödsdatum och -plats från personens
    händelser för att visa i personrutan.

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

    # Prefer birth name
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
