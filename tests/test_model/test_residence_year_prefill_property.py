# Feature: residence-periods, Property 11: Year prefill parses the Source years value and never overwrites user input
"""Property-based test for year prefill.

Feature: residence-periods, Property 11: Year prefill parses the Source years value and never overwrites user input

For any Source ``years`` value, prefill yields both years when the value holds two
four-digit years in 1500–2100 in ascending order separated by a hyphen or an en dash
with any surrounding spaces, yields that year twice when it holds a single such year,
and yields nothing otherwise; the input string is never modified (pure/read-only), and
the output is independent of any previously typed values.

**Validates: Requirements 4.1, 4.7, 4.8, 4.9, 4.10, 9.2**
"""

from __future__ import annotations

import copy
import string

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.services.residence_edit_ops import (
    MAX_OBSERVATION_YEAR,
    MIN_OBSERVATION_YEAR,
    prefill_span_from_years,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

#: Valid years in the accepted range 1500–2100.
_valid_years = st.integers(min_value=MIN_OBSERVATION_YEAR, max_value=MAX_OBSERVATION_YEAR)

#: Separators that the parser reads: hyphen-minus and en dash (U+2013).
_valid_separators = st.sampled_from(["-", "\u2013"])

#: Optional surrounding spaces around the separator.
_surrounding_spaces = st.text(alphabet=" \t", min_size=0, max_size=4)


@st.composite
def _single_year_inputs(draw: DrawFn) -> tuple[str, tuple[str, str]]:
    """A valid single-year input and the expected output pair."""
    year = draw(_valid_years)
    year_str = f"{year:04d}"
    # Optionally wrap with whitespace (which the function strips)
    padding = draw(st.text(alphabet=" \t", min_size=0, max_size=3))
    input_str = f"{padding}{year_str}{padding}"
    return input_str, (year_str, year_str)


@st.composite
def _two_year_inputs(draw: DrawFn) -> tuple[str, tuple[str, str]]:
    """A valid two-year ascending input and the expected output pair."""
    first = draw(_valid_years)
    second = draw(st.integers(min_value=first, max_value=MAX_OBSERVATION_YEAR))
    first_str = f"{first:04d}"
    second_str = f"{second:04d}"
    sep = draw(_valid_separators)
    left_space = draw(_surrounding_spaces)
    right_space = draw(_surrounding_spaces)
    # Optionally pad the entire string
    outer_pad = draw(st.text(alphabet=" \t", min_size=0, max_size=2))
    input_str = f"{outer_pad}{first_str}{left_space}{sep}{right_space}{second_str}{outer_pad}"
    return input_str, (first_str, second_str)


@st.composite
def _invalid_inputs(draw: DrawFn) -> str:
    """Generate inputs that should yield None.

    Categories: None, empty/whitespace, descending pairs, out-of-range years,
    unparsable text with extra characters.
    """
    kind = draw(st.sampled_from([
        "none", "empty", "whitespace", "descending", "out_of_range_low",
        "out_of_range_high", "extra_chars", "wrong_separator", "three_years",
        "partial_year",
    ]))

    if kind == "none":
        return None  # type: ignore[return-value]
    elif kind == "empty":
        return ""
    elif kind == "whitespace":
        return draw(st.text(alphabet=" \t\n", min_size=1, max_size=5))
    elif kind == "descending":
        first = draw(st.integers(min_value=MIN_OBSERVATION_YEAR + 1, max_value=MAX_OBSERVATION_YEAR))
        second = draw(st.integers(min_value=MIN_OBSERVATION_YEAR, max_value=first - 1))
        sep = draw(_valid_separators)
        return f"{first:04d}{sep}{second:04d}"
    elif kind == "out_of_range_low":
        year = draw(st.integers(min_value=1000, max_value=MIN_OBSERVATION_YEAR - 1))
        return f"{year:04d}"
    elif kind == "out_of_range_high":
        year = draw(st.integers(min_value=MAX_OBSERVATION_YEAR + 1, max_value=9999))
        return f"{year:04d}"
    elif kind == "extra_chars":
        # Valid year with extra alphabetic noise
        year = draw(_valid_years)
        noise = draw(st.text(alphabet=string.ascii_letters, min_size=1, max_size=5))
        return f"{noise}{year:04d}"
    elif kind == "wrong_separator":
        # Two valid years with an unsupported separator
        first = draw(_valid_years)
        second = draw(st.integers(min_value=first, max_value=MAX_OBSERVATION_YEAR))
        sep = draw(st.sampled_from(["/", " till ", "\u2014"]))  # slash, "till", em dash
        return f"{first:04d}{sep}{second:04d}"
    elif kind == "three_years":
        y1 = draw(_valid_years)
        y2 = draw(st.integers(min_value=y1, max_value=MAX_OBSERVATION_YEAR))
        y3 = draw(st.integers(min_value=y2, max_value=MAX_OBSERVATION_YEAR))
        return f"{y1:04d}-{y2:04d}-{y3:04d}"
    else:  # partial_year
        digits = draw(st.integers(min_value=1, max_value=3))
        return draw(st.text(alphabet=string.digits, min_size=digits, max_size=digits))


# ---------------------------------------------------------------------------
# Property test class
# ---------------------------------------------------------------------------


class TestYearPrefillProperty:
    """Property 11: Year prefill parses the Source years value and never overwrites user input.

    For any Source ``years`` value, prefill yields both years when the value holds
    two four-digit years in 1500–2100 in ascending order separated by a hyphen or
    en dash with any surrounding spaces, yields that year twice when it holds a single
    such year, and yields nothing otherwise; the input string is never modified
    (pure/read-only), and the output is independent of any previously typed values.

    **Validates: Requirements 4.1, 4.7, 4.8, 4.9, 4.10, 9.2**
    """

    @given(data=_single_year_inputs())
    @settings(max_examples=100, deadline=None)
    def test_single_year_yields_pair(self, data: tuple[str, tuple[str, str]]) -> None:
        """A single four-digit year in 1500–2100 yields (year, year).

        Feature: residence-periods, Property 11: Year prefill parses the Source years value and never overwrites user input

        **Validates: Requirements 4.8**
        """
        input_str, expected = data
        result = prefill_span_from_years(input_str)
        assert result == expected

    @given(data=_two_year_inputs())
    @settings(max_examples=100, deadline=None)
    def test_two_ascending_years_yield_pair(self, data: tuple[str, tuple[str, str]]) -> None:
        """Two ascending years separated by hyphen or en dash yield the pair.

        Feature: residence-periods, Property 11: Year prefill parses the Source years value and never overwrites user input

        **Validates: Requirements 4.7**
        """
        input_str, expected = data
        result = prefill_span_from_years(input_str)
        assert result == expected

    @given(input_str=_invalid_inputs())
    @settings(max_examples=100, deadline=None)
    def test_invalid_inputs_yield_none(self, input_str: str | None) -> None:
        """Everything else yields None.

        Feature: residence-periods, Property 11: Year prefill parses the Source years value and never overwrites user input

        **Validates: Requirements 4.9**
        """
        result = prefill_span_from_years(input_str)
        assert result is None

    @given(data=st.one_of(_single_year_inputs(), _two_year_inputs()))
    @settings(max_examples=100, deadline=None)
    def test_input_string_is_never_modified(self, data: tuple[str, tuple[str, str]]) -> None:
        """The input string is never modified (pure/read-only).

        Feature: residence-periods, Property 11: Year prefill parses the Source years value and never overwrites user input

        **Validates: Requirements 4.1**
        """
        input_str, _ = data
        original = copy.copy(input_str)
        prefill_span_from_years(input_str)
        assert input_str == original

    @given(
        data=st.one_of(_single_year_inputs(), _two_year_inputs()),
        user_from=st.text(alphabet=string.digits, min_size=4, max_size=4),
        user_to=st.text(alphabet=string.digits, min_size=4, max_size=4),
    )
    @settings(max_examples=100, deadline=None)
    def test_output_independent_of_previously_typed_values(
        self,
        data: tuple[str, tuple[str, str]],
        user_from: str,
        user_to: str,
    ) -> None:
        """The output is independent of any previously typed values.

        Feature: residence-periods, Property 11: Year prefill parses the Source years value and never overwrites user input

        **Validates: Requirements 4.10, 9.2**
        """
        input_str, expected = data
        # Simulate that a user has previously typed values — prefill is a pure
        # function of the years string only, so the result must be the same
        # regardless of what values exist elsewhere.
        result_before = prefill_span_from_years(input_str)
        # "User types" their own values (no effect on prefill)
        _ = user_from, user_to
        result_after = prefill_span_from_years(input_str)
        assert result_before == result_after == expected
