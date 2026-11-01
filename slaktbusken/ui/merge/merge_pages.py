"""Pages of the Merge_Review wizard (design 15.8).

Pages hold no merge logic. They render a ``MergePlan`` (items, conflicts and
required choices of one section) and report the user's choices to the wizard
through signals. All choices are kept by the wizard, so navigating between
pages never loses a decision (Requirement 26.3).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.services import merge_rules as rules
from slaktbusken.services.merge_planner import MergePlan, UnresolvedChoice
from slaktbusken.ui.merge.merge_preview import format_conflict

KEEP_PERSON_TEXT = "Behåll den här personen"
CONFIRM_SURVIVOR_TEXT = "Bekräfta val"
CONFIRM_SECTION_TEXT = "Bekräfta"
SURVIVOR_RESET_TEXT = (
    "Personen som behålls ändrades. Alla övriga val har nollställts och behöver göras om."
)
NO_ITEMS_TEXT = "Inga"
NOTES_MODES = (
    (rules.NOTES_CONCATENATE, "Slå ihop anteckningarna"),
    (rules.NOTES_KEEP_SURVIVOR, "Behåll bara den behållna personens anteckningar"),
    (rules.NOTES_KEEP_OTHER, "Behåll bara den andra personens anteckningar"),
)

#: (title, plan sections shown, plan item categories shown)
SECTION_DEFS: tuple[tuple[str, str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("attributes", "Personuppgifter", ("attributes",), ("attributes",)),
    ("names", "Namn", ("names",), ("names",)),
    ("events", "Händelser", ("events",), ("events",)),
    ("residences", "Boenden", ("residences",), ("residences",)),
    ("families", "Familj", ("families",), ("families",)),
    ("media", "Källor, media och DNA", ("media", "dna", "sources"), ("media", "sources", "dna")),
    (
        "other_refs", "Forskning och övriga referenser", ("research", "other_refs"),
        ("research", "references", "project"),
    ),
)


@dataclass(frozen=True)
class ChoiceOption:
    """One selectable answer: ``value`` goes to the decisions, ``text`` is shown."""

    value: str
    text: str


@dataclass(frozen=True)
class ChoiceSpec:
    key: str
    section: str
    label: str
    options: tuple[ChoiceOption, ...]


class SurvivorPage(QWidget):
    """Two persons side by side with radio buttons and no default."""

    selection_changed = Signal(str)  # person id
    confirmed = Signal()

    def __init__(self, person_ids: Sequence[str], describe: Callable[[str], str],
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._ids = tuple(person_ids)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Välj vilken person som ska behållas. Den andra personen tas bort."))
        row = QHBoxLayout()
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.radios: dict[str, QRadioButton] = {}
        for pid in self._ids:
            box = QGroupBox(describe(pid))
            box_layout = QVBoxLayout(box)
            radio = QRadioButton(KEEP_PERSON_TEXT)
            radio.setAccessibleName(f"{KEEP_PERSON_TEXT}: {describe(pid)}")
            self._group.addButton(radio)
            radio.toggled.connect(lambda on, p=pid: on and self.selection_changed.emit(p))
            box_layout.addWidget(radio)
            self.radios[pid] = radio
            row.addWidget(box)
        layout.addLayout(row)
        self.reset_label = QLabel("")
        self.reset_label.setWordWrap(True)
        layout.addWidget(self.reset_label)
        self.confirm_button = QPushButton(CONFIRM_SURVIVOR_TEXT)
        self.confirm_button.setEnabled(False)
        self.confirm_button.clicked.connect(self.confirmed)
        layout.addWidget(self.confirm_button, 0, Qt.AlignmentFlag.AlignRight)
        layout.addStretch(1)

    def selected(self) -> Optional[str]:
        for pid, radio in self.radios.items():
            if radio.isChecked():
                return pid
        return None

    def set_confirm_enabled(self, enabled: bool) -> None:
        self.confirm_button.setEnabled(enabled)

    def show_reset_message(self, show: bool) -> None:
        self.reset_label.setText(SURVIVOR_RESET_TEXT if show else "")


class SectionPage(QWidget):
    """One review section: plan items, conflicts and the choices of the section."""

    choice_made = Signal(str, str)  # key, value
    notes_mode_changed = Signal(str)
    confirmed = Signal()

    def __init__(self, section_id: str, title: str, sections: tuple[str, ...],
                 categories: tuple[str, ...], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.section_id = section_id
        self.title = title
        self._sections = sections
        self._categories = categories
        self._known: dict[str, ChoiceSpec] = {}
        self._selected: dict[str, str] = {}
        self._groups: dict[str, list[tuple[ChoiceOption, QRadioButton]]] = {}

        layout = QVBoxLayout(self)
        heading = QLabel(title)
        font = heading.font()
        font.setBold(True)
        heading.setFont(font)
        layout.addWidget(heading)
        self.items_list = QListWidget()
        self.items_list.setAccessibleName(f"Poster i avsnittet {title}")
        layout.addWidget(self.items_list, 2)
        self.problems_list = QListWidget()
        self.problems_list.setAccessibleName(f"Konflikter och varningar i avsnittet {title}")
        layout.addWidget(self.problems_list, 1)

        self.choices_layout = QVBoxLayout()
        layout.addLayout(self.choices_layout)

        self.notes_combo: Optional[QComboBox] = None
        if section_id == "attributes":
            self.notes_combo = QComboBox()
            self.notes_combo.setAccessibleName("Hantering av anteckningar")
            for value, text in NOTES_MODES:
                self.notes_combo.addItem(text, value)
            self.notes_combo.currentIndexChanged.connect(
                lambda _i: self.notes_mode_changed.emit(self.notes_combo.currentData())
            )
            layout.addWidget(self.notes_combo)

        self.confirm_button = QPushButton(CONFIRM_SECTION_TEXT)
        self.confirm_button.clicked.connect(self.confirmed)
        layout.addWidget(self.confirm_button, 0, Qt.AlignmentFlag.AlignRight)

    # -- rendering -----------------------------------------------------

    def reset(self) -> None:
        self._known.clear()
        self._selected.clear()
        if self.notes_combo is not None:
            self.notes_combo.blockSignals(True)
            self.notes_combo.setCurrentIndex(0)
            self.notes_combo.blockSignals(False)
        self._rebuild_choices()

    def set_selected(self, selected: dict[str, str]) -> None:
        self._selected = dict(selected)

    def show_plan(self, plan: Optional[MergePlan], specs: Sequence[ChoiceSpec],
                  selected: dict[str, str]) -> None:
        self.items_list.clear()
        self.problems_list.clear()
        self._selected = dict(selected)
        for spec in specs:
            if spec.section in self._sections:
                self._known[spec.key] = spec
        if plan is not None:
            shown = [i for i in plan.items if i.category in self._categories]
            if not shown:
                self.items_list.addItem(NO_ITEMS_TEXT)
            for item in shown:
                text = f"{item.label} · {item.disposition.value}"
                self.items_list.addItem(f"{text} · {item.detail}" if item.detail else text)
            for conflict in plan.conflicts:
                if conflict.section in self._sections:
                    self.problems_list.addItem(format_conflict(conflict))
        self._rebuild_choices()

    def _rebuild_choices(self) -> None:
        while self.choices_layout.count():
            child = self.choices_layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()
        self._groups.clear()
        for spec in self._known.values():
            box = QGroupBox(spec.label)
            box_layout = QVBoxLayout(box)
            group = QButtonGroup(box)
            entries: list[tuple[ChoiceOption, QRadioButton]] = []
            for option in spec.options:
                radio = QRadioButton(option.text)
                group.addButton(radio)
                radio.setChecked(self._selected.get(spec.key) == option.value)
                radio.toggled.connect(
                    lambda on, k=spec.key, v=option.value: on and self.choice_made.emit(k, v)
                )
                box_layout.addWidget(radio)
                entries.append((option, radio))
            self._groups[spec.key] = entries
            self.choices_layout.addWidget(box)

    def choice_radio(self, key: str, value: str) -> Optional[QRadioButton]:
        for option, radio in self._groups.get(key, ()):
            if option.value == value:
                return radio
        return None


def build_choice_specs(
    unresolved: Sequence[UnresolvedChoice],
    describe_person: Callable[[str], str],
    survivor_id: str,
    retired_id: str,
    profile_media: dict[str, Optional[str]],
    name_options: Sequence[tuple[str, str]],
) -> list[ChoiceSpec]:
    """Turn the plan's unresolved choices into radio-button specs.

    ``name_options`` holds ``(encoded name key, label)`` pairs for the
    primary-name choice; ``profile_media`` maps person id to profile media id.
    """
    specs: list[ChoiceSpec] = []
    for u in unresolved:
        if u.key in ("title", "occupation"):
            options = tuple(ChoiceOption(pid, f"Värdet från {describe_person(pid)}") for pid in u.options)
        elif u.key == "profile_media_id":
            options = tuple(
                ChoiceOption(profile_media[pid] or "", f"Bild {profile_media[pid]} från {describe_person(pid)}")
                for pid in (survivor_id, retired_id)
                if profile_media.get(pid)
            )
        elif u.key == "primary_name":
            options = tuple(ChoiceOption(k, text) for k, text in name_options)
        else:
            options = tuple(ChoiceOption(o, o) for o in u.options)
        specs.append(ChoiceSpec(u.key, u.section, u.label, options))
    return specs
