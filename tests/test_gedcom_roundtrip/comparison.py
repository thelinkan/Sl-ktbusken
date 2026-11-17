"""Comparator for two Stable_Views (design C12, Requirement 14).

``compare(a, b)`` pairs the items of each section (first by exact key, then by
the loose key of the item), reports every field that differs, and gives each
difference a code of the difference catalog. A difference whose code is not in
the catalog (including ``UNCLASSIFIED``, used when no rule covers the
difference) makes ``compare`` raise ``UncatalogedDifference``. The exception
carries all differences, so a failing test shows the full list.

``a`` is the original, ``b`` the result of the round trip.

The comparator never fails on a ``fixed`` difference by itself; use
``blocking(differences)`` for the differences that a test must assert to be
empty (Requirement 14.4) and ``reportable(differences)`` for those that the
report lists (Requirement 14.5).
"""

from __future__ import annotations

from collections import Counter

from dataclasses import dataclass
from typing import Any, Callable, Optional, Union

from tests.test_gedcom_roundtrip.difference_catalog import (
    CATALOG,
    FIXED,
    UNCOVERED_SOURCE_FIELDS,
    CatalogEntry,
)
from tests.test_gedcom_roundtrip.stable_view import Item, StableView, stable_view

from slaktbusken.model.project import ProjectData

UNCLASSIFIED = "UNCLASSIFIED"

#: Event types that belong to a family. Their absence is K1; any other type is K27.
FAMILY_EVENT_TYPES = frozenset(
    {
        "marriage",
        "divorce",
        "engagement",
        "separation",
        "annulment",
        "custom_family_event",
    }
)

_NON_DEFAULT_PARENTAGE = frozenset({"legal", "step", "unknown_donor", "donation"})


@dataclass(frozen=True)
class Difference:
    """One difference between two views."""

    code: str
    section: str
    key: tuple
    field: Optional[str]
    before: Any
    after: Any
    description: str = ""

    @property
    def entry(self) -> Optional[CatalogEntry]:
        return CATALOG.get(self.code)

    @property
    def status(self) -> Optional[str]:
        entry = self.entry
        return None if entry is None else entry.status

    @property
    def difference_class(self) -> Optional[str]:
        entry = self.entry
        return None if entry is None else entry.difference_class

    def describe(self) -> str:
        where = self.section if self.field is None else f"{self.section}.{self.field}"
        return f"{self.code} [{where}] {self.description}: {self.before!r} -> {self.after!r}"


class UncatalogedDifference(AssertionError):
    """Raised by ``compare`` when a difference has no catalog entry."""

    def __init__(self, differences: list[Difference]) -> None:
        self.differences = differences
        lines = [d.describe() for d in differences if d.entry is None]
        super().__init__(
            "Differences without difference catalog entry:\n  " + "\n  ".join(lines)
        )


# --------------------------------------------------------------------------
# Rules: (section, field) -> code
# --------------------------------------------------------------------------

_Rule = Callable[[Any, Any], str]


def _participants_rule(before: Any, after: Any) -> str:
    refs_before = sorted({ref for ref, _ in before}, key=repr)
    refs_after = sorted({ref for ref, _ in after}, key=repr)
    return "K29" if refs_before != refs_after else "K28"


def _citations_rule(before: Any, after: Any) -> str:
    def strip(citations, *, context: bool = False, quality: bool = False):
        out = []
        for ctx, title, qual, note, aspects in citations:
            out.append(
                ("" if context else ctx, title, "" if quality else qual, note, aspects)
            )
        return sorted(out, key=repr)

    def from_place(citations):
        return sorted((c for c in citations if c[0] == "from_place"), key=repr)

    if from_place(before) != from_place(after):
        return "K20"
    if strip(before, context=True) == strip(after, context=True):
        return "K16"
    if strip(before, quality=True) == strip(after, quality=True):
        return "K17"
    return "K18"


def _parentage_rule(before: Any, after: Any) -> str:
    only_before = [link for link in before if link not in after]
    if any(link[2] in _NON_DEFAULT_PARENTAGE for link in only_before):
        return "K14"
    return "K15"


def _observations_rule(before: Any, after: Any) -> str:
    # element: (title, from, to, page_note, quality, note, aspects)
    def periods(obs):
        return sorted((o[0], o[1], o[2], o[3]) for o in obs)

    return "K22" if periods(before) != periods(after) else "K23"


def _event_refs_rule(before: Any, after: Any) -> str:
    # An orphan family event that the family lists after the import (K51); a
    # reference that is missing or changed is still K1.
    gained = len(after) > len(before) and all(ref in after for ref in before)
    return "K51" if gained else "K1"


def _fixed(code: str) -> _Rule:
    return lambda before, after: code


_FIELD_RULES: dict[tuple[str, str], _Rule] = {
    ("persons", "names"): _fixed("K7"),
    ("persons", "sex"): _fixed("K13"),
    ("persons", "notes"): _fixed("K3"),
    ("persons", "title"): _fixed("K4"),
    ("persons", "occupation"): _fixed("K42"),
    ("persons", "name_event_links"): _fixed("K9"),
    ("persons", "has_profile_media"): _fixed("K40"),
    ("events", "participants"): _participants_rule,
    ("events", "from_place"): _fixed("K21"),
    ("events", "citations"): _citations_rule,
    ("events", "media_count"): _fixed("K30"),
    ("families", "partners"): _fixed("K11"),
    ("families", "parentage"): _parentage_rule,
    ("families", "event_refs"): _event_refs_rule,
    ("residences", "start"): _fixed("K24"),
    ("residences", "end"): _fixed("K24"),
    ("residences", "start_event"): _fixed("K25"),
    ("residences", "end_event"): _fixed("K25"),
    ("residences", "role"): _fixed("K26"),
    ("residences", "notes"): _fixed("K26"),
    ("residences", "observations"): _observations_rule,
    ("sources", "source_type"): _fixed("K33"),
    ("sources", "provider"): _fixed("K32"),
    ("sources", "leverantor"): _fixed("K32"),
    ("sources", "kalltyp"): _fixed("K32"),
    ("sources", "reference_text"): _fixed("K50"),
    ("events", "cause"): _fixed("K56"),
    ("sources", "structured_reference"): _fixed("K34"),
    ("sources", "repository_refs"): _fixed("K31"),
    ("repositories", "phone"): _fixed("K31"),
    ("repositories", "email"): _fixed("K31"),
    ("repositories", "web"): _fixed("K31"),
    ("repositories", "notes"): _fixed("K31"),
    ("repositories", "external_ids"): _fixed("K31"),
    ("totals", "count"): _fixed("K30"),
}
for _field, _code in UNCOVERED_SOURCE_FIELDS.items():
    _FIELD_RULES[("sources", _field)] = _fixed(_code)


def _missing_code(section: str, item: Item) -> str:
    """Code for an item of the original that has no counterpart in the result."""
    if section == "events":
        return "K1" if item.identity[0] in FAMILY_EVENT_TYPES else "K27"
    if section == "repositories":
        return "K31"
    return UNCLASSIFIED


def _field_code(section: str, name: str, before: Any, after: Any) -> str:
    rule = _FIELD_RULES.get((section, name))
    return UNCLASSIFIED if rule is None else rule(before, after)


# --------------------------------------------------------------------------
# Pairing and comparison
# --------------------------------------------------------------------------


def _pair(
    a_items: tuple[Item, ...], b_items: tuple[Item, ...]
) -> tuple[list[tuple[Item, Item]], list[Item], list[Item]]:
    b_by_key = {item.key: item for item in b_items}
    pairs: list[tuple[Item, Item]] = []
    left_a: list[Item] = []
    used: set[tuple] = set()
    for item in a_items:
        other = b_by_key.get(item.key)
        if other is None:
            left_a.append(item)
        else:
            pairs.append((item, other))
            used.add(item.key)
    left_b = [item for item in b_items if item.key not in used]

    by_loose: dict[tuple, list[Item]] = {}
    for item in left_b:
        by_loose.setdefault(item.loose, []).append(item)
    missing: list[Item] = []
    for item in left_a:
        candidates = by_loose.get(item.loose)
        if candidates:
            pairs.append((item, candidates.pop(0)))
        else:
            missing.append(item)
    extra = [item for items in by_loose.values() for item in items]
    extra.sort(key=lambda i: (repr(i.identity), i.ordinal))
    return pairs, missing, extra


#: Event types that the importer derives for foster and adoptive links (K53).
PLACEMENT_EVENT_TYPES = frozenset({"foster_home", "adoption"})


def _fold_derived_families(
    pairs: list[tuple[Item, Item]], extra: list[Item]
) -> tuple[list[tuple[Item, Item]], list[Item], list[Item]]:
    """Fold derived placement families into the family of the same partners (K53).

    The importer derives a family from a placement event. When the original
    family held the placement and other events, the result has two families
    with the same partners. Their event references and parentage links are
    taken together, and the derived family is returned as a K53 item.
    """
    derived: list[Item] = []
    rest: list[Item] = []
    pair_of: dict[tuple, int] = {}
    for index, (_before, after) in enumerate(pairs):
        pair_of.setdefault(after.loose, index)
    result = list(pairs)
    for item in extra:
        index = pair_of.get(item.loose)
        if index is None:
            rest.append(item)
            continue
        before, after = result[index]
        fields = dict(after.fields)
        for name in ("event_refs", "parentage"):
            # Multiset union: identical references (two undated marriages of
            # the same partner) must not collapse into one.
            merged = (Counter(fields.get(name, ())) | Counter(item.fields.get(name, ()))).elements()
            fields[name] = tuple(sorted(merged, key=repr))
        result[index] = (before, Item(after.identity, after.ordinal, after.loose, fields))
        derived.append(item)
    return result, derived, rest


def compare_sections(a: StableView, b: StableView) -> list[Difference]:
    differences: list[Difference] = []
    for section in sorted(set(a.sections) | set(b.sections), key=_section_order):
        pairs, missing, extra = _pair(a.items(section), b.items(section))
        derived: list[Item] = []
        if section == "families":
            pairs, derived, extra = _fold_derived_families(pairs, extra)
        for item in derived:
            differences.append(
                Difference(
                    code="K53",
                    section=section,
                    key=item.key,
                    field=None,
                    before=None,
                    after=item.identity,
                    description="families derived family for a placement event",
                )
            )
        for before, after in pairs:
            for name in sorted(set(before.fields) | set(after.fields)):
                value_a = before.fields.get(name)
                value_b = after.fields.get(name)
                if value_a == value_b:
                    continue
                differences.append(
                    Difference(
                        code=_field_code(section, name, value_a, value_b),
                        section=section,
                        key=before.key,
                        field=name,
                        before=value_a,
                        after=value_b,
                        description=f"{section} {before.identity!r} differs in {name}",
                    )
                )
        for item in missing:
            differences.append(
                Difference(
                    code=_missing_code(section, item),
                    section=section,
                    key=item.key,
                    field=None,
                    before=item.identity,
                    after=None,
                    description=f"{section} item is missing in the result",
                )
            )
        for item in extra:
            derived_event = section == "events" and item.identity[0] in PLACEMENT_EVENT_TYPES
            differences.append(
                Difference(
                    code="K53" if derived_event else UNCLASSIFIED,
                    section=section,
                    key=item.key,
                    field=None,
                    before=None,
                    after=item.identity,
                    description=f"{section} item is new in the result",
                )
            )
    return differences


def _section_order(section: str) -> int:
    from tests.test_gedcom_roundtrip.stable_view import SECTIONS

    return SECTIONS.index(section) if section in SECTIONS else len(SECTIONS)


def _as_view(value: Union[ProjectData, StableView]) -> StableView:
    return value if isinstance(value, StableView) else stable_view(value)


def compare(
    a: Union[ProjectData, StableView], b: Union[ProjectData, StableView]
) -> list[Difference]:
    """Return the differences between *a* (original) and *b* (round-tripped).

    Raises ``UncatalogedDifference`` when any difference has no catalog entry.
    """
    differences = compare_sections(_as_view(a), _as_view(b))
    if any(d.code not in CATALOG for d in differences):
        raise UncatalogedDifference(differences)
    return differences


def blocking(differences: list[Difference]) -> list[Difference]:
    """Differences whose catalog status is ``fixed``; a test asserts this is empty."""
    return [d for d in differences if d.status == FIXED]


def reportable(differences: list[Difference]) -> list[Difference]:
    """Differences that are listed in the report (not ``fixed``)."""
    return [d for d in differences if d.status != FIXED]
