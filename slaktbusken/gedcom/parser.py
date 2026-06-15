"""GEDCOM 5.5.1 line-level parser.

Parses GEDCOM files into a tree structure of ``GedcomLine`` nodes. Each line
in a GEDCOM file follows the format::

    LEVEL [XREF_ID] TAG [LINE_VALUE]

The parser handles continuation lines (CONC appends without space, CONT
appends with a newline) and builds a hierarchical tree based on line levels.

Example usage::

    from slaktbusken.gedcom.parser import parse_gedcom

    result = parse_gedcom(gedcom_text)
    for record in result.records:
        print(record.tag, record.value)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class GedcomLine:
    """A single parsed GEDCOM line with its children.

    Attributes:
        level: The indentation level (0-99).
        tag: The GEDCOM tag (e.g., INDI, FAM, NAME).
        value: The optional text value after the tag.
        xref_id: The optional cross-reference identifier (e.g., @I1@).
        line_number: The 1-based line number in the source file.
        children: Child lines (level N+1 lines following this level N line).
    """

    level: int
    tag: str
    value: Optional[str]
    xref_id: Optional[str]
    line_number: int
    children: list[GedcomLine] = field(default_factory=list)


@dataclass
class ParseWarning:
    """A warning generated during parsing.

    Attributes:
        line_number: The 1-based line number where the issue occurred.
        message: A description of the problem (in Swedish).
    """

    line_number: int
    message: str


@dataclass
class ParseResult:
    """The result of parsing a GEDCOM file.

    Attributes:
        records: Top-level (level 0) GEDCOM records as a tree.
        warnings: Any warnings accumulated during parsing.
    """

    records: list[GedcomLine] = field(default_factory=list)
    warnings: list[ParseWarning] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Regex matching a valid GEDCOM line:
# LEVEL [XREF_ID] TAG [VALUE]
_GEDCOM_LINE_RE = re.compile(
    r"^(\d{1,2})"           # Level (0-99)
    r"\s+"                   # Separator
    r"(?:(@[^@]+@)\s+)?"    # Optional XREF_ID like @I1@
    r"([A-Za-z_][A-Za-z0-9_]*)"  # Tag
    r"(?:\s(.*))?$"          # Optional value (rest of line)
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_gedcom(text: str) -> ParseResult:
    """Parse a GEDCOM-formatted string into a structured tree.

    Performs best-effort parsing: malformed lines generate warnings but do not
    stop the parser. Non-GEDCOM files (those lacking a ``0 HEAD`` record near
    the beginning) raise ``GedcomParseError``.

    Args:
        text: The full GEDCOM file content as a string.

    Returns:
        A ``ParseResult`` containing the parsed record tree and any warnings.

    Raises:
        GedcomParseError: If the file does not appear to be a valid GEDCOM file
            (no ``0 HEAD`` found within the first 5 non-empty lines).
    """
    lines = text.splitlines()
    _validate_is_gedcom(lines)
    return _build_tree(lines)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class GedcomParseError(Exception):
    """Raised when a file cannot be identified as a valid GEDCOM file.

    Attributes:
        message: Swedish-language error description.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_is_gedcom(lines: list[str]) -> None:
    """Check that the file appears to be GEDCOM (has ``0 HEAD`` near the start).

    Scans the first 5 non-empty lines for a line matching ``0 HEAD``.

    Args:
        lines: All lines from the file.

    Raises:
        GedcomParseError: If no ``0 HEAD`` is found.
    """
    non_empty_count = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        non_empty_count += 1
        if stripped == "0 HEAD" or stripped.startswith("0 HEAD "):
            return
        if non_empty_count >= 5:
            break

    raise GedcomParseError(
        "Filen verkar inte vara en giltig GEDCOM-fil: "
        "saknar '0 HEAD'-post i början av filen."
    )


def _build_tree(lines: list[str]) -> ParseResult:
    """Parse all lines and build the hierarchical tree structure.

    Args:
        lines: All lines from the GEDCOM file.

    Returns:
        A ``ParseResult`` with the tree and accumulated warnings.
    """
    result = ParseResult()
    # Stack tracks the current nesting: stack[i] is the most recent node at level i
    stack: list[GedcomLine] = []

    for line_number, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue

        parsed = _parse_line(stripped, line_number)
        if parsed is None:
            result.warnings.append(ParseWarning(
                line_number=line_number,
                message=f"Rad {line_number}: Felformaterad rad kunde inte tolkas.",
            ))
            continue

        # Handle continuation lines
        if parsed.tag in ("CONC", "CONT"):
            _handle_continuation(parsed, stack, result.warnings)
            continue

        # Place the node in the tree
        if parsed.level == 0:
            result.records.append(parsed)
            stack = [parsed]
        else:
            # Find the parent: the most recent node at level - 1
            parent_level = parsed.level - 1
            if parent_level < len(stack) and stack[parent_level] is not None:
                stack[parent_level].children.append(parsed)
                # Update stack: trim to current level and set this node
                if parsed.level < len(stack):
                    stack[parsed.level] = parsed
                    # Trim anything deeper
                    del stack[parsed.level + 1:]
                else:
                    stack.append(parsed)
            else:
                # Orphan line — level is too deep for current context
                result.warnings.append(ParseWarning(
                    line_number=line_number,
                    message=(
                        f"Rad {line_number}: Nivå {parsed.level} saknar "
                        f"föräldrapost på nivå {parent_level}."
                    ),
                ))

    return result


def _parse_line(stripped: str, line_number: int) -> Optional[GedcomLine]:
    """Attempt to parse a single GEDCOM line.

    Args:
        stripped: The whitespace-trimmed line text.
        line_number: The 1-based line number for error reporting.

    Returns:
        A ``GedcomLine`` if the line is valid, or ``None`` if it cannot be parsed.
    """
    match = _GEDCOM_LINE_RE.match(stripped)
    if not match:
        return None

    level = int(match.group(1))
    xref_id = match.group(2)
    tag = match.group(3)
    value = match.group(4)

    # Validate level range
    if level > 99:
        return None

    return GedcomLine(
        level=level,
        tag=tag,
        value=value if value else None,
        xref_id=xref_id,
        line_number=line_number,
    )


def _handle_continuation(
    parsed: GedcomLine,
    stack: list[GedcomLine],
    warnings: list[ParseWarning],
) -> None:
    """Handle CONC and CONT continuation lines.

    CONC appends to the previous value without any separator.
    CONT appends to the previous value with a newline separator.

    Args:
        parsed: The parsed continuation line.
        stack: The current parsing stack.
        warnings: Warning list to append to if there's no parent.
    """
    parent_level = parsed.level - 1
    if parent_level < 0 or parent_level >= len(stack) or stack[parent_level] is None:
        warnings.append(ParseWarning(
            line_number=parsed.line_number,
            message=(
                f"Rad {parsed.line_number}: {parsed.tag}-rad saknar "
                f"föregående post att fortsätta."
            ),
        ))
        return

    parent = stack[parent_level]
    continuation_value = parsed.value or ""

    if parsed.tag == "CONC":
        # Append without separator
        if parent.value is None:
            parent.value = continuation_value
        else:
            parent.value += continuation_value
    elif parsed.tag == "CONT":
        # Append with newline separator
        if parent.value is None:
            parent.value = "\n" + continuation_value
        else:
            parent.value += "\n" + continuation_value
