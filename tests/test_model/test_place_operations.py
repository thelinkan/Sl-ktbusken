"""Unit tests for External ID helper operations on Place.

Tests add_external_id, remove_external_id, and edit_external_id functions.
"""

from __future__ import annotations

from slaktbusken.model.place import (
    ExternalId,
    Place,
    add_external_id,
    edit_external_id,
    remove_external_id,
)


def _make_place(**kwargs) -> Place:
    """Create a minimal Place for testing."""
    defaults = {"id": "p1", "type": "parish", "name": "Test", "parent_place_id": "c1"}
    defaults.update(kwargs)
    return Place(**defaults)


# ---------------------------------------------------------------------------
# add_external_id
# ---------------------------------------------------------------------------


class TestAddExternalId:
    """Tests for add_external_id."""

    def test_add_valid_entry(self) -> None:
        place = _make_place()
        ext_id = ExternalId(key="_PARISH_AID", value="12345")
        errors = add_external_id(place, ext_id)
        assert errors == []
        assert len(place.external_ids) == 1
        assert place.external_ids[0].key == "_PARISH_AID"
        assert place.external_ids[0].value == "12345"

    def test_add_duplicate_key_rejected(self) -> None:
        place = _make_place(external_ids=[ExternalId(key="AID", value="111")])
        ext_id = ExternalId(key="AID", value="222")
        errors = add_external_id(place, ext_id)
        assert len(errors) == 1
        assert "AID" in errors[0]
        # Original entry unchanged
        assert len(place.external_ids) == 1
        assert place.external_ids[0].value == "111"

    def test_add_whitespace_only_key_rejected(self) -> None:
        place = _make_place()
        ext_id = ExternalId(key="   ", value="val")
        errors = add_external_id(place, ext_id)
        assert len(errors) > 0
        assert "Nyckel krävs." in errors
        assert len(place.external_ids) == 0

    def test_add_empty_key_rejected(self) -> None:
        place = _make_place()
        ext_id = ExternalId(key="", value="val")
        errors = add_external_id(place, ext_id)
        assert "Nyckel krävs." in errors
        assert len(place.external_ids) == 0

    def test_add_whitespace_only_value_rejected(self) -> None:
        place = _make_place()
        ext_id = ExternalId(key="key", value="  \t  ")
        errors = add_external_id(place, ext_id)
        assert "Värde krävs." in errors
        assert len(place.external_ids) == 0

    def test_add_key_too_long_rejected(self) -> None:
        place = _make_place()
        ext_id = ExternalId(key="k" * 101, value="val")
        errors = add_external_id(place, ext_id)
        assert "Nyckeln får vara högst 100 tecken." in errors
        assert len(place.external_ids) == 0

    def test_add_value_too_long_rejected(self) -> None:
        place = _make_place()
        ext_id = ExternalId(key="key", value="v" * 501)
        errors = add_external_id(place, ext_id)
        assert "Värdet får vara högst 500 tecken." in errors
        assert len(place.external_ids) == 0

    def test_add_multiple_distinct_keys(self) -> None:
        place = _make_place()
        add_external_id(place, ExternalId(key="A", value="1"))
        add_external_id(place, ExternalId(key="B", value="2"))
        assert len(place.external_ids) == 2

    def test_add_preserves_case(self) -> None:
        place = _make_place()
        ext_id = ExternalId(key="MyKey", value="MyValue")
        add_external_id(place, ext_id)
        assert place.external_ids[0].key == "MyKey"
        assert place.external_ids[0].value == "MyValue"


# ---------------------------------------------------------------------------
# remove_external_id
# ---------------------------------------------------------------------------


class TestRemoveExternalId:
    """Tests for remove_external_id."""

    def test_remove_existing_entry(self) -> None:
        place = _make_place(
            external_ids=[
                ExternalId(key="A", value="1"),
                ExternalId(key="B", value="2"),
            ]
        )
        remove_external_id(place, "A")
        assert len(place.external_ids) == 1
        assert place.external_ids[0].key == "B"

    def test_remove_nonexistent_key_no_change(self) -> None:
        place = _make_place(external_ids=[ExternalId(key="A", value="1")])
        remove_external_id(place, "Z")
        assert len(place.external_ids) == 1

    def test_remove_last_entry(self) -> None:
        place = _make_place(external_ids=[ExternalId(key="X", value="9")])
        remove_external_id(place, "X")
        assert place.external_ids == []

    def test_remove_preserves_order_of_remaining(self) -> None:
        place = _make_place(
            external_ids=[
                ExternalId(key="A", value="1"),
                ExternalId(key="B", value="2"),
                ExternalId(key="C", value="3"),
            ]
        )
        remove_external_id(place, "B")
        assert [e.key for e in place.external_ids] == ["A", "C"]


# ---------------------------------------------------------------------------
# edit_external_id
# ---------------------------------------------------------------------------


class TestEditExternalId:
    """Tests for edit_external_id."""

    def test_edit_value_only(self) -> None:
        place = _make_place(external_ids=[ExternalId(key="K", value="old")])
        errors = edit_external_id(place, "K", ExternalId(key="K", value="new"))
        assert errors == []
        assert place.external_ids[0].value == "new"

    def test_edit_key_and_value(self) -> None:
        place = _make_place(external_ids=[ExternalId(key="OLD", value="1")])
        errors = edit_external_id(place, "OLD", ExternalId(key="NEW", value="2"))
        assert errors == []
        assert place.external_ids[0].key == "NEW"
        assert place.external_ids[0].value == "2"

    def test_edit_duplicate_key_rejected(self) -> None:
        place = _make_place(
            external_ids=[
                ExternalId(key="A", value="1"),
                ExternalId(key="B", value="2"),
            ]
        )
        # Try to rename B to A — should fail
        errors = edit_external_id(place, "B", ExternalId(key="A", value="99"))
        assert len(errors) == 1
        assert "A" in errors[0]
        # Original entries unchanged
        assert place.external_ids[0].key == "A"
        assert place.external_ids[1].key == "B"
        assert place.external_ids[1].value == "2"

    def test_edit_same_key_no_conflict(self) -> None:
        """Editing an entry to keep the same key should not trigger duplicate error."""
        place = _make_place(external_ids=[ExternalId(key="K", value="old")])
        errors = edit_external_id(place, "K", ExternalId(key="K", value="updated"))
        assert errors == []
        assert place.external_ids[0].value == "updated"

    def test_edit_whitespace_key_rejected(self) -> None:
        place = _make_place(external_ids=[ExternalId(key="K", value="v")])
        errors = edit_external_id(place, "K", ExternalId(key="  ", value="v"))
        assert "Nyckel krävs." in errors
        # Original unchanged
        assert place.external_ids[0].key == "K"

    def test_edit_whitespace_value_rejected(self) -> None:
        place = _make_place(external_ids=[ExternalId(key="K", value="v")])
        errors = edit_external_id(place, "K", ExternalId(key="K", value="  "))
        assert "Värde krävs." in errors
        assert place.external_ids[0].value == "v"

    def test_edit_nonexistent_old_key(self) -> None:
        """Editing a key that doesn't exist returns empty errors (no-op)."""
        place = _make_place(external_ids=[ExternalId(key="A", value="1")])
        errors = edit_external_id(place, "MISSING", ExternalId(key="NEW", value="2"))
        assert errors == []
        # Place unchanged
        assert len(place.external_ids) == 1
        assert place.external_ids[0].key == "A"

    def test_edit_preserves_position(self) -> None:
        """Edited entry stays at the same index."""
        place = _make_place(
            external_ids=[
                ExternalId(key="A", value="1"),
                ExternalId(key="B", value="2"),
                ExternalId(key="C", value="3"),
            ]
        )
        edit_external_id(place, "B", ExternalId(key="B2", value="22"))
        assert [e.key for e in place.external_ids] == ["A", "B2", "C"]
