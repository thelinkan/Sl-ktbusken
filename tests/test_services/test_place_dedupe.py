"""Unit tests for place id de-duplication."""

from __future__ import annotations

from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData
from slaktbusken.services.place_dedupe import (
    deduplicate_places,
    deduplicate_project_places,
)


def _p(id_: str, name: str, type_: str, parent: str | None = None) -> Place:
    return Place(id=id_, type=type_, name=name, parent_place_id=parent)


class TestDeduplicatePlaces:
    def test_no_duplicates_returns_input_unchanged(self):
        places = [
            _p("p1", "Europa", "continent"),
            _p("p2", "Sverige", "country", "p1"),
            _p("p3", "Ljusdal", "socken", "p2"),
        ]
        result, messages = deduplicate_places(places)
        assert result is places  # fast path returns same list object
        assert messages == []

    def test_keeps_record_with_more_complete_chain(self):
        # Two records share id "county"; one resolves up to a country/continent,
        # the other dead-ends at a place with no parent.
        continent = _p("cont", "Europa", "continent")
        country = _p("country", "Sverige", "country", "cont")
        # Good county: parent chain reaches the country/continent.
        good = _p("county", "Gävleborgs län", "county", "country")
        # Bad duplicate: parent points at a dangling/short record named Stockholm.
        stockholm = _p("sthlm", "Stockholm", "ort")
        bad = _p("county", "Gävleborgs län", "county", "sthlm")

        places = [continent, country, good, stockholm, bad]
        result, messages = deduplicate_places(places)

        ids = [p.id for p in result]
        assert ids.count("county") == 1
        kept = next(p for p in result if p.id == "county")
        assert kept is good
        assert len(messages) == 1

    def test_preserves_original_order_of_kept_records(self):
        continent = _p("cont", "Europa", "continent")
        country = _p("country", "Sverige", "country", "cont")
        good = _p("county", "Gävleborgs län", "county", "country")
        bad = _p("county", "Gävleborgs län", "county", None)

        # "bad" appears first, "good" later; good must win but ordering of the
        # remaining records is preserved.
        places = [bad, continent, country, good]
        result, _ = deduplicate_places(places)

        assert [p.id for p in result] == ["cont", "country", "county"]
        assert next(p for p in result if p.id == "county") is good

    def test_tie_break_keeps_earliest(self):
        # Two records with identical (empty) chains: earliest wins.
        first = _p("x", "A", "ort")
        second = _p("x", "B", "ort")
        result, messages = deduplicate_places([first, second])
        assert len(result) == 1
        assert result[0] is first
        assert len(messages) == 1

    def test_circular_parent_reference_is_safe(self):
        # a -> b -> a cycle must not hang.
        a = _p("a", "A", "ort", "b")
        b = _p("b", "B", "ort", "a")
        dup_a = _p("a", "A2", "ort", None)
        result, _ = deduplicate_places([a, b, dup_a])
        assert len(result) == 2
        assert sorted(p.id for p in result) == ["a", "b"]


class TestDeduplicateProjectPlaces:
    def test_mutates_project_and_reports_count(self):
        data = ProjectData()
        data.places = [
            _p("cont", "Europa", "continent"),
            _p("country", "Sverige", "country", "cont"),
            _p("county", "Gävleborgs län", "county", "country"),
            _p("county", "Gävleborgs län", "county", None),  # duplicate
        ]
        log: list[str] = []
        removed = deduplicate_project_places(data, log=log)
        assert removed == 1
        assert len(data.places) == 3
        assert [p.id for p in data.places].count("county") == 1
        assert len(log) == 1
