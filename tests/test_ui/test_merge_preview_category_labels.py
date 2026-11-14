"""Every plan item category has a Swedish label in the merge preview summary."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from slaktbusken.services.merge_planner import Disposition, PlanItem
from slaktbusken.ui.merge import merge_preview

SERVICES = Path(merge_preview.__file__).resolve().parents[2] / "services"

#: Categories that the planner passes as variables, not as string literals.
_DYNAMIC = {
    "relatives", "research_cases", "research_hypotheses",
    "identity_mappings", "identity_aliases", "references",
}


def _emitted_categories() -> set[str]:
    found: set[str] = set(_DYNAMIC)
    for path in SERVICES.glob("merge_planner*.py"):
        text = path.read_text(encoding="utf-8")
        found.update(re.findall(r'add_item\(\s*"(\w+)"', text))
    found.discard("")
    return found


def test_every_planner_category_has_a_swedish_label() -> None:
    categories = _emitted_categories()
    assert {"candidates", "dna_summary", "dna_profiles"} <= categories
    missing = sorted(c for c in categories if c not in merge_preview._CATEGORY_LABELS)
    assert not missing
    for category in categories:
        label = merge_preview.category_label(category)
        assert label != category and "_" not in label


def test_summary_lines_show_no_internal_category_names() -> None:
    categories = sorted(_emitted_categories())
    items = tuple(
        PlanItem(c, "x", "x", Disposition.PRESERVED, "") for c in categories
    )
    plan = SimpleNamespace(
        survivor_id="p1", retired_id="p2", items=items,
        preview=SimpleNamespace(
            family_count=0, added_family_ids=(), removed_family_ids=(), changed_family_ids=()
        ),
        research=SimpleNamespace(links_rewired=0, links_collapsed=0),
        candidate_ops=SimpleNamespace(redirected=(), collided=(), archived=()),
        identity_ops=SimpleNamespace(mappings_moved=(), aliases_rewritten=()),
    )
    lines = merge_preview.summary_lines(plan, lambda pid: pid)  # type: ignore[arg-type]
    category_lines = [ln for ln in lines if ln.endswith(f"· {Disposition.PRESERVED.value}")]
    assert len(category_lines) == len(categories)
    for line in category_lines:
        assert "_" not in line
        assert not re.match(r"[a-z]", line)
    assert "Kandidater: 1 · Bevaras" in lines
    assert "DNA-sammanfattning: 1 · Bevaras" in lines
