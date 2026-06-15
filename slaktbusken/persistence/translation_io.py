"""Read and write translation JSON files for GEDCOM↔App_JSON ID mapping.

Translation files live in the project's ``translation/`` subfolder and map
GEDCOM identifiers to App_JSON identifiers.  There are three files:

- **sources.json** – maps GEDCOM source IDs to App_JSON source IDs
- **places.json** – maps GEDCOM place strings to App_JSON place IDs
- **persons.json** – maps GEDCOM person/family IDs to App_JSON person/family IDs
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class SourceMapping:
    """A single GEDCOM source → App_JSON source translation entry.

    Attributes:
        gedcom_id: The GEDCOM source cross-reference identifier (e.g. ``"@S1@"``).
        app_id: The corresponding App_JSON source ID (e.g. ``"source_birth_005"``).
        title: Human-readable title for the source (aids manual editing).
    """

    gedcom_id: str
    app_id: str
    title: str = ""


@dataclass
class PlaceMapping:
    """A single GEDCOM place string → App_JSON place translation entry.

    Attributes:
        gedcom_place: The verbatim GEDCOM place string
            (e.g. ``"Ljusdal, Gävleborgs län, Sverige"``).
        app_id: The corresponding App_JSON place ID
            (e.g. ``"place_ljusdal_parish"``).
        name: Short display name for the place (e.g. ``"Ljusdal"``).
    """

    gedcom_place: str
    app_id: str
    name: str = ""


@dataclass
class PersonMapping:
    """A single GEDCOM person → App_JSON person translation entry.

    Attributes:
        gedcom_id: The GEDCOM individual cross-reference (e.g. ``"@I1@"``).
        app_id: The corresponding App_JSON person ID (e.g. ``"person_1"``).
        fingerprint: Optional composite-key hash used for re-import matching.
    """

    gedcom_id: str
    app_id: str
    fingerprint: Optional[str] = None


@dataclass
class FamilyMapping:
    """A single GEDCOM family → App_JSON family translation entry.

    Attributes:
        gedcom_id: The GEDCOM family cross-reference (e.g. ``"@F1@"``).
        app_id: The corresponding App_JSON family ID (e.g. ``"family_001"``).
    """

    gedcom_id: str
    app_id: str


@dataclass
class TranslationData:
    """Container holding all translation mappings for a project.

    Attributes:
        sources: List of GEDCOM source → App_JSON source mappings.
        places: List of GEDCOM place → App_JSON place mappings.
        persons: List of GEDCOM person → App_JSON person mappings.
        families: List of GEDCOM family → App_JSON family mappings.
    """

    sources: list[SourceMapping] = field(default_factory=list)
    places: list[PlaceMapping] = field(default_factory=list)
    persons: list[PersonMapping] = field(default_factory=list)
    families: list[FamilyMapping] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class TranslationIOError(OSError):
    """Raised when a translation file cannot be read or written.

    Wraps the underlying OS/IO error with additional context about which
    translation file was involved.
    """

    def __init__(self, message: str, path: Path, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.path = path
        self.__cause__ = cause


# ---------------------------------------------------------------------------
# Read functions
# ---------------------------------------------------------------------------


def read_sources(path: Path) -> list[SourceMapping]:
    """Load source translation mappings from a JSON file.

    Args:
        path: Path to ``sources.json``.

    Returns:
        A list of :class:`SourceMapping` instances.  Returns an empty list if
        the file does not exist.

    Raises:
        TranslationIOError: If the file exists but cannot be read or parsed.
    """
    data = _read_json(path)
    if data is None:
        return []

    mappings: list[SourceMapping] = []
    for entry in data.get("mappings", []):
        mappings.append(
            SourceMapping(
                gedcom_id=entry.get("gedcom_id", ""),
                app_id=entry.get("app_id", ""),
                title=entry.get("title", ""),
            )
        )
    return mappings


def read_places(path: Path) -> list[PlaceMapping]:
    """Load place translation mappings from a JSON file.

    Args:
        path: Path to ``places.json``.

    Returns:
        A list of :class:`PlaceMapping` instances.  Returns an empty list if
        the file does not exist.

    Raises:
        TranslationIOError: If the file exists but cannot be read or parsed.
    """
    data = _read_json(path)
    if data is None:
        return []

    mappings: list[PlaceMapping] = []
    for entry in data.get("mappings", []):
        mappings.append(
            PlaceMapping(
                gedcom_place=entry.get("gedcom_place", ""),
                app_id=entry.get("app_id", ""),
                name=entry.get("name", ""),
            )
        )
    return mappings


def read_persons(path: Path) -> tuple[list[PersonMapping], list[FamilyMapping]]:
    """Load person and family translation mappings from a JSON file.

    The persons translation file contains both person mappings and family
    mappings in separate top-level arrays.

    Args:
        path: Path to ``persons.json``.

    Returns:
        A tuple of ``(person_mappings, family_mappings)``.  Returns empty lists
        for both if the file does not exist.

    Raises:
        TranslationIOError: If the file exists but cannot be read or parsed.
    """
    data = _read_json(path)
    if data is None:
        return [], []

    person_mappings: list[PersonMapping] = []
    for entry in data.get("person_mappings", []):
        person_mappings.append(
            PersonMapping(
                gedcom_id=entry.get("gedcom_id", ""),
                app_id=entry.get("app_id", ""),
                fingerprint=entry.get("fingerprint"),
            )
        )

    family_mappings: list[FamilyMapping] = []
    for entry in data.get("family_mappings", []):
        family_mappings.append(
            FamilyMapping(
                gedcom_id=entry.get("gedcom_id", ""),
                app_id=entry.get("app_id", ""),
            )
        )

    return person_mappings, family_mappings


def read_all(translation_dir: Path) -> TranslationData:
    """Load all translation files from a translation directory.

    Convenience function that reads sources.json, places.json, and
    persons.json from the given directory and returns a unified
    :class:`TranslationData` container.

    Args:
        translation_dir: Path to the project's ``translation/`` directory.

    Returns:
        A :class:`TranslationData` instance with all mappings populated.
        Missing files result in empty lists for the corresponding mapping type.

    Raises:
        TranslationIOError: If any existing file cannot be read or parsed.
    """
    sources = read_sources(translation_dir / "sources.json")
    places = read_places(translation_dir / "places.json")
    persons, families = read_persons(translation_dir / "persons.json")
    return TranslationData(
        sources=sources,
        places=places,
        persons=persons,
        families=families,
    )


# ---------------------------------------------------------------------------
# Write functions
# ---------------------------------------------------------------------------


def write_sources(mappings: list[SourceMapping], path: Path) -> None:
    """Write source translation mappings to a JSON file.

    Creates parent directories if they do not exist.  The output is UTF-8
    encoded with 2-space indentation for human readability.

    Args:
        mappings: The source mappings to persist.
        path: Destination path for ``sources.json``.

    Raises:
        TranslationIOError: If the file cannot be written.
    """
    data = {
        "mappings": [
            {
                "gedcom_id": m.gedcom_id,
                "app_id": m.app_id,
                "title": m.title,
            }
            for m in mappings
        ]
    }
    _write_json(data, path)


def write_places(mappings: list[PlaceMapping], path: Path) -> None:
    """Write place translation mappings to a JSON file.

    Creates parent directories if they do not exist.  The output is UTF-8
    encoded with 2-space indentation for human readability.

    Args:
        mappings: The place mappings to persist.
        path: Destination path for ``places.json``.

    Raises:
        TranslationIOError: If the file cannot be written.
    """
    data = {
        "mappings": [
            {
                "gedcom_place": m.gedcom_place,
                "app_id": m.app_id,
                "name": m.name,
            }
            for m in mappings
        ]
    }
    _write_json(data, path)


def write_persons(
    person_mappings: list[PersonMapping],
    family_mappings: list[FamilyMapping],
    path: Path,
) -> None:
    """Write person and family translation mappings to a JSON file.

    Creates parent directories if they do not exist.  The output is UTF-8
    encoded with 2-space indentation for human readability.

    Args:
        person_mappings: The person mappings to persist.
        family_mappings: The family mappings to persist.
        path: Destination path for ``persons.json``.

    Raises:
        TranslationIOError: If the file cannot be written.
    """
    data: dict = {
        "person_mappings": [
            {
                "gedcom_id": m.gedcom_id,
                "app_id": m.app_id,
                "fingerprint": m.fingerprint,
            }
            for m in person_mappings
        ],
        "family_mappings": [
            {
                "gedcom_id": m.gedcom_id,
                "app_id": m.app_id,
            }
            for m in family_mappings
        ],
    }
    _write_json(data, path)


def write_all(data: TranslationData, translation_dir: Path) -> None:
    """Write all translation files to a translation directory.

    Convenience function that persists all mapping types to their respective
    JSON files within the given directory.

    Args:
        data: The :class:`TranslationData` container with all mappings.
        translation_dir: Path to the project's ``translation/`` directory.

    Raises:
        TranslationIOError: If any file cannot be written.
    """
    write_sources(data.sources, translation_dir / "sources.json")
    write_places(data.places, translation_dir / "places.json")
    write_persons(data.persons, data.families, translation_dir / "persons.json")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _read_json(path: Path) -> dict | None:
    """Read and parse a JSON file, returning None if the file doesn't exist.

    Args:
        path: Path to the JSON file.

    Returns:
        The parsed JSON as a dict, or None if the file does not exist.

    Raises:
        TranslationIOError: If the file exists but cannot be read or contains
            invalid JSON.
    """
    if not path.exists():
        return None

    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise TranslationIOError(
            f"Ogiltig JSON i översättningsfil: {path.name} ({exc})",
            path=path,
            cause=exc,
        ) from exc
    except OSError as exc:
        raise TranslationIOError(
            f"Kan inte läsa översättningsfil: {path.name} ({exc})",
            path=path,
            cause=exc,
        ) from exc


def _write_json(data: dict, path: Path) -> None:
    """Serialize a dict to a JSON file with UTF-8 encoding and 2-space indent.

    Creates parent directories if they do not exist.

    Args:
        data: The dictionary to serialize.
        path: Destination file path.

    Raises:
        TranslationIOError: If the file cannot be written.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(data, ensure_ascii=False, indent=2)
        path.write_text(text + "\n", encoding="utf-8")
    except OSError as exc:
        raise TranslationIOError(
            f"Kan inte skriva översättningsfil: {path.name} ({exc})",
            path=path,
            cause=exc,
        ) from exc
