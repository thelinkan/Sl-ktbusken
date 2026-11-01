"""Merge preview widget: "Förhandsgranskning av sammanslagning" (design 15.8).

Shows the summary of a ``MergePlan``, blocking conflicts ("⛔ Konflikt") and
warnings ("⚠ Varning") that differ by icon and label, unresolved choices, the
single GEDCOM update warning and the "Slå samman personer" button. Nothing
here writes data.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.gedcom import capabilities
from slaktbusken.services.merge_planner import Disposition, MergeConflict, MergePlan

PREVIEW_TITLE = "Förhandsgranskning av sammanslagning"
EXECUTE_TEXT = "Slå samman personer"
RECONFIRM_TEXT = "Bekräfta ny förhandsgranskning"
STALE_NOTICE = "Projektet har ändrats. Granska förhandsgranskningen igen."
UNAVAILABLE_TEXT = "Förhandsgranskningen är inte tillgänglig."
BUILDING_TEXT = "Förhandsgranskningen byggs…"
GEDCOM_WARNING_TEXT = (
    "En senare GEDCOM-uppdatering kan skriva över namn, anteckningar, titel och yrke "
    "för den behållna personen. Granska en sådan import noggrant."
)
BLOCKING_ICON, BLOCKING_LABEL = "⛔", "Konflikt"
WARNING_ICON, WARNING_LABEL = "⚠", "Varning"

SECTION_NAMES = {
    "survivor": "Välj person som behålls",
    "attributes": "Personuppgifter",
    "names": "Namn",
    "events": "Händelser",
    "residences": "Boenden",
    "families": "Familj",
    "media": "Källor, media och DNA",
    "dna": "Källor, media och DNA",
    "sources": "Källor, media och DNA",
    "research": "Forskning och övriga referenser",
    "other_refs": "Forskning och övriga referenser",
}

_CATEGORY_LABELS = {
    "attributes": "Personuppgifter",
    "names": "Namn",
    "events": "Händelser",
    "residences": "Boenden",
    "families": "Familjer",
    "media": "Media",
    "sources": "Källor",
    "dna": "DNA",
    "research": "Forskning",
    "references": "Övriga referenser",
    "project": "Projekt",
}


def gedcom_warning_visible() -> bool:
    """The warning shows while no non-destructive update exists."""
    return not capabilities.NON_DESTRUCTIVE_UPDATE_AVAILABLE


def format_conflict(conflict: MergeConflict) -> str:
    """One list line: icon, label, message and the section that can resolve it."""
    icon, label = (
        (BLOCKING_ICON, BLOCKING_LABEL) if conflict.is_blocking else (WARNING_ICON, WARNING_LABEL)
    )
    section = SECTION_NAMES.get(conflict.section, conflict.section)
    return f"{icon} {label}: {conflict.message} (Avsnitt: {section})"


def summary_lines(plan: MergePlan, person_text: Callable[[str], str]) -> list[str]:
    """Plain-text summary of what the merge does (Requirement 26.2)."""
    if plan.survivor_id is None or plan.retired_id is None:
        return []
    lines = [
        f"Behålls: {person_text(plan.survivor_id)}",
        f"Tas bort: {person_text(plan.retired_id)}",
    ]
    counts: dict[tuple[str, Disposition], int] = {}
    for item in plan.items:
        counts[(item.category, item.disposition)] = counts.get((item.category, item.disposition), 0) + 1
    for (category, disposition), n in sorted(counts.items(), key=lambda kv: (kv[0][0], kv[0][1].value)):
        lines.append(f"{_CATEGORY_LABELS.get(category, category)}: {n} · {disposition.value}")
    p = plan.preview
    lines.append(
        f"Familjer efter sammanslagningen: {p.family_count} "
        f"(nya {len(p.added_family_ids)}, borttagna {len(p.removed_family_ids)}, "
        f"ändrade {len(p.changed_family_ids)})"
    )
    lines.append(
        f"Forskningslänkar: {plan.research.links_rewired} omskrivna, "
        f"{plan.research.links_collapsed} hopslagna"
    )
    c = plan.candidate_ops
    lines.append(
        f"Kandidater: {len(c.redirected)} omdirigerade, {len(c.collided)} kolliderar, "
        f"{len(c.archived)} arkiveras"
    )
    i = plan.identity_ops
    lines.append(
        f"Identitetskopplingar: {len(i.mappings_moved)} flyttas, "
        f"{len(i.aliases_rewritten)} alias skrivs om"
    )
    return lines


class MergePreviewWidget(QWidget):
    """The preview page. Emits :attr:`execute_requested` from the button."""

    execute_requested = Signal()
    reconfirm_requested = Signal()

    def __init__(self, person_text: Callable[[str], str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._person_text = person_text
        self._plan: Optional[MergePlan] = None
        self._stale = False
        self._unavailable = False
        self._building = False

        layout = QVBoxLayout(self)
        self.title_label = QLabel(PREVIEW_TITLE)
        font = self.title_label.font()
        font.setBold(True)
        self.title_label.setFont(font)
        layout.addWidget(self.title_label)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.summary_list = QListWidget()
        self.summary_list.setAccessibleName("Sammanfattning av sammanslagningen")
        layout.addWidget(self.summary_list, 2)

        self.problem_list = QListWidget()
        self.problem_list.setAccessibleName("Konflikter, varningar och val som saknas")
        layout.addWidget(self.problem_list, 2)

        self.gedcom_label = QLabel(GEDCOM_WARNING_TEXT)
        self.gedcom_label.setWordWrap(True)
        layout.addWidget(self.gedcom_label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.reconfirm_button = QPushButton(RECONFIRM_TEXT)
        self.reconfirm_button.clicked.connect(self.reconfirm_requested)
        buttons.addWidget(self.reconfirm_button)
        self.execute_button = QPushButton(EXECUTE_TEXT)
        self.execute_button.clicked.connect(self.execute_requested)
        buttons.addWidget(self.execute_button)
        layout.addLayout(buttons)
        self.refresh()

    # -- state ---------------------------------------------------------

    @property
    def plan(self) -> Optional[MergePlan]:
        return self._plan

    def set_building(self, building: bool) -> None:
        self._building = building
        self.refresh()

    def set_plan(self, plan: Optional[MergePlan], unavailable: bool = False) -> None:
        self._plan = plan
        self._unavailable = unavailable
        self._stale = False
        self._building = False
        self.refresh()

    def set_stale(self, stale: bool) -> None:
        self._stale = stale
        self.refresh()

    def can_execute(self) -> bool:
        return (
            self._plan is not None
            and not self._stale
            and not self._unavailable
            and not self._building
            and self._plan.can_execute
        )

    # -- rendering -----------------------------------------------------

    def refresh(self) -> None:
        self.summary_list.clear()
        self.problem_list.clear()
        plan = self._plan
        if self._building:
            self.status_label.setText(BUILDING_TEXT)
        elif self._unavailable:
            self.status_label.setText(UNAVAILABLE_TEXT)
        elif self._stale:
            self.status_label.setText(STALE_NOTICE)
        else:
            self.status_label.setText("")
        if plan is not None and not self._unavailable:
            for line in summary_lines(plan, self._person_text):
                self.summary_list.addItem(line)
            for conflict in sorted(plan.conflicts, key=lambda c: not c.is_blocking):
                self.problem_list.addItem(QListWidgetItem(format_conflict(conflict)))
            for choice in plan.unresolved:
                section = SECTION_NAMES.get(choice.section, choice.section)
                self.problem_list.addItem(f"Val saknas: {choice.label} (Avsnitt: {section})")
        self.gedcom_label.setVisible(gedcom_warning_visible())
        self.reconfirm_button.setVisible(self._stale)
        self.execute_button.setEnabled(self.can_execute())
