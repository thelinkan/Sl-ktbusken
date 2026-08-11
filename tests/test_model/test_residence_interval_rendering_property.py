# Feature: residence-periods, Property 23: The Residence_Formatter renders each classification pair distinguishably
"""Property-based test for interval rendering.

Feature: residence-periods, Property 23: The Residence_Formatter renders each classification pair distinguishably

For any pair of Endpoints, the rendered interval carries at each position exactly
the marker that position's classification requires — no marker for an exact date,
"senast" for an Endpoint holding only `latest`, "tidigast" for one holding only
`earliest`, "mellan … och" for a transition window, "okänt" for an unknown
Endpoint — with the same wording used at the start and end positions alike; the
two rendered Endpoints are joined by exactly one en dash U+2013 with no space
before or after it and no "?" placeholder; two Endpoints that are both unknown
render as "okänd period" with no separator; month and day precision values render
in their stored ÅÅÅÅ-MM and ÅÅÅÅ-MM-DD forms without truncation to the year; a
non-empty `role_in_household` is appended after the interval as a comma and one
space followed by the stored value, and an empty one adds no separator and no
trailing whitespace; consequently the marker pair recovered from any rendered
interval identifies its classification pair, so two ordered pairs whose
classifications differ render differently.

**Validates: Requirements 10.8, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.11, 11.12, 11.13**
"""

from __future__ import annotations

import re
from itertools import product

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.residence import Endpoint, EndpointKind, classify_endpoint
from slaktbusken.ui.swedish_locale import (
    RESIDENCE_INTERVAL_DASH,
    RESIDENCE_UNKNOWN_ENDPOINT,
    RESIDENCE_UNKNOWN_PERIOD,
    format_residence_endpoint,
    format_residence_interval,
    format_residence_line,
)
from tests.test_model.residence_strategies import endpoints


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# The en dash U+2013 that separates rendered endpoints (Requirement 11.11).
_EN_DASH = "\u2013"

# Marker words per classification (Requirements 11.1–11.5).
_MARKER_WORDS = {
    EndpointKind.EXACT: None,           # bare value, no prefix
    EndpointKind.OPEN_LATEST: "senast",
    EndpointKind.OPEN_EARLIEST: "tidigast",
    EndpointKind.WINDOW: "mellan",      # "mellan {e} och {l}"
    EndpointKind.UNKNOWN: "okänt",
}


def _endpoint_has_marker(rendered: str, kind: EndpointKind) -> bool:
    """Check that the rendered Endpoint carries exactly its required marker."""
    if kind is EndpointKind.UNKNOWN:
        return rendered == RESIDENCE_UNKNOWN_ENDPOINT
    if kind is EndpointKind.OPEN_LATEST:
        return rendered.startswith("senast ")
    if kind is EndpointKind.OPEN_EARLIEST:
        return rendered.startswith("tidigast ")
    if kind is EndpointKind.WINDOW:
        return rendered.startswith("mellan ") and " och " in rendered
    # EXACT: no marker word — just a bare date value.
    return (
        not rendered.startswith("senast ")
        and not rendered.startswith("tidigast ")
        and not rendered.startswith("mellan ")
        and rendered != RESIDENCE_UNKNOWN_ENDPOINT
    )


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


class TestIntervalRendering:
    """Property 23: The Residence_Formatter renders each classification pair distinguishably.

    **Validates: Requirements 10.8, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.11, 11.12, 11.13**
    """

    @given(
        start=endpoints(include_notes=False),
        end=endpoints(include_notes=False),
        role=st.one_of(
            st.just(""),
            st.text(
                alphabet=st.characters(categories=("Ll", "Lu", "Nd"), max_codepoint=0x24F),
                min_size=1,
                max_size=30,
            ),
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_classification_pair_determines_rendering(
        self, start: Endpoint, end: Endpoint, role: str
    ) -> None:
        """Every classification pair renders with the correct markers, dash and role suffix.

        Feature: residence-periods, Property 23: The Residence_Formatter renders each classification pair distinguishably

        **Validates: Requirements 10.8, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.11, 11.12, 11.13**
        """
        start_kind = classify_endpoint(start)
        end_kind = classify_endpoint(end)
        rendered_start = format_residence_endpoint(start)
        rendered_end = format_residence_endpoint(end)
        interval = format_residence_interval(start, end)

        # --- Requirement 11.11: joined by exactly one en dash, no spaces around it ---
        if start_kind is EndpointKind.UNKNOWN and end_kind is EndpointKind.UNKNOWN:
            # Requirement 11.12: two unknown endpoints → "okänd period"
            assert interval == RESIDENCE_UNKNOWN_PERIOD
            assert _EN_DASH not in interval
        else:
            # Exactly one en dash, no space before/after it (11.11).
            assert interval.count(_EN_DASH) == 1
            dash_pos = interval.index(_EN_DASH)
            if dash_pos > 0:
                assert interval[dash_pos - 1] != " "
            if dash_pos < len(interval) - 1:
                assert interval[dash_pos + 1] != " "
            # No "?" placeholder anywhere.
            assert "?" not in interval
            # The interval is the concatenation of rendered start + dash + rendered end.
            assert interval == f"{rendered_start}{_EN_DASH}{rendered_end}"

        # --- Requirements 11.1–11.5: each position carries its marker ---
        assert _endpoint_has_marker(rendered_start, start_kind)
        assert _endpoint_has_marker(rendered_end, end_kind)

        # --- Requirement 11.13: month and day values keep stored forms ---
        # If earliest or latest is month precision (ÅÅÅÅ-MM) or day (ÅÅÅÅ-MM-DD)
        # and the endpoint kind uses it, the rendered output contains it as-is.
        for ep, rendered in [(start, rendered_start), (end, rendered_end)]:
            ep_kind = classify_endpoint(ep)
            if ep_kind in (EndpointKind.EXACT, EndpointKind.WINDOW):
                if ep.earliest and ep.earliest.strip():
                    assert ep.earliest.strip() in rendered
            if ep_kind is EndpointKind.OPEN_LATEST:
                if ep.latest and ep.latest.strip():
                    assert ep.latest.strip() in rendered
            if ep_kind is EndpointKind.OPEN_EARLIEST:
                if ep.earliest and ep.earliest.strip():
                    assert ep.earliest.strip() in rendered
            if ep_kind is EndpointKind.WINDOW:
                if ep.latest and ep.latest.strip():
                    assert ep.latest.strip() in rendered

        # --- Requirement 10.8: role appending ---
        line = format_residence_line("", start, end, role)
        if role:
            # Non-empty role: interval followed by ", {role}"
            assert line.endswith(f", {role}")
            assert not line.endswith(f", {role} ")  # no trailing whitespace
        else:
            # Empty role: no trailing comma/space, no trailing whitespace.
            assert line == interval
            assert line == line.rstrip()

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_distinct_classification_pairs_render_differently(
        self, data: st.DataObject
    ) -> None:
        """Two ordered pairs whose classifications differ render differently (11.6).

        Feature: residence-periods, Property 23: The Residence_Formatter renders each classification pair distinguishably

        **Validates: Requirements 11.6**
        """
        kinds = list(EndpointKind)
        # Pick two distinct ordered classification pairs.
        pair1 = data.draw(
            st.tuples(st.sampled_from(kinds), st.sampled_from(kinds))
        )
        pair2 = data.draw(
            st.tuples(st.sampled_from(kinds), st.sampled_from(kinds)).filter(
                lambda p: p != pair1
            )
        )

        start1 = data.draw(endpoints(kind=pair1[0], include_notes=False))
        end1 = data.draw(endpoints(kind=pair1[1], include_notes=False))
        start2 = data.draw(endpoints(kind=pair2[0], include_notes=False))
        end2 = data.draw(endpoints(kind=pair2[1], include_notes=False))

        interval1 = format_residence_interval(start1, end1)
        interval2 = format_residence_interval(start2, end2)

        # Different classification pairs must produce different rendered strings.
        assert interval1 != interval2
