# Requirements Document

## Introduction

Släktbusken records genealogical facts — persons, families, events, places, sources, media, and DNA — but offers no structured place to record the *research* behind those facts. A genealogist investigating "who was Anna Andersdotter's father?" today has only free-text notes (the existing `ResearchNote` entity: a title, a body, and a loose list of `LinkedEntity` links). That cannot express a research question with competing hypotheses, each weighed by the researcher, nor a plan of research actions that move from "to do" to "done" while citing the volumes examined — including the ones that turned up nothing.

This feature introduces a project-level **Research Case** system layered onto the existing project model. A Research Case (Swedish "Forskningsärende") is a research question that may concern any number of project entities at once. It holds zero or more **Hypotheses** (possible explanations, each manually assessed and annotated with dated comments) and zero or more **Research Actions** (planned or completed work, each able to cite existing sources). The system is deliberately *descriptive*: it never mutates a genealogical fact as a side effect of a hypothesis or a conclusion. Closing a case does not mark its actions done; rejecting a hypothesis does not delete it; deleting a person does not delete the research about that person.

The feature is a shared system, not per-editor notes. One Research Case is visible and editable from every entity it links to — the person editor, place editor, event editor, source editor, media editor, and the DNA views — and from a central **Research Overview** window reached from a new **Forskning** menu. A shared research index answers "which cases link to this entity" and "which actions cite this source" efficiently, so person-list rows and diagram boxes can show a research indicator without rescanning every case.

The entity follows the conventions the Residence_Fact ("Boende") feature established at format version 0.2: plain dataclasses with a string `id` first, top-level collections on `ProjectData`, reflection-based JSON serialization with omit-defaults, a registered migration that adds the empty collections, validators returning Swedish error-string lists, and a `ProjectService` dirty flag. This feature raises the project format version to 0.3.

All code identifiers, internal keys, and developer comments are in English. All user-facing labels, messages, menus, tooltips, and report headings are in Swedish.

## Glossary

- **Research_Case**: The new entity, displayed in Swedish as "Forskningsärende" (plural "Forskningsärenden") with the internal key `research_case` and id prefix `case_`. Holds `id`, `title`, `description`, `status`, `priority`, `conclusion`, `primary_entity_ref`, and `linked_entities`. A research question that may concern zero or more project entities.
- **Research_Hypothesis**: The new entity, Swedish "Hypotes", internal key `research_hypothesis`, id prefix `hypothesis_`. A proposed explanation belonging to one Research_Case. Holds `id`, `research_case_id`, `statement`, `assessment`, `reasoning`, `linked_entities`, and `comments`. Stored as a top-level `ProjectData.research_hypotheses` collection keyed back to its case by `research_case_id`.
- **Hypothesis_Comment**: Swedish "Hypoteskommentar", id prefix `hypcomment_`. A dated free-text observation about one Research_Hypothesis. Holds `id`, `date`, and `text`. Nested inside its Research_Hypothesis `comments` list.
- **Research_Action**: The new entity, Swedish "Forskningsåtgärd", internal key `research_action`, id prefix `action_`. Planned or completed research work belonging to one Research_Case. Holds `id`, `research_case_id`, `title`, `text`, `completed_date`, `sort_order`, and `source_refs`. Stored as a top-level `ProjectData.research_actions` collection. Its `completed_date` is `None` for every Pending_Action; an empty string is never a valid stored value and is normalized to `None` before validation and storage (see Normalized_Completion_Date).
- **Normalized_Completion_Date**: The rule that `ResearchAction.completed_date` holds either `None` (pending) or a non-empty valid calendar date; an empty, whitespace-only, or otherwise absent input is normalized to `None` so that no Research_Action is ever treated as completed on the basis of an empty string. Covered by Requirement 7.
- **Valid_Calendar_Date**: A date string that is not only ISO-8601-shaped (ÅÅÅÅ, ÅÅÅÅ-MM, or ÅÅÅÅ-MM-DD) but also denotes a real calendar date, so that "2026-02-30" and "2026-13-01" are rejected. The feature validates completion dates and hypothesis-comment dates as Valid_Calendar_Dates, reusing or extending the existing date-parsing used elsewhere in the model rather than a shape-only regex. Covered by Requirements 5, 6, 7.
- **Research_Entity_Link**: A reference from a Research_Case or Research_Hypothesis to a project entity, holding `entity_type`, `entity_id`, and an optional `role`. Follows the shape of the existing `LinkedEntity` (`slaktbusken/model/media.py`). Used for both `primary_entity_ref` (where `role` is unused) and each item of `linked_entities`.
- **Research_Status**: The state of a Research_Case, one of `open`, `in_progress`, `on_hold`, `closed`. Swedish "Status". Default `open`.
- **Research_Priority**: The priority of a Research_Case, one of `low`, `normal`, `high`. Swedish "Prioritet". Default `normal`.
- **Hypothesis_Assessment**: The researcher's manual judgement of a Research_Hypothesis, one of `unassessed`, `possible`, `strong_support`, `confirmed`, `rejected`. Default `unassessed`.
- **Pending_Action**: A Research_Action whose `completed_date` is absent (None). Displayed under "Nästa åtgärder".
- **Completed_Action**: A Research_Action whose `completed_date` is present. Displayed under "Genomförda åtgärder".
- **Non_Closed_Case**: A Research_Case whose `status` is not `closed`, i.e. `open`, `in_progress`, or `on_hold`. The research indicator and the person-list column count non-closed cases.
- **Supported_Entity_Type**: One of the internal entity keys a research link may target: `person`, `family`, `event`, `place`, `source`, `media`, `dna_match`, `dna_cluster`.
- **Research_Model**: The dataclasses and pure functions defining Research_Case, Research_Hypothesis, Hypothesis_Comment, Research_Action, and Research_Entity_Link, in `slaktbusken/model/research_case.py`.
- **Research_Validator**: The validation functions for the research entities, following the conventions of `slaktbusken/model/validators.py` and returning Swedish error-string lists.
- **Research_Index**: A rebuild-on-demand lookup bundle over a Project, following the pattern of `foster_sync._ProjectIndex` and `person_check_engine.CheckContext`, providing reverse lookups (cases by entity, counts by entity, actions by source, actions by case, hypotheses by case, pending-action counts, hypotheses by entity). Lives in `slaktbusken/services/research_index.py`.
- **Research_Service**: The CRUD and reference-integrity functions for research entities, following `slaktbusken/services/project_service.py` and `slaktbusken/services/delete_service.py` conventions.
- **Research_Overview**: The central PySide6 window listing Research_Cases in a filterable, sortable table, Swedish "Forskningsöversikt".
- **Research_Case_Editor**: The PySide6 editor for one Research_Case, including its hypotheses and actions. It edits a Working_Copy and commits transactionally.
- **Working_Copy**: A deep copy of the Research_Case together with its Research_Hypotheses, Hypothesis_Comments, and Research_Actions that the Research_Case_Editor mutates in isolation. Nothing in the Working_Copy reaches `ProjectData` until a single transactional commit succeeds; cancel or a validation failure discards the Working_Copy and leaves `ProjectData` unchanged. Covered by Requirement 19.
- **Research_Changed_Notification**: A signal the application emits after any research create, update, or delete so that already-open windows — the person, place, source, event, media, and DNA editors, other open Research windows, the person list, and the diagrams — rebuild their research-derived content from a fresh Research_Index. Rebuilding the Research_Index alone does not update a widget that has already been drawn; the notification is what prompts open widgets to refresh. Covered by Requirement 13.
- **Research_Consistency_Report**: A consistency report, Swedish "Forskningskonsistens", following the convention of `slaktbusken/reports/geographic.py` (Issue dataclass + `check_*` + `generate_*` producing `ReportContent`).
- **Project**: The root container `ProjectData` (`slaktbusken/model/project.py`) holding all entities.
- **Serialization_Module**: `slaktbusken/persistence/serialization.py`, which writes the Project to JSON and reads it back.
- **Migration_Manager**: `slaktbusken/persistence/migration.py`, which registers and applies format migrations and guards the stored version.
- **Delete_Service**: `slaktbusken/services/delete_service.py`, which cascades entity deletion and reports blocking dependencies.
- **GEDCOM_Importer** / **GEDCOM_Exporter**: `slaktbusken/gedcom/importer.py` and `slaktbusken/gedcom/exporter.py`.

## Requirements

### Requirement 1: Research Case Entity

**User Story:** As a genealogist, I want to record a research question as its own entity with a status and priority, so that I can track an investigation rather than keeping it in a loose note.

#### Acceptance Criteria

1. THE Research_Model SHALL define a Research_Case whose field `id` is required and whose fields `title`, `description`, `status`, `priority`, `conclusion`, `primary_entity_ref`, and `linked_entities` are present, where `title`, `description`, and `conclusion` default to empty text, `status` defaults to `open`, `priority` defaults to `normal`, `primary_entity_ref` defaults to absent, and `linked_entities` defaults to an empty ordered list.
2. THE Project SHALL hold Research_Cases in a `research_cases` collection alongside `residences`, SHALL initialize that collection as empty for a newly created Project, and SHALL preserve the order in which Research_Cases were added.
3. WHEN a Research_Case is added to the Project, THE Research_Service SHALL assign it an `id` using the existing `IDGenerator` with the prefix `case_` and SHALL make that `id` unique among all identifiers currently in the Project. The non-reuse guarantee across a save-and-reopen cycle is defined centrally in Requirement 2, because the existing `IDGenerator` derives its counter from the high-water mark of the ids it is seeded with, and every current call site seeds it only from live entities, so a naive approach would reuse the id of a deleted highest-numbered entity after reopening.
4. THE Research_Model SHALL accept `status` values from the set `open`, `in_progress`, `on_hold`, `closed`, and THE Research_Validator SHALL return exactly one occurrence of the error message "Ogiltig status för forskningsärendet." WHEN `status` holds any other value.
5. THE Research_Model SHALL accept `priority` values from the set `low`, `normal`, `high`, and THE Research_Validator SHALL return exactly one occurrence of the error message "Ogiltig prioritet för forskningsärendet." WHEN `priority` holds any other value.
6. THE Research_Model SHALL accept a Research_Case whose `title` is empty and whose `description`, `conclusion`, `primary_entity_ref`, and `linked_entities` are all empty or absent, and THE Research_Validator SHALL return zero errors for that Research_Case based on its emptiness, so that the model layer tolerates an empty `title` for loading and round-tripping data; the requirement that the user supply a non-empty `title` before a Research_Case can be saved from the editor is a Research_Case_Editor rule defined in Requirement 19 criterion 12, not a model validation error.
7. THE Research_Model SHALL accept `title` holding 0 to 200 characters and `description` and `conclusion` each holding 0 to 10000 characters, counted as Unicode code points, and THE Research_Validator SHALL return the error message "Rubriken får vara högst 200 tecken.", "Frågeställningen får vara högst 10000 tecken.", or "Slutsatsen får vara högst 10000 tecken." respectively WHEN a value exceeds its limit.
8. THE Research_Model SHALL treat `conclusion` as free text whose presence or absence is independent of `status`, so that a Research_Case may hold `status` `closed` with an empty `conclusion` and a Research_Case may hold `status` `open` with a non-empty `conclusion`, and THE Research_Validator SHALL return zero errors for either combination.
9. WHEN THE Research_Validator checks a Research_Case that violates none of the stated rules, THE Research_Validator SHALL return an empty list of Swedish error messages.
10. WHEN a Research_Case is created, updated, or deleted through THE Research_Service, THE Research_Service SHALL set the `ProjectService` dirty flag to true.

### Requirement 2: Identifier Non-Reuse Across Save and Reopen

**User Story:** As a genealogist, I want a deleted research item's id never to be handed to a different item after I save and reopen, so that a stored reference can never silently point at the wrong thing.

#### Acceptance Criteria

1. THE application SHALL guarantee that an `id` assigned to any Research_Case, Research_Hypothesis, Research_Action, or Hypothesis_Comment is never assigned to a different research entity later, including after the Project is saved, closed, and reopened, and including when the deleted entity held the highest numeric suffix for its prefix at the time of deletion.
2. THE application SHALL NOT rely on seeding the `IDGenerator` from live entities alone to satisfy criterion 1, because the current call sites seed it only from entities currently present, so the high-water mark is lost when the highest-numbered entity is deleted and the file is reopened.
3. THE application SHALL satisfy criterion 1 by one of: (a) persisting a per-prefix high-water mark in the Project file and seeding the `IDGenerator` from it in addition to live ids, (b) seeding the `IDGenerator` from a persisted project-wide ledger of every id ever used, or (c) assigning research ids that are not reused by construction, such that the chosen mechanism is implemented and not merely asserted.
4. WHERE the chosen mechanism persists a high-water mark or a used-id ledger in the Project file, THE Serialization_Module and THE Migration_Manager SHALL round-trip that data following the same backward-compatibility rules as the research collections, so that a pre-feature project loads with a correctly initialized mechanism and no error.
5. WHEN an id is freed by a deletion within a single open session, THE application SHALL NOT reuse that id for a different research entity during that session either.
6. THE application SHALL document the chosen mechanism from criterion 3 in the design, SHALL avoid changing the format of existing non-research ids, and SHALL keep research ids human-readable where the chosen mechanism permits it.

### Requirement 3: Linking Research Cases to Project Entities

**User Story:** As a genealogist, I want one research question to concern several entities at once — two person records I suspect are the same individual, plus the event that ties them — so that the case is not forced to belong to a single person.

#### Acceptance Criteria

1. THE Research_Model SHALL define a Research_Entity_Link holding `entity_type`, `entity_id`, and an optional `role` defaulting to empty text, following the field shape of the existing `LinkedEntity`.
2. THE Research_Model SHALL accept a Research_Case whose `primary_entity_ref` is absent and whose `linked_entities` is empty, so that a Research_Case need reference no entity at all, and THE Research_Validator SHALL return zero errors for that Research_Case.
3. THE Research_Model SHALL accept `primary_entity_ref` as an optional Research_Entity_Link and `linked_entities` as any number of Research_Entity_Links, and SHALL preserve the order of `linked_entities`.
4. THE Research_Model SHALL accept a Research_Entity_Link whose `entity_type` is one of the Supported_Entity_Types `person`, `family`, `event`, `place`, `source`, `media`, `dna_match`, `dna_cluster`, and THE Research_Validator SHALL return exactly one occurrence of the error message "Forskningslänken har en okänd objekttyp." per link whose `entity_type` is none of those values.
5. IF a Research_Entity_Link's `entity_id` is non-empty and resolves to no entity of its `entity_type` in the Project, THEN THE Research_Validator SHALL return exactly one occurrence of the error message "Forskningsärendet refererar till ett objekt som inte finns." per unresolved link, naming no entity data beyond the stored `entity_type` and `entity_id`.
6. THE Research_Model SHALL NOT store a copy of any person name, place name, source title, or other display text on a Research_Entity_Link, and THE Research_Overview, THE Research_Case_Editor, and every integration point SHALL resolve display names from the referenced project entity at render time.
7. WHERE a Research_Case's `primary_entity_ref` and one or more `linked_entities` reference the same `(entity_type, entity_id)` pair, or two `linked_entities` reference the same pair, THE Research_Validator SHALL return exactly one warning-level finding with the message "Forskningsärendet länkar till samma objekt mer än en gång.", and THE Research_Index SHALL count that Research_Case exactly once for that entity.
8. WHEN THE Research_Index is asked for the Research_Cases linked to a given `(entity_type, entity_id)`, THE Research_Index SHALL return each matching Research_Case exactly once whether the entity is referenced by `primary_entity_ref`, by `linked_entities`, or by both, and SHALL treat a Research_Case with no matching link as absent from the result.

### Requirement 4: Research Hypotheses

**User Story:** As a genealogist, I want to record several competing explanations for one question and weigh each one myself, so that conflicting ideas stay visible instead of being collapsed into a single answer.

#### Acceptance Criteria

1. THE Research_Model SHALL define a Research_Hypothesis whose fields `id` and `research_case_id` are required and whose fields `statement`, `assessment`, `reasoning`, `linked_entities`, and `comments` are present, where `statement` and `reasoning` default to empty text, `assessment` defaults to `unassessed`, and `linked_entities` and `comments` default to empty ordered lists.
2. THE Project SHALL hold Research_Hypotheses in a top-level `research_hypotheses` collection, SHALL initialize it empty for a new Project, and SHALL preserve insertion order, each Research_Hypothesis naming its owning Research_Case through its `research_case_id`.
3. WHEN a Research_Hypothesis is added, THE Research_Service SHALL assign it an `id` with the prefix `hypothesis_` from the `IDGenerator`, unique among all Project identifiers and never reused in the sense defined in Requirement 2.
4. THE Research_Model SHALL accept `assessment` values from the set `unassessed`, `possible`, `strong_support`, `confirmed`, `rejected`, and THE Research_Validator SHALL return the error message "Ogiltig bedömning för hypotesen." WHEN `assessment` holds any other value.
5. THE Research_Model SHALL NOT compute an automatic probability, confidence score, or assessment value for a Research_Hypothesis, and `assessment` SHALL change only through explicit user action.
6. THE Research_Model SHALL accept two or more Research_Hypotheses naming the same `research_case_id`, including Research_Hypotheses whose `assessment` values conflict (for example one `confirmed` and one `rejected`), and THE Research_Validator SHALL return zero errors for that combination.
7. IF a Research_Hypothesis's `research_case_id` resolves to no Research_Case in the Project, THEN THE Research_Validator SHALL return the error message "Hypotesen refererar till ett forskningsärende som inte finns."
8. WHEN the user sets a Research_Hypothesis `assessment` to `rejected`, THE Research_Service SHALL leave the Research_Hypothesis, its `statement`, its `reasoning`, its `linked_entities`, and all of its `comments` present and unchanged, deleting nothing.
9. THE Research_Model SHALL apply to a Research_Hypothesis `linked_entities` the same Research_Entity_Link rules defined in Requirement 3 criteria 1, 4, and 5.
10. THE Research_Model SHALL accept `statement` holding 0 to 1000 characters and `reasoning` holding 0 to 10000 characters, and THE Research_Validator SHALL return the error message "Hypotesens påstående får vara högst 1000 tecken." or "Hypotesens motivering får vara högst 10000 tecken." WHEN a value exceeds its limit.

### Requirement 5: Hypothesis Comments

**User Story:** As a genealogist, I want to add dated observations under a hypothesis as evidence accumulates, so that I keep a log of what I noticed and when, without that log changing my assessment on its own.

#### Acceptance Criteria

1. THE Research_Model SHALL define a Hypothesis_Comment holding a required `id`, a `date`, and a `text`, where `date` holds either an empty value or a Valid_Calendar_Date in the form ÅÅÅÅ, ÅÅÅÅ-MM, or ÅÅÅÅ-MM-DD and defaults to empty, and `text` holds at most 10000 characters and defaults to empty. A `date` of day precision is permitted but not required; a comment may be dated to a year or a month.
2. THE Research_Model SHALL nest Hypothesis_Comments inside their Research_Hypothesis `comments` list, SHALL append each newly added comment after those already present, and SHALL preserve that order across serialization.
3. WHEN a Hypothesis_Comment is added, THE Research_Service SHALL assign it an `id` with the prefix `hypcomment_` from the `IDGenerator`, unique among all Project identifiers and never reused in the sense defined in Requirement 2.
4. WHEN THE Research_Case_Editor creates a new Hypothesis_Comment, THE Research_Case_Editor SHALL default its `date` to today's local date in ÅÅÅÅ-MM-DD form and SHALL allow the user to change the `date` or clear it to empty before the comment is committed.
5. IF a Hypothesis_Comment's `date` is non-empty and is not a Valid_Calendar_Date — whether because its shape is wrong or because it names a day that does not exist, such as "2026-02-30" — THEN THE Research_Validator SHALL return the error message "Hypoteskommentarens datum är inte ett giltigt datum (förväntat ÅÅÅÅ, ÅÅÅÅ-MM eller ÅÅÅÅ-MM-DD)." and SHALL leave the stored value unchanged.
6. THE Research_Case_Editor SHALL allow a Hypothesis_Comment to be edited and deleted through normal editor controls, and deleting a Hypothesis_Comment SHALL leave every other Hypothesis_Comment of the same Research_Hypothesis unchanged and in its existing relative order.
7. WHEN the user adds a Hypothesis_Comment to a Research_Hypothesis, THE Research_Service SHALL leave that Research_Hypothesis's `assessment` unchanged.
8. THE Research_Model SHALL treat a Hypothesis_Comment as free text that may describe an observation, a piece of reasoning, a contradiction, or new information, and SHALL impose no requirement that a comment correspond to an assessment change, and THE feature SHALL NOT maintain an automatic revision history of hypothesis assessments in this version.

### Requirement 6: Research Actions

**User Story:** As a genealogist, I want to list the research work for a case and tick items off as I do them, so that I can see at a glance what remains and what I already checked.

#### Acceptance Criteria

1. THE Research_Model SHALL define a Research_Action whose fields `id` and `research_case_id` are required and whose fields `title`, `text`, `completed_date`, `sort_order`, and `source_refs` are present, where `title` and `text` default to empty text, `completed_date` defaults to absent (None), `sort_order` defaults to 0, and `source_refs` defaults to an empty ordered list of source-reference values. THE Research_Model SHALL enforce the Normalized_Completion_Date rule: `completed_date` is either `None` or a non-empty Valid_Calendar_Date, and an empty or whitespace-only value is normalized to `None` before storage.
2. THE Project SHALL hold Research_Actions in a top-level `research_actions` collection, SHALL initialize it empty for a new Project, and SHALL preserve insertion order, each Research_Action naming its owning Research_Case through its `research_case_id`.
3. WHEN a Research_Action is added, THE Research_Service SHALL assign it an `id` with the prefix `action_` from the `IDGenerator`, unique among all Project identifiers and never reused in the sense defined in Requirement 2.
4. THE Research_Model SHALL define a Research_Action as a Pending_Action exactly when its `completed_date` is `None`, and as a Completed_Action exactly when its `completed_date` is a non-empty Valid_Calendar_Date, and THE Research_Model SHALL impose no separate status field on a Research_Action. THE Research_Model SHALL NOT treat an empty string as a Completed_Action; any empty or whitespace-only `completed_date` reaching the model SHALL be normalized to `None` and therefore classified as a Pending_Action.
5. IF a Research_Action's `research_case_id` resolves to no Research_Case in the Project, THEN THE Research_Validator SHALL return the error message "Forskningsåtgärden refererar till ett forskningsärende som inte finns."
6. THE Research_Model SHALL accept any number of Pending_Actions for one `research_case_id`, including two or more Research_Actions whose `completed_date` is absent, and THE Research_Validator SHALL return zero errors for that condition.
7. IF a Research_Action's `completed_date` is not `None` and is not a Valid_Calendar_Date — whether because its shape is wrong or because it names a day that does not exist — THEN THE Research_Validator SHALL return the error message "Forskningsåtgärdens färdigdatum är inte ett giltigt datum (förväntat ÅÅÅÅ, ÅÅÅÅ-MM eller ÅÅÅÅ-MM-DD)."
8. THE Research_Model SHALL accept `title` holding 0 to 200 characters and `text` holding 0 to 10000 characters, and THE Research_Validator SHALL return the error message "Forskningsåtgärdens rubrik får vara högst 200 tecken." or "Forskningsåtgärdens text får vara högst 10000 tecken." WHEN a value exceeds its limit.
9. THE Research_Model SHALL permit a `completed_date` of year, month, or day precision and SHALL NOT require day precision, since a completed action may be dated only to the month or year it was carried out, and THE application SHALL default a newly completed action's date to today's date at day precision as defined in Requirement 7 while leaving the user free to coarsen it.

### Requirement 7: Completing and Reopening a Research Action

**User Story:** As a genealogist, I want to mark an action done and later undo that, so that a misclick or a changed mind never loses the work I recorded under the action.

#### Acceptance Criteria

1. THE Research_Case_Editor SHALL present for each Research_Action a completion control labelled "Åtgärden genomförd" together with an editable completion-date field labelled "Färdigdatum".
2. WHEN the user turns the completion control on for a Research_Action whose `completed_date` is `None`, THE Research_Case_Editor SHALL set `completed_date` to today's local date in ÅÅÅÅ-MM-DD form, and WHERE the Research_Action already carries a non-empty Valid_Calendar_Date, THE Research_Case_Editor SHALL keep that existing date rather than overwriting it.
3. WHEN the completion control is on, THE Research_Case_Editor SHALL display the completion-date field and SHALL allow the user to edit it to any Valid_Calendar_Date accepted by Requirement 6 criterion 7, and WHEN the user clears that field to empty while the control is on, THE Research_Case_Editor SHALL treat the action as not yet having a committable completion date and SHALL either prompt for a date or turn the completion control off rather than storing an empty string.
4. WHEN the user turns the completion control off for a Research_Action, THE Research_Case_Editor SHALL set `completed_date` to `None` (never an empty string) and SHALL leave `title`, `text`, `source_refs`, and `sort_order` of that Research_Action unchanged.
5. THE Research_Case_Editor SHALL make turning the completion control on and off a reversible operation, so that turning it off after turning it on returns the Research_Action to a Pending_Action carrying its original `title`, `text`, `source_refs`, and `sort_order`.
6. THE Research_Case_Editor SHALL display Pending_Actions under the heading "Nästa åtgärder" and Completed_Actions under the heading "Genomförda åtgärder", and WHEN a Research_Action's `completed_date` changes between absent and present, THE Research_Case_Editor SHALL move that Research_Action between the two headings accordingly.
7. THE Research_Case_Editor SHALL keep a Completed_Action editable, allowing its `title`, `text`, `source_refs`, and `completed_date` to be changed while it remains a Completed_Action.
8. WHEN the Research_Case_Editor commits a Research_Action whose completion control is off, or whose completion-date field is empty or whitespace-only, THE Research_Case_Editor SHALL store `completed_date` as `None`, applying the Normalized_Completion_Date rule, so that no committed Pending_Action carries an empty-string completion date.

### Requirement 8: Ordering of Research Actions

**User Story:** As a genealogist, I want to arrange my pending actions in the order I intend to tackle them, and see completed actions in the order I finished them, so that the list reads as a plan and a log.

#### Acceptance Criteria

1. THE Research_Case_Editor SHALL order Pending_Actions by their `sort_order` ascending and SHALL break a tie by ascending Research_Action `id`.
2. THE Research_Case_Editor SHALL allow the user to change the relative order of Pending_Actions, and WHEN the user reorders them, THE Research_Case_Editor SHALL assign `sort_order` values that produce the chosen order and SHALL persist those `sort_order` values so that the order is reproduced when the Project is reopened.
3. THE Research_Case_Editor SHALL order Completed_Actions by `completed_date` descending by default, SHALL break a tie by ascending Research_Action `id`, and SHALL place a Completed_Action whose `completed_date` has coarser precision using the first day of that value for comparison.
4. WHEN a Pending_Action becomes a Completed_Action or a Completed_Action becomes a Pending_Action, THE Research_Case_Editor SHALL leave its `sort_order` value unchanged, so that reopening a completed action restores its place among the Pending_Actions.

### Requirement 9: Source References on Research Actions

**User Story:** As a genealogist, I want an action to cite the volumes I examined — including ones where I found nothing — so that negative results are documented instead of lost.

#### Acceptance Criteria

1. THE Research_Model SHALL store a Research_Action's `source_refs` using the existing source-citation convention, so that each entry resolves to a Source in the Project `sources` collection through the same identifier the rest of the application cites a Source by.
2. THE Research_Model SHALL accept a Research_Action whose `source_refs` is empty, and THE Research_Validator SHALL return zero errors for an empty `source_refs`, so that the user may document research work before registering any formal Source.
3. THE Research_Model SHALL accept a Research_Action whose `source_refs` names one Source or several Sources, and THE Research_Case_Editor SHALL allow the user to add and remove Source references on a Research_Action reusing the application's existing Source-selection flow rather than a new parallel one.
4. IF a Research_Action `source_ref` resolves to no Source in the Project, THEN THE Research_Validator SHALL return the error message "Forskningsåtgärden refererar till en källa som inte finns." per unresolved reference.
5. THE Research_Model SHALL impose no constraint linking a Source reference to a positive or negative research result, so that a Research_Action whose `text` records that a person was not found in an examined volume may still reference that examined Source.
6. WHERE the existing source model distinguishes a source record from a precise page-level citation, THE Research_Model SHALL cite Sources through the same `SourceRef` structure the rest of the application uses and SHALL introduce no incompatible duplicate citation structure.
7. THE Research_Model SHALL treat a `source_ref` on a Research_Action as a record of a Source examined during that research work, which is distinct from evidence supporting a Research_Hypothesis, and SHALL NOT infer, derive, or display that an examined Source supports or weakens any Research_Hypothesis of the owning Research_Case.
8. THE application SHALL present the Source-selection flow for a Research_Action's `source_refs` with wording that frames the reference as an examined or consulted Source (for example a Swedish section label "Granskade källor"), keeping the reference optional and equally usable for a negative result where the examined Source did not contain the sought record.
9. WHERE a Research_Hypothesis needs to record supporting or contradicting evidence, THE application SHALL express that through the Research_Hypothesis `reasoning` text and its Hypothesis_Comments, and SHALL NOT repurpose a Research_Action `source_ref` as a hypothesis evidence link in this version.

### Requirement 10: Case Status Independent of Action Completion

**User Story:** As a genealogist, I want a case's open/closed state to be my own decision, separate from whether its actions are done, so that I can close an unsolved case or keep an open one with everything ticked off.

#### Acceptance Criteria

1. THE Research_Model SHALL treat a Research_Case's `status` as independent of the `completed_date` values of its Research_Actions, so that THE Research_Validator SHALL return zero errors for a Research_Case holding `status` `open` with zero Pending_Actions, `status` `in_progress` with several Pending_Actions, `status` `closed` with one or more Pending_Actions, and `status` `closed` with an empty `conclusion`.
2. WHEN the user changes a Research_Case `status` to `closed` while that Research_Case has one or more Pending_Actions, THE Research_Case_Editor SHALL display a warning dialog titled "Forskningsärendet har öppna åtgärder" whose body reads "Forskningsärendet har fortfarande {count} forskningsåtgärder utan färdigdatum. Vill du ändå avsluta ärendet?" where {count} is the number of Pending_Actions of that Research_Case.
3. THE warning dialog of criterion 2 SHALL present a button "Gå tillbaka" that cancels the status change and restores the previous `status`, and a button "Avsluta ändå" that applies the `closed` status, and SHALL NOT block closing.
4. WHEN the user chooses "Avsluta ändå", THE Research_Case_Editor SHALL set `status` to `closed` and SHALL leave every Pending_Action of that Research_Case a Pending_Action, marking none of them completed.
5. WHEN the user saves a Research_Case whose `status` is already `closed` without changing its `status`, THE Research_Case_Editor SHALL NOT display the warning dialog of criterion 2.
6. WHEN a Research_Case's `status` changes to `closed`, THE Research_Service SHALL change no `Person`, `Event`, `Family`, `Place`, `Source`, `Media`, DNA, or other genealogical fact as a consequence.
7. WHEN the user changes a closed Research_Case's `status` to any Non_Closed_Case value, THE Research_Service SHALL leave every Research_Hypothesis, Research_Action, Hypothesis_Comment, `source_ref`, and `conclusion` of that Research_Case present and unchanged.

### Requirement 11: Adding Actions to a Closed Case

**User Story:** As a genealogist, I want to add a new idea to check onto a case I already closed, without the case silently reopening, so that the case state stays under my control.

#### Acceptance Criteria

1. THE Research_Case_Editor SHALL allow a new Research_Action to be added to a Research_Case whose `status` is `closed`.
2. WHEN a Research_Action is added to a closed Research_Case, THE Research_Service SHALL leave that Research_Case's `status` as `closed`, changing it automatically to no other value.
3. WHEN the user adds a Pending_Action to a closed Research_Case, THE Research_Case_Editor SHALL display a non-blocking informational message stating that pending actions belonging to closed cases are excluded from the default "Att göra" view, and SHALL still add the Research_Action.

### Requirement 12: Shared Research Index

**User Story:** As a genealogist with a large tree, I want research indicators and counts to appear instantly as I scroll the person list, so that the feature never slows the views it decorates.

#### Acceptance Criteria

1. THE Research_Index SHALL be a lookup bundle built on demand from the authoritative Project data, following the pattern of `foster_sync._ProjectIndex` and `person_check_engine.CheckContext`, and SHALL NOT be a stored collection that competes with the Project as a source of truth.
2. THE Research_Index SHALL provide the directly linked Research_Cases for a given `(entity_type, entity_id)`, returning each matching Research_Case exactly once as defined in Requirement 3 criterion 8.
3. THE Research_Index SHALL provide, for a given `(entity_type, entity_id)`, the count of Non_Closed_Cases and the count of total directly linked Research_Cases, counting each Research_Case at most once even when it links the entity more than once.
4. THE Research_Index SHALL provide the Research_Actions whose `source_refs` reference a given Source `id`, returning every such Research_Action and allowing the same Source to appear on Research_Actions of two or more different Research_Cases.
5. THE Research_Index SHALL provide the Research_Actions of a given `research_case_id`, the Research_Hypotheses of a given `research_case_id`, and the count of Pending_Actions of a given `research_case_id`.
6. WHEN a Research_Case, Research_Hypothesis, or Research_Action is created, modified, or deleted, WHEN a Research_Case `status` changes, WHEN a Research_Entity_Link changes, WHEN a Research_Action `source_ref` changes, or WHEN a Research_Hypothesis is added or removed, THE application SHALL obtain Research_Index results that reflect the new Project state on the next build of the Research_Index, so that no stale result survives a change.
7. WHEN an entity is deleted or merged, THE Research_Index SHALL reflect the resulting Project state on its next build, reporting the surviving links after a merge and omitting a deleted entity's links from entity-keyed lookups.
8. WHEN the Research_Index is built for a Project holding up to 10000 Research_Cases, 20000 Research_Actions, and 20000 persons, THE Research_Index SHALL answer each lookup defined in criteria 2 to 5 in constant or near-constant time after the build, the build itself completing in at most 2 seconds.
9. THE Research_Index SHALL provide the Research_Hypotheses that explicitly reference a given `(entity_type, entity_id)` through their `linked_entities`, returning each such Research_Hypothesis together with its owning Research_Case, to support the "Förekommer i hypoteser" section of Requirement 22, and SHALL keep these hypothesis references separate from the directly-linked-case lookups of criteria 2 and 3 so that they never enter indicator counts.

### Requirement 13: Refreshing Already-Open Views After Research Changes

**User Story:** As a genealogist with several windows open, I want a research change in one window to show up in the others without reopening them, so that what I see is never stale.

#### Acceptance Criteria

1. THE application SHALL emit a Research_Changed_Notification after every committed create, update, or delete of a Research_Case, Research_Hypothesis, Hypothesis_Comment, or Research_Action, and after a merge or deletion that rewires or removes research references.
2. WHEN a Research_Changed_Notification is emitted, THE application SHALL cause every already-open view that presents research-derived content — the person list, the diagrams, the Research_Overview windows, and the person, place, source, event, media, and DNA editors' research tabs or sections — to rebuild that content from a freshly built Research_Index.
3. THE application SHALL treat the rebuild of the Research_Index as necessary but not sufficient for updating an already-drawn widget, and SHALL additionally refresh each open widget's displayed rows, indicators, counts, and tooltips in response to the notification.
4. WHEN a Research_Case shown in an open view is deleted, THE open view SHALL remove it from its display on the next refresh rather than continuing to show a stale row, and WHEN a Research_Case's status changes, THE open indicators and counts SHALL update to the new state.
5. WHERE two windows show the same Research_Case and the user edits it in one and commits, THE other window SHALL reflect the committed values on its next refresh, following Requirement 30 criterion 2.
6. THE refresh triggered by a Research_Changed_Notification SHALL preserve each open view's current selection and scroll position where practical, and SHALL NOT discard unsaved edits in any editor that did not originate the change, following Requirement 30 criterion 4.

### Requirement 14: Research Indicators in Existing Views

**User Story:** As a genealogist, I want a small marker on a person who has open research, coloured so it never implies the facts are verified, so that I can spot where work remains.

#### Acceptance Criteria

1. THE application SHALL derive a research indicator for an entity solely from the Research_Cases directly linked to that entity through `primary_entity_ref` or `linked_entities`, and SHALL NOT derive it by traversing indirectly related genealogical data.
2. WHERE an entity has zero directly linked Research_Cases, THE application SHALL show no research indicator for that entity.
3. WHERE an entity has one or more directly linked Research_Cases and every one of them is `closed`, THE application SHALL show a neutral grey research indicator, and SHALL NOT use green, since a closed case does not imply the genealogical information is verified.
4. WHERE an entity has at least one directly linked Non_Closed_Case, THE application SHALL show an orange research indicator.
5. THE research indicator tooltip SHALL read "{total} forskningsärenden, varav {open} öppna" where {total} is the number of directly linked Research_Cases and {open} is the number of directly linked Non_Closed_Cases, where "öppna" counts every Research_Case whose `status` is not `closed`.
6. THE application SHALL update an entity's research indicator state and tooltip to reflect a Research_Case being closed or reopened the next time the view is refreshed.

### Requirement 15: Person List Research Column

**User Story:** As a genealogist, I want an optional column in the person list showing each person's research counts, sortable, and switched on through the same settings I use for every other column, so that it fits the list I already know.

#### Acceptance Criteria

1. THE person list SHALL provide an optional column headed "Forskningsärenden" that, for each person, displays the count of directly linked Non_Closed_Cases and the count of total directly linked Research_Cases in the form "{open}/{total}", for example "2/3", and SHALL display nothing in that cell WHERE the person has zero directly linked Research_Cases.
2. WHERE a person has one or more directly linked Non_Closed_Cases, THE person list SHALL render the column value with an orange indicator, and WHERE a person has one or more directly linked Research_Cases that are all `closed`, THE person list SHALL render it with a grey indicator, following Requirement 14.
3. THE person list SHALL make the "Forskningsärenden" column sortable, ordering primarily by the Non_Closed_Case count and secondarily by the total Research_Case count.
4. THE visibility of the "Forskningsärenden" column SHALL be controlled through the existing "Inställningar → Personlista → Synliga kolumner och ikoner" mechanism, extending the existing `PersonListConfig` and column-visibility settings rather than introducing a separate settings store.
5. WHEN the user hides or shows the "Forskningsärenden" column through that settings mechanism, THE person list SHALL hide or show the column accordingly and SHALL persist the choice across application restarts using the existing settings persistence.
6. THE person list research counts SHALL be derived through the Research_Index so that building the person display list for a Project holding 20000 persons and 10000 Research_Cases stays within the person list's existing performance budget.

### Requirement 16: Diagram Research Indicator

**User Story:** As a genealogist, I want a compact research marker on person boxes in my diagrams, controlled by its own diagram setting, so that charts can show research without a whole extra text row and independently of the person list.

#### Acceptance Criteria

1. THE diagram person box SHALL provide an optional research indicator controlled by a checkbox labelled "Forskningsärenden" in "Inställningar → Diagram → Personsruta – synliga fält", extending the existing `PersonBoxConfig` rather than introducing a separate settings store.
2. THE diagram research indicator SHALL be compact, occupying no dedicated text row, and SHALL follow the indicator states and colours of Requirement 14 for the Research_Cases directly linked to the person the box represents.
3. WHEN the user clicks the diagram research indicator, THE application SHALL open the research related to that person, either the Research_Overview filtered to that person or the person's research directly.
4. WHEN the diagram research indicator is shown or clicked, THE application SHALL leave the existing person selection and diagram navigation behaviour unchanged.
5. THE person-list research column visibility setting of Requirement 15 and the diagram research indicator setting of this requirement SHALL be independent, so that changing one SHALL NOT change the other.

### Requirement 17: Entity Views Beyond the Person List

**User Story:** As a genealogist, I want the same research marker on places, events, sources, media, and DNA matches where the view supports it, so that research is visible wherever the entity appears.

#### Acceptance Criteria

1. WHERE a place list or place detail, an event list or event detail, a source list or source detail, a media list, a DNA match list, or a DNA cluster view already renders per-entity markers, THE application SHALL offer a research indicator for that entity following Requirement 14, derived from the Research_Cases directly linked to that entity.
2. THE general-purpose research indicators of criterion 1 SHALL be derived only from directly linked Research_Cases, excluding Research_Cases that reach the entity only indirectly through a Research_Action.
3. THE source editor's "Forskningsåtgärder där källan används" section defined in Requirement 23 SHALL be the one intentional exception to criterion 2, displaying Research_Actions that reference the Source indirectly.

### Requirement 18: Forskning Menu and Research Overview Window

**User Story:** As a genealogist, I want one place that lists all my research with filters and sorting, reached from a Forskning menu, so that I can survey and manage every case.

#### Acceptance Criteria

1. THE application SHALL add a top-level menu "Forskning" to the main menu bar containing the items "Forskningsöversikt", "Att göra", and "Hypoteser", wired following the existing `MainWindow` action and `Application` dialog-opening conventions, and SHALL enable those items only when a project is open.
2. THE menu items "Forskningsöversikt", "Att göra", and "Hypoteser" SHALL open the same Research_Overview window with different initial filters and SHALL NOT use separate persistence systems.
3. THE Research_Overview SHALL show Research_Cases in a searchable, sortable table whose columns include "Rubrik", "Status", "Prioritet", "Huvudobjekt", "Antal hypoteser", "Nästa åtgärder", and "Antal åtgärder", resolving "Huvudobjekt" from the referenced project entity at render time.
4. THE Research_Overview SHALL provide filtering by case status, by priority, by linked entity type, by a specific linked entity, by presence of Pending_Actions, by absence of Pending_Actions, by presence of Research_Hypotheses, by absence of Research_Hypotheses, and by free-text search over "Rubrik" and "Frågeställning".
5. THE Research_Overview SHALL allow the user to open a Research_Case for editing and to create a new Research_Case, and SHALL provide a control to include `closed` Research_Cases in the table.
6. THE "Att göra" view SHALL show Pending_Actions, SHALL by default include only Pending_Actions whose owning Research_Case is a Non_Closed_Case, and SHALL provide an option to also include Pending_Actions whose owning Research_Case is `closed`.
7. THE "Att göra" view SHALL show for each Pending_Action its owning Research_Case title and SHALL allow navigation both to the Research_Action and to its owning Research_Case.
8. THE "Hypoteser" view SHALL open the same central Research_Overview window in a distinct hypothesis-table mode that lists individual Research_Hypotheses — one row per Research_Hypothesis, not one row per Research_Case — showing for each at least its `statement`, its Hypothesis_Assessment, and its owning Research_Case title, and SHALL NOT merely list the Research_Cases that contain hypotheses.
9. THE hypothesis-table mode SHALL allow the user to open the owning Research_Case for editing from a hypothesis row, SHALL provide sorting and free-text search over the hypothesis `statement` and owning case title, and SHALL reuse the same Research_Overview window and persistence as the case-table mode rather than a separate window or store.

### Requirement 19: Research Case Editor

**User Story:** As a genealogist, I want to edit a case, all its hypotheses, and all its actions in one place and jump to the entities it concerns, so that I manage the whole investigation without hunting through separate windows.

#### Acceptance Criteria

1. THE Research_Case_Editor SHALL present fields and sections for "Frågeställning", "Status", "Prioritet", "Berörda objekt", "Hypoteser", "Nästa åtgärder", "Genomförda åtgärder", and "Slutsats".
2. THE Research_Case_Editor SHALL allow one Research_Case to hold multiple Research_Hypotheses and multiple Research_Actions without requiring a separate editor instance per hypothesis or per action.
3. THE Research_Case_Editor SHALL allow the user to add, edit, and remove Research_Entity_Links in "Berörda objekt", designating at most one as the `primary_entity_ref`, and reusing the existing entity-selection widgets where one exists for the entity type.
4. WHEN the user removes the Research_Entity_Link currently designated as the `primary_entity_ref`, THE Research_Case_Editor SHALL set `primary_entity_ref` to absent (None) and SHALL NOT promote another `linked_entities` item to primary automatically, leaving the Research_Case with no primary entity until the user designates one, and a Research_Case with no primary entity SHALL remain valid.
5. WHEN the user designates an existing `linked_entities` item as the `primary_entity_ref`, or demotes the `primary_entity_ref` to an ordinary linked entity, THE Research_Case_Editor SHALL keep the set of referenced `(entity_type, entity_id)` pairs unchanged apart from the primary designation and SHALL not create a duplicate link, following Requirement 3 criterion 7.
6. THE Research_Case_Editor SHALL provide navigation to each linked project entity where a view for that entity type exists, and WHEN the user navigates to a linked entity, THE application SHALL NOT discard unsaved edits in the originating editor.
7. THE Research_Case_Editor SHALL present `status` through a control offering the Swedish labels "Öppen", "Pågår", "Vilande", and "Avslutad" mapped to the internal values `open`, `in_progress`, `on_hold`, and `closed`, and `priority` through a control offering "Låg", "Normal", and "Hög" mapped to `low`, `normal`, and `high`.
8. THE Research_Case_Editor SHALL edit a Working_Copy of the Research_Case and all of its Research_Hypotheses, Hypothesis_Comments, and Research_Actions, mutating only that Working_Copy while the editor is open and leaving the corresponding entities in `ProjectData` untouched until a successful commit.
9. WHEN the user saves the Research_Case_Editor, THE Research_Service SHALL validate the entire Working_Copy — the Research_Case and every Research_Hypothesis, Hypothesis_Comment, and Research_Action it holds — through the Research_Validator before writing any of it, and IF validation returns one or more errors, THEN THE Research_Case_Editor SHALL display those Swedish messages, SHALL write nothing to `ProjectData`, and SHALL keep the editor open with the user's edits intact.
10. WHEN validation of the Working_Copy succeeds, THE Research_Service SHALL commit every change in the Working_Copy to `ProjectData` as a single transactional operation — creating, updating, and deleting the affected research entities together — SHALL set the dirty flag, and SHALL emit the Research_Changed_Notification of Requirement 13.
11. WHEN the user cancels the Research_Case_Editor, or WHEN the transactional commit cannot complete, THE application SHALL discard the Working_Copy and SHALL leave `ProjectData` in exactly the state it held before the editor was opened, creating, updating, and deleting nothing.
12. THE Research_Case_Editor SHALL open with an empty editor for a new Research_Case, allowing the user to begin with no title, but WHEN the user saves, THE Research_Case_Editor SHALL require a non-empty `title` after trimming surrounding whitespace, and IF the `title` is empty, THEN THE Research_Case_Editor SHALL display the Swedish message "Forskningsärendet måste ha en rubrik." and SHALL NOT commit, so that an initially empty editor is permitted but an untitled case is never saved.

### Requirement 20: Confirming Research Case Deletion

**User Story:** As a genealogist, I want a clear warning before deleting a research case so that I understand its hypotheses, comments, and actions go with it, while removing an entity link never deletes the case.

#### Acceptance Criteria

1. WHEN the user invokes deletion of a Research_Case from the Research_Overview or the Research_Case_Editor, THE application SHALL display a confirmation dialog that names, by count, the Research_Hypotheses, Hypothesis_Comments, and Research_Actions that will be deleted along with the Research_Case, using a Swedish message such as "Att ta bort forskningsärendet tar även bort {h} hypoteser, {k} hypoteskommentarer och {å} forskningsåtgärder. Detta kan inte ångras.".
2. THE confirmation dialog of criterion 1 SHALL present a cancel option (for example "Avbryt") that aborts the deletion leaving the Research_Case and all its children unchanged, and a confirm option (for example "Ta bort") that proceeds.
3. WHEN the user confirms, THE Research_Service SHALL delete the Research_Case together with exactly its own Research_Hypotheses, Hypothesis_Comments, and Research_Actions, SHALL leave every other Research_Case and its children unchanged, SHALL change no genealogical fact, SHALL set the dirty flag, and SHALL emit the Research_Changed_Notification.
4. WHEN the user removes the association between a Research_Case and an entity — as in Requirement 21 criterion 2 — THE application SHALL remove only that Research_Entity_Link, SHALL NOT display the case-deletion confirmation of criterion 1, and SHALL delete neither the Research_Case nor any Research_Hypothesis, Hypothesis_Comment, or Research_Action.
5. THE application SHALL distinguish in its UI wording between "ta bort forskningsärendet" (delete the case) and "ta bort kopplingen" (remove the association) so that the two actions are not confused.

### Requirement 21: Integration with Existing Entity Editors

**User Story:** As a genealogist, I want to reach a person's or place's or event's research from the editor I am already in, so that I never have to route through the central overview for everyday work.

#### Acceptance Criteria

1. THE person editor SHALL present a "Forskning" tab, added following the programmatic tab-insertion pattern of the existing "Boenden" tab, that lists the Research_Cases directly linked to the person and shows for each its status and priority and an indication of whether it has Pending_Actions.
2. THE person editor "Forskning" tab SHALL allow the user to open an existing linked Research_Case, create a new Research_Case, link an existing Research_Case to the person, and remove the association between a Research_Case and the person, where removing the association deletes neither the Research_Case nor any other link it holds.
3. WHEN the user creates a Research_Case from the person editor "Forskning" tab, THE application SHALL set that person as the new Research_Case's `primary_entity_ref` where the Research_Case has no primary entity yet.
4. THE place editor SHALL present a "Forskning" tab following criteria 1 and 2 for the place, supporting Research_Cases about place identity, historical names, geographic interpretation, possible duplicate places, uncertain place hierarchy, and other place questions, and WHEN the user creates a Research_Case from it, THE application SHALL link the current place.
5. THE event editor SHALL present contextual access — a tab or a compact research section consistent with its existing structure — to the Research_Cases directly linked to the event, and WHEN the user opens or creates a Research_Case from the event editor, THE application SHALL NOT discard unsaved event changes.
6. THE application SHALL present contextual research access where the existing UI edits family and parent-child relationships, supporting Research_Cases about uncertain parentage, marriage, adoption, foster relationships, and other family questions, using the `family` or `event` Supported_Entity_Type as appropriate.
7. THE media editor SHALL present contextual access to the Research_Cases directly linked to the media item, supporting Research_Cases about identifying people, places, and dates in the item and about interpreting documents.
8. THE DNA match view and the DNA cluster view SHALL present contextual research access for the DNA match and the DNA cluster respectively, supporting Research_Cases about proposed common ancestors, unknown branches, cluster interpretation, and conflicting DNA evidence, using the `dna_match` and `dna_cluster` Supported_Entity_Types.
9. Every integration point of this requirement SHALL operate on the same shared Research_Case model, so that a Research_Case created or edited from one entity editor is visible and current in every other entity editor it links to and in the Research_Overview.

### Requirement 22: Discovering Hypotheses That Reference an Entity

**User Story:** As a genealogist, I want to find the hypotheses that name a particular person — for example as a candidate father — even when the research case is not directly about that person, so that I can see where that person appears in my reasoning.

#### Acceptance Criteria

1. THE person editor research tab, and the research tab or section of every other integrating entity editor where it is useful, SHALL present a section labelled "Förekommer i hypoteser" that lists the Research_Hypotheses whose `linked_entities` explicitly reference the current entity, obtained through the Research_Index hypothesis-by-entity lookup of Requirement 12 criterion 9.
2. THE "Förekommer i hypoteser" section SHALL show for each listed Research_Hypothesis at least its `statement`, its Hypothesis_Assessment, and its owning Research_Case title resolved at render time, and SHALL allow the user to open the owning Research_Case.
3. THE "Förekommer i hypoteser" section SHALL be kept separate from the directly-linked-case list of Requirement 21, and the Research_Hypotheses it lists SHALL NOT be counted in any research indicator or in the person-list "Forskningsärenden" column, which remain based on directly linked Research_Cases only following Requirement 14 criterion 1.
4. WHERE the current entity is referenced by no Research_Hypothesis `linked_entities`, THE "Förekommer i hypoteser" section SHALL show an empty-state message rather than a non-empty list.
5. THE "Förekommer i hypoteser" section SHALL refresh in response to a Research_Changed_Notification following Requirement 13.

### Requirement 23: Source Editor Research Tab

**User Story:** As a genealogist, I want the source editor to show both the questions about a source and every action that used the source, so that I see the source's full research footprint, including negative checks against it.

#### Acceptance Criteria

1. THE source editor SHALL present a "Forskning" tab containing two distinct sections under the headings "Forskningsärenden om denna källa" and "Forskningsåtgärder där källan används".
2. THE "Forskningsärenden om denna källa" section SHALL list the Research_Cases directly linked to the Source entity through `primary_entity_ref` or `linked_entities`, supporting Research_Cases about uncertain source identification, questionable page numbering, uncertain transcription, and conflicting interpretation of the source.
3. THE "Forskningsåtgärder där källan används" section SHALL list every Research_Action whose `source_refs` reference the current Source, obtained through the Research_Index, and SHALL include a Research_Action whose owning Research_Case is not itself directly linked to the Source.
4. THE "Forskningsåtgärder där källan används" section SHALL display for each listed Research_Action its title, its completion state, its `completed_date` where present, its owning Research_Case title, and its owning Research_Case status.
5. WHERE one Research_Case has two or more Research_Actions that each reference the current Source, THE source editor SHALL display every such Research_Action, and WHERE the source editor shows an aggregate count of Research_Cases, THE source editor SHALL count each distinct Research_Case once.
6. THE source editor "Forskning" tab SHALL allow the user to open a listed Research_Action, open the Research_Case owning a listed Research_Action, open a Research_Case concerning the Source, and create a new Research_Case concerning the Source.
7. THE Research_Case_Editor SHALL allow the user to navigate from a Research_Action to a Source referenced by that Research_Action.
8. WHEN a Research_Action is completed or a Research_Case is closed, THE application SHALL change no content of any referenced Source as a consequence.

### Requirement 24: Person List Filter Dialog Extension

**User Story:** As a genealogist, I want to filter the person list by research alongside the filters I already use, in a layout that stays readable, so that I can find people with open questions without losing the existing filters.

#### Acceptance Criteria

1. THE "Filtrera personlistan" dialog SHALL be refactored into a two-column layout placing "Namnfilter", "Datumintervall", "Församling", and "DNA-kluster" in the left column and "Händelsetyper" and "Forskningsärenden" in the right column, keeping the event-type list in a scrollable area, and SHALL keep the "Filtrera" and "Rensa" buttons accessible at the bottom.
2. THE "Filtrera personlistan" dialog SHALL be resizable and SHALL provide scrolling when the available screen size requires it.
3. THE dialog SHALL provide a "Forskningsärenden" section with a case-existence filter offering "Alla personer", "Har forskningsärenden", and "Saknar forskningsärenden".
4. THE "Forskningsärenden" section SHALL provide a case-status filter offering "Alla statusar", "Minst ett ej avslutat ärende", and "Enbart avslutade ärenden".
5. THE "Forskningsärenden" section SHALL provide a research-action filter offering "Alla åtgärder", "Minst en ej genomförd åtgärd", "Minst en genomförd åtgärd", and "Inga forskningsåtgärder".
6. THE research filters SHALL operate only on Research_Cases directly linked to the person, following Requirement 14 criterion 1.
7. WHEN the case-status filter and the research-action filter are both active with selections more specific than "Alla", THE filtering SHALL require both conditions to hold for the same directly linked Research_Case of the person, not for two different Research_Cases that happen to be linked to the same person.
8. WHERE a combination of research filter selections cannot match any person, THE dialog SHALL disable, normalize, or give clear feedback for that combination rather than silently returning misleading results.
9. THE new research filters SHALL be integrated into the existing `FilterCriteria` and `filter_persons` logic and into the "Rensa" reset behaviour, and SHALL leave every existing person-list filter (name, title, occupation, event types, date ranges, parish, DNA cluster) functioning unchanged.

### Requirement 25: Research Consistency Report

**User Story:** As a genealogist, I want a report that flags broken or doubtful research data and notes loose ends, so that I can clean up without the app deleting my research history behind my back.

#### Acceptance Criteria

1. THE application SHALL provide a consistency report titled "Forskningskonsistens", implemented as an Issue dataclass plus a pure `check_*` function plus a `generate_*` function producing a `ReportContent`, following the convention of `slaktbusken/reports/geographic.py`, and SHALL register it by promoting an existing "Forskningsrapporter" or "Konsistensrapporter" menu placeholder to a wired action.
2. THE Research_Consistency_Report SHALL report as errors: a Research_Case `primary_entity_ref` or `linked_entities` link to an entity that no longer exists; a Research_Hypothesis referencing a missing Research_Case; a Research_Action referencing a missing Research_Case; a Research_Action `source_ref` referencing a Source that no longer exists; a Research_Entity_Link whose `entity_type` is not a Supported_Entity_Type; a duplicate entity link within the same Research_Case; an invalid `status`, `priority`, or `assessment` value; an invalid `completed_date`; and an invalid Hypothesis_Comment `date`.
3. THE Research_Consistency_Report SHALL report as informational findings, grouped separately from the errors: a closed Research_Case with one or more Pending_Actions; a Research_Case with no linked entity; and a Research_Case with no Research_Action.
4. THE Research_Consistency_Report SHALL present its findings as Swedish-labelled grouped sections following the `HeadingBlock` plus `ListBlock` or `EmptyStateBlock` convention, with an empty section rendering "Inga problem hittades.", and SHALL separate error sections from informational sections visibly, since the existing report framework carries no severity enum.
5. THE Research_Model SHALL treat a Research_Case with no linked entity and no Research_Action as valid, and the application SHALL NOT automatically delete such a Research_Case.
6. EACH finding produced by the Research_Consistency_Report SHALL carry the identity of the affected research entity — at least the owning Research_Case `id`, and where applicable the Research_Hypothesis `id`, Research_Action `id`, or Hypothesis_Comment `id`, and for a broken reference the stored `entity_type` and `entity_id` or Source id — stored on the Issue dataclass so that a later navigation feature can open the affected research entity from the report, even though the rendered line remains Swedish human-readable text.
7. THE Research_Consistency_Report SHALL phrase each finding with enough Swedish context to identify the affected research entity to the reader, for example including the Research_Case title or `id`, so that a finding is actionable without the reader guessing which case it concerns.

### Requirement 26: Display of Broken Entity References

**User Story:** As a genealogist, I want a research link to an entity I deleted to be preserved for the consistency report, yet never shown in ordinary views as though the entity still exists, so that nothing looks valid when it is not.

#### Acceptance Criteria

1. THE application SHALL keep a stored Research_Entity_Link or Research_Action `source_ref` whose referenced entity no longer exists, so that the Research_Consistency_Report can report it, following Requirement 27 criterion 2.
2. WHERE an ordinary entity view, the Research_Overview, the Research_Case_Editor's "Berörda objekt", or a research tab would list a Research_Entity_Link whose referenced entity no longer resolves, THE application SHALL NOT present it as a valid, navigable link to an existing entity, and SHALL instead mark it as a broken or missing reference with a Swedish indication such as "(saknat objekt)" or omit it from the navigable list while still allowing the user to remove it.
3. THE Research_Index entity-keyed lookups SHALL return a Research_Case for an entity only while that entity resolves, so that a broken reference contributes to no research indicator, no person-list count, and no directly-linked-case list after the referenced entity is gone.
4. THE application SHALL allow the user to repair a broken reference by removing it or relinking it from the Research_Case_Editor, and removing a broken reference SHALL follow the association-removal rules of Requirement 20 criterion 4, deleting no Research_Case.

### Requirement 27: Deleting and Merging Entities

**User Story:** As a genealogist, I want my research to survive when I delete or merge the people and sources it talks about, so that reorganizing the tree never erases the investigation behind it.

#### Acceptance Criteria

1. WHEN a `Person`, `Event`, `Place`, `Source`, `Media`, DNA match, or DNA cluster is deleted from the Project, THE Delete_Service SHALL delete no Research_Case, Research_Hypothesis, Hypothesis_Comment, or Research_Action as a consequence.
2. WHEN an entity that a Research_Case, Research_Hypothesis, or Research_Action references is deleted, THE application SHALL leave the stored reference values unchanged, preserving enough information for the Research_Consistency_Report to report the now-broken reference, following the application's existing convention of keeping stored reference values and letting the validator flag them.
3. WHEN the existing functionality merges two person records or two other entities, THE application SHALL update every Research_Entity_Link and Research_Action `source_ref` that references the merged-away entity so that it references the surviving entity.
4. WHEN a merge updates research references, THE application SHALL leave no Research_Entity_Link or `source_ref` pointing at the merged-away entity, and WHERE updating a link to the survivor would duplicate an existing link within the same Research_Case, THE application SHALL collapse the duplicate following Requirement 3 criterion 7 rather than creating a duplicate listing.
5. THE Research_Service SHALL provide a dependency-reporting function in the style of `delete_service.find_residence_dependencies` that returns, for a given entity, the Research_Cases, Research_Hypotheses, and Research_Actions that reference it, so that a caller can present research consequences of a deletion without the deletion removing that research.
6. WHEN a merge rewires a Research_Action `source_ref` to the surviving Source, THE application SHALL change only the referenced Source identifier and SHALL preserve every other property of that `SourceRef` — its `quality`, its `note`, and its `aspects` — unchanged, so that the rewire never silently discards the citation's quality assessment, note, or aspect list.
7. WHEN a merge rewires a Research_Entity_Link to the surviving entity, THE application SHALL preserve that link's `role` unchanged, and WHERE collapsing a resulting duplicate under criterion 4 must choose which link survives, THE application SHALL keep a non-empty `role` in preference to an empty one and otherwise keep the first link in order.

### Requirement 28: GEDCOM Import and Export

**User Story:** As a genealogist, I want my research to survive GEDCOM updates to the tree, so that re-importing a newer GEDCOM never wipes or duplicates my research.

#### Acceptance Criteria

1. WHEN existing persons, events, families, or other entities are updated through a GEDCOM re-import, THE GEDCOM_Importer SHALL preserve the internal `id` of each entity its matching system considers the same, following the existing `TranslationData`/`PersonMapping` identity preservation, so that Research_Cases referencing those ids remain valid.
2. WHEN a GEDCOM re-import updates an entity, THE GEDCOM_Importer SHALL leave every Research_Case, Research_Hypothesis, Hypothesis_Comment, and Research_Action, together with their `source_refs` and entity links, present and unchanged, touching only the GEDCOM-derived fields of the matched entity as it already does.
3. WHEN the same GEDCOM is imported a second time, THE GEDCOM_Importer SHALL create no duplicate Research_Case, Research_Hypothesis, Hypothesis_Comment, or Research_Action.
4. WHEN a referenced person is absent from a later GEDCOM import, THE GEDCOM_Importer SHALL delete no Research_Case referencing that person and SHALL leave the stored reference unchanged for the Research_Consistency_Report to surface.
5. THE GEDCOM_Exporter SHALL NOT encode Research_Cases, Research_Hypotheses, Hypothesis_Comments, or Research_Actions into standard GEDCOM in this version, SHALL continue exporting existing genealogical data unchanged, and SHALL record the omitted research entities in `_collect_omissions` as native-only data in the manner it already records "Forskningsanteckningar", using a Swedish label such as "Forskningsärenden".
6. THE research entities SHALL remain stored in the native Släktbusken project format, and any future custom GEDCOM extension for them SHALL be handled as a separate feature.

### Requirement 29: Persistence, Migration, and Compatibility

**User Story:** As a genealogist, I want adopting this feature to cost me nothing — old projects keep opening, and my research round-trips through save and load intact — so that I can start using it without risk.

#### Acceptance Criteria

1. WHEN the Project is saved, THE Serialization_Module SHALL write the `research_cases`, `research_hypotheses`, and `research_actions` collections in their stored order, with Hypothesis_Comments nested inside their Research_Hypothesis, following the existing reflection-based serialization with omit-defaults, by adding those collection names to the `entity_fields` list and the `_ENTITY_MAP` and nested-type registries.
2. THE Serialization_Module SHALL produce, for every research entity serialized and then deserialized, an entity equal field by field, where an absent `completed_date` deserializes as absent and never as an empty string, an empty text field deserializes as an empty string and never as absent, `sort_order` round-trips as its integer value, and every Hypothesis_Comment and `source_ref` deserializes in the same list position, including Research_Cases with zero hypotheses and zero actions and Research_Hypotheses with zero comments.
3. WHEN a project file holding no `research_cases`, `research_hypotheses`, or `research_actions` key, or holding a null value for one, is loaded, THE Serialization_Module SHALL set that collection to zero elements and SHALL complete the load with zero errors, so that a pre-feature project loads unchanged.
4. THE Migration_Manager SHALL register a migration whose target version is 0.3, which adds empty `research_cases`, `research_hypotheses`, and `research_actions` collections to project data lacking them, which leaves existing research collections unchanged when applied a second time, which bumps both `version` and `format_version` to 0.3, and SHALL raise `CURRENT_VERSION` to 0.3 in both `migration.py` and `file_io.py` and the `ProjectData.version` default.
5. IF a project file's stored version is newer than 0.3, THEN THE Migration_Manager SHALL refuse the load with the existing newer-version message and SHALL leave the file unchanged on disk, so that an older application version never writes back over research data it cannot represent.
6. IF a `research_cases`, `research_hypotheses`, or `research_actions` value in a project file is present and is not a list, THEN THE Serialization_Module SHALL abort the load with a Swedish message naming the invalid research section and SHALL leave the previously open Project unchanged in memory, following the `residences` precedent.
7. WHEN a loaded research entity holds a reference that resolves to no entity in the loaded Project, THE Serialization_Module SHALL keep that entity with its stored reference values unchanged, SHALL discard no research entity, SHALL complete the load with zero errors, and SHALL record the unresolved reference in the load log, leaving the Research_Validator and the Research_Consistency_Report to report it.
8. WHEN research data is created or changed, THE Research_Service SHALL mark the Project modified, and THE application SHALL preserve UTF-8 Swedish text in `title`, `description`, `conclusion`, `statement`, `reasoning`, Hypothesis_Comment `text`, and Research_Action `title` and `text` across a save and load round-trip, and a failed save SHALL NOT silently discard research information, following the existing atomic-save convention.

### Requirement 30: User Experience and Navigation

**User Story:** As a genealogist, I want the feature to feel like part of the application I already use, with no duplicated data and no lost edits, so that research is a natural extension rather than a bolt-on.

#### Acceptance Criteria

1. THE application SHALL allow a Research_Case to be created from the Research_Overview and from any integrating entity editor, and WHEN created from an entity editor, SHALL prepopulate the Research_Entity_Link to that entity following Requirement 21.
2. THE application SHALL make the same Research_Case visible from every entity it links to, and editing a Research_Case from one location SHALL update the information shown from every other location the next time that location refreshes.
3. THE application SHALL store each Research_Case, Research_Hypothesis, Hypothesis_Comment, and Research_Action once in the Project collections, and SHALL NOT duplicate research data across the persons, places, sources, or other entities that link to it.
4. WHEN the user navigates between a Research_Case, a Research_Action, a linked entity, and a Source, THE application SHALL NOT lose unsaved edits in the originating editor.
5. THE application SHALL use the existing Qt dialog styles, list and table conventions, context menus, Source-selection flow, save and cancel mechanisms, Swedish localization in `swedish_locale.py`, settings storage, and keyboard and mouse navigation patterns, and SHALL prefer reusable widgets over a separate implementation per entity type.
6. THE application SHALL add the Swedish entity-type and status/priority/assessment labels for the research feature to the central `swedish_locale.py` label dictionaries with their getter-and-fallback convention, and SHALL keep all code identifiers and internal keys in English.

### Requirement 31: Non-Goals for the First Implementation

**User Story:** As a maintainer, I want the first implementation scoped so that it stays descriptive and extensible, so that it does not quietly take on automation the design explicitly excludes.

#### Acceptance Criteria

1. THE feature SHALL NOT automatically change any genealogical fact from a Research_Hypothesis or a Research_Case `conclusion`.
2. THE feature SHALL NOT generate a research conclusion, compute an automatic confidence percentage, or validate a Research_Hypothesis automatically from DNA data.
3. THE feature SHALL NOT integrate an external research service, schedule reminders, integrate a calendar, or provide multi-user collaboration or assignment.
4. THE feature SHALL NOT maintain a full automatic revision history of Research_Hypothesis assessments, consistent with Requirement 5 criterion 8.
5. THE feature SHALL NOT export the complete research model to standard GEDCOM, consistent with Requirement 28.
6. THE feature SHALL NOT introduce a separate database or storage system exclusively for research data, storing research in the native project format alongside the existing collections, and SHALL leave the architecture able to accept the excluded extensions later without requiring them now.
