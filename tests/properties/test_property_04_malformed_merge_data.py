"""Property 4: Malformed merge data is kept and reported.

**Validates: Requirements 7.7**
"""

from __future__ import annotations

import json

import pytest
from hypothesis import given, strategies as st

from slaktbusken.persistence.file_io import CorruptedFileError
from slaktbusken.persistence.serialization import deserialize, serialize

SECTIONS = ("merge_candidates", "merge_history")

# field name -> (required, kind) where kind is the JSON type the field expects.
CANDIDATE_FIELDS = {
    "id": (True, "str"),
    "person_1_id": (True, "str"),
    "person_2_id": (True, "str"),
    "assessment": (False, "str"),
    "enabled": (False, "bool"),
    "research_case_id": (False, "optstr"),
    "comments": (False, "list"),
}
HISTORY_FIELDS = {
    "id": (True, "str"),
    "surviving_person_id": (True, "str"),
    "merged_person_id": (True, "str"),
    "merged_person_name": (True, "str"),
    "merged_person_lifespan": (True, "str"),
    "merge_date": (True, "str"),
    "merge_candidate_id": (False, "optstr"),
    "archived_candidates": (False, "list"),
    "identity_mappings": (False, "list"),
    "summary_lines": (False, "list"),
}
FIELDS = {"merge_candidates": CANDIDATE_FIELDS, "merge_history": HISTORY_FIELDS}

_text = st.text(max_size=8)


def _valid_value(kind):
    return {
        "str": _text,
        "bool": st.booleans(),
        "optstr": st.one_of(st.none(), _text),
        "list": st.just([]),
    }[kind]


def _wrong_value(kind):
    if kind == "str":
        return st.one_of(st.integers(), st.none(), st.lists(_text, max_size=2), st.booleans())
    if kind == "bool":
        return st.one_of(st.integers(), _text, st.none(), st.just([]))
    if kind == "optstr":
        return st.one_of(st.integers(), st.booleans(), st.just({}), st.just([]))
    return st.one_of(_text, st.integers(), st.none(), st.just({}))


@st.composite
def dict_items(draw, section):
    """A dict item: valid fields, then some dropped and some given a wrong type."""
    spec = FIELDS[section]
    item = {name: draw(_valid_value(kind)) for name, (_, kind) in spec.items()}
    for name, (_, kind) in spec.items():
        action = draw(st.sampled_from(["keep", "keep", "drop", "wrong"]))
        if action == "drop":
            del item[name]
        elif action == "wrong":
            item[name] = draw(_wrong_value(kind))
    if draw(st.booleans()):
        item["unknown_extra"] = draw(_text)
    if "comments" in item and item["comments"] == [] and draw(st.booleans()):
        item["comments"] = [draw(st.one_of(st.integers(), _text, st.none()))]
    return item


_non_dict = st.one_of(
    st.none(), st.integers(), st.booleans(), _text, st.lists(st.integers(), max_size=2)
)


@st.composite
def section_items(draw, section):
    return draw(
        st.lists(st.one_of(dict_items(section), _non_dict), max_size=5)
    )


@st.composite
def documents(draw):
    return {
        "format": "släktbuske-file",
        "version": "0.4",
        "project": {"title": "T"},
        "merge_candidates": draw(section_items("merge_candidates")),
        "merge_history": draw(section_items("merge_history")),
    }


def _accepts(kind, value):
    if kind == "str":
        return isinstance(value, str)
    if kind == "bool":
        return isinstance(value, bool)
    if kind == "optstr":
        return value is None or isinstance(value, str)
    return isinstance(value, list)


def _findings(data, section):
    return [f for f in data.merge_load_findings if f.section == section]


@given(documents())
def test_property_04_malformed_merge_data_kept_and_reported(doc):
    data = deserialize(json.dumps(doc, ensure_ascii=False))

    for section in SECTIONS:
        raw_items = doc[section]
        spec = FIELDS[section]
        loaded = list(getattr(data, section))
        unreadable = data.unreadable_merge_items.get(section, [])
        findings = _findings(data, section)

        # Nothing is deleted: every raw item is either loaded or preserved.
        raw_dicts = [i for i in raw_items if isinstance(i, dict)]
        raw_other = [i for i in raw_items if not isinstance(i, dict)]
        assert len(loaded) + len(unreadable) == len(raw_items)
        assert unreadable == raw_other
        assert len(loaded) == len(raw_dicts)

        # Non-object items are reported once each, without an entry id.
        assert (
            sum(1 for f in findings if f.kind == "unreadable_item" and f.entry_id is None)
            >= len(raw_other)
        )

        for raw, obj in zip(raw_dicts, loaded):
            entry_id = raw.get("id") if isinstance(raw.get("id"), str) else None
            missing = {n for n, (req, _) in spec.items() if req and n not in raw}
            wrong = {
                n for n, (_, k) in spec.items() if n in raw and not _accepts(k, raw[n])
            }
            if isinstance(raw.get("comments"), list) and any(
                not isinstance(c, dict) for c in raw["comments"]
            ):
                wrong.add("comments")

            # Readable fields are kept as stored.
            for name, (_, kind) in spec.items():
                if name in raw and (_accepts(kind, raw[name])):
                    if kind != "list":
                        assert getattr(obj, name) == raw[name]
                elif name in raw:
                    assert getattr(obj, name) == raw[name]  # raw value kept

            # Findings carry the entry id and the affected field names.
            mine = [
                f for f in findings if f.entry_id == entry_id and f.kind != "unreadable_item"
            ]
            reported_missing = {n for f in mine if f.kind == "missing_field" for n in f.fields}
            reported_wrong = {n for f in mine if f.kind == "wrong_type" for n in f.fields}
            assert missing <= reported_missing
            assert wrong <= reported_wrong

        # Save then load keeps every entry and every unreadable item.
        again = deserialize(serialize(data))
        assert len(getattr(again, section)) + len(
            again.unreadable_merge_items.get(section, [])
        ) == len(raw_items)
        assert again.unreadable_merge_items.get(section, []) == raw_other


@pytest.mark.parametrize("section", SECTIONS)
@given(
    bad=st.one_of(
        st.integers(), st.booleans(), _text, st.dictionaries(_text, st.integers(), max_size=2)
    )
)
def test_property_04_non_list_section_raises(section, bad):
    doc = {"format": "släktbuske-file", "version": "0.4", "project": {"title": "T"}, section: bad}
    with pytest.raises(CorruptedFileError):
        deserialize(json.dumps(doc))

