"""Research consistency report ("Forskningskonsistens").

Checks the research collections for broken or doubtful data and notes loose ends,
and reports the findings as structured ReportContent for the report preview
system. It follows the convention of ``geographic.py``: an issue dataclass, a pure
``check_*`` function and a ``generate_*`` function.

Nothing here changes or deletes research data. A case with no linked entity and
no action is valid and is only noted, never removed.

The report framework has no severity type, so severity is expressed the way the
other consistency reports express it: findings are grouped into labelled
sections, here under two headings, "Fel" and "Informationspunkter".

Each issue carries the identity of the affected research entity (case,
hypothesis, action or comment id, and for a broken reference the stored target),
so a later feature can open it from the report. The rendered line stays plain
Swedish text that names the case, so a finding is useful on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from slaktbusken.model.project import ProjectData
from slaktbusken.model.research_case import (
    SUPPORTED_ENTITY_TYPES,
    VALID_HYPOTHESIS_ASSESSMENTS,
    VALID_RESEARCH_PRIORITIES,
    VALID_RESEARCH_STATUSES,
    ResearchCase,
    ResearchEntityLink,
    ResearchHypothesis,
    case_entity_links,
    is_pending,
    is_valid_calendar_date,
)
from slaktbusken.model.validators import research_case_findings
from slaktbusken.reports.content import (
    EmptyStateBlock,
    HeadingBlock,
    ListBlock,
    ReportContent,
)
from slaktbusken.ui.swedish_locale import get_research_entity_type_label

SEVERITY_ERROR = "error"
SEVERITY_INFO = "info"

_EMPTY_SECTION_TEXT = "Inga problem hittades."
_EMPTY_PROJECT_TEXT = "Det finns inga forskningsärenden att kontrollera."

#: How long a hypothesis statement may be before it is shortened in a message.
_SHORT_STATEMENT_LENGTH = 40

#: Error sections in display order: (heading, check types shown under it).
ERROR_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Länkar till objekt som inte finns", ("missing_entity",)),
    ("Länkar med okänd objekttyp", ("unknown_entity_type",)),
    ("Dubbla länkar i samma ärende", ("duplicate_link",)),
    ("Ogiltig status eller prioritet", ("invalid_status", "invalid_priority")),
    ("Ogiltig hypotesbedömning", ("invalid_assessment",)),
    ("Hypoteser utan forskningsärende", ("orphan_hypothesis",)),
    ("Åtgärder utan forskningsärende", ("orphan_action",)),
    ("Åtgärder som hänvisar till saknade källor", ("missing_source",)),
    ("Ogiltiga färdigdatum", ("invalid_completed_date",)),
    ("Ogiltiga kommentarsdatum", ("invalid_comment_date",)),
)

#: Informational sections in display order.
INFO_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Avslutade ärenden med öppna åtgärder", ("closed_with_pending_actions",)),
    ("Ärenden utan kopplat objekt", ("no_linked_entity",)),
    ("Ärenden utan forskningsåtgärder", ("no_actions",)),
)


@dataclass
class ResearchIssue:
    """A single research consistency finding.

    Attributes:
        severity: ``"error"`` or ``"info"``. Used for grouping only.
        check_type: Which check produced it, for example ``"missing_entity"``.
        message: Swedish, render-ready, and naming the affected case.
        case_id: The affected research case, when the finding concerns one.
        hypothesis_id: The affected hypothesis, if any.
        action_id: The affected action, if any.
        comment_id: The affected hypothesis comment, if any.
        ref_entity_type: For a broken reference, the stored target type.
        ref_entity_id: For a broken reference, the stored target id.
    """

    severity: str
    check_type: str
    message: str
    case_id: Optional[str] = None
    hypothesis_id: Optional[str] = None
    action_id: Optional[str] = None
    comment_id: Optional[str] = None
    ref_entity_type: Optional[str] = None
    ref_entity_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Labels used inside messages
# ---------------------------------------------------------------------------


def _case_label(case_id: str, cases_by_id: dict[str, ResearchCase]) -> str:
    """Name a case for a message: its title and id, or just the id."""
    case = cases_by_id.get(case_id)
    if case is not None and case.title.strip():
        return f"{case.title.strip()} ({case.id})"
    return case_id


def _hypothesis_label(hypothesis: ResearchHypothesis) -> str:
    """Name a hypothesis for a message: a short statement and its id."""
    statement = " ".join(hypothesis.statement.split())
    if not statement:
        return hypothesis.id
    if len(statement) > _SHORT_STATEMENT_LENGTH:
        statement = statement[: _SHORT_STATEMENT_LENGTH - 1].rstrip() + "…"
    return f"{statement} ({hypothesis.id})"


def _action_label(action_id: str, title: str) -> str:
    """Name an action for a message: its title and id, or just the id."""
    title = " ".join(title.split())
    return f"{title} ({action_id})" if title else action_id


def _plural_actions(count: int) -> str:
    return f"{count} åtgärd" if count == 1 else f"{count} åtgärder"


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def _entity_ids(data: ProjectData) -> dict[str, set[str]]:
    """Return the ids that exist, per supported entity type, built once."""
    return {
        "person": {x.id for x in data.persons},
        "family": {x.id for x in data.families},
        "event": {x.id for x in data.events},
        "place": {x.id for x in data.places},
        "source": {x.id for x in data.sources},
        "media": {x.id for x in data.media},
        "dna_match": {x.id for x in data.dna_matches},
        "dna_cluster": {x.id for x in data.dna_clusters},
    }


def _check_links(
    links: list[ResearchEntityLink],
    owner: str,
    case_id: str,
    hypothesis_id: Optional[str],
    entity_ids: dict[str, set[str]],
    issues: list[ResearchIssue],
) -> None:
    """Report links of unsupported type and links to entities that no longer exist.

    *owner* is the already-built start of the message, naming the case (and the
    hypothesis, for a hypothesis link).
    """
    for link in links:
        if link.entity_type not in SUPPORTED_ENTITY_TYPES:
            issues.append(
                ResearchIssue(
                    SEVERITY_ERROR,
                    "unknown_entity_type",
                    f"{owner}: länken till '{link.entity_id}' har en okänd "
                    f"objekttyp ('{link.entity_type}').",
                    case_id=case_id,
                    hypothesis_id=hypothesis_id,
                    ref_entity_type=link.entity_type,
                    ref_entity_id=link.entity_id,
                )
            )
        elif link.entity_id.strip() and link.entity_id not in entity_ids[link.entity_type]:
            type_label = get_research_entity_type_label(link.entity_type).lower()
            issues.append(
                ResearchIssue(
                    SEVERITY_ERROR,
                    "missing_entity",
                    f"{owner}: länken till {type_label} '{link.entity_id}' pekar på "
                    f"ett objekt som inte finns.",
                    case_id=case_id,
                    hypothesis_id=hypothesis_id,
                    ref_entity_type=link.entity_type,
                    ref_entity_id=link.entity_id,
                )
            )


def check_research_consistency(data: ProjectData) -> list[ResearchIssue]:
    """Check the research collections and return every finding.

    Errors: links to entities that no longer exist, links of an unsupported
    type, the same entity linked twice in one case, an invalid status, priority
    or assessment, a hypothesis or action whose case is missing, an action
    citing a source that no longer exists, and an invalid completion or comment
    date.

    Informational: a closed case that still has pending actions, a case with no
    linked entity, and a case with no actions. These are valid states and are
    never reported as errors.

    Nothing is changed or deleted.
    """
    issues: list[ResearchIssue] = []
    entity_ids = _entity_ids(data)
    cases_by_id = {case.id: case for case in data.research_cases}

    actions_by_case: dict[str, list] = {}
    for action in data.research_actions:
        actions_by_case.setdefault(action.research_case_id, []).append(action)

    # --- Cases ---------------------------------------------------------------
    for case in data.research_cases:
        label = _case_label(case.id, cases_by_id)

        if case.status not in VALID_RESEARCH_STATUSES:
            issues.append(
                ResearchIssue(
                    SEVERITY_ERROR, "invalid_status",
                    f"{label}: ogiltig status '{case.status}'.", case_id=case.id,
                )
            )
        if case.priority not in VALID_RESEARCH_PRIORITIES:
            issues.append(
                ResearchIssue(
                    SEVERITY_ERROR, "invalid_priority",
                    f"{label}: ogiltig prioritet '{case.priority}'.", case_id=case.id,
                )
            )

        links = case_entity_links(case)
        _check_links(links, label, case.id, None, entity_ids, issues)

        for finding in research_case_findings(case):
            issues.append(
                ResearchIssue(
                    SEVERITY_ERROR, "duplicate_link",
                    f"{label}: ärendet länkar till samma objekt mer än en gång.",
                    case_id=finding.case_id,
                )
            )

        case_actions = actions_by_case.get(case.id, [])
        pending = sum(1 for action in case_actions if is_pending(action))
        if case.status == "closed" and pending:
            issues.append(
                ResearchIssue(
                    SEVERITY_INFO, "closed_with_pending_actions",
                    f"{label}: avslutat ärende med {_plural_actions(pending)} utan färdigdatum.",
                    case_id=case.id,
                )
            )
        if not links:
            issues.append(
                ResearchIssue(
                    SEVERITY_INFO, "no_linked_entity",
                    f"{label}: ärendet saknar kopplat objekt.", case_id=case.id,
                )
            )
        if not case_actions:
            issues.append(
                ResearchIssue(
                    SEVERITY_INFO, "no_actions",
                    f"{label}: ärendet saknar forskningsåtgärder.", case_id=case.id,
                )
            )

    # --- Hypotheses ------------------------------------------------------------
    for hypothesis in data.research_hypotheses:
        hypothesis_label = _hypothesis_label(hypothesis)
        case_label = _case_label(hypothesis.research_case_id, cases_by_id)

        if hypothesis.research_case_id not in cases_by_id:
            issues.append(
                ResearchIssue(
                    SEVERITY_ERROR, "orphan_hypothesis",
                    f"Hypotesen {hypothesis_label}: hör till forskningsärendet "
                    f"'{hypothesis.research_case_id}' som inte finns.",
                    case_id=hypothesis.research_case_id, hypothesis_id=hypothesis.id,
                )
            )

        owner = f"Hypotesen {hypothesis_label} i {case_label}"
        if hypothesis.assessment not in VALID_HYPOTHESIS_ASSESSMENTS:
            issues.append(
                ResearchIssue(
                    SEVERITY_ERROR, "invalid_assessment",
                    f"{owner}: ogiltig bedömning '{hypothesis.assessment}'.",
                    case_id=hypothesis.research_case_id, hypothesis_id=hypothesis.id,
                )
            )

        _check_links(
            hypothesis.linked_entities, owner, hypothesis.research_case_id,
            hypothesis.id, entity_ids, issues,
        )

        for comment in hypothesis.comments:
            if comment.date.strip() and not is_valid_calendar_date(comment.date):
                issues.append(
                    ResearchIssue(
                        SEVERITY_ERROR, "invalid_comment_date",
                        f"{owner}: kommentarens datum '{comment.date}' är inte ett giltigt datum.",
                        case_id=hypothesis.research_case_id, hypothesis_id=hypothesis.id,
                        comment_id=comment.id,
                    )
                )

    # --- Actions ---------------------------------------------------------------
    for action in data.research_actions:
        action_label = _action_label(action.id, action.title)
        case_label = _case_label(action.research_case_id, cases_by_id)

        if action.research_case_id not in cases_by_id:
            issues.append(
                ResearchIssue(
                    SEVERITY_ERROR, "orphan_action",
                    f"Åtgärden {action_label}: hör till forskningsärendet "
                    f"'{action.research_case_id}' som inte finns.",
                    case_id=action.research_case_id, action_id=action.id,
                )
            )

        owner = f"Åtgärden {action_label} i {case_label}"
        if action.completed_date is not None and not is_valid_calendar_date(action.completed_date):
            issues.append(
                ResearchIssue(
                    SEVERITY_ERROR, "invalid_completed_date",
                    f"{owner}: färdigdatumet '{action.completed_date}' är inte ett giltigt datum.",
                    case_id=action.research_case_id, action_id=action.id,
                )
            )

        for source_ref in action.source_refs:
            if source_ref.source_id not in entity_ids["source"]:
                issues.append(
                    ResearchIssue(
                        SEVERITY_ERROR, "missing_source",
                        f"{owner}: hänvisar till källan '{source_ref.source_id}' som inte finns.",
                        case_id=action.research_case_id, action_id=action.id,
                        ref_entity_type="source", ref_entity_id=source_ref.source_id,
                    )
                )

    return issues


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _section_blocks(
    heading: str, check_types: tuple[str, ...], issues: list[ResearchIssue]
) -> list:
    """Render one section: a sub-heading, then its findings or the empty-state text."""
    wanted = set(check_types)
    messages = [issue.message for issue in issues if issue.check_type in wanted]
    blocks: list = [HeadingBlock(text=heading, level=3)]
    if messages:
        blocks.append(ListBlock(items=messages))
    else:
        blocks.append(EmptyStateBlock(text=_EMPTY_SECTION_TEXT))
    return blocks


def generate_research_consistency_report(data: ProjectData) -> ReportContent:
    """Generate the "Forskningskonsistens" report from project data.

    Findings are shown under two headings, "Fel" and "Informationspunkter", each
    holding one labelled section per kind of finding. Every section is shown;
    one without findings says "Inga problem hittades.".
    """
    report = ReportContent(title="Forskningskonsistens")

    if not (data.research_cases or data.research_hypotheses or data.research_actions):
        report.blocks.append(EmptyStateBlock(text=_EMPTY_PROJECT_TEXT))
        return report

    issues = check_research_consistency(data)
    errors = [issue for issue in issues if issue.severity == SEVERITY_ERROR]
    notes = [issue for issue in issues if issue.severity == SEVERITY_INFO]

    report.blocks.append(HeadingBlock(text="Fel", level=2))
    for heading, check_types in ERROR_SECTIONS:
        report.blocks.extend(_section_blocks(heading, check_types, errors))

    report.blocks.append(HeadingBlock(text="Informationspunkter", level=2))
    for heading, check_types in INFO_SECTIONS:
        report.blocks.extend(_section_blocks(heading, check_types, notes))

    return report
