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
from pathlib import Path
from typing import Optional

import shiboken6

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QGraphicsScene

from slaktbusken.model.family import Family
from slaktbusken.model.name_parser import ParsedGivenName, parse_given_name
from slaktbusken.model.person import Person
from slaktbusken.model.project import ProjectData
from slaktbusken.persistence.settings_io import DiagramSettings, PersonBoxConfig
from slaktbusken.services.safe_io import resolve_within
from slaktbusken.ui.views.parent_display import (
    ParentSetDisplay,
    _connection_type_for,
    resolve_parent_display,
)
from slaktbusken.ui.widgets.connection_line import ConnectionLineItem, ConnectionType
from slaktbusken.ui.widgets.person_box import PersonBoxItem, _BOX_WIDTH
from slaktbusken.ui.widgets.research_marker import diagram_research_counts
from slaktbusken.ui.widgets.placeholder_box import PlaceholderBoxItem, PlaceholderRole

logger = logging.getLogger(__name__)

# Layout constants
_H_GAP = 40.0  # Horizontal gap between sibling columns
_V_GAP = 50.0  # Vertical gap between rows
_PARENT_GAP = 50.0  # Horizontal gap between father and mother boxes
_CHILD_V_GAP = 20.0  # Vertical gap between stacked children
_BAR_DROP = 25.0  # Distance from parent bottom / sibling top to the bar
_PLACEHOLDER_HEIGHT = 50.0  # Fixed height of placeholder boxes

# Parentage types the resolver groups into one-or-two-parent derived sets.
_NON_BIOLOGICAL_TYPES = frozenset({"foster", "adoptive"})

# Badge labels painted on a derived parent-child connector when the diagram's
# badge setting is enabled (Req 3.6). Biological edges never carry a badge.
_BADGE_TEXT: dict[ConnectionType, str] = {
    ConnectionType.FOSTER: "foster",
    ConnectionType.ADOPTIVE: "adoptiv",
}


def _badge_for(
    connection_type: ConnectionType, badge_enabled: bool
) -> Optional[str]:
    """Return the badge text for a connection, or ``None``.

    Only foster/adoptive connectors carry a badge, and only when the diagram's
    badge setting is on (Req 3.6/3.7). Biological ``PARENT_CHILD`` edges never
    get a badge.
    """
    if not badge_enabled:
        return None
    return _BADGE_TEXT.get(connection_type)


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
        ancestor_set: Optional[set[str]] = None,
        descendant_set: Optional[set[str]] = None,
        project_folder: Optional[Path] = None,
        diagram_settings: Optional[DiagramSettings] = None,
    ) -> None:
        """Rendera familjediagrammet i scenen.

        Args:
            scene: QGraphicsScene att populera.
            project_data: Projektdata med personer, familjer och händelser.
            active_person_id: ID för den aktiva personen.
            config: Konfiguration för personrutornas innehåll.
            ancestor_set: Mängd av person-ID:n som är direkta förfäder till huvudpersonen.
            descendant_set: Mängd av person-ID:n som är direkta ättlingar till huvudpersonen.
            project_folder: Path to the project folder for resolving media files.
            diagram_settings: Diagram display settings driving parentage
                show-level, the foster/adoptive badge, and the fallback. When
                ``None`` the view behaves as before this feature: show-level
                "biological", badge off, fallback on.
        """
        self._person_boxes = []
        self._placeholder_boxes = []

        # Resolve the parentage display settings with safe pre-feature defaults
        # so existing callers/tests that pass no DiagramSettings are unaffected.
        if diagram_settings is not None:
            show_level = diagram_settings.parentage_show_level
            badge_enabled = diagram_settings.parentage_badge
            fallback_enabled = diagram_settings.parentage_fallback
        else:
            show_level = "biological"
            badge_enabled = False
            fallback_enabled = True
        connection_overrides = project_data.connection_overrides

        if ancestor_set is None:
            ancestor_set = set()
        if descendant_set is None:
            descendant_set = set()

        def _augment_display_data(person: Person) -> dict:
            """Build display_data with lineage flags for a person."""
            display_data = _build_display_data(person, project_data, project_folder)
            display_data["is_ancestor"] = person.id in ancestor_set
            display_data["is_descendant"] = person.id in descendant_set
            display_data["is_main_person"] = (
                person.id == project_data.project.main_person_id
            )
            return display_data

        person = _find_person(project_data, active_person_id)
        if person is None:
            logger.warning("Aktiv person %s hittades inte.", active_person_id)
            return

        # Collect every family where the active person is a child — the
        # biological family and any derived foster/adoptive families — then let
        # the shared resolver decide which Parent_Set(s) to draw (override >
        # show-level > fallback). _find_parent_family is kept for the biological
        # spine used elsewhere; the resolver works off the full set so a derived
        # single-parent set can be drawn per the single-parent rule.
        parent_families = _find_parent_families(project_data, active_person_id)
        parent_family = _find_parent_family(project_data, active_person_id)

        parent_display = resolve_parent_display(
            child_id=active_person_id,
            parent_families=parent_families,
            show_level=show_level,
            override=connection_overrides.get(active_person_id),
            fallback_enabled=fallback_enabled,
        )

        # The parent row draws the first resolved set. The existing layout has
        # room for a single parent row; when the resolver returns several sets
        # (e.g. show-level "all" with both a biological pair and a derived set),
        # we draw the first and rely on the resolver's ordering (biological
        # groups first) to keep the biological spine primary. This is a
        # deliberate simplification documented here: the must-hold behaviour is
        # the single-parent rule and the connection-type/badge wiring for the
        # set that is drawn.
        drawn_set: Optional[ParentSetDisplay] = (
            parent_display.sets[0] if parent_display.sets else None
        )

        # Siblings come from the family that the drawn set belongs to so the
        # sibling bar matches the parents being shown; fall back to the
        # biological parent family when nothing is drawn (empty placeholders).
        sibling_source = None
        if drawn_set is not None and drawn_set.family_id is not None:
            sibling_source = _find_family_by_id(
                project_data, drawn_set.family_id
            )
        if sibling_source is None:
            sibling_source = parent_family

        siblings: list[str] = []
        if sibling_source:
            siblings = [
                cid for cid in sibling_source.children if cid != active_person_id
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
            display_data = _augment_display_data(p)
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

        # The bar is at a fixed distance above the sibling row
        bar_y = siblings_y - _BAR_DROP

        # The connection type / badge for the parent-child drop comes from the
        # drawn set: biological -> PARENT_CHILD (no badge), foster/adoptive ->
        # FOSTER/ADOPTIVE with an optional "foster"/"adoptiv" badge (Req 3.5,
        # 3.6, 3.7). When nothing is drawn (empty placeholders) it stays the
        # solid biological style.
        parent_conn_type = (
            drawn_set.connection_type if drawn_set else ConnectionType.PARENT_CHILD
        )
        parent_badge = _badge_for(parent_conn_type, badge_enabled)

        # A derived Parent_Set with exactly one parent is drawn as a single
        # complete parent: one box, no partner connector, no second-parent
        # placeholder, with the drop line centred on that parent (Req 3.8–3.10).
        single_parent_mode = bool(
            drawn_set is not None
            and drawn_set.is_derived
            and drawn_set.cardinality == 1
        )

        if single_parent_mode:
            # -------- Single-parent derived set --------------------------------
            assert drawn_set is not None
            single_parent_id = drawn_set.links[0].parent_id
            single_box: Optional[PersonBoxItem] = None
            single_height = _PLACEHOLDER_HEIGHT
            if single_parent_id:
                p = _find_person(project_data, single_parent_id)
                if p:
                    display_data = _augment_display_data(p)
                    single_box = PersonBoxItem(
                        single_parent_id, display_data, config
                    )
                    single_height = single_box.box_height

            parents_y = bar_y - _BAR_DROP - single_height
            # Centre the single parent box over the sibling bar.
            single_x = bar_center_x - _BOX_WIDTH / 2.0
            if single_box:
                single_box.setPos(single_x, parents_y)
                scene.addItem(single_box)
                self._person_boxes.append(single_box)

            # Drop straight down from the single parent's bottom-centre to the
            # bar — no partner line, no second-parent placeholder.
            single_bottom = QPointF(bar_center_x, parents_y + single_height)
            scene.addItem(ConnectionLineItem(
                single_bottom,
                QPointF(bar_center_x, bar_y),
                parent_conn_type,
                badge_text=parent_badge,
            ))
        else:
            # -------- Two-slot layout (biological pair or two-parent set) ------
            # A biological pair keeps its father/mother placeholder for an
            # unknown slot (Req 3.10); a derived two-parent set draws both boxes
            # with no placeholder (both parents are present).
            is_two_parent_derived = bool(
                drawn_set is not None
                and drawn_set.is_derived
                and drawn_set.cardinality == 2
            )

            father_id: Optional[str] = None
            mother_id: Optional[str] = None

            if is_two_parent_derived:
                # Assign the set's two parents to the slots in link order.
                assert drawn_set is not None
                set_parent_ids = [
                    link.parent_id
                    for link in drawn_set.links
                    if link.parent_id
                ]
                if len(set_parent_ids) >= 1:
                    father_id = set_parent_ids[0]
                if len(set_parent_ids) >= 2:
                    mother_id = set_parent_ids[1]
                slot_family_id = drawn_set.family_id
            else:
                # Biological pair: derive father/mother from the family roles.
                slot_source = sibling_source if sibling_source else parent_family
                if slot_source:
                    for partner in slot_source.partners:
                        if partner.role in ("father", "husband"):
                            father_id = partner.person_id
                        elif partner.role in ("mother", "wife"):
                            mother_id = partner.person_id
                        elif partner.role == "partner":
                            # Same-sex / gender-neutral: first empty slot.
                            if father_id is None:
                                father_id = partner.person_id
                            elif mother_id is None:
                                mother_id = partner.person_id
                slot_family_id = slot_source.id if slot_source else None

            # Create parent boxes to determine their heights
            father_box: Optional[PersonBoxItem] = None
            mother_box: Optional[PersonBoxItem] = None
            father_height = _PLACEHOLDER_HEIGHT
            mother_height = _PLACEHOLDER_HEIGHT

            if father_id:
                p = _find_person(project_data, father_id)
                if p:
                    display_data = _augment_display_data(p)
                    father_box = PersonBoxItem(father_id, display_data, config)
                    father_height = father_box.box_height

            if mother_id:
                p = _find_person(project_data, mother_id)
                if p:
                    display_data = _augment_display_data(p)
                    mother_box = PersonBoxItem(mother_id, display_data, config)
                    mother_height = mother_box.box_height

            max_parent_height = max(father_height, mother_height)
            parents_y = bar_y - _BAR_DROP - max_parent_height

            # Place father (or a placeholder only for a biological pair)
            if father_box:
                father_box.setPos(father_x, parents_y)
                scene.addItem(father_box)
                self._person_boxes.append(father_box)
            elif not is_two_parent_derived:
                placeholder = PlaceholderBoxItem(
                    PlaceholderRole.FATHER,
                    family_id=slot_family_id,
                )
                placeholder.setPos(father_x, parents_y)
                scene.addItem(placeholder)
                self._placeholder_boxes.append(placeholder)

            # Place mother (or a placeholder only for a biological pair)
            if mother_box:
                mother_box.setPos(mother_x, parents_y)
                scene.addItem(mother_box)
                self._person_boxes.append(mother_box)
            elif not is_two_parent_derived:
                placeholder = PlaceholderBoxItem(
                    PlaceholderRole.MOTHER,
                    family_id=slot_family_id,
                )
                placeholder.setPos(mother_x, parents_y)
                scene.addItem(placeholder)
                self._placeholder_boxes.append(placeholder)

            # ===============================================================
            # STEP 3: Connection lines — parents to sibling bar
            # ===============================================================
            # Horizontal partner line between the two parent slots.
            partner_line_y = parents_y + max_parent_height / 2.0
            father_right = QPointF(father_x + _BOX_WIDTH, partner_line_y)
            mother_left = QPointF(mother_x, partner_line_y)
            scene.addItem(
                ConnectionLineItem(
                    father_right, mother_left, ConnectionType.PARTNER
                )
            )

            # Vertical drop from the midpoint of the partner line to the bar,
            # styled/badged per the drawn set's parentage type.
            partner_mid_x = (father_x + _BOX_WIDTH + mother_x) / 2.0
            scene.addItem(ConnectionLineItem(
                QPointF(partner_mid_x, partner_line_y),
                QPointF(bar_center_x, bar_y),
                parent_conn_type,
                badge_text=parent_badge,
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

            # Merge partner families that share the same set of *other* partners
            # into one spouse block. A sibling can have several derived
            # families with the identical partner set (e.g. a biological family
            # and a foster family both with the same spouse); each merged block
            # draws ONE spouse box and ONE "Lägg till barn" placeholder, with
            # the children of every family in the group stacked beneath it.
            partner_groups = _group_partner_families_by_partner_set(
                box.person_id, sib_partner_families
            )

            for other_ids, group_families in partner_groups:
                # Spouse box is indented to the right of the spine
                spouse_x = sib_x

                # The spouse is the first "other" partner of the shared set,
                # taken from the first family that names it (preserves the
                # pre-merge ordering for the common single-family case).
                spouse_partner_id: Optional[str] = None
                for fam in group_families:
                    for fp in fam.partners:
                        if fp.person_id != box.person_id:
                            spouse_partner_id = fp.person_id
                            break
                    if spouse_partner_id is not None:
                        break

                # Place spouse box (once per merged block)
                spouse_box_item: Optional[PersonBoxItem] = None
                if spouse_partner_id is not None:
                    sp = _find_person(project_data, spouse_partner_id)
                    if sp:
                        display_data = _augment_display_data(sp)
                        spouse_box_item = PersonBoxItem(
                            spouse_partner_id, display_data, config
                        )
                        spouse_box_item.setPos(spouse_x, cur_y)
                        scene.addItem(spouse_box_item)
                        self._person_boxes.append(spouse_box_item)

                # The placeholder "owning" family: prefer a biological family in
                # the group (so "Lägg till barn" / the missing-spouse placeholder
                # keep the biological family_id as before the merge), otherwise
                # the first family in the group.
                owning_family = next(
                    (
                        fam for fam in group_families
                        if not _is_derived_single_parent_family(fam)
                    ),
                    group_families[0],
                )

                # If no spouse was found, show a placeholder for the missing
                # parent — UNLESS the whole group is derived single-parent
                # foster/adoptive sets, where there is no implied second parent
                # to add (Req 3.8, same single-parent suppression as the parent
                # row). A biological family in the group keeps its placeholder.
                group_is_derived_single = not other_ids and all(
                    _is_derived_single_parent_family(fam)
                    for fam in group_families
                )
                if spouse_box_item is None and group_is_derived_single:
                    pass
                elif spouse_box_item is None:
                    # Determine placeholder role based on the current person's role
                    current_partner = next(
                        (
                            fp
                            for fp in owning_family.partners
                            if fp.person_id == box.person_id
                        ),
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
                        ph_role, family_id=owning_family.id
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
                # Union of children across the grouped families. Each child
                # remembers the Family it belongs to so its connector style can
                # come from the right family's parent_child_links.
                merged_children: list[tuple[str, Family]] = []
                seen_children: set[tuple[str, str]] = set()
                for fam in group_families:
                    for cid in fam.children:
                        if not any(
                            link.child_id == cid
                            and link.parent_id == box.person_id
                            for link in fam.parent_child_links
                        ):
                            continue
                        key = (fam.id, cid)
                        if key in seen_children:
                            continue
                        seen_children.add(key)
                        merged_children.append((cid, fam))

                child_center_x = spouse_x + _BOX_WIDTH / 2.0

                for child_id, child_family in merged_children:
                    cp = _find_person(project_data, child_id)
                    if cp:
                        display_data = _augment_display_data(cp)
                        child_box = PersonBoxItem(child_id, display_data, config)
                        child_box.setPos(spouse_x, cur_y)
                        scene.addItem(child_box)
                        self._person_boxes.append(child_box)

                        # The child's connector style comes from its own
                        # family's parent_child_link to the sibling: biological
                        # -> PARENT_CHILD (solid, no badge), foster -> FOSTER,
                        # adoptive -> ADOPTIVE (dashed + optional badge). Older
                        # biological data with no explicit link defaults to
                        # biological/PARENT_CHILD.
                        child_link_type = next(
                            (
                                link.parentage_type
                                for link in child_family.parent_child_links
                                if link.child_id == child_id
                                and link.parent_id == box.person_id
                            ),
                            "biological",
                        )
                        child_conn_type = _connection_type_for(child_link_type)
                        child_badge = _badge_for(child_conn_type, badge_enabled)

                        # Vertical line from above to child top
                        scene.addItem(ConnectionLineItem(
                            QPointF(child_center_x, cur_y - _CHILD_V_GAP),
                            QPointF(child_center_x, cur_y),
                            child_conn_type,
                            badge_text=child_badge,
                        ))

                        cur_y += child_box.box_height + _CHILD_V_GAP

                # Placeholder for adding new child (one per merged block)
                placeholder = PlaceholderBoxItem(
                    PlaceholderRole.CHILD, family_id=owning_family.id
                )
                placeholder.setPos(spouse_x, cur_y)
                scene.addItem(placeholder)
                self._placeholder_boxes.append(placeholder)

                # Line to placeholder from above — the add button is not a real
                # child, so it keeps the solid PARENT_CHILD style with no badge.
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


def _find_parent_families(
    project_data: ProjectData, person_id: str
) -> list[Family]:
    """Hitta alla familjer där personen är ett barn.

    Till skillnad från :func:`_find_parent_family` returneras *alla* familjer
    där personen förekommer som barn — både den biologiska familjen och
    härledda foster-/adoptivfamiljer — i projektets ordning. Används för att
    mata :func:`resolve_parent_display`.

    Args:
        project_data: Projektdata att söka i.
        person_id: ID för barnet.

    Returns:
        Lista med alla familjer där personen är barn.
    """
    return [
        family
        for family in project_data.families
        if person_id in family.children
    ]


def _find_family_by_id(
    project_data: ProjectData, family_id: str
) -> Optional[Family]:
    """Hitta en familj via ID.

    Args:
        project_data: Projektdata att söka i.
        family_id: Familjens ID.

    Returns:
        Family-instansen eller None om ej hittad.
    """
    for family in project_data.families:
        if family.id == family_id:
            return family
    return None


def _is_derived_single_parent_family(family: Family) -> bool:
    """Return whether ``family`` is a derived single-parent foster/adoptive set.

    A derived single-parent Parent_Set holds exactly one parent and all its
    parent-child links are foster or adoptive. For such a partner family the
    diagram suppresses the missing-spouse placeholder, since there is no implied
    second foster/adoptive parent (Requirement 3.8).

    Args:
        family: The partner family being laid out in STEP 4.

    Returns:
        ``True`` when the family has one partner and only non-biological links.
    """
    if len(family.partners) != 1:
        return False
    link_types = {link.parentage_type for link in family.parent_child_links}
    if not link_types:
        return False
    return link_types.issubset(_NON_BIOLOGICAL_TYPES)


def _group_partner_families_by_partner_set(
    person_id: str, families: list[Family]
) -> list[tuple[frozenset[str], list[Family]]]:
    """Group a person's partner families by their *other*-partner set.

    STEP 4 draws one spouse block per distinct set of co-partners. A person may
    have several derived :class:`Family` objects that share the same partner
    (e.g. a biological family and a foster family both with the same spouse);
    those must collapse into a single spouse block so the spouse box is drawn
    once with the union of all children stacked beneath it.

    Families are grouped by the frozenset of partner ids *excluding*
    ``person_id``. The returned list preserves the first-appearance order of
    each distinct other-partner set (in the original ``families`` order), and
    each group preserves the original order of its member families.

    Args:
        person_id: The sibling/active person whose partner families are grouped.
        families: The partner families as returned by ``_find_partner_families``.

    Returns:
        A list of ``(other_partner_ids, grouped_families)`` tuples, one per
        distinct other-partner set, in stable first-appearance order.
    """
    order: list[frozenset[str]] = []
    groups: dict[frozenset[str], list[Family]] = {}
    for family in families:
        other_ids = frozenset(
            fp.person_id
            for fp in family.partners
            if fp.person_id != person_id
        )
        if other_ids not in groups:
            groups[other_ids] = []
            order.append(other_ids)
        groups[other_ids].append(family)
    return [(key, groups[key]) for key in order]


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
    person: Person, project_data: ProjectData,
    project_folder: Optional[Path] = None,
) -> dict:
    """Bygg display_data-dictionary för en person.

    Extraherar namn, födelse-/dödsdatum och -plats från personens
    händelser för att visa i personrutan.

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
        "research_counts": diagram_research_counts(person.id),
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
            else:
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
    """Load a media item as a QPixmap, optionally scaled.

    Tries multiple path resolution strategies for backward compatibility.
    Normalizes Unicode (NFC) to handle Swedish characters consistently.

    Args:
        media_id: The MediaItem ID to load.
        project_data: Project data containing media items.
        project_folder: Path to the project folder.
        size: If set, scale the pixmap to fit within size×size preserving ratio.

    Returns:
        QPixmap or None if loading fails.
    """
    import unicodedata

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap

    # Find the MediaItem
    media_item = None
    for item in project_data.media:
        if item.id == media_id:
            media_item = item
            break
    if media_item is None:
        return None

    # Normalize the file path to NFC for consistent Swedish character handling
    normalized_file = unicodedata.normalize("NFC", media_item.file)

    # Resolve file path — try multiple strategies. The project-relative
    # strategies are routed through resolve_within so a ``..`` sequence in the
    # stored reference cannot climb out of the project folder; the explicit
    # absolute-path strategy is preserved for media that legitimately lives
    # outside the project.
    file_path: Path | None = None
    # Strategy 1: relative to project folder (e.g. "media/photos/photo.jpg")
    contained = resolve_within(project_folder, normalized_file)
    if contained is not None and contained.is_file():
        file_path = contained
    else:
        # Strategy 2: relative to media subfolder (legacy, e.g. just "photo.jpg")
        contained = resolve_within(project_folder / "media", normalized_file)
        if contained is not None and contained.is_file():
            file_path = contained
        else:
            # Strategy 3: absolute path
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
