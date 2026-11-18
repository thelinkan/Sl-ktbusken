"""Tests of the pure event assembler and of the editors' save paths (task 9.4).

Covers Requirements 6 (date citations), 7 (place citations), 8 (from_place),
12.3, 12.6, 15.5 and 16 (unparsed dates). B6, B7 and B8 are reproduced
headlessly: first on the assembler, then through the real ``EventEditor``
with the citation prompt intercepted at ``_ask_citation_choice``.
"""

from __future__ import annotations

import copy
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from hypothesis import given, strategies as st

from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef, SourceRef
from slaktbusken.model.event_citations import CitationContext, event_citations
from slaktbusken.model.residence import Endpoint, ResidenceFact
from slaktbusken.ui.editors.event_assembler import (
    CitationChoice,
    CitationRow,
    DateFormState,
    PromptNeed,
    append_moved,
    assemble_event,
    prompts_needed,
)

from tests.test_dataskydd.strategies_events import (
    PLACE_IDS,
    distinct_ref_keys,
    event_st,
    event_with_all_contexts,
    form_from_event,
    make_project,
    ref_key,
    refs_in_context,
    unparsed_event,
)

pytestmark = pytest.mark.mandatory_integrity

C = CitationContext
Ch = CitationChoice


def _contexts(needs: list[PromptNeed]) -> list[CitationContext]:
    return [n.context for n in needs]


def _drop_rows(form, context: CitationContext) -> None:
    form.citation_rows = [r for r in form.citation_rows if r.context != context]


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


@given(event=event_st())
def test_dp_property_3_open_save_without_edits_is_identity(event: Event) -> None:
    """**Validates: Requirements 7.2, 7.3, 8.1, 8.3, 12.3, 16.2**"""
    before = copy.deepcopy(event)
    form = form_from_event(event)
    assert prompts_needed(event, form) == []
    assert assemble_event(event, form, {}) == before
    assert event == before  # the base is never mutated


@st.composite
def _citation_change(draw):
    """An event with citations in date, place and from-place and one change."""
    event = draw(event_st(require_date=True))
    event.place = draw(st.builds(PlaceRef, place_id=st.sampled_from(PLACE_IDS[:2]),
                                 source_refs=st.lists(_ref(), min_size=1, max_size=3)))
    event.from_place = draw(st.builds(PlaceRef, place_id=st.sampled_from(PLACE_IDS[:2]),
                                      source_refs=st.lists(_ref(), min_size=1, max_size=3)))
    event.date.source_refs = draw(st.lists(_ref(), min_size=1, max_size=3))
    context = draw(st.sampled_from([C.DATE, C.PLACE, C.FROM_PLACE]))
    removal = context == C.DATE or draw(st.booleans())
    return event, context, removal


def _ref():
    from tests.test_dataskydd.strategies_events import source_ref_st

    return source_ref_st


@given(data=_citation_change(), pick=st.integers(0, 3))
def test_dp_property_4_citations_follow_the_chosen_choice(data, pick) -> None:
    """**Validates: Requirements 12.1, 12.2, 14.1, 14.7, 16.5, 19.1, 22.1**"""
    event, context, removal = data
    project = make_project()
    sources_before = copy.deepcopy(project.sources)
    base = copy.deepcopy(event)
    form = form_from_event(event)
    new_id = None
    if context == C.DATE:
        form.date = DateFormState()
    elif context == C.PLACE:
        if removal:
            form.place_id = None
        else:
            new_id = "place_4"
            form.place_id = new_id
    else:
        if removal:
            form.from_place_id = None
        else:
            new_id = "place_4"
            form.from_place_id = new_id

    needs = prompts_needed(event, form)
    assert _contexts(needs) == [context]
    allowed = needs[0].allowed
    assert (Ch.KEEP_FOR_NEW_PLACE in allowed) == (not removal)
    choice = allowed[pick % len(allowed)]

    affected = [copy.deepcopy(r) for r in refs_in_context(event, context)]
    others_before = {
        c: refs_in_context(event, c) for c in (C.EVENT, C.DATE, C.PLACE, C.FROM_PLACE)
    }

    if choice == Ch.CANCEL:
        with pytest.raises(ValueError):
            assemble_event(event, form, {context: choice})
        assert event == base
        assert project.sources == sources_before
        return

    result = assemble_event(event, form, {context: choice})
    assert event == base  # base never mutated
    assert project.sources == sources_before

    if choice == Ch.MOVE_TO_EVENT:
        assert distinct_ref_keys(result) == distinct_ref_keys(base)
        n = len(base.source_refs)
        assert [ref_key(r) for r in result.source_refs[:n]] == [
            ref_key(r) for r in base.source_refs
        ]
        tail = result.source_refs[n:]
        seen = [ref_key(r) for r in result.source_refs[:n]]
        for ref in tail:
            assert ref_key(ref) in {ref_key(a) for a in affected}
            assert ref_key(ref) not in seen
            seen.append(ref_key(ref))
        # every moved reference is present at event level afterwards
        assert {ref_key(a) for a in affected} <= {ref_key(r) for r in result.source_refs}
    elif choice == Ch.KEEP_FOR_NEW_PLACE:
        ref = result.place if context == C.PLACE else result.from_place
        assert ref is not None and ref.place_id == new_id
        assert [ref_key(r) for r in ref.source_refs] == [ref_key(r) for r in affected]
        assert [ref_key(r) for r in result.source_refs] == [
            ref_key(r) for r in base.source_refs
        ]
    else:  # REMOVE_LINKS
        assert refs_in_context(result, context) == []
        assert [ref_key(r) for r in result.source_refs] == [
            ref_key(r) for r in base.source_refs
        ]
    # Contexts that were not affected keep their references
    for other in (C.EVENT, C.DATE, C.PLACE, C.FROM_PLACE):
        if other == context or (other == C.EVENT and choice == Ch.MOVE_TO_EVENT):
            continue
        assert [ref_key(r) for r in refs_in_context(result, other)] == [
            ref_key(r) for r in others_before[other]
        ]


@given(event=event_st(with_original_text=True, require_date=True), data=st.data())
def test_dp_property_13_original_text_survives_unrelated_edits(event: Event, data) -> None:
    """**Validates: Requirements 16.2, 16.3**"""
    assert event.date is not None and event.date.original_text
    base = copy.deepcopy(event)

    # Edits outside the date, with the date fields as loaded
    form = form_from_event(event)
    form.type = data.draw(st.sampled_from(["birth", "death", "marriage"]))
    form.cause_of_death = data.draw(st.sampled_from([None, "Ålder"]))
    form.media_ids = data.draw(st.lists(st.sampled_from(["m1", "m2"]), max_size=2, unique=True))
    result = assemble_event(event, form, {})
    assert result.date == base.date

    # A change of the date fields drops original_text
    new_text = data.draw(st.sampled_from(["1851-02-03", "1900", "1777-12"]))
    form2 = form_from_event(event)
    form2.date = DateFormState(text=new_text, qualifier="exact")
    if form2.date.same_as(DateFormState.from_date(base.date)):
        return
    result2 = assemble_event(event, form2, {})
    assert result2.date is not None
    assert result2.date.original_text is None
    assert result2.date.value == new_text


# ---------------------------------------------------------------------------
# Date citations (Requirement 6)
# ---------------------------------------------------------------------------


def test_empty_date_keeps_citations_as_event_level() -> None:
    """B6: citations of an event without a date stay on the event."""
    event = Event(
        id="e", type="birth", participants=[Participant("person_1", "huvudperson")],
        source_refs=[SourceRef("src_1", "primary", "x")],
    )
    form = form_from_event(event)
    assert prompts_needed(event, form) == []
    result = assemble_event(event, form, {})
    assert result.date is None
    assert result.source_refs == event.source_refs


def test_clear_date_prompt_move_preserves_all_fields() -> None:
    event = event_with_all_contexts()
    base = copy.deepcopy(event)
    form = form_from_event(event)
    form.date = DateFormState()
    needs = prompts_needed(event, form)
    assert _contexts(needs) == [C.DATE]
    assert needs[0].allowed == (Ch.MOVE_TO_EVENT, Ch.REMOVE_LINKS, Ch.CANCEL)
    result = assemble_event(event, form, {C.DATE: Ch.MOVE_TO_EVENT})
    assert result.date is None
    assert [ref_key(r) for r in result.source_refs] == [
        ref_key(r) for r in base.source_refs + base.date.source_refs
    ]
    assert result.place == base.place and result.from_place == base.from_place
    assert result.participants == base.participants and result.type == base.type


def test_clear_date_prompt_remove_keeps_source_record() -> None:
    project = make_project()
    event = event_with_all_contexts()
    form = form_from_event(event)
    form.date = DateFormState()
    result = assemble_event(event, form, {C.DATE: Ch.REMOVE_LINKS})
    assert result.date is None
    assert result.source_refs == event.source_refs
    assert {s.id for s in project.sources} >= {"src_1"}


def test_clear_date_prompt_cancel_preserves_state() -> None:
    event = event_with_all_contexts()
    base = copy.deepcopy(event)
    form = form_from_event(event)
    form.date = DateFormState()
    with pytest.raises(ValueError):
        assemble_event(event, form, {C.DATE: Ch.CANCEL})
    assert event == base


def test_move_dedupes_only_exact_identical_references() -> None:
    ref = SourceRef("src_1", "primary", "n", ["a"])
    target = [copy.deepcopy(ref), copy.deepcopy(ref)]  # existing duplicates stay
    out = append_moved(target, [copy.deepcopy(ref), SourceRef("src_2", "primary")])
    assert [ref_key(r) for r in out] == [
        ref_key(ref), ref_key(ref), ("src_2", "primary", "", ())
    ]
    # Two identical moved references land once
    assert len(append_moved([], [copy.deepcopy(ref), copy.deepcopy(ref)])) == 1


def test_move_keeps_distinct_citation_details() -> None:
    base = SourceRef("src_1", "primary", "n", ["a"])
    variants = [
        SourceRef("src_1", "secondary", "n", ["a"]),
        SourceRef("src_1", "primary", "annan", ["a"]),
        SourceRef("src_1", "primary", "n", ["b"]),
        SourceRef("src_1", "primary", "n", ["a", "b"]),
        SourceRef("src_2", "primary", "n", ["a"]),
    ]
    out = append_moved([base], variants)
    assert len(out) == 1 + len(variants)


# ---------------------------------------------------------------------------
# Place citations (Requirement 7)
# ---------------------------------------------------------------------------


def test_place_citations_survive_save() -> None:
    """B7: place citations are kept when the place is unchanged."""
    event = event_with_all_contexts()
    form = form_from_event(event)
    form.type = "death"
    result = assemble_event(event, form, {})
    assert result.place == event.place
    assert refs_in_context(result, C.PLACE) == event.place.source_refs


def test_open_save_unchanged_event_no_prompt() -> None:
    event = event_with_all_contexts()
    form = form_from_event(event)
    assert prompts_needed(event, form) == []
    assert assemble_event(event, form, {}) == event


def test_remove_place_prompt_move_to_event() -> None:
    event = event_with_all_contexts()
    form = form_from_event(event)
    form.place_id = None
    needs = prompts_needed(event, form)
    assert _contexts(needs) == [C.PLACE] and needs[0].kind == "removed"
    assert needs[0].allowed == (Ch.MOVE_TO_EVENT, Ch.REMOVE_LINKS, Ch.CANCEL)
    result = assemble_event(event, form, {C.PLACE: Ch.MOVE_TO_EVENT})
    assert result.place is None
    assert ref_key(event.place.source_refs[0]) in {ref_key(r) for r in result.source_refs}


def test_remove_place_prompt_remove_links() -> None:
    event = event_with_all_contexts()
    form = form_from_event(event)
    form.place_id = None
    result = assemble_event(event, form, {C.PLACE: Ch.REMOVE_LINKS})
    assert result.place is None
    assert result.source_refs == event.source_refs


def test_remove_place_prompt_cancel_preserves_state() -> None:
    event = event_with_all_contexts()
    base = copy.deepcopy(event)
    form = form_from_event(event)
    form.place_id = None
    with pytest.raises(ValueError):
        assemble_event(event, form, {C.PLACE: Ch.CANCEL})
    assert event == base


def test_remove_from_place_prompt_move_to_event() -> None:
    event = event_with_all_contexts()
    form = form_from_event(event)
    form.from_place_id = None
    needs = prompts_needed(event, form)
    assert _contexts(needs) == [C.FROM_PLACE]
    result = assemble_event(event, form, {C.FROM_PLACE: Ch.MOVE_TO_EVENT})
    assert result.from_place is None
    assert ref_key(event.from_place.source_refs[0]) in {ref_key(r) for r in result.source_refs}


def _changed_place_case():
    event = event_with_all_contexts()
    form = form_from_event(event)
    form.place_id = "place_3"
    return event, form


def test_change_place_prompt_keep_for_new_place() -> None:
    event, form = _changed_place_case()
    needs = prompts_needed(event, form)
    assert _contexts(needs) == [C.PLACE] and needs[0].kind == "changed"
    result = assemble_event(event, form, {C.PLACE: Ch.KEEP_FOR_NEW_PLACE})
    assert result.place == PlaceRef("place_3", copy.deepcopy(event.place.source_refs))
    assert result.source_refs == event.source_refs


def test_change_place_prompt_move_to_event() -> None:
    event, form = _changed_place_case()
    result = assemble_event(event, form, {C.PLACE: Ch.MOVE_TO_EVENT})
    assert result.place == PlaceRef("place_3", [])
    assert ref_key(event.place.source_refs[0]) in {ref_key(r) for r in result.source_refs}


def test_change_place_prompt_remove_links() -> None:
    event, form = _changed_place_case()
    result = assemble_event(event, form, {C.PLACE: Ch.REMOVE_LINKS})
    assert result.place == PlaceRef("place_3", [])
    assert result.source_refs == event.source_refs


def test_change_place_prompt_cancel_preserves_state() -> None:
    event, form = _changed_place_case()
    base = copy.deepcopy(event)
    with pytest.raises(ValueError):
        assemble_event(event, form, {C.PLACE: Ch.CANCEL})
    assert event == base


def test_change_from_place_prompt_choices() -> None:
    event = event_with_all_contexts()
    form = form_from_event(event)
    form.from_place_id = "place_4"
    needs = prompts_needed(event, form)
    assert _contexts(needs) == [C.FROM_PLACE]
    assert set(needs[0].allowed) == {
        Ch.KEEP_FOR_NEW_PLACE, Ch.MOVE_TO_EVENT, Ch.REMOVE_LINKS, Ch.CANCEL
    }
    kept = assemble_event(event, form, {C.FROM_PLACE: Ch.KEEP_FOR_NEW_PLACE})
    assert kept.from_place == PlaceRef("place_4", copy.deepcopy(event.from_place.source_refs))
    # Default (no answer) moves to the event and loses nothing
    default = assemble_event(event, form, {})
    assert default.from_place == PlaceRef("place_4", [])
    assert distinct_ref_keys(default) == distinct_ref_keys(event)


def test_change_place_without_citations_no_prompt() -> None:
    event = event_with_all_contexts()
    event.place.source_refs = []
    form = form_from_event(event)
    form.place_id = "place_3"
    assert prompts_needed(event, form) == []
    assert assemble_event(event, form, {}).place == PlaceRef("place_3", [])


def test_multiple_prompts_cancel_changes_nothing() -> None:
    event = event_with_all_contexts()
    base = copy.deepcopy(event)
    form = form_from_event(event)
    form.date = DateFormState()
    form.place_id = "place_3"
    form.from_place_id = None
    assert _contexts(prompts_needed(event, form)) == [C.DATE, C.PLACE, C.FROM_PLACE]
    with pytest.raises(ValueError):
        assemble_event(
            event, form,
            {C.DATE: Ch.MOVE_TO_EVENT, C.PLACE: Ch.CANCEL, C.FROM_PLACE: Ch.REMOVE_LINKS},
        )
    assert event == base


# ---------------------------------------------------------------------------
# from_place (Requirement 8)
# ---------------------------------------------------------------------------


def test_open_save_without_edit_is_identity_for_flytt() -> None:
    event = event_with_all_contexts()
    assert assemble_event(event, form_from_event(event), {}) == event


def test_clear_from_place_stores_none() -> None:
    event = event_with_all_contexts()
    event.from_place.source_refs = []
    form = form_from_event(event)
    form.from_place_id = None
    assert prompts_needed(event, form) == []
    assert assemble_event(event, form, {}).from_place is None


def test_from_place_citations_keep_separate_context() -> None:
    shared = SourceRef("src_1", "primary", "samma")
    event = event_with_all_contexts(place_id="place_1", from_place_id="place_1")
    event.place.source_refs = [copy.deepcopy(shared)]
    event.from_place.source_refs = [copy.deepcopy(shared)]
    result = assemble_event(event, form_from_event(event), {})
    assert [ref_key(r) for r in refs_in_context(result, C.PLACE)] == [ref_key(shared)]
    assert [ref_key(r) for r in refs_in_context(result, C.FROM_PLACE)] == [ref_key(shared)]
    assert [c.context for c in event_citations(result)].count(C.FROM_PLACE) == 1


def test_type_change_away_from_flytt_keeps_from_place() -> None:
    event = event_with_all_contexts()
    form = form_from_event(event)
    form.type = "birth"
    assert prompts_needed(event, form) == []
    result = assemble_event(event, form, {})
    assert result.type == "birth"
    assert result.from_place == event.from_place


def test_event_editor_save_preserves_from_place(qapp) -> None:
    """B8 through the real editor: from_place, its citations and origin survive."""
    from tests.test_dataskydd._event_editor_harness import open_and_save

    event = event_with_all_contexts()
    from slaktbusken.model.record_origin import RecordOrigin

    event.origin = RecordOrigin("INDI", "person_1", "@I1@", "EVEN:flytt", 0, "abc")
    base = copy.deepcopy(event)
    saved, asked = open_and_save(make_project(), event)
    assert asked == []
    assert saved == base
    assert saved.from_place == base.from_place and saved.origin == base.origin


def test_residence_editor_save_preserves_from_place(qapp) -> None:
    """The residence editor sets place and from_place and never edits flytt events."""
    from slaktbusken.ui.editors.residence_editor import ResidenceEditor

    data = make_project()
    from slaktbusken.model.person import Name, Person

    data.persons.append(Person(id="person_1", sex="M", names=[Name(type="birth", given="A", surname="B")]))
    existing_flytt = event_with_all_contexts()
    existing_flytt.id = "event_existing"
    data.events.append(existing_flytt)
    snapshot = copy.deepcopy(existing_flytt)
    earlier = ResidenceFact(
        id="res_1", person_id="person_1", place_id="place_1",
        start=Endpoint(earliest="1800", latest="1800"),
        end=Endpoint(earliest="1850-05-01", latest="1850-05-01"),
    )
    later = ResidenceFact(
        id="res_2", person_id="person_1", place_id="place_2",
        start=Endpoint(earliest="1850-05-01", latest="1850-05-01"),
        end=Endpoint(),
    )
    data.residences = [earlier, later]
    editor = ResidenceEditor(data, residence=data.residences[0], person_id="person_1")
    editor._on_create_flytt()
    created = [e for e in data.events if e.id != "event_existing"]
    assert len(created) == 1
    assert created[0].type == "flytt"
    assert created[0].place == PlaceRef("place_2")
    assert created[0].from_place == PlaceRef("place_1")
    assert data.events[0] == snapshot


# ---------------------------------------------------------------------------
# Unparsed dates (Requirement 16)
# ---------------------------------------------------------------------------


def test_unparsed_date_preserved_by_unrelated_edit() -> None:
    event = unparsed_event()
    form = form_from_event(event)
    form.type = "death"
    form.cause_of_death = "Ålder"
    result = assemble_event(event, form, {})
    assert result.date == event.date


def test_unparsed_date_replaced_only_by_explicit_new_date() -> None:
    event = unparsed_event()
    form = form_from_event(event)
    assert assemble_event(event, form, {}).date == event.date
    form.date = DateFormState(text="1850-06-24", qualifier="exact")
    result = assemble_event(event, form, {})
    assert result.date.value == "1850-06-24" and result.date.qualifier == "exact"
    assert result.date.original_text is None
    # citations on the date stay on the date
    assert refs_in_context(result, C.DATE) == event.date.source_refs
    assert prompts_needed(event, form) == []


def test_original_text_cleared_when_date_changed() -> None:
    event = event_with_all_contexts()
    event.date.original_text = "4 mars 1850"
    form = form_from_event(event)
    form.type = "death"
    assert assemble_event(event, form, {}).date.original_text == "4 mars 1850"
    form.date = DateFormState(text="1850-03-05", qualifier="exact")
    assert assemble_event(event, form, {}).date.original_text is None


def test_unparsed_date_save_reopen_round_trip(qapp) -> None:
    from tests.test_dataskydd._event_editor_harness import open_and_save

    event = unparsed_event()
    base = copy.deepcopy(event)
    saved, asked = open_and_save(make_project(), event)
    assert asked == [] and saved == base
    again, asked = open_and_save(make_project(), saved)
    assert asked == [] and again == base


def test_editor_add_citation_defaults_to_event_level(qapp) -> None:
    from PySide6.QtCore import Qt

    from slaktbusken.ui.editors.event_editor import EventEditor

    editor = EventEditor(make_project(), event=event_with_all_contexts())
    n = editor._ui.sources_table.rowCount()
    editor._ui.source_combo.setCurrentIndex(editor._ui.source_combo.findData("src_2"))
    editor._on_add_source()
    assert editor._ui.sources_table.rowCount() == n + 1
    assert editor._row_context(n) == C.EVENT
    assert editor._collect_citation_rows()[n].context == C.EVENT
    assert editor._ui.sources_table.item(n, 0).data(Qt.ItemDataRole.UserRole) == "src_2"


def test_invalid_day_rejected_in_editor(qapp) -> None:
    from slaktbusken.ui.editors.event_editor import EventEditor

    event = event_with_all_contexts()
    editor = EventEditor(make_project(), event=event)
    editor._ui.date_value_input.setText("1851-02-30")
    editor._on_save()
    assert editor.saved_event is None
    assert editor._ui.status_label.text()
    # The pure path rejects it the same way
    form = form_from_event(event)
    form.date = DateFormState(text="1851-02-30", qualifier="exact")
    with pytest.raises(ValueError):
        assemble_event(event, form, {})


# ---------------------------------------------------------------------------
# Editor-level prompts and headless reproductions of B6, B7 and B8
# ---------------------------------------------------------------------------


def test_place_citations_survive_save_in_editor_b7(qapp) -> None:
    from tests.test_dataskydd._event_editor_harness import open_and_save

    event = event_with_all_contexts()
    saved, asked = open_and_save(make_project(), event)
    assert asked == []
    assert saved.place.source_refs == event.place.source_refs  # B7


def test_clearing_date_in_editor_keeps_date_citations_b6(qapp) -> None:
    from tests.test_dataskydd._event_editor_harness import open_and_save

    event = event_with_all_contexts()
    saved, asked = open_and_save(
        make_project(), event,
        edit=lambda ed: ed._ui.date_value_input.setText(""),
        answers={C.DATE: Ch.MOVE_TO_EVENT},
    )
    assert asked == [C.DATE]
    assert saved.date is None
    assert ref_key(event.date.source_refs[0]) in {ref_key(r) for r in saved.source_refs}  # B6


@pytest.mark.parametrize("choice", list(Ch))
def test_no_prompt_choice_deletes_a_source_record(qapp, choice) -> None:
    from tests.test_dataskydd._event_editor_harness import open_and_save

    project = make_project()
    sources = copy.deepcopy(project.sources)
    event = event_with_all_contexts()

    def edit(ed) -> None:
        ed._ui.date_value_input.setText("")
        ed._ui.place_combo.setCurrentIndex(ed._ui.place_combo.findData("place_3"))
        ed._from_place_combo.setCurrentIndex(0)

    answers = {C.DATE: choice, C.PLACE: choice, C.FROM_PLACE: choice}
    if choice == Ch.KEEP_FOR_NEW_PLACE:
        answers[C.DATE] = Ch.MOVE_TO_EVENT
        answers[C.FROM_PLACE] = Ch.MOVE_TO_EVENT
    saved, _ = open_and_save(project, event, edit=edit, answers=answers)
    assert project.sources == sources


def test_multiple_prompts_cancel_in_editor_changes_nothing(qapp) -> None:
    from tests.test_dataskydd._event_editor_harness import open_and_save

    project = make_project()
    event = event_with_all_contexts()
    base = copy.deepcopy(event)

    def edit(ed) -> None:
        ed._ui.date_value_input.setText("")
        ed._ui.place_combo.setCurrentIndex(ed._ui.place_combo.findData("place_3"))

    saved, asked = open_and_save(
        project, event, edit=edit,
        answers={C.DATE: Ch.MOVE_TO_EVENT, C.PLACE: Ch.CANCEL},
    )
    assert saved is None
    assert asked == [C.DATE, C.PLACE]
    assert event == base


def test_clear_from_place_in_editor_stores_none(qapp) -> None:
    from tests.test_dataskydd._event_editor_harness import open_and_save

    event = event_with_all_contexts()
    saved, asked = open_and_save(
        make_project(), event,
        edit=lambda ed: ed._from_place_combo.setCurrentIndex(0),
        answers={C.FROM_PLACE: Ch.REMOVE_LINKS},
    )
    assert asked == [C.FROM_PLACE]
    assert saved.from_place is None
