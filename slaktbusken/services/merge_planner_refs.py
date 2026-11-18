"""Planning steps for sources, media, DNA, research and other references.

Qt-free. Registered through :func:`merge_planner.plan_step` in the slots
``media_sources``, ``dna``, ``research`` and ``other_refs`` (Requirements 1.5
and 22.1 to 22.17, design sections 10.9 to 10.11).

``merge_planner`` imports this module at its end. Steps read ``ctx.data`` and
edit clones through ``ctx.work`` only. The functions that apply one inventory
row are registered with :func:`person_reference_index.register_handler`.
"""

from __future__ import annotations

from typing import Optional

from slaktbusken.model.event import SourceRef
from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.services import merge_rules as rules
from slaktbusken.services import person_reference_index as pri
from slaktbusken.services.merge_planner import (
    SEVERITY_WARNING,
    Disposition,
    PlanContext,
    _count_instances,
    plan_step,
)

SOURCE_REFS_KEY = "all"

#: Inventory rows summarised by ``plan_reference_summary`` (22.17).
_SUMMARY_RULES = (pri.RULE_PRESERVE_SEPARATELY, pri.RULE_HISTORICAL)


# ---------------------------------------------------------------------------
# Sources (22.1) and media (22.2 to 22.5)
# ---------------------------------------------------------------------------


def _person_link_count(item: MediaItem) -> int:
    return sum(1 for le in item.linked_entities if le.entity_type == "person") + len(
        item.mentioned_person_ids
    )


def _media_title(item: MediaItem) -> str:
    return item.title or item.file or item.id


def _unique_refs(ctx: PlanContext, key: str) -> list:
    """Objects referencing the retired person at *key*, each once, in index order."""
    seen: set[int] = set()
    result = []
    for obj in ctx.index.references(key, ctx.retired_id):
        if id(obj) not in seen:
            seen.add(id(obj))
            result.append(obj)
    return result


def _unchosen_profile_media(ctx: PlanContext) -> Optional[str]:
    """The profile media id the user did not keep, once the choice is made."""
    by_id = {p.id: p for p in ctx.data.persons}
    s_val = by_id[ctx.survivor_id].profile_media_id
    r_val = by_id[ctx.retired_id].profile_media_id
    res = rules.resolve_single_value(s_val, r_val)
    if res.status != rules.SINGLE_VALUE_CONFLICT:
        return None
    chosen = ctx.decisions.profile_media_id
    if chosen is None:
        return None
    if chosen.strip() == s_val.strip():  # type: ignore[union-attr]
        return r_val.strip()  # type: ignore[union-attr]
    if chosen.strip() == r_val.strip():  # type: ignore[union-attr]
        return s_val.strip()  # type: ignore[union-attr]
    return None


@plan_step("media_sources")
def plan_media_sources(ctx: PlanContext) -> None:
    s_id, r_id = ctx.survivor_id, ctx.retired_id
    data = ctx.data

    # Source references are never edited by a merge (22.1).
    count = ctx.source_ref_count
    if count is None:
        count = _count_instances(data.events, SourceRef) + _count_instances(
            data.residences, SourceRef
        )
    ctx.add_item(
        "source_refs", SOURCE_REFS_KEY, "Källhänvisningar", Disposition.PRESERVED,
        f"{count} källhänvisningar bevaras oförändrade",
    )

    touched = {
        id(m) for key in (
            "media.linked_entities", "media.mentioned_person_ids", "media.annotations"
        ) for m in ctx.index.references(key, r_id)
    }
    outcome: dict[str, tuple[Disposition, str]] = {}
    for item in data.media:
        if id(item) not in touched:
            continue
        clone: MediaItem = ctx.work.edit("media", item.id)
        before = _person_link_count(item)
        clone.linked_entities = rules.collapse_linked_entities(
            item.linked_entities, r_id, s_id
        )
        clone.mentioned_person_ids = rules.collapse_id_list(
            item.mentioned_person_ids, r_id, s_id
        )
        clone.annotations = rules.rewrite_annotations(item.annotations, r_id, s_id)
        removed = before - _person_link_count(clone)
        if removed:
            ctx.note_dedup("media_person_links", removed)
            outcome[item.id] = (Disposition.COMBINED, "Dubbla personlänkar slås ihop till en")
        else:
            outcome[item.id] = (Disposition.REASSIGNED, "Personlänkarna flyttas till behållen person")

        retired_regions = sum(
            1 for a in item.annotations if a.entity_type == "person" and a.entity_id == r_id
        )
        survivor_regions = sum(
            1 for a in clone.annotations if a.entity_type == "person" and a.entity_id == s_id
        )
        if retired_regions and survivor_regions >= 2:
            ctx.add_conflict(
                SEVERITY_WARNING, "annotation_same_person", "media",
                f"Bilden {_media_title(item)} får två markerade områden för samma person.",
                (item.id, s_id),
            )

    # The profile photo that was not chosen stays linked to the survivor (22.4).
    unchosen = _unchosen_profile_media(ctx)
    if unchosen is not None and any(m.id == unchosen for m in data.media):
        current = ctx.work.change_set.replaced.get("media", {}).get(unchosen)
        if current is None:
            current = ctx.work.original("media", unchosen)
        has_link = any(
            le.entity_type == "person" and le.entity_id == s_id
            for le in current.linked_entities
        )
        if not has_link:
            ctx.work.edit("media", unchosen).linked_entities.append(
                LinkedEntity("person", s_id, "")
            )
            ctx.note_dedup("media_person_links", -1)
        if unchosen not in outcome:
            outcome[unchosen] = (
                Disposition.PRESERVED,
                "Profilbilden som inte valdes är länkad till behållen person",
            )
    by_id = {m.id: m for m in data.media}
    for media_id in sorted(outcome):
        disp, detail = outcome[media_id]
        ctx.add_item("media", media_id, _media_title(by_id[media_id]), disp, detail)


# ---------------------------------------------------------------------------
# DNA (22.6 to 22.9)
# ---------------------------------------------------------------------------


@plan_step("dna")
def plan_dna(ctx: PlanContext) -> None:
    s_id, r_id = ctx.survivor_id, ctx.retired_id
    data = ctx.data
    moved: set[str] = set()

    for prof in data.dna_profiles:
        owned = prof.person_id == r_id
        admin = prof.admin_person_id == r_id
        if owned or admin:
            clone = ctx.work.edit("dna_profiles", prof.id)
            if owned:
                clone.person_id = s_id
                moved.add(prof.id)
            if admin:
                clone.admin_person_id = s_id
            ctx.add_item(
                "dna_profiles", prof.id, f"DNA-profil {prof.id}", Disposition.REASSIGNED,
                "Profilen flyttas till behållen person och behålls som egen profil"
                if owned else "Administratören flyttas till behållen person",
            )
        elif prof.person_id == s_id or prof.admin_person_id == s_id:
            ctx.add_item("dna_profiles", prof.id, f"DNA-profil {prof.id}",
                         Disposition.PRESERVED, "Profilen bevaras")

    # Profiles of the survivor with equal company, test type and kit id (22.8).
    groups: dict[tuple, list[str]] = {}
    for prof in data.dna_profiles:
        if prof.person_id in (s_id, r_id):
            groups.setdefault((prof.company_id, prof.test_type, prof.kit_id), []).append(prof.id)
    for key, ids in groups.items():
        if len(ids) >= 2 and any(i in moved for i in ids):
            ctx.add_conflict(
                SEVERITY_WARNING, "dna_duplicate_profile", "dna",
                f"Behållen person får flera DNA-profiler med samma företag, testtyp "
                f"och kit-id ({key[0]}, {key[1]}, {key[2] or 'saknas'}): {', '.join(ids)}. "
                "Alla behålls.",
                tuple(ids),
            )

    # Clusters (22.9).
    for cluster in _unique_refs(ctx, "dna_cluster.person_ids"):
        clone = ctx.work.edit("dna_clusters", cluster.id)
        before = len(cluster.person_ids)
        clone.person_ids = rules.collapse_id_list(cluster.person_ids, r_id, s_id)
        if len(clone.person_ids) < before:
            ctx.add_item("dna_clusters", cluster.id, f"DNA-kluster {cluster.name or cluster.id}",
                         Disposition.COMBINED, "Personen listas en gång")
        else:
            ctx.add_item("dna_clusters", cluster.id, f"DNA-kluster {cluster.name or cluster.id}",
                         Disposition.REASSIGNED, "Personen flyttas till behållen person")

    # Counts per entity type for the review (22.6) and the same-person match warning.
    owner = {p.id: p.person_id for p in data.dna_profiles}
    profile_ids = {i for i, o in owner.items() if o in (s_id, r_id)}
    matches = [
        m for m in data.dna_matches
        if m.profile1_id in profile_ids or m.profile2_id in profile_ids
    ]
    match_ids = {m.id for m in matches}
    segments = [s for s in data.dna_segments if s.match_id in match_ids]
    tris = [t for t in data.dna_triangulations if any(p in profile_ids for p in t.profile_ids)]
    clusters = [c for c in data.dna_clusters if s_id in c.person_ids or r_id in c.person_ids]
    for key, label, n in (
        ("dna_profiles", "DNA-profiler", len(profile_ids)),
        ("dna_matches", "DNA-träffar", len(matches)),
        ("dna_segments", "DNA-segment", len(segments)),
        ("dna_clusters", "DNA-kluster", len(clusters)),
        ("dna_triangulations", "DNA-triangulering", len(tris)),
    ):
        ctx.add_item("dna_summary", key, label, Disposition.PRESERVED, f"Antal: {n}")
    for m in matches:
        o1, o2 = owner.get(m.profile1_id), owner.get(m.profile2_id)
        if {o1, o2} == {s_id, r_id}:
            ctx.add_conflict(
                SEVERITY_WARNING, "dna_match_same_person", "dna",
                f"DNA-träffen {m.id} kopplar efter sammanslagningen en person till sig själv.",
                (m.id, s_id),
            )


# ---------------------------------------------------------------------------
# Research (22.10 to 22.13)
# ---------------------------------------------------------------------------


@plan_step("research")
def plan_research(ctx: PlanContext) -> None:
    s_id, r_id = ctx.survivor_id, ctx.retired_id
    ctx.research = ctx.work.rewire_research(r_id, s_id)

    for key, category, noun in (
        ("research_case.entities", "research_cases", "Forskningsärende"),
        ("research_hypothesis.entities", "research_hypotheses", "Hypotes"),
    ):
        for obj in _unique_refs(ctx, key):
            ctx.add_item(category, obj.id, f"{noun} {obj.id}", Disposition.REASSIGNED,
                         "Forskningslänkarna skrivs om till behållen person")

    for note in _unique_refs(ctx, "research_note.linked_entities"):
        clone = ctx.work.edit("research_notes", note.id)
        before = len(note.linked_entities)
        clone.linked_entities = rules.collapse_linked_entities(note.linked_entities, r_id, s_id)
        if len(clone.linked_entities) < before:
            ctx.add_item("research_notes", note.id, f"Forskningsanteckning {note.id}",
                         Disposition.COMBINED, "Dubbla personlänkar slås ihop till en")
        else:
            ctx.add_item("research_notes", note.id, f"Forskningsanteckning {note.id}",
                         Disposition.REASSIGNED, "Personlänken flyttas till behållen person")


# ---------------------------------------------------------------------------
# Main person, connection overrides, summary of the remaining rows
# ---------------------------------------------------------------------------


def _plan_main_person(ctx: PlanContext) -> None:
    if ctx.data.project.main_person_id == ctx.retired_id:
        ctx.work.set_scalar("main_person_id", ctx.survivor_id)
        ctx.add_item("project", "main_person_id", "Huvudperson", Disposition.REASSIGNED,
                     "Huvudpersonen flyttas till behållen person")


def _plan_connection_override(ctx: PlanContext) -> None:
    s_id, r_id = ctx.survivor_id, ctx.retired_id
    overrides = ctx.data.connection_overrides
    if r_id not in overrides:
        return
    label = "Anslutningsåsidosättning"
    new = {k: v for k, v in overrides.items() if k != r_id}
    r_val = overrides[r_id]
    if s_id not in overrides:
        new[s_id] = r_val
        ctx.add_item("project", "connection_override", label, Disposition.REASSIGNED,
                     "Åsidosättningen flyttas till behållen person")
    elif overrides[s_id] == r_val:
        ctx.add_item("project", "connection_override", label, Disposition.COMBINED,
                     "Lika åsidosättningar, en behålls")
    else:
        s_val = overrides[s_id]
        chosen = ctx.decisions.connection_override
        if chosen in (s_val, r_val):
            new[s_id] = chosen
            ctx.add_item("project", "connection_override", label,
                         Disposition.EXCLUDED if chosen == s_val else Disposition.REASSIGNED,
                         "Valt av användaren")
        else:
            ctx.add_item("project", "connection_override", label, Disposition.FLAGGED,
                         "Val krävs")
            ctx.add_unresolved(
                "connection_override", "other_refs",
                "Välj anslutningsåsidosättning.", (s_val, r_val),
            )
    ctx.work.set_scalar("connection_overrides", new)


def _plan_reference_summary(ctx: PlanContext) -> None:
    """Count and rule for every row no other requirement covers (22.17)."""
    s_id, r_id = ctx.survivor_id, ctx.retired_id
    for loc in pri.PERSON_REFERENCE_INVENTORY:
        if loc.rule not in _SUMMARY_RULES:
            continue
        r, s = ctx.index.count(loc.key, r_id), ctx.index.count(loc.key, s_id)
        ctx.add_item(
            "references", loc.key, f"{loc.owner_class}.{loc.field_path}",
            Disposition.PRESERVED,
            f"Regel {loc.rule}: {loc.dedupe_statement} Antal: {r} (borttagen), {s} (behållen).",
        )


@plan_step("other_refs")
def plan_other_refs(ctx: PlanContext) -> None:
    _plan_main_person(ctx)
    _plan_connection_override(ctx)
    _plan_reference_summary(ctx)


# ---------------------------------------------------------------------------
# Handler registration (inventory rows this module applies)
# ---------------------------------------------------------------------------

_HANDLERS = {
    "person.profile_media_id": plan_media_sources,
    "media.linked_entities": plan_media_sources,
    "media.mentioned_person_ids": plan_media_sources,
    "media.annotations": plan_media_sources,
    "research_note.linked_entities": plan_research,
    "research_case.entities": plan_research,
    "research_hypothesis.entities": plan_research,
    "dna_profile.person": plan_dna,
    "dna_profile.admin_person": plan_dna,
    "dna_cluster.person_ids": plan_dna,
    "project.main_person_id": _plan_main_person,
    "project.connection_overrides": _plan_connection_override,
}

for _key, _func in _HANDLERS.items():
    pri.register_handler(_key, _func)
