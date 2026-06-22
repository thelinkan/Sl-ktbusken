"""Bekräftelsedialog för att ta bort en person.

Visar varningstext med information om vilka händelser och familjer
som påverkas av borttagningen, och kräver uttrycklig bekräftelse
från användaren innan radering genomförs.

Validates: Requirements 1.6, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.2, 7.3
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.event import Event
from slaktbusken.services.delete_service import DeletionConsequences

# Swedish translations for known event types
_EVENT_TYPE_TRANSLATIONS: dict[str, str] = {
    "birth": "Födelse",
    "death": "Död",
    "marriage": "Vigsel",
    "baptism": "Dop",
    "burial": "Begravning",
    "census": "Folkräkning",
    "divorce": "Skilsmässa",
    "engagement": "Förlovning",
    "immigration": "Invandring",
    "emigration": "Utvandring",
    "confirmation": "Konfirmation",
    "graduation": "Examen",
    "retirement": "Pensionering",
    "occupation": "Yrke",
    "residence": "Bostad",
}


def _translate_event_type(event: Event) -> str:
    """Translate an event type to Swedish display text.

    Uses custom_type_name if available, otherwise looks up in the
    translation table, falling back to capitalized type string.
    """
    if event.custom_type_name:
        return event.custom_type_name
    return _EVENT_TYPE_TRANSLATIONS.get(event.type, event.type.capitalize())


def _format_event_line(event: Event) -> str:
    """Format a single event as a warning line entry.

    Shows type and date value, or 'inget datum' when no date is set.
    """
    event_type = _translate_event_type(event)
    date_str = event.date.value if event.date else "inget datum"
    return f"  • {event_type} ({date_str})"


def build_warning_lines(
    consequences: DeletionConsequences,
    max_events: int = 10,
) -> list[str]:
    """Build Swedish-language warning lines for the deletion confirmation dialog.

    Returns a list of warning lines describing what will happen if the
    person is deleted. Caps event listing at max_events items total,
    appending "...och N till" when more events exist.

    Args:
        consequences: The computed deletion consequences.
        max_events: Maximum number of events to list individually.

    Returns:
        List of Swedish-language warning strings.
    """
    lines: list[str] = []

    lines.append(
        f'Du är på väg att ta bort "{consequences.person_name}" från projektet.'
    )
    lines.append("")

    # Collect all events to display (family events + non-family shared events)
    family_events = consequences.family_events
    shared_events = consequences.non_family_shared_events

    has_events = bool(family_events or shared_events)

    if has_events:
        total_events = len(family_events) + len(shared_events)
        events_shown = 0

        if family_events:
            lines.append("Följande familjehändelser kommer att tas bort:")
            for event in family_events:
                if events_shown >= max_events:
                    break
                lines.append(_format_event_line(event))
                events_shown += 1

        if shared_events and events_shown < max_events:
            lines.append("Personen kommer att tas bort från dessa delade händelser:")
            for event in shared_events:
                if events_shown >= max_events:
                    break
                lines.append(_format_event_line(event))
                events_shown += 1

        if total_events > max_events:
            overflow = total_events - max_events
            lines.append(f"...och {overflow} till")

        lines.append("")
    else:
        lines.append("Personen har inga delade händelser som påverkas.")
        lines.append("")

    # Exclusive events summary
    if consequences.exclusive_events:
        count = len(consequences.exclusive_events)
        lines.append(
            f"{count} händelse{'r' if count != 1 else ''} som bara tillhör "
            f"denna person kommer att tas bort."
        )
        lines.append("")

    # Family associations
    if consequences.affected_families:
        count = len(consequences.affected_families)
        lines.append(
            f"{count} familjeassociation{'er' if count != 1 else ''} kommer att uppdateras."
        )
        lines.append("")

    # Disconnection warning
    if consequences.would_disconnect:
        lines.append(
            f"⚠ Varning: Borttagningen kommer att koppla bort "
            f"{consequences.disconnected_person_count} "
            f"person{'er' if consequences.disconnected_person_count != 1 else ''} "
            f"från huvudpersonen i trädet."
        )
        lines.append("")

    return lines


class DeletePersonDialog(QDialog):
    """Bekräftelsedialog för att ta bort en person.

    Visar varningstext om konsekvenserna av borttagningen och erbjuder
    knappar för att bekräfta ("Ta bort") eller avbryta ("Avbryt").

    Args:
        parent: Föräldrawidget.
        consequences: Beräknade konsekvenser av borttagningen.
    """

    def __init__(
        self,
        parent: Optional[QWidget],
        consequences: DeletionConsequences,
    ) -> None:
        """Initiera dialogen med konsekvensdata.

        Args:
            parent: Föräldrawidget.
            consequences: Beräknade konsekvenser av borttagningen.
        """
        super().__init__(parent)
        self._consequences = consequences
        self.setWindowTitle("Ta bort person")
        self.setMinimumWidth(450)

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Bygg dialogens UI-layout."""
        layout = QVBoxLayout(self)

        # Warning text
        warning_text = self._build_warning_text()
        self._warning_label = QLabel(warning_text)
        self._warning_label.setWordWrap(True)
        layout.addWidget(self._warning_label)

        # Button box with "Ta bort" and "Avbryt"
        self._button_box = QDialogButtonBox()

        # Add "Ta bort" as the destructive/accept button
        self._delete_button = self._button_box.addButton(
            "Ta bort", QDialogButtonBox.ButtonRole.AcceptRole
        )

        # Add "Avbryt" as the cancel button
        self._cancel_button = self._button_box.addButton(
            "Avbryt", QDialogButtonBox.ButtonRole.RejectRole
        )

        layout.addWidget(self._button_box)

    def _connect_signals(self) -> None:
        """Koppla signaler för knappar."""
        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self.reject)

    def _build_warning_text(self) -> str:
        """Build the warning text from consequences using build_warning_lines."""
        lines = build_warning_lines(self._consequences)
        return "\n".join(lines)
