"""Person_Reference_Inventory and PersonReferenceIndex for person merges.

The inventory lists every location in the project (and in
``translation/persons.json``) that holds, or looks like it holds, a person id.
Each row has exactly one Reference_Rule, the name of the handler that applies
it, and a statement of what happens to duplicates after a rewrite.

``PersonReferenceIndex.build`` makes one pass over each collection and records
which objects reference the survivor or the retired person per location. All
later lookups are dictionary accesses.

This module has no Qt imports.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from typing import Any, Callable, Iterable, Mapping, Optional

# ---------------------------------------------------------------------------
# Reference rules
# ---------------------------------------------------------------------------

RULE_REWIRE = "R"
RULE_MERGE_DEDUPE = "M"
RULE_PRESERVE_SEPARATELY = "S"
RULE_EXPLICIT = "E"
RULE_HISTORICAL = "H"
RULE_SPECIAL = "special"

REFERENCE_RULES = (
    RULE_REWIRE,
    RULE_MERGE_DEDUPE,
    RULE_PRESERVE_SEPARATELY,
    RULE_EXPLICIT,
    RULE_HISTORICAL,
    RULE_SPECIAL,
)

# Rules that need a handler. S and H rows leave data unchanged.
RULES_REQUIRING_HANDLER = frozenset(
    {RULE_REWIRE, RULE_MERGE_DEDUPE, RULE_EXPLICIT, RULE_SPECIAL}
)

DEDUPE_NONE = "none"
DEDUPE_COLLAPSE = "collapse"
DEDUPE_BLOCK = "block"
DEDUPE_NOT_APPLICABLE = "n/a"


@dataclass(frozen=True)
class ReferenceLocation:
    """One row of the Person_Reference_Inventory."""

    key: str  # "family.partners", "event.participants", ...
    owner_class: str  # dataclass name, or "translation:persons.json"
    field_path: str  # "partners[].person_id"
    rule: str  # R | M | S | E | H | special
    handler: Optional[str]  # None only for S and H rows
    dedupe: str  # none | collapse | block | n/a
    dedupe_statement: str  # what happens to duplicates after a rewrite

    @property
    def field_name(self) -> str:
        """Last path segment, for example ``person_id``."""
        return self.field_path.rsplit(".", 1)[-1].replace("[]", "")

    @property
    def requires_handler(self) -> bool:
        return self.rule in RULES_REQUIRING_HANDLER


def _loc(
    key: str,
    owner: str,
    path: str,
    rule: str,
    dedupe: str,
    statement: str,
) -> ReferenceLocation:
    handler = f"handle_{key.replace('.', '_')}" if rule in RULES_REQUIRING_HANDLER else None
    return ReferenceLocation(key, owner, path, rule, handler, dedupe, statement)


_TRANSLATION = "translation:persons.json"

PERSON_REFERENCE_INVENTORY: tuple[ReferenceLocation, ...] = (
    _loc("family.partners", "FamilyPartner", "partners[].person_id", "R", "block",
         "Both persons in one family is a Blocking_Conflict (self-partner); no silent dedupe."),
    _loc("family.children", "Family", "children", "M", "collapse",
         "Duplicate child entry collapses to the first position; Merge_Warning."),
    _loc("family.parent_child_links.child", "ParentChildLink", "parent_child_links[].child_id", "M", "collapse",
         "Same (child, parent, type) collapses; different parentage_type stays separate with one Merge_Warning per pair."),
    _loc("family.parent_child_links.parent", "ParentChildLink", "parent_child_links[].parent_id", "M", "collapse",
         "As child_id; child equal to parent is a Blocking_Conflict. None (unknown donor) is left alone."),
    _loc("family.event_ids", "Family", "event_ids", "S", "n/a",
         "Event ids, not person ids; unchanged."),
    _loc("event.participants", "Participant", "participants[].person_id", "M", "collapse",
         "Same person and role collapses to the first entry; different roles need an explicit role choice."),
    _loc("residence.person", "ResidenceFact", "person_id", "R", "none",
         "Never collapsed, also when date or place are equal."),
    _loc("residence.refs", "ResidenceFact", "observations[]", "S", "n/a",
         "Source and event ids; unchanged."),
    _loc("person.profile_media_id", "Person", "profile_media_id", "E", "n/a",
         "Both non-empty and different: user chooses."),
    _loc("person.sex", "Person", "sex", "E", "n/a",
         "Two different known values: user chooses; U counts as unknown."),
    _loc("person.title_occupation", "Person", "title / occupation", "E", "n/a",
         "Both non-empty and different: user chooses."),
    _loc("person.notes", "Person", "notes", "M", "n/a",
         "Keep survivor's, keep other's, or concatenate with a visible separator."),
    _loc("person.names", "Person", "names[]", "M", "collapse",
         "Exact duplicates collapse; same string with different type or event_id stays."),
    _loc("person.names.event_id", "Person", "names[].event_id", "S", "n/a",
         "Event id; unchanged."),
    _loc("media.linked_entities", "LinkedEntity", "linked_entities[].entity_id", "M", "collapse",
         "Duplicate person links collapse into the first; role is the first non-empty role."),
    _loc("media.mentioned_person_ids", "MediaItem", "mentioned_person_ids", "M", "collapse",
         "Duplicates collapse to the first position."),
    _loc("media.annotations", "Annotation", "annotations[].entity_id", "R", "none",
         "Kept as separate entries (own region coordinates); Merge_Warning for two regions of one person."),
    _loc("media.mentioned_names", "MediaItem", "mentioned_names", "S", "n/a",
         "Free-text names, not ids; unchanged."),
    _loc("research_note.linked_entities", "LinkedEntity", "linked_entities[].entity_id", "M", "collapse",
         "Duplicates collapse to one per note."),
    _loc("dna_profile.person", "DnaProfile", "person_id", "R", "none",
         "Profiles are never merged; counts unchanged."),
    _loc("dna_profile.admin_person", "DnaProfile", "admin_person_id", "R", "n/a",
         "Replaced when equal to the retired id."),
    _loc("dna_cluster.person_ids", "DnaCluster", "person_ids", "M", "collapse",
         "Duplicate collapses; order of the others preserved."),
    _loc("dna.profile_match_refs", "DnaMatch", "profile1_id / profile2_id / match_id / profile_ids", "S", "n/a",
         "Profile and match ids, not person ids; unchanged. Merge_Warning when a match now joins one person."),
    _loc("research_case.entities", "ResearchEntityLink", "primary_entity_ref / linked_entities[].entity_id", "M", "collapse",
         "rewire_entity_merge on a copy; counts reported separately."),
    _loc("research_hypothesis.entities", "ResearchEntityLink", "linked_entities[].entity_id", "M", "collapse",
         "Same helper call as for cases."),
    _loc("research_action.none", "ResearchAction", "(no person fields)", "S", "n/a",
         "ResearchAction and HypothesisComment hold no person ids; unchanged."),
    _loc("project.main_person_id", "ProjectMetadata", "main_person_id", "R", "n/a",
         "Set to the survivor when equal to the retired id."),
    _loc("project.connection_overrides", "ProjectData", "connection_overrides (keys)", "E", "n/a",
         "Both with different values: user chooses; otherwise move or keep the key."),
    _loc("merge_candidate.persons", "MergeCandidate", "person_1_id / person_2_id", "special", "collapse",
         "Redirect, collision or archive per the candidate algorithm; one candidate per unordered pair."),
    _loc("merge_history.persons", "MergeHistoryEntry", "surviving_person_id / merged_person_id", "H", "n/a",
         "Never rewritten; later merges are followed through Redirect_Resolution."),
    _loc("merge_history.archived_candidates", "ArchivedCandidate", "person_1_id / person_2_id", "H", "n/a",
         "Original ids as archived."),
    _loc("translation.person_mappings", _TRANSLATION, "person_mappings[].app_id", "special", "n/a",
         "Mappings of the retired person move to identity_aliases."),
    _loc("translation.identity_aliases", _TRANSLATION, "identity_aliases[].person_id", "R", "n/a",
         "Earlier aliases pointing at the retired person are rewritten to the survivor."),
    _loc("translation.family_mappings", _TRANSLATION, "family_mappings[].app_id", "S", "n/a",
         "Family ids; a merge does not combine families."),
    _loc("settings.none", "ProjectSettings / AppSettings", "(no person ids)", "S", "n/a",
         "Verified: neither settings file stores a person id."),
    _loc("media.publication_dates", "MediaItem", "publication / photo_date", "S", "n/a",
         "Free-form dicts without person ids."),
)

INVENTORY_BY_KEY: dict[str, ReferenceLocation] = {
    loc.key: loc for loc in PERSON_REFERENCE_INVENTORY
}

# ---------------------------------------------------------------------------
# Allow-list for generic reference fields (name does not end in person_id/s)
# ---------------------------------------------------------------------------

# "Class.field" -> inventory key that explains the field. A new generic
# reference field must be added here (or to the inventory) deliberately.
GENERIC_REFERENCE_FIELD_ALLOWLIST: dict[str, str] = {
    "LinkedEntity.entity_id": "media.linked_entities",  # also research_note.linked_entities
    "Annotation.entity_id": "media.annotations",
    "ResearchEntityLink.entity_id": "research_case.entities",  # also hypotheses
    "ParentChildLink.child_id": "family.parent_child_links.child",
    "ParentChildLink.parent_id": "family.parent_child_links.parent",
    "ProjectData.connection_overrides": "project.connection_overrides",
}


def _is_person_reference_name(name: str) -> bool:
    return name.endswith("person_id") or name.endswith("person_ids")


def inventory_field_pairs() -> set[tuple[str, str]]:
    """(owner class, field name) pairs covered by the inventory rows."""
    pairs: set[tuple[str, str]] = set()
    for loc in PERSON_REFERENCE_INVENTORY:
        for part in loc.field_path.split("/"):
            name = part.strip().split(" ")[0].rsplit(".", 1)[-1].replace("[]", "")
            if name:
                pairs.add((loc.owner_class, name))
    return pairs


def find_unlisted_person_reference_fields(classes: Iterable[type]) -> list[str]:
    """Return ``"Class.field"`` for each person-reference field not in the
    inventory or the allow-list. Used by the completeness test."""
    covered = inventory_field_pairs()
    unlisted: list[str] = []
    for cls in classes:
        if not is_dataclass(cls):
            continue
        for f in fields(cls):
            if not _is_person_reference_name(f.name):
                continue
            qualified = f"{cls.__name__}.{f.name}"
            if (cls.__name__, f.name) in covered:
                continue
            if qualified in GENERIC_REFERENCE_FIELD_ALLOWLIST:
                continue
            unlisted.append(qualified)
    return unlisted


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

HANDLER_REGISTRY: dict[str, Callable[..., Any]] = {}


def register_handler(key: str, func: Callable[..., Any]) -> None:
    """Register the handler for an inventory key (done by ``merge_planner``)."""
    if key not in INVENTORY_BY_KEY:
        raise KeyError(f"Okänd referensplats: {key}")
    HANDLER_REGISTRY[key] = func


def missing_handlers(
    registry: Optional[Mapping[str, Callable[..., Any]]] = None,
) -> list[ReferenceLocation]:
    """Locations whose rule needs a handler but have none registered."""
    reg = HANDLER_REGISTRY if registry is None else registry
    return [
        loc
        for loc in PERSON_REFERENCE_INVENTORY
        if loc.requires_handler and loc.key not in reg
    ]


def missing_handlers_message(
    registry: Optional[Mapping[str, Callable[..., Any]]] = None,
) -> Optional[str]:
    """Swedish error text naming each location without a handler, or None."""
    missing = missing_handlers(registry)
    if not missing:
        return None
    lines = [f"- {loc.owner_class}.{loc.field_path} ({loc.key})" for loc in missing]
    return (
        "Sammanslagningen kan inte genomföras. Följande platser med "
        "personreferenser saknar hanterare:\n" + "\n".join(lines)
    )


# ---------------------------------------------------------------------------
# PersonReferenceIndex
# ---------------------------------------------------------------------------


class PersonReferenceIndex:
    """Which objects reference the survivor or retired id, per location.

    ``refs[key][person_id]`` is the list of referencing objects (the partner,
    link, event, media item, ... that holds the id). Built in one pass per
    collection; lookups are dictionary accesses.
    """

    def __init__(self, ids: frozenset[str]) -> None:
        self.ids = ids
        self.refs: dict[str, dict[str, list[Any]]] = {
            loc.key: {} for loc in PERSON_REFERENCE_INVENTORY
        }

    # -- construction -----------------------------------------------------

    def _add(self, key: str, person_id: Any, obj: Any) -> None:
        if isinstance(person_id, str) and person_id in self.ids:
            self.refs[key].setdefault(person_id, []).append(obj)

    def _add_person_links(self, key: str, links: Iterable[Any], owner: Any) -> None:
        for link in links:
            if getattr(link, "entity_type", None) == "person":
                self._add(key, link.entity_id, owner)

    @classmethod
    def build(
        cls,
        data: Any,
        person_ids: Iterable[str],
        translation: Any = None,
    ) -> "PersonReferenceIndex":
        """Index references to *person_ids* (``{survivor, retired}``)."""
        ids = frozenset(person_ids)
        idx = cls(ids)
        add = idx._add

        for fam in data.families:
            for partner in fam.partners:
                add("family.partners", partner.person_id, fam)
            for child in fam.children:
                add("family.children", child, fam)
            for link in fam.parent_child_links:
                add("family.parent_child_links.child", link.child_id, fam)
                add("family.parent_child_links.parent", link.parent_id, fam)

        for ev in data.events:
            for part in ev.participants:
                add("event.participants", part.person_id, ev)

        for fact in data.residences:
            add("residence.person", fact.person_id, fact)

        for person in data.persons:
            if person.id in ids:
                add("person.names", person.id, person)

        for item in data.media:
            idx._add_person_links("media.linked_entities", item.linked_entities, item)
            for pid in item.mentioned_person_ids:
                add("media.mentioned_person_ids", pid, item)
            idx._add_person_links("media.annotations", item.annotations, item)

        for note in data.research_notes:
            idx._add_person_links("research_note.linked_entities", note.linked_entities, note)

        for prof in data.dna_profiles:
            add("dna_profile.person", prof.person_id, prof)
            add("dna_profile.admin_person", prof.admin_person_id, prof)

        for cluster in data.dna_clusters:
            for pid in cluster.person_ids:
                add("dna_cluster.person_ids", pid, cluster)

        for case in data.research_cases:
            if case.primary_entity_ref is not None:
                idx._add_person_links("research_case.entities", [case.primary_entity_ref], case)
            idx._add_person_links("research_case.entities", case.linked_entities, case)

        for hyp in data.research_hypotheses:
            idx._add_person_links("research_hypothesis.entities", hyp.linked_entities, hyp)

        add("project.main_person_id", data.project.main_person_id, data.project)

        for child_id in data.connection_overrides:
            add("project.connection_overrides", child_id, child_id)

        for cand in getattr(data, "merge_candidates", None) or []:
            add("merge_candidate.persons", getattr(cand, "person_1_id", None), cand)
            add("merge_candidate.persons", getattr(cand, "person_2_id", None), cand)

        for entry in getattr(data, "merge_history", None) or []:
            add("merge_history.persons", getattr(entry, "surviving_person_id", None), entry)
            add("merge_history.persons", getattr(entry, "merged_person_id", None), entry)
            for arch in getattr(entry, "archived_candidates", None) or []:
                add("merge_history.archived_candidates", getattr(arch, "person_1_id", None), arch)
                add("merge_history.archived_candidates", getattr(arch, "person_2_id", None), arch)

        if translation is not None:
            for m in getattr(translation, "persons", None) or []:
                add("translation.person_mappings", getattr(m, "app_id", None), m)
            for a in getattr(translation, "person_aliases", None) or []:
                add("translation.identity_aliases", getattr(a, "person_id", None), a)

        return idx

    # -- lookups ----------------------------------------------------------

    def references(self, key: str, person_id: str) -> list[Any]:
        """Objects at *key* referencing *person_id* (empty list when none)."""
        return self.refs.get(key, {}).get(person_id, [])

    def count(self, key: str, person_id: str) -> int:
        return len(self.references(key, person_id))

    def counts(self) -> dict[str, dict[str, int]]:
        """Per location and person id, the number of references (non-zero only)."""
        return {
            key: {pid: len(objs) for pid, objs in by_id.items() if objs}
            for key, by_id in self.refs.items()
            if any(by_id.values())
        }

    def total(self, person_id: str) -> int:
        return sum(len(by_id.get(person_id, ())) for by_id in self.refs.values())

    def missing_handlers(
        self, registry: Optional[Mapping[str, Callable[..., Any]]] = None
    ) -> list[ReferenceLocation]:
        """Same as the module-level :func:`missing_handlers`."""
        return missing_handlers(registry)
