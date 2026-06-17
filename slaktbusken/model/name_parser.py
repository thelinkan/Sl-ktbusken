"""Parse given-name strings for tilltalsnamn (primary name) asterisk markers.

Implements the Swedish genealogy convention where a trailing '*' on a name part
marks it as the tilltalsnamn — the name a person actually goes by.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedGivenName:
    """Result of parsing a given-name string for tilltalsnamn marker.

    Attributes:
        parts: Ordered list of name parts with asterisks removed.
        tilltalsnamn_index: Zero-based index of the marked part, or None.
        display_string: Clean display string (parts joined by spaces).
        raw: The original input string.
    """

    parts: list[str]
    tilltalsnamn_index: int | None
    display_string: str
    raw: str


def parse_given_name(given: str) -> ParsedGivenName:
    """Parse a given-name string, extracting tilltalsnamn marker.

    A name part is considered marked if it ends with exactly '*'.
    A '*' embedded within a name part (not at the end) is treated
    as a literal character.

    Args:
        given: The raw given-name string (may contain one '*' marker).

    Returns:
        ParsedGivenName with extracted information.

    Raises:
        ValueError: If more than one marker is found.
    """
    if not given or not given.strip():
        return ParsedGivenName(
            parts=[],
            tilltalsnamn_index=None,
            display_string="",
            raw=given,
        )

    raw_parts = given.split()
    clean_parts: list[str] = []
    marker_indices: list[int] = []

    for i, part in enumerate(raw_parts):
        if part.endswith("*"):
            # Trailing '*' is a marker — strip it
            clean_part = part[:-1]
            clean_parts.append(clean_part)
            marker_indices.append(i)
        else:
            # Any '*' embedded within the part is literal
            clean_parts.append(part)

    if len(marker_indices) > 1:
        raise ValueError(
            "Only one tilltalsnamn marker is permitted, "
            f"but found {len(marker_indices)} markers."
        )

    tilltalsnamn_index = marker_indices[0] if marker_indices else None
    display_string = " ".join(clean_parts)

    return ParsedGivenName(
        parts=clean_parts,
        tilltalsnamn_index=tilltalsnamn_index,
        display_string=display_string,
        raw=given,
    )


def format_given_name(parsed: ParsedGivenName) -> str:
    """Re-format a ParsedGivenName back to the raw marker string.

    Reconstructs the original given-name string by appending '*'
    after parts[tilltalsnamn_index].

    Args:
        parsed: A previously parsed given-name result.

    Returns:
        The reconstructed raw string equal to parsed.raw.
    """
    if not parsed.parts:
        return parsed.raw

    if parsed.tilltalsnamn_index is None:
        return " ".join(parsed.parts)

    result_parts = list(parsed.parts)
    result_parts[parsed.tilltalsnamn_index] = (
        result_parts[parsed.tilltalsnamn_index] + "*"
    )
    return " ".join(result_parts)


def validate_given_name_markers(given: str) -> list[str]:
    """Validate asterisk marker placement in a given-name string.

    Checks:
    - At most one '*' marker is present.
    - The '*' is placed immediately after a name part (not standalone,
      not leading, not preceded by whitespace).

    Args:
        given: The raw given-name string to validate.

    Returns:
        List of error messages (empty if valid).
    """
    if not given or not given.strip():
        return []

    errors: list[str] = []
    tokens = given.split()

    # Count trailing markers and detect malformed placements
    trailing_marker_count = 0
    malformed = False

    for token in tokens:
        if token == "*":
            # Standalone '*' — not attached to any name part
            malformed = True
        elif token.startswith("*"):
            # Leading '*' on a name part (e.g., "*Anna")
            malformed = True
        elif token.endswith("*"):
            # Valid trailing marker position
            trailing_marker_count += 1

    if trailing_marker_count > 1:
        errors.append(
            "Only one tilltalsnamn marker is permitted."
        )

    if malformed:
        errors.append(
            "The marker must be placed directly after a name part."
        )

    return errors
