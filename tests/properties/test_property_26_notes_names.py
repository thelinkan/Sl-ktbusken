"""Property 26: Notes and names.

**Validates: Requirements 21.6, 21.8, 21.9, 21.10**
"""

from __future__ import annotations

from hypothesis import given, strategies as st

from slaktbusken.model.person import Name
from slaktbusken.services.merge_rules import (
    NOTES_CONCATENATE,
    concatenate_notes,
    name_identity,
    notes_separator,
    resolve_notes,
    union_names,
)

# Small pools make collisions (identical identities, same strings with another
# type or event id) frequent.
_TEXT = st.sampled_from(["Anna", "Erik", "Lind", "Berg", "Anna*", "Å", ""])
_TYPES = st.sampled_from(["birth", "married", "alias"])
_EVENT_IDS = st.sampled_from([None, "ev_1", "ev_2"])

names = st.builds(Name, type=_TYPES, given=_TEXT, surname=_TEXT, event_id=_EVENT_IDS)
name_lists = st.lists(names, max_size=6)

note_texts = st.text(min_size=1, max_size=60).filter(lambda s: s.strip())
person_ids = st.text(alphabet="abcdefghij0123456789_", min_size=1, max_size=10)
display_names = st.text(min_size=1, max_size=20)


@given(note_texts, note_texts, display_names, person_ids)
def test_concatenated_notes_contain_both_texts_and_separator(a, b, name, pid):
    if a.strip() == b.strip():
        return  # identical notes are kept once (not a concatenation case)
    result = concatenate_notes(a, b, name, pid)
    separator = notes_separator(name, pid)
    assert a in result
    assert b in result
    assert separator in result
    # Survivor text first, then separator, then the other text.
    assert result == f"{a}\n\n{separator}\n\n{b}"
    assert resolve_notes(a, b, name, pid, NOTES_CONCATENATE) == result


@given(note_texts, st.sampled_from(["", " ", "\n\t "]), display_names, person_ids)
def test_blank_note_never_overwrites_or_adds_separator(a, blank, name, pid):
    assert concatenate_notes(a, blank, name, pid) == a
    assert concatenate_notes(blank, a, name, pid) == a


@given(name_lists, name_lists, st.data())
def test_name_union_and_primary_first(survivor_names, other_names, data):
    before_s = [(n.type, n.given, n.surname, n.event_id) for n in survivor_names]
    before_o = [(n.type, n.given, n.surname, n.event_id) for n in other_names]

    # Expected: first-seen distinct identities, survivor's names first.
    expected: list[tuple] = []
    for n in list(survivor_names) + list(other_names):
        identity = name_identity(n)
        if identity not in expected:
            expected.append(identity)

    # Without a primary: every distinct name exactly once, original order.
    plain = union_names(survivor_names, other_names)
    assert [name_identity(n) for n in plain] == expected

    # Same strings with another type or event id are separate entries.
    assert len(set(name_identity(n) for n in plain)) == len(plain)

    if expected:
        primary_identity = data.draw(st.sampled_from(expected))
        for primary in (primary_identity, Name(
            type=primary_identity[2],
            given=primary_identity[0],
            surname=primary_identity[1],
            event_id=primary_identity[3],
        )):
            merged = union_names(survivor_names, other_names, primary=primary)
            ids = [name_identity(n) for n in merged]
            assert ids[0] == primary_identity
            assert len(ids) == len(expected)
            rest_expected = [i for i in expected if i != primary_identity]
            assert ids[1:] == rest_expected

    # Inputs are not modified.
    assert [(n.type, n.given, n.surname, n.event_id) for n in survivor_names] == before_s
    assert [(n.type, n.given, n.surname, n.event_id) for n in other_names] == before_o
