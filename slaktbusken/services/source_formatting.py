"""Source title formatting utilities.

Provides functions for formatting structured reference fields into
human-readable source titles used in the Swedish genealogy application.
"""

from __future__ import annotations

import re


def format_source_title(structured_ref: dict) -> str:
    """Format a source title from structured reference fields.

    Args:
        structured_ref: Dict with optional keys "parish", "series", "volume", "page".
            Each value may be a string (possibly empty) or missing from the dict.

    Returns:
        Formatted title string. Example: "Ljusdal AI:17 Sida: 32"

    Rules:
        1. If "parish" is present and non-empty: include it
        2. If "series" and "volume" are both present and non-empty: include "{series}:{volume}"
           - If only "series" is present: include just "{series}"
           - If only "volume" is present: skip it (volume alone doesn't make sense)
        3. If "page" is present and non-empty: append "Sida: {page}"
        4. Join all non-empty parts with single space
        5. Post-process: strip leading/trailing whitespace, collapse consecutive spaces to one
    """
    parts: list[str] = []

    parish = structured_ref.get("parish", "").strip()
    series = structured_ref.get("series", "").strip()
    volume = structured_ref.get("volume", "").strip()
    page = structured_ref.get("page", "").strip()
    image = structured_ref.get("image", "").strip()

    if parish:
        parts.append(parish)

    if series and volume:
        parts.append(f"{series}:{volume}")
    elif series:
        parts.append(series)
    # volume alone is skipped

    if page:
        parts.append(f"Sida: {page}")
    elif image:
        parts.append(f"Bild: {image}")

    result = " ".join(parts)

    # Post-process: trim and collapse multiple spaces
    result = result.strip()
    result = re.sub(r" {2,}", " ", result)

    return result
