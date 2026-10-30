"""DNA subfolder file management utilities.

Provides functions to read/write/delete JSON files in the dna/ subfolder
relative to the project file location.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from slaktbusken.services.safe_io import resolve_within

logger = logging.getLogger(__name__)


def _resolve_dna_file(dna_folder: Path, filename: str) -> Path:
    """Resolve *filename* strictly within *dna_folder*.

    The filename originates from project data (a profile's ``raw_data_file`` or
    a match/triangulation ``segment_file``). An absolute path or a ``..``
    sequence must not let a read, write, or delete touch a file outside the
    dna/ folder, so a reference that escapes it is rejected rather than acted
    on.

    Args:
        dna_folder: The project's dna/ subfolder.
        filename: The stored filename within that folder.

    Returns:
        The resolved path inside ``dna_folder``.

    Raises:
        ValueError: When ``filename`` resolves outside ``dna_folder``.
    """
    resolved = resolve_within(dna_folder, filename)
    if resolved is None:
        raise ValueError(f"DNA-filnamn utanför dna-mappen: {filename!r}")
    return resolved


def get_dna_folder(project_path: Path) -> Path:
    """Resolve the dna/ subfolder path relative to the project file's parent directory.

    Args:
        project_path: Path to the .json.gz project file, or the project folder itself.

    Returns:
        Path to the dna/ subfolder (may not exist yet).
    """
    if project_path.is_dir():
        return project_path / "dna"
    return project_path.parent / "dna"


def ensure_dna_folder_exists(project_path: Path) -> Path:
    """Create the dna/ subfolder if it doesn't exist.

    Args:
        project_path: Path to the .json.gz project file.

    Returns:
        Path to the dna/ subfolder (guaranteed to exist after call).
    """
    dna_folder = get_dna_folder(project_path)
    dna_folder.mkdir(parents=True, exist_ok=True)
    return dna_folder


def write_dna_file(project_path: Path, filename: str, data: Any) -> None:
    """Write data as JSON to a file in the dna/ subfolder.

    Creates the dna/ folder if it doesn't exist.

    Args:
        project_path: Path to the .json.gz project file.
        filename: The filename within the dna/ subfolder (e.g., 'raw_profile123.json').
        data: Data to serialize as JSON.
    """
    dna_folder = ensure_dna_folder_exists(project_path)
    file_path = _resolve_dna_file(dna_folder, filename)
    file_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_dna_file(project_path: Path, filename: str) -> Any:
    """Read and parse a JSON file from the dna/ subfolder.

    Args:
        project_path: Path to the .json.gz project file.
        filename: The filename within the dna/ subfolder.

    Returns:
        Parsed JSON data.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        json.JSONDecodeError: If the file content is not valid JSON.
        ValueError: If the filename resolves outside the dna/ folder.
    """
    dna_folder = get_dna_folder(project_path)
    file_path = _resolve_dna_file(dna_folder, filename)
    return json.loads(file_path.read_text(encoding="utf-8"))


def delete_dna_file(project_path: Path, filename: str) -> None:
    """Delete a file from the dna/ subfolder.

    Logs a warning if the file doesn't exist (non-fatal).

    Args:
        project_path: Path to the .json.gz project file.
        filename: The filename within the dna/ subfolder.
    """
    dna_folder = get_dna_folder(project_path)
    try:
        file_path = _resolve_dna_file(dna_folder, filename)
    except ValueError:
        # A filename pointing outside the dna/ folder must never cause a delete
        # elsewhere on disk; refuse it rather than unlinking an arbitrary file.
        logger.warning("Vägrade att ta bort DNA-fil utanför dna-mappen: %s", filename)
        return
    if file_path.exists():
        file_path.unlink()
    else:
        logger.warning("DNA-fil hittades inte vid borttagning: %s", file_path)
