"""Merge preview widget: "Förhandsgranskning av sammanslagning" (design 15.8).

Shows the summary of a ``MergePlan``, blocking conflicts ("⛔ Konflikt") and
warnings ("⚠ Varning") that differ by icon and label, unresolved choices, the
single GEDCOM update warning and the "Slå samman personer" button. Nothing
here writes data.
"""

from __future__ import annotations

import html
from typing import Any, Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPalette, QTextDocument
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
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
    "relatives": "Närstående",
    "source_refs": "Källhänvisningar",
    "dna_profiles": "DNA-profiler",
    "dna_clusters": "DNA-kluster",
    "dna_summary": "DNA-sammanfattning",
    "research_cases": "Forskningsärenden",
    "research_hypotheses": "Hypoteser",
    "research_notes": "Forskningsanteckningar",
    "candidates": "Kandidater",
    "identity_mappings": "Identitetskopplingar",
    "identity_aliases": "Identitetsalias",
}


def category_label(category: str) -> str:
    """Swedish label for a plan item category (never the raw internal name)."""
    return _CATEGORY_LABELS.get(category, category)


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


#: Red used for the word "Varning" when the user still has a choice to make.
CHOICE_WARNING_COLOR = "#c0392b"
CHOICE_REQUIRED_SUFFIX = " (val krävs)"
#: Item data role holding True for a warning that has an open choice.
CHOICE_OPEN_ROLE = Qt.ItemDataRole.UserRole + 1


def conflict_has_open_choice(plan: Optional[MergePlan], conflict: MergeConflict) -> bool:
    """True when ``conflict`` is a warning with a choice the user has not made.

    Data-driven: a warning whose subjects include a family offered for removal
    (``plan.empty_family_offers``) that is not in ``decisions.remove_empty_family_ids``.
    """
    if plan is None or conflict.is_blocking:
        return False
    chosen = set(plan.decisions.remove_empty_family_ids)
    return any(
        offer.family_id in conflict.subjects and offer.family_id not in chosen
        for offer in plan.empty_family_offers
    )


def add_conflict_item(list_widget: QListWidget, plan: Optional[MergePlan],
                      conflict: MergeConflict, in_owning_section: bool = False) -> QListWidgetItem:
    """Add one conflict line; "Varning" is red when a choice is still open.

    ``in_owning_section`` is True when the list belongs to the section where the
    choice is made; otherwise the tooltip names that section.
    """
    text = format_conflict(conflict)
    item = QListWidgetItem(text)
    if conflict_has_open_choice(plan, conflict):
        item.setData(CHOICE_OPEN_ROLE, True)
        item.setData(Qt.ItemDataRole.AccessibleTextRole, text + CHOICE_REQUIRED_SUFFIX)
        if in_owning_section:
            item.setToolTip("Det finns ett val att göra i det här avsnittet.")
        else:
            section = SECTION_NAMES.get(conflict.section, conflict.section)
            item.setToolTip(f"Det finns ett val att göra i avsnittet {section}.")
        if not isinstance(list_widget.itemDelegate(), ChoiceWarningDelegate):
            list_widget.setItemDelegate(ChoiceWarningDelegate(list_widget))
    list_widget.addItem(item)
    return item


class ChoiceWarningDelegate(QStyledItemDelegate):
    """Paints the word "Varning" in red for items flagged with ``CHOICE_OPEN_ROLE``."""

    def _html(self, text: str, color: str) -> str:
        label = f"{WARNING_ICON} {WARNING_LABEL}"
        escaped = html.escape(text)
        prefix = html.escape(label)
        if escaped.startswith(prefix):
            icon = html.escape(WARNING_ICON)
            word = html.escape(WARNING_LABEL)
            rest = escaped[len(prefix):]
            return f'{icon} <span style="color:{CHOICE_WARNING_COLOR};font-weight:bold">{word}</span>{rest}'
        return escaped

    def paint(self, painter, option, index) -> None:  # noqa: ANN001
        if not index.data(CHOICE_OPEN_ROLE):
            super().paint(painter, option, index)
            return
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        role = QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.Text
        color = opt.palette.color(role).name()
        doc = QTextDocument()
        doc.setDefaultFont(opt.font)
        doc.setDocumentMargin(0)
        doc.setHtml(f'<span style="color:{color}">{self._html(text, color)}</span>')
        rect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, opt, opt.widget)
        painter.save()
        painter.translate(rect.left() + 3, rect.top() + max(0, (rect.height() - doc.size().height()) / 2))
        doc.drawContents(painter)
        painter.restore()

    def sizeHint(self, option, index):  # noqa: ANN001
        return super().sizeHint(option, index)


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
        lines.append(f"{category_label(category)}: {n} · {disposition.value}")
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
                add_conflict_item(self.problem_list, plan, conflict)
            for choice in plan.unresolved:
                section = SECTION_NAMES.get(choice.section, choice.section)
                self.problem_list.addItem(f"Val saknas: {choice.label} (Avsnitt: {section})")
        self.gedcom_label.setVisible(gedcom_warning_visible())
        self.reconfirm_button.setVisible(self._stale)
        self.execute_button.setEnabled(self.can_execute())
