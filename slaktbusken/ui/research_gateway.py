"""Bridge between the entity editors and the application's research actions.

The editors (person, place, event, media, source, DNA) only know their project
data. When the user opens, creates, links or unlinks a research case from one of
them, the work needs the application: it owns the project service, the case
editor dialog and the research-changed notification. ``Application`` registers
a :class:`ResearchGateway` here at start-up and the editors reach it through
:func:`get_research_gateway`.

Without a gateway (for example in a test that builds an editor alone) the tabs
still show their lists but their buttons do nothing.
"""

from __future__ import annotations

from typing import Optional, Protocol

from PySide6.QtCore import SignalInstance
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QWidget

from slaktbusken.model.project import ProjectData
from slaktbusken.ui.widgets.research_tab import ResearchTab


class ResearchGateway(Protocol):
    """What the editors may ask of the application."""

    @property
    def research_changed(self) -> SignalInstance:
        """Signal emitted after research data changed."""

    def open_research_case(self, case_id: str) -> None: ...

    def open_research_action(self, case_id: str, action_id: str) -> None: ...

    def show_research_for_entity(self, entity_type: str, entity_id: str) -> None: ...

    def create_research_case(self, entity_type: str, entity_id: str) -> None: ...

    def link_research_case(self, entity_type: str, entity_id: str) -> None: ...

    def unlink_research_case(self, case_id: str, entity_type: str, entity_id: str) -> None: ...


_gateway: Optional[ResearchGateway] = None


def set_research_gateway(gateway: Optional[ResearchGateway]) -> None:
    """Register (or with None, remove) the application's gateway."""
    global _gateway
    _gateway = gateway


def get_research_gateway() -> Optional[ResearchGateway]:
    """Return the registered gateway, or None."""
    return _gateway


def connect_research_tab(tab: ResearchTab) -> None:
    """Wire a research tab to the gateway, if there is one.

    The tab's buttons call the gateway with the tab's current entity, and the
    tab rebuilds itself whenever research data changes.
    """
    gateway = get_research_gateway()
    if gateway is None:
        return

    def entity() -> tuple[str, Optional[str]]:
        return tab.entity()

    tab.open_case_requested.connect(gateway.open_research_case)
    tab.open_hypothesis_case_requested.connect(gateway.open_research_case)
    tab.create_case_requested.connect(lambda: _call_with_entity(gateway.create_research_case, entity))
    tab.link_existing_requested.connect(lambda: _call_with_entity(gateway.link_research_case, entity))
    tab.remove_association_requested.connect(
        lambda case_id: gateway.unlink_research_case(case_id, *_entity_or_none(entity))
    )
    gateway.research_changed.connect(tab.refresh)


def connect_source_research(section) -> None:
    """Wire the source editor's research section to the gateway, if there is one."""
    gateway = get_research_gateway()
    if gateway is None:
        return
    section.open_case_requested.connect(gateway.open_research_case)
    section.open_action_requested.connect(gateway.open_research_action)
    section.create_case_requested.connect(
        lambda: _call_with_entity(
            gateway.create_research_case, lambda: ("source", section.source_id())
        )
    )
    gateway.research_changed.connect(section.refresh)


def _entity_or_none(entity) -> tuple[str, str]:
    entity_type, entity_id = entity()
    return (entity_type, entity_id or "")


def _call_with_entity(call, entity) -> None:
    entity_type, entity_id = entity()
    if entity_id:
        call(entity_type, entity_id)


class ResearchSection(QGroupBox):
    """A "Forskning" group box holding a research tab, for editors without tabs.

    Args:
        project_data: The project data.
        entity_type: The research entity type of the editor's entity.
        resolver: Returns the id of the entity the editor currently shows, or
            None while it shows a new, unsaved one. Called on every refresh, so
            the section follows the editor's selection.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        project_data: ProjectData,
        entity_type: str,
        resolver,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__("Forskning", parent)
        self._resolver = resolver
        layout = QVBoxLayout(self)
        self.tab = ResearchTab(project_data, entity_type, resolver() or "", self)
        layout.addWidget(self.tab)
        connect_research_tab(self.tab)
        self.refresh()

    def refresh(self) -> None:
        """Re-resolve the editor's current entity and rebuild."""
        entity_type, _old = self.tab.entity()
        self.tab.set_entity(entity_type, self._resolver() or None)
