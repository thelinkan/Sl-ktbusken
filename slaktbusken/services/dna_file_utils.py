"""DNA subfolder file management utilities.

Provides functions to read/write/delete JSON files in the dna/ subfolder
relative to the project file location.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


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
    file_path = dna_folder / filename
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
    """
    dna_folder = get_dna_folder(project_path)
    file_path = dna_folder / filename
    return json.loads(file_path.read_text(encoding="utf-8"))


def delete_dna_file(project_path: Path, filename: str) -> None:
    """Delete a file from the dna/ subfolder.

    Logs a warning if the file doesn't exist (non-fatal).

    Args:
        project_path: Path to the .json.gz project file.
        filename: The filename within the dna/ subfolder.
    """
    dna_folder = get_dna_folder(project_path)
    file_path = dna_folder / filename
    if file_path.exists():
        file_path.unlink()
    else:
        logger.warning("DNA-fil hittades inte vid borttagning: %s", file_path)
