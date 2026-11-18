"""Indicator rules and research settings tests (task 10.5)."""

from __future__ import annotations

import colorsys
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from slaktbusken.model.project import ProjectData
from slaktbusken.model.research_case import ResearchCase, ResearchEntityLink
from slaktbusken.persistence.app_settings_io import AppSettings, AppSettingsService
from slaktbusken.persistence.settings_io import PersonBoxConfig, PersonListConfig
from slaktbusken.services.research_index import ResearchCaseCounts, ResearchIndex
from slaktbusken.ui.widgets.research_indicator import (
    INDICATOR_COLORS,
    STATE_GREY,
    STATE_NONE,
    STATE_ORANGE,
    format_research_counts,
    indicator_color,
    indicator_state,
    indicator_tooltip,
    research_sort_key,
)
from slaktbusken.ui.widgets.research_marker import research_icon


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class TestStateAndColour:
    def test_states(self) -> None:
        assert indicator_state(ResearchCaseCounts(0, 0)) == STATE_NONE
        assert indicator_state(ResearchCaseCounts(1, 3)) == STATE_ORANGE
        assert indicator_state(ResearchCaseCounts(0, 3)) == STATE_GREY

    def test_nothing_is_drawn_when_there_is_no_research(self) -> None:
        assert indicator_color(STATE_NONE) is None
        assert indicator_tooltip(ResearchCaseCounts(0, 0)) == ""
        assert format_research_counts(ResearchCaseCounts(0, 0)) == ""

    def test_colours_are_never_green(self) -> None:
        for colour in INDICATOR_COLORS.values():
            hue, _sat, _val = colorsys.rgb_to_hsv(
                *(c / 255 for c in QColor(colour).getRgb()[:3])
            )
            # Green occupies roughly 75-165 degrees of the hue circle.
            assert not (75 / 360 <= hue <= 165 / 360)
        assert indicator_color(STATE_ORANGE) != indicator_color(STATE_GREY)

    @pytest.mark.parametrize(
        ("counts", "text"),
        [
            (ResearchCaseCounts(1, 1), "1 forskningsärende, varav 1 öppet"),
            (ResearchCaseCounts(0, 1), "1 forskningsärende, varav 0 öppna"),
            (ResearchCaseCounts(2, 3), "3 forskningsärenden, varav 2 öppna"),
            (ResearchCaseCounts(0, 2), "2 forskningsärenden, varav 0 öppna"),
        ],
    )
    def test_tooltip_text(self, counts: ResearchCaseCounts, text: str) -> None:
        assert indicator_tooltip(counts) == text

    def test_cell_text_and_sort_key(self) -> None:
        assert format_research_counts(ResearchCaseCounts(2, 5)) == "2/5"
        assert research_sort_key(ResearchCaseCounts(2, 5)) > research_sort_key(
            ResearchCaseCounts(1, 9)
        )
        assert research_sort_key(ResearchCaseCounts(1, 9)) > research_sort_key(
            ResearchCaseCounts(1, 2)
        )

    def test_icon_is_drawn_in_the_indicator_colour(self, qapp) -> None:
        pixmap = research_icon(INDICATOR_COLORS[STATE_ORANGE], 14)
        assert not pixmap.isNull() and pixmap.width() == 14
        image = pixmap.toImage()
        coloured = [
            QColor(image.pixelColor(x, y))
            for x in range(14)
            for y in range(14)
            if image.pixelColor(x, y).alpha() > 200
        ]
        assert coloured, "the icon has solid pixels"
        assert all(c.red() > c.green() > c.blue() - 1 for c in coloured)


class TestCountsFollowStatus:
    def test_close_and_reopen_update_the_counts(self) -> None:
        data = ProjectData()
        case = ResearchCase(
            id="case_1", title="x", primary_entity_ref=ResearchEntityLink("person", "person_1")
        )
        data.research_cases = [case]
        data.persons = []

        from slaktbusken.model.person import Name, Person

        data.persons = [Person(id="person_1", sex="M", names=[Name(type="birth", given="A", surname="B")])]

        def counts() -> ResearchCaseCounts:
            return ResearchIndex(data).counts_for_entity("person", "person_1")

        assert indicator_state(counts()) == STATE_ORANGE
        case.status = "closed"
        assert indicator_state(counts()) == STATE_GREY
        case.status = "in_progress"
        assert indicator_state(counts()) == STATE_ORANGE
        data.research_cases.clear()
        assert indicator_state(counts()) == STATE_NONE

    def test_broken_link_contributes_nothing(self) -> None:
        data = ProjectData()
        data.research_cases = [
            ResearchCase(
                id="case_1", primary_entity_ref=ResearchEntityLink("person", "person_gone")
            )
        ]
        counts = ResearchIndex(data).counts_for_entity("person", "person_gone")
        assert indicator_state(counts) == STATE_NONE


@pytest.fixture
def service(tmp_path) -> AppSettingsService:
    svc = AppSettingsService()
    svc.SETTINGS_PATH = tmp_path / ".slaktbusken" / "app_settings.json"
    return svc


class TestSettings:
    def test_defaults(self) -> None:
        settings = AppSettings()
        assert settings.column_visibility.research is True
        assert settings.person_list_config.research is True
        assert settings.person_box_config.research is True

    def test_column_visibility_persists(self, service: AppSettingsService) -> None:
        settings = service.load()
        settings.column_visibility.research = False
        service.save(settings)

        again = AppSettingsService()
        again.SETTINGS_PATH = service.SETTINGS_PATH
        assert again.load().column_visibility.research is False

    def test_non_boolean_value_falls_back_to_visible(self, service: AppSettingsService) -> None:
        service.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        service.SETTINGS_PATH.write_text('{"column_visibility": {"research": "no"}}', encoding="utf-8")
        assert service.load().column_visibility.research is True

    def test_diagram_and_person_list_settings_are_independent(
        self, service: AppSettingsService
    ) -> None:
        settings = service.load()
        settings.person_box_config.research = False
        service.save(settings)
        loaded = service.load()
        assert loaded.person_box_config.research is False
        assert loaded.person_list_config.research is True
        assert loaded.column_visibility.research is True

        loaded.person_list_config.research = False
        loaded.column_visibility.research = False
        loaded.person_box_config.research = True
        service.save(loaded)
        again = service.load()
        assert again.person_box_config.research is True
        assert again.person_list_config.research is False

    def test_settings_dialog_keeps_the_two_settings_apart(self, qapp) -> None:
        from slaktbusken.persistence.settings_io import DiagramSettings
        from slaktbusken.ui.dialogs.settings_dialog import SettingsDialog

        dialog = SettingsDialog(
            PersonBoxConfig(research=True),
            DiagramSettings(),
            PersonListConfig(research=True),
        )
        dialog._pl_check_research.setChecked(False)
        assert dialog.person_box_config.research is True
        assert dialog.person_list_config.research is False
        dialog._pl_check_research.setChecked(True)
        dialog._check_research.setChecked(False)
        assert dialog.person_box_config.research is False
        assert dialog.person_list_config.research is True

    def test_person_list_column_follows_the_setting(self, qapp, tmp_path) -> None:
        from types import SimpleNamespace

        from slaktbusken.ui.person_list_panel import PersonListPanel

        # The panel saves on every toggle: keep it away from the real settings file.
        service = AppSettingsService()
        service.SETTINGS_PATH = tmp_path / "app_settings.json"
        settings = AppSettings()
        settings.column_visibility.research = False
        service._settings = settings
        app = SimpleNamespace(
            app_settings_service=service,
            project_service=SimpleNamespace(data=ProjectData(), project_path=None),
        )
        panel = PersonListPanel(app)
        assert panel._tree_widget.isColumnHidden(10) is True

        panel._on_column_visibility_changed("research", True)
        assert panel._tree_widget.isColumnHidden(10) is False
        assert service._settings.column_visibility.research is True
        assert service.SETTINGS_PATH.exists()
