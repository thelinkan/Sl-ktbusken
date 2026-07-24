"""Read/write application-level settings JSON file.

This module handles persistence of application-level settings including
the recent projects list, default project path, and all visual preferences
(diagram settings, person box config, person list config). Settings are
stored as a human-readable JSON file (UTF-8, indented) in the user's home
directory under ~/.slaktbusken/app_settings.json.

All user preferences are stored here at the application level — they are
global and apply regardless of which project is open.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from slaktbusken.persistence.settings_io import (
    DiagramSettings,
    PersonBoxConfig,
    PersonListConfig,
)

logger = logging.getLogger(__name__)

_MAX_RECENT_PROJECTS = 10


@dataclass
class ColumnVisibility:
    """Per-column visibility flags for the person list table.

    Each field corresponds to an optional column that the user can
    show or hide. All columns are visible by default.
    """

    titel: bool = True
    yrke: bool = True
    kluster: bool = True
    dna_company: bool = True


@dataclass
class AppSettings:
    """Application-level settings persisted across sessions.

    All user preferences are stored here — none are project-specific.

    Attributes:
        recent_projects: File paths of recently opened projects, most
            recent first. Limited to a maximum of 10 entries.
        startup_mode: What to do on startup: "none" (open nothing),
            "recent" (open last used project), "default_project" (open
            the specified default project).
        default_project_path: Path to the project that should be opened
            automatically on application start (used when startup_mode
            is "default_project"), or None if not set.
        default_folder: Default base folder for creating new projects,
            or None to use the system default.
        person_box_config: Configuration for person box content fields.
        diagram_settings: Diagram view depth and background settings.
        person_list_config: Configuration for person list columns/icons.
        column_visibility: Visibility flags for optional columns in the
            person list table.
    """

    recent_projects: list[str] = field(default_factory=list)
    startup_mode: str = "none"
    default_project_path: Optional[str] = None
    default_folder: Optional[str] = None
    person_box_config: PersonBoxConfig = field(default_factory=PersonBoxConfig)
    diagram_settings: DiagramSettings = field(default_factory=DiagramSettings)
    person_list_config: PersonListConfig = field(default_factory=PersonListConfig)
    column_visibility: ColumnVisibility = field(default_factory=ColumnVisibility)


class AppSettingsService:
    """Manages reading/writing application-level settings.

    Settings are stored at ~/.slaktbusken/app_settings.json. The service
    handles missing or corrupt files gracefully by falling back to fresh
    defaults. If the settings directory is not writable, a warning is
    logged and the application continues without persisting changes.
    """

    SETTINGS_PATH = Path.home() / ".slaktbusken" / "app_settings.json"

    def __init__(self) -> None:
        """Initialize the service with default settings."""
        self._settings: AppSettings = AppSettings()

    def load(self) -> AppSettings:
        """Load application settings from disk.

        If the settings file does not exist, returns fresh defaults.
        If the file contains invalid JSON or unexpected structure,
        logs a warning and returns fresh defaults.

        Returns:
            The loaded AppSettings, or defaults if the file is
            missing or corrupt.
        """
        if not self.SETTINGS_PATH.exists():
            logger.info(
                "App settings file not found at %s, using defaults.",
                self.SETTINGS_PATH,
            )
            self._settings = AppSettings()
            return self._settings

        try:
            data = json.loads(
                self.SETTINGS_PATH.read_text(encoding="utf-8")
            )
            self._settings = self._deserialize(data)
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            logger.warning(
                "Could not read app settings from %s (%s), using defaults.",
                self.SETTINGS_PATH,
                exc,
            )
            self._settings = AppSettings()

        return self._settings

    def save(self, settings: AppSettings) -> None:
        """Persist application settings to disk.

        Creates the parent directory if it does not exist. If the
        directory or file is not writable, logs a warning and
        continues without persisting.

        Args:
            settings: The AppSettings instance to save.
        """
        self._settings = settings

        try:
            self.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = self._serialize(settings)
            json_str = json.dumps(data, indent=2, ensure_ascii=False)
            self.SETTINGS_PATH.write_text(json_str + "\n", encoding="utf-8")
        except OSError as exc:
            logger.warning(
                "Could not write app settings to %s (%s), continuing without persisting.",
                self.SETTINGS_PATH,
                exc,
            )

    def add_recent_project(self, path: str) -> None:
        """Add a project path to the top of the recent projects list.

        If the path already exists in the list, it is moved to the top
        (most recent). The list is trimmed to a maximum of 10 entries,
        removing the oldest entry when the limit is exceeded.

        Paths are compared in a normalized form to avoid duplicates
        from mixed slash/backslash styles on Windows.

        Args:
            path: The file path of the project to add.
        """
        import os.path

        # Normalize for comparison to catch slash/backslash duplicates
        def _norm(p: str) -> str:
            return os.path.normpath(p)

        normalized = _norm(path)
        # Remove existing entry if present (compare normalized forms)
        projects = [
            p for p in self._settings.recent_projects
            if _norm(p) != normalized
        ]
        # Insert at the front (most recent first), store normalized form
        projects.insert(0, normalized)
        # Enforce maximum limit
        self._settings.recent_projects = projects[:_MAX_RECENT_PROJECTS]
        self.save(self._settings)

    def set_default_project(self, path: Optional[str]) -> None:
        """Set or clear the default project path.

        Args:
            path: The file path to set as the default project, or
                None to clear the default project setting.
        """
        self._settings.default_project_path = path
        self.save(self._settings)

    def get_recent_projects(self) -> list[str]:
        """Return the list of recently opened project paths.

        Returns:
            A list of file path strings, most recent first,
            with at most 10 entries.
        """
        return list(self._settings.recent_projects)

    def get_default_project(self) -> Optional[str]:
        """Return the default project path, or None if not set.

        Returns:
            The default project file path, or None.
        """
        return self._settings.default_project_path

    def set_startup_mode(self, mode: str) -> None:
        """Set the startup mode.

        Args:
            mode: One of "none", "recent", or "default_project".
        """
        self._settings.startup_mode = mode
        self.save(self._settings)

    def get_startup_mode(self) -> str:
        """Return the current startup mode.

        Returns:
            One of "none", "recent", or "default_project".
        """
        return self._settings.startup_mode

    def set_default_folder(self, path: Optional[str]) -> None:
        """Set or clear the default folder for new projects.

        Args:
            path: The folder path to use as base for new projects,
                or None to clear the setting.
        """
        self._settings.default_folder = path
        self.save(self._settings)

    def get_default_folder(self) -> Optional[str]:
        """Return the default folder for new projects, or None if not set.

        Returns:
            The default folder path, or None.
        """
        return self._settings.default_folder

    def _serialize(self, settings: AppSettings) -> dict:
        """Convert an AppSettings instance to a JSON-compatible dict.

        Args:
            settings: The settings to serialize.

        Returns:
            A dictionary ready for JSON serialization.
        """
        cv = settings.column_visibility
        return {
            "recent_projects": settings.recent_projects,
            "startup_mode": settings.startup_mode,
            "default_project_path": settings.default_project_path,
            "default_folder": settings.default_folder,
            "person_box_config": asdict(settings.person_box_config),
            "diagram_settings": asdict(settings.diagram_settings),
            "person_list_config": asdict(settings.person_list_config),
            "column_visibility": {
                "titel": cv.titel,
                "yrke": cv.yrke,
                "kluster": cv.kluster,
                "dna_company": cv.dna_company,
            },
        }

    def _deserialize(self, data: dict) -> AppSettings:
        """Reconstruct an AppSettings instance from raw dict data.

        Handles missing keys gracefully by falling back to defaults.

        Args:
            data: Dictionary parsed from the settings JSON file.

        Returns:
            A fully populated AppSettings instance.
        """
        import os.path

        recent_projects = data.get("recent_projects", [])
        if not isinstance(recent_projects, list):
            recent_projects = []
        # Ensure all entries are strings, normalize paths, and deduplicate
        seen: set[str] = set()
        deduped: list[str] = []
        for p in recent_projects:
            if not isinstance(p, str):
                continue
            normalized = os.path.normpath(p)
            if normalized not in seen:
                seen.add(normalized)
                deduped.append(normalized)
        recent_projects = deduped[:_MAX_RECENT_PROJECTS]

        default_project_path = data.get("default_project_path")
        if default_project_path is not None and not isinstance(
            default_project_path, str
        ):
            default_project_path = None

        # Read startup_mode with backward compatibility: if not present
        # but default_project_path is set, assume "default_project"
        _VALID_STARTUP_MODES = ("none", "recent", "default_project")
        startup_mode = data.get("startup_mode")
        if startup_mode not in _VALID_STARTUP_MODES:
            # Backward compat: old settings without startup_mode
            if default_project_path:
                startup_mode = "default_project"
            else:
                startup_mode = "none"

        default_folder = data.get("default_folder")
        if default_folder is not None and not isinstance(default_folder, str):
            default_folder = None

        # Deserialize column visibility with graceful fallback
        cv_data = data.get("column_visibility")
        if isinstance(cv_data, dict):
            titel = cv_data.get("titel", True)
            yrke = cv_data.get("yrke", True)
            kluster = cv_data.get("kluster", True)
            dna_company = cv_data.get("dna_company", True)
            # Fall back to True for non-boolean values
            column_visibility = ColumnVisibility(
                titel=titel if isinstance(titel, bool) else True,
                yrke=yrke if isinstance(yrke, bool) else True,
                kluster=kluster if isinstance(kluster, bool) else True,
                dna_company=dna_company if isinstance(dna_company, bool) else True,
            )
        else:
            column_visibility = ColumnVisibility()

        # Deserialize visual settings with graceful fallback
        pbc_data = data.get("person_box_config")
        if isinstance(pbc_data, dict):
            person_box_config = PersonBoxConfig(
                name=pbc_data.get("name", True),
                birth_date=pbc_data.get("birth_date", True),
                birth_place=pbc_data.get("birth_place", True),
                death_date=pbc_data.get("death_date", True),
                death_place=pbc_data.get("death_place", True),
                marriage_date=pbc_data.get("marriage_date", False),
                marriage_place=pbc_data.get("marriage_place", False),
                occupation=pbc_data.get("occupation", False),
                photo=pbc_data.get("photo", True),
                dna_info=pbc_data.get("dna_info", True),
                notes=pbc_data.get("notes", False),
                cause_of_death=pbc_data.get("cause_of_death", True),
                clusters=pbc_data.get("clusters", True),
                age=pbc_data.get("age", True),
            )
        else:
            person_box_config = PersonBoxConfig()

        ds_data = data.get("diagram_settings")
        if isinstance(ds_data, dict):
            diagram_settings = DiagramSettings(
                ancestry_depth=ds_data.get("ancestry_depth", 4),
                descendants_depth=ds_data.get("descendants_depth", 4),
                ancestry_compact=ds_data.get("ancestry_compact", False),
                background_color=ds_data.get("background_color", "#f0f0f0"),
            )
        else:
            diagram_settings = DiagramSettings()

        plc_data = data.get("person_list_config")
        if isinstance(plc_data, dict):
            person_list_config = PersonListConfig(
                sex=plc_data.get("sex", True),
                relation=plc_data.get("relation", True),
                multiple_names=plc_data.get("multiple_names", True),
                birth_date=plc_data.get("birth_date", True),
                birth_place=plc_data.get("birth_place", True),
                death_date=plc_data.get("death_date", True),
                death_place=plc_data.get("death_place", True),
                title=plc_data.get("title", True),
                occupation=plc_data.get("occupation", True),
                clusters=plc_data.get("clusters", True),
                dna=plc_data.get("dna", True),
            )
        else:
            person_list_config = PersonListConfig()

        return AppSettings(
            recent_projects=recent_projects,
            startup_mode=startup_mode,
            default_project_path=default_project_path,
            default_folder=default_folder,
            person_box_config=person_box_config,
            diagram_settings=diagram_settings,
            person_list_config=person_list_config,
            column_visibility=column_visibility,
        )
