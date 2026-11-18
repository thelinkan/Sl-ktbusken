# Feature: residence-periods, Property 22: role_in_household is stored trimmed and otherwise byte-exact
"""Property-based test for role storage.

Feature: residence-periods, Property 22: role_in_household is stored trimmed and otherwise byte-exact

`normalize_role_in_household` trims leading and trailing whitespace and preserves
every remaining character (internal whitespace, case, å/ä/ö) with no
capitalization, case folding, substitution or normalization; whitespace-only or
empty becomes empty; the result contains at most 100 code points.

**Validates: Requirements 10.1, 10.4, 10.5, 10.7**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.residence import normalize_role_in_household


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Characters that include Swedish letters, internal whitespace, mixed case,
# digits, and common punctuation — covering the interesting domain.
_SWEDISH_ALPHABET = st.characters(
    categories=("Ll", "Lu", "Nd", "Zs", "Pd"),
    include_characters="åäöÅÄÖ \t",
    max_codepoint=0x024F,
)

# Whitespace characters used for padding (leading/trailing).
_WHITESPACE = st.sampled_from([" ", "\t", "\n", "\r", "  ", "\t\t", " \t\n"])


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


class TestRoleStorage:
    """Property 22: role_in_household is stored trimmed and otherwise byte-exact.

    **Validates: Requirements 10.1, 10.4, 10.5, 10.7**
    """

    @given(
        raw=st.one_of(
            # Empty or whitespace-only values
            st.just(""),
            st.text(alphabet=st.sampled_from([" ", "\t", "\n", "\r"]), min_size=1, max_size=20),
            # Normal role text with optional leading/trailing whitespace
            st.builds(
                lambda prefix, core, suffix: prefix + core + suffix,
                prefix=st.one_of(st.just(""), _WHITESPACE),
                core=st.text(alphabet=_SWEDISH_ALPHABET, min_size=1, max_size=100),
                suffix=st.one_of(st.just(""), _WHITESPACE),
            ),
            # Roles with Swedish characters and mixed case
            st.builds(
                lambda prefix, core, suffix: prefix + core + suffix,
                prefix=st.one_of(st.just(""), _WHITESPACE),
                core=st.sampled_from([
                    "husbonde",
                    "Husbonde",
                    "HUSBONDE",
                    "piga",
                    "Piga",
                    "inhyses",
                    "dräng",
                    "Dräng",
                    "änka",
                    "Änka",
                    "ÄNKA",
                    "torpare  med  familj",
                    "hfl  anteckning",
                ]),
                suffix=st.one_of(st.just(""), _WHITESPACE),
            ),
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_role_normalized_is_trimmed_and_byte_exact(self, raw: str) -> None:
        """normalize_role_in_household trims whitespace, preserves internals exactly.

        Feature: residence-periods, Property 22: role_in_household is stored trimmed and otherwise byte-exact

        **Validates: Requirements 10.1, 10.4, 10.5, 10.7**
        """
        result = normalize_role_in_household(raw)

        # Expected: just strip leading/trailing whitespace.
        expected = raw.strip()

        # Requirement 10.4: stored with leading/trailing whitespace removed,
        # every remaining character exactly as typed.
        assert result == expected, (
            f"Expected byte-exact trimmed value.\n"
            f"  raw    = {raw!r}\n"
            f"  result = {result!r}\n"
            f"  expect = {expected!r}"
        )

        # Requirement 10.5: whitespace-only or empty becomes empty.
        if raw.strip() == "":
            assert result == ""

        # Requirement 10.4: no capitalization, case folding, substitution or
        # normalization applied — the result is identical to stripped input.
        assert result == raw.strip()

        # Requirement 10.1: at most 100 code points after trimming.
        # (The function accepts up to 100; the validator rejects >100.)
        # We verify the function does not silently truncate.
        assert len(result) == len(raw.strip())

        # No leading or trailing whitespace in result.
        if result:
            assert result[0] not in (" ", "\t", "\n", "\r")
            assert result[-1] not in (" ", "\t", "\n", "\r")

        # Internal whitespace is preserved exactly.
        if len(result) >= 3:
            inner = result[1:-1]
            expected_inner = raw.strip()[1:-1]
            assert inner == expected_inner

