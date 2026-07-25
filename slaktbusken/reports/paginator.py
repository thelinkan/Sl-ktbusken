"""Report paginator — lays out ReportContent blocks into pages.

This is a pure layout engine with no Qt dependencies. It works entirely
with mm dimensions and produces RenderedPage objects that the UI layer
can later paint using QPainter.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from slaktbusken.reports.content import (
    EmptyStateBlock,
    HeadingBlock,
    ImageBlock,
    ListBlock,
    ParagraphBlock,
    ReportBlock,
    ReportContent,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PageLayout:
    """Physical page dimensions with margins."""

    width_mm: float
    height_mm: float
    margin_mm: float = 15.0

    @property
    def printable_width(self) -> float:
        """Width available for content (excluding left + right margins)."""
        return self.width_mm - 2 * self.margin_mm

    @property
    def printable_height(self) -> float:
        """Height available for content (excluding top + bottom margins)."""
        return self.height_mm - 2 * self.margin_mm


@dataclass
class RenderedElement:
    """A single rendered element positioned on a page.

    Coordinates are relative to the page's top-left corner (including margins),
    i.e. (x=0, y=0) means the top-left of the printable area.

    Attributes:
        x_mm: Horizontal position in mm from left margin.
        y_mm: Vertical position in mm from top margin.
        width_mm: Width of the element in mm.
        height_mm: Height of the element in mm.
        element_type: One of "heading", "paragraph_line", "list_item_line",
                      "image", "caption", "empty_state".
        text: Text content (for text elements).
        level: Heading level (1, 2, 3) — only relevant for headings.
        image_path: Path to image file (only for image elements).
        source_block: Reference to the original ReportBlock this came from.
    """

    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float
    element_type: str
    text: str | None = None
    level: int | None = None
    image_path: Path | None = None
    source_block: ReportBlock | None = field(default=None, repr=False)


@dataclass
class RenderedPage:
    """A single rendered page of the report.

    Attributes:
        page_number: 1-based page number.
        total_pages: Total number of pages (filled after full pagination).
        elements: Ordered list of rendered elements on this page.
    """

    page_number: int
    total_pages: int
    elements: list[RenderedElement] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Paper sizes
# ---------------------------------------------------------------------------

PAPER_SIZES: dict[str, PageLayout] = {
    "A4": PageLayout(width_mm=210.0, height_mm=297.0),
    "A3": PageLayout(width_mm=297.0, height_mm=420.0),
    "A5": PageLayout(width_mm=148.0, height_mm=210.0),
}

# ---------------------------------------------------------------------------
# Layout constants (approximate mm heights for text)
# ---------------------------------------------------------------------------

_HEADING_HEIGHTS: dict[int, float] = {
    1: 9.0,  # Report title
    2: 7.0,  # Section heading
    3: 6.0,  # Subsection heading
}

_PARAGRAPH_LINE_HEIGHT: float = 5.0
_LIST_ITEM_LINE_HEIGHT: float = 5.0
_CAPTION_LINE_HEIGHT: float = 5.0
_EMPTY_STATE_LINE_HEIGHT: float = 5.0

# Spacing after a heading before its content
_HEADING_SPACING: float = 2.0
# Spacing between blocks
_BLOCK_SPACING: float = 3.0

# Approximate character width in mm for word-wrapping calculations.
# This is an approximation assuming ~2.2mm per character for body text.
_CHAR_WIDTH_BODY: float = 2.2
_CHAR_WIDTH_HEADING: dict[int, float] = {
    1: 3.5,
    2: 2.8,
    3: 2.5,
}

# Default assumed image size when PIL cannot read the file (mm)
_DEFAULT_IMAGE_WIDTH_MM: float = 100.0
_DEFAULT_IMAGE_HEIGHT_MM: float = 75.0

# DPI assumption for converting image pixels to mm
_IMAGE_DPI: float = 96.0
_PX_TO_MM: float = 25.4 / _IMAGE_DPI


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wrap_text(text: str, max_width_mm: float, char_width: float) -> list[str]:
    """Break text into lines at word/hyphen boundaries to fit max_width_mm.

    Line breaks occur ONLY at whitespace or hyphen boundaries (Requirement 6.1).
    URLs (starting with http:// or https://) are never broken at hyphens.
    """
    if not text:
        return [""]

    max_chars = max(1, int(max_width_mm / char_width))
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current_line = ""

    for word in words:
        # Never split URLs at hyphens — they must stay intact
        if word.startswith("http://") or word.startswith("https://"):
            parts = [word]
        else:
            # Handle words with hyphens — we can break at hyphens too
            parts = _split_at_hyphens(word)
        for i, part in enumerate(parts):
            candidate = part
            if current_line:
                test = current_line + " " + candidate
            else:
                test = candidate

            if len(test) <= max_chars:
                current_line = test
            else:
                if current_line:
                    lines.append(current_line)
                # If the part itself is longer than max_chars, it still goes
                # on its own line (we do not break words mid-character).
                current_line = candidate

    if current_line:
        lines.append(current_line)

    return lines if lines else [""]


def _split_at_hyphens(word: str) -> list[str]:
    """Split a word at hyphen boundaries, keeping the hyphen attached to the left part.

    For example: "twenty-five" -> ["twenty-", "five"]
    """
    if "-" not in word:
        return [word]

    parts: list[str] = []
    remaining = word
    while "-" in remaining:
        idx = remaining.index("-")
        parts.append(remaining[: idx + 1])  # include the hyphen
        remaining = remaining[idx + 1 :]
    if remaining:
        parts.append(remaining)
    return parts


def _get_image_size_mm(path: Path) -> tuple[float, float] | None:
    """Get image dimensions in mm. Returns None if image is unreadable."""
    try:
        from PIL import Image

        with Image.open(path) as img:
            width_px, height_px = img.size
        return (width_px * _PX_TO_MM, height_px * _PX_TO_MM)
    except Exception:
        # PIL not available or image unreadable
        return None


# ---------------------------------------------------------------------------
# Paginator
# ---------------------------------------------------------------------------


class ReportPaginator:
    """Lays out ReportContent blocks into pages respecting paper size,
    line-breaking rules, section-keep-together, and image placement."""

    def paginate(
        self, content: ReportContent, paper_size: str
    ) -> list[RenderedPage]:
        """Paginate report content for the given paper size.

        Args:
            content: The report content to paginate.
            paper_size: Paper size key (e.g. "A4", "A3", "A5").
                       Falls back to "A4" if unrecognized.

        Returns:
            List of RenderedPage objects with page numbers and elements.
        """
        layout = PAPER_SIZES.get(paper_size, PAPER_SIZES["A4"])
        pages: list[RenderedPage] = []
        current_page = RenderedPage(page_number=1, total_pages=0, elements=[])
        pages.append(current_page)
        y_cursor: float = 0.0  # vertical position on current page

        printable_w = layout.printable_width
        printable_h = layout.printable_height

        for block in content.blocks:
            if isinstance(block, HeadingBlock):
                y_cursor = self._layout_heading(
                    block, pages, current_page, y_cursor, printable_w, printable_h, layout
                )
                current_page = pages[-1]

            elif isinstance(block, ParagraphBlock):
                y_cursor = self._layout_paragraph(
                    block, pages, current_page, y_cursor, printable_w, printable_h, layout
                )
                current_page = pages[-1]

            elif isinstance(block, ListBlock):
                y_cursor = self._layout_list(
                    block, pages, current_page, y_cursor, printable_w, printable_h, layout
                )
                current_page = pages[-1]

            elif isinstance(block, ImageBlock):
                y_cursor = self._layout_image(
                    block, pages, current_page, y_cursor, printable_w, printable_h, layout
                )
                current_page = pages[-1]

            elif isinstance(block, EmptyStateBlock):
                y_cursor = self._layout_empty_state(
                    block, pages, current_page, y_cursor, printable_w, printable_h, layout
                )
                current_page = pages[-1]

        # Fill in total_pages
        total = len(pages)
        for page in pages:
            page.total_pages = total

        return pages

    # ------------------------------------------------------------------
    # Layout methods for each block type
    # ------------------------------------------------------------------

    def _layout_heading(
        self,
        block: HeadingBlock,
        pages: list[RenderedPage],
        current_page: RenderedPage,
        y_cursor: float,
        printable_w: float,
        printable_h: float,
        layout: PageLayout,
    ) -> float:
        """Lay out a heading block with section-keep-together logic."""
        level = block.level
        heading_height = _HEADING_HEIGHTS.get(level, 5.0)
        char_width = _CHAR_WIDTH_HEADING.get(level, 2.5)

        # Wrap heading text
        lines = _wrap_text(block.text, printable_w, char_width)
        total_heading_height = heading_height * len(lines)

        # Section-keep-together: heading + at least one content line must fit.
        # We require heading height + heading_spacing + block_spacing (from next block) + one body line (4mm).
        min_section_height = total_heading_height + _HEADING_SPACING + _BLOCK_SPACING + _PARAGRAPH_LINE_HEIGHT

        # Add block spacing if not at top of page
        spacing = _BLOCK_SPACING if y_cursor > 0 else 0.0

        if y_cursor + spacing + min_section_height > printable_h:
            # Start new page
            current_page = self._new_page(pages)
            y_cursor = 0.0
            spacing = 0.0

        y_cursor += spacing

        for line_text in lines:
            element = RenderedElement(
                x_mm=0.0,
                y_mm=y_cursor,
                width_mm=printable_w,
                height_mm=heading_height,
                element_type="heading",
                text=line_text,
                level=level,
                source_block=block,
            )
            current_page.elements.append(element)
            y_cursor += heading_height

        # Add spacing after heading
        y_cursor += _HEADING_SPACING

        return y_cursor

    def _layout_paragraph(
        self,
        block: ParagraphBlock,
        pages: list[RenderedPage],
        current_page: RenderedPage,
        y_cursor: float,
        printable_w: float,
        printable_h: float,
        layout: PageLayout,
    ) -> float:
        """Lay out a paragraph block, wrapping text and handling page overflow."""
        lines = _wrap_text(block.text, printable_w, _CHAR_WIDTH_BODY)

        # Add block spacing if not at top of page
        spacing = _BLOCK_SPACING if y_cursor > 0 else 0.0
        y_cursor += spacing

        for line_text in lines:
            if y_cursor + _PARAGRAPH_LINE_HEIGHT > printable_h:
                current_page = self._new_page(pages)
                y_cursor = 0.0

            element = RenderedElement(
                x_mm=0.0,
                y_mm=y_cursor,
                width_mm=printable_w,
                height_mm=_PARAGRAPH_LINE_HEIGHT,
                element_type="paragraph_line",
                text=line_text,
                source_block=block,
            )
            current_page.elements.append(element)
            y_cursor += _PARAGRAPH_LINE_HEIGHT

        return y_cursor

    def _layout_list(
        self,
        block: ListBlock,
        pages: list[RenderedPage],
        current_page: RenderedPage,
        y_cursor: float,
        printable_w: float,
        printable_h: float,
        layout: PageLayout,
    ) -> float:
        """Lay out a list block, wrapping each item and handling page overflow."""
        # Add block spacing if not at top of page
        spacing = _BLOCK_SPACING if y_cursor > 0 else 0.0
        y_cursor += spacing

        for item_text in block.items:
            # Prefix with bullet
            full_text = f"• {item_text}"
            lines = _wrap_text(full_text, printable_w, _CHAR_WIDTH_BODY)

            for line_text in lines:
                if y_cursor + _LIST_ITEM_LINE_HEIGHT > printable_h:
                    current_page = self._new_page(pages)
                    y_cursor = 0.0

                element = RenderedElement(
                    x_mm=0.0,
                    y_mm=y_cursor,
                    width_mm=printable_w,
                    height_mm=_LIST_ITEM_LINE_HEIGHT,
                    element_type="list_item_line",
                    text=line_text,
                    source_block=block,
                )
                current_page.elements.append(element)
                y_cursor += _LIST_ITEM_LINE_HEIGHT

        return y_cursor

    def _layout_image(
        self,
        block: ImageBlock,
        pages: list[RenderedPage],
        current_page: RenderedPage,
        y_cursor: float,
        printable_w: float,
        printable_h: float,
        layout: PageLayout,
    ) -> float:
        """Lay out an image block with page-fit and caption co-location logic."""
        # Try to get image dimensions
        image_size = _get_image_size_mm(block.path)

        if image_size is None:
            # Corrupt or unreadable image — insert placeholder text
            logger.warning(
                "Could not read image at %s, inserting placeholder.", block.path
            )
            return self._layout_placeholder(
                block, pages, current_page, y_cursor, printable_w, printable_h
            )

        img_w, img_h = image_size

        # Scale down if larger than printable area (Requirement 7.3)
        img_w, img_h = self._scale_image_to_fit(
            img_w, img_h, printable_w, printable_h, block.caption
        )

        # Calculate total height needed: image + optional caption
        caption_height = 0.0
        caption_lines: list[str] = []
        if block.caption:
            caption_lines = _wrap_text(block.caption, printable_w, _CHAR_WIDTH_BODY)
            caption_height = _CAPTION_LINE_HEIGHT * len(caption_lines)

        total_height = img_h + caption_height

        # Add block spacing if not at top of page
        spacing = _BLOCK_SPACING if y_cursor > 0 else 0.0

        # Check if image + caption fits on current page (Requirement 7.2)
        if y_cursor + spacing + total_height > printable_h:
            # Move to next page
            current_page = self._new_page(pages)
            y_cursor = 0.0
            spacing = 0.0

        y_cursor += spacing

        # Place image element
        element = RenderedElement(
            x_mm=0.0,
            y_mm=y_cursor,
            width_mm=img_w,
            height_mm=img_h,
            element_type="image",
            image_path=block.path,
            source_block=block,
        )
        current_page.elements.append(element)
        y_cursor += img_h

        # Place caption on same page (Requirement 7.4)
        if block.caption and caption_lines:
            for line_text in caption_lines:
                element = RenderedElement(
                    x_mm=0.0,
                    y_mm=y_cursor,
                    width_mm=printable_w,
                    height_mm=_CAPTION_LINE_HEIGHT,
                    element_type="caption",
                    text=line_text,
                    source_block=block,
                )
                current_page.elements.append(element)
                y_cursor += _CAPTION_LINE_HEIGHT

        return y_cursor

    def _layout_empty_state(
        self,
        block: EmptyStateBlock,
        pages: list[RenderedPage],
        current_page: RenderedPage,
        y_cursor: float,
        printable_w: float,
        printable_h: float,
        layout: PageLayout,
    ) -> float:
        """Lay out an empty state message."""
        lines = _wrap_text(block.text, printable_w, _CHAR_WIDTH_BODY)

        # Add block spacing if not at top of page
        spacing = _BLOCK_SPACING if y_cursor > 0 else 0.0
        y_cursor += spacing

        for line_text in lines:
            if y_cursor + _EMPTY_STATE_LINE_HEIGHT > printable_h:
                current_page = self._new_page(pages)
                y_cursor = 0.0

            element = RenderedElement(
                x_mm=0.0,
                y_mm=y_cursor,
                width_mm=printable_w,
                height_mm=_EMPTY_STATE_LINE_HEIGHT,
                element_type="empty_state",
                text=line_text,
                source_block=block,
            )
            current_page.elements.append(element)
            y_cursor += _EMPTY_STATE_LINE_HEIGHT

        return y_cursor

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _layout_placeholder(
        self,
        block: ImageBlock,
        pages: list[RenderedPage],
        current_page: RenderedPage,
        y_cursor: float,
        printable_w: float,
        printable_h: float,
    ) -> float:
        """Insert placeholder text for a corrupt/unreadable image."""
        placeholder_text = "Bilden kunde inte laddas"
        lines = _wrap_text(placeholder_text, printable_w, _CHAR_WIDTH_BODY)

        spacing = _BLOCK_SPACING if y_cursor > 0 else 0.0
        y_cursor += spacing

        for line_text in lines:
            if y_cursor + _PARAGRAPH_LINE_HEIGHT > printable_h:
                current_page = self._new_page(pages)
                y_cursor = 0.0

            element = RenderedElement(
                x_mm=0.0,
                y_mm=y_cursor,
                width_mm=printable_w,
                height_mm=_PARAGRAPH_LINE_HEIGHT,
                element_type="paragraph_line",
                text=line_text,
                source_block=block,
            )
            current_page.elements.append(element)
            y_cursor += _PARAGRAPH_LINE_HEIGHT

        return y_cursor

    def _scale_image_to_fit(
        self,
        img_w: float,
        img_h: float,
        printable_w: float,
        printable_h: float,
        caption: str | None,
    ) -> tuple[float, float]:
        """Scale image to fit within printable area, preserving aspect ratio.

        If a caption is present, the available height is reduced to ensure
        caption fits on the same page as the image (Requirement 7.4).
        """
        # Reserve space for caption if present
        available_h = printable_h
        if caption:
            # Estimate caption height (at least one line)
            caption_lines = _wrap_text(caption, printable_w, _CHAR_WIDTH_BODY)
            caption_h = _CAPTION_LINE_HEIGHT * len(caption_lines)
            available_h -= caption_h

        if img_w <= printable_w and img_h <= available_h:
            return (img_w, img_h)

        # Scale proportionally
        scale_w = printable_w / img_w if img_w > printable_w else 1.0
        scale_h = available_h / img_h if img_h > available_h else 1.0
        scale = min(scale_w, scale_h)

        return (img_w * scale, img_h * scale)

    def _new_page(self, pages: list[RenderedPage]) -> RenderedPage:
        """Create a new page and append it to the pages list."""
        new_page = RenderedPage(
            page_number=len(pages) + 1, total_pages=0, elements=[]
        )
        pages.append(new_page)
        return new_page
