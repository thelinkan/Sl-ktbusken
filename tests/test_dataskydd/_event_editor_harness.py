"""Drives the real ``EventEditor`` offscreen with its citation prompt intercepted."""

from __future__ import annotations

import os
from typing import Callable, Mapping, Optional

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from slaktbusken.model.event import Event
from slaktbusken.model.event_citations import CitationContext
from slaktbusken.model.project import ProjectData
from slaktbusken.ui.editors.event_assembler import CitationChoice, PromptNeed


def open_and_save(
    project: ProjectData,
    event: Event,
    edit: Optional[Callable] = None,
    answers: Optional[Mapping[CitationContext, CitationChoice]] = None,
) -> tuple[Optional[Event], list[CitationContext]]:
    """Open ``event`` in an editor, apply ``edit``, save.

    Returns the saved event (None when the save was aborted) and the contexts
    of the prompts that were asked, in order. An unanswered prompt gets the
    default answer "Flytta till händelsen".
    """
    from slaktbusken.ui.editors.event_editor import EventEditor

    editor = EventEditor(project, event=event)
    asked: list[CitationContext] = []

    def ask(need: PromptNeed) -> CitationChoice:
        asked.append(need.context)
        return (answers or {}).get(need.context, CitationChoice.MOVE_TO_EVENT)

    editor._ask_citation_choice = ask  # type: ignore[method-assign]
    if edit is not None:
        edit(editor)
    editor._on_save()
    return editor.saved_event, asked
