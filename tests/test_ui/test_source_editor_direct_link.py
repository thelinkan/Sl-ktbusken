"""Unit tests for the SourceEditor direct link display and click handling.

Tests that:
- A clickable link is displayed when conditions are met (Källtyp has root_url,
  source has arkivreferens)
- The link is hidden when conditions are not met
- An error indicator is shown when link generation fails
- QDesktopServices.openUrl is called on link click
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication

from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.source import Kalltyp, Leverantor, Source
from slaktbusken.ui.editors.source_editor import SourceEditor


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def project_with_link_conditions() -> ProjectData:
    """Create a project where direct link conditions are met."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        leverantorer=[
            Leverantor(id="lev-1", name="Rötter.se"),
        ],
        kalltyper=[
            Kalltyp(
                id="kt-1",
                leverantor_id="lev-1",
                name="Sveriges Dödbok Webb",
                root_url="https://www.rotter.se/abonnemang/sveriges-dodbok-webb/post/",
            ),
        ],
        sources=[
            Source(
                id="src-1",
                provider="Rötter.se",
                source_type="database",
                title="Sveriges Dödbok",
                kalltyp_id="kt-1",
                arkivreferens="12345",
            ),
        ],
    )


@pytest.fixture()
def project_without_link_conditions() -> ProjectData:
    """Create a project where direct link conditions are NOT met (no root_url)."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        leverantorer=[
            Leverantor(id="lev-1", name="Arkiv Digital"),
        ],
        kalltyper=[
            Kalltyp(
                id="kt-2",
                leverantor_id="lev-1",
                name="Husförhörslängd",
                root_url="",  # No root_url
            ),
        ],
        sources=[
            Source(
                id="src-2",
                provider="Arkiv Digital",
                source_type="church_book",
                title="Test Source",
                kalltyp_id="kt-2",
                arkivreferens="some-ref",
            ),
        ],
    )


@pytest.fixture()
def project_without_arkivreferens() -> ProjectData:
    """Create a project where arkivreferens is empty."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        leverantorer=[
            Leverantor(id="lev-1", name="Rötter.se"),
        ],
        kalltyper=[
            Kalltyp(
                id="kt-1",
                leverantor_id="lev-1",
                name="Sveriges Dödbok Webb",
                root_url="https://www.rotter.se/post/",
            ),
        ],
        sources=[
            Source(
                id="src-3",
                provider="Rötter.se",
                source_type="database",
                title="Test Source",
                kalltyp_id="kt-1",
                arkivreferens="",  # Empty arkivreferens
            ),
        ],
    )


class TestDirectLinkDisplay:
    """Tests for direct link display in SourceEditor."""

    def test_link_visible_when_conditions_met(
        self, qapp, project_with_link_conditions
    ) -> None:
        editor = SourceEditor(
            project_data=project_with_link_conditions,
            source=project_with_link_conditions.sources[0],
        )
        assert not editor._direct_link_label.isHidden()
        expected_url = (
            "https://www.rotter.se/abonnemang/sveriges-dodbok-webb/post/12345"
        )
        assert expected_url in editor._direct_link_label.text()

    def test_link_hidden_when_no_root_url(
        self, qapp, project_without_link_conditions
    ) -> None:
        editor = SourceEditor(
            project_data=project_without_link_conditions,
            source=project_without_link_conditions.sources[0],
        )
        assert editor._direct_link_label.isHidden()

    def test_link_hidden_when_no_arkivreferens(
        self, qapp, project_without_arkivreferens
    ) -> None:
        editor = SourceEditor(
            project_data=project_without_arkivreferens,
            source=project_without_arkivreferens.sources[0],
        )
        assert editor._direct_link_label.isHidden()

    def test_link_hidden_after_clear_form(
        self, qapp, project_with_link_conditions
    ) -> None:
        editor = SourceEditor(
            project_data=project_with_link_conditions,
            source=project_with_link_conditions.sources[0],
        )
        assert not editor._direct_link_label.isHidden()
        editor._clear_form()
        assert editor._direct_link_label.isHidden()

    def test_link_contains_href(
        self, qapp, project_with_link_conditions
    ) -> None:
        editor = SourceEditor(
            project_data=project_with_link_conditions,
            source=project_with_link_conditions.sources[0],
        )
        text = editor._direct_link_label.text()
        assert '<a href="' in text
        assert "https://www.rotter.se/abonnemang/sveriges-dodbok-webb/post/12345" in text

    @patch("slaktbusken.ui.editors.source_editor.QDesktopServices.openUrl")
    def test_click_opens_url(
        self, mock_open_url, qapp, project_with_link_conditions
    ) -> None:
        editor = SourceEditor(
            project_data=project_with_link_conditions,
            source=project_with_link_conditions.sources[0],
        )
        url = "https://www.rotter.se/abonnemang/sveriges-dodbok-webb/post/12345"
        editor._on_direct_link_clicked(url)
        mock_open_url.assert_called_once_with(QUrl(url))

    @patch(
        "slaktbusken.ui.editors.source_editor.generate_direct_link",
        side_effect=Exception("test error"),
    )
    def test_error_indicator_on_exception(
        self, mock_gen, qapp, project_with_link_conditions
    ) -> None:
        editor = SourceEditor(
            project_data=project_with_link_conditions,
            source=project_with_link_conditions.sources[0],
        )
        assert not editor._direct_link_label.isHidden()
        assert "Länk kunde inte genereras" in editor._direct_link_label.text()
