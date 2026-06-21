"""Unit tests for slaktbusken.persistence.settings_io module."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from slaktbusken.persistence.settings_io import (
    DiagramSettings,
    PersonBoxConfig,
    ProjectSettings,
    UiState,
    create_default_settings,
    read_settings,
    write_settings,
)


class TestCreateDefaultSettings:
    """Tests for the create_default_settings factory function."""

    def test_returns_project_settings_instance(self) -> None:
        settings = create_default_settings()
        assert isinstance(settings, ProjectSettings)

    def test_default_person_box_config_enabled_fields(self) -> None:
        settings = create_default_settings()
        assert settings.person_box_config.name is True
        assert settings.person_box_config.birth_date is True
        assert settings.person_box_config.birth_place is True
        assert settings.person_box_config.death_date is True
        assert settings.person_box_config.death_place is True
        assert settings.person_box_config.photo is True
        assert settings.person_box_config.dna_info is True
        assert settings.person_box_config.cause_of_death is True
        assert settings.person_box_config.clusters is True

    def test_default_person_box_config_disabled_fields(self) -> None:
        settings = create_default_settings()
        assert settings.person_box_config.marriage_date is False
        assert settings.person_box_config.marriage_place is False
        assert settings.person_box_config.occupation is False
        assert settings.person_box_config.notes is False

    def test_default_diagram_settings(self) -> None:
        settings = create_default_settings()
        assert settings.diagram_settings.ancestry_depth == 4
        assert settings.diagram_settings.descendants_depth == 4

    def test_default_ui_state_all_none(self) -> None:
        settings = create_default_settings()
        assert settings.ui_state.window_width is None
        assert settings.ui_state.window_height is None
        assert settings.ui_state.splitter_position is None
        assert settings.ui_state.last_view is None


class TestReadSettings:
    """Tests for reading settings from JSON files."""

    def test_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        path = tmp_path / "nonexistent.json"
        result = read_settings(path)
        assert result == create_default_settings()

    def test_reads_complete_settings(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        data = {
            "person_box_config": {
                "name": True,
                "birth_date": False,
                "birth_place": True,
                "death_date": False,
                "death_place": True,
                "marriage_date": True,
                "marriage_place": False,
                "occupation": True,
                "photo": True,
                "dna_info": True,
                "notes": True,
            },
            "diagram_settings": {
                "ancestry_depth": 8,
                "descendants_depth": 2,
            },
            "ui_state": {
                "window_width": 1920,
                "window_height": 1080,
                "splitter_position": 350,
                "last_view": "family",
            },
        }
        path.write_text(json.dumps(data), encoding="utf-8")

        result = read_settings(path)
        assert result.person_box_config.name is True
        assert result.person_box_config.birth_date is False
        assert result.person_box_config.birth_place is True
        assert result.person_box_config.occupation is True
        assert result.diagram_settings.ancestry_depth == 8
        assert result.diagram_settings.descendants_depth == 2
        assert result.ui_state.window_width == 1920
        assert result.ui_state.window_height == 1080
        assert result.ui_state.splitter_position == 350
        assert result.ui_state.last_view == "family"

    def test_partial_data_fills_defaults(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        data = {"person_box_config": {"name": False}}
        path.write_text(json.dumps(data), encoding="utf-8")

        result = read_settings(path)
        assert result.person_box_config.name is False
        assert result.person_box_config.birth_date is True  # default
        assert result.diagram_settings.ancestry_depth == 4  # default
        assert result.ui_state.window_width is None  # default

    def test_empty_json_object_returns_defaults(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        path.write_text("{}", encoding="utf-8")

        result = read_settings(path)
        assert result == create_default_settings()

    def test_invalid_json_raises_error(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        path.write_text("not json content", encoding="utf-8")

        with pytest.raises(json.JSONDecodeError):
            read_settings(path)


class TestWriteSettings:
    """Tests for writing settings to JSON files."""

    def test_writes_valid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        settings = create_default_settings()
        write_settings(settings, path)

        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
        assert "person_box_config" in data
        assert "diagram_settings" in data
        assert "ui_state" in data

    def test_writes_utf8_encoding(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        write_settings(create_default_settings(), path)

        # Read as bytes to verify encoding
        raw = path.read_bytes()
        assert raw.decode("utf-8")  # Should not raise

    def test_writes_indented_json(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        write_settings(create_default_settings(), path)

        content = path.read_text(encoding="utf-8")
        # Indented JSON has newlines and spaces
        assert "\n" in content
        assert "  " in content

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "dir" / "settings.json"
        write_settings(create_default_settings(), path)
        assert path.exists()

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        path.write_text("old content", encoding="utf-8")

        settings = ProjectSettings(
            diagram_settings=DiagramSettings(ancestry_depth=10)
        )
        write_settings(settings, path)

        loaded = read_settings(path)
        assert loaded.diagram_settings.ancestry_depth == 10


class TestRoundTrip:
    """Tests for write → read round-trip consistency."""

    def test_default_settings_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        original = create_default_settings()
        write_settings(original, path)
        loaded = read_settings(path)
        assert loaded == original

    def test_custom_settings_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        original = ProjectSettings(
            person_box_config=PersonBoxConfig(
                name=True,
                birth_date=False,
                birth_place=True,
                death_date=False,
                death_place=True,
                marriage_date=True,
                marriage_place=True,
                occupation=True,
                photo=True,
                dna_info=True,
                notes=True,
            ),
            diagram_settings=DiagramSettings(
                ancestry_depth=1,
                descendants_depth=10,
            ),
            ui_state=UiState(
                window_width=800,
                window_height=600,
                splitter_position=200,
                last_view="descendants",
            ),
        )
        write_settings(original, path)
        loaded = read_settings(path)
        assert loaded == original

    def test_ui_state_with_none_values_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        original = ProjectSettings(
            ui_state=UiState(window_width=1024, last_view="ancestry")
        )
        write_settings(original, path)
        loaded = read_settings(path)
        assert loaded == original
        assert loaded.ui_state.window_height is None
        assert loaded.ui_state.splitter_position is None
