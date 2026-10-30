"""Script-injection safety of the map marker JSON.

``markers_to_json`` output is spliced directly into a ``<script>`` block in the
map HTML template. Marker names come from project data, so the serialized JSON
must not be able to terminate the surrounding script element.
"""

from __future__ import annotations

import json

from slaktbusken.services.map_data_service import MapMarker, markers_to_json


def _marker(place_name: str) -> MapMarker:
    return MapMarker(
        place_id="p1",
        place_name=place_name,
        latitude=59.0,
        longitude=18.0,
    )


def test_script_close_tag_cannot_break_out() -> None:
    payload = "Ort</script><img src=x onerror=alert(1)>"
    out = markers_to_json([_marker(payload)])
    # No raw markup that would close the <script> or open a tag survives.
    assert "</script>" not in out
    assert "<" not in out
    assert ">" not in out


def test_output_round_trips_to_identical_data() -> None:
    payload = "Ort</script> & <b>bold</b>\u2028\u2029"
    out = markers_to_json([_marker(payload)])
    parsed = json.loads(out)
    assert parsed[0]["place_name"] == payload


def test_ampersand_and_line_separators_are_escaped() -> None:
    out = markers_to_json([_marker("A & B\u2028C\u2029D")])
    assert "&" not in out
    assert "\u2028" not in out
    assert "\u2029" not in out
