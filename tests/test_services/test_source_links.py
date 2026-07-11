"""Unit tests for source direct link generation.

Tests generate_direct_link from the source_links module.
"""

from __future__ import annotations

from slaktbusken.model.source import Kalltyp, Source
from slaktbusken.services.source_links import generate_direct_link


def _make_source(kalltyp_id: str = "", arkivreferens: str = "") -> Source:
    """Create a minimal Source for testing."""
    return Source(
        id="src-1",
        provider="",
        source_type="",
        title="Test",
        kalltyp_id=kalltyp_id,
        arkivreferens=arkivreferens,
    )


def _make_kalltyp(
    id: str = "kt-1",
    leverantor_id: str = "lev-1",
    name: str = "Sveriges Dödbok Webb",
    root_url: str = "",
) -> Kalltyp:
    """Create a minimal Kalltyp for testing."""
    return Kalltyp(id=id, leverantor_id=leverantor_id, name=name, root_url=root_url)


class TestGenerateDirectLink:
    """Tests for generate_direct_link."""

    def test_returns_concatenated_url_when_all_conditions_met(self) -> None:
        source = _make_source(kalltyp_id="kt-1", arkivreferens="12345")
        kalltyper = [
            _make_kalltyp(
                id="kt-1",
                root_url="https://www.rotter.se/abonnemang/sveriges-dodbok-webb/post/",
            )
        ]
        result = generate_direct_link(source, kalltyper)
        assert result == "https://www.rotter.se/abonnemang/sveriges-dodbok-webb/post/12345"

    def test_returns_none_when_kalltyp_id_empty(self) -> None:
        source = _make_source(kalltyp_id="", arkivreferens="12345")
        kalltyper = [
            _make_kalltyp(
                id="kt-1",
                root_url="https://example.com/",
            )
        ]
        result = generate_direct_link(source, kalltyper)
        assert result is None

    def test_returns_none_when_kalltyp_not_found(self) -> None:
        source = _make_source(kalltyp_id="kt-unknown", arkivreferens="12345")
        kalltyper = [
            _make_kalltyp(
                id="kt-1",
                root_url="https://example.com/",
            )
        ]
        result = generate_direct_link(source, kalltyper)
        assert result is None

    def test_returns_none_when_root_url_empty(self) -> None:
        source = _make_source(kalltyp_id="kt-1", arkivreferens="12345")
        kalltyper = [_make_kalltyp(id="kt-1", root_url="")]
        result = generate_direct_link(source, kalltyper)
        assert result is None

    def test_returns_none_when_arkivreferens_empty(self) -> None:
        source = _make_source(kalltyp_id="kt-1", arkivreferens="")
        kalltyper = [
            _make_kalltyp(
                id="kt-1",
                root_url="https://example.com/",
            )
        ]
        result = generate_direct_link(source, kalltyper)
        assert result is None

    def test_returns_none_with_empty_kalltyper_list(self) -> None:
        source = _make_source(kalltyp_id="kt-1", arkivreferens="12345")
        result = generate_direct_link(source, [])
        assert result is None

    def test_finds_correct_kalltyp_among_multiple(self) -> None:
        source = _make_source(kalltyp_id="kt-2", arkivreferens="ref-abc")
        kalltyper = [
            _make_kalltyp(id="kt-1", root_url="https://wrong.com/"),
            _make_kalltyp(id="kt-2", root_url="https://correct.com/path/"),
            _make_kalltyp(id="kt-3", root_url="https://other.com/"),
        ]
        result = generate_direct_link(source, kalltyper)
        assert result == "https://correct.com/path/ref-abc"
