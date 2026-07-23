"""Person detail panel showing comprehensive info about the selected person.

Displays person data including names, title, occupation, notes, and all
associated events with dates and places. Updates when a new person is
selected in the person list or diagram.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from slaktbusken.app import Application


# Swedish event type labels
_EVENT_TYPE_LABELS: dict[str, str] = {
    "birth": "Födelse",
    "baptism": "Dop",
    "death": "Död",
    "burial": "Begravning",
    "marriage": "Vigsel",
    "divorce": "Skilsmässa",
    "emigration": "Utvandring",
    "immigration": "Invandring",
    "census": "Folkräkning",
    "confirmation": "Konfirmation",
    "first_communion": "Nattvardsgång",
    "graduation": "Examen",
    "retirement": "Pension",
    "will": "Testamente",
    "cremation": "Kremering",
    "adoption": "Adoption",
    "blessing": "Välsignelse",
    "engagement": "Förlovning",
    "divorce_filed": "Skilsmässoansökan",
    "name_change": "Namnbyte",
    "gender_correction": "Könskorrigering",
    "custom_individual_event": "Anpassad händelse",
    "custom_family_event": "Anpassad familjehändelse",
}

_SEX_LABELS: dict[str, str] = {
    "M": "Man",
    "F": "Kvinna",
    "X": "Annat",
    "U": "Okänt",
}


class PersonDetailPanel(QWidget):
    """Panel showing detailed information about the currently selected person.

    Shows: name(s), sex, title, occupation, notes, and all events with
    dates and places.

    Args:
        app: The Application instance providing project data.
        parent: Optional parent widget.
    """

    def __init__(self, app: Application, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._app = app
        self._current_person_id: Optional[str] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Build the panel UI with a scrollable content area."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(0)

        # Title
        self._title_label = QLabel("Detaljerad vy")
        self._title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self._title_label)

        # Scrollable content area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 8, 0, 0)
        self._content_layout.setSpacing(4)
        self._content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Placeholder when no person is selected
        self._placeholder = QLabel("Välj en person för att visa detaljer")
        self._placeholder.setStyleSheet("color: gray; font-style: italic;")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._content_layout.addWidget(self._placeholder)

        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_person(self, person_id: str) -> None:
        """Update the panel to show details for the given person.

        Args:
            person_id: The ID of the person to display.
        """
        self._current_person_id = person_id
        self._refresh()

    def clear(self) -> None:
        """Clear the panel content."""
        self._current_person_id = None
        self._clear_content()
        self._placeholder.setVisible(True)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        """Rebuild the content for the current person."""
        self._clear_content()

        if self._current_person_id is None:
            self._placeholder.setVisible(True)
            return

        data = self._app.project_service.data
        person = next(
            (p for p in data.persons if p.id == self._current_person_id), None
        )
        if person is None:
            self._placeholder.setText("Person hittades inte")
            self._placeholder.setVisible(True)
            return

        self._placeholder.setVisible(False)

        # --- Name section ---
        for i, name in enumerate(person.names):
            full_name = f"{name.given} {name.surname}".strip()
            if i == 0:
                name_label = QLabel(f"<b style='font-size:13px'>{full_name}</b>")
            else:
                type_label = self._name_type_label(name.type)
                name_label = QLabel(f"  {type_label}: {full_name}")
            name_label.setTextFormat(Qt.TextFormat.RichText)
            name_label.setWordWrap(True)
            self._content_layout.addWidget(name_label)

        # --- Basic info ---
        sex_label = _SEX_LABELS.get(person.sex, person.sex)
        info_parts = [sex_label]
        if person.title:
            info_parts.append(f"Titel: {person.title}")
        if person.occupation:
            info_parts.append(f"Yrke: {person.occupation}")

        info_text = " · ".join(info_parts)
        info_widget = QLabel(info_text)
        info_widget.setStyleSheet("color: #555; margin-top: 4px;")
        info_widget.setWordWrap(True)
        self._content_layout.addWidget(info_widget)

        # --- Events section ---
        events = self._get_person_events(self._current_person_id)
        if events:
            events_header = QLabel("<b>Händelser</b>")
            events_header.setTextFormat(Qt.TextFormat.RichText)
            events_header.setStyleSheet("margin-top: 12px;")
            self._content_layout.addWidget(events_header)

            # Sort events by date
            events.sort(key=lambda e: e.date.value if e.date else "")

            for event in events:
                event_widget = self._build_event_widget(event)
                self._content_layout.addWidget(event_widget)

        # --- Family section ---
        fam_header = QLabel("<b>Familjer</b>")
        fam_header.setTextFormat(Qt.TextFormat.RichText)
        fam_header.setStyleSheet("margin-top: 12px;")
        self._content_layout.addWidget(fam_header)

        # Föräldrar och syskon
        parents_siblings = self._get_parents_and_siblings(self._current_person_id)
        if parents_siblings:
            ps_header = QLabel("<i>Föräldrar och syskon</i>")
            ps_header.setTextFormat(Qt.TextFormat.RichText)
            ps_header.setStyleSheet("margin-left: 8px; margin-top: 4px;")
            self._content_layout.addWidget(ps_header)

            for entry in parents_siblings:
                entry_widget = QLabel(f"  {entry}")
                entry_widget.setWordWrap(True)
                entry_widget.setStyleSheet("margin-left: 8px; margin-top: 2px;")
                self._content_layout.addWidget(entry_widget)

        # Partner/barn familjer
        families = self._get_person_families(self._current_person_id)
        if families:
            for family in families:
                fam_widget = self._build_family_widget(family)
                self._content_layout.addWidget(fam_widget)

        if not parents_siblings and not families:
            no_fam = QLabel("  Inga familjeuppgifter")
            no_fam.setStyleSheet("color: gray; margin-left: 8px;")
            self._content_layout.addWidget(no_fam)

        # --- Notes ---
        if person.notes and person.notes.strip():
            notes_header = QLabel("<b>Anteckningar</b>")
            notes_header.setTextFormat(Qt.TextFormat.RichText)
            notes_header.setStyleSheet("margin-top: 12px;")
            self._content_layout.addWidget(notes_header)

            notes_widget = QLabel(person.notes)
            notes_widget.setWordWrap(True)
            notes_widget.setStyleSheet("color: #333; margin-left: 8px;")
            self._content_layout.addWidget(notes_widget)

        # --- DNA section ---
        dna_profiles = self._get_person_dna_profiles(self._current_person_id)
        if dna_profiles:
            dna_header = QLabel("<b>DNA</b>")
            dna_header.setTextFormat(Qt.TextFormat.RichText)
            dna_header.setStyleSheet("margin-top: 12px;")
            self._content_layout.addWidget(dna_header)

            for profile in dna_profiles:
                profile_widget = self._build_dna_profile_widget(profile)
                self._content_layout.addWidget(profile_widget)

        # --- Kluster section ---
        clusters = self._get_person_clusters(self._current_person_id)
        if clusters:
            cluster_header = QLabel("<b>Kluster</b>")
            cluster_header.setTextFormat(Qt.TextFormat.RichText)
            cluster_header.setStyleSheet("margin-top: 12px;")
            self._content_layout.addWidget(cluster_header)

            for cluster in clusters:
                cluster_widget = QLabel(f"  • {cluster.name}")
                cluster_widget.setStyleSheet("margin-left: 8px; margin-top: 2px;")
                self._content_layout.addWidget(cluster_widget)

        # Spacer at bottom
        self._content_layout.addStretch()

    def _clear_content(self) -> None:
        """Remove all widgets from the content layout."""
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget and widget is not self._placeholder:
                widget.deleteLater()
            elif widget is self._placeholder:
                # Keep placeholder but re-add later if needed
                pass

        # Re-add placeholder (hidden by default)
        self._content_layout.addWidget(self._placeholder)
        self._placeholder.setText("Välj en person för att visa detaljer")
        self._placeholder.setVisible(False)

    def _build_event_widget(self, event) -> QWidget:
        """Build a compact widget for an event."""
        data = self._app.project_service.data

        type_label = _EVENT_TYPE_LABELS.get(event.type, event.type)
        if event.type in ("custom_individual_event", "custom_family_event") and event.custom_type_name:
            type_label = event.custom_type_name

        parts = [f"<b>{type_label}</b>"]

        if event.date:
            parts.append(event.date.value)

        if event.place:
            place = next((p for p in data.places if p.id == event.place.place_id), None)
            if place:
                parts.append(place.name)

        if event.cause_of_death:
            parts.append(f"({event.cause_of_death})")

        text = " — ".join(parts)
        label = QLabel(f"  {text}")
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        label.setStyleSheet("margin-left: 8px; margin-top: 2px;")
        return label

    def _build_family_widget(self, family) -> QWidget:
        """Build a compact widget for a family relationship."""
        data = self._app.project_service.data

        # Find partner(s)
        partner_names = []
        for partner in family.partners:
            if partner.person_id != self._current_person_id:
                person = next((p for p in data.persons if p.id == partner.person_id), None)
                if person and person.names:
                    name = f"{person.names[0].given} {person.names[0].surname}".strip()
                    partner_names.append(name)

        # Children
        child_names = []
        for child_id in family.children:
            person = next((p for p in data.persons if p.id == child_id), None)
            if person and person.names:
                name = f"{person.names[0].given} {person.names[0].surname}".strip()
                child_names.append(name)

        parts = []
        if partner_names:
            parts.append(f"Partner: {', '.join(partner_names)}")
        if child_names:
            parts.append(f"Barn: {', '.join(child_names)}")

        text = "  " + " · ".join(parts) if parts else "  (inga detaljer)"
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet("margin-left: 8px; margin-top: 2px;")
        return label

    def _get_person_events(self, person_id: str) -> list:
        """Get all events where this person is a participant."""
        data = self._app.project_service.data
        return [
            e for e in data.events
            if any(p.person_id == person_id for p in e.participants)
        ]

    def _get_person_families(self, person_id: str) -> list:
        """Get all families where this person is a partner."""
        data = self._app.project_service.data
        return [
            f for f in data.families
            if any(p.person_id == person_id for p in f.partners)
        ]

    def _get_person_dna_profiles(self, person_id: str) -> list:
        """Get all DNA profiles belonging to this person."""
        data = self._app.project_service.data
        return [p for p in data.dna_profiles if p.person_id == person_id]

    def _get_person_clusters(self, person_id: str) -> list:
        """Get all DNA clusters this person is a member of."""
        data = self._app.project_service.data
        return [c for c in data.dna_clusters if person_id in c.person_ids]

    def _get_parents_and_siblings(self, person_id: str) -> list[str]:
        """Get parents and siblings for this person.

        Returns a list of display strings like:
        - "Far: Erik Svensson"
        - "Mor: Anna Persdotter"
        - "Syskon: Karl Eriksson, Maria Eriksdotter"
        """
        data = self._app.project_service.data
        entries: list[str] = []

        for family in data.families:
            if person_id not in family.children:
                continue

            # Found a family where this person is a child
            # List parents
            for partner in family.partners:
                parent = next((p for p in data.persons if p.id == partner.person_id), None)
                if parent:
                    name = f"{parent.names[0].given} {parent.names[0].surname}".strip() if parent.names else parent.id
                    role_label = "Far" if parent.sex == "M" else "Mor" if parent.sex == "F" else "Förälder"
                    entries.append(f"{role_label}: {name}")

            # List siblings (other children in this family)
            sibling_names = []
            for child_id in family.children:
                if child_id == person_id:
                    continue
                sibling = next((p for p in data.persons if p.id == child_id), None)
                if sibling:
                    name = f"{sibling.names[0].given} {sibling.names[0].surname}".strip() if sibling.names else sibling.id
                    sibling_names.append(name)

            if sibling_names:
                entries.append(f"Syskon: {', '.join(sibling_names)}")

        return entries

    def _build_dna_profile_widget(self, profile) -> QWidget:
        """Build a widget showing a DNA profile with match/triangulation counts."""
        data = self._app.project_service.data

        # Get company name
        company = next((c for c in data.dna_companies if c.id == profile.company_id), None)
        company_name = company.name if company else profile.company_id

        # Count matches involving this profile
        match_count = sum(
            1 for m in data.dna_matches
            if m.profile1_id == profile.id or m.profile2_id == profile.id
        )

        # Count triangulations involving this profile
        tri_count = sum(
            1 for t in data.dna_triangulations
            if profile.id in t.profile_ids
        )

        # Build display
        test_type_labels = {
            "autosomal": "Autosomal",
            "y-dna": "Y-DNA",
            "mtdna": "mtDNA",
            "combined": "Kombinerad",
        }
        test_label = test_type_labels.get(profile.test_type, profile.test_type)

        parts = [f"<b>{company_name}</b> ({test_label})"]
        details = []
        if profile.kit_name:
            details.append(f"Kit: {profile.kit_name}")
        details.append(f"Matchningar: {match_count}")
        details.append(f"Triangleringar: {tri_count}")

        text = f"  {parts[0]}<br/>    <span style='color:#555'>{' · '.join(details)}</span>"
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        label.setStyleSheet("margin-left: 8px; margin-top: 4px;")
        return label

    @staticmethod
    def _name_type_label(name_type: str) -> str:
        """Get Swedish label for a name type."""
        labels = {
            "birth": "Födelsenamn",
            "married": "Gift namn",
            "adopted": "Adoptivnamn",
            "other": "Annat namn",
        }
        return labels.get(name_type, name_type)
