"""Report generation package for Släktbusken.

Exposes the report content data model and generator service for convenient imports.
"""

from __future__ import annotations

from slaktbusken.reports.content import (
    EmptyStateBlock,
    HeadingBlock,
    ImageBlock,
    ListBlock,
    ParagraphBlock,
    ReportBlock,
    ReportContent,
)
from slaktbusken.reports.generator import ReportGeneratorService

__all__ = [
    "EmptyStateBlock",
    "HeadingBlock",
    "ImageBlock",
    "ListBlock",
    "ParagraphBlock",
    "ReportBlock",
    "ReportContent",
    "ReportGeneratorService",
]
