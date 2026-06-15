"""Atomic read/write of gzipped JSON project files.

Provides the FilePersistence class for saving and loading ProjectData
in .json.gz format with atomic writes (temp file + os.replace) and
early version checking before full deserialization.
"""

from __future__ import annotations

import gzip
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from slaktbusken.model.project import ProjectData

# Current format version supported by this application.
CURRENT_VERSION = "0.1"


class CorruptedFileError(Exception):
    """Raised when a project file cannot be read due to corruption.

    The message is in Swedish and describes the specific problem
    (invalid gzip, JSON parse error, or missing required sections).
    """


class UnsupportedVersionError(Exception):
    """Raised when a project file has a newer version than supported.

    The message is in Swedish and indicates that the file requires
    a newer version of Släktbusken.
    """


class FilePersistence:
    """Atomic read/write of gzipped JSON project files."""

    @staticmethod
    def save(data: ProjectData, path: Path) -> None:
        """Serialize and atomically save ProjectData to a .json.gz file.

        Steps:
            1. Serialize ProjectData to JSON (UTF-8) with format_version first.
            2. Gzip-compress the JSON bytes.
            3. Write compressed data to a temp file in the same directory.
            4. Atomically replace the target file via os.replace.

        Args:
            data: The ProjectData instance to persist.
            path: Target file path (should end with .json.gz).
        """
        from slaktbusken.persistence.serialization import serialize

        json_bytes = serialize(data).encode("utf-8")
        compressed = gzip.compress(json_bytes)

        # Write to a temp file in the same directory for atomic replace.
        target_dir = path.parent
        target_dir.mkdir(parents=True, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(
            suffix=".tmp", prefix=".slaktbusken_", dir=str(target_dir)
        )
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(compressed)
            os.replace(tmp_path, str(path))
        except BaseException:
            # Clean up temp file on any failure.
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    @staticmethod
    def load(path: Path) -> ProjectData:
        """Load and deserialize a .json.gz project file.

        Steps:
            1. Read and decompress .json.gz data.
            2. Extract format_version without full deserialization.
            3. If version > CURRENT_VERSION: raise UnsupportedVersionError.
            4. If version < CURRENT_VERSION: run migration (if available).
            5. Parse and validate full JSON.
            6. Deserialize into ProjectData.

        Args:
            path: Path to the .json.gz file to load.

        Returns:
            Deserialized ProjectData instance.

        Raises:
            CorruptedFileError: If the file has invalid gzip, JSON errors,
                or missing required sections.
            UnsupportedVersionError: If the file version is newer than
                what this application supports.
            FileNotFoundError: If the file does not exist.
        """
        from slaktbusken.persistence.serialization import deserialize

        # Step 1: Read and decompress.
        raw_bytes = _read_and_decompress(path)

        # Step 2: Extract version without full parse.
        raw_dict = _parse_json(raw_bytes, path)
        version = _extract_version(raw_dict, path)

        # Step 3: Check if version is too new.
        if _is_newer_version(version):
            raise UnsupportedVersionError(
                f"Filen skapades med en nyare version av Släktbusken "
                f"(filversion {version}, appversion {CURRENT_VERSION}). "
                f"Uppdatera Släktbusken för att kunna öppna denna fil."
            )

        # Step 4: If version is older, attempt migration.
        if _is_older_version(version):
            raw_dict = _run_migration(raw_dict, version, path)

        # Step 5-6: Validate required sections and deserialize.
        _validate_required_sections(raw_dict, path)
        json_str = json.dumps(raw_dict, ensure_ascii=False)
        return deserialize(json_str)


def _read_and_decompress(path: Path) -> bytes:
    """Read a gzip file and return decompressed bytes.

    Raises:
        FileNotFoundError: If the file does not exist.
        CorruptedFileError: If the file has an invalid gzip header or
            cannot be decompressed.
    """
    if not path.exists():
        raise FileNotFoundError(f"Filen hittades inte: {path}")

    try:
        with open(path, "rb") as f:
            compressed = f.read()
        return gzip.decompress(compressed)
    except gzip.BadGzipFile:
        raise CorruptedFileError(
            f"Filen har ett ogiltigt gzip-format och kan inte läsas: {path.name}"
        )
    except OSError as e:
        raise CorruptedFileError(
            f"Filen kunde inte läsas på grund av ett filsystemfel: {e}"
        )


def _parse_json(raw_bytes: bytes, path: Path) -> dict[str, Any]:
    """Parse decompressed bytes as JSON.

    Raises:
        CorruptedFileError: If the content is not valid JSON.
    """
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise CorruptedFileError(
            f"Filen innehåller ogiltigt UTF-8 och kan inte tolkas: {path.name}"
        )

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise CorruptedFileError(
            f"Filen innehåller ogiltig JSON (rad {e.lineno}, kolumn {e.colno}): "
            f"{path.name}"
        )

    if not isinstance(data, dict):
        raise CorruptedFileError(
            f"Filen har ett oväntat format (förväntade ett JSON-objekt): {path.name}"
        )

    return data


def _extract_version(data: dict[str, Any], path: Path) -> str:
    """Extract format version from parsed JSON dict.

    Looks for 'format_version' first, then falls back to 'version'.

    Raises:
        CorruptedFileError: If neither format_version nor version is found.
    """
    version = data.get("format_version") or data.get("version")
    if version is None:
        raise CorruptedFileError(
            f"Filen saknar obligatoriskt fält 'format_version': {path.name}"
        )
    return str(version)


def _is_newer_version(version: str) -> bool:
    """Check if the file version is newer than the current application version."""
    return _compare_versions(version, CURRENT_VERSION) > 0


def _is_older_version(version: str) -> bool:
    """Check if the file version is older than the current application version."""
    return _compare_versions(version, CURRENT_VERSION) < 0


def _compare_versions(a: str, b: str) -> int:
    """Compare two version strings (dot-separated numbers).

    Returns:
        Negative if a < b, zero if a == b, positive if a > b.
    """
    parts_a = [int(x) for x in a.split(".")]
    parts_b = [int(x) for x in b.split(".")]

    # Pad shorter list with zeros.
    max_len = max(len(parts_a), len(parts_b))
    parts_a.extend([0] * (max_len - len(parts_a)))
    parts_b.extend([0] * (max_len - len(parts_b)))

    for pa, pb in zip(parts_a, parts_b):
        if pa < pb:
            return -1
        if pa > pb:
            return 1
    return 0


def _run_migration(data: dict[str, Any], version: str, path: Path) -> dict[str, Any]:
    """Attempt to run migrations on older version data.

    If the MigrationManager is available, delegates migration to it.
    Otherwise, proceeds with the data as-is (best effort for early
    development where migration infrastructure may not exist yet).

    Args:
        data: The parsed JSON dict at the older version.
        version: The file's format_version string.
        path: The file path (for backup creation).

    Returns:
        The migrated data dict.
    """
    try:
        from slaktbusken.persistence.migration import MigrationManager

        if MigrationManager.needs_migration(version):
            MigrationManager.create_backup(path, version)
            data = MigrationManager.migrate(data, version)
    except ImportError:
        # MigrationManager not yet implemented; proceed without migration.
        pass
    return data


def _validate_required_sections(data: dict[str, Any], path: Path) -> None:
    """Validate that the JSON contains required top-level sections.

    Raises:
        CorruptedFileError: If required sections are missing.
    """
    required_sections = {"format", "version", "project"}
    missing = required_sections - set(data.keys())
    if missing:
        missing_str = ", ".join(sorted(missing))
        raise CorruptedFileError(
            f"Filen saknar obligatoriska avsnitt ({missing_str}): {path.name}"
        )
