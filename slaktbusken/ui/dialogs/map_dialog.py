"""Map dialog for displaying interactive maps with event markers.

This module provides the MapBridge for JavaScript-to-Python communication
and the MapDialog for rendering Leaflet.js maps inside a QWebEngineView.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QDialog, QVBoxLayout

from slaktbusken.services.map_data_service import MapMarker, markers_to_json

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "static" / "map_template.html"


class MapBridge(QObject):
    """Bridge object exposed to JavaScript via QWebChannel.

    Allows the Leaflet map running in QWebEngineView to invoke Python
    callbacks, e.g., when a participant link is clicked in a marker popup.
    """

    navigate_to_person = Signal(str)  # Emits person_id

    @Slot(str)
    def navigateToPerson(self, person_id: str) -> None:
        """Called from JavaScript when a participant link is clicked.

        Args:
            person_id: The ID of the person to navigate to.
        """
        self.navigate_to_person.emit(person_id)


class MapDialog(QDialog):
    """Modal dialog displaying an interactive map with event markers.

    Args:
        markers: List of MapMarker objects to display on the map.
        title: Dialog window title.
        parent: Parent widget.
    """

    person_navigation_requested = Signal(str)  # Emits person_id

    def __init__(
        self,
        markers: list[MapMarker],
        title: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(900, 700)
        self.setModal(True)

        # Layout
        layout = QVBoxLayout(self)

        # Web view
        self._web_view = QWebEngineView(self)
        layout.addWidget(self._web_view)

        # Bridge
        self._bridge = MapBridge(self)
        self._bridge.navigate_to_person.connect(self._on_navigate)

        # Web channel
        channel = QWebChannel(self._web_view.page())
        channel.registerObject("bridge", self._bridge)
        self._web_view.page().setWebChannel(channel)

        # Load map
        self._load_map(markers)

    def _on_navigate(self, person_id: str) -> None:
        """Handle navigation request from the map bridge.

        Emits person_navigation_requested and closes the dialog.
        """
        self.person_navigation_requested.emit(person_id)
        self.accept()

    def _load_map(self, markers: list[MapMarker]) -> None:
        """Read the HTML template, inject marker data, and load into the web view."""
        html_content = _TEMPLATE_PATH.read_text(encoding="utf-8")

        # Inject marker JSON by replacing the placeholder in the template
        marker_json = markers_to_json(markers)
        html_content = html_content.replace("$$MARKER_DATA$$", marker_json)

        # Load HTML with a base URL that allows qrc:///qtwebchannel/qwebchannel.js to resolve
        self._web_view.setHtml(html_content, QUrl("qrc:/"))
