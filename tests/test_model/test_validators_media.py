"""Property-based tests for MediaItem validation (redigera-person-media spec).

Tests for annotation count validation and title length validation properties
from the design document.
"""

from __future__ import annotations

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from slaktbusken.model.media import MediaItem
from slaktbusken.model.validators import validate_media_item
from tests.conftest import annotation_strategy


# ===========================================================================
# Property 18: Title length validation
# **Validates: Requirements 9.7**
#
# For any string, title validation SHALL pass if and only if the string
# length is between 1 and 200 characters inclusive.
# ===========================================================================


class TestPropertyTitleLengthValidation:
    """Feature: redigera-person-media, Property 18: Title length validation"""

    @given(
        title=st.text(
            alphabet=st.characters(categories=("L", "N", "P", "Z")),
            min_size=1,
            max_size=200,
        )
    )
    @settings(max_examples=100)
    def test_valid_title_length_passes(self, title: str) -> None:
        """Feature: redigera-person-media, Property 18: Title length validation

        **Validates: Requirements 9.7**
        """
        media_item = MediaItem(
            id="media_1",
            type="photo",
            file="images/test.jpg",
            title=title,
        )
        errors = validate_media_item(media_item)
        title_error = "Mediatitel måste vara 1–200 tecken."
        assert title_error not in errors, (
            f"Valid title of length {len(title)} was rejected"
        )

    def test_empty_title_fails(self) -> None:
        """Feature: redigera-person-media, Property 18: Title length validation

        **Validates: Requirements 9.7**
        """
        media_item = MediaItem(
            id="media_1",
            type="photo",
            file="images/test.jpg",
            title="",
        )
        errors = validate_media_item(media_item)
        title_error = "Mediatitel måste vara 1–200 tecken."
        assert title_error in errors, (
            f"Empty title was not rejected. Errors: {errors}"
        )

    @given(
        title=st.text(
            alphabet=st.characters(categories=("L", "N", "P", "Z")),
            min_size=201,
            max_size=500,
        )
    )
    @settings(max_examples=100)
    def test_too_long_title_fails(self, title: str) -> None:
        """Feature: redigera-person-media, Property 18: Title length validation

        **Validates: Requirements 9.7**
        """
        media_item = MediaItem(
            id="media_1",
            type="photo",
            file="images/test.jpg",
            title=title,
        )
        errors = validate_media_item(media_item)
        title_error = "Mediatitel måste vara 1–200 tecken."
        assert title_error in errors, (
            f"Title of length {len(title)} was not rejected. Errors: {errors}"
        )


# ===========================================================================
# Property 15: Annotation count validation
# **Validates: Requirements 6.5**
#
# For any MediaItem, validation SHALL pass when annotations contains 0 to 100
# records and SHALL fail when it exceeds 100.
# ===========================================================================


class TestPropertyAnnotationCountValidation:
    """Feature: redigera-person-media, Property 15: Annotation count validation"""

    @given(
        annotation_count=st.integers(min_value=0, max_value=100),
        data=st.data(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_valid_annotation_count_passes(
        self, annotation_count: int, data: st.DataObject
    ) -> None:
        """Feature: redigera-person-media, Property 15: Annotation count validation

        **Validates: Requirements 6.5**
        """
        annotations = data.draw(
            st.lists(annotation_strategy(), min_size=annotation_count, max_size=annotation_count)
        )
        media_item = MediaItem(
            id="media_1",
            type="photo",
            file="images/test.jpg",
            title="Test",
            annotations=annotations,
        )
        errors = validate_media_item(media_item)
        assert "MediaItem får ha max 100 annoteringar." not in errors

    @given(
        annotation_count=st.integers(min_value=101, max_value=150),
        data=st.data(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_exceeding_annotation_count_fails(
        self, annotation_count: int, data: st.DataObject
    ) -> None:
        """Feature: redigera-person-media, Property 15: Annotation count validation

        **Validates: Requirements 6.5**
        """
        annotations = data.draw(
            st.lists(annotation_strategy(), min_size=annotation_count, max_size=annotation_count)
        )
        media_item = MediaItem(
            id="media_1",
            type="photo",
            file="images/test.jpg",
            title="Test",
            annotations=annotations,
        )
        errors = validate_media_item(media_item)
        assert "MediaItem får ha max 100 annoteringar." in errors
