"""Platform-independent data structures representing report output.

These dataclasses describe the content of a report in a rendering-agnostic
way. The Report_Paginator later lays out these blocks into pages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ReportBlock:
    """Base class for all report content blocks."""

    pass


@dataclass
class HeadingBlock(ReportBlock):
    """A heading at a given level.

    Levels:
        1 — report title
        2 — section
        3 — subsection
    """

    text: str
    level: int


@dataclass
class ParagraphBlock(ReportBlock):
    """A block of plain text forming a paragraph."""

    text: str


@dataclass
class ListBlock(ReportBlock):
    """An unordered list of text items."""

    items: list[str] = field(default_factory=list)


@dataclass
class ImageBlock(ReportBlock):
    """An embedded image with an optional caption."""

    path: Path
    caption: str | None = None


@dataclass
class EmptyStateBlock(ReportBlock):
    """Swedish-language 'no data' message shown when a section has no content."""

    text: str


@dataclass
class ReportContent:
    """Top-level container for a full report's content.

    Attributes:
        title: The report title (used for window title and page header).
        blocks: Ordered sequence of content blocks making up the report body.
    """

    title: str
    blocks: list[ReportBlock] = field(default_factory=list)
