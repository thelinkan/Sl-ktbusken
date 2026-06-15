"""Read/write project settings JSON file.

This module handles persistence of project-level settings including
person box configuration, diagram display settings, and UI state.
Settings are stored as a human-readable JSON file (UTF-8, indented)
in the project folder.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PersonBoxConfig:
    """Configuration for which fields are shown in diagram person boxes.

    Each boolean flag controls visibility of the corresponding content
    field in person box rendering. Default for new projects enables
    name, birth_date, and death_date only.

    Attributes:
        name: Show the person's display name.
        birth_date: Show the birth date.
        birth_place: Show the birth place.
        death_date: Show the death date.
        death_place: Show the death place.
        marriage_date: Show the marriage date.
        marriage_place: Show the marriage place.
        occupation: Show the person's occupation.
        photo: Show the profile photo.
        dna_info: Show DNA cluster/match indicators.
        notes: Show research notes excerpt.
    """

    name: bool = True
    birth_date: bool = True
    birth_place: bool = False
    death_date: bool = True
    death_place: bool = False
    marriage_date: bool = False
    marriage_place: bool = False
    occupation: bool = False
    photo: bool = False
    dna_info: bool = False
    notes: bool = False


@dataclass
class DiagramSettings:
    """Settings controlling diagram view depth limits.

    Attributes:
        ancestry_depth: Number of ancestor generations to display (1-10).
        descendants_depth: Number of descendant generations to display (1-10).
    """

    ancestry_depth: int = 4
    descendants_depth: int = 4


@dataclass
class UiState:
    """Optional UI state for restoring window layout on reopen.

    All fields are optional. When None, the application uses its own
    defaults for window sizing and layout.

    Attributes:
        window_width: Last known window width in pixels.
        window_height: Last known window height in pixels.
        splitter_position: Last known splitter position in pixels.
        last_view: Last active diagram view type.
    """

    window_width: Optional[int] = None
    window_height: Optional[int] = None
    splitter_position: Optional[int] = None
    last_view: Optional[str] = None


@dataclass
class ProjectSettings:
    """Container for all project-level settings.

    Attributes:
        person_box_config: Configuration for person box content fields.
        diagram_settings: Diagram view depth settings.
        ui_state: Optional saved UI layout state.
    """

    person_box_config: PersonBoxConfig = field(default_factory=PersonBoxConfig)
    diagram_settings: DiagramSettings = field(default_factory=DiagramSettings)
    ui_state: UiState = field(default_factory=UiState)


def create_default_settings() -> ProjectSettings:
    """Create a new ProjectSettings instance with default values.

    Returns a settings object suitable for new projects, with name,
    birth_date, and death_date enabled in person box config, ancestry
    and descendants depth set to 4, and no saved UI state.

    Returns:
        A ProjectSettings instance with all default values.
    """
    return ProjectSettings()


def read_settings(path: Path) -> ProjectSettings:
    """Read project settings from a JSON file.

    If the file does not exist, returns default settings. Handles
    partial data gracefully by merging with defaults so that new
    fields added in future versions get their default values.

    Args:
        path: Path to the settings JSON file.

    Returns:
        A ProjectSettings instance populated from file data, or
        defaults if the file is missing.

    Raises:
        OSError: If the file exists but cannot be read due to a
            file system error (permission denied, I/O error, etc.).
        json.JSONDecodeError: If the file contains invalid JSON.
    """
    if not path.exists():
        logger.info("Settings file not found at %s, using defaults.", path)
        return create_default_settings()

    data = json.loads(path.read_text(encoding="utf-8"))
    return _deserialize_settings(data)


def write_settings(settings: ProjectSettings, path: Path) -> None:
    """Serialize and write project settings to a JSON file.

    Writes UTF-8 encoded JSON with 2-space indentation for
    human readability. Creates parent directories if they do
    not exist.

    Args:
        settings: The ProjectSettings instance to persist.
        path: Path where the settings JSON file will be written.

    Raises:
        OSError: If the file cannot be written due to a file system
            error (permission denied, disk full, read-only, etc.).
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    data = _serialize_settings(settings)
    json_str = json.dumps(data, indent=2, ensure_ascii=False)
    path.write_text(json_str + "\n", encoding="utf-8")


def _serialize_settings(settings: ProjectSettings) -> dict:
    """Convert a ProjectSettings instance to a JSON-compatible dict.

    Args:
        settings: The settings to serialize.

    Returns:
        A nested dictionary ready for JSON serialization.
    """
    return asdict(settings)


def _deserialize_settings(data: dict) -> ProjectSettings:
    """Reconstruct a ProjectSettings instance from raw dict data.

    Handles missing keys gracefully by falling back to defaults,
    making the format forward-compatible when new fields are added.

    Args:
        data: Dictionary parsed from the settings JSON file.

    Returns:
        A fully populated ProjectSettings instance.
    """
    person_box_data = data.get("person_box_config", {})
    diagram_data = data.get("diagram_settings", {})
    ui_state_data = data.get("ui_state", {})

    person_box_config = PersonBoxConfig(
        name=person_box_data.get("name", True),
        birth_date=person_box_data.get("birth_date", True),
        birth_place=person_box_data.get("birth_place", False),
        death_date=person_box_data.get("death_date", True),
        death_place=person_box_data.get("death_place", False),
        marriage_date=person_box_data.get("marriage_date", False),
        marriage_place=person_box_data.get("marriage_place", False),
        occupation=person_box_data.get("occupation", False),
        photo=person_box_data.get("photo", False),
        dna_info=person_box_data.get("dna_info", False),
        notes=person_box_data.get("notes", False),
    )

    diagram_settings = DiagramSettings(
        ancestry_depth=diagram_data.get("ancestry_depth", 4),
        descendants_depth=diagram_data.get("descendants_depth", 4),
    )

    ui_state = UiState(
        window_width=ui_state_data.get("window_width"),
        window_height=ui_state_data.get("window_height"),
        splitter_position=ui_state_data.get("splitter_position"),
        last_view=ui_state_data.get("last_view"),
    )

    return ProjectSettings(
        person_box_config=person_box_config,
        diagram_settings=diagram_settings,
        ui_state=ui_state,
    )
