"""Property-based tests for the report paginator.

Feature: report-menu
Validates: Requirements 6.3, 7.1, 7.2
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import given, settings, strategies as st
from hypothesis.strategies import DrawFn
from PIL import Image

from slaktbusken.reports.content import (
    EmptyStateBlock,
    HeadingBlock,
    ImageBlock,
    ListBlock,
    ParagraphBlock,
    ReportBlock,
    ReportContent,
)
from slaktbusken.reports.paginator import PAPER_SIZES, ReportPaginator


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Safe text without null bytes — avoids problematic characters in layout
_safe_text = st.text(
    alphabet=st.characters(categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=120,
)


def _word_strategy() -> st.SearchStrategy[str]:
    """Generate a single word (letters/digits, no internal whitespace)."""
    return st.text(
        alphabet=st.characters(categories=("L", "N")),
        min_size=1,
        max_size=15,
    )


def _hyphenated_word_strategy() -> st.SearchStrategy[str]:
    """Generate a hyphenated word like 'twenty-five' or 'south-west-corner'."""
    parts = st.lists(_word_strategy(), min_size=2, max_size=4)
    return parts.map(lambda ps: "-".join(ps))


@st.composite
def paragraph_text_strategy(draw: st.DrawFn) -> str:
    """Generate paragraph text with a mix of plain and hyphenated words."""
    words = draw(
        st.lists(
            st.one_of(_word_strategy(), _hyphenated_word_strategy()),
            min_size=1,
            max_size=80,
        )
    )
    return " ".join(words)


@st.composite
def report_block_strategy(draw: DrawFn) -> ReportBlock:
    """Generate a random ReportBlock (excluding ImageBlock which needs real files)."""
    block_type = draw(st.sampled_from(["heading", "paragraph", "list", "empty_state"]))

    if block_type == "heading":
        text = draw(_safe_text)
        level = draw(st.sampled_from([1, 2, 3]))
        return HeadingBlock(text=text, level=level)
    elif block_type == "paragraph":
        text = draw(_safe_text)
        return ParagraphBlock(text=text)
    elif block_type == "list":
        items = draw(st.lists(_safe_text, min_size=1, max_size=5))
        return ListBlock(items=items)
    else:  # empty_state
        text = draw(_safe_text)
        return EmptyStateBlock(text=text)


# ---------------------------------------------------------------------------
# Property 10: Line breaking at word boundaries
# Feature: report-menu, Property 10: Line breaking at word boundaries
# ---------------------------------------------------------------------------


@given(
    text=paragraph_text_strategy(),
    paper_size=st.sampled_from(list(PAPER_SIZES.keys())),
)
@settings(max_examples=100)
def test_line_breaks_only_at_word_or_hyphen_boundaries(text: str, paper_size: str) -> None:
    """For any paragraph text, when the ReportPaginator breaks it into lines,
    every line break occurs at a whitespace or hyphen boundary. No word is
    split mid-character across lines.

    Validates: Requirements 6.1
    """
    content = ReportContent(title="Test", blocks=[ParagraphBlock(text=text)])
    paginator = ReportPaginator()
    pages = paginator.paginate(content, paper_size)

    # Collect all paragraph_line texts in order across pages
    lines: list[str] = []
    for page in pages:
        for element in page.elements:
            if element.element_type == "paragraph_line" and element.text is not None:
                lines.append(element.text)

    # Verify that every line break occurred at a whitespace or hyphen boundary.
    # The paginator may split at hyphens (keeping the hyphen on the left part),
    # so we need to account for that when reconstructing.
    #
    # Strategy: collect all "tokens" from the output lines. Adjacent lines that
    # were split at a hyphen will have the left line ending with a trailing
    # hyphen-terminated token and the right line starting with the continuation.
    # We rejoin by concatenating tokens where the previous one ends with '-'.
    output_tokens: list[str] = []
    for line in lines:
        output_tokens.extend(line.split())

    # Reconstruct words: merge consecutive tokens where the left ends with '-'
    # (this is how the paginator splits hyphenated words)
    reconstructed_words: list[str] = []
    for token in output_tokens:
        if reconstructed_words and reconstructed_words[-1].endswith("-"):
            # This token continues a hyphenated word from the previous token
            reconstructed_words[-1] = reconstructed_words[-1] + token
        else:
            reconstructed_words.append(token)

    original_words = text.split()

    assert reconstructed_words == original_words, (
        f"Line breaking split words incorrectly.\n"
        f"Original words: {original_words}\n"
        f"Reconstructed words: {reconstructed_words}"
    )


# ---------------------------------------------------------------------------
# Property 11: Block ordering preserved across pages
# Feature: report-menu, Property 11: Block ordering preserved across pages
# ---------------------------------------------------------------------------


@given(
    blocks=st.lists(report_block_strategy(), min_size=1, max_size=20),
    paper_size=st.sampled_from(list(PAPER_SIZES.keys())),
)
@settings(max_examples=100)
def test_block_ordering_preserved_across_pages(
    blocks: list[ReportBlock], paper_size: str
) -> None:
    """For any sequence of ReportBlocks, after pagination the order in which blocks
    appear across all pages SHALL match the original input order.

    Validates: Requirements 6.3
    """
    content = ReportContent(title="Test Report", blocks=blocks)
    paginator = ReportPaginator()
    pages = paginator.paginate(content, paper_size)

    # Collect the sequence of source_block references from all elements
    # across all pages (in page order), remove duplicates while preserving
    # first-occurrence order, and verify this matches the input block order.
    seen_blocks: list[ReportBlock] = []
    seen_ids: set[int] = set()

    for page in pages:
        for element in page.elements:
            block_id = id(element.source_block)
            if block_id not in seen_ids and element.source_block is not None:
                seen_ids.add(block_id)
                seen_blocks.append(element.source_block)

    # The deduplicated order of source blocks must match the input order
    assert seen_blocks == blocks, (
        f"Block ordering not preserved across pages.\n"
        f"Expected {len(blocks)} blocks in input order, "
        f"got {len(seen_blocks)} blocks in output order."
    )


# ---------------------------------------------------------------------------
# Strategy (Property 13)
# ---------------------------------------------------------------------------


@st.composite
def report_content_strategy(draw: DrawFn) -> ReportContent:
    """Generate a ReportContent with a random mix of block types (no images)."""
    blocks = draw(st.lists(report_block_strategy(), min_size=0, max_size=30))
    title = draw(_safe_text)
    return ReportContent(title=title, blocks=blocks)


# ---------------------------------------------------------------------------
# Property 13: Page numbering correctness
# Feature: report-menu, Property 13: Page numbering correctness
# ---------------------------------------------------------------------------


@given(
    content=report_content_strategy(),
    paper_size=st.sampled_from(list(PAPER_SIZES.keys())),
)
@settings(max_examples=100)
def test_page_numbering_correctness(content: ReportContent, paper_size: str) -> None:
    """For any paginated report producing N pages, every RenderedPage SHALL have
    page_number in [1, N] and total_pages equal to N, with page numbers forming
    a consecutive sequence from 1 to N.

    Validates: Requirements 6.5
    """
    paginator = ReportPaginator()
    pages = paginator.paginate(content, paper_size)

    # 1. pages is non-empty (at least 1 page, even for empty content)
    assert len(pages) >= 1, "Pagination must produce at least 1 page"

    N = len(pages)

    # 2. Every page has total_pages == N
    for page in pages:
        assert page.total_pages == N, (
            f"Page {page.page_number} has total_pages={page.total_pages}, expected {N}"
        )

    # 3. page_numbers form exactly the sequence [1, 2, ..., N]
    page_numbers = [page.page_number for page in pages]
    expected_sequence = list(range(1, N + 1))
    assert page_numbers == expected_sequence, (
        f"Page numbers {page_numbers} do not form the expected sequence {expected_sequence}"
    )


# ---------------------------------------------------------------------------
# Property 14: Image fits single page
# Feature: report-menu, Property 14: Image fits single page
# ---------------------------------------------------------------------------

# Module-level temp directory for image files used in hypothesis tests
_IMAGE_TEMP_DIR = tempfile.mkdtemp(prefix="pbt_images_")


def _create_temp_image(width: int, height: int, index: int) -> Path:
    """Create a temporary PNG file with the given dimensions."""
    path = Path(_IMAGE_TEMP_DIR) / f"img_{index}_{width}x{height}.png"
    img = Image.new("RGB", (width, height), color=(128, 128, 128))
    img.save(path, format="PNG")
    return path


@given(
    img_dimensions=st.lists(
        st.tuples(
            st.integers(min_value=1, max_value=5000),
            st.integers(min_value=1, max_value=5000),
        ),
        min_size=1,
        max_size=5,
    ),
    paper_size=st.sampled_from(list(PAPER_SIZES.keys())),
    paragraph_texts=st.lists(
        st.text(
            alphabet=st.characters(categories=("L", "N", "Z")),
            min_size=1,
            max_size=100,
        ),
        min_size=0,
        max_size=3,
    ),
)
@settings(max_examples=100, deadline=None)
def test_image_fits_single_page(
    img_dimensions: list[tuple[int, int]],
    paper_size: str,
    paragraph_texts: list[str],
) -> None:
    """For any image block in a paginated report, the image (including any scaling)
    SHALL be rendered entirely within the bounds of a single page. No image shall
    span two pages.

    Validates: Requirements 7.1, 7.2
    """
    layout = PAPER_SIZES[paper_size]
    printable_w = layout.printable_width
    printable_h = layout.printable_height

    # Build blocks: intersperse paragraphs and images
    blocks = []
    for i, text in enumerate(paragraph_texts):
        blocks.append(ParagraphBlock(text=text))
        # Insert an image after each paragraph if available
        if i < len(img_dimensions):
            w, h = img_dimensions[i]
            img_path = _create_temp_image(w, h, i)
            blocks.append(ImageBlock(path=img_path))

    # Add remaining images that weren't interspersed
    for i in range(len(paragraph_texts), len(img_dimensions)):
        w, h = img_dimensions[i]
        img_path = _create_temp_image(w, h, i)
        blocks.append(ImageBlock(path=img_path))

    content = ReportContent(title="Image Test Report", blocks=blocks)
    paginator = ReportPaginator()
    pages = paginator.paginate(content, paper_size)

    # Check every image element
    for page in pages:
        for element in page.elements:
            if element.element_type == "image":
                # 1. y_mm >= 0 (within page bounds from top)
                assert element.y_mm >= 0, (
                    f"Image y_mm={element.y_mm} is negative (above page bounds)"
                )

                # 2. y_mm + height_mm <= printable_height (within page bounds from bottom)
                assert element.y_mm + element.height_mm <= printable_h + 1e-9, (
                    f"Image exceeds page height: y_mm={element.y_mm} + "
                    f"height_mm={element.height_mm} = {element.y_mm + element.height_mm} > "
                    f"printable_height={printable_h}"
                )

                # 3. width_mm <= printable_width (within page bounds horizontally)
                assert element.width_mm <= printable_w + 1e-9, (
                    f"Image exceeds page width: width_mm={element.width_mm} > "
                    f"printable_width={printable_w}"
                )

    # 4. Each image appears on exactly one page (not split across pages)
    # Since each image is a single RenderedElement on a single page,
    # and we've verified it fits within bounds, it cannot span two pages.
    # But let's also verify no image_path appears on multiple pages.
    image_page_map: dict[str, list[int]] = {}
    for page in pages:
        for element in page.elements:
            if element.element_type == "image" and element.image_path is not None:
                key = str(element.image_path)
                if key not in image_page_map:
                    image_page_map[key] = []
                image_page_map[key].append(page.page_number)

    for img_path_str, page_numbers in image_page_map.items():
        assert len(page_numbers) == 1, (
            f"Image {img_path_str} appears on multiple pages: {page_numbers}"
        )


# ---------------------------------------------------------------------------
# Strategies (Property 12)
# ---------------------------------------------------------------------------


@st.composite
def content_block_strategy(draw: DrawFn) -> ReportBlock:
    """Generate a non-heading content block (ParagraphBlock, ListBlock, or EmptyStateBlock)."""
    block_type = draw(st.sampled_from(["paragraph", "list", "empty_state"]))

    if block_type == "paragraph":
        text = draw(_safe_text)
        return ParagraphBlock(text=text)
    elif block_type == "list":
        items = draw(st.lists(_safe_text, min_size=1, max_size=5))
        return ListBlock(items=items)
    else:  # empty_state
        text = draw(_safe_text)
        return EmptyStateBlock(text=text)


@st.composite
def heading_then_content_strategy(draw: DrawFn) -> list[ReportBlock]:
    """Generate a heading block always followed by at least one content block.

    This ensures the input sequence respects the invariant that every heading
    is followed by content — so the paginator's section-keep-together logic
    should never produce an orphaned heading.
    """
    heading_text = draw(st.text(
        alphabet=st.characters(categories=("L", "N", "Z")),
        min_size=1,
        max_size=60,
    ))
    level = draw(st.sampled_from([1, 2, 3]))
    heading = HeadingBlock(text=heading_text, level=level)

    # At least one content block after the heading
    content_blocks = draw(st.lists(content_block_strategy(), min_size=1, max_size=4))

    return [heading] + content_blocks


@st.composite
def blocks_with_headings_followed_by_content(draw: DrawFn) -> list[ReportBlock]:
    """Generate a sequence of blocks where every heading is followed by at least one content block.

    The sequence is built from groups — each group is either:
    - A heading followed by 1+ content blocks
    - A standalone content block
    """
    num_groups = draw(st.integers(min_value=1, max_value=8))
    blocks: list[ReportBlock] = []

    for _ in range(num_groups):
        is_heading_group = draw(st.booleans())
        if is_heading_group:
            group = draw(heading_then_content_strategy())
            blocks.extend(group)
        else:
            block = draw(content_block_strategy())
            blocks.append(block)

    return blocks


# ---------------------------------------------------------------------------
# Property 12: Section heading never orphaned
# Feature: report-menu, Property 12: Section heading never orphaned
# ---------------------------------------------------------------------------


@given(
    blocks=blocks_with_headings_followed_by_content(),
    paper_size=st.sampled_from(list(PAPER_SIZES.keys())),
)
@settings(max_examples=100)
def test_section_heading_never_orphaned(
    blocks: list[ReportBlock], paper_size: str
) -> None:
    """For any paginated report, no page SHALL end with a section heading as its
    last element unless the heading's content starts on the same page.
    Equivalently: every heading block must be followed by at least one content
    line on the same page.

    Validates: Requirements 6.4
    """
    content = ReportContent(title="Test Report", blocks=blocks)
    paginator = ReportPaginator()
    pages = paginator.paginate(content, paper_size)

    for page in pages:
        elements = page.elements
        if not elements:
            continue

        # Find all heading elements on this page
        for i, element in enumerate(elements):
            if element.element_type == "heading":
                # There must be at least one non-heading element on the same
                # page that appears AFTER this heading (higher y_mm position).
                has_content_after = any(
                    subsequent.element_type != "heading"
                    and subsequent.y_mm > element.y_mm
                    for subsequent in elements[i + 1:]
                )
                assert has_content_after, (
                    f"Page {page.page_number}: heading '{element.text}' at y={element.y_mm}mm "
                    f"is orphaned — no non-heading content follows it on the same page. "
                    f"Elements on page: {[(e.element_type, e.y_mm, e.text) for e in elements]}"
                )


# ---------------------------------------------------------------------------
# Property 15: Image scaling preserves aspect ratio
# Feature: report-menu, Property 15: Image scaling preserves aspect ratio
# ---------------------------------------------------------------------------


@given(
    img_dimensions=st.lists(
        st.tuples(
            st.integers(min_value=200, max_value=5000),
            st.integers(min_value=200, max_value=5000),
        ),
        min_size=1,
        max_size=5,
    ),
    paper_size=st.sampled_from(list(PAPER_SIZES.keys())),
)
@settings(max_examples=100, deadline=None)
def test_image_scaling_preserves_aspect_ratio(
    img_dimensions: list[tuple[int, int]],
    paper_size: str,
) -> None:
    """For any image whose original dimensions exceed the printable area of the
    selected Paper_Size, the scaled dimensions SHALL fit within the printable area
    AND the ratio width/height SHALL equal the original aspect ratio (within
    floating-point tolerance).

    Validates: Requirements 7.3
    """
    from slaktbusken.reports.paginator import _PX_TO_MM

    layout = PAPER_SIZES[paper_size]
    printable_w = layout.printable_width
    printable_h = layout.printable_height

    # Build image blocks
    blocks: list[ReportBlock] = []
    for i, (w_px, h_px) in enumerate(img_dimensions):
        img_path = _create_temp_image(w_px, h_px, 1000 + i)
        blocks.append(ImageBlock(path=img_path))

    content = ReportContent(title="Aspect Ratio Test", blocks=blocks)
    paginator = ReportPaginator()
    pages = paginator.paginate(content, paper_size)

    # Check every image element
    img_idx = 0
    for page in pages:
        for element in page.elements:
            if element.element_type == "image":
                assert img_idx < len(img_dimensions), "More image elements than expected"
                w_px, h_px = img_dimensions[img_idx]
                img_idx += 1

                # Original dimensions in mm
                original_w_mm = w_px * _PX_TO_MM
                original_h_mm = h_px * _PX_TO_MM

                # Determine available height (account for caption if present)
                # Since we didn't add captions here, available_h = printable_h
                available_h = printable_h

                # Only check aspect ratio if the original image exceeded the
                # printable area (i.e. it was actually scaled down)
                if original_w_mm > printable_w or original_h_mm > available_h:
                    # 1. Rendered width fits within printable width
                    assert element.width_mm <= printable_w + 1e-9, (
                        f"Scaled image width {element.width_mm}mm exceeds "
                        f"printable width {printable_w}mm"
                    )

                    # 2. Rendered height fits within printable height
                    assert element.height_mm <= available_h + 1e-9, (
                        f"Scaled image height {element.height_mm}mm exceeds "
                        f"printable height {available_h}mm"
                    )

                    # 3. Aspect ratio is preserved (within tolerance)
                    original_ratio = original_w_mm / original_h_mm
                    rendered_ratio = element.width_mm / element.height_mm
                    assert abs(rendered_ratio - original_ratio) < 1e-3, (
                        f"Aspect ratio not preserved: original={original_ratio:.6f}, "
                        f"rendered={rendered_ratio:.6f}, "
                        f"diff={abs(rendered_ratio - original_ratio):.6f}"
                    )


# ---------------------------------------------------------------------------
# Property 16: Caption on same page as image
# Feature: report-menu, Property 16: Caption on same page as image
# ---------------------------------------------------------------------------


@given(
    img_dimensions=st.lists(
        st.tuples(
            st.integers(min_value=10, max_value=3000),
            st.integers(min_value=10, max_value=3000),
        ),
        min_size=1,
        max_size=5,
    ),
    captions=st.lists(
        st.text(
            alphabet=st.characters(categories=("L", "N", "Z")),
            min_size=1,
            max_size=80,
        ),
        min_size=1,
        max_size=5,
    ),
    paper_size=st.sampled_from(list(PAPER_SIZES.keys())),
    paragraph_texts=st.lists(
        st.text(
            alphabet=st.characters(categories=("L", "N", "Z")),
            min_size=1,
            max_size=100,
        ),
        min_size=0,
        max_size=5,
    ),
)
@settings(max_examples=100, deadline=None)
def test_caption_on_same_page_as_image(
    img_dimensions: list[tuple[int, int]],
    captions: list[str],
    paper_size: str,
    paragraph_texts: list[str],
) -> None:
    """For any image block with a caption, the caption and the image SHALL appear
    on the same RenderedPage.

    Validates: Requirements 7.4
    """
    # Build blocks: intersperse paragraph blocks and image blocks with captions
    blocks: list[ReportBlock] = []
    num_images = min(len(img_dimensions), len(captions))

    for i, text in enumerate(paragraph_texts):
        blocks.append(ParagraphBlock(text=text))

    for i in range(num_images):
        w, h = img_dimensions[i]
        img_path = _create_temp_image(w, h, 1000 + i)
        blocks.append(ImageBlock(path=img_path, caption=captions[i]))

    content = ReportContent(title="Caption Test Report", blocks=blocks)
    paginator = ReportPaginator()
    pages = paginator.paginate(content, paper_size)

    # For each page, find image elements and caption elements.
    # For each image element, verify that all caption elements sharing the same
    # source_block are on the SAME page.
    for page in pages:
        for element in page.elements:
            if element.element_type == "image" and element.source_block is not None:
                source = element.source_block
                # Find all pages that contain caption elements for this source_block
                caption_pages: set[int] = set()
                for p in pages:
                    for el in p.elements:
                        if el.element_type == "caption" and el.source_block is source:
                            caption_pages.add(p.page_number)

                # All captions for this image must be on the same page as the image
                assert caption_pages <= {page.page_number}, (
                    f"Image on page {page.page_number} has captions on pages "
                    f"{caption_pages}. Caption must be on the same page as its image."
                )

    # Also verify that every image block with a caption actually produced
    # both image and caption elements on the same page
    for i in range(num_images):
        source_block = blocks[len(paragraph_texts) + i]
        image_pages: set[int] = set()
        caption_pages_for_block: set[int] = set()
        for page in pages:
            for element in page.elements:
                if element.source_block is source_block:
                    if element.element_type == "image":
                        image_pages.add(page.page_number)
                    elif element.element_type == "caption":
                        caption_pages_for_block.add(page.page_number)

        if image_pages and caption_pages_for_block:
            assert image_pages == caption_pages_for_block, (
                f"ImageBlock {i} has image on page(s) {image_pages} but caption on "
                f"page(s) {caption_pages_for_block}. They must be on the same page."
            )
