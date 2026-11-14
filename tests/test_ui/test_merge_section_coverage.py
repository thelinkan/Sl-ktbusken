"""Every plan item, conflict and choice is shown on exactly one wizard page."""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.services.merge_planner import (
    Disposition, MergeConflict, PlanItem, SEVERITY_BLOCKING, SEVERITY_WARNING,
    UnresolvedChoice,
)
from slaktbusken.ui.merge import merge_pages, merge_preview
from slaktbusken.ui.merge.merge_pages import (
    FALLBACK_SECTION_ID, SECTION_DEFS, SectionPage, build_choice_specs,
    section_id_for_category, section_id_for_plan_section,
)

from tests.test_ui.test_merge_preview_category_labels import SERVICES, _emitted_categories


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _pages() -> list[SectionPage]:
    return [SectionPage(*d) for d in SECTION_DEFS]


def _emitted_plan_sections() -> set[str]:
    found: set[str] = set()
    for path in SERVICES.glob("merge_planner*.py"):
        text = path.read_text(encoding="utf-8")
        found.update(re.findall(r'add_conflict\(\s*SEVERITY_\w+,\s*"\w+",\s*"(\w+)"', text))
        found.update(re.findall(r'add_unresolved\(\s*[^,]+,\s*"(\w+)"', text))
    return found


def _plan(items, conflicts=()):
    return SimpleNamespace(
        items=tuple(items), conflicts=tuple(conflicts), empty_family_offers=(),
        decisions=SimpleNamespace(remove_empty_family_ids=()),
    )


def _show(pages, plan, specs=()):
    for page in pages:
        page.show_plan(plan, specs, {})


def test_every_planner_category_maps_to_one_section_or_the_fallback(qapp) -> None:
    categories = _emitted_categories() | {"dna", "sources", "media", "research"}
    pages = _pages()
    for category in categories:
        owners = [p.section_id for p in pages if p._owns_category(category)]
        assert len(owners) == 1, (category, owners)
        assert owners == [section_id_for_category(category)]
    assert [p.section_id for p in pages if p._owns_category("future_kind")] == [FALLBACK_SECTION_ID]


def test_every_emitted_conflict_and_choice_section_has_one_page(qapp) -> None:
    sections = _emitted_plan_sections()
    assert {"attributes", "families", "dna", "media", "other_refs"} <= sections
    pages = _pages()
    for section in sections | {"something_new"}:
        owners = [p.section_id for p in pages if p._owns_section(section)]
        assert len(owners) == 1, (section, owners)
        assert owners == [section_id_for_plan_section(section)]
    assert not any(p._owns_section("survivor") for p in pages)


def test_section_names_cover_every_section_page_section() -> None:
    for sid, title, sections, _cats in SECTION_DEFS:
        for section in sections:
            assert merge_preview.SECTION_NAMES[section] == title
    assert merge_preview.SECTION_NAMES["survivor"]


def test_all_items_appear_once_with_category_prefix(qapp) -> None:
    categories = sorted(_emitted_categories())
    items = [
        PlanItem(c, f"id_{c}", f"Post {c}", Disposition.PRESERVED, "") for c in categories
    ] + [PlanItem("unknown_kind", "x", "Okänd post", Disposition.PRESERVED, "")]
    pages = _pages()
    _show(pages, _plan(items))
    shown = [
        p.items_list.item(i).text() for p in pages for i in range(p.items_list.count())
    ]
    assert len(shown) == len(items)
    assert merge_pages.NO_ITEMS_TEXT not in shown
    for category in categories:
        page = next(p for p in pages if p._owns_category(category))
        plain = f"Post {category} ·"
        expected = (
            f"{merge_preview.category_label(category)}: {plain}"
            if page._shows_many_categories() else plain
        )
        assert sum(t.startswith(expected) for t in shown) == 1, category
    assert any(t.startswith("unknown_kind: Okänd post") for t in shown)
    by_id = {p.section_id: p for p in pages}
    media_texts = [by_id["media"].items_list.item(i).text() for i in range(by_id["media"].items_list.count())]
    assert any(t.startswith("DNA-profiler: ") for t in media_texts)
    assert any(t.startswith("Källhänvisningar: ") for t in media_texts)
    other = [by_id["other_refs"].items_list.item(i).text() for i in range(by_id["other_refs"].items_list.count())]
    for label in ("Forskningsärenden", "Hypoteser", "Forskningsanteckningar", "Kandidater",
                  "Identitetskopplingar"):
        assert any(t.startswith(f"{label}: ") for t in other), label


def test_single_category_section_keeps_plain_lines(qapp) -> None:
    pages = _pages()
    _show(pages, _plan([PlanItem("names", "n", "Anna", Disposition.PRESERVED, "")]))
    names = next(p for p in pages if p.section_id == "names")
    assert names.items_list.item(0).text() == f"Anna · {Disposition.PRESERVED.value}"


def test_every_conflict_and_choice_is_shown_once(qapp) -> None:
    sections = sorted(_emitted_plan_sections()) + ["something_new"]
    conflicts = [
        MergeConflict(SEVERITY_WARNING if i % 2 else SEVERITY_BLOCKING, f"c{i}", s, f"Meddelande {i}", ())
        for i, s in enumerate(sections)
    ]
    pages = _pages()
    _show(pages, _plan([], conflicts))
    shown = [
        p.problems_list.item(i).text() for p in pages for i in range(p.problems_list.count())
    ]
    assert len(shown) == len(conflicts)
    for i in range(len(conflicts)):
        assert sum(bool(re.search(rf"Meddelande {i}\b", t)) for t in shown) == 1, i

    choices = [UnresolvedChoice(f"k{i}", s, f"Val {i}", ("a", "b")) for i, s in enumerate(sections)]
    specs = build_choice_specs(choices, lambda p: p, "p1", "p2", {}, ())
    _show(pages, _plan([]), specs)
    keys = [k for p in pages for k in p._known]
    assert sorted(keys) == sorted(c.key for c in choices)
