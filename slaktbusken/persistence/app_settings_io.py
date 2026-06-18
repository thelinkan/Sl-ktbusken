"""Read/write application-level settings JSON file.

This module handles persistence of application-level settings including
the recent projects list and default project path. Settings are stored
as a human-readable JSON file (UTF-8, indented) in the user's home
directory under ~/.slaktbusken/app_settings.json.

Unlike project settings (which live alongside a project file), application
settings are shared across all projects and persist independently.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_MAX_RECENT_PROJECTS = 10


@dataclass
class AppSettings:
    """Application-level settings persisted across sessions.

    Attributes:
        recent_projects: File paths of recently opened projects, most
            recent first. Limited to a maximum of 10 entries.
        default_project_path: Path to the project that should be opened
            automatically on application start, or None if not set.
    """

    recent_projects: list[str] = field(default_factory=list)
    default_project_path: Optional[str] = None


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

        Args:
            path: The file path of the project to add.
        """
        # Remove existing entry if present (case-sensitive comparison)
        projects = [p for p in self._settings.recent_projects if p != path]
        # Insert at the front (most recent first)
        projects.insert(0, path)
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

    def _serialize(self, settings: AppSettings) -> dict:
        """Convert an AppSettings instance to a JSON-compatible dict.

        Args:
            settings: The settings to serialize.

        Returns:
            A dictionary ready for JSON serialization.
        """
        return {
            "recent_projects": settings.recent_projects,
            "default_project_path": settings.default_project_path,
        }

    def _deserialize(self, data: dict) -> AppSettings:
        """Reconstruct an AppSettings instance from raw dict data.

        Handles missing keys gracefully by falling back to defaults.

        Args:
            data: Dictionary parsed from the settings JSON file.

        Returns:
            A fully populated AppSettings instance.
        """
        recent_projects = data.get("recent_projects", [])
        if not isinstance(recent_projects, list):
            recent_projects = []
        # Ensure all entries are strings and limit to max
        recent_projects = [
            p for p in recent_projects if isinstance(p, str)
        ][:_MAX_RECENT_PROJECTS]

        default_project_path = data.get("default_project_path")
        if default_project_path is not None and not isinstance(
            default_project_path, str
        ):
            default_project_path = None

        return AppSettings(
            recent_projects=recent_projects,
            default_project_path=default_project_path,
        )
