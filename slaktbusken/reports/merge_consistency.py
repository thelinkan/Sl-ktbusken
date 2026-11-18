"""Merge consistency report ("Sammanslagning och dubletter").

Checks merge candidates and merge history for broken or notable data. It follows
the convention of ``research_consistency.py``: an issue dataclass, a pure
``check_*`` function and a ``generate_*`` function. Nothing is changed or
deleted. The functions let unexpected errors propagate, so a caller can show
"Rapporten kunde inte skapas." instead of a partial report.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from slaktbusken.model.merge_candidate import (
    CANDIDATE_ASSESSMENTS,
    assessment_label,
    pair_key,
)
from slaktbusken.model.project import ProjectData
from slaktbusken.model.research_case import case_entity_links
from slaktbusken.model.validators import (
    validate_family,
    validate_merge_candidate_comment,
    validate_merge_history_entry,
)
from slaktbusken.reports.content import (
    EmptyStateBlock,
    HeadingBlock,
    ListBlock,
    ReportContent,
)
from slaktbusken.services.merge_planner_families import find_cycle_through
from slaktbusken.services.redirect_resolution import RedirectResolver

SEVERITY_ERROR = "error"
SEVERITY_INFO = "info"

REPORT_TITLE = "Sammanslagning och dubletter"
REPORT_FAILED_TEXT = "Rapporten kunde inte skapas."

_EMPTY_SECTION_TEXT = "Inga problem hittades."
_EMPTY_PROJECT_TEXT = (
    "Det finns inga sammanslagningskandidater eller sammanslagningar att kontrollera."
)
_MISSING_PERSON_NAME = "Okänd person"

ERROR_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Kandidater som hänvisar till saknade personer", ("missing_person",)),
    ("Kandidater med samma person två gånger", ("same_person",)),
    ("Dubbla kandidater för samma personpar", ("duplicate_pair",)),
    ("Ogiltig bedömning", ("invalid_assessment",)),
    ("Ogiltiga kommentarer", ("invalid_comment",)),
    ("Kandidater med saknat forskningsärende", ("missing_case",)),
    ("Ogiltig sammanslagningshistorik", ("invalid_history",)),
    ("Sammanslagningar vars kvarvarande person saknas", ("history_survivor",)),
    ("Ogiltiga kopplingar för borttagna personer", ("invalid_retired_mapping",)),
    ("Omdirigeringscykler", ("redirect_cycle",)),
    ("Referenser till borttagna personer", ("retired_reference",)),
    ("Ogiltiga släktrelationer", ("invalid_relationship",)),
    ("Problem vid inläsning av sammanslagningsdata", ("load_finding",)),
)

INFO_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Bekräftade dubletter som inte slagits ihop", ("confirmed_not_merged",)),
    ("Inaktiverade kandidater", ("disabled_candidate",)),
    ("Avvisade kandidater", ("rejected_candidate",)),
    ("Genomförda sammanslagningar", ("completed_merge",)),
)


@dataclass
class MergeIssue:
    """A single merge consistency finding.

    Attributes:
        severity: ``"error"`` or ``"info"``. Used for grouping only.
        check_type: Which check produced it, for example ``"missing_person"``.
        message: Swedish, render-ready, with display names and ids.
        candidate_id: The affected merge candidate, if any.
        history_id: The affected merge history entry, if any.
        person_ids: The person ids the finding concerns.
    """

    severity: str
    check_type: str
    message: str
    candidate_id: Optional[str] = None
    history_id: Optional[str] = None
    person_ids: tuple[str, ...] = ()


def check_merge_consistency(data: ProjectData) -> list[MergeIssue]:
    """Check merge candidates and merge history and return every finding.

    Read-only: the project data is never changed.
    """
    issues: list[MergeIssue] = []
    person_names: dict[str, str] = {}
    for person in data.persons:
        name = ""
        for n in person.names:
            text = " ".join(f"{n.given} {n.surname}".split())
            if text:
                name = text
                break
        person_names[person.id] = name or person.id
    person_ids = set(person_names)
    case_ids = {case.id for case in data.research_cases}
    resolver = RedirectResolver(data.merge_history)

    def who(pid: str) -> str:
        if not pid:
            return f"{_MISSING_PERSON_NAME} (saknar id)"
        if pid in person_names:
            return f"{person_names[pid]} ({pid})"
        return f"{_MISSING_PERSON_NAME} ({pid})"

    def cand_label(c) -> str:
        return f"Kandidaten {c.id}: {who(c.person_1_id)} och {who(c.person_2_id)}"

    # --- Candidates ------------------------------------------------------------
    by_pair: dict[tuple[str, str], list] = {}
    for c in data.merge_candidates:
        label = cand_label(c)
        pids = (c.person_1_id, c.person_2_id)
        for pid in pids:
            if not pid or pid not in person_ids:
                issues.append(MergeIssue(
                    SEVERITY_ERROR, "missing_person",
                    f"{label}: personen {who(pid)} finns inte.",
                    candidate_id=c.id, person_ids=pids,
                ))
        if c.person_1_id and c.person_1_id == c.person_2_id:
            issues.append(MergeIssue(
                SEVERITY_ERROR, "same_person",
                f"{label}: båda personerna är samma person.",
                candidate_id=c.id, person_ids=pids,
            ))
        elif c.person_1_id and c.person_2_id:
            by_pair.setdefault(pair_key(c.person_1_id, c.person_2_id), []).append(c)
        if c.assessment not in CANDIDATE_ASSESSMENTS:
            issues.append(MergeIssue(
                SEVERITY_ERROR, "invalid_assessment",
                f"{label}: ogiltig bedömning '{c.assessment}'.",
                candidate_id=c.id, person_ids=pids,
            ))
        for comment in c.comments:
            problems: list[str] = []
            if not comment.id:
                problems.append("saknar id")
            if any("datum" in e.lower() for e in validate_merge_candidate_comment(comment)):
                problems.append(f"har ett ogiltigt datum '{comment.date}'")
            if problems:
                issues.append(MergeIssue(
                    SEVERITY_ERROR, "invalid_comment",
                    f"{label}: kommentaren '{comment.id}' " + " och ".join(problems) + ".",
                    candidate_id=c.id, person_ids=pids,
                ))
        if c.research_case_id is not None and c.research_case_id not in case_ids:
            issues.append(MergeIssue(
                SEVERITY_ERROR, "missing_case",
                f"{label}: forskningsärendet '{c.research_case_id}' finns inte.",
                candidate_id=c.id, person_ids=pids,
            ))

    for key, group in by_pair.items():
        if len(group) > 1:
            ids = ", ".join(c.id for c in group)
            issues.append(MergeIssue(
                SEVERITY_ERROR, "duplicate_pair",
                f"Personparet {who(key[0])} och {who(key[1])} har flera kandidater: {ids}.",
                candidate_id=group[0].id, person_ids=key,
            ))

    # --- History ---------------------------------------------------------------
    ambiguous = set(resolver.ambiguous_ids())
    for e in data.merge_history:
        label = (
            f"Sammanslagningen {e.id}: {who(e.merged_person_id)} in i "
            f"{who(e.surviving_person_id)}"
        )
        pids = (e.surviving_person_id, e.merged_person_id)
        for problem in validate_merge_history_entry(e):
            issues.append(MergeIssue(
                SEVERITY_ERROR, "invalid_history", f"{label}: {problem}",
                history_id=e.id, person_ids=pids,
            ))
        if e.surviving_person_id:
            final = resolver.resolve(e.surviving_person_id)
            if final is not None and final not in person_ids:
                issues.append(MergeIssue(
                    SEVERITY_ERROR, "history_survivor",
                    f"{label}: den kvarvarande personen {who(final)} finns inte.",
                    history_id=e.id, person_ids=pids,
                ))
        if e.merged_person_id and e.merged_person_id in person_ids:
            issues.append(MergeIssue(
                SEVERITY_ERROR, "invalid_retired_mapping",
                f"{label}: den borttagna personen {who(e.merged_person_id)} finns fortfarande.",
                history_id=e.id, person_ids=pids,
            ))
        if e.merged_person_id in ambiguous:
            issues.append(MergeIssue(
                SEVERITY_ERROR, "invalid_retired_mapping",
                f"{label}: {who(e.merged_person_id)} är borttagen i mer än en sammanslagning.",
                history_id=e.id, person_ids=pids,
            ))

    for cycle in resolver.cycles():
        issues.append(MergeIssue(
            SEVERITY_ERROR, "redirect_cycle",
            "Omdirigeringscykel mellan: " + ", ".join(who(p) for p in cycle) + ".",
            person_ids=tuple(cycle),
        ))

    # --- References to retired ids ---------------------------------------------
    retired = {e.merged_person_id for e in data.merge_history if e.merged_person_id}
    retired -= person_ids  # a still-existing person is reported above, not as dangling

    def ref(where: str, pid: Optional[str]) -> None:
        if pid and pid in retired:
            issues.append(MergeIssue(
                SEVERITY_ERROR, "retired_reference",
                f"{where} pekar på den borttagna personen {who(pid)}.",
                person_ids=(pid,),
            ))

    ref("Projektets huvudperson", data.project.main_person_id)
    for fam in data.families:
        for partner in fam.partners:
            ref(f"Familjen {fam.id} (partner)", partner.person_id)
        for child in fam.children:
            ref(f"Familjen {fam.id} (barn)", child)
        for link in fam.parent_child_links:
            ref(f"Familjen {fam.id} (föräldrabarnlänk)", link.parent_id)
            ref(f"Familjen {fam.id} (föräldrabarnlänk)", link.child_id)
    for ev in data.events:
        for part in ev.participants:
            ref(f"Händelsen {ev.id}", part.person_id)
    for res in data.residences:
        ref(f"Boendet {res.id}", getattr(res, "person_id", None))
    for prof in data.dna_profiles:
        ref(f"DNA-profilen {prof.id}", prof.person_id)
        ref(f"DNA-profilen {prof.id}", prof.admin_person_id)
    for cl in data.dna_clusters:
        for pid in cl.person_ids:
            ref(f"DNA-klustret {cl.id}", pid)
    for m in data.media:
        for le in m.linked_entities:
            if le.entity_type == "person":
                ref(f"Mediet {m.id}", le.entity_id)
        for pid in m.mentioned_person_ids:
            ref(f"Mediet {m.id}", pid)
        for an in m.annotations:
            if an.entity_type == "person":
                ref(f"Mediet {m.id} (markering)", an.entity_id)
    for case in data.research_cases:
        for link in case_entity_links(case):
            if link.entity_type == "person":
                ref(f"Forskningsärendet {case.id}", link.entity_id)
    for hyp in data.research_hypotheses:
        for link in hyp.linked_entities:
            if link.entity_type == "person":
                ref(f"Hypotesen {hyp.id}", link.entity_id)

    # --- Relationship structure ------------------------------------------------
    for fam in data.families:
        for problem in validate_family(fam, person_ids | retired):
            issues.append(MergeIssue(
                SEVERITY_ERROR, "invalid_relationship",
                f"Familjen {fam.id}: {problem}",
            ))
    parents_by_child: dict[str, set[str]] = {}
    for fam in data.families:
        for link in fam.parent_child_links:
            if link.parent_id:
                parents_by_child.setdefault(link.child_id, set()).add(link.parent_id)
    reported_cycles: set[frozenset[str]] = set()
    for child in sorted(parents_by_child):
        chain = find_cycle_through(parents_by_child, child)
        if chain is not None:
            nodes = frozenset(chain)
            if nodes not in reported_cycles:
                reported_cycles.add(nodes)
                issues.append(MergeIssue(
                    SEVERITY_ERROR, "invalid_relationship",
                    "Förälder-barn-cykel: " + " → ".join(who(p) for p in chain) + ".",
                    person_ids=tuple(chain),
                ))

    # --- Load findings -----------------------------------------------------------
    for lf in data.merge_load_findings:
        issues.append(MergeIssue(
            SEVERITY_ERROR, "load_finding",
            f"Posten {lf.entry_id or '(saknar id)'} i {lf.section}: {lf.kind} "
            f"(fält: {', '.join(lf.fields) if lf.fields else 'okänt'}).",
        ))

    # --- Information -------------------------------------------------------------
    for c in data.merge_candidates:
        label = cand_label(c)
        pids = (c.person_1_id, c.person_2_id)
        if c.assessment == "confirmed":
            issues.append(MergeIssue(
                SEVERITY_INFO, "confirmed_not_merged",
                f"{label}: bekräftad dublett som inte är sammanslagen "
                f"({assessment_label(c.assessment)}).",
                candidate_id=c.id, person_ids=pids,
            ))
        if not c.enabled:
            issues.append(MergeIssue(
                SEVERITY_INFO, "disabled_candidate", f"{label}: kandidaten är inaktiverad.",
                candidate_id=c.id, person_ids=pids,
            ))
        if c.assessment == "rejected":
            issues.append(MergeIssue(
                SEVERITY_INFO, "rejected_candidate", f"{label}: kandidaten är avvisad.",
                candidate_id=c.id, person_ids=pids,
            ))
    for e in data.merge_history:
        issues.append(MergeIssue(
            SEVERITY_INFO, "completed_merge",
            f"Sammanslagningen {e.id}: {who(e.merged_person_id)} slogs ihop med "
            f"{who(e.surviving_person_id)} ({e.merge_date}).",
            history_id=e.id, person_ids=(e.surviving_person_id, e.merged_person_id),
        ))

    return issues


def _section_blocks(
    heading: str, check_types: tuple[str, ...], issues: list[MergeIssue]
) -> list:
    wanted = set(check_types)
    messages = [i.message for i in issues if i.check_type in wanted]
    blocks: list = [HeadingBlock(text=heading, level=3)]
    if messages:
        blocks.append(ListBlock(items=messages))
    else:
        blocks.append(EmptyStateBlock(text=_EMPTY_SECTION_TEXT))
    return blocks


def generate_merge_consistency_report(data: ProjectData) -> ReportContent:
    """Generate the "Sammanslagning och dubletter" report from project data.

    Raises whatever an unexpected failure raises; no partial report is returned.
    """
    report = ReportContent(title=REPORT_TITLE)

    if not (data.merge_candidates or data.merge_history):
        report.blocks.append(EmptyStateBlock(text=_EMPTY_PROJECT_TEXT))
        return report

    issues = check_merge_consistency(data)
    errors = [i for i in issues if i.severity == SEVERITY_ERROR]
    notes = [i for i in issues if i.severity == SEVERITY_INFO]

    report.blocks.append(HeadingBlock(text="Fel", level=2))
    for heading, check_types in ERROR_SECTIONS:
        report.blocks.extend(_section_blocks(heading, check_types, errors))

    report.blocks.append(HeadingBlock(text="Informationspunkter", level=2))
    for heading, check_types in INFO_SECTIONS:
        report.blocks.extend(_section_blocks(heading, check_types, notes))

    return report
