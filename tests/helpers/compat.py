"""Compatibility comparison helper for format 0.3 -> 0.4 tests.

Format version 0.4 changes two values of an otherwise identical file, so every
compatibility and regression test compares serialisations through this module.
Nothing else may be normalised (Requirements 7.14, 32.1).
"""

from __future__ import annotations

import copy
import gzip
import json
from collections.abc import Mapping
from typing import Any

VERSION_KEYS = ("version", "format_version")  # the only two permitted differences
PLACEHOLDER = "<version>"

_MAX_REPORTED_DIFFERENCES = 10


def decode_project(source: bytes | str | Mapping) -> dict:
    """Return gzip bytes, JSON text or a decoded mapping as a plain dict (deep copy)."""
    if isinstance(source, Mapping):
        return copy.deepcopy(dict(source))
    if isinstance(source, (bytes, bytearray)):
        raw = bytes(source)
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        text = raw.decode("utf-8")
    elif isinstance(source, str):
        text = source
    else:
        raise TypeError(f"Unsupported project source: {type(source).__name__}")
    decoded = json.loads(text)
    if not isinstance(decoded, dict):
        raise ValueError("A project document must decode to a JSON object")
    return decoded


def normalise_version_fields(doc: Mapping[str, Any]) -> dict[str, Any]:
    """Return a new dict equal to *doc* except the top-level version values.

    The VALUES of the top-level keys ``version`` and ``format_version`` are
    replaced by PLACEHOLDER. An absent key stays absent. Nothing nested is
    touched and the input is not modified.
    """
    result = copy.deepcopy(dict(doc))
    for key in VERSION_KEYS:
        if key in result:
            result[key] = PLACEHOLDER
    return result


def _differences(a: Any, b: Any, path: str, out: list[str]) -> None:
    if len(out) >= _MAX_REPORTED_DIFFERENCES:
        return
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b), key=str):
            child = f"{path}.{key}" if path else str(key)
            if key not in a:
                out.append(f"{child}: only in after")
            elif key not in b:
                out.append(f"{child}: only in before")
            else:
                _differences(a[key], b[key], child, out)
            if len(out) >= _MAX_REPORTED_DIFFERENCES:
                return
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: list length {len(a)} != {len(b)}")
        for index, (x, y) in enumerate(zip(a, b)):
            _differences(x, y, f"{path}[{index}]", out)
            if len(out) >= _MAX_REPORTED_DIFFERENCES:
                return
    elif type(a) is not type(b) or a != b:
        out.append(f"{path}: {a!r} != {b!r}")


def assert_equal_except_version_fields(
    before: bytes | str | Mapping,
    after: bytes | str | Mapping,
    *,
    old_versions: tuple[str, ...] = ("0.1", "0.2", "0.3"),
    new_version: str = "0.4",
) -> None:
    """Fail unless normalise(decode(before)) == normalise(decode(after)).

    Also fails if *before*'s version fields are not one of *old_versions*, or
    *after*'s are not *new_version*, so the helper cannot degrade into a
    blanket pass. The message lists the JSON paths of the first 10 differences.
    """
    before_doc = decode_project(before)
    after_doc = decode_project(after)

    for label, doc, allowed in (
        ("before", before_doc, tuple(old_versions)),
        ("after", after_doc, (new_version,)),
    ):
        for key in VERSION_KEYS:
            if key not in doc:
                raise AssertionError(f"{label}: top-level '{key}' is missing")
            if doc[key] not in allowed:
                raise AssertionError(
                    f"{label}: '{key}' is {doc[key]!r}, expected one of {allowed!r}"
                )

    differences: list[str] = []
    _differences(
        normalise_version_fields(before_doc),
        normalise_version_fields(after_doc),
        "",
        differences,
    )
    if differences:
        raise AssertionError(
            "Documents differ beyond the version fields:\n  " + "\n  ".join(differences)
        )
