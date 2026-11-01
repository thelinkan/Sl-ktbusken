"""Frozen copy of the format 0.3 serialiser (before the person merge feature).

Do NOT change this file to follow the production serialiser. It is the oracle
for "a project without merge data serialises as before" (Requirements 7.14,
32.1, Property 45). It reads only the ProjectData attributes that existed in
0.3 and therefore never touches merge candidates, merge history or load
findings.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import fields as dc_fields
from typing import Any, get_args, get_origin

_ENTITY_FIELDS = [
    "persons", "families", "events", "residences", "places", "sources",
    "media", "repositories", "dna_companies", "dna_profiles",
    "dna_matches", "dna_segments", "dna_clusters",
    "dna_triangulations", "research_notes", "leverantorer", "kalltyper",
    "research_cases", "research_hypotheses", "research_actions",
]


def serialize_v0_3(data: Any) -> str:
    """Serialise *data* exactly as the 0.3 code did, returning a JSON string."""
    output: dict[str, Any] = {}
    output["format"] = data.format
    output["version"] = data.version
    output["format_version"] = data.version

    output["project"] = _serialize_dataclass(data.project)

    for field_name in _ENTITY_FIELDS:
        items = getattr(data, field_name, [])
        if field_name == "places":
            from slaktbusken.services.place_dedupe import deduplicate_places

            items, _ = deduplicate_places(list(items))
        output[field_name] = [_serialize_dataclass(item) for item in items]

    if data.connection_overrides:
        output["connection_overrides"] = dict(data.connection_overrides)

    if data.id_high_water_marks:
        output["id_high_water_marks"] = dict(data.id_high_water_marks)

    return json.dumps(output, ensure_ascii=False, indent=2)


def _serialize_dataclass(obj: Any) -> dict[str, Any]:
    if not hasattr(obj, "__dataclass_fields__"):
        return obj

    result: dict[str, Any] = {}
    for f in dc_fields(obj):
        value = getattr(obj, f.name)
        if value is None and _is_optional_field(f) and _has_default(f):
            continue
        if value == [] and _has_default_factory_list(f):
            continue
        if value == "" and _has_default_empty_string(f):
            continue
        result[f.name] = _serialize_value(value)
    return result


def _serialize_value(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return _serialize_dataclass(value)
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    return value


def _is_optional_field(f: Any) -> bool:
    origin = get_origin(f.type)
    if origin is not None:
        return type(None) in get_args(f.type)
    type_str = str(f.type) if not isinstance(f.type, str) else f.type
    return "Optional" in type_str or "None" in type_str


def _has_default(f: Any) -> bool:
    return (
        f.default is not dataclasses.MISSING
        or f.default_factory is not dataclasses.MISSING
    )


def _has_default_factory_list(f: Any) -> bool:
    return (
        f.default_factory is not dataclasses.MISSING
        and f.default_factory is list
    )


def _has_default_empty_string(f: Any) -> bool:
    return f.default is not dataclasses.MISSING and f.default == ""
