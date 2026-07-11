"""Property-based tests for direct link generation correctness.

Feature: source-management, Property 17: Direct link generation correctness

Validates: Requirements 10.1, 10.3
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.source import Kalltyp, Source
from slaktbusken.services.source_links import generate_direct_link


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Non-empty strings for identifiers and URL parts
non_empty_text = st.text(min_size=1, max_size=50).filter(lambda s: s.strip() != "")

# Non-empty root URLs (typically ending with a path separator but not required)
non_empty_root_url = st.text(min_size=1, max_size=100).filter(lambda s: s.strip() != "")

# Non-empty arkivreferens values
non_empty_arkivreferens = st.text(min_size=1, max_size=100).filter(
    lambda s: s.strip() != ""
)

# Empty-ish strings (empty or whitespace-only)
empty_text = st.just("")


@st.composite
def source_strategy(draw: st.DrawFn, kalltyp_id: str = "", arkivreferens: str = "") -> Source:
    """Generate a Source with specified or random kalltyp_id and arkivreferens."""
    return Source(
        id=draw(non_empty_text),
        provider=draw(non_empty_text),
        source_type=draw(non_empty_text),
        title=draw(non_empty_text),
        kalltyp_id=kalltyp_id,
        arkivreferens=arkivreferens,
    )


@st.composite
def kalltyp_strategy(draw: st.DrawFn, kt_id: str = "", root_url: str = "") -> Kalltyp:
    """Generate a Kalltyp with specified or random id and root_url."""
    return Kalltyp(
        id=kt_id if kt_id else draw(non_empty_text),
        leverantor_id=draw(non_empty_text),
        name=draw(non_empty_text),
        root_url=root_url,
    )


# ---------------------------------------------------------------------------
# Property 17: Direct link generation correctness
# ---------------------------------------------------------------------------


class TestDirectLinkGenerationProperty:
    """Feature: source-management, Property 17: Direct link generation correctness

    For any source with a kalltyp_id pointing to a Källtyp with non-empty
    root_url, and a non-empty arkivreferens, the generated link SHALL equal
    root_url concatenated with arkivreferens. For any source missing one or
    more of these conditions (no kalltyp_id, empty root_url, or empty
    arkivreferens), no link SHALL be generated.

    **Validates: Requirements 10.1, 10.3**
    """

    @given(
        root_url=non_empty_root_url,
        arkivreferens=non_empty_arkivreferens,
        kt_id=non_empty_text,
        data=st.data(),
    )
    @settings(max_examples=100, deadline=None)
    def test_all_conditions_met_returns_concatenation(
        self, root_url: str, arkivreferens: str, kt_id: str, data: st.DataObject
    ) -> None:
        """When all conditions are met, result equals root_url + arkivreferens.

        Feature: source-management, Property 17: Direct link generation correctness
        **Validates: Requirements 10.1, 10.3**
        """
        source = data.draw(source_strategy(kalltyp_id=kt_id, arkivreferens=arkivreferens))
        kalltyp = data.draw(kalltyp_strategy(kt_id=kt_id, root_url=root_url))
        # May include other unrelated kalltyper
        other_kalltyper = data.draw(
            st.lists(kalltyp_strategy(root_url=root_url), max_size=3)
        )
        # Filter out any other kalltyp that accidentally has the same id
        other_kalltyper = [kt for kt in other_kalltyper if kt.id != kt_id]
        kalltyper = other_kalltyper + [kalltyp]

        result = generate_direct_link(source, kalltyper)
        assert result == root_url + arkivreferens, (
            f"Expected '{root_url + arkivreferens}', got '{result}'"
        )

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_empty_kalltyp_id_returns_none(self, data: st.DataObject) -> None:
        """When source.kalltyp_id is empty, returns None.

        Feature: source-management, Property 17: Direct link generation correctness
        **Validates: Requirements 10.1, 10.3**
        """
        source = data.draw(source_strategy(kalltyp_id="", arkivreferens="something"))
        kalltyper = data.draw(st.lists(kalltyp_strategy(root_url="http://x.com/"), max_size=3))

        result = generate_direct_link(source, kalltyper)
        assert result is None, f"Expected None for empty kalltyp_id, got '{result}'"

    @given(
        kt_id=non_empty_text,
        root_url=non_empty_root_url,
        arkivreferens=non_empty_arkivreferens,
        data=st.data(),
    )
    @settings(max_examples=100, deadline=None)
    def test_no_matching_kalltyp_returns_none(
        self, kt_id: str, root_url: str, arkivreferens: str, data: st.DataObject
    ) -> None:
        """When source.kalltyp_id doesn't match any Källtyp, returns None.

        Feature: source-management, Property 17: Direct link generation correctness
        **Validates: Requirements 10.1, 10.3**
        """
        source = data.draw(source_strategy(kalltyp_id=kt_id, arkivreferens=arkivreferens))
        # Generate kalltyper that do NOT match the source's kalltyp_id
        kalltyper = data.draw(
            st.lists(kalltyp_strategy(root_url=root_url), max_size=5).filter(
                lambda kts: all(kt.id != kt_id for kt in kts)
            )
        )

        result = generate_direct_link(source, kalltyper)
        assert result is None, (
            f"Expected None when no Källtyp matches id '{kt_id}', got '{result}'"
        )

    @given(
        kt_id=non_empty_text,
        arkivreferens=non_empty_arkivreferens,
        data=st.data(),
    )
    @settings(max_examples=100, deadline=None)
    def test_empty_root_url_returns_none(
        self, kt_id: str, arkivreferens: str, data: st.DataObject
    ) -> None:
        """When matching Källtyp has empty root_url, returns None.

        Feature: source-management, Property 17: Direct link generation correctness
        **Validates: Requirements 10.1, 10.3**
        """
        source = data.draw(source_strategy(kalltyp_id=kt_id, arkivreferens=arkivreferens))
        kalltyp = data.draw(kalltyp_strategy(kt_id=kt_id, root_url=""))
        kalltyper = [kalltyp]

        result = generate_direct_link(source, kalltyper)
        assert result is None, (
            f"Expected None for empty root_url, got '{result}'"
        )

    @given(
        kt_id=non_empty_text,
        root_url=non_empty_root_url,
        data=st.data(),
    )
    @settings(max_examples=100, deadline=None)
    def test_empty_arkivreferens_returns_none(
        self, kt_id: str, root_url: str, data: st.DataObject
    ) -> None:
        """When source.arkivreferens is empty, returns None.

        Feature: source-management, Property 17: Direct link generation correctness
        **Validates: Requirements 10.1, 10.3**
        """
        source = data.draw(source_strategy(kalltyp_id=kt_id, arkivreferens=""))
        kalltyp = data.draw(kalltyp_strategy(kt_id=kt_id, root_url=root_url))
        kalltyper = [kalltyp]

        result = generate_direct_link(source, kalltyper)
        assert result is None, (
            f"Expected None for empty arkivreferens, got '{result}'"
        )

    @given(
        root_url=non_empty_root_url,
        arkivreferens=non_empty_arkivreferens,
        kt_id=non_empty_text,
        data=st.data(),
    )
    @settings(max_examples=100, deadline=None)
    def test_result_starts_with_root_url(
        self, root_url: str, arkivreferens: str, kt_id: str, data: st.DataObject
    ) -> None:
        """Result (when not None) always starts with the Källtyp's root_url.

        Feature: source-management, Property 17: Direct link generation correctness
        **Validates: Requirements 10.1, 10.3**
        """
        source = data.draw(source_strategy(kalltyp_id=kt_id, arkivreferens=arkivreferens))
        kalltyp = data.draw(kalltyp_strategy(kt_id=kt_id, root_url=root_url))
        kalltyper = [kalltyp]

        result = generate_direct_link(source, kalltyper)
        assert result is not None, "Expected a link but got None"
        assert result.startswith(root_url), (
            f"Expected result to start with '{root_url}', got '{result}'"
        )

    @given(
        root_url=non_empty_root_url,
        arkivreferens=non_empty_arkivreferens,
        kt_id=non_empty_text,
        data=st.data(),
    )
    @settings(max_examples=100, deadline=None)
    def test_result_ends_with_arkivreferens(
        self, root_url: str, arkivreferens: str, kt_id: str, data: st.DataObject
    ) -> None:
        """Result (when not None) always ends with the source's arkivreferens.

        Feature: source-management, Property 17: Direct link generation correctness
        **Validates: Requirements 10.1, 10.3**
        """
        source = data.draw(source_strategy(kalltyp_id=kt_id, arkivreferens=arkivreferens))
        kalltyp = data.draw(kalltyp_strategy(kt_id=kt_id, root_url=root_url))
        kalltyper = [kalltyp]

        result = generate_direct_link(source, kalltyper)
        assert result is not None, "Expected a link but got None"
        assert result.endswith(arkivreferens), (
            f"Expected result to end with '{arkivreferens}', got '{result}'"
        )
