"""Property-based tests for multi-line reference parsing.

Feature: source-management, Property 14: Multi-line reference parsing creates separate sources

Validates: Requirements 8.4
"""

from __future__ import annotations

import random

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from slaktbusken.parsing.reference_parser import (
    ParsedReference,
    parse_multi_line,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid SDB line: "SDB{single_digit}_{one_or_more_digits}"
valid_sdb_line = st.tuples(
    st.integers(0, 9), st.integers(1, 99999)
).map(lambda t: f"SDB{t[0]}_{t[1]}")

# Valid Sveriges dödbok webb line: "Sveriges dödbok webb - {id}"
valid_dodbok_line = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
    min_size=1,
    max_size=20,
).map(lambda s: f"Sveriges dödbok webb - {s}")

# Combined valid line: either SDB or dodbok format
valid_line = st.one_of(valid_sdb_line, valid_dodbok_line)

# Invalid line: text that doesn't match any known pattern
invalid_line = (
    st.text(min_size=1, max_size=50)
    .filter(
        lambda s: "SDB" not in s.upper()
        and "sveriges dödbok" not in s.lower()
        and not s.strip().startswith("r")
        and "AID:" not in s.upper()
        and "\n" not in s
        and "\r" not in s
    )
)


# ---------------------------------------------------------------------------
# Property 14: Multi-line reference parsing creates separate sources
# ---------------------------------------------------------------------------


class TestMultiLineParsingProperty:
    """Property 14: Multi-line reference parsing creates separate sources.

    **Validates: Requirements 8.4**

    For any multi-line text where M lines contain a valid Sveriges Dödbok
    reference and K lines do not, the parser SHALL produce exactly M
    ParsedReference results, one per valid line.
    """

    @given(valid_lines=st.lists(valid_line, min_size=1, max_size=10))
    @settings(max_examples=100, deadline=None)
    def test_valid_lines_produce_one_result_each(
        self, valid_lines: list[str]
    ) -> None:
        """N valid SDB/dodbok lines produce exactly N parsed results."""
        text = "\n".join(valid_lines)
        results = parse_multi_line(text)
        assert len(results) == len(valid_lines), (
            f"Expected {len(valid_lines)} results but got {len(results)} "
            f"for input: {text!r}"
        )

    @given(invalid_lines=st.lists(invalid_line, min_size=1, max_size=10))
    @settings(max_examples=100, deadline=None)
    def test_invalid_lines_produce_no_results(
        self, invalid_lines: list[str]
    ) -> None:
        """N invalid lines produce zero parsed results."""
        text = "\n".join(invalid_lines)
        results = parse_multi_line(text)
        assert len(results) == 0, (
            f"Expected 0 results but got {len(results)} "
            f"for input: {text!r}"
        )

    @given(
        valid_lines=st.lists(valid_line, min_size=1, max_size=5),
        invalid_lines=st.lists(invalid_line, min_size=1, max_size=5),
        data=st.data(),
    )
    @settings(max_examples=100, deadline=None)
    def test_mixed_valid_and_invalid_lines(
        self,
        valid_lines: list[str],
        invalid_lines: list[str],
        data: st.DataObject,
    ) -> None:
        """M valid lines and K invalid lines produce exactly M results."""
        # Combine and shuffle
        all_lines = valid_lines + invalid_lines
        shuffled = data.draw(st.permutations(all_lines))

        text = "\n".join(shuffled)
        results = parse_multi_line(text)
        assert len(results) == len(valid_lines), (
            f"Expected {len(valid_lines)} results but got {len(results)} "
            f"for input with {len(valid_lines)} valid and "
            f"{len(invalid_lines)} invalid lines"
        )

    @given(valid_lines=st.lists(valid_line, min_size=1, max_size=10))
    @settings(max_examples=100, deadline=None)
    def test_each_result_corresponds_to_one_line(
        self, valid_lines: list[str]
    ) -> None:
        """Each ParsedReference has reference_text matching one valid input line."""
        text = "\n".join(valid_lines)
        results = parse_multi_line(text)

        # Each result's reference_text should be one of the valid input lines
        for result in results:
            assert result.reference_text in valid_lines, (
                f"Result reference_text {result.reference_text!r} "
                f"not found in valid input lines"
            )

        # Each valid line should have exactly one corresponding result
        result_texts = [r.reference_text for r in results]
        for line in valid_lines:
            assert line in result_texts, (
                f"Valid line {line!r} has no corresponding result"
            )
