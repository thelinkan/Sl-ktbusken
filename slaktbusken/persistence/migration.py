"""Migration management for App_JSON format version upgrades.

This module provides the MigrationManager class which handles detection of
outdated or too-new format versions, sequential migration between versions
via registered migration functions, and backup creation before applying
migrations.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable


class MigrationError(Exception):
    """Raised when no migration path exists between versions.

    Attributes:
        from_version: The source version that has no registered migration.
        to_version: The target version (typically CURRENT_VERSION).
    """

    def __init__(self, from_version: str, to_version: str) -> None:
        self.from_version = from_version
        self.to_version = to_version
        super().__init__(
            f"Ingen migreringsväg hittades från version {from_version} "
            f"till version {to_version}."
        )


def _parse_version(version: str) -> tuple[int, int]:
    """Parse a semantic version string (major.minor) into a tuple.

    Args:
        version: A version string in "major.minor" format (e.g., "0.1", "1.2").

    Returns:
        A tuple of (major, minor) integers.

    Raises:
        ValueError: If the version string is not in valid major.minor format.
    """
    parts = version.strip().split(".")
    if len(parts) != 2:
        raise ValueError(
            f"Ogiltig version: '{version}'. Förväntat format: 'major.minor'."
        )
    return (int(parts[0]), int(parts[1]))


class MigrationManager:
    """Manages sequential migrations between App_JSON format versions.

    The MigrationManager maintains a registry of migration functions that
    transform data from one format version to the next. Migrations are
    applied sequentially (chained) from the file's version up to the
    current application version.

    Class Attributes:
        CURRENT_VERSION: The current App_JSON format version string.

    Example:
        Register a migration::

            @MigrationManager.register("0.1", "0.2")
            def migrate_01_to_02(data: dict) -> dict:
                data["new_field"] = []
                data["version"] = "0.2"
                return data

        Apply migrations::

            migrated_data = MigrationManager.migrate(old_data, "0.1")
    """

    CURRENT_VERSION: str = "0.1"

    # Registry: maps source version → (target version, migration function)
    _migrations: dict[str, tuple[str, Callable[[dict], dict]]] = {}

    @classmethod
    def register(cls, from_version: str, to_version: str) -> Callable:
        """Decorator to register a migration function.

        Registers the decorated function as the migration that transforms
        data from ``from_version`` to ``to_version``. Only one migration
        may be registered per source version.

        Args:
            from_version: The source format version (e.g., "0.1").
            to_version: The target format version (e.g., "0.2").

        Returns:
            A decorator that registers the function and returns it unchanged.

        Example:
            ::

                @MigrationManager.register("0.1", "0.2")
                def _migrate_0_1_to_0_2(data: dict) -> dict:
                    data["new_section"] = []
                    data["version"] = "0.2"
                    return data
        """

        def decorator(func: Callable[[dict], dict]) -> Callable[[dict], dict]:
            cls._migrations[from_version] = (to_version, func)
            return func

        return decorator

    @classmethod
    def migrate(cls, data: dict, from_version: str) -> dict:
        """Apply sequential migrations from from_version to CURRENT_VERSION.

        Looks up the migration registered for the current version, applies it
        to produce data at the next version, then repeats until the data
        reaches CURRENT_VERSION.

        Args:
            data: The raw project data dictionary to migrate.
            from_version: The format version the data is currently at.

        Returns:
            The migrated data dictionary at CURRENT_VERSION.

        Raises:
            MigrationError: If no migration is registered for an intermediate
                version, meaning no complete path from from_version to
                CURRENT_VERSION exists.
        """
        current = from_version
        while current != cls.CURRENT_VERSION:
            if current not in cls._migrations:
                raise MigrationError(current, cls.CURRENT_VERSION)
            target, func = cls._migrations[current]
            data = func(data)
            current = target
        return data

    @classmethod
    def needs_migration(cls, version: str) -> bool:
        """Check if a file version requires migration (is older than current).

        Args:
            version: The format version string from the file (e.g., "0.1").

        Returns:
            True if the given version is strictly less than CURRENT_VERSION,
            meaning the file data needs to be migrated forward.
        """
        return _parse_version(version) < _parse_version(cls.CURRENT_VERSION)

    @classmethod
    def is_too_new(cls, version: str) -> bool:
        """Check if a file version is newer than what this app supports.

        Args:
            version: The format version string from the file (e.g., "2.0").

        Returns:
            True if the given version is strictly greater than CURRENT_VERSION,
            meaning this application cannot open the file.
        """
        return _parse_version(version) > _parse_version(cls.CURRENT_VERSION)

    @staticmethod
    def create_backup(path: Path, old_version: str) -> Path:
        """Create a backup copy of the project file before migrating.

        The backup is placed in the same directory as the original file,
        with the old version number appended to the filename stem. For
        example, ``project.json.gz`` becomes ``project_v0.1.json.gz``.

        Args:
            path: Path to the original project file.
            old_version: The version string of the file before migration,
                used in the backup filename suffix.

        Returns:
            The Path to the newly created backup file.

        Raises:
            OSError: If the backup file cannot be created (e.g., permission
                denied, disk full).
        """
        # Handle compound extensions like .json.gz
        suffixes = "".join(path.suffixes)
        # Get the base name without any suffixes
        stem = path.name[: len(path.name) - len(suffixes)]

        backup_name = f"{stem}_v{old_version}{suffixes}"
        backup_path = path.parent / backup_name
        shutil.copy2(path, backup_path)
        return backup_path
