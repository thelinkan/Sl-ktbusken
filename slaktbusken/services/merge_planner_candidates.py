"""Planning steps for candidates, history entry and identity (slots ``candidates``, ``identity``).

Qt-free. Requirements 29 and 30.1/30.10, design sections 11 and 10.4. The steps
read ``ctx.data`` and ``ctx.translation`` and record their result only in the
plan:

* ``change_set`` holds the replaced, removed (archived) candidates and the new
  ``MergeHistoryEntry`` (``added["merge_history"]``), and the preview
  ``id_high_water_marks`` (scalar).
* ``identity_ops`` describes the translation changes (``new_aliases``,
  ``rewritten_aliases``); the merge engine applies them.

The history entry id and the new comment ids come from a
``ProtectedIdGenerator`` running on a scratch copy, so ``ctx.data`` is untouched.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Any

from slaktbusken.model.event import SourceRef
from slaktbusken.model.merge_candidate import (
    MergedIdentityMapping,
    MergeHistoryEntry,
)
from slaktbusken.persistence.translation_io import IdentityAlias
from slaktbusken.services import person_reference_index as pri
from slaktbusken.services.id_registry import ProtectedIdGenerator
from slaktbusken.services.merge_candidate_redirect import plan_candidate_changes
from slaktbusken.services.merge_planner import (
    CandidateOps,
    Disposition,
    IdentityOps,
    PlanContext,
    PlanItem,
    _count_instances,
    plan_step,
)
from slaktbusken.services.person_summary import PersonSummaryIndex

_SCRATCH = "id_scratch"
_ENTRY = "history_entry"


def _merge_date(ctx: PlanContext) -> str:
    return ctx.state.get("merge_date") or date.today().isoformat()


def _scratch(ctx: PlanContext):
    """A throw-away ProjectData whose id marks the generator may advance."""
    if _SCRATCH not in ctx.state:
        ctx.state[_SCRATCH] = replace(
            ctx.data, id_high_water_marks=dict(ctx.data.id_high_water_marks)
        )
    return ctx.state[_SCRATCH]


def _generate(ctx: PlanContext, entity_type: str) -> str:
    scratch = _scratch(ctx)
    new_id = ProtectedIdGenerator(scratch).generate(entity_type)
    ctx.work.set_scalar("id_high_water_marks", dict(scratch.id_high_water_marks))
    return new_id


def history_entry(ctx: PlanContext) -> MergeHistoryEntry:
    """The history entry of this plan (created once, then reused)."""
    entry = ctx.state.get(_ENTRY)
    if entry is None:
        summaries = PersonSummaryIndex.build(ctx.data)
        retired_summary = summaries.get(ctx.retired_id)
        entry = MergeHistoryEntry(
            id=_generate(ctx, "merge_history"),
            surviving_person_id=ctx.survivor_id,
            merged_person_id=ctx.retired_id,
            # Empty for a nameless person, so views show "Okänd person" (36.3).
            merged_person_name=retired_summary.name if retired_summary else "",
            merged_person_lifespan=summaries.lifespan_text(ctx.retired_id),
            merge_date=_merge_date(ctx),
        )
        ctx.state[_ENTRY] = entry
        ctx.work.add("merge_history", entry)
    return entry


# ---------------------------------------------------------------------------
# Candidates (Requirement 29)
# ---------------------------------------------------------------------------


@plan_step("candidates")
def plan_candidates(ctx: PlanContext) -> None:
    entry = history_entry(ctx)
    originals = list(ctx.data.merge_candidates)
    result = plan_candidate_changes(
        originals, ctx.survivor_id, ctx.retired_id, _merge_date(ctx),
        lambda: _generate(ctx, "merge_candidate_comment"),
    )
    entry.archived_candidates = list(result.archived)
    direct = [a for a in result.archived if a.role == "direct"]
    if direct:
        entry.merge_candidate_id = direct[0].id

    archived_ids = {a.id for a in result.archived}
    active_by_id = {c.id: c for c in result.active}
    for cand in originals:
        if cand.id in archived_ids:
            ctx.work.remove("merge_candidates", cand.id)
            continue
        new = active_by_id[cand.id]
        if new != cand:
            clone = ctx.work.edit("merge_candidates", cand.id)
            clone.person_1_id = new.person_1_id
            clone.person_2_id = new.person_2_id
            clone.assessment = new.assessment
            clone.enabled = new.enabled
            clone.research_case_id = new.research_case_id
            clone.comments = new.comments

    roles = {a.id: a.role for a in result.archived}
    for cand_id in sorted(set(result.redirected)):
        ctx.add_item("candidates", cand_id, f"Kandidat {cand_id}", Disposition.REASSIGNED,
                     "Omdirigeras till behållen person")
    for cand_id in sorted(roles):
        ctx.add_item(
            "candidates", cand_id, f"Kandidat {cand_id}", Disposition.PRESERVED,
            {
                "direct": "Arkiveras i sammanslagningshistoriken (direkt kandidat)",
                "collision": "Arkiveras i sammanslagningshistoriken (krock med befintlig kandidat)",
                "self_after_redirect": "Arkiveras i sammanslagningshistoriken (skulle bli en kandidat med samma person)",
            }[roles[cand_id]],
        )

    ctx.candidate_ops = CandidateOps(
        redirected=tuple(result.redirected),
        collided=tuple(result.collided),
        archived=tuple(a.id for a in result.archived),
    )
    # Archived candidates leave the active list; their comments are kept in the
    # history entry (documented deduplication in the ledger).
    removed_comments = sum(len(c.comments) for c in originals) - sum(
        len(c.comments) for c in result.active
    )
    if result.archived:
        ctx.note_dedup("candidates", len(result.archived))
    if removed_comments:
        ctx.note_dedup("candidate_comments", removed_comments)


# ---------------------------------------------------------------------------
# Identity (Requirement 30.1, 30.10)
# ---------------------------------------------------------------------------


@plan_step("identity")
def plan_identity(ctx: PlanContext) -> None:
    entry = history_entry(ctx)
    translation: Any = ctx.translation
    mappings = [
        m for m in (getattr(translation, "persons", None) or [])
        if m.app_id == ctx.retired_id
    ]
    aliases = [
        a for a in (getattr(translation, "person_aliases", None) or [])
        if a.person_id == ctx.retired_id
    ]
    new_aliases = tuple(
        IdentityAlias(m.gedcom_id, m.fingerprint, ctx.survivor_id, entry.id)
        for m in mappings
    )
    rewritten = tuple(
        IdentityAlias(a.gedcom_id, a.fingerprint, ctx.survivor_id, a.merge_id)
        for a in aliases
    )
    entry.identity_mappings = [
        MergedIdentityMapping(m.gedcom_id, m.fingerprint) for m in mappings
    ]
    ctx.identity_ops = IdentityOps(
        mappings_moved=tuple(m.gedcom_id for m in mappings),
        aliases_rewritten=tuple(a.gedcom_id for a in aliases),
        new_aliases=new_aliases,
        rewritten_aliases=rewritten,
    )
    seen: set[tuple[str, str]] = set()
    for category, gedcom_ids, detail in (
        ("identity_mappings", [m.gedcom_id for m in mappings],
         "Flyttas till identitetsalias för behållen person"),
        ("identity_aliases", [a.gedcom_id for a in aliases],
         "Alias skrivs om till behållen person"),
    ):
        for gedcom_id in gedcom_ids:
            if (category, gedcom_id) not in seen:
                seen.add((category, gedcom_id))
                ctx.add_item(category, gedcom_id, gedcom_id, Disposition.REASSIGNED, detail)
    # Last planning step: the plan is complete, so the Merge_Summary is fixed here.
    entry.summary_lines = merge_summary_lines(ctx)


# ---------------------------------------------------------------------------
# Merge_Summary (Requirement 36.1, design 15.12)
# ---------------------------------------------------------------------------

#: ``(category, detail)`` of attribute items that record a decision of the user
#: for conflicting single-valued fields (sex, title, occupation, profile photo,
#: notes, connection override).
_DECISION_DETAILS = frozenset({
    "Den andra personens värde utesluts efter val",
    "Den andra personens värde väljs",
    "Valt av användaren",
    "Den ena personens anteckningar utesluts efter val",
})
_MOVED = (Disposition.REASSIGNED, Disposition.COMBINED)


def merge_summary_lines(ctx: PlanContext) -> list[str]:
    """Swedish summary of what the plan combines, derived from ``ctx.items``.

    Pure and deterministic: the same plan gives the same lines. Only counts are
    written, no names, so no personal data beyond the entry's own fields.
    """
    items = ctx.items
    r_id = ctx.retired_id

    def moved(category: str) -> list[PlanItem]:
        return [i for i in items if i.category == category and i.disposition in _MOVED]

    events_by_id = {e.id: e for e in ctx.data.events}
    residences_by_id = {f.id: f for f in ctx.data.residences}
    moved_events = moved("events")
    moved_residences = moved("residences")
    citations = sum(
        _count_instances(events_by_id[i.item_id], SourceRef)
        for i in moved_events if i.item_id in events_by_id
    ) + sum(
        _count_instances(residences_by_id[i.item_id], SourceRef)
        for i in moved_residences if i.item_id in residences_by_id
    )
    names = sum(
        1 for i in items
        if i.category == "names" and i.item_id.startswith(f"{r_id}:")
        and i.disposition is Disposition.REASSIGNED
    )
    decisions = sum(
        1 for i in items
        if i.category in ("attributes", "project") and i.detail in _DECISION_DETAILS
    )
    notes_joined = any(
        i.category == "attributes" and i.item_id == "notes"
        and i.disposition is Disposition.COMBINED
        and i.detail.startswith("Anteckningarna slås ihop")
        for i in items
    )
    ops = ctx.candidate_ops
    return [
        f"Namn tillagda: {names}",
        f"Händelser flyttade: {len(moved_events)}",
        f"Boenden flyttade: {len(moved_residences)}",
        f"Källhänvisningar flyttade: {citations}",
        f"Mediaobjekt med flyttade personlänkar: {len(moved('media'))}",
        f"Familjer berörda: {len(moved('families'))}",
        f"Forskningslänkar flyttade: {ctx.research.links_rewired}",
        f"Beslut för motstridiga fält: {decisions}",
        f"Anteckningar sammanslagna: {'ja' if notes_joined else 'nej'}",
        f"Kandidater omdirigerade: {len(set(ops.redirected))}",
        f"Kandidater arkiverade: {len(ops.archived)}",
    ]


# ---------------------------------------------------------------------------
# Handler registration (inventory rows this module applies)
# ---------------------------------------------------------------------------

for _key, _func in (
    ("merge_candidate.persons", plan_candidates),
    ("translation.person_mappings", plan_identity),
    ("translation.identity_aliases", plan_identity),
):
    pri.register_handler(_key, _func)
