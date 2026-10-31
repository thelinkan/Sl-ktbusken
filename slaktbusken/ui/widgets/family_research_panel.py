"""Contextual research for the families a person belongs to.

Research about uncertain parentage, marriage, adoption or foster relationships
is linked to the ``family`` entity (Requirement 21 criterion 6). The person
editor has no family editor of its own, so this panel offers a family chooser
(the families the person is a partner or child in) above one research tab.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QLabel, QVBoxLayout, QWidget

from slaktbusken.model.project import ProjectData
from slaktbusken.services.research_entities import entity_label
from slaktbusken.ui.research_gateway import connect_research_tab
from slaktbusken.ui.widgets.research_tab import ResearchTab

NO_FAMILIES_TEXT = "Personen ingår inte i någon familj."


def person_families(data: ProjectData, person_id: str) -> list[tuple[str, str]]:
    """Return ``(family_id, label)`` for each family the person is a partner or child in."""
    if not person_id:
        return []
    result: list[tuple[str, str]] = []
    for family in data.families:
        is_partner = any(p.person_id == person_id for p in family.partners)
        is_child = person_id in family.children or any(
            link.child_id == person_id for link in family.parent_child_links
        )
        if is_partner or is_child:
            label = entity_label(data, "family", family.id) or family.id
            result.append((family.id, f"{label} ({family.id})"))
    return result


class FamilyResearchPanel(QWidget):
    """Family chooser plus a research tab for the chosen family."""

    def __init__(
        self,
        project_data: ProjectData,
        person_id: Optional[str],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._data = project_data
        self._person_id = person_id or ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._empty_label = QLabel(NO_FAMILIES_TEXT)
        layout.addWidget(self._empty_label)
        self._combo = QComboBox()
        layout.addWidget(self._combo)
        self._tab = ResearchTab(project_data, "family", "", self)
        connect_research_tab(self._tab)
        layout.addWidget(self._tab)

        self._combo.currentIndexChanged.connect(self._on_family_changed)
        self.reload()

    def reload(self) -> None:
        """Rebuild the family chooser (keeps the chosen family when still present)."""
        current = self._combo.currentData()
        families = person_families(self._data, self._person_id)
        self._combo.blockSignals(True)
        self._combo.clear()
        for family_id, label in families:
            self._combo.addItem(label, family_id)
        index = self._combo.findData(current) if current else -1
        self._combo.setCurrentIndex(index if index >= 0 else 0)
        self._combo.blockSignals(False)
        has_families = bool(families)
        self._combo.setVisible(has_families)
        self._tab.setVisible(has_families)
        self._empty_label.setVisible(not has_families)
        self._on_family_changed()

    def _on_family_changed(self, *_args) -> None:
        self._tab.set_entity("family", self._combo.currentData() or None)

    def current_family_id(self) -> Optional[str]:
        """The family whose research is shown, or None."""
        return self._combo.currentData()
