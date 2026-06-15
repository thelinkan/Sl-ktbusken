"""Unit tests for slaktbusken.gedcom.translation.matcher module.

Tests cover the core matching utilities: normalization, exact matching,
fuzzy matching, name matching with Swedish equivalents, place string
matching, and composite key similarity scoring.
"""

from __future__ import annotations

import pytest

from slaktbusken.gedcom.translation.matcher import (
    composite_key_similarity,
    compute_similarity,
    exact_match,
    fuzzy_match,
    match_name,
    match_place_string,
    normalize_string,
)


# ---------------------------------------------------------------------------
# normalize_string tests
# ---------------------------------------------------------------------------


class TestNormalizeString:
    """Tests for the normalize_string function."""

    def test_strips_whitespace(self) -> None:
        assert normalize_string("  hello  ") == "hello"

    def test_lowercases(self) -> None:
        assert normalize_string("HELLO") == "hello"

    def test_collapses_multiple_spaces(self) -> None:
        assert normalize_string("carl   gustaf") == "carl gustaf"

    def test_preserves_swedish_characters(self) -> None:
        assert normalize_string("Gävleborgs län") == "gävleborgs län"
        assert normalize_string("Malmö") == "malmö"
        assert normalize_string("Åkerström") == "åkerström"

    def test_empty_string(self) -> None:
        assert normalize_string("") == ""

    def test_whitespace_only(self) -> None:
        assert normalize_string("   ") == ""

    def test_tabs_and_newlines(self) -> None:
        assert normalize_string("hello\t\nworld") == "hello world"


# ---------------------------------------------------------------------------
# exact_match tests
# ---------------------------------------------------------------------------


class TestExactMatch:
    """Tests for the exact_match function."""

    def test_case_insensitive_match(self) -> None:
        result = exact_match("Ljusdal", ["ljusdal", "Stockholm", "Göteborg"])
        assert result == "ljusdal"

    def test_whitespace_normalized_match(self) -> None:
        result = exact_match("  Carl  ", ["Carl", "Karl", "Erik"])
        assert result == "Carl"

    def test_no_match_returns_none(self) -> None:
        result = exact_match("Unknown", ["Carl", "Karl", "Erik"])
        assert result is None

    def test_empty_value_returns_none(self) -> None:
        result = exact_match("", ["Carl", "Karl"])
        assert result is None

    def test_empty_candidates_returns_none(self) -> None:
        result = exact_match("Carl", [])
        assert result is None

    def test_returns_original_candidate(self) -> None:
        result = exact_match("STOCKHOLM", ["Stockholm", "Göteborg"])
        assert result == "Stockholm"

    def test_swedish_characters(self) -> None:
        result = exact_match("GÄVLEBORGS LÄN", ["Gävleborgs län", "Uppsala län"])
        assert result == "Gävleborgs län"


# ---------------------------------------------------------------------------
# compute_similarity tests
# ---------------------------------------------------------------------------


class TestComputeSimilarity:
    """Tests for the compute_similarity function."""

    def test_identical_strings_return_1(self) -> None:
        assert compute_similarity("Ljusdal", "Ljusdal") == 1.0

    def test_case_insensitive_identical_return_1(self) -> None:
        assert compute_similarity("LJUSDAL", "ljusdal") == 1.0

    def test_empty_vs_nonempty_returns_0(self) -> None:
        assert compute_similarity("", "something") == 0.0

    def test_both_empty_returns_1(self) -> None:
        assert compute_similarity("", "") == 1.0

    def test_similar_strings_above_zero(self) -> None:
        score = compute_similarity("Ljusdal", "Ljusdals")
        assert 0.0 < score < 1.0

    def test_completely_different_strings(self) -> None:
        score = compute_similarity("abc", "xyz")
        assert score < 0.5

    def test_result_in_valid_range(self) -> None:
        score = compute_similarity("Carl", "Karl")
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# fuzzy_match tests
# ---------------------------------------------------------------------------


class TestFuzzyMatch:
    """Tests for the fuzzy_match function."""

    def test_exact_match_included(self) -> None:
        results = fuzzy_match("Ljusdal", ["Ljusdal", "Stockholm"])
        assert len(results) >= 1
        assert results[0] == ("Ljusdal", 1.0)

    def test_similar_candidates_above_threshold(self) -> None:
        results = fuzzy_match("Ljusdal", ["Ljusdals", "Stockholm"], threshold=0.8)
        # "Ljusdals" should be close to "Ljusdal"
        ljusdals_matches = [r for r in results if r[0] == "Ljusdals"]
        assert len(ljusdals_matches) == 1
        assert ljusdals_matches[0][1] >= 0.8

    def test_below_threshold_excluded(self) -> None:
        results = fuzzy_match("Ljusdal", ["Stockholm"], threshold=0.8)
        assert len(results) == 0

    def test_sorted_by_score_descending(self) -> None:
        results = fuzzy_match("Ljusdal", ["Ljusdal", "Ljusdals", "Ljusda"], threshold=0.7)
        scores = [score for _, score in results]
        assert scores == sorted(scores, reverse=True)

    def test_empty_value_returns_empty(self) -> None:
        results = fuzzy_match("", ["Ljusdal", "Stockholm"])
        assert results == []

    def test_empty_candidates_returns_empty(self) -> None:
        results = fuzzy_match("Ljusdal", [])
        assert results == []

    def test_custom_threshold(self) -> None:
        # With very low threshold, more candidates should match
        results_low = fuzzy_match("abc", ["abd", "xyz", "abcdef"], threshold=0.3)
        results_high = fuzzy_match("abc", ["abd", "xyz", "abcdef"], threshold=0.9)
        assert len(results_low) >= len(results_high)


# ---------------------------------------------------------------------------
# match_name tests
# ---------------------------------------------------------------------------


class TestMatchName:
    """Tests for the match_name function."""

    def test_exact_name_match(self) -> None:
        results = match_name(
            "Carl", "Andersson",
            ["Carl", "Erik"], ["Andersson", "Svensson"],
        )
        assert results[0][0] == 0  # First candidate is best match
        assert results[0][1] == 1.0  # Perfect score

    def test_swedish_equivalent_match(self) -> None:
        results = match_name(
            "Carl", "Andersson",
            ["Karl", "Erik"], ["Andersson", "Svensson"],
        )
        # "Carl"/"Karl" are equivalents → should get high score
        assert results[0][0] == 0
        assert results[0][1] > 0.9

    def test_different_surname_lower_score(self) -> None:
        results = match_name(
            "Carl", "Andersson",
            ["Carl"], ["Svensson"],
        )
        # Given name matches but surname doesn't → partial score
        assert results[0][1] < 1.0

    def test_mismatched_lengths_raises(self) -> None:
        with pytest.raises(ValueError):
            match_name("Carl", "Andersson", ["Carl", "Erik"], ["Andersson"])

    def test_empty_candidates(self) -> None:
        results = match_name("Carl", "Andersson", [], [])
        assert results == []

    def test_sorted_by_score_descending(self) -> None:
        results = match_name(
            "Carl", "Andersson",
            ["Karl", "Erik", "Carl"], ["Andersson", "Andersson", "Andersson"],
        )
        scores = [score for _, score in results]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# match_place_string tests
# ---------------------------------------------------------------------------


class TestMatchPlaceString:
    """Tests for the match_place_string function."""

    def test_exact_most_specific_match(self) -> None:
        results = match_place_string(
            "Ljusdal, Gävleborgs län, Sverige",
            ["Ljusdal", "Stockholm", "Malmö"],
        )
        assert results[0][0] == 0  # "Ljusdal" is best match
        assert results[0][1] == 1.0

    def test_full_string_match(self) -> None:
        results = match_place_string(
            "Ljusdal, Gävleborgs län, Sverige",
            ["Ljusdal, Gävleborgs län, Sverige", "Stockholm"],
        )
        assert results[0][0] == 0
        assert results[0][1] == 1.0

    def test_empty_gedcom_place(self) -> None:
        results = match_place_string("", ["Ljusdal", "Stockholm"])
        assert results == []

    def test_sorted_by_score_descending(self) -> None:
        results = match_place_string(
            "Ljusdal, Gävleborgs län, Sverige",
            ["Ljusdal", "Ljusdals", "Stockholm"],
        )
        scores = [score for _, score in results]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# composite_key_similarity tests
# ---------------------------------------------------------------------------


class TestCompositeKeySimilarity:
    """Tests for the composite_key_similarity function."""

    def test_identical_keys_return_1(self) -> None:
        key = ("Carl", "Andersson", "1850-03-15", "Ljusdal")
        assert composite_key_similarity(key, key) == 1.0

    def test_both_none_dates_and_places_count_as_match(self) -> None:
        key_a = ("Anna", "Svensson", None, None)
        key_b = ("Anna", "Svensson", None, None)
        assert composite_key_similarity(key_a, key_b) == 1.0

    def test_one_none_date_reduces_score(self) -> None:
        key_a = ("Anna", "Svensson", "1850-03-15", None)
        key_b = ("Anna", "Svensson", None, None)
        score = composite_key_similarity(key_a, key_b)
        # Should be less than 1.0 since birth_date mismatch (one None)
        assert score < 1.0
        # But still high since names match and birth_place both None
        assert score > 0.7

    def test_swedish_name_equivalents_boost_score(self) -> None:
        key_a = ("Carl", "Andersson", "1850-03-15", "Ljusdal")
        key_b = ("Karl", "Andersson", "1850-03-15", "Ljusdal")
        score = composite_key_similarity(key_a, key_b)
        # Carl/Karl are equivalents → should be very high
        assert score >= 0.95

    def test_completely_different_keys(self) -> None:
        key_a = ("Anna", "Svensson", "1900-01-01", "Malmö")
        key_b = ("Erik", "Johansson", "1850-06-20", "Luleå")
        score = composite_key_similarity(key_a, key_b)
        assert score < 0.5

    def test_surname_weighted_higher_than_given(self) -> None:
        # Use completely different names to isolate the weighting effect.
        # same given + completely different surname vs
        # completely different given + same surname
        key_base = ("Carl", "Andersson", "1850", "Ljusdal")
        key_diff_surname = ("Carl", "Borg", "1850", "Ljusdal")
        key_diff_given = ("Nils", "Andersson", "1850", "Ljusdal")

        score_diff_surname = composite_key_similarity(key_base, key_diff_surname)
        score_diff_given = composite_key_similarity(key_base, key_diff_given)

        # Different surname should hurt more than different given name
        # because surname weight (0.35) > given name weight (0.30)
        assert score_diff_given > score_diff_surname

    def test_result_in_valid_range(self) -> None:
        key_a = ("Carl", "Andersson", "1850", "Ljusdal")
        key_b = ("Karl", "Svensson", None, "Malmö")
        score = composite_key_similarity(key_a, key_b)
        assert 0.0 <= score <= 1.0
