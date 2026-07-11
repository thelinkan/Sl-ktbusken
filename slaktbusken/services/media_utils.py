"""Utility functions for media file handling.

This module provides helpers for managing media files within a project,
including filename conflict resolution for copying files into the media directory.
"""

from __future__ import annotations

import os


def resolve_filename_conflict(target_name: str, existing_names: set[str]) -> str:
    """Resolve filename conflicts by appending a numeric suffix.

    If target_name is not in existing_names, returns it unchanged.
    Otherwise appends _{n} before the file extension where n is the smallest
    positive integer that produces a unique name.

    Args:
        target_name: The desired filename (e.g., "photo.jpg")
        existing_names: Set of filenames already present in the directory

    Returns:
        A unique filename that doesn't conflict with existing_names.

    Examples:
        resolve_filename_conflict("photo.jpg", set()) → "photo.jpg"
        resolve_filename_conflict("photo.jpg", {"photo.jpg"}) → "photo_1.jpg"
        resolve_filename_conflict("photo.jpg", {"photo.jpg", "photo_1.jpg"}) → "photo_2.jpg"
        resolve_filename_conflict("file", {"file"}) → "file_1"
    """
    if target_name not in existing_names:
        return target_name

    stem, ext = os.path.splitext(target_name)
    n = 1
    while True:
        candidate = f"{stem}_{n}{ext}"
        if candidate not in existing_names:
            return candidate
        n += 1
