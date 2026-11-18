"""Merge candidate operations (Qt-free, no I/O).

Every function validates first and changes the project only when all checks
pass. Edits use copy-validate-swap: a modified copy of the candidate is built
and validated, then replaces the stored object by index. A failure leaves the
project unchanged. Nothing here reads or modifies a ``Person``, and candidates
are only created by explicit calls, never from computed similarity.

The functions do not touch the dirty flag or notify anybody; ``ProjectService``
does that after a successful call.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

from slaktbusken.model.merge_candidate import (
    MergeCandidate,
    MergeCandidateComment,
    pair_key,
)
from slaktbusken.model.project import ProjectData
from slaktbusken.model.research_case import ResearchCase, ResearchEntityLink
from slaktbusken.model.validators import (
    validate_merge_candidate,
    validate_merge_candidate_comment,
    validate_research_case,
)
from slaktbusken.services.id_registry import ProtectedIdGenerator
from slaktbusken.services.research_service import ResearchIdGenerator

MSG_SELF_PAIR = "En person kan inte vara kandidat till sig själv."
MSG_UNKNOWN_PERSON = "Personen finns inte: {id}."
MSG_DUPLICATE_PAIR = "Paret är redan registrerat som sammanslagningskandidat."
MSG_UNKNOWN_CANDIDATE = "Ingen sammanslagningskandidat med id {id!r}."
MSG_UNKNOWN_COMMENT = "Ingen kommentar med id {id!r}."


class CandidateError(Exception):
    """Raised when a candidate operation is rejected; carries Swedish messages."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def find_candidate_by_pair(
    data: ProjectData, a: str, b: str
) -> Optional[MergeCandidate]:
    """Return the candidate for the unordered pair, enabled or not."""
    key = pair_key(a, b)
    for cand in data.merge_candidates:
        if pair_key(cand.person_1_id, cand.person_2_id) == key:
            return cand
    return None


def _index(data: ProjectData, candidate_id: str) -> int:
    for i, cand in enumerate(data.merge_candidates):
        if cand.id == candidate_id:
            return i
    raise KeyError(MSG_UNKNOWN_CANDIDATE.format(id=candidate_id))


def _copy(cand: MergeCandidate) -> MergeCandidate:
    return replace(cand, comments=[replace(c) for c in cand.comments])


def _swap(
    data: ProjectData,
    index: int,
    new: MergeCandidate,
    valid_case_ids: Optional[set[str]] = None,
) -> MergeCandidate:
    errors = validate_merge_candidate(new, None, valid_case_ids)
    if errors:
        raise CandidateError(errors)
    data.merge_candidates[index] = new
    return new


def get_or_create_candidate(
    data: ProjectData, person_1_id: str, person_2_id: str
) -> tuple[MergeCandidate, bool]:
    """Return ``(candidate, created)``; an existing pair is returned, not raised."""
    existing = find_candidate_by_pair(data, person_1_id, person_2_id)
    if existing is not None and person_1_id != person_2_id:
        return existing, False
    return create_candidate(data, person_1_id, person_2_id), True


def create_candidate(
    data: ProjectData, person_1_id: str, person_2_id: str
) -> MergeCandidate:
    """Create an unreviewed, enabled candidate for an explicit pair.

    Raises:
        CandidateError: Equal ids, unknown person or an already registered pair.
    """
    if person_1_id == person_2_id:
        raise CandidateError([MSG_SELF_PAIR])
    person_ids = {p.id for p in data.persons}
    unknown = [pid for pid in (person_1_id, person_2_id) if pid not in person_ids]
    if unknown:
        raise CandidateError([MSG_UNKNOWN_PERSON.format(id=pid) for pid in unknown])
    if find_candidate_by_pair(data, person_1_id, person_2_id) is not None:
        raise CandidateError([MSG_DUPLICATE_PAIR])
    candidate = MergeCandidate(
        id="", person_1_id=person_1_id, person_2_id=person_2_id
    )
    errors = validate_merge_candidate(candidate, person_ids, None)
    if errors:
        raise CandidateError(errors)
    candidate.id = ProtectedIdGenerator(data).generate("merge_candidate")
    data.merge_candidates.append(candidate)
    return candidate


def set_assessment(
    data: ProjectData, candidate_id: str, assessment: str
) -> MergeCandidate:
    """Change the assessment only; comments and everything else stay as they are."""
    i = _index(data, candidate_id)
    new = _copy(data.merge_candidates[i])
    new.assessment = assessment
    return _swap(data, i, new)


def set_enabled(data: ProjectData, candidate_id: str, enabled: bool) -> MergeCandidate:
    """Enable or disable a candidate (it is never deleted by this)."""
    i = _index(data, candidate_id)
    new = _copy(data.merge_candidates[i])
    new.enabled = enabled
    return _swap(data, i, new)


def set_research_case(
    data: ProjectData, candidate_id: str, case_id: Optional[str]
) -> MergeCandidate:
    """Link a candidate to an existing research case, or unlink with ``None``."""
    i = _index(data, candidate_id)
    new = _copy(data.merge_candidates[i])
    new.research_case_id = case_id
    return _swap(data, i, new, {c.id for c in data.research_cases})


MSG_CASE_NOT_CREATED = "Forskningsärendet skapades inte: {reason}"
MSG_CASE_TITLE = "Möjlig sammanslagning: {a} och {b}"
MSG_CASE_TITLE_REQUIRED = "Forskningsärendet måste ha en rubrik."


def create_research_case_for_candidate(
    data: ProjectData, candidate_id: str, title: str = ""
) -> ResearchCase:
    """Create a research case for a candidate's pair as one all-or-nothing step.

    Creates one ``ResearchCase`` with exactly two person ``ResearchEntityLink``
    entries (one per person) and sets ``research_case_id`` on the candidate.
    Any failure restores cases, candidate and id high-water marks.

    No assessment is copied between the candidate and the case; the case is
    created with the default hypothesis-free state.

    Raises:
        KeyError: Unknown candidate.
        CandidateError: Validation or any other failure; nothing was changed.
    """
    i = _index(data, candidate_id)
    cand = data.merge_candidates[i]
    old_cand = cand
    old_marks = dict(data.id_high_water_marks)
    cases_before = len(data.research_cases)
    try:
        names = {p.id: p.id for p in data.persons}
        case_title = title.strip() or MSG_CASE_TITLE.format(
            a=names.get(cand.person_1_id, cand.person_1_id),
            b=names.get(cand.person_2_id, cand.person_2_id),
        )
        case = ResearchCase(
            id="",
            title=case_title,
            linked_entities=[
                ResearchEntityLink("person", cand.person_1_id, "candidate"),
                ResearchEntityLink("person", cand.person_2_id, "candidate"),
            ],
        )
        errors = validate_research_case(case, None)
        if errors:
            raise CandidateError(errors)
        case.id = ResearchIdGenerator(data).generate("research_case")
        data.research_cases.append(case)
        set_research_case(data, candidate_id, case.id)
        return case
    except Exception as exc:
        del data.research_cases[cases_before:]
        data.merge_candidates[i] = old_cand
        data.id_high_water_marks.clear()
        data.id_high_water_marks.update(old_marks)
        if isinstance(exc, CandidateError):
            errors = [MSG_CASE_NOT_CREATED.format(reason=m) for m in exc.errors]
        else:
            errors = [MSG_CASE_NOT_CREATED.format(reason=str(exc))]
        raise CandidateError(errors) from exc


def add_comment(
    data: ProjectData, candidate_id: str, date: str, text: str
) -> MergeCandidateComment:
    """Append a comment with a new protected id."""
    i = _index(data, candidate_id)
    comment = MergeCandidateComment(id="", date=date or "", text=text)
    errors = validate_merge_candidate_comment(comment)
    if errors:
        raise CandidateError(errors)
    new = _copy(data.merge_candidates[i])
    new.comments.append(comment)
    # Check the count limit before an id is issued.
    errors = validate_merge_candidate(new)
    if errors:
        raise CandidateError(errors)
    comment.id = ProtectedIdGenerator(data).generate("merge_candidate_comment")
    _swap(data, i, new)
    return comment


def update_comment(
    data: ProjectData, candidate_id: str, comment_id: str, date: str, text: str
) -> MergeCandidateComment:
    """Replace date and text of one comment; its id and position are kept."""
    i = _index(data, candidate_id)
    new = _copy(data.merge_candidates[i])
    for j, existing in enumerate(new.comments):
        if existing.id == comment_id:
            break
    else:
        raise KeyError(MSG_UNKNOWN_COMMENT.format(id=comment_id))
    edited = MergeCandidateComment(id=comment_id, date=date or "", text=text)
    errors = validate_merge_candidate_comment(edited)
    if errors:
        raise CandidateError(errors)
    new.comments[j] = edited
    _swap(data, i, new)
    return edited


def delete_comment(data: ProjectData, candidate_id: str, comment_id: str) -> bool:
    """Delete one comment. Returns False (a no-op) when it does not exist."""
    i = _index(data, candidate_id)
    cand = data.merge_candidates[i]
    if not any(c.id == comment_id for c in cand.comments):
        return False
    new = _copy(cand)
    new.comments = [c for c in new.comments if c.id != comment_id]
    _swap(data, i, new)
    return True
