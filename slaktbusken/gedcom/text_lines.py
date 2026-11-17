"""GEDCOM free-text writer (CONT per line break, CONC for long lines).

Pure module, no Qt. The parser (``parser.py``) is the reading counterpart:
CONT appends a newline, CONC appends without separator, and a doubled leading
``@`` reads as one ``@``.

Design: ``.kiro/specs/gedcom-roundtrip-0-3-0/design.md``, component C1.
"""

from __future__ import annotations

__all__ = ["text_lines", "escape_text"]


def escape_text(text: str) -> str:
    """Double a leading ``@`` (GEDCOM 5.5.1, escape for line values)."""
    return "@" + text if text.startswith("@") else text


def _split_at(line: str, max_len: int) -> list[str]:
    """Split ``line`` into chunks of at most ``max_len`` characters.

    Spaces stay at the end of the chunk before the split, because the parser
    joins CONC without a separator. A chunk never ends between the two halves
    of a surrogate pair.
    """
    chunks: list[str] = []
    start = 0
    while len(line) - start > max_len:
        end = start + max_len
        if "\ud800" <= line[end - 1] <= "\udbff" and "\udc00" <= line[end] <= "\udfff":
            end -= 1
        chunks.append(line[start:end])
        start = end
    chunks.append(line[start:])
    return chunks


def text_lines(level: int, tag: str, text: str, max_len: int = 200) -> list[str]:
    """Return the GEDCOM lines that carry ``text`` under ``level tag``.

    A line break in ``text`` starts a ``CONT`` line at ``level + 1``. A line
    longer than ``max_len`` characters continues in ``CONC`` lines. A leading
    ``@`` of the first line and of each CONT line is doubled. CR and CRLF count
    as line breaks. An empty text gives the bare ``level tag`` line.
    """
    if max_len < 2:
        raise ValueError("max_len must be at least 2")
    physical = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    for index, line in enumerate(physical):
        chunks = _split_at(escape_text(line), max_len)
        head_level, head_tag = (level, tag) if index == 0 else (level + 1, "CONT")
        out.append(_format(head_level, head_tag, chunks[0]))
        out.extend(_format(level + 1, "CONC", chunk) for chunk in chunks[1:])
    return out


def _format(level: int, tag: str, value: str) -> str:
    return f"{level} {tag} {value}" if value else f"{level} {tag}"
