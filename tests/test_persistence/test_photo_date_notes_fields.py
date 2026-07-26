"""Unit tests for photo_date and notes fields on MediaItem.

Validates Requirements 4.9, 4.10, 6.3 - MediaItem stores photo date and notes.
"""

from __future__ import annotations

import json

from slaktbusken.model.media import MediaItem
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.persistence.serialization import deserialize, serialize


class TestPhotoDateAndNotesFields:
    """Tests for photo_date and notes field serialization behavior."""

    def test_photo_date_none_omitted_from_json(self) -> None:
        """When photo_date is None (default), it is omitted from serialized output."""
        item = MediaItem(id="m1", type="photo", file="img/test.jpg", title="Test")
        data = ProjectData(media=[item])
        json_str = serialize(data)
        parsed = json.loads(json_str)
        media_dict = parsed["media"][0]
        assert "photo_date" not in media_dict

    def test_notes_empty_omitted_from_json(self) -> None:
        """When notes is empty string (default), it is omitted from serialized output."""
        item = MediaItem(id="m1", type="photo", file="img/test.jpg", title="Test")
        data = ProjectData(media=[item])
        json_str = serialize(data)
        parsed = json.loads(json_str)
        media_dict = parsed["media"][0]
        assert "notes" not in media_dict

    def test_photo_date_populated_included_in_json(self) -> None:
        """When photo_date has a value, it is included in serialized output."""
        item = MediaItem(
            id="m1", type="photo", file="img/test.jpg", title="Test",
            photo_date={"year": 1920, "month": 5, "day": 15},
        )
        data = ProjectData(media=[item])
        json_str = serialize(data)
        parsed = json.loads(json_str)
        media_dict = parsed["media"][0]
        assert media_dict["photo_date"] == {"year": 1920, "month": 5, "day": 15}

    def test_notes_populated_included_in_json(self) -> None:
        """When notes has content, it is included in serialized output."""
        item = MediaItem(
            id="m1", type="photo", file="img/test.jpg", title="Test",
            notes="This is a test note",
        )
        data = ProjectData(media=[item])
        json_str = serialize(data)
        parsed = json.loads(json_str)
        media_dict = parsed["media"][0]
        assert media_dict["notes"] == "This is a test note"

    def test_photo_date_round_trip_full_date(self) -> None:
        """Full photo_date dict round-trips correctly through serialize/deserialize."""
        item = MediaItem(
            id="m1", type="photo", file="img/test.jpg", title="Test",
            photo_date={"year": 1920, "month": 5, "day": 15},
        )
        data = ProjectData(media=[item])
        result = deserialize(serialize(data))
        assert result.media[0].photo_date == {"year": 1920, "month": 5, "day": 15}

    def test_photo_date_round_trip_year_only(self) -> None:
        """Year-only photo_date round-trips correctly (month and day are None)."""
        item = MediaItem(
            id="m1", type="photo", file="img/test.jpg", title="Test",
            photo_date={"year": 1850, "month": None, "day": None},
        )
        data = ProjectData(media=[item])
        result = deserialize(serialize(data))
        assert result.media[0].photo_date == {"year": 1850, "month": None, "day": None}

    def test_photo_date_round_trip_year_month(self) -> None:
        """Year+month photo_date round-trips correctly (day is None)."""
        item = MediaItem(
            id="m1", type="photo", file="img/test.jpg", title="Test",
            photo_date={"year": 1920, "month": 3, "day": None},
        )
        data = ProjectData(media=[item])
        result = deserialize(serialize(data))
        assert result.media[0].photo_date == {"year": 1920, "month": 3, "day": None}

    def test_photo_date_none_round_trip(self) -> None:
        """None photo_date round-trips correctly (gets default None)."""
        item = MediaItem(id="m1", type="photo", file="img/test.jpg", title="Test")
        data = ProjectData(media=[item])
        result = deserialize(serialize(data))
        assert result.media[0].photo_date is None

    def test_notes_round_trip(self) -> None:
        """Notes content round-trips correctly through serialize/deserialize."""
        item = MediaItem(
            id="m1", type="photo", file="img/test.jpg", title="Test",
            notes="Foto taget vid Ljusdals kyrka",
        )
        data = ProjectData(media=[item])
        result = deserialize(serialize(data))
        assert result.media[0].notes == "Foto taget vid Ljusdals kyrka"

    def test_notes_empty_round_trip(self) -> None:
        """Empty notes round-trips correctly (gets default empty string)."""
        item = MediaItem(id="m1", type="photo", file="img/test.jpg", title="Test")
        data = ProjectData(media=[item])
        result = deserialize(serialize(data))
        assert result.media[0].notes == ""

    def test_old_json_without_new_fields_gets_defaults(self) -> None:
        """Old JSON files without photo_date/notes deserialize with correct defaults."""
        old_json = json.dumps({
            "format": "slaktbuske-file",
            "version": "0.1",
            "project": {"title": "Old Project"},
            "media": [
                {"id": "m1", "type": "photo", "file": "old.jpg", "title": "Old Photo"}
            ],
        })
        result = deserialize(old_json)
        m = result.media[0]
        assert m.photo_date is None
        assert m.notes == ""
