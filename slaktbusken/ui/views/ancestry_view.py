"""Ancestry view — renders the ancestor tree diagram.

Displays the active person's ancestors up to a configurable depth (1-10,
default 4) in a binary tree pattern. The active person is positioned on
the left, with parents branching to the right. Each generation column
doubles the number of positions.

Layout (left to right):
    Gen 0: Active person (centred vertically)
    Gen 1: Father (top), Mother (bottom)
    Gen 2: Four grandparents
    ...up to configured depth
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import shiboken6
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
_H_GAP = 60.0  # Horizontal gap between generation columns
_V_GAP = 20.0  # Minimum vertical gap between boxes in same generation
_BOX_HEIGHT_ESTIMATE = 70.0  # Estimated box height for layout spacing


class AncestryView:
    """Renderar anordiagrammet i en QGraphicsScene.

    Visar den aktiva personens förfäder i ett binärt trädmönster
    med konfigurerat djup (1-10). Aktiv person till vänster, förfäder
    förgrenar sig åt höger med ökande generationer.

    Attributes:
        selected_person_id: ID för den visuellt markerade personen.
    """

    def __init__(self) -> None:
        """Initialisera AncestryView."""
        self.selected_person_id: Optional[str] = None
        self._person_boxes: list[PersonBoxItem] = []
        self._placeholder_boxes: list[PlaceholderBoxItem] = []

    def render(
        self,
        scene: QGraphicsScene,
        project_data: ProjectData,
        active_person_id: str,
        config: PersonBoxConfig,
        depth: int = 4,
        ancestor_set: Optional[set[str]] = None,
        descendant_set: Optional[set[str]] = None,
        project_folder: Optional[Path] = None,
        compact: bool = False,
    ) -> None:
        """Rendera anordiagrammet i scenen.

        Args:
            scene: QGraphicsScene att populera.
            project_data: Projektdata med personer, familjer och händelser.
            active_person_id: ID för den aktiva personen.
            config: Konfiguration för personrutornas innehåll.
            depth: Antal generationer att visa (1-30, standard 4).
            ancestor_set: Mängd av person-ID:n som är direkta förfäder till huvudpersonen.
            descendant_set: Mängd av person-ID:n som är direkta ättlingar till huvudpersonen.
            project_folder: Path to the project folder for resolving media files.
            compact: If True, reduce vertical space for branches with fewer generations.
        """
        self._person_boxes = []
        self._placeholder_boxes = []
        self._placeholder_y_map: dict[tuple[int, int], float] = {}
        self._project_folder = project_folder

        if ancestor_set is None:
            ancestor_set = set()
        if descendant_set is None:
            descendant_set = set()

        # Clamp depth to valid range
        depth = max(1, min(30, depth))

        person = _find_person(project_data, active_person_id)
        if person is None:
            logger.warning("Aktiv person %s hittades inte.", active_person_id)
            return

        # Collect ancestors into a tree structure (SPARSE approach)
        # ancestor_map: (generation, position) -> person_id or None
        # Only stores positions that have a known person OR are direct
        # parent slots of a known person (placeholders).
        ancestor_map: dict[tuple[int, int], Optional[str]] = {}
        ancestor_map[(0, 0)] = active_person_id

        # Track which positions at each generation have known persons
        # so we only expand those (sparse BFS)
        known_positions: dict[int, set[int]] = {0: {0}}

        # Build ancestor map breadth-first — only expand positions with known persons
        for gen in range(depth):
            next_gen = gen + 1
            if gen not in known_positions:
                break
            next_known: set[int] = set()
            for pos in known_positions[gen]:
                person_id = ancestor_map.get((gen, pos))
                if person_id is None:
                    continue

                # Find parent family for this person
                parent_family = _find_parent_family(project_data, person_id)
                father_id: Optional[str] = None
                mother_id: Optional[str] = None

                if parent_family:
                    for partner in parent_family.partners:
                        if partner.role in ("father", "husband"):
                            father_id = partner.person_id
                        elif partner.role in ("mother", "wife"):
                            mother_id = partner.person_id
                        elif partner.role == "partner":
                            if father_id is None:
                                father_id = partner.person_id
                            elif mother_id is None:
                                mother_id = partner.person_id

                # Always store both parent slots (for placeholder rendering)
                ancestor_map[(next_gen, pos * 2)] = father_id
                ancestor_map[(next_gen, pos * 2 + 1)] = mother_id
                if father_id is not None:
                    next_known.add(pos * 2)
                if mother_id is not None:
                    next_known.add(pos * 2 + 1)

            if next_known:
                known_positions[next_gen] = next_known

        # Determine the effective deepest generation that has content
        effective_depth = max(known_positions.keys()) if known_positions else 0
        # But don't exceed the requested depth
        effective_depth = min(effective_depth, depth)

        # Layout: each generation is a column from left to right
        # Gen 0 (active person) at x=0, Gen 1 at x=(_BOX_WIDTH + _H_GAP), etc.

        # Calculate total height needed based on deepest generation
        # Two-pass approach: first create boxes to know actual heights,
        # then position them to avoid overlap.
        max_gen = effective_depth  # deepest generation index
        max_slots = 2**max_gen

        # Pass 1: Create all boxes and track actual heights per (gen, pos)
        # Only iterate positions that exist in ancestor_map (sparse)
        box_map: dict[tuple[int, int], PersonBoxItem] = {}
        placeholder_positions: list[tuple[int, int, float]] = []  # (gen, pos, col_x)

        # Add placeholder parent slots for known persons at the deepest generation
        # so they get "Lägg till far/mor" buttons
        if effective_depth < depth:
            deepest_known = known_positions.get(effective_depth, set())
            placeholder_gen = effective_depth + 1
            placeholder_col_x = placeholder_gen * (_BOX_WIDTH + _H_GAP)
            for pos in deepest_known:
                # Add father and mother placeholder slots
                ancestor_map[(placeholder_gen, pos * 2)] = None
                ancestor_map[(placeholder_gen, pos * 2 + 1)] = None
            if deepest_known:
                effective_depth += 1
                max_gen = effective_depth
                max_slots = 2**max_gen

        for (gen, pos), person_id in ancestor_map.items():
            if gen > effective_depth:
                continue
            col_x = gen * (_BOX_WIDTH + _H_GAP)

            if person_id is not None:
                p = _find_person(project_data, person_id)
                if p is not None:
                    display_data = _build_display_data(p, project_data, self._project_folder)
                    display_data["is_ancestor"] = p.id in ancestor_set
                    display_data["is_descendant"] = p.id in descendant_set
                    display_data["is_main_person"] = (
                        p.id == project_data.project.main_person_id
                    )
                    box = PersonBoxItem(person_id, display_data, config)
                    box_map[(gen, pos)] = box
                else:
                    placeholder_positions.append((gen, pos, col_x))
            elif gen > 0:
                parent_pos = pos // 2
                parent_id = ancestor_map.get((gen - 1, parent_pos))
                if parent_id is not None:
                    placeholder_positions.append((gen, pos, col_x))

        # Determine the effective box height for layout: use the maximum
        # actual height across all created boxes to prevent any overlap.
        max_box_height = _BOX_HEIGHT_ESTIMATE
        for box in box_map.values():
            if box.box_height > max_box_height:
                max_box_height = box.box_height

        # Compute total_height using actual max box height
        effective_box_height = max_box_height

        if compact:
            # Compact mode: calculate actual leaf count per subtree to reduce
            # vertical space for branches with fewer generations.
            _ph_set = {(g, p) for g, p, _ in placeholder_positions}

            def _calc_weight_fast(g: int, p: int) -> int:
                if g == max_gen:
                    return 1
                child_gen = g + 1
                child_pos_f = p * 2
                child_pos_m = p * 2 + 1
                has_f = ancestor_map.get((child_gen, child_pos_f)) is not None or (child_gen, child_pos_f) in _ph_set
                has_m = ancestor_map.get((child_gen, child_pos_m)) is not None or (child_gen, child_pos_m) in _ph_set

                if not has_f and not has_m:
                    return 1
                w = 0
                w += _calc_weight_fast(child_gen, child_pos_f) if has_f else 1
                w += _calc_weight_fast(child_gen, child_pos_m) if has_m else 1
                return w

            total_leaves = _calc_weight_fast(0, 0)
            total_height = total_leaves * (effective_box_height + _V_GAP) - _V_GAP

            # Build a cumulative offset map — sparse iteration via pos_layout keys
            pos_layout: dict[tuple[int, int], tuple[float, float]] = {}
            pos_layout[(0, 0)] = (0.0, total_height)

            for g in range(effective_depth):
                child_gen = g + 1
                # Only process positions that have layout assigned
                positions_at_gen = [(gg, pp) for (gg, pp) in pos_layout if gg == g]
                for _, p in positions_at_gen:
                    y_start, h = pos_layout[(g, p)]
                    child_pos_f = p * 2
                    child_pos_m = p * 2 + 1

                    has_f = ancestor_map.get((child_gen, child_pos_f)) is not None or (child_gen, child_pos_f) in _ph_set
                    has_m = ancestor_map.get((child_gen, child_pos_m)) is not None or (child_gen, child_pos_m) in _ph_set

                    if not has_f and not has_m:
                        continue

                    w_f = _calc_weight_fast(child_gen, child_pos_f) if has_f else 1
                    w_m = _calc_weight_fast(child_gen, child_pos_m) if has_m else 1
                    total_w = w_f + w_m

                    h_f = (w_f / total_w) * h
                    h_m = (w_m / total_w) * h

                    pos_layout[(child_gen, child_pos_f)] = (y_start, h_f)
                    pos_layout[(child_gen, child_pos_m)] = (y_start + h_f, h_m)

            # Pass 2: Position boxes using compact layout (sparse)
            for (gen, pos), box in box_map.items():
                col_x = gen * (_BOX_WIDTH + _H_GAP)
                if (gen, pos) in pos_layout:
                    y_start, h = pos_layout[(gen, pos)]
                    y = y_start + (h - effective_box_height) / 2.0
                else:
                    y = 0.0
                box.setPos(col_x, y)
                scene.addItem(box)
                self._person_boxes.append(box)
                box.setFlag(box.GraphicsItemFlag.ItemIsSelectable, True)

            # Add placeholders at compact positions
            for gen, pos, col_x in placeholder_positions:
                if (gen, pos) in pos_layout:
                    y_start, h = pos_layout[(gen, pos)]
                    y = y_start + (h - effective_box_height) / 2.0
                else:
                    y = 0.0
                self._add_placeholder(scene, gen, pos, col_x, y)

        else:
            # Non-compact mode: uniform slot height based on deepest generation
            total_height = max_slots * (effective_box_height + _V_GAP) - _V_GAP

            # Pass 2: Position and add boxes to scene (sparse)
            for (gen, pos), box in box_map.items():
                col_x = gen * (_BOX_WIDTH + _H_GAP)
                num_slots = 2**gen
                slot_height = total_height / num_slots
                y = pos * slot_height + (slot_height - effective_box_height) / 2.0
                box.setPos(col_x, y)
                scene.addItem(box)
                self._person_boxes.append(box)
                box.setFlag(box.GraphicsItemFlag.ItemIsSelectable, True)

            # Add placeholders at correct positions
            for gen, pos, col_x in placeholder_positions:
                num_slots = 2**gen
                slot_height = total_height / num_slots
                y = pos * slot_height + (slot_height - effective_box_height) / 2.0
                self._add_placeholder(scene, gen, pos, col_x, y)

        # Draw connection lines (sparse — only iterate entries in ancestor_map)
        for (gen, pos) in list(ancestor_map.keys()):
            if gen < 1 or gen > effective_depth:
                continue
            person_id = ancestor_map.get((gen, pos))
            child_gen = gen - 1
            col_x = gen * (_BOX_WIDTH + _H_GAP)
            child_col_x = child_gen * (_BOX_WIDTH + _H_GAP)
            mid_x = child_col_x + _BOX_WIDTH + _H_GAP / 2.0

            child_pos = pos // 2
            child_id = ancestor_map.get((child_gen, child_pos))

            has_ancestor = person_id is not None and _find_person(project_data, person_id) is not None
            has_placeholder_at_pos = self._has_item_at_gen_pos(gen, pos)

            if child_id is None:
                continue
            if not has_ancestor and not has_placeholder_at_pos:
                continue

            child_box = box_map.get((child_gen, child_pos))
            ancestor_box = box_map.get((gen, pos))

            if child_box is not None:
                child_y = child_box.pos().y()
                child_h = child_box.box_height
            else:
                child_y = self._get_placeholder_y(child_gen, child_pos)
                child_h = 50.0

            if ancestor_box is not None:
                ancestor_y = ancestor_box.pos().y()
                ancestor_h = ancestor_box.box_height
            else:
                ancestor_y = self._get_placeholder_y(gen, pos)
                ancestor_h = 50.0

            child_mid_y = child_y + child_h / 2.0
            ancestor_mid_y = ancestor_y + ancestor_h / 2.0

            scene.addItem(ConnectionLineItem(
                QPointF(child_col_x + _BOX_WIDTH, child_mid_y),
                QPointF(mid_x, child_mid_y),
                ConnectionType.PARENT_CHILD,
            ))
            scene.addItem(ConnectionLineItem(
                QPointF(mid_x, child_mid_y),
                QPointF(mid_x, ancestor_mid_y),
                ConnectionType.PARENT_CHILD,
            ))
            scene.addItem(ConnectionLineItem(
                QPointF(mid_x, ancestor_mid_y),
                QPointF(col_x, ancestor_mid_y),
                ConnectionType.PARENT_CHILD,
            ))

    def _add_placeholder(
        self,
        scene: QGraphicsScene,
        gen: int,
        pos: int,
        x: float,
        y: float,
    ) -> None:
        """Lägg till en platshållarruta för en saknad förfader.

        The y parameter is the top position where a full-size box would be placed.
        We center the placeholder vertically at the same midpoint as a regular box.

        Args:
            scene: Scenen att lägga till i.
            gen: Generationsnummer.
            pos: Position inom generationen.
            x: X-koordinat.
            y: Y-koordinat (top of where a regular box would be).
        """
        # Even positions are fathers, odd are mothers
        role = PlaceholderRole.FATHER if pos % 2 == 0 else PlaceholderRole.MOTHER
        placeholder = PlaceholderBoxItem(role)

        # Center the placeholder (50px tall) at the same midpoint as a regular box
        # Regular box center = y + effective_box_height / 2
        # We need to find effective_box_height — approximate from the passed y context
        # The placeholder is 50px (_BOX_HEIGHT in placeholder_box.py)
        placeholder_height = 50.0
        # Determine the effective box height from existing boxes
        max_box_h = _BOX_HEIGHT_ESTIMATE
        for box in self._person_boxes:
            if box.box_height > max_box_h:
                max_box_h = box.box_height

        # Adjust y so placeholder center aligns with where a regular box center would be
        adjusted_y = y + (max_box_h - placeholder_height) / 2.0

        placeholder.setPos(x, adjusted_y)
        scene.addItem(placeholder)
        self._placeholder_boxes.append(placeholder)
        # Track position for connection line drawing (use the adjusted center point)
        self._placeholder_y_map[(gen, pos)] = adjusted_y

    def _get_placeholder_y(self, gen: int, pos: int) -> float:
        """Get the Y position of a placed placeholder at (gen, pos).

        Returns the top-left Y coordinate of the placeholder box.
        Connection line code adds placeholder_height/2 to get mid-y.
        """
        return self._placeholder_y_map.get((gen, pos), 0.0)

    def _has_item_at_gen_pos(self, gen: int, pos: int) -> bool:
        """Kontrollera om det finns en ruta vid given generations-position.

        Approximerar genom att kontrollera om en platshållare lagts till
        vid rätt index. Implementerad via räkning av platshållare per
        generation.

        Args:
            gen: Generationsnummer.
            pos: Position inom generationen.

        Returns:
            True om en ruta (person eller platshållare) finns.
        """
        # This is a simplified check - we always draw lines if parent is known
        # The render logic ensures placeholders are placed when parent is known
        return True

    def handle_click(self, person_id: str) -> None:
        """Hantera klick på en personruta — markera visuellt.

        Avmarkerar alla andra rutor och markerar den klickade.

        Args:
            person_id: ID för den klickade personen.
        """
        self.selected_person_id = person_id
        for box in self._person_boxes:
            if shiboken6.isValid(box):
                box.set_selected(box.person_id == person_id)

    def deselect_all(self) -> None:
        """Avmarkera alla personrutor."""
        self.selected_person_id = None
        for box in self._person_boxes:
            if shiboken6.isValid(box):
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


def collect_ancestors(
    project_data: ProjectData,
    person_id: str,
    depth: int,
) -> dict[tuple[int, int], Optional[str]]:
    """Samla in förfäder för en person upp till angivet djup.

    Returnerar en karta från (generation, position) till person-ID.
    Generation 0 är den aktiva personen, generation 1 är föräldrar, osv.
    Position inom en generation: jämna nummer = fäder, udda = mödrar.

    Denna funktion är den rena datainsamlingslogiken som testats via
    property-based tests (Property 12).

    Args:
        project_data: Projektdata med familjer och personer.
        person_id: ID för startpersonen.
        depth: Antal generationer att samla in (1-30).

    Returns:
        Dictionary med (generation, position) -> person_id eller None.
    """
    depth = max(1, min(30, depth))
    ancestor_map: dict[tuple[int, int], Optional[str]] = {}
    ancestor_map[(0, 0)] = person_id

    # Sparse BFS: only expand positions where a known person exists
    known_positions: dict[int, set[int]] = {0: {0}}

    for gen in range(depth):
        if gen not in known_positions:
            break
        next_gen = gen + 1
        next_known: set[int] = set()

        for pos in known_positions[gen]:
            pid = ancestor_map.get((gen, pos))
            if pid is None:
                continue

            parent_family = _find_parent_family(project_data, pid)
            father_id: Optional[str] = None
            mother_id: Optional[str] = None

            if parent_family:
                for partner in parent_family.partners:
                    if partner.role in ("father", "husband"):
                        father_id = partner.person_id
                    elif partner.role in ("mother", "wife"):
                        mother_id = partner.person_id
                    elif partner.role == "partner":
                        if father_id is None:
                            father_id = partner.person_id
                        elif mother_id is None:
                            mother_id = partner.person_id

            ancestor_map[(next_gen, pos * 2)] = father_id
            ancestor_map[(next_gen, pos * 2 + 1)] = mother_id
            if father_id is not None:
                next_known.add(pos * 2)
            if mother_id is not None:
                next_known.add(pos * 2 + 1)

        if next_known:
            known_positions[next_gen] = next_known

    return ancestor_map


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


def _build_display_data(
    person: Person, project_data: ProjectData,
    project_folder: Optional[Path] = None,
) -> dict:
    """Bygg display_data-dictionary för en person.

    Extraherar namn, födelse-/dödsdatum och -plats från personens
    händelser.

    Args:
        person: Personobjektet.
        project_data: Projektdata för att hämta händelser och platser.
        project_folder: Projektmappens sökväg för att ladda mediafiler.

    Returns:
        Dictionary med nycklar som matchar PersonBoxConfig-fält.
    """
    display_name, name_parsed = _get_display_name_and_parsed(person)
    data: dict = {
        "name": display_name,
        "name_parsed": name_parsed,
        "has_multiple_names": len(person.names) > 1,
        "names_tooltip": _build_names_tooltip(person) if len(person.names) > 1 else "",
        "profile_photo": None,
        "dna_companies": [],
        "clusters": [],
        "cause_of_death": None,
        "birth_date": None,
        "birth_place": None,
        "death_date": None,
        "death_place": None,
        "marriage_date": None,
        "marriage_place": None,
        "occupation": person.occupation,
        "dna_info": None,
        "notes": person.notes if person.notes else None,
        "sex": person.sex,
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
            else:
                # Death recorded but no date — mark for display
                data["death_date"] = "Datum okänt"
            if event.place:
                place = _find_place(project_data, event.place.place_id)
                if place:
                    data["death_place"] = place.name
            if event.cause_of_death:
                data["cause_of_death"] = event.cause_of_death
        elif event.type == "marriage":
            if event.date:
                data["marriage_date"] = event.date.value
            if event.place:
                place = _find_place(project_data, event.place.place_id)
                if place:
                    data["marriage_place"] = place.name

    # Load profile photo if project_folder is available
    if project_folder and person.profile_media_id:
        data["profile_photo"] = _load_media_pixmap(
            person.profile_media_id, project_data, project_folder, size=40
        )

    # Build dna_companies list from DnaProfile records
    company_ids: set[str] = set()
    for profile in project_data.dna_profiles:
        if profile.person_id == person.id:
            company_ids.add(profile.company_id)

    if company_ids:
        from slaktbusken.ui.icons.icon_registry import icon_registry

        companies_list: list[dict] = []
        for company in project_data.dna_companies:
            if company.id in company_ids:
                logo = None
                if company.logo_media_id and project_folder:
                    def _logo_loader(mid: str) -> "QPixmap | None":
                        return _load_media_pixmap(mid, project_data, project_folder)
                    logo = icon_registry.get_dna_company_logo(
                        company.logo_media_id, _logo_loader
                    )
                companies_list.append({"name": company.name, "logo": logo})
        companies_list.sort(key=lambda c: c["name"])
        data["dna_companies"] = companies_list

    # Build clusters list from DnaCluster records
    person_clusters: list[dict] = []
    for cluster in project_data.dna_clusters:
        if person.id in cluster.person_ids:
            person_clusters.append({"name": cluster.name, "color": cluster.color})
    person_clusters.sort(key=lambda c: c["name"])
    data["clusters"] = person_clusters[:5]

    # Calculate age text
    data["age_text"] = None
    data["age_over_100"] = False
    birth_date_str = data.get("birth_date")
    death_date_str = data.get("death_date")
    if birth_date_str:
        from slaktbusken.ui.views._age_helper import compute_age_display
        age_text, over_100 = compute_age_display(birth_date_str, death_date_str)
        data["age_text"] = age_text
        data["age_over_100"] = over_100

    return data


def _load_media_pixmap(
    media_id: str,
    project_data: ProjectData,
    project_folder: Path,
    size: Optional[int] = None,
) -> "QPixmap | None":
    """Load a media item as a QPixmap, optionally scaled."""
    import unicodedata

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap

    media_item = None
    for item in project_data.media:
        if item.id == media_id:
            media_item = item
            break
    if media_item is None:
        return None

    # Normalize the file path to NFC for consistent Swedish character handling
    normalized_file = unicodedata.normalize("NFC", media_item.file)

    # Resolve file path — try multiple strategies
    file_path: Path | None = None
    candidate = project_folder / Path(normalized_file)
    if candidate.is_file():
        file_path = candidate
    else:
        candidate = project_folder / "media" / Path(normalized_file)
        if candidate.is_file():
            file_path = candidate
        else:
            candidate = Path(normalized_file)
            if candidate.is_file():
                file_path = candidate

    if file_path is None:
        return None

    pixmap = QPixmap(str(file_path))
    if pixmap.isNull():
        return None

    if size is not None:
        pixmap = pixmap.scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    return pixmap


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


def _build_names_tooltip(person: Person) -> str:
    """Build tooltip text listing all names for a person.

    Each name is shown on one line as "typ: förnamn efternamn",
    with name types translated to Swedish.

    Args:
        person: The person with multiple names.

    Returns:
        Multi-line tooltip text.
    """
    _NAME_TYPE_SV: dict[str, str] = {
        "birth": "Födelsenamn",
        "married": "Giftnamn",
        "adopted": "Adoptivnamn",
        "other": "Övrigt",
    }
    lines: list[str] = []
    for name in person.names:
        parts: list[str] = []
        if name.given:
            parts.append(name.given.replace("*", ""))
        if name.surname:
            parts.append(name.surname)
        name_str = " ".join(parts)
        if name.type:
            type_label = _NAME_TYPE_SV.get(name.type, name.type)
            lines.append(f"{type_label}: {name_str}")
        else:
            lines.append(name_str)
    return "\n".join(lines)
