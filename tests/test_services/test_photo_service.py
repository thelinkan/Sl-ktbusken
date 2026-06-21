"""Unit tests for PhotoService.

Tests cover file extension validation, path computation, filename conflict
resolution, title formatting/parsing, photo retrieval, and linked entity
synchronization.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services.photo_service import PhotoService


@pytest.fixture
def project_data() -> ProjectData:
    """Create a minimal ProjectData instance."""
    return ProjectData(project=ProjectMetadata(title="Test"))


@pytest.fixture
def foto_mapp(tmp_path: Path) -> Path:
    """Create a temporary foto_mapp directory."""
    mapp = tmp_path / "fotos"
    mapp.mkdir()
    return mapp


@pytest.fixture
def service(project_data: ProjectData, foto_mapp: Path) -> PhotoService:
    """Create a PhotoService instance."""
    return PhotoService(project_data, foto_mapp)


# ---------------------------------------------------------------------------
# validate_file_extension
# ---------------------------------------------------------------------------


class TestValidateFileExtension:
    """Tests for file extension validation (Req 3.8)."""

    @pytest.mark.parametrize(
        "filename",
        [
            "photo.jpg",
            "photo.jpeg",
            "photo.png",
            "photo.tif",
            "photo.tiff",
            "photo.bmp",
            "photo.gif",
            "photo.webp",
        ],
    )
    def test_allowed_extensions(self, service: PhotoService, filename: str) -> None:
        assert service.validate_file_extension(filename) is True

    @pytest.mark.parametrize(
        "filename",
        [
            "photo.JPG",
            "photo.JPEG",
            "photo.PNG",
            "photo.Tif",
        ],
    )
    def test_case_insensitive(self, service: PhotoService, filename: str) -> None:
        assert service.validate_file_extension(filename) is True

    @pytest.mark.parametrize(
        "filename",
        [
            "document.pdf",
            "text.txt",
            "archive.zip",
            "video.mp4",
            "noext",
        ],
    )
    def test_rejected_extensions(self, service: PhotoService, filename: str) -> None:
        assert service.validate_file_extension(filename) is False


# ---------------------------------------------------------------------------
# compute_target_path
# ---------------------------------------------------------------------------


class TestComputeTargetPath:
    """Tests for path computation (Req 4.1, 4.2)."""

    def test_file_inside_foto_mapp_returns_relative(
        self, service: PhotoService, foto_mapp: Path
    ) -> None:
        inside_file = foto_mapp / "portrait.jpg"
        inside_file.touch()
        target, needs_copy = service.compute_target_path(inside_file)
        assert needs_copy is False
        assert target == Path("portrait.jpg")

    def test_file_in_subfolder_returns_relative(
        self, service: PhotoService, foto_mapp: Path
    ) -> None:
        sub = foto_mapp / "2024"
        sub.mkdir()
        inside_file = sub / "wedding.png"
        inside_file.touch()
        target, needs_copy = service.compute_target_path(inside_file)
        assert needs_copy is False
        assert target == Path("2024/wedding.png")

    def test_file_outside_foto_mapp_needs_copy(
        self, service: PhotoService, foto_mapp: Path, tmp_path: Path
    ) -> None:
        external = tmp_path / "desktop" / "photo.jpg"
        external.parent.mkdir(parents=True, exist_ok=True)
        external.touch()
        target, needs_copy = service.compute_target_path(external)
        assert needs_copy is True
        assert target == foto_mapp / "photo.jpg"


# ---------------------------------------------------------------------------
# resolve_filename_conflict
# ---------------------------------------------------------------------------


class TestResolveFilenameConflict:
    """Tests for filename conflict resolution (Req 4.5)."""

    def test_no_conflict_returns_same_path(
        self, service: PhotoService, foto_mapp: Path
    ) -> None:
        target = foto_mapp / "unique.jpg"
        result = service.resolve_filename_conflict(target)
        assert result == target

    def test_conflict_appends_1(
        self, service: PhotoService, foto_mapp: Path
    ) -> None:
        existing = foto_mapp / "test.jpg"
        existing.touch()
        result = service.resolve_filename_conflict(existing)
        assert result == foto_mapp / "test_1.jpg"

    def test_multiple_conflicts_increments(
        self, service: PhotoService, foto_mapp: Path
    ) -> None:
        (foto_mapp / "test.jpg").touch()
        (foto_mapp / "test_1.jpg").touch()
        (foto_mapp / "test_2.jpg").touch()
        result = service.resolve_filename_conflict(foto_mapp / "test.jpg")
        assert result == foto_mapp / "test_3.jpg"


# ---------------------------------------------------------------------------
# format_title / parse_title
# ---------------------------------------------------------------------------


class TestTitleFormatting:
    """Tests for title formatting and parsing (Req 3.4, 3.5, 3.6)."""

    def test_format_title(self, service: PhotoService) -> None:
        result = service.format_title("Porträtt", "Min bild")
        assert result == "[Porträtt] Min bild"

    def test_parse_title_with_bracket_prefix(self, service: PhotoService) -> None:
        foto_typ, title = service.parse_title("[Gruppfoto] Familjen 2024")
        assert foto_typ == "Gruppfoto"
        assert title == "Familjen 2024"

    def test_parse_title_without_bracket_prefix(self, service: PhotoService) -> None:
        foto_typ, title = service.parse_title("Just a title")
        assert foto_typ == "Övrigt foto"
        assert title == "Just a title"

    def test_roundtrip(self, service: PhotoService) -> None:
        original_typ = "Bröllopsfoto"
        original_title = "Vigsel i kyrkan"
        formatted = service.format_title(original_typ, original_title)
        parsed_typ, parsed_title = service.parse_title(formatted)
        assert parsed_typ == original_typ
        assert parsed_title == original_title

    def test_parse_empty_title_part(self, service: PhotoService) -> None:
        foto_typ, title = service.parse_title("[Porträtt] ")
        assert foto_typ == "Porträtt"
        assert title == ""


# ---------------------------------------------------------------------------
# get_photos_for_person
# ---------------------------------------------------------------------------


class TestGetPhotosForPerson:
    """Tests for photo retrieval (Req 3.2)."""

    def test_returns_photos_linked_to_person(
        self, project_data: ProjectData, foto_mapp: Path
    ) -> None:
        m1 = MediaItem(
            id="m1", type="photo", file="a.jpg", title="[Porträtt] Alpha",
            linked_entities=[LinkedEntity(entity_type="person", entity_id="p1")],
        )
        m2 = MediaItem(
            id="m2", type="photo", file="b.jpg", title="[Gruppfoto] Beta",
            linked_entities=[LinkedEntity(entity_type="person", entity_id="p1")],
        )
        m3 = MediaItem(
            id="m3", type="photo", file="c.jpg", title="[Dopfoto] Gamma",
            linked_entities=[LinkedEntity(entity_type="person", entity_id="p2")],
        )
        project_data.media = [m1, m2, m3]
        service = PhotoService(project_data, foto_mapp)

        photos = service.get_photos_for_person("p1")
        assert len(photos) == 2
        assert all(p.id in ("m1", "m2") for p in photos)

    def test_ordered_alphabetically_by_title(
        self, project_data: ProjectData, foto_mapp: Path
    ) -> None:
        m1 = MediaItem(
            id="m1", type="photo", file="a.jpg", title="[Porträtt] Zebra",
            linked_entities=[LinkedEntity(entity_type="person", entity_id="p1")],
        )
        m2 = MediaItem(
            id="m2", type="photo", file="b.jpg", title="[Gruppfoto] Alpha",
            linked_entities=[LinkedEntity(entity_type="person", entity_id="p1")],
        )
        project_data.media = [m1, m2]
        service = PhotoService(project_data, foto_mapp)

        photos = service.get_photos_for_person("p1")
        assert photos[0].id == "m2"  # Alpha before Zebra
        assert photos[1].id == "m1"

    def test_excludes_non_photo_media(
        self, project_data: ProjectData, foto_mapp: Path
    ) -> None:
        m1 = MediaItem(
            id="m1", type="document", file="doc.pdf", title="A doc",
            linked_entities=[LinkedEntity(entity_type="person", entity_id="p1")],
        )
        project_data.media = [m1]
        service = PhotoService(project_data, foto_mapp)

        photos = service.get_photos_for_person("p1")
        assert len(photos) == 0

    def test_empty_result_for_unknown_person(
        self, project_data: ProjectData, foto_mapp: Path
    ) -> None:
        service = PhotoService(project_data, foto_mapp)
        photos = service.get_photos_for_person("nobody")
        assert photos == []


# ---------------------------------------------------------------------------
# sync_linked_entities
# ---------------------------------------------------------------------------


class TestSyncLinkedEntities:
    """Tests for linked entity synchronization (Req 5.5, 5.6)."""

    def test_adds_missing_person_links(self, service: PhotoService) -> None:
        media = MediaItem(id="m1", type="photo", file="a.jpg", title="test")
        service.sync_linked_entities(media, ["p1", "p2"])

        person_links = [
            le for le in media.linked_entities if le.entity_type == "person"
        ]
        assert len(person_links) == 2
        assert {le.entity_id for le in person_links} == {"p1", "p2"}

    def test_removes_stale_person_links(self, service: PhotoService) -> None:
        media = MediaItem(
            id="m1", type="photo", file="a.jpg", title="test",
            linked_entities=[
                LinkedEntity(entity_type="person", entity_id="p1"),
                LinkedEntity(entity_type="person", entity_id="p2"),
            ],
        )
        service.sync_linked_entities(media, ["p1"])

        person_links = [
            le for le in media.linked_entities if le.entity_type == "person"
        ]
        assert len(person_links) == 1
        assert person_links[0].entity_id == "p1"

    def test_preserves_non_person_links(self, service: PhotoService) -> None:
        media = MediaItem(
            id="m1", type="photo", file="a.jpg", title="test",
            linked_entities=[
                LinkedEntity(entity_type="source", entity_id="s1"),
                LinkedEntity(entity_type="event", entity_id="e1"),
                LinkedEntity(entity_type="person", entity_id="p1"),
            ],
        )
        service.sync_linked_entities(media, ["p2"])

        non_person = [
            le for le in media.linked_entities if le.entity_type != "person"
        ]
        assert len(non_person) == 2
        assert {le.entity_id for le in non_person} == {"s1", "e1"}

    def test_no_change_when_already_in_sync(self, service: PhotoService) -> None:
        media = MediaItem(
            id="m1", type="photo", file="a.jpg", title="test",
            linked_entities=[
                LinkedEntity(entity_type="person", entity_id="p1"),
                LinkedEntity(entity_type="person", entity_id="p2"),
            ],
        )
        service.sync_linked_entities(media, ["p1", "p2"])

        person_links = [
            le for le in media.linked_entities if le.entity_type == "person"
        ]
        assert len(person_links) == 2
        assert {le.entity_id for le in person_links} == {"p1", "p2"}

    def test_empty_new_ids_removes_all_person_links(
        self, service: PhotoService
    ) -> None:
        media = MediaItem(
            id="m1", type="photo", file="a.jpg", title="test",
            linked_entities=[
                LinkedEntity(entity_type="person", entity_id="p1"),
                LinkedEntity(entity_type="source", entity_id="s1"),
            ],
        )
        service.sync_linked_entities(media, [])

        person_links = [
            le for le in media.linked_entities if le.entity_type == "person"
        ]
        assert len(person_links) == 0
        # Non-person link preserved
        assert len(media.linked_entities) == 1
        assert media.linked_entities[0].entity_id == "s1"
