"""Service for managing photo media items.

PhotoService encapsulates business logic for photo file validation,
path computation, title formatting with Foto_Typ prefix, and
synchronization of linked entity records for person mentions.
"""

from __future__ import annotations

import re
from pathlib import Path

from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.project import ProjectData


class PhotoService:
    """Business logic for photo management in the Foto_Tab."""

    ALLOWED_EXTENSIONS: set[str] = {
        ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp"
    }

    FOTO_TYPES: list[str] = [
        "Porträtt",
        "Gruppfoto",
        "Familjefoto",
        "Bröllopsfoto",
        "Konfirmationsfoto",
        "Dopfoto",
        "Skolfoto",
        "Militärfoto",
        "Arbetsfoto",
        "Begravningsfoto",
        "Gravfoto",
        "Övrigt foto",
    ]

    def __init__(self, project_data: ProjectData, foto_mapp: Path) -> None:
        self._project_data = project_data
        self._foto_mapp = foto_mapp

    def validate_file_extension(self, file_path: str) -> bool:
        """Check if file extension is in ALLOWED_EXTENSIONS."""
        ext = Path(file_path).suffix.lower()
        return ext in self.ALLOWED_EXTENSIONS

    def compute_target_path(self, source_path: Path) -> tuple[Path, bool]:
        """Determine target path in foto_mapp. Returns (target, needs_copy).

        If source_path is already inside foto_mapp, returns its relative path
        without needing a copy. Otherwise returns foto_mapp / filename and
        signals that a copy is needed.
        """
        try:
            relative = source_path.resolve().relative_to(self._foto_mapp.resolve())
            return relative, False
        except ValueError:
            # Source is outside foto_mapp - needs copy
            target = self._foto_mapp / source_path.name
            return target, True

    def resolve_filename_conflict(self, target_path: Path) -> Path:
        """Generate unique filename with numeric suffix if conflict exists.

        Appends _1, _2, etc. before the file extension until a path is found
        that does not exist on disk.
        """
        if not target_path.exists():
            return target_path

        stem = target_path.stem
        suffix = target_path.suffix
        parent = target_path.parent
        counter = 1

        while True:
            candidate = parent / f"{stem}_{counter}{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

    def format_title(self, foto_typ: str, title: str) -> str:
        """Format as '[Foto_Typ] title'."""
        return f"[{foto_typ}] {title}"

    def parse_title(self, raw_title: str) -> tuple[str, str]:
        """Parse '[Foto_Typ] title' into (foto_typ, title).

        Returns ('Övrigt foto', raw_title) if no bracket prefix found.
        """
        match = re.match(r"^\[([^\]]+)\] (.*)", raw_title, re.DOTALL)
        if match:
            return match.group(1), match.group(2)
        return "Övrigt foto", raw_title

    def get_photos_for_person(self, person_id: str) -> list[MediaItem]:
        """Return all photo MediaItems linked to person, ordered by title.

        A photo is linked to a person via a LinkedEntity with
        entity_type="person" and matching entity_id.
        """
        photos: list[MediaItem] = []
        for item in self._project_data.media:
            if item.type != "photo":
                continue
            for link in item.linked_entities:
                if link.entity_type == "person" and link.entity_id == person_id:
                    photos.append(item)
                    break

        photos.sort(key=lambda m: m.title.lower())
        return photos

    def sync_linked_entities(
        self, media_item: MediaItem, new_person_ids: list[str]
    ) -> None:
        """Synchronize Linked_Entity records with mentioned_person_ids.

        Ensures a LinkedEntity with entity_type="person" exists for each
        person_id in new_person_ids. Removes stale person links that are
        no longer in the list. Non-person linked entities are left untouched.
        """
        new_ids_set = set(new_person_ids)

        # Partition existing linked entities into person and non-person
        non_person_links: list[LinkedEntity] = []
        existing_person_ids: set[str] = set()

        for link in media_item.linked_entities:
            if link.entity_type == "person":
                existing_person_ids.add(link.entity_id)
            else:
                non_person_links.append(link)

        # Determine which to add and which to remove
        to_add = new_ids_set - existing_person_ids
        to_remove = existing_person_ids - new_ids_set

        # Keep person links that are still valid
        kept_person_links: list[LinkedEntity] = [
            link
            for link in media_item.linked_entities
            if link.entity_type == "person" and link.entity_id not in to_remove
        ]

        # Add new person links
        for pid in sorted(to_add):
            kept_person_links.append(
                LinkedEntity(entity_type="person", entity_id=pid)
            )

        # Rebuild linked_entities: non-person links + person links
        media_item.linked_entities = non_person_links + kept_person_links
