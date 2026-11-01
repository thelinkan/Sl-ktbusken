"""Candidate redirect and collision after a person merge (Requirement 29).

Qt-free and pure: the input candidates are never modified. The result holds the
new active candidate list (copies), the candidates archived with their role and
the ids of redirected and colliding candidates.

Determinism: candidates are processed sorted by the numeric suffix of their id,
and every other person X is handled independently, so the result does not
depend on the storage order of the input list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Callable, Optional

from slaktbusken.model.merge_candidate import (
    ArchivedCandidate,
    MergeCandidate,
    MergeCandidateComment,
    assessment_label,
    pair_key,
)


@dataclass
class CandidateRedirectResult:
    """Outcome of :func:`plan_candidate_changes`."""

    #: Active candidates after the merge, in the storage order of the input.
    active: list[MergeCandidate] = field(default_factory=list)
    #: Candidates removed from the active list, in full original content.
    archived: list[ArchivedCandidate] = field(default_factory=list)
    #: Ids of candidates redirected without collision.
    redirected: list[str] = field(default_factory=list)
    #: Ids of redirected candidates that collided with an existing candidate.
    collided: list[str] = field(default_factory=list)
    #: Number of comments created by the algorithm.
    comments_added: int = 0


def _id_key(cand: MergeCandidate) -> tuple[int, str]:
    match = re.search(r"(\d+)$", cand.id or "")
    return (int(match.group(1)) if match else -1, cand.id or "")


def _copy(cand: MergeCandidate) -> MergeCandidate:
    return replace(cand, comments=[replace(c) for c in cand.comments])


def _archive(cand: MergeCandidate, role: str) -> ArchivedCandidate:
    return ArchivedCandidate(
        id=cand.id,
        person_1_id=cand.person_1_id,
        person_2_id=cand.person_2_id,
        assessment=cand.assessment,
        enabled=cand.enabled,
        research_case_id=cand.research_case_id,
        comments=[replace(c) for c in cand.comments],
        role=role,
    )


def redirect_comment_text(retired: str, survivor: str, original_assessment: str) -> str:
    return (
        f"Omdirigerad vid sammanslagning av {retired} in i {survivor}. "
        f"Ursprunglig bedömning: {assessment_label(original_assessment)}."
    )


def _yes_no(value: bool) -> str:
    return "ja" if value else "nej"


def _case(value) -> str:
    return value or "inget"


def explanatory_comment_text(
    retired: str, survivor: str, existing_id: str, redirected_id: str,
    original_existing: str, original_redirected: str,
    assessments_differ: bool,
    enabled: tuple[bool, bool] | None = None,
    cases: tuple[Optional[str], Optional[str]] | None = None,
) -> str:
    """The single explanatory comment of a collision (Requirement 29.13).

    *enabled* and *cases* are ``(existing, redirected)`` pairs, given only when
    the two values differ.
    """
    prefix = f"Sammanslagning av {retired} in i {survivor}:"
    if assessments_differ:
        text = (
            f"{prefix} bedömningarna {assessment_label(original_existing)} ({existing_id}) "
            f"och {assessment_label(original_redirected)} ({redirected_id}) "
            "stämde inte överens. Bedömningen återställd till Ej granskad."
        )
    else:
        text = f"{prefix} kandidaterna {existing_id} och {redirected_id} skilde sig åt."
    if enabled is not None:
        text += (
            f" Aktiv: {existing_id} {_yes_no(enabled[0])}, "
            f"{redirected_id} {_yes_no(enabled[1])}."
        )
    if cases is not None:
        text += (
            f" Forskningsärende: {existing_id} {_case(cases[0])}, "
            f"{redirected_id} {_case(cases[1])}."
        )
    return text


def effective_redirected_assessment(assessment: str) -> str:
    """The only change a redirect makes: ``confirmed`` becomes ``possible``."""
    return "possible" if assessment == "confirmed" else assessment


def plan_candidate_changes(
    candidates: list[MergeCandidate],
    survivor: str,
    retired: str,
    merge_date: str,
    new_comment_id: Callable[[], str],
) -> CandidateRedirectResult:
    """Apply Requirement 29 to *candidates* for a merge of *retired* into *survivor*."""
    result = CandidateRedirectResult()
    merged_pair = pair_key(survivor, retired)

    direct: list[MergeCandidate] = []
    selfs: list[MergeCandidate] = []
    touching: dict[str, list[MergeCandidate]] = {}
    for cand in candidates:
        ids = (cand.person_1_id, cand.person_2_id)
        if pair_key(*ids) == merged_pair:
            direct.append(cand)
        elif ids[0] == retired and ids[1] == retired:
            selfs.append(cand)
        elif retired in ids:
            other = ids[1] if ids[0] == retired else ids[0]
            touching.setdefault(other, []).append(cand)

    archived_ids: set[str] = set()
    replacements: dict[int, MergeCandidate] = {}  # id(original) -> new object

    for cand in sorted(direct, key=_id_key):
        result.archived.append(_archive(cand, "direct"))
        archived_ids.add(id(cand))
    for cand in sorted(selfs, key=_id_key):
        result.archived.append(_archive(cand, "self_after_redirect"))
        archived_ids.add(id(cand))

    def comment(text: str) -> MergeCandidateComment:
        result.comments_added += 1
        return MergeCandidateComment(id=new_comment_id(), date=merge_date, text=text)

    for other in sorted(touching):
        # The existing candidate for (survivor, other): lowest id, not touching retired.
        existing_originals = sorted(
            (
                c for c in candidates
                if pair_key(c.person_1_id, c.person_2_id) == pair_key(survivor, other)
            ),
            key=_id_key,
        )
        existing_orig = existing_originals[0] if existing_originals else None
        existing = _copy(existing_orig) if existing_orig is not None else None

        for cand in sorted(touching[other], key=_id_key):
            original_assessment = cand.assessment
            if existing is None:
                moved = _copy(cand)
                if moved.person_1_id == retired:
                    moved.person_1_id = survivor
                if moved.person_2_id == retired:
                    moved.person_2_id = survivor
                moved.assessment = effective_redirected_assessment(original_assessment)
                moved.comments.append(
                    comment(redirect_comment_text(retired, survivor, original_assessment))
                )
                replacements[id(cand)] = moved
                result.redirected.append(cand.id)
                existing = moved
                continue

            # Collision: fixed order of operations of Requirement 29.6.
            orig_e = existing.assessment
            orig_c = original_assessment
            eff_c = effective_redirected_assessment(orig_c)
            eff_e = orig_e
            assessments_differ = eff_c != eff_e
            enabled_differs = existing.enabled != cand.enabled
            case_differs = existing.research_case_id != cand.research_case_id
            enabled_pair = (existing.enabled, cand.enabled) if enabled_differs else None
            case_pair = (
                (existing.research_case_id, cand.research_case_id) if case_differs else None
            )
            if not existing.research_case_id:
                existing.research_case_id = cand.research_case_id
            existing.assessment = "unreviewed" if assessments_differ else eff_e
            existing.comments.extend(replace(c) for c in cand.comments)
            existing.comments.append(
                comment(redirect_comment_text(retired, survivor, orig_c))
            )
            if assessments_differ or enabled_differs or case_differs:
                existing.comments.append(
                    comment(
                        explanatory_comment_text(
                            retired, survivor, existing.id, cand.id, orig_e, orig_c,
                            assessments_differ, enabled_pair, case_pair,
                        )
                    )
                )
            result.archived.append(_archive(cand, "collision"))
            archived_ids.add(id(cand))
            result.collided.append(cand.id)
            if existing_orig is not None and existing_orig is not existing:
                replacements[id(existing_orig)] = existing

    # Existing candidates modified by collisions are keyed by their original.
    for cand in candidates:
        if id(cand) in archived_ids:
            continue
        result.active.append(replacements.get(id(cand), _copy(cand)))
    return result
