"""Unit tests for slaktbusken.persistence.app_settings_io module."""

from __future__ import annotations

import json
import os.path
from pathlib import Path
from unittest.mock import patch

import pytest

from slaktbusken.persistence.app_settings_io import (
    AppSettings,
    AppSettingsService,
    ColumnVisibility,
)


@pytest.fixture
def service(tmp_path: Path) -> AppSettingsService:
    """Create an AppSettingsService with SETTINGS_PATH pointing to tmp_path."""
    svc = AppSettingsService()
    svc.SETTINGS_PATH = tmp_path / ".slaktbusken" / "app_settings.json"
    return svc


class TestAppSettingsDefaults:
    """Tests for AppSettings default values."""

    def test_default_recent_projects_is_empty(self) -> None:
        settings = AppSettings()
        assert settings.recent_projects == []

    def test_default_project_path_is_none(self) -> None:
        settings = AppSettings()
        assert settings.default_project_path is None

    def test_default_column_visibility_all_true(self) -> None:
        settings = AppSettings()
        cv = settings.column_visibility
        assert cv.titel is True
        assert cv.yrke is True
        assert cv.kluster is True
        assert cv.dna_company is True


class TestLoad:
    """Tests for AppSettingsService.load()."""

    def test_missing_file_returns_defaults(self, service: AppSettingsService) -> None:
        result = service.load()
        assert result.recent_projects == []
        assert result.default_project_path is None

    def test_loads_complete_settings(self, service: AppSettingsService) -> None:
        data = {
            "recent_projects": ["/path/a.json.gz", "/path/b.json.gz"],
            "default_project_path": "/path/a.json.gz",
        }
        service.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        service.SETTINGS_PATH.write_text(
            json.dumps(data), encoding="utf-8"
        )

        result = service.load()
        assert result.recent_projects == [
            os.path.normpath("/path/a.json.gz"),
            os.path.normpath("/path/b.json.gz"),
        ]
        assert result.default_project_path == "/path/a.json.gz"

    def test_corrupt_json_returns_defaults(self, service: AppSettingsService) -> None:
        service.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        service.SETTINGS_PATH.write_text("not valid json{{{", encoding="utf-8")

        result = service.load()
        assert result.recent_projects == []
        assert result.default_project_path is None

    def test_empty_json_object_returns_defaults(
        self, service: AppSettingsService
    ) -> None:
        service.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        service.SETTINGS_PATH.write_text("{}", encoding="utf-8")

        result = service.load()
        assert result.recent_projects == []
        assert result.default_project_path is None

    def test_non_list_recent_projects_returns_empty_list(
        self, service: AppSettingsService
    ) -> None:
        data = {"recent_projects": "not a list", "default_project_path": None}
        service.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        service.SETTINGS_PATH.write_text(
            json.dumps(data), encoding="utf-8"
        )

        result = service.load()
        assert result.recent_projects == []

    def test_non_string_entries_in_recent_projects_are_filtered(
        self, service: AppSettingsService
    ) -> None:
        data = {
            "recent_projects": ["/valid/path.json.gz", 123, None, "/also/valid.json.gz"],
        }
        service.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        service.SETTINGS_PATH.write_text(
            json.dumps(data), encoding="utf-8"
        )

        result = service.load()
        assert result.recent_projects == [
            os.path.normpath("/valid/path.json.gz"),
            os.path.normpath("/also/valid.json.gz"),
        ]

    def test_recent_projects_limited_to_max_10(
        self, service: AppSettingsService
    ) -> None:
        data = {
            "recent_projects": [f"/path/{i}.json.gz" for i in range(15)],
        }
        service.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        service.SETTINGS_PATH.write_text(
            json.dumps(data), encoding="utf-8"
        )

        result = service.load()
        assert len(result.recent_projects) == 10

    def test_non_string_default_project_path_returns_none(
        self, service: AppSettingsService
    ) -> None:
        data = {"default_project_path": 42}
        service.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        service.SETTINGS_PATH.write_text(
            json.dumps(data), encoding="utf-8"
        )

        result = service.load()
        assert result.default_project_path is None

    def test_missing_column_visibility_returns_all_true(
        self, service: AppSettingsService
    ) -> None:
        data = {"recent_projects": []}
        service.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        service.SETTINGS_PATH.write_text(json.dumps(data), encoding="utf-8")

        result = service.load()
        assert result.column_visibility == ColumnVisibility()

    def test_non_dict_column_visibility_returns_all_true(
        self, service: AppSettingsService
    ) -> None:
        data = {"column_visibility": "not a dict"}
        service.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        service.SETTINGS_PATH.write_text(json.dumps(data), encoding="utf-8")

        result = service.load()
        assert result.column_visibility == ColumnVisibility()

    def test_column_visibility_partial_keys_defaults_missing_to_true(
        self, service: AppSettingsService
    ) -> None:
        data = {"column_visibility": {"titel": False, "yrke": False}}
        service.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        service.SETTINGS_PATH.write_text(json.dumps(data), encoding="utf-8")

        result = service.load()
        assert result.column_visibility.titel is False
        assert result.column_visibility.yrke is False
        assert result.column_visibility.kluster is True
        assert result.column_visibility.dna_company is True

    def test_column_visibility_non_bool_value_defaults_to_true(
        self, service: AppSettingsService
    ) -> None:
        data = {"column_visibility": {"titel": "yes", "yrke": 1, "kluster": None, "dna_company": False}}
        service.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        service.SETTINGS_PATH.write_text(json.dumps(data), encoding="utf-8")

        result = service.load()
        assert result.column_visibility.titel is True
        assert result.column_visibility.yrke is True
        assert result.column_visibility.kluster is True
        assert result.column_visibility.dna_company is False


class TestSave:
    """Tests for AppSettingsService.save()."""

    def test_saves_valid_json(self, service: AppSettingsService) -> None:
        settings = AppSettings(
            recent_projects=["/path/project.json.gz"],
            default_project_path="/path/project.json.gz",
        )
        service.save(settings)

        content = service.SETTINGS_PATH.read_text(encoding="utf-8")
        data = json.loads(content)
        assert data["recent_projects"] == ["/path/project.json.gz"]
        assert data["default_project_path"] == "/path/project.json.gz"

    def test_creates_parent_directories(self, service: AppSettingsService) -> None:
        settings = AppSettings()
        service.save(settings)
        assert service.SETTINGS_PATH.exists()

    def test_writes_indented_json(self, service: AppSettingsService) -> None:
        settings = AppSettings(recent_projects=["/a.json.gz"])
        service.save(settings)

        content = service.SETTINGS_PATH.read_text(encoding="utf-8")
        assert "\n" in content
        assert "  " in content

    def test_non_writable_directory_logs_warning(
        self, service: AppSettingsService, tmp_path: Path
    ) -> None:
        # Point to a path that cannot be created
        service.SETTINGS_PATH = Path("/nonexistent_root_xyz/sub/app_settings.json")
        settings = AppSettings(recent_projects=["/path/a.json.gz"])

        # Should not raise — just logs a warning
        service.save(settings)


class TestAddRecentProject:
    """Tests for AppSettingsService.add_recent_project()."""

    def test_adds_project_to_front(self, service: AppSettingsService) -> None:
        import os.path

        service.load()
        service.add_recent_project("/path/a.json.gz")
        service.add_recent_project("/path/b.json.gz")

        projects = service.get_recent_projects()
        assert projects[0] == os.path.normpath("/path/b.json.gz")
        assert projects[1] == os.path.normpath("/path/a.json.gz")

    def test_moves_existing_project_to_front(
        self, service: AppSettingsService
    ) -> None:
        import os.path

        service.load()
        service.add_recent_project("/path/a.json.gz")
        service.add_recent_project("/path/b.json.gz")
        service.add_recent_project("/path/a.json.gz")

        projects = service.get_recent_projects()
        assert projects == [
            os.path.normpath("/path/a.json.gz"),
            os.path.normpath("/path/b.json.gz"),
        ]

    def test_limits_to_10_entries(self, service: AppSettingsService) -> None:
        import os.path

        service.load()
        for i in range(12):
            service.add_recent_project(f"/path/{i}.json.gz")

        projects = service.get_recent_projects()
        assert len(projects) == 10
        # Most recent should be first
        assert projects[0] == os.path.normpath("/path/11.json.gz")

    def test_persists_to_disk(self, service: AppSettingsService) -> None:
        import os.path

        service.load()
        service.add_recent_project("/path/a.json.gz")

        # Create a new service pointing to same file and load
        svc2 = AppSettingsService()
        svc2.SETTINGS_PATH = service.SETTINGS_PATH
        svc2.load()
        assert svc2.get_recent_projects() == [os.path.normpath("/path/a.json.gz")]

    def test_deduplicates_mixed_separators(self, service: AppSettingsService) -> None:
        """Paths with mixed separators should be treated as the same project."""
        import os.path

        service.load()
        service.add_recent_project("C:/Users/test/project.json.gz")
        service.add_recent_project("C:\\Users\\test\\project.json.gz")

        projects = service.get_recent_projects()
        assert len(projects) == 1
        assert projects[0] == os.path.normpath("C:/Users/test/project.json.gz")


class TestSetDefaultProject:
    """Tests for AppSettingsService.set_default_project()."""

    def test_sets_default_project(self, service: AppSettingsService) -> None:
        service.load()
        service.set_default_project("/path/default.json.gz")
        assert service.get_default_project() == "/path/default.json.gz"

    def test_clears_default_project_with_none(
        self, service: AppSettingsService
    ) -> None:
        service.load()
        service.set_default_project("/path/default.json.gz")
        service.set_default_project(None)
        assert service.get_default_project() is None

    def test_persists_to_disk(self, service: AppSettingsService) -> None:
        service.load()
        service.set_default_project("/path/default.json.gz")

        svc2 = AppSettingsService()
        svc2.SETTINGS_PATH = service.SETTINGS_PATH
        svc2.load()
        assert svc2.get_default_project() == "/path/default.json.gz"


class TestGetRecentProjects:
    """Tests for AppSettingsService.get_recent_projects()."""

    def test_returns_copy_not_reference(self, service: AppSettingsService) -> None:
        import os.path

        service.load()
        service.add_recent_project("/path/a.json.gz")

        projects = service.get_recent_projects()
        projects.append("/path/extra.json.gz")

        # Original should not be modified
        assert service.get_recent_projects() == [os.path.normpath("/path/a.json.gz")]


class TestRoundTrip:
    """Tests for save → load round-trip consistency."""

    def test_default_settings_round_trip(self, service: AppSettingsService) -> None:
        settings = AppSettings()
        service.save(settings)

        svc2 = AppSettingsService()
        svc2.SETTINGS_PATH = service.SETTINGS_PATH
        loaded = svc2.load()
        assert loaded.recent_projects == []
        assert loaded.default_project_path is None
        assert loaded.column_visibility == ColumnVisibility()

    def test_full_settings_round_trip(self, service: AppSettingsService) -> None:
        settings = AppSettings(
            recent_projects=["/path/a.json.gz", "/path/b.json.gz"],
            default_project_path="/path/a.json.gz",
            column_visibility=ColumnVisibility(
                titel=False, yrke=True, kluster=False, dna_company=True
            ),
        )
        service.save(settings)

        svc2 = AppSettingsService()
        svc2.SETTINGS_PATH = service.SETTINGS_PATH
        loaded = svc2.load()
        assert loaded.recent_projects == [
            os.path.normpath("/path/a.json.gz"),
            os.path.normpath("/path/b.json.gz"),
        ]
        assert loaded.default_project_path == "/path/a.json.gz"
        assert loaded.column_visibility.titel is False
        assert loaded.column_visibility.yrke is True
        assert loaded.column_visibility.kluster is False
        assert loaded.column_visibility.dna_company is True
