"""Property-based tests for non-matching reference strings.

Feature: source-management, Property 11: Non-matching strings produce no source

Validates: Requirements 7.5, 8.5
"""

from __future__ import annotations

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from slaktbusken.parsing.reference_parser import parse_reference


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate text that cannot match any known pattern.
# Excludes characters and patterns that would trigger any parser.
nonmatch_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Zs"),
        blacklist_characters="()",  # avoid parens that could form AID patterns
    ),
    min_size=0,
    max_size=200,
).filter(
    lambda s: (
        "AID:" not in s.upper()
        and "SDB" not in s.upper()
        and "sveriges dödbok" not in s.lower()
        and not (s.strip().startswith("r") and ".p" in s)  # avoid census-like
    )
)

# Strategy for whitespace-only strings
whitespace_strategy = st.text(
    alphabet=" \t\n\r",
    min_size=1,
    max_size=50,
)

# Strategy for random common words without pattern keywords
safe_words = st.sampled_from([
    "hello", "world", "test", "data", "name", "value", "foo", "bar",
    "Stockholm", "Göteborg", "Malmö", "person", "event", "date",
    "family", "tree", "record", "note", "document", "archive",
])

random_sentence_strategy = st.lists(safe_words, min_size=1, max_size=10).map(
    lambda words: " ".join(words)
)

# Strategy for partial patterns that are close but don't match
partial_pattern_strategy = st.sampled_from([
    "AID without colon",
    "AID 12345",
    "something AID something",
    "SDB without digits",
    "SDB_123",  # missing version digit before underscore
    "SDB",
    "r123",  # missing .p part
    ".p456",  # missing r prefix
    "r.p",  # missing digits
    "Sveriges",  # partial match, not full phrase
    "dödbok",  # partial match, not full phrase
    "Bild 5 / sid 10",  # missing AID
])


# ---------------------------------------------------------------------------
# Property 11: Non-matching strings produce no source
# ---------------------------------------------------------------------------


class TestNonMatchingStringsProperty:
    """Property 11: Non-matching strings produce no source.

    **Validates: Requirements 7.5, 8.5**

    For any string that does not match any defined Arkiv Digital or Rötter.se
    reference pattern, the parse_reference function SHALL return None
    (no source created).
    """

    @given(text=nonmatch_strategy)
    @settings(max_examples=100, deadline=None)
    def test_nonmatching_strings_return_none(self, text: str) -> None:
        """Non-matching generated strings return None from parse_reference."""
        result = parse_reference(text)
        assert result is None, (
            f"Expected None for non-matching string, got {result!r} "
            f"for input: {text!r}"
        )

    def test_empty_string_returns_none(self) -> None:
        """Empty string returns None from parse_reference."""
        result = parse_reference("")
        assert result is None, "Expected None for empty string"

    @given(text=whitespace_strategy)
    @settings(max_examples=100, deadline=None)
    def test_whitespace_only_returns_none(self, text: str) -> None:
        """Whitespace-only strings return None from parse_reference."""
        result = parse_reference(text)
        assert result is None, (
            f"Expected None for whitespace-only string, got {result!r} "
            f"for input: {text!r}"
        )

    @given(text=random_sentence_strategy)
    @settings(max_examples=100, deadline=None)
    def test_random_words_return_none(self, text: str) -> None:
        """Random common words/sentences without pattern keywords return None."""
        result = parse_reference(text)
        assert result is None, (
            f"Expected None for random sentence, got {result!r} "
            f"for input: {text!r}"
        )

    @given(text=partial_pattern_strategy)
    @settings(max_examples=100, deadline=None)
    def test_partial_patterns_return_none(self, text: str) -> None:
        """Strings close to patterns but not matching return None."""
        result = parse_reference(text)
        assert result is None, (
            f"Expected None for partial pattern, got {result!r} "
            f"for input: {text!r}"
        )
