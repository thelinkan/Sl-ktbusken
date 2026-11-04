# Requirements Document

## Introduction

Släktbusken stores each individual as one `Person` record with a stable id (`person_<n>`). Genealogists regularly end up with two records for the same individual: an import brought in a second copy, or two research threads turned out to concern one person. Today the application has no way to say "these two records may be the same person", no way to look at two persons and their families side by side, and no safe way to combine two records. Deleting one record cascades through events, families, media and residences (`execute_person_deletion`) and would destroy exactly the information a merge must keep.

This feature adds three connected workflows on top of the existing project model:

1. **Merge candidates** ("Sammanslagningskandidater"): a project-level register of pairs of person records that may represent the same individual. A candidate carries a user-set assessment, an optional enabled flag, an optional link to a research case, and dated comments. Registering a candidate never changes either person.
2. **Person comparison** ("Jämför personer"): a resizable window with two family views and a personal-information table, so the user can judge whether two records are the same individual before deciding anything.
3. **Person merging** ("Slå samman personer"): a reviewed, previewed and atomic operation that combines two person records into one, rewires every stored reference, and leaves a persistent merge history so that a later GEDCOM re-import cannot silently recreate the retired record.

The governing safety principle is that different person ids are separate person records until the user explicitly merges them. Comparison is not merging. A merge candidate is not a confirmed identity. A confirmed duplicate is not a completed merge. The same internal person id is exact record identity; similar names, dates, places or family positions are not. Relatives stay separate unless the user explicitly merges them. No merge may silently discard genealogical information or leave the project partially modified.

The feature reuses what already exists: the `Person`, `Family`, `Event`, `ResidenceFact`, `DnaProfile` and `MediaItem` models in `slaktbusken/model`; `ProjectData` and `ProjectService` (dirty flag, `FilePersistence.save`); the `IDGenerator` and the `id_high_water_marks` mechanism introduced by research cases; the reflection-based serialization in `slaktbusken/persistence/serialization.py` and `MigrationManager` (current format version `0.3`, raised to `0.4` by this feature); `rewire_entity_merge` and `find_research_dependencies` in `research_service.py`; the family diagram rendering (`FamilyView`, `DiagramPanel`, `PersonBoxItem`); `PersonSearchWidget`; the person-list research column and its `ResearchIndex`-based counts; `PersonListConfig` and `PersonBoxConfig`; the GEDCOM `TranslationData` / `PersonMapping` files under `translation/persons.json`; the `foster_sync` service that derives foster and adoptive families from placement events; and the report framework in `slaktbusken/reports` (`research_consistency.py`).

Observations from the current code that shape these requirements:

- Translation mappings (`translation/persons.json`) live in separate files beside the project file, not in `ProjectData`. A merge must therefore update and recover two storage locations.
- `PersonSearchWidget` today searches by display name only. Comparison needs name, id and date search, so the widget or a sibling is extended.
- `IDGenerator` derives its counter from live ids. A retired person id would be reused if it held the highest suffix, so retired ids must be reserved.
- Foster and adoptive families are derived from placement events by `sync_parentage_links`. A merge changes event participants, so derived families must be reconciled after rewiring and checked.
- `rewire_entity_merge(data, "person", old_id, survivor_id)` already rewires research case and hypothesis links and collapses duplicate links. It does not know about merge candidates or merge history.
- The person-list research column header and the settings checkbox are currently both labelled "Forskningsärenden", and the diagram setting in `PersonBoxConfig.research` is also labelled "Forskningsärenden". The requested labels "Forskningsuppslag" and "Forskningsuppslag och dubletter" differ from the current text; Requirements 17 and 18 define the label changes. The label "Forskningsärende" for a single research case is unchanged (for example the Candidate_Register column in Requirement 15).

All code identifiers, internal keys, and developer comments are in English. All user-facing labels, messages, menus, tooltips, and report headings are in Swedish.

## Glossary

- **Person_Comparison_Window**: The new resizable and maximizable PySide6 window "Jämför personer" containing Person_Slot 1, Person_Slot 2 and the Comparison_Table in a horizontal `QSplitter`.
- **Person_Slot**: One of the two positions (Person 1, Person 2) in the Person_Comparison_Window. Each holds zero or one person id, one Slot_Search_Control and one Comparison_Family_View.
- **Slot_Search_Control**: The person search field above a Comparison_Family_View. Reuses or extends `PersonSearchWidget` so that a person can be found by name, person id, or date, and so that results with similar names are distinguishable by dates, places and ids.
- **Comparison_Family_View**: A family diagram inside a Person_Slot, rendered by the existing family-view rendering (`FamilyView`, `ZoomableGraphicsView`, `PersonBoxItem`), with the slot's person as focal person. It has its own navigation, expansion and zoom state.
- **Comparison_Table**: The third panel, a read-only table comparing personal information of the two slot persons row by row.
- **Focal_Person**: The person a Comparison_Family_View is centred on.
- **Shared_Person**: A person id that appears in both Comparison_Family_Views. Swedish "Samma registrerade person".
- **Merge_Candidate**: A project-level record that two distinct person ids may represent the same individual. Swedish "Sammanslagningskandidat". Holds `id`, `person_1_id`, `person_2_id`, `assessment`, `enabled`, `research_case_id` and `comments`. Id prefix `mergecand_`.
- **Merge_Candidate_Comment**: A dated free-text note on one Merge_Candidate, holding `id`, `date` and `text`. Swedish "Kommentar". Id prefix `mergecomment_`.
- **Candidate_Assessment**: The user-set judgement on a Merge_Candidate, one of `unreviewed` ("Ej granskad"), `possible` ("Möjlig dubblett"), `confirmed` ("Bekräftad dublett"), `rejected` ("Inte samma person"). Swedish "Bedömning". Default `unreviewed`.
- **Unordered_Pair**: The set of two person ids of a Merge_Candidate, where (A, B) and (B, A) are the same pair.
- **Active_Candidate**: A Merge_Candidate whose `enabled` is true.
- **Candidate_Register**: The new window "Sammanslagningskandidater" listing all Merge_Candidates in a searchable, sortable, filterable table.
- **Candidate_Indicator**: The compact marker showing a person's Merge_Candidate or Merge_History relationships, in the person list and in diagram person boxes.
- **Indicator_Colour**: The colour of a Candidate_Indicator, one of orange, blue, grey, or none, determined by Indicator_Precedence.
- **Indicator_Precedence**: The single centralized rule that picks one Indicator_Colour for a person: blue if the person has an Active_Candidate with assessment `confirmed`; otherwise orange if the person has an Active_Candidate with assessment `possible` or `unreviewed`; otherwise grey if the person has only rejected candidates, disabled candidates or Merge_History entries; otherwise none.
- **Person_Merge**: The operation that combines two person records into one. Swedish "Slå samman personer".
- **Surviving_Person**: The person record that remains active after a Person_Merge. Swedish "Person som behålls".
- **Merged_Away_Person**: The person record that stops being an active `Person` after a Person_Merge. Swedish "Person som tas bort".
- **Merge_Review**: The multi-section guided process in which the user inspects and decides every aspect of a Person_Merge. Reached from the Person_Comparison_Window by "Fortsätt till sammanslagning".
- **Merge_Plan**: The in-memory description of every change a Person_Merge would make, built from the Merge_Review decisions without mutating `ProjectData`.
- **Merge_Preview**: The "Förhandsgranskning av sammanslagning" screen presenting the Merge_Plan.
- **Merge_Conflict**: A situation where the two persons hold incompatible information or structure. Swedish "Konflikt". Either a Blocking_Conflict or a Merge_Warning.
- **Blocking_Conflict**: A Merge_Conflict that prevents final confirmation until the user resolves it.
- **Merge_Warning**: A non-blocking Merge_Conflict shown in the Merge_Preview.
- **Similar_Event_Rule**: The deterministic criterion of Requirement 21 criterion 14 that decides whether one event of Person 1 and one event of Person 2 are flagged as possible duplicates: same event type, compatible dates (equal at shared precision, or both full dates within 365 days), and places that do not contradict each other. Place or type alone never suffices.
- **Merge_Engine**: The service that validates a Merge_Plan and applies it atomically.
- **Recovery_Point**: A restorable copy of all state a Person_Merge can change, created before the Merge_Engine mutates anything. It is taken from the saved state, because a Person_Merge starts only from a Project without unsaved changes (Saved_State_Precondition).
- **Saved_State_Precondition**: The rule that a Person_Merge executes only when the Project dirty flag is false and no open editor holds unsaved changes, so that the committed result never contains unsaved edits made before the merge.
- **Revision_Counter**: The Project-level counter held by Project_Service that is incremented once for each completed change notification, including a completed Person_Merge, so that views, indexes and open Merge_Reviews can detect that the Project changed.
- **Recovery_Refusal**: The outcome in which automatic recovery of a Merge_Transaction is refused because a target file matches neither the expected old state nor the expected new state, or because the Merge_Journal or the backup is corrupt. All recovery artifacts are preserved untouched.
- **Research_Gateway**: The existing mechanism through which a research indicator or other caller opens the research overview from the person list or a diagram person box.
- **Mandatory_Test_Group**: One of the test groups listed in Requirement 35, which must pass for the feature to count as complete and must not be skipped, optional, xfail-ed or deselected.
- **Merge_History**: The persistent record of completed merges. Swedish "Sammanslagningshistorik". Each Merge_History_Entry holds `id`, `surviving_person_id`, `merged_person_id`, `merged_person_name`, `merged_person_lifespan`, `merge_date`, `merge_candidate_id` (optional), an archived copy of the direct Merge_Candidate if one existed, and the identity mapping needed by the GEDCOM importer. Id prefix `merge_`.
- **Retired_Person_ID**: The id of a Merged_Away_Person. It never again denotes an active `Person` and is never reissued by the `IDGenerator`.
- **Redirect_Resolution**: The deterministic lookup that maps any Retired_Person_ID to the Surviving_Person that currently holds its identity, following Merge_History across successive merges.
- **Person_Reference_Inventory**: The documented list of every location in `ProjectData` and persisted files that stores a person id, with a Reference_Rule for each.
- **Reference_Rule**: One of `rewire`, `merge_and_deduplicate`, `preserve_separately`, `require_explicit_resolution`, `preserve_historical`, assigned per reference location.
- **Translation_Data**: The GEDCOM identity mapping container in `slaktbusken/persistence/translation_io.py`, including `PersonMapping` entries stored in `translation/persons.json`.
- **Merge_History_Window**: The non-modal window "Sammanslagningshistorik" that lists Merge_History_Entries, either those of one Surviving_Person or all of them (Requirement 36). It is the "Merge_History view" of Requirement 28 criterion 9.
- **Merge_Summary**: The list of Swedish summary lines stored in a Merge_History_Entry (`summary_lines`) that states what the merge combined (Requirement 36 criterion 1).
- **Identity_Alias**: A `PersonMapping` entry kept after a merge so that a GEDCOM id previously mapped to the Merged_Away_Person resolves to the Surviving_Person.
- **Research_Rewire_Helper**: `rewire_entity_merge` in `slaktbusken/services/research_service.py`. It is used for person references only; combining families is out of scope for version 1.
- **Merge_Transaction**: The project file together with `translation/persons.json` and any other translation file changed by one Person_Merge, treated as one recoverable logical operation.
- **Merge_Journal**: A durable marker file written beside the project file during the commit of a Merge_Transaction, listing the intended target files, the temporary files and the expected old and new content checksums of each. Swedish "Sammanslagningsjournal".
- **Synchronized_Working_Copy**: The planned working copy of the affected data after the Merge_Plan has been applied and the equivalent of `sync_parentage_links` has been run on it. The Merge_Preview and the Merge_Plan describe this copy.
- **Redirected_Candidate**: A Merge_Candidate between the Merged_Away_Person and a third person C that is redirected to the Surviving_Person and C.
- **Collision**: The situation in which a Redirected_Candidate would duplicate an existing Merge_Candidate for (Surviving_Person, C).
- **Merge_Consistency_Report**: The new consistency report "Sammanslagning och dubletter", following the convention of `slaktbusken/reports/research_consistency.py`.
- **Project**: The root container `ProjectData` (`slaktbusken/model/project.py`).
- **Project_Service**: `slaktbusken/services/project_service.py`, owning the dirty flag and save.
- **Serialization_Module**: `slaktbusken/persistence/serialization.py`.
- **Migration_Manager**: `slaktbusken/persistence/migration.py`.
- **Person_List**: The person list panel in `slaktbusken/ui/person_list_panel.py`.
- **Person_Editor**: `slaktbusken/ui/editors/person_editor.py`, including its "Forskning" tab.
- **Settings_Dialog**: `slaktbusken/ui/dialogs/settings_dialog.py`.

## Requirements

### Requirement 1: Person Reference Inventory and Merge Rules

**User Story:** As a maintainer, I want every place that stores a person id documented with a handling rule before any merge code is written, so that a merge cannot leave a dangling or wrongly rewritten reference.

#### Acceptance Criteria

1. THE Person_Reference_Inventory SHALL list each of the following reference locations found in the current code, and SHALL list any further location discovered during design: `Family.partners[].person_id`, `Family.children`, `Family.parent_child_links[].child_id` and `parent_id`, `Event.participants[].person_id`, `ResidenceFact.person_id`, `Person.profile_media_id` (reverse direction: media owned by the person), `MediaItem.linked_entities` with `entity_type` `person`, `MediaItem.mentioned_person_ids`, `MediaItem.annotations` with `entity_type` `person`, `ResearchNote.linked_entities` with `entity_type` `person`, `DnaProfile.person_id`, `DnaProfile.admin_person_id`, `DnaCluster.person_ids`, `ResearchCase.primary_entity_ref` and `linked_entities`, `ResearchHypothesis.linked_entities`, `ProjectMetadata.main_person_id`, `ProjectData.connection_overrides` keys, `Merge_Candidate.person_1_id` and `person_2_id`, `Merge_History` entries, `PersonMapping.app_id` in `translation/persons.json`, and any persisted settings or view state that stores a person id.
2. THE Person_Reference_Inventory SHALL assign exactly one Reference_Rule (`rewire`, `merge_and_deduplicate`, `preserve_separately`, `require_explicit_resolution` or `preserve_historical`) to each listed location, and SHALL state for each `rewire` location whether a resulting duplicate entry is removed so that one entry remains, or is kept as separate entries.
3. THE Person_Reference_Inventory SHALL assign `require_explicit_resolution` to any location where both persons hold a differing non-empty single-valued value, including `Person.sex`, `Person.title`, `Person.occupation`, `Person.profile_media_id` and a `connection_overrides` entry for each person as child.
4. THE Merge_Engine SHALL update each reference according to the Reference_Rule recorded for its location in the Person_Reference_Inventory, and THE Merge_Engine SHALL NOT use a generic recursive string replacement of the Retired_Person_ID.
5. WHEN the Merge_Engine rewires research references, THE Merge_Engine SHALL call the Research_Rewire_Helper with entity type `person` instead of re-implementing research link rewiring.
6. IF the Person_Reference_Inventory contains a reference location that has no completed handler, THEN THE Merge_Engine SHALL refuse to execute any Person_Merge, SHALL return an error naming each location without a handler, and SHALL leave the Project unchanged.
7. THE Person_Reference_Inventory SHALL be recorded in the design document.
8. IF a dataclass in `slaktbusken/model` has a field whose name ends in `person_id` or `person_ids` and that field is absent from the Person_Reference_Inventory, THEN the automated inventory test SHALL fail and SHALL name the dataclass and field.

### Requirement 2: Merge Candidate Entity

**User Story:** As a genealogist, I want to record that two person records may be the same individual without changing either record, so that I can park a suspicion and come back to it.

#### Acceptance Criteria

1. THE Project SHALL hold Merge_Candidates in a project-level `merge_candidates` collection, initialized as an empty list for a new Project, preserving the order in which Merge_Candidates were added, including after save and reopen.
2. THE Merge_Candidate SHALL hold `id`, `person_1_id`, `person_2_id`, `assessment` (one of the four Candidate_Assessment values, default `unreviewed`), `enabled` (boolean, default true), `research_case_id` (default absent) and `comments` (default empty ordered list), following the dataclass conventions used by `ResearchCase`.
3. WHEN a Merge_Candidate is created, THE Project_Service SHALL assign `id` using the `IDGenerator` with prefix `mergecand_` and SHALL record the issued suffix in `id_high_water_marks`, so that a deleted candidate id is not reissued after save and reopen.
4. WHEN a Merge_Candidate is created or edited, THE Project_Service SHALL set the dirty flag and SHALL leave both referenced `Person` records unmodified.
5. IF `person_1_id` equals `person_2_id`, THEN THE Project_Service SHALL reject the Merge_Candidate with the Swedish message "En person kan inte vara kandidat till sig själv.", SHALL NOT add it to `merge_candidates`, and SHALL leave the Project and its dirty flag unchanged.
6. IF `person_1_id` or `person_2_id` does not resolve to an active `Person`, THEN THE Project_Service SHALL reject creation of the Merge_Candidate with a Swedish message naming the unresolved id, SHALL NOT add it to `merge_candidates`, and SHALL leave the Project and its dirty flag unchanged.
7. THE Project_Service SHALL create a Merge_Candidate only as the result of an explicit user action, and SHALL NOT create a Merge_Candidate from similarity of names, dates, places, sex, family position or any other computed signal.
8. THE Merge_Candidate SHALL store no copy of a person name, date or place; WHEN a candidate is displayed, THE application SHALL resolve person display text from the referenced `Person` at render time.
9. IF an Unordered_Pair of `person_1_id` and `person_2_id` already exists in `merge_candidates`, THEN THE Project_Service SHALL reject creation of the new Merge_Candidate with a Swedish message stating that the pair is already registered, SHALL NOT add it to `merge_candidates`, and SHALL leave the Project and its dirty flag unchanged.
10. IF `research_case_id` is present and does not resolve to an existing `ResearchCase`, THEN THE Project_Service SHALL reject the create or edit with a Swedish message naming the unresolved id, and SHALL leave the Merge_Candidate and its dirty flag unchanged.

### Requirement 3: Candidate Assessment

**User Story:** As a genealogist, I want to set my own judgement on a candidate pair, so that the register shows what I believe and nothing is concluded for me.

#### Acceptance Criteria

1. THE Merge_Candidate SHALL accept exactly the `assessment` values `unreviewed`, `possible`, `confirmed` and `rejected`, displayed respectively as "Ej granskad", "Möjlig dubblett", "Bekräftad dublett" and "Inte samma person".
2. IF `assessment` holds any value other than `unreviewed`, `possible`, `confirmed` or `rejected` (including an empty or missing value), THEN THE validator SHALL return exactly one occurrence of the message "Ogiltig bedömning för sammanslagningskandidaten." for that Merge_Candidate and SHALL leave the stored `assessment` unchanged.
3. WHEN a Merge_Candidate is created, THE application SHALL set its `assessment` to `unreviewed`.
4. WHEN the user selects an `assessment` value for a Merge_Candidate in the user interface and confirms the selection, THE application SHALL change the Candidate_Assessment to the selected value, and THE application SHALL NOT change a Candidate_Assessment in any other way, including on project load, save, import or when a person is edited.
5. THE application SHALL NOT compute, store or display an automatic confidence value, percentage or similarity score for a Merge_Candidate.
6. WHEN the user changes `assessment`, THE application SHALL keep all existing `comments` of the Merge_Candidate unchanged in number, order and text.
7. WHEN the user sets `assessment` to `confirmed`, THE application SHALL record only the value `confirmed` and SHALL NOT start, schedule or apply a Person_Merge, nor modify any Person record referenced by the Merge_Candidate.
8. WHERE a Merge_Candidate carries `rejected`, THE application SHALL retain the Merge_Candidate in the Project and SHALL list it in the register when the register filter for "Inte samma person" is selected.
9. IF saving a changed `assessment` fails, THEN THE application SHALL display an error message indicating that the assessment was not saved and SHALL keep the previously stored `assessment` and `comments` unchanged.

### Requirement 4: Candidate Comments

**User Story:** As a genealogist, I want to add dated notes to a candidate pair, so that the reasoning behind my judgement is kept with it.

#### Acceptance Criteria

1. THE Merge_Candidate SHALL hold from 0 to 500 Merge_Candidate_Comments, each with an `id` (prefix `mergecomment_`) that is unique within the project and never changes after creation, a `date` and a `text` of 1 to 5000 characters.
2. WHEN the user adds a comment, THE application SHALL default `date` to the current local date in the form ÅÅÅÅ-MM-DD, and SHALL allow the user to edit or clear that date before saving.
3. IF a non-empty comment `date` is not a real calendar date in the form ÅÅÅÅ, ÅÅÅÅ-MM or ÅÅÅÅ-MM-DD, THEN THE validator SHALL return exactly one occurrence of the message "Kommentarens datum är inte ett giltigt datum." per comment, reusing `is_valid_calendar_date`.
4. IF the user saves a comment whose `text` is empty or contains only whitespace, or is longer than 5000 characters, THEN THE application SHALL reject the save, show an error message indicating the text is missing or too long, and keep the unsaved comment in the editor.
5. WHEN the user saves a comment, THE application SHALL leave the Merge_Candidate `assessment` unchanged.
6. WHEN the user edits, saves or loads a Merge_Candidate, THE application SHALL keep its comments in their existing order, with each comment keeping its `id`, `date` and `text`, so that a save followed by a load returns the same ordered list.
7. WHEN the user requests deletion of a comment, THE application SHALL show a confirmation prompt that names the comment `date` (or states that the comment has no date if `date` is empty), and SHALL remove the comment only after the user confirms.
8. IF the user cancels the deletion confirmation, THEN THE application SHALL keep the comment and the order and content of all other comments unchanged.

### Requirement 5: Enabled Flag and Pair Uniqueness

**User Story:** As a genealogist, I want to switch a candidate off without losing it, and I want each pair to exist only once, so that the register stays trustworthy.

#### Acceptance Criteria

1. WHEN the user disables a Merge_Candidate, THE application SHALL set `enabled` to false and SHALL retain `assessment`, `comments` and `research_case_id` unchanged.
2. THE Candidate_Register SHALL exclude every Merge_Candidate whose `enabled` is false from its default view.
3. WHEN the user selects the disabled filter in the Candidate_Register, THE Candidate_Register SHALL include all Merge_Candidates whose `enabled` is false.
4. WHEN the user enters a search query in the Candidate_Register, THE Candidate_Register SHALL include disabled Merge_Candidates in the results if either person of the pair matches the query.
5. THE Project SHALL contain at most one Merge_Candidate per Unordered_Pair, regardless of the `enabled` value, so that (A, B) and (B, A) are the same pair.
6. IF the user attempts to create a Merge_Candidate for an Unordered_Pair that already has one, whether enabled or disabled, THEN THE application SHALL open the existing Merge_Candidate, SHALL NOT create a duplicate, and SHALL leave the existing Merge_Candidate's fields unchanged.
7. THE Project SHALL allow one person to appear in any number of different Merge_Candidates, each with a different Unordered_Pair.
8. IF a loaded Project contains two or more Merge_Candidates for the same Unordered_Pair, THEN THE Merge_Consistency_Report SHALL list that pair together with every Merge_Candidate that shares it, THE application SHALL complete loading the Project, and THE application SHALL keep all of those records unchanged.

### Requirement 6: Research Case Link

**User Story:** As a genealogist, I want to tie a candidate pair to a research case, so that evidence and planned work live in the research feature.

#### Acceptance Criteria

1. THE Merge_Candidate SHALL hold either no `research_case_id` or exactly one `research_case_id` that references an existing `ResearchCase`.
2. WHEN the user confirms a selection in the research case picker (reusing `research_case_picker_dialog`), THE application SHALL store the selected case id as `research_case_id`, replace any previous value, and persist the change with the Merge_Candidate.
3. WHERE the research feature is available, WHEN the user chooses "Skapa forskningsärende" in the Candidate editor, THE Candidate editor SHALL create one `ResearchCase` through Project_Service, create exactly two `ResearchEntityLink` entries with entity type `person` (one for each person in the pair), and set `research_case_id` on the Merge_Candidate to the new case.
4. IF Project_Service fails to create the `ResearchCase` or either `ResearchEntityLink`, THEN THE Candidate editor SHALL show an error message indicating that the research case was not created, SHALL leave `research_case_id` unchanged, and SHALL leave no new `ResearchCase` or `ResearchEntityLink` persisted by that attempt.
5. WHEN the user removes the association, THE application SHALL set `research_case_id` to empty and SHALL delete neither the `ResearchCase`, its `ResearchEntityLink` entries, nor the Merge_Candidate.
6. THE application SHALL NOT copy, synchronize or derive any hypothesis assessment from a Candidate_Assessment, nor a Candidate_Assessment from a hypothesis assessment.
7. IF `research_case_id` references a case that no longer exists, THEN THE Merge_Consistency_Report SHALL include one finding per affected Merge_Candidate that identifies the candidate and the missing case id, and THE application SHALL keep the stored `research_case_id` value unchanged.
8. WHEN a research case is deleted through the research feature, THE Delete_Service SHALL NOT delete or modify any Merge_Candidate that references the case.
### Requirement 7: Persistence and Format Migration

**User Story:** As a genealogist, I want candidates, comments and merge history saved with my project, so that nothing is lost between sessions and old projects still open.

#### Acceptance Criteria

1. WHEN a Project is saved, THE Serialization_Module SHALL write `merge_candidates` and `merge_history` as top-level collections in the compressed JSON project file, preserving collection order, stable ids, comment order and Swedish characters (å, ä, ö, Å, Ä, Ö) unchanged.
2. WHEN the Serialization_Module reads a project file that lacks `merge_candidates`, `merge_history` or both, THE Serialization_Module SHALL load the Project with each missing collection empty, SHALL leave any present collection unchanged, and SHALL raise no error.
3. WHEN the Migration_Manager migrates a project from a version lower than the new version, THE Migration_Manager SHALL raise `CURRENT_VERSION` from `0.3` to `0.4` and SHALL register an additive migration that adds the empty collections and leaves every other part of the project unchanged. Applying the migration a second time to its own output SHALL produce a project identical to the first result (idempotent).
4. FOR ALL valid Projects, serializing then deserializing then serializing SHALL produce an equivalent Project including Merge_Candidates, Merge_Candidate_Comments and Merge_History entries (round-trip property). The two serialized outputs SHALL be equal in content, and every field of every entry SHALL be equal after deserialization.
5. WHEN a Project is saved, THE Serialization_Module SHALL persist the Retired_Person_ID set, either derived from Merge_History or stored explicitly. WHEN a project is opened, THE application SHALL seed the `IDGenerator` with every Retired_Person_ID so that none of them is issued again.
6. WHEN a Project is saved, THE Serialization_Module SHALL persist the `id_high_water_marks` entries for the prefixes `mergecand_`, `mergecomment_` and `merge_`. WHEN the project is reopened, each of these prefixes SHALL issue ids greater than every existing id with that prefix.
7. IF a Merge_Candidate, comment or Merge_History entry is malformed on load (a required field is missing, a field has the wrong type, or the entry cannot be parsed), THEN THE Serialization_Module SHALL keep every readable field of the entry, SHALL record the entry id and the affected field names for the Merge_Consistency_Report, SHALL NOT delete the entry, and SHALL still open the Project.
8. WHEN `MigrationManager.create_backup` runs for this migration, THE application SHALL create the same pre-migration backup, with the same naming and location rules, as for earlier migrations.
9. WHEN `MigrationManager.create_backup` or the Merge_Transaction backup (Recovery_Point) of Requirement 27 is created, THE application SHALL include `translation/persons.json` in that backup, so that a restored backup contains the identity mappings needed to repeat a merge safely. This criterion applies only to those two backups and SHALL NOT require implementing a general-purpose project backup feature.
10. IF `translation/persons.json` does not exist when `MigrationManager.create_backup` or the Merge_Transaction backup is created, THEN THE application SHALL complete that backup without error and without the file.
11. IF writing the project file fails during save (for example the disk is full or the file is locked), THEN THE Serialization_Module SHALL leave the previously saved project file unchanged and SHALL report an error indicating that the save failed.
12. WHEN a Person_Merge is committed, THE Project_Service SHALL write the project file and the changed translation files as one Merge_Transaction under the commit protocol of Requirement 27 criteria 14 to 18, and a project file and `translation/persons.json` written by a Merge_Transaction SHALL be consistent with each other after any interruption.
13. WHEN a project is opened, THE application SHALL perform the Merge_Journal recovery of Requirement 27 criterion 16 before the Serialization_Module reads the project file, and IF recovery is refused under Requirement 27 criterion 25, THEN THE application SHALL NOT read or open the project file.
14. THE compatibility and regression tests for a project without Merge_Candidates and Merge_History SHALL explicitly permit differences in the `version` field and the `format_version` field only between the serialisation produced before this feature and the serialisation produced after this feature, and SHALL fail on any other difference.

### Requirement 8: Merge Menus and Entry Points

**User Story:** As a genealogist, I want to reach comparison and the candidate register from the places I already work, so that I do not need a separate merge command.

#### Acceptance Criteria

1. WHEN the user chooses the action "Jämför personer..." in the Person menu, THE main window SHALL open the Person_Comparison_Window with both Person_Slots empty.
2. THE main window SHALL add the action "Sammanslagningskandidater" to the Forskning menu after "Hypoteser", which opens the Candidate_Register, and SHALL keep "Forskningsöversikt", "Att göra" and "Hypoteser" unchanged.
3. THE main window SHALL provide no menu command that starts a Person_Merge directly.
4. WHEN exactly two persons are selected in the Person_List, THE context menu SHALL enable "Jämför personer..." and "Markera som sammanslagningskandidater".
5. WHEN exactly one person is selected in the Person_List, THE context menu SHALL enable "Jämför personer..." and SHALL disable "Markera som sammanslagningskandidater".
6. WHEN zero persons or three or more persons are selected in the Person_List, THE context menu SHALL disable both "Jämför personer..." and "Markera som sammanslagningskandidater".
7. WHEN the user chooses "Jämför personer..." from the context menu, THE application SHALL open the Person_Comparison_Window with the selected persons placed in the Person_Slots in the order they appear in the Person_List, leaving the second Person_Slot empty if only one person is selected.
8. WHEN the user chooses "Markera som sammanslagningskandidater" for two selected persons, THE application SHALL create the Merge_Candidate or open the existing one for that Unordered_Pair, and SHALL open the candidate editor for it.
9. IF creating the Merge_Candidate fails, THEN THE application SHALL display an error message indicating that the candidate could not be created, SHALL leave the stored Merge_Candidates unchanged, and SHALL NOT open the candidate editor.
10. THE application SHALL allow the Person_Comparison_Window and the Merge_Review to be started for a pair that has no saved Merge_Candidate.
11. WHILE no project is open, THE application SHALL disable all actions added by this feature.
12. THE Person_List SHALL use `ExtendedSelection` so that the user can select more than one person, while keeping the existing single-click navigation: WHEN the user selects exactly one person by a plain click, THE application SHALL set that person as the current person exactly as before this feature.
13. WHEN the user Ctrl-clicks a row, THE Person_List SHALL add that row to or remove it from the selection, and WHEN the user Shift-clicks a row, THE Person_List SHALL select the contiguous range from the anchor row to the clicked row; in both cases THE Person_List SHALL follow standard Qt `ExtendedSelection` behaviour.
14. WHEN the user right-clicks a row that is part of an existing selection of two or more persons, THE Person_List SHALL open the context menu without clearing or changing the selection.
15. WHEN the user right-clicks a row that is not part of the current selection, THE Person_List SHALL select the clicked row only and open the context menu, as before this feature.
16. THE automated test suite SHALL contain regression tests for Ctrl-click selection, Shift-click selection, the context menus (including a right-click inside an existing two-person selection, which leaves the selection unchanged, and a right-click outside the selection, which selects the clicked row) and current-person navigation by single click.

### Requirement 9: Selecting Persons in the Comparison Window

**User Story:** As a genealogist, I want to open the comparison with the right persons already in place and swap either one freely, so that I can work through several comparisons in one window.

#### Acceptance Criteria

1. WHEN the Person_Comparison_Window is opened with exactly two selected persons, THE Person_Comparison_Window SHALL populate Person_Slot 1 and Person_Slot 2 with those persons in the order they appear in the Person_List, so that the same selection always yields the same slot order.
2. WHEN the Person_Comparison_Window is opened with exactly one selected person, THE Person_Comparison_Window SHALL populate Person_Slot 1, leave Person_Slot 2 empty, and move keyboard focus to the Slot_Search_Control of Person_Slot 2.
3. WHEN the Person_Comparison_Window is opened with no selected person, THE Person_Comparison_Window SHALL leave both Person_Slots empty.
4. WHEN the Person_Comparison_Window is opened from the Person_Editor, THE Person_Comparison_Window SHALL populate Person_Slot 1 with the edited person and move keyboard focus to the Slot_Search_Control of Person_Slot 2.
5. WHEN the Person_Comparison_Window is opened from the Candidate_Register, THE Person_Comparison_Window SHALL populate both Person_Slots from the saved pair and SHALL display the Candidate_Assessment and the comments of that Merge_Candidate.
6. WHEN the user activates the action "Byt plats", THE Person_Comparison_Window SHALL swap the persons of the two Person_Slots, including the case where one Person_Slot is empty, and SHALL update both Comparison_Family_Views, the Comparison_Table and the displayed candidate relation within 1 second.
7. WHEN the user enters at least 2 characters in a Slot_Search_Control, THE Slot_Search_Control SHALL list up to 50 persons whose name, person id or birth or death date contains the entered text (case-insensitive), and SHALL show with each result the person name, life dates, birth place and person id.
8. IF a search in a Slot_Search_Control matches no person, THEN THE Slot_Search_Control SHALL show a Swedish message stating that no person was found, and SHALL leave the current slot content unchanged.
9. WHEN the user selects a person from the Slot_Search_Control results, THE Person_Comparison_Window SHALL place that person in the corresponding Person_Slot without closing the Person_Comparison_Window; this applies to either Person_Slot, whether it is empty or already holds a person.
10. IF the user selects for one Person_Slot the same person id that the other Person_Slot holds, THEN THE Person_Comparison_Window SHALL reject the selection with the Swedish message "En person kan inte jämföras med sig själv." and SHALL keep the previous slot content.
11. WHEN a Person_Slot's person is replaced, THE Person_Comparison_Window SHALL update both Comparison_Family_Views, the Comparison_Table and the displayed candidate relation for the new pair within 1 second.
12. WHEN a Person_Slot's person is replaced, THE Person_Comparison_Window SHALL NOT carry over the assessment or comments of the previous pair to the new pair; the new pair shows its own saved Merge_Candidate or none.

### Requirement 10: Comparison Window Layout and Family Views

**User Story:** As a genealogist, I want to see both persons' families side by side with their personal details, so that I can judge identity from context rather than from names alone.

#### Acceptance Criteria

1. WHEN the Person_Comparison_Window opens, THE Person_Comparison_Window SHALL arrange Comparison_Family_View 1, Comparison_Family_View 2 and the Comparison_Table in a horizontal `QSplitter` with initial width proportions of 35%, 35% and 30%, each within a tolerance of ±2 percentage points.
2. THE Person_Comparison_Window SHALL allow the user to resize each panel by dragging the splitter handles and SHALL provide a window maximize control.
3. THE Comparison_Family_View SHALL render through the existing family-view rendering and SHALL NOT be implemented as a plain list of relatives.
4. THE Comparison_Family_View SHALL place a Slot_Search_Control above it and SHALL show the slot's person as Focal_Person.
5. WHEN a Person_Slot receives a person, THE Comparison_Family_View SHALL, within 2 seconds for a Focal_Person with up to 50 directly related persons, show the Focal_Person's parents, partners, children and siblings, as the existing family view shows them.
6. THE Comparison_Family_View SHALL represent each `ParentChildLink.parentage_type` value defined by the data model (including biological, adoptive, foster, step, legal and other) using the same connection styling as the existing family diagram.
7. WHEN the user requests expansion of a displayed person in a Comparison_Family_View, THE Comparison_Family_View SHALL show that person's parents, partners and children, without changing the other Comparison_Family_View.
8. WHEN the user navigates to another displayed person or changes zoom in a Comparison_Family_View, THE Comparison_Family_View SHALL apply the change to that view only and SHALL leave the other Comparison_Family_View's displayed persons and zoom level unchanged.
9. WHEN the user navigates within a Comparison_Family_View, THE Person_Comparison_Window SHALL keep the Person_Slot's person unchanged until the user explicitly assigns a displayed person to the slot.
10. WHILE the two slot persons appear in each other's Comparison_Family_Views, THE Person_Comparison_Window SHALL render both views without error and without altering either view's Focal_Person.
11. THE Comparison_Family_View SHALL apply the Settings_Dialog diagram settings for person-box fields and parentage display options, so that its person boxes show the same fields as the existing family diagram.
12. WHEN project data changes while the Person_Comparison_Window is open, THE Person_Comparison_Window SHALL refresh both Comparison_Family_Views and the Comparison_Table within 2 seconds, keeping each view's Focal_Person and zoom level unchanged.
13. IF a Person_Slot is empty, THEN THE Comparison_Family_View SHALL show an empty-state indication that no person is assigned, and THE Comparison_Table SHALL show no values for that slot.
14. IF a project data change deletes the person assigned to a Person_Slot, THEN THE Person_Comparison_Window SHALL clear that slot, show the empty-state indication, and keep the other slot's person unchanged.

### Requirement 11: Personal Information Comparison Table

**User Story:** As a genealogist, I want a row-by-row comparison of the two persons' details, so that matches, gaps and conflicts are easy to see.

#### Acceptance Criteria

1. THE Comparison_Table SHALL show one row per attribute and one column per slot person, covering names including alternative names, sex, birth date and place, death date and place, occupation, title, notes, profile photo, events relevant to identity, residences, and DNA profiles.
2. THE Comparison_Table SHALL resolve every value from the existing `Person`, `Event`, `ResidenceFact` and `DnaProfile` data at render time and SHALL NOT keep a second authoritative copy of any value.
3. WHEN both slot persons hold a value for an attribute and the values differ, THE Comparison_Table SHALL mark the row as "Avviker". Values are equal when they are identical after trimming leading and trailing whitespace and ignoring letter case. Dates are equal only when they have the same precision and the same value. For multi-valued attributes (alternative names, events, residences, DNA profiles), the values differ when the two sets of items are not equal, regardless of item order.
4. WHEN exactly one slot person holds a value for an attribute, THE Comparison_Table SHALL mark the row as "Saknas" on the empty side, and SHALL render the mark differently from "Avviker". A value that is empty or contains only whitespace counts as no value.
5. WHEN both slot persons hold equal values, THE Comparison_Table SHALL render the row without a conflict mark.
6. THE Comparison_Table SHALL explain in a tooltip or legend that "Avviker" is an observation for the user to weigh and is not evidence that the persons are different individuals.
7. WHERE a value has source references, THE Comparison_Table SHALL let the user open each referenced source from that value.
8. WHILE the Person_Comparison_Window is in the comparison stage, THE Comparison_Table and both Comparison_Family_Views SHALL NOT modify any genealogical data.
9. WHEN either slot is empty, THE Comparison_Table SHALL show the populated column only and SHALL leave the other column blank. THE Comparison_Table SHALL NOT apply "Avviker" or "Saknas" marks to any row.
10. IF a referenced source cannot be opened, THEN THE Comparison_Table SHALL show an error message indicating that the source is unavailable, SHALL keep the Person_Comparison_Window open, and SHALL leave all displayed values and marks unchanged.
11. WHEN a slot person's data changes while the Person_Comparison_Window is open, THE Comparison_Table SHALL re-resolve all values and recompute all marks within 1 second.

### Requirement 12: Shared Persons in Both Family Views

**User Story:** As a genealogist, I want to see at a glance when both family views contain the very same record, so that I do not mistake a shared relative for a duplicate.

#### Acceptance Criteria

1. WHEN a person id appears in both Comparison_Family_Views, THE Person_Comparison_Window SHALL mark that person's box in both views with the same Shared_Person marker, for parents, partners and children alike.
2. THE Shared_Person marker SHALL differ from any Candidate_Indicator in both symbol and color, and SHALL show the tooltip "Samma registrerade person i båda familjevyerna" within 500 ms when the pointer rests on the marker or the marker receives keyboard focus.
3. WHEN two different person ids appear, one in each Comparison_Family_View, and a Merge_Candidate exists for that Unordered_Pair, THE Person_Comparison_Window SHALL show the Candidate_Assessment on both boxes.
4. WHEN the user activates the Candidate_Assessment on a box in the situation described in criterion 3, THE Person_Comparison_Window SHALL open the comments of that Merge_Candidate within 1 second.
5. WHEN two different person ids appear, one in each Comparison_Family_View, and no Merge_Candidate exists for that Unordered_Pair, THE Person_Comparison_Window SHALL show neither a Shared_Person marker, a Candidate_Indicator, nor any connecting line between the two boxes.
6. THE Person_Comparison_Window SHALL NOT pair, link, mark or select two different person ids on the basis of name, date, sex, place, family position or similarity of any kind.
7. WHEN two siblings with the same name appear in one Comparison_Family_View or across both views, THE Person_Comparison_Window SHALL treat them as distinct persons identified by id, and SHALL show a Shared_Person marker only if their ids are identical.
8. WHEN the content of either Comparison_Family_View changes, THE Person_Comparison_Window SHALL update all Shared_Person markers to match the new content within 1 second.
### Requirement 13: Registering Candidates for Displayed Relatives

**User Story:** As a genealogist, I want to pick any person shown on the left and any person shown on the right and register them as a candidate pair, so that I can record "the two fathers might be one man" while comparing the children.

#### Acceptance Criteria

1. WHEN the user clicks a displayed person in Comparison_Family_View 1 or Comparison_Family_View 2, THE Person_Comparison_Window SHALL mark that person as the selected person for that view, SHALL replace any previously selected person in the same view, and SHALL keep at most one selected person per view.
2. WHILE one person is selected in Comparison_Family_View 1 and one person is selected in Comparison_Family_View 2, THE Person_Comparison_Window SHALL show the selected pair in an action area with the actions "Markera valda som kandidater" and "Jämför dessa".
3. WHILE fewer than two persons are selected (one per view), THE action area SHALL disable both actions "Markera valda som kandidater" and "Jämför dessa".
4. THE Person_Comparison_Window SHALL set a selected pair only from explicit user clicks, and SHALL NOT infer, preselect or suggest a pair.
5. IF both selected persons carry the same person id, THEN THE action area SHALL disable both actions and show the message "Samma registrerade person kan inte vara kandidat till sig själv."
6. WHEN the user chooses "Markera valda som kandidater" with a valid pair selected, THE Person_Comparison_Window SHALL create the Merge_Candidate for the selected Unordered_Pair, or open the existing Merge_Candidate if one already exists for that pair, SHALL allow setting the Candidate_Assessment and adding a dated comment, and SHALL return to the original comparison with Person_Slots, view state and Comparison_Table unchanged.
6a. WHILE both Person_Slots are filled with two different persons, THE Person_Comparison_Window SHALL offer a toolbar action "Markera dessa som kandidater", enabled regardless of in-view selection, that creates or opens the Merge_Candidate for the slot pair and opens its candidate panel; IF creating or opening it fails, THEN THE window SHALL show an error message indicating that the candidates could not be registered and SHALL leave the comparison unchanged.
7. IF creating or opening the Merge_Candidate fails, THEN THE Person_Comparison_Window SHALL show an error message indicating that the candidate could not be registered, SHALL keep the current selection, and SHALL NOT create a partial Merge_Candidate.
8. WHEN the user chooses "Jämför dessa" with a valid pair selected, THE Person_Comparison_Window SHALL show the two selected persons in the Person_Slots for comparison.
9. THE Person_Comparison_Window SHALL allow at least 20 Merge_Candidates to be registered during one review, including the pair of fathers and the pair of mothers, without closing the window.
10. WHEN a Merge_Candidate is registered for relatives, THE application SHALL NOT merge, modify or reassign any relative as a side effect.
11. WHEN the user closes the candidate editor with unsaved comment text, THE application SHALL ask whether to save, discard or return, and SHALL NOT silently discard the text.
12. IF the user chooses to return when asked about unsaved comment text, THEN THE application SHALL keep the candidate editor open with the unsaved text unchanged.

### Requirement 14: Sub-Comparison and Navigation Back

**User Story:** As a genealogist, I want to dive into a comparison of two relatives and come back to where I was, so that I do not lose my place or unsaved notes.

#### Acceptance Criteria

1. WHEN the user chooses "Jämför dessa", THE Person_Comparison_Window SHALL show a comparison of the selected pair in the same window and SHALL push the previous comparison context (slot persons, Comparison_Family_View focus, expansion state, zoom level and selections) onto a navigation stack.
2. WHILE the navigation stack contains at least one entry, THE Person_Comparison_Window SHALL show an enabled navigation control labelled "Tillbaka till föregående jämförelse".
3. WHILE the navigation stack is empty, THE Person_Comparison_Window SHALL NOT show the "Tillbaka till föregående jämförelse" control as enabled.
4. WHEN the user chooses "Tillbaka till föregående jämförelse", THE Person_Comparison_Window SHALL pop exactly one entry from the navigation stack and restore its slot persons, Comparison_Family_View focus, expansion state, zoom level and selections, and SHALL complete the restore within 1 second.
5. THE Person_Comparison_Window SHALL implement sub-comparison within a single window and SHALL NOT open nested modal dialogs for it.
6. IF unsaved comment text exists WHEN the user chooses "Jämför dessa" or "Tillbaka till föregående jämförelse", THEN THE Person_Comparison_Window SHALL show a prompt offering exactly three choices: save, discard or stay, and SHALL NOT change the current comparison until the user selects one.
7. WHEN the user selects "stay" in the unsaved-comment prompt, THE Person_Comparison_Window SHALL close the prompt, keep the current comparison and navigation stack unchanged, and retain the unsaved comment text.
8. IF saving the comment fails after the user selects "save", THEN THE Person_Comparison_Window SHALL show an error message indicating the save failed, remain on the current comparison, keep the navigation stack unchanged and retain the unsaved comment text.
9. THE Person_Comparison_Window SHALL support repeated sub-comparisons up to a navigation stack depth of 20 entries, and each activation of "Tillbaka till föregående jämförelse" SHALL return exactly one level.
10. IF the navigation stack already contains 20 entries WHEN the user chooses "Jämför dessa", THEN THE Person_Comparison_Window SHALL show a message indicating the maximum sub-comparison depth is reached and SHALL keep the current comparison and navigation stack unchanged.

### Requirement 15: Candidate Register

**User Story:** As a genealogist, I want one central list of all candidate pairs, so that I can review, filter and revisit them.

#### Acceptance Criteria

1. THE Candidate_Register SHALL list each Merge_Candidate as one table row with the columns "Person 1", "Person 2", "Bedömning", "Aktiv", "Senaste kommentar" and "Forskningsärende", in that order.
2. WHEN the user selects a column header, THE Candidate_Register SHALL sort the rows by that column in ascending order, and SHALL sort in descending order when the user selects the same header again.
3. WHEN the user enters search text of 1 to 200 characters, THE Candidate_Register SHALL show only rows where a case-insensitive substring match exists in a person name, a person id, comment text or research case title, and SHALL show all rows that pass the active filters when the search text is empty.
4. THE Candidate_Register SHALL offer filters for Candidate_Assessment (`unreviewed`, `possible`, `confirmed`, `rejected`), enabled or disabled, a specific person, candidate name or id, and linked research case, and SHALL show only rows that satisfy all active filters and the search text combined.
5. WHEN the Candidate_Register is opened, THE Candidate_Register SHALL by default show Active_Candidates with assessment `unreviewed`, `possible` or `confirmed`, and SHALL make `rejected` and disabled candidates visible only when the corresponding filter is selected.
6. WHEN the user double-clicks a row, THE application SHALL open the Person_Comparison_Window with both persons of that row preselected.
7. WHEN the user edits Candidate_Assessment, `enabled`, `research_case_id` or a comment in the Candidate_Register, THE Candidate_Register SHALL save the change to the Merge_Candidate without starting a Person_Merge and without modifying either person.
8. IF saving an edit from the Candidate_Register fails, THEN THE Candidate_Register SHALL keep the previously stored value in the row and SHALL show an error message indicating that the change was not saved.
9. THE Candidate_Register SHALL show "Senaste kommentar" as the comment with the latest non-empty `date`, falling back to the last comment in stored order when no comment has a non-empty `date`, and SHALL show an empty cell when no comment exists.
10. WHEN a Merge_Candidate, a person or a research case is created, changed or deleted, THE Candidate_Register SHALL refresh its rows within 1 second while preserving the active sort, search text and filters.
11. WHILE a referenced person has no resolvable name, THE Candidate_Register SHALL show the person id in place of the name.
12. IF no Merge_Candidate matches the active filters and search text, THEN THE Candidate_Register SHALL show an empty table together with a message indicating that no candidates match.

### Requirement 16: Person Editor Integration

**User Story:** As a genealogist, I want to see and manage a person's candidate pairs while editing that person, so that I do not leave the editor to find them.

#### Acceptance Criteria

1. WHEN the "Forskning" tab of the Person_Editor is displayed for a saved person, THE Person_Editor SHALL show a section "Sammanslagningskandidater" listing every Merge_Candidate that involves the edited person, except rejected and disabled Merge_Candidates while "Visa historiska" is off.
2. THE section SHALL show for each entry the other person's name, the other person's birth and death years (or a placeholder for each unknown year), the Candidate_Assessment, the enabled state, and the text of the most recent comment truncated to 100 characters.
3. IF the edited person has no Merge_Candidate visible under the current "Visa historiska" setting, THEN THE section SHALL show an empty-state message indicating that no candidates exist.
4. WHEN the user selects the open-candidate action for an entry, THE Person_Editor SHALL open the candidate record for that Merge_Candidate.
5. WHEN the user selects the compare action for an entry, THE Person_Editor SHALL open the Person_Comparison_Window for the pair.
6. WHEN the user chooses another person through the person search and confirms, THE Person_Editor SHALL create a Merge_Candidate between the edited person and the chosen person and show it in the section.
7. IF the chosen person is the edited person itself, or a Merge_Candidate for the same pair already exists, THEN THE Person_Editor SHALL reject the creation, show an error message indicating the reason, and leave the existing candidates unchanged.
8. THE section SHALL provide a toggle "Visa historiska" that is off by default; WHILE the toggle is off, THE section SHALL hide Merge_Candidates with Candidate_Assessment `rejected` and disabled Merge_Candidates, and WHILE it is on, THE section SHALL include them.
9. THE Person_Editor SHALL read candidate data from the project-level collection and SHALL store no candidate data on `Person`.
10. WHEN a Merge_Candidate involving the edited person is created, changed or deleted, THE Person_Editor SHALL refresh the section within 500 ms, preserving the "Visa historiska" setting.
11. WHILE the edited person is new and unsaved, THE section SHALL disable candidate creation and show an indication that the person must be saved first.
12. WHEN the edited person is saved for the first time, THE section SHALL enable candidate creation.

### Requirement 17: Person List Indicators and Setting

**User Story:** As a genealogist, I want research and duplicate markers together in the existing research column, so that the list stays compact.

#### Acceptance Criteria

1. THE Settings_Dialog SHALL label the person-list visibility checkbox in "Personlista" under "Synliga kolumner och ikoner" as "Forskningsuppslag och dubletter", and that single setting SHALL control both the research indicator and the Candidate_Indicator in the Person_List.
2. THE Person_List SHALL keep the existing research column in place and SHALL NOT add a column for the Candidate_Indicator, so that the total number of Person_List columns is unchanged by this feature.
3. THE Person_List SHALL label the research column header "Forskningsuppslag", replacing the current header text "Forskningsärenden". THE header context-menu toggle for that column SHALL be labelled exactly "Forskningsuppslag och dubletter", the same text as the Settings_Dialog checkbox of criterion 1, and the two controls SHALL change the same combined setting.
4. WHILE the setting is enabled, THE Person_List SHALL render the research indicator and the Candidate_Indicator side by side inside the research column cell, as two separate indicators with the research indicator on the left and the Candidate_Indicator on the right.
5. IF the setting is disabled, THEN THE Person_List SHALL hide both the research indicator and the Candidate_Indicator for all persons while retaining the stored Merge_Candidate and Merge_History data unchanged.
6. THE research indicator SHALL keep its existing counts and tooltip, and its click action SHALL change only as specified in criteria 8 and 15.
7. THE Candidate_Indicator SHALL have its own tooltip and its own click target, independent of the research indicator, such that a click on one indicator never triggers the action of the other.
8. WHEN the user clicks the research indicator of a person in the Person_List, THE Person_List SHALL open the research overview through the Research_Gateway filtered to that person, so that only the research items that involve that person are listed, and SHALL NOT open the unfiltered research overview.
9. WHEN the user clicks the Candidate_Indicator and the person has at least one Merge_Candidate, THE Person_List SHALL open the Candidate_Register filtered to that person.
10. WHEN the user clicks the Candidate_Indicator and the indicator is grey only because of Merge_History, THE Person_List SHALL open the Merge_History view for that person.
11. IF the Indicator_Colour of a person is none, THEN THE Person_List SHALL show no Candidate_Indicator for that person and SHALL leave the research indicator position unchanged.
12. WHEN a Merge_Candidate or Merge_History entry changes, THE Person_List SHALL refresh the Candidate_Indicator of each affected person within 1 second and without reloading the project or resetting the list's scroll position and selection.
13. WHEN a project saved before this feature is loaded, THE Settings_Dialog SHALL treat the existing `PersonListConfig.research` value as the value of the combined setting, so that the checkbox state equals the previously saved value.
14. IF a project is loaded with no stored `PersonListConfig.research` value, THEN THE Settings_Dialog SHALL treat the combined setting as enabled.
15. THE Research_Gateway SHALL accept an optional person filter holding one person id, and WHEN the Research_Gateway opens the research overview with a person filter, THE research overview SHALL apply that filter and SHALL show an indication of the active filter and the filtered person's name together with a control that removes the filter.
16. WHEN the Research_Gateway is called without a person filter, THE Research_Gateway SHALL behave exactly as before this feature, so that all existing callers of the Research_Gateway are unchanged.

### Requirement 18: Diagram Person-Box Indicators and Settings

**User Story:** As a genealogist, I want to choose separately whether diagram boxes show research markers and duplicate markers, so that the boxes stay as small as I want.

#### Acceptance Criteria

1. THE Settings_Dialog SHALL provide, in "Diagram" under the person-box visible fields group, two independent checkboxes labelled "Forskningsuppslag" and "Sammanslagningskandidater", where changing one checkbox SHALL NOT change the state of the other.
2. THE Settings_Dialog SHALL store the "Sammanslagningskandidater" value as a new boolean in `PersonBoxConfig` with default true.
3. IF a settings file lacks the "Sammanslagningskandidater" value, THEN THE Settings_Dialog SHALL load the setting as true and SHALL NOT report an error.
4. THE "Forskningsuppslag" checkbox SHALL control the existing `PersonBoxConfig.research` value, and its stored value and default SHALL remain unchanged.
5. THE diagram settings SHALL be independent of the combined Person_List setting, so that changing either one does not change the other's stored value.
6. WHILE both settings are enabled and both indicators are relevant for a person, THE PersonBoxItem SHALL show the research indicator and the Candidate_Indicator side by side without overlapping each other.
7. THE PersonBoxItem SHALL show the indicators without adding a text row and with the same box width and height in pixels as when no indicator is shown.
8. WHILE the "Sammanslagningskandidater" setting is disabled, THE PersonBoxItem SHALL show no Candidate_Indicator and the diagram renderer SHALL NOT build the candidate index.
9. THE PersonBoxItem SHALL give the Candidate_Indicator its own tooltip and its own click target, and SHALL NOT reuse the marker shape or colour set of the research indicator.
10. WHEN the user clicks the Candidate_Indicator, THE PersonBoxItem SHALL trigger only the candidate action and SHALL NOT trigger the research indicator action.
11. WHEN a diagram render starts, THE diagram renderer SHALL build the candidate index exactly once for that render, following the pattern of `begin_diagram_render`, and SHALL NOT scan `merge_candidates` per box.
12. WHEN the user changes either diagram setting and confirms, THE diagram renderer SHALL apply the new values on the next render of the diagram.
13. THE Comparison_Family_View SHALL apply the same diagram settings, and THE Person_Comparison_Window SHALL NOT show the Candidate_Indicator of the currently compared pair in a way that hides the Shared_Person marker.
14. WHEN the user clicks the research indicator of a person in a PersonBoxItem, THE PersonBoxItem SHALL open the research overview through the Research_Gateway filtered to that person, as specified in Requirement 17 criteria 8, 15 and 16, and SHALL NOT open the unfiltered research overview.

### Requirement 19: Indicator Colours and Tooltips

**User Story:** As a genealogist, I want the colour and tooltip of the duplicate marker to follow one clear rule, so that I can trust what I see.

#### Acceptance Criteria

1. THE application SHALL compute Indicator_Colour in one central function applying Indicator_Precedence, and THE Person_List, the diagrams and the Person_Editor SHALL all call that function and SHALL display the same colour for the same person at the same time.
2. WHEN a person has an Active_Candidate with assessment `confirmed`, THE Candidate_Indicator SHALL be blue, regardless of any other candidates, Merge_History entries or relationships the person has.
3. WHEN a person has no Active_Candidate with assessment `confirmed` and has at least one Active_Candidate with assessment `possible` or `unreviewed`, THE Candidate_Indicator SHALL be orange, regardless of any rejected or disabled candidates or Merge_History entries the person also has.
4. WHEN a person has no Active_Candidate with assessment `confirmed`, `possible` or `unreviewed`, and has at least one `rejected` candidate, disabled candidate or Merge_History entry, THE Candidate_Indicator SHALL be grey.
5. WHEN a person has no candidate and no Merge_History entry, THE Candidate_Indicator SHALL be absent and THE tooltip SHALL NOT be shown.
6. WHEN the user hovers over the Candidate_Indicator for 500 milliseconds, THE application SHALL show a tooltip listing every relationship of the person, one per line, using these Swedish forms: "Möjlig dublett med <namn> (<år–år>)", "Bekräftad dublett med <namn> (<år–år>)", "Inte samma person som <namn> (<år–år>)", "Dublettkontroll avstängd: <namn> (<år–år>)", and "Slogs samman med <namn> (<år–år>)".
7. IF a person has more than five relationships, THEN THE tooltip SHALL show the first five lines followed by one summary line stating the total number of relationships, and SHALL order the lines by Indicator_Precedence (confirmed, then possible/unreviewed, then rejected, then disabled, then merged), using the person name in ascending alphabetical order within the same group.
8. IF a birth year or death year is missing, THEN THE tooltip SHALL render the lifespan with the available year only, in the form "(<år>)" for a birth year only and "(–<år>)" for a death year only, and SHALL omit the parentheses WHEN both years are missing.
9. WHEN the assessment is `unreviewed`, THE tooltip SHALL use the form "Ej granskad kandidat: <namn> (<år–år>)".
10. THE tooltip SHALL resolve names and years from the current `Person` data at the time it is shown, and SHALL use `merged_person_name` and `merged_person_lifespan` from Merge_History for a Merged_Away_Person.
11. IF the `Person` data for a related person cannot be found and no Merge_History entry exists for it, THEN THE tooltip SHALL show the relationship line with the name replaced by the text "Okänd person" and no lifespan, and SHALL still show the remaining lines.
### Requirement 20: From Comparison to Merging, and the Surviving Person

**User Story:** As a genealogist, I want to move from comparing to merging only by a deliberate step, and to decide which record survives, so that no merge happens by accident or by an algorithm's choice.

#### Acceptance Criteria

1. THE Person_Comparison_Window SHALL provide the button "Fortsätt till sammanslagning".
2. WHILE both Person_Slots hold different persons, THE Person_Comparison_Window SHALL show the button "Fortsätt till sammanslagning" as enabled.
3. WHILE a Person_Slot is empty or both Person_Slots hold the same person, THE Person_Comparison_Window SHALL show the button "Fortsätt till sammanslagning" as disabled.
4. WHEN the user chooses "Fortsätt till sammanslagning", THE application SHALL start the Merge_Review as a separate process and SHALL NOT change any data in the Project or the translation files and SHALL NOT set the dirty flag.
5. THE application SHALL NOT start a Person_Merge from a Candidate_Assessment, including `confirmed`.
6. THE application SHALL allow a Person_Merge for a pair that has no Merge_Candidate.
7. WHEN the Merge_Review opens, THE Merge_Review SHALL show neither person as "Person som behålls" or "Person som tas bort", and SHALL require the user to select one person as "Person som behålls", whereupon the other is "Person som tas bort".
8. THE application SHALL NOT determine the Surviving_Person from completeness, birth date, import order, slot position, Focal_Person, id order or any other computed criterion.
9. THE Merge_Review SHALL show the id, name and life years of both persons next to the choice. IF a person has no name or no birth or death year, THEN THE Merge_Review SHALL show an explicit placeholder for the missing value.
10. WHEN the user has selected a Surviving_Person, THE Merge_Review SHALL keep the next section closed until the user performs a separate explicit confirmation action for the choice.
11. WHEN the user cancels at any stage of the Merge_Review, THE application SHALL close the Merge_Review within 1 second and SHALL leave the Project, the translation files and the dirty flag identical to their state before the Merge_Review started.
12. WHEN the user changes the Surviving_Person choice after later sections have been filled in, THE Merge_Review SHALL discard every decision that depended on the previous choice, SHALL keep decisions that did not depend on it, and SHALL show a message listing each decision that was reset.

### Requirement 21: Merge Review of Person Data, Names, Events and Residences

**User Story:** As a genealogist, I want to see and decide how each part of the two records is combined, so that nothing I know is overwritten or lost.

#### Acceptance Criteria

1. WHEN the Merge_Review is opened, THE Merge_Review SHALL present, for each category (person attributes, names, events, residences), every item with exactly one disposition label from: preserved, combined, reassigned, left separate, flagged, or excluded by explicit user choice.
2. WHEN only one person holds a value for a person attribute (sex, title, occupation, notes, profile photo), THE Merge_Plan SHALL keep that value.
3. WHEN both persons hold equal values for a person attribute, THE Merge_Plan SHALL keep exactly one copy of that value.
4. WHEN both persons hold differing single-valued values for a person attribute (sex, title, occupation, profile photo), THE Merge_Review SHALL require an explicit user choice for each such field before the Merge_Plan can be executed.
5. IF one person's value for an attribute is non-empty and the other's is empty, THEN THE Merge_Plan SHALL keep the non-empty value and SHALL NOT overwrite it with the empty value.
6. WHEN both persons have non-empty notes, THE Merge_Review SHALL offer the options keep Surviving_Person notes, keep other person's notes, or concatenate both with a visible separator line, and SHALL preselect concatenation so that no note text is lost.
7. IF the two persons have different `sex` values (M, F) and the user has not chosen one, THEN THE Merge_Plan SHALL report a Blocking_Conflict and SHALL NOT execute the merge.
8. WHEN the Merge_Review is opened, THE Merge_Review SHALL list all names of both persons, and THE Merge_Plan SHALL keep every distinct name as an alternative name with its `type` and `event_id`.
9. THE Merge_Review SHALL require the user to choose exactly one preferred primary name from the listed names before the Merge_Plan can be executed.
10. IF two name entries have identical name strings but a different `type` or `event_id`, THEN THE Merge_Plan SHALL keep both entries; IF they have identical strings, `type` and `event_id`, THEN THE Merge_Plan SHALL keep one entry.
11. WHEN the Merge_Review is opened, THE Merge_Review SHALL list events grouped by event, and THE Merge_Plan SHALL keep every distinct event with its date, place, source references, media and citation metadata, with zero items dropped.
12. WHEN an event lists both persons as participants or lists one person twice, THE Merge_Plan SHALL deduplicate the participant reference to a single entry and SHALL keep the role.
13. IF the two participant entries for an event carry different roles, THEN THE Merge_Plan SHALL report a Blocking_Conflict requiring the user to choose one role, and SHALL NOT execute the merge until a role is chosen.
14. WHEN an event of Person 1 and a distinct event of Person 2 satisfy the Similar_Event_Rule, THE Merge_Review SHALL flag the pair as a Merge_Warning, and THE Merge_Plan SHALL keep both events unless the user separately deletes one outside the merge. THE Merge_Review SHALL compare only one event from the events of Person 1 with one event from the events of Person 2, and SHALL NOT warn about similar events that already existed within the records of one person. The Similar_Event_Rule is satisfied only when all of the following hold: (a) both events have the same event type; (b) both events have a date, and the dates are compatible, meaning that they are equal at the precision both dates share (for example year-only 1850 and full date 1850-03-12 are equal at year precision), or both dates are fully specified to day precision and lie within 365 days of each other; (c) the places do not contradict each other, meaning that the pair is not excluded when at least one event has no place or both events have the same place id, and the pair is excluded when both events have a place and the place ids differ. A match on event type alone, on place alone, or on event type and place without compatible dates SHALL NOT produce a warning, and an event without a date on either side SHALL NOT produce a warning. Examples: two Births in the same parish with no date or with different years produce no warning; two Births with equal full dates and the same or no place produce a warning; two Births with equal full dates in different places produce no warning; two Marriages 10 years apart in the same place produce no warning; two Marriages 100 days apart with no place on either side produce a warning.
15. THE Merge_Review SHALL NOT require a separate event merge, THE Merge_Plan SHALL NOT combine two distinct event ids, and THE Merge_Plan SHALL preserve both events of a flagged pair as separate event records.
16. WHEN the merge is planned, THE Merge_Plan SHALL keep every `ResidenceFact` of both persons with its observations and citations, SHALL reassign `person_id` to the Surviving_Person, and SHALL NOT collapse residences that share a date or place.
17. IF any required user choice (primary name, differing single-valued attribute, sex, participant role) is unresolved, THEN THE Merge_Review SHALL disable merge execution and SHALL indicate each unresolved item, leaving both person records unchanged.

### Requirement 22: Merge Review of Sources, Media, DNA, Research and Other References

**User Story:** As a genealogist, I want citations, photos, DNA kits and research to follow the surviving person intact, so that merging two records never costs me evidence.

#### Acceptance Criteria

1. THE Merge_Plan SHALL preserve every `SourceRef` attached to a moved or kept value, including `quality`, `note` and `aspects`, so that the count of `SourceRef` entries after the merge equals the count before the merge, with each field value unchanged.
2. THE Merge_Plan SHALL rewrite every media person link (`MediaItem.linked_entities`, `mentioned_person_ids`, person `annotations`) that references the Merged_Away_Person to reference the Surviving_Person.
3. WHEN a media item holds more than one link to the Surviving_Person after rewriting, THE Merge_Plan SHALL keep exactly one link and SHALL set its `role` to the first non-empty `role` among the duplicate links, in their original order, or leave it empty if all are empty.
4. WHEN both persons have a `profile_media_id` with different values, THE Merge_Review SHALL require the user to choose one before the merge can be confirmed, and THE Merge_Plan SHALL keep the media item not chosen linked to the Surviving_Person.
5. IF the user has not chosen a `profile_media_id` when both persons have different values, THEN THE Merge_Review SHALL disable the merge confirmation action and SHALL indicate which choice is missing.
6. THE Merge_Review SHALL list every `DnaProfile`, `DnaMatch`, `DnaSegment`, `DnaCluster` and `DnaTriangulation` that references either person through a profile, showing the count per entity type, and THE Merge_Plan SHALL reassign `DnaProfile.person_id`, `admin_person_id` and `DnaCluster.person_ids` entries that equal the Merged_Away_Person id to the Surviving_Person id.
7. THE Merge_Plan SHALL keep each `DnaProfile` as a separate profile, and SHALL NOT combine, delete or alter the contents of any kit, test, match or segment, so that the counts of `DnaProfile`, `DnaMatch` and `DnaSegment` entries are equal before and after the merge.
8. WHEN the Surviving_Person would own two or more `DnaProfile` entries with the same company, test type and kit id, THE Merge_Review SHALL flag each such group as a Merge_Warning, and THE Merge_Plan SHALL keep all of them.
9. WHEN `DnaCluster.person_ids` would list the Surviving_Person more than once, THE Merge_Plan SHALL keep exactly one entry and SHALL preserve the order of the remaining entries.
10. THE Merge_Plan SHALL call the Research_Rewire_Helper for entity type `person` with the Merged_Away_Person id and the Surviving_Person id, and SHALL preserve all research cases, hypotheses, comments, actions, source references and conclusions, so that the count of each is equal before and after the merge.
11. THE Merge_Preview SHALL show the number of research links rewired and the number of research links collapsed as separate integer counts.
12. IF the Research_Rewire_Helper reports an error, THEN THE Merge_Plan SHALL abort the merge, SHALL leave all persons and research data unchanged, and THE Merge_Review SHALL show an error message indicating the research rewiring failed.
13. THE Merge_Plan SHALL rewrite `ResearchNote.linked_entities` entries of type `person` that reference the Merged_Away_Person to reference the Surviving_Person, and SHALL remove duplicate entries so that each person link appears at most once per note.
14. IF `ProjectMetadata.main_person_id` equals the Merged_Away_Person id, THEN THE Merge_Plan SHALL set it to the Surviving_Person id and THE Merge_Preview SHALL list that change.
15. WHEN both persons have a `connection_overrides` entry with different values, THE Merge_Review SHALL require the user to choose one value before the merge can be confirmed.
16. WHEN only the Merged_Away_Person has a `connection_overrides` entry, THE Merge_Plan SHALL move it to the Surviving_Person.
17. THE Merge_Review SHALL show, for every location in the Person_Reference_Inventory not covered by another requirement, the count of references affected and the Reference_Rule that applies.

### Requirement 23: Family Relationship Review

**User Story:** As a genealogist, I want a dedicated review of parents, partners and children before two persons are merged, so that legitimate adoption, foster and step relationships survive and impossible structures are caught.

#### Acceptance Criteria

1. WHEN the Merge_Review is generated for two persons, THE Merge_Review SHALL include a family relationship section that lists, for both persons, every parent and parent-child link type, partner, child, family and its membership, marriage and family event, adoption and foster relation, step, legal and donor relation, and every other relationship structure supported by the model, and SHALL show an explicit empty indication for each category that has no entries.
2. WHEN a family, parent-child link or event references both persons through the same relative id, THE Merge_Plan SHALL treat the relative as one individual and SHALL keep exactly one equivalent link, preserving all link metadata, family events and citations from both original links.
3. WHEN two parent-child links become equivalent after rewiring (same child, same parent, same `parentage_type`), THE Merge_Plan SHALL keep exactly one link and SHALL keep the metadata and citations of both original links.
4. WHEN two parent-child links connect the same child and parent with different `parentage_type` values, THE Merge_Plan SHALL keep both links as distinct historical assertions and SHALL report one Merge_Warning for each such child-parent pair, identifying the child, the parent and both `parentage_type` values.
5. IF a child has several parental relationships of different types (biological, adoptive, foster, step, legal, donor), THEN THE Merge_Plan SHALL NOT report a Blocking_Conflict on the basis of that multiplicity alone.
6. IF the merge would make a person their own parent, their own child, their own partner in one family, or their own ancestor through parent-child links at any generational depth, including cycles through intermediate generations, THEN THE Merge_Plan SHALL report a Blocking_Conflict that names the person and the cycle or relationship that results, and SHALL leave the stored data unchanged.
7. IF the two persons are partners of the same family, parent and child of each other, or members of one family in a way that becomes a self-relationship, THEN THE Merge_Plan SHALL report a Blocking_Conflict that names the family and the relationship.
8. IF rewiring would leave a family with partners or children that cannot be represented without losing information, THEN THE Merge_Plan SHALL report a Blocking_Conflict that names the family and the information at risk, and SHALL NOT drop that information.
9. WHEN two families would have the same partner set after rewiring, THE Merge_Review SHALL present the pair as a potential duplicate family in a Merge_Warning, naming both families and their partners, and THE Merge_Plan SHALL keep them as separate families with all their children, links, events and citations unchanged.
10. THE Merge_Review SHALL NOT offer an option to combine families, and THE Merge_Plan SHALL NOT combine, delete or reassign the contents of any family on the basis of equal partner sets; combining families is out of scope for version 1 and the user can handle it separately after the Person_Merge, and a Merge_Warning about potential duplicate families SHALL NOT block the Person_Merge.
11. WHEN the model can preserve conflicting historical assertions, THE Merge_Plan SHALL preserve them and report a Merge_Warning instead of a Blocking_Conflict.
12. WHEN the Merge_Plan is built, THE Merge_Plan SHALL apply the plan to a working copy, SHALL run the same reconciliation as `sync_parentage_links` on that working copy to produce the Synchronized_Working_Copy before any family, link, warning or conflict is computed for the Merge_Preview, and IF the reconciliation would remove or alter a link that the plan retains, THEN THE Merge_Plan SHALL report a Blocking_Conflict that identifies the affected link. The families, links and warnings of criteria 3 to 11 and 13 SHALL be computed on the Synchronized_Working_Copy.
13. WHEN the Merge_Plan is built, THE Merge_Plan SHALL run the existing family validation (`validate_family`) on every changed family of the Synchronized_Working_Copy and SHALL report each failure as a separate Blocking_Conflict that names the family and the failed validation.

### Requirement 24: Relatives with Different Ids Stay Separate

**User Story:** As a genealogist, I want merging two mothers never to fuse their children by accident, so that two infants named Kalle remain two infants.

#### Acceptance Criteria

1. THE Merge_Plan SHALL keep every relative with a different person id as a separate person, regardless of equal names, dates, places, roles or identical-looking citations.
2. THE Merge_Plan SHALL NOT merge, link, pair or deduplicate two different relative ids, and SHALL NOT propose doing so as part of the same Person_Merge.
3. WHEN the Surviving_Person ends up with children from both records, THE Merge_Plan SHALL list all of them as children of the Surviving_Person, preserving each child's own parent-child links and `parentage_type`, with no child id appearing more than once in the list.
4. GIVEN two persons "Brita" where Person 1 has children Pelle, Kalle (1829–1831) and Olle (1834), and Person 2 has children Stina, Fia, Kalle (1832) and Olle (1834), WHEN the two Britas are merged, THEN the Surviving_Person SHALL have seven distinct children (all seven child ids), the two Kalle records and the two Olle records SHALL remain separate persons, and no relationship SHALL be lost.
5. WHEN the Merge_Review is displayed and two or more relatives of the two persons, with different person ids, share the same name (compared case-insensitively), THE Merge_Review SHALL display the note "Flera släktingar har samma namn; de förblir separata personer om du inte slår samman dem särskilt." once per Merge_Review, and SHALL NOT display the note when no relatives share a name.
6. WHEN the user wants to merge two relatives, THE application SHALL require a separate Person_Merge for that pair through the same Merge_Review, and SHALL NOT offer a merge action for relatives within the Merge_Review of the original pair.
7. IF the Surviving_Person would end up with the same relative id linked through both records with conflicting `parentage_type` values, THEN THE Merge_Plan SHALL list the conflict for user resolution in the Merge_Review and SHALL NOT silently drop either link.
8. THE Merge_Plan, THE Merge_Review and THE Merge_Preview SHALL NOT automatically identify, pair, flag as duplicate, propose as Merge_Candidate or merge any of the child records, or any other relative records, on the basis of names, dates, places or any other attribute; the note of criterion 5 is informational only and SHALL NOT pair the relatives or mark them as candidates.

### Requirement 25: Order Independence of Merges

**User Story:** As a genealogist, I want to merge parents before children or children before parents, so that I can work in the order the evidence arrives.

#### Acceptance Criteria

1. WHEN a user confirms a merge of two persons, THE Merge_Engine SHALL complete the merge even if any of their parents, partners or children remain unmerged separate persons, and SHALL leave those related persons in the Project as distinct persons.
2. WHEN a user confirms a merge of two persons who are parents of different children, THE Merge_Engine SHALL complete the merge without requiring or triggering a merge of any of those children, and SHALL attach every child of both parents to the surviving person.
3. WHEN a user confirms a merge of two persons who are children of different parents, THE Merge_Engine SHALL complete the merge without requiring or triggering a merge of any of those parents, and SHALL link the surviving person to the parents of both merged persons.
4. FOR ALL pairs of independent merges (A into B, C into D) whose affected persons do not overlap, applying them in either order SHALL produce an equivalent final Project (confluence property), where equivalent means the same set of persons, the same field values on each person, and the same set of relationships, ignoring internal identifiers and the order of entries.
5. IF the Merge_Plan of a second merge classifies the situation as a Blocking_Conflict that did not exist before the first merge was applied, THEN THE Merge_Engine SHALL report that conflict at the time the second merge is planned, SHALL refuse to apply the second merge, and SHALL leave the Project unchanged by the second merge while keeping the result of the first merge.
6. WHEN the first merge made two families equivalent, THE second merge's Merge_Review SHALL display them under Requirement 23 criterion 9.

### Requirement 26: Merge Preview and Confirmation

**User Story:** As a genealogist, I want a complete preview of everything the merge will change before I confirm, so that the final click is an informed one.

#### Acceptance Criteria

1. WHEN the user completes the last section of the Merge_Review, THE Merge_Review SHALL display the Merge_Preview titled "Förhandsgranskning av sammanslagning" as the final step.
2. THE Merge_Preview SHALL present the outcome as the Synchronized_Working_Copy of Requirement 23 criterion 12, so that the family relationships, links, derived foster and adoptive families, Merge_Warnings (including potential duplicate families of Requirement 23 criterion 9) and Blocking_Conflicts it shows are those that remain after the equivalent of `sync_parentage_links` has run, and THE Merge_Preview SHALL show the Surviving_Person with id, the Merged_Away_Person with id, the chosen primary attributes and name, the events and residences affected, the family relationships affected, the sources and media affected, the DNA references affected, the research references affected, the Merge_Candidates affected, the GEDCOM identity mappings affected, and all warnings and unresolved conflicts.
3. WHEN the user navigates from the Merge_Preview to an earlier section, THE Merge_Review SHALL retain every decision made so far, and the earlier section SHALL display each of those decisions unchanged.
4. WHILE any Blocking_Conflict is unresolved, THE Merge_Preview SHALL disable the "Slå samman personer" button and SHALL list each unresolved Blocking_Conflict together with the name of the section where it can be resolved.
5. THE Merge_Preview SHALL render Merge_Warnings with a visual style distinct from Blocking_Conflicts, using both a different text label and a different icon or style, so the two are distinguishable without relying on color alone.
6. WHEN the user activates the enabled button "Slå samman personer" and the Saved_State_Precondition of criteria 11 and 12 is met, THE Merge_Preview SHALL display a second confirmation naming both the Surviving_Person and the Merged_Away_Person with their ids, SHALL NOT state that unsaved edits will be saved with the merge, and SHALL execute the merge only after the user explicitly confirms there.
7. WHEN the user cancels or dismisses the second confirmation, THE Merge_Review SHALL return to the Merge_Preview, SHALL leave the Project unchanged, and SHALL retain all decisions made.
8. THE Merge_Preview SHALL be built from the Merge_Plan without mutating `ProjectData`, translation files or settings; the synchronization of derived relationships SHALL be run on the planned working copy only.
9. WHEN the Project changes while the Merge_Review is open, THE Merge_Review SHALL rebuild the Merge_Plan within 2 seconds, SHALL show a notice that the Project changed, and SHALL disable execution until the user re-confirms the rebuilt Merge_Preview.
10. IF the Merge_Plan cannot be built or rebuilt, THEN THE Merge_Review SHALL show an error message indicating that the preview is unavailable, SHALL disable the "Slå samman personer" button, and SHALL leave the Project unchanged.
11. WHEN the user activates the enabled button "Slå samman personer" WHILE the Project dirty flag is true, THE Merge_Review SHALL, before the second confirmation, offer exactly two choices, "Spara och fortsätt" and "Avbryt", and SHALL offer no other choice.
12. WHEN the user chooses "Spara och fortsätt", THE Project_Service SHALL save the Project; WHEN the save succeeds, THE Merge_Review SHALL continue to the second confirmation of criterion 6 without rebuilding the Merge_Plan, because the saved content equals the content on which the Merge_Plan was built; IF the save fails, THEN THE Merge_Review SHALL show a Swedish error message stating that the save failed and that nothing was merged, SHALL NOT start the merge, SHALL leave all Project data and translation files as they were before the attempt, and SHALL keep the Merge_Review open.
13. WHEN the user chooses "Avbryt" in the choice of criterion 11, THE Merge_Review SHALL return to the Merge_Preview, SHALL NOT save the Project, SHALL NOT start the merge, and SHALL retain all decisions made.
14. IF any open editor or dialog (including the Person_Editor and other editors that can modify the Project) holds unsaved changes WHEN the user activates the enabled button "Slå samman personer", THEN THE application SHALL NOT start the merge and SHALL NOT show the choice of criterion 11; THE application SHALL inform the user in Swedish which editor holds unsaved changes and SHALL block the merge until the user has explicitly saved or explicitly discarded those changes in that editor; THE application SHALL NOT save or discard editor content automatically, and SHALL NOT commit unsaved editor content as part of the merge.
15. THE Merge_Preview SHALL show the GEDCOM update warning of Requirement 30 criterion 13 before the second confirmation of criterion 6.
### Requirement 27: Atomic Execution and Recovery

**User Story:** As a genealogist, I want a merge to either complete fully or leave my data exactly as it was, so that a crash or a bug cannot leave a half-merged project.

#### Acceptance Criteria

1. WHEN the user confirms, THE Merge_Engine SHALL execute in this order: validate the Merge_Plan against current data; create a Recovery_Point; apply the plan as one logical operation; validate the resulting state; commit; after a successful commit clear the dirty flag, increment the Revision_Counter and notify change listeners; refresh views and indexes. A completed merge SHALL NOT leave the Project marked as modified, because the commit has written the result to disk and the disk state equals the in-memory state.
2. THE Recovery_Point SHALL capture the in-memory `ProjectData` changes the plan will make and the contents of `translation/persons.json`, so that restoring it yields data equal in every field to the data before step 2 of criterion 1.
3. THE Merge_Engine SHALL apply the plan to a working copy of the affected data and SHALL swap the result into `ProjectData` and Translation_Data only after post-merge validation passes.
4. THE post-merge validation SHALL verify that the Merged_Away_Person is absent from `ProjectData.persons`, that no reference to the Retired_Person_ID remains in a `rewire` location, that every family passes `validate_family`, that no parent-child cycle exists, that no Merge_Candidate refers to the Retired_Person_ID in an active position, and that no information-bearing record from the plan was dropped.
5. IF any step before the commit protocol of criterion 14 begins fails, THEN THE Merge_Engine SHALL restore the previous state of `ProjectData`, Translation_Data and the dirty flag, SHALL report the failure in Swedish with a message indicating which step failed and that no data was changed, and SHALL leave the project file, `translation/persons.json` and every other translation file unchanged on disk. IF a step of the commit protocol fails with an error, THEN THE Merge_Engine SHALL apply criterion 17.
6. THE Merge_Engine SHALL NOT write an intermediate state of the Merge_Transaction to the final target files, and SHALL NOT be implemented as a sequence of independent saves performed by editors; temporary files and the Merge_Journal of criterion 14 are not intermediate states of the targets.
7. WHEN a Person_Merge is committed, THE Project_Service SHALL write the project file with the existing save conventions of `FilePersistence.save` (compressed JSON, same encoding, same target path) and the translation files together as one Merge_Transaction under criterion 14.
8. IF the translation file write fails, or the project file write fails, during the commit of a Merge_Transaction, THEN THE Project_Service SHALL apply criterion 17, SHALL report the failure in Swedish, and SHALL keep the in-memory state equal to the state before the merge, with the dirty flag false and the Revision_Counter unchanged.
9. THE Merge_Engine SHALL follow the existing file-save, media storage and backup conventions and SHALL NOT delete or move media files as part of a merge.
10. WHILE the Merge_Engine has not begun step 2 of criterion 1, THE Merge_Review SHALL remain cancelable, and a cancel SHALL leave `ProjectData`, Translation_Data and the dirty flag unchanged.
11. WHILE the Merge_Engine is executing step 2 of criterion 1 or any later step, THE application SHALL show a progress state and SHALL NOT offer cancel.
12. WHEN the merge completes, THE application SHALL refresh the Person_List, diagrams, Person_Editor, Candidate_Register and research views, and SHALL remove the Merged_Away_Person from every list.
13. WHILE the Merge_Engine applies a plan, THE application SHALL prevent every editor from modifying the Project, either by running the Merge_Engine as a single UI-thread operation or by holding a project lock.
14. THE Merge_Engine SHALL commit a Merge_Transaction with a commit protocol that has these ordered steps, where the design chooses the exact mechanism: (a) write the new project file and each new or changed translation file to temporary files in the same directory as their targets; (b) write the Merge_Journal durably, listing the intended target files, the temporary files and the expected content checksum of each; (c) flush the temporary files and the Merge_Journal to stable storage (fsync or equivalent); (d) replace each target with its temporary file using an atomic replace operation; (e) remove the Merge_Journal; (f) remove the Recovery_Point backup of criterion 15.
15. WHEN the Merge_Engine creates the Recovery_Point, THE Merge_Engine SHALL create, before step (a) of criterion 14, a pre-merge backup on disk of the project file and of every translation file the merge changes as the on-disk part of the Recovery_Point, taken from the saved state under the Saved_State_Precondition, SHALL record the content checksum of each backed-up file, and SHALL keep that backup until step (e) of criterion 14 has completed.
16. WHEN a project is opened, THE application SHALL check for a Merge_Journal beside the project file BEFORE loading any data; IF a Merge_Journal exists, THEN THE application SHALL classify every target file by the SHA-256 content checksum of its content, and SHALL decide deterministically as follows, after first applying criterion 25 (a target matching neither state, or a corrupt journal or backup, refuses recovery before any of (a) to (f) is applied): (a) a target whose content equals the exact expected NEW checksum counts as already replaced; (b) a target whose content equals the expected OLD state (the expected old checksum, or absent where it did not exist before the merge) counts as not yet replaced; (c) IF all targets are in the NEW state, THEN THE application SHALL treat the merge as completed; (d) IF every target is in the NEW state, or is in the OLD state with its temporary file present and equal to the expected NEW checksum, THEN THE application SHALL roll forward by completing the remaining replace operations; (e) OTHERWISE, IF every target is in the OLD or NEW state and the pre-merge backup is verifiable against the recorded old checksums, THEN THE application SHALL roll back by restoring every target not in the OLD state from the pre-merge backup; (f) IF a target is not in the OLD state and the backup needed to restore it is not verifiable, THEN recovery is refused under criterion 25. THE application SHALL, after a roll forward or roll back, remove the temporary files, the backup and finally the Merge_Journal, and SHALL report the outcome ("sammanslagningen slutfördes" or "sammanslagningen återställdes") to the user in Swedish. The decision table in the design document SHALL specify every combination of target state, temporary file state and backup state.
17. IF an error occurs during the commit protocol, THEN THE Merge_Engine SHALL apply the same deterministic decision as criterion 16 without requiring an application restart, so that the observable result is identical to the result of a crash at the same point.
18. FOR ALL points at which the application may stop between or during the steps of criterion 14 (crash, power loss or exception) and for which recovery is not refused under criterion 25, on reopening the Project EITHER the entire Merge_Transaction SHALL be applied to the project file and to every translation file OR none of it SHALL be applied, so that the project file and `translation/persons.json` are always consistent with each other, no Retired_Person_ID has a missing or orphaned PersonMapping or Identity_Alias, and no Merge_History_Entry exists whose mapping update is absent.
19. THE automated test suite SHALL include fault-injection tests that simulate a crash (process stop without cleanup) and an exception immediately before and after each step (a) to (f) of criterion 14, including between the replace of the project file and the replace of `translation/persons.json`, and SHALL assert criterion 18 after reopening, that the user message of criterion 16 is shown, and that no Merge_Journal or temporary file remains after recovery. THE fault-injection tests SHALL additionally cover the Recovery_Refusal of criterion 25 for each of these cases: the project file matches neither the expected old nor the expected new content; `translation/persons.json` matches neither; a combination in which one target is new and the other matches neither; a corrupt Merge_Journal; a corrupt or missing backup that is needed for a roll back. For each case the tests SHALL assert that the Merge_Journal, temporary files and backup remain byte-for-byte untouched, that every target file is unchanged by recovery, that the project is not opened, and that the Swedish message of criterion 25 is shown.
20. IF the project file, `translation/persons.json` (where it exists) or another translation file the merge changes is read-only, locked or not writable, or the directory does not permit creating temporary files, THEN THE Merge_Engine SHALL refuse the merge before step 2 of criterion 1 with a Swedish message naming the file, SHALL change nothing in memory or on disk, and SHALL keep the Merge_Review open.
21. WHEN recovery under criterion 16 or 17 rolls back, THE application SHALL leave the Project in the state it had before the merge, including the dirty flag state recorded in the Recovery_Point (false, because of the Saved_State_Precondition).
22. IF the Project dirty flag is true WHEN the Merge_Engine is asked to execute, THEN THE Merge_Engine SHALL refuse with the Swedish message "Projektet har osparade ändringar. Spara projektet innan sammanslagningen.", SHALL change nothing in memory or on disk, and SHALL leave the dirty flag unchanged.
23. IF an open editor holds unsaved changes WHEN the Merge_Engine is asked to execute, THEN THE application SHALL refuse the merge as specified in Requirement 26 criterion 14, SHALL change nothing in memory or on disk, and SHALL NOT save, commit or discard the editor content.
24. WHEN a Merge_Transaction commits successfully, THE Project_Service SHALL, in this order, clear the dirty flag, increment the Revision_Counter by exactly one, and notify all change listeners exactly once, so that the Person_List, diagrams, indexes, Person_Editor, Candidate_Register, research views and open Merge_Reviews refresh from the committed state; the committed project file SHALL contain no unsaved edit that existed before the merge.
25. IF automatic recovery finds that a target file matches neither the expected old state nor the expected new state, OR the Merge_Journal fails its own checksum or cannot be parsed and the backup manifest is also unusable, OR the backup needed for a roll back is corrupt or missing, THEN THE application SHALL refuse automatic recovery, SHALL leave the Merge_Journal, all temporary files and the backup untouched and unmodified, SHALL NOT modify, replace or delete any target file, SHALL NOT open the project silently, and SHALL show a Swedish message that states that the merge was interrupted, names the project file, the Merge_Journal, the temporary files and the backup folder with their paths, states that these files are preserved, and tells the user not to delete them and what to do next (restore the backup manually or contact support with the preserved files).

### Requirement 28: Merge History

**User Story:** As a genealogist, I want a permanent record of which record was folded into which, so that I can always find out what happened to an id.

#### Acceptance Criteria

1. WHEN a Person_Merge completes, THE Merge_Engine SHALL add exactly one Merge_History_Entry holding `id`, `surviving_person_id`, `merged_person_id`, `merged_person_name`, `merged_person_lifespan`, `merge_date` (current local date), `merge_candidate_id` (the direct candidate id if one existed, else absent), the archived direct candidate if any, and the identity mapping information of Requirement 30, in the same Merge_Transaction commit as the merge itself, so that the Merge_History_Entry is part of the committed project file and the Project is clean after the merge.
2. WHEN a Person_Merge completes, THE Merged_Away_Person SHALL no longer be an active `Person`, SHALL NOT appear in any person list, search result or diagram, and its id SHALL be a Retired_Person_ID.
3. THE `IDGenerator` SHALL never issue a Retired_Person_ID, including when the Retired_Person_ID carries the highest suffix and the project is saved and reopened.
4. WHILE no relationship of higher priority than a merge exists for the Surviving_Person, THE Surviving_Person SHALL show a grey Candidate_Indicator with the tooltip "Slogs samman med <namn> (<år–år>)", where <namn> and <år–år> are the `merged_person_name` and `merged_person_lifespan` of the Merge_History_Entry.
5. THE Merge_History SHALL allow an unlimited number of entries with the same `surviving_person_id`, and SHALL list them in ascending `merge_date` order, with entries sharing a date ordered by creation sequence.
6. WHEN the Surviving_Person is itself merged into another person later, THE Merge_Engine SHALL update Redirect_Resolution so that every earlier Retired_Person_ID resolves to the final Surviving_Person, and SHALL keep earlier Merge_History_Entries unmodified apart from the redirect target.
7. THE Redirect_Resolution SHALL terminate for any stored Merge_History.
8. IF the stored Merge_History contains a cycle, THEN THE Merge_Consistency_Report SHALL report the ids in the cycle, AND Redirect_Resolution SHALL return no person for the affected ids, AND the stored entries SHALL remain unchanged.
9. WHEN the user opens the grey Candidate_Indicator or the Merge_History section of the Person_Editor for a person, THE application SHALL display a Merge_History view listing every merge into that person, showing for each entry the `merged_person_name`, `merged_person_lifespan`, `merged_person_id` and `merge_date`.
10. IF a person has no Merge_History_Entries, THEN THE Merge_History view SHALL show an empty-state message indicating that no merges exist, and THE grey Candidate_Indicator SHALL NOT be shown.
11. THE Merge_History SHALL survive save and load, restore from the migration backup or the Merge_Transaction backup (Requirement 7 criterion 9), and later merges, with all entry fields identical before and after.
12. IF saving a Person_Merge fails, THEN THE Merge_Engine SHALL add no Merge_History_Entry, SHALL retain the Merged_Away_Person as an active `Person`, and THE application SHALL show an error message indicating that the merge was not saved.

### Requirement 29: Candidates After a Completed Merge

**User Story:** As a genealogist, I want my earlier candidate notes to survive a merge in a sensible, predictable way, so that no comment I wrote is lost and no unreviewed guess becomes a fact.

#### Acceptance Criteria

1. WHEN a merge completes, THE Merge_Engine SHALL archive the direct Merge_Candidate for the merged pair in its Merge_History_Entry with its assessment, `enabled`, `research_case_id` and all comments, and SHALL remove it from the active `merge_candidates` collection.
2. WHEN a merge completes and a Merge_Candidate between the Merged_Away_Person and a third person C exists and no candidate for the Unordered_Pair (Surviving_Person, C) exists, THE Merge_Engine SHALL redirect that Redirected_Candidate to (Surviving_Person, C), keeping its `id`, `enabled`, `research_case_id`, assessment (except as criterion 3 specifies) and all comments, in their original order and with their original dates. This applies equally to the situation A↔B merged with A surviving, B↔C existing and no A↔C existing.
3. THE only change of Candidate_Assessment that a redirect makes SHALL be this: WHEN a Redirected_Candidate had assessment `confirmed`, THE Merge_Engine SHALL set it to `possible`; WHEN it had assessment `unreviewed`, `possible` or `rejected`, THE Merge_Engine SHALL keep that assessment unchanged. THE Merge_Engine SHALL keep the `enabled` value of a Redirected_Candidate unchanged.
4. WHEN the Merge_Engine redirects a Merge_Candidate, THE Merge_Engine SHALL append exactly one comment dated with the merge date, after the original comments, recording the redirect and the original assessment, in Swedish, for example "Omdirigerad vid sammanslagning av <id> in i <id>. Ursprunglig bedömning: <bedömning>."
5. THE Merge_Engine SHALL NOT infer from a redirect that the Surviving_Person and C are confirmed duplicates, and SHALL NOT change the assessment of any redirected candidate to `confirmed`.
6. WHEN a merge completes and a Collision exists, THE Merge_Engine SHALL preserve both original assessments and both comment histories as follows, in this deterministic order of operations: (a) take the original assessment of the Redirected_Candidate and the original assessment of the existing candidate; (b) apply the `confirmed` to `possible` rule of criterion 3 to the redirected side only, giving its effective assessment; (c) compare the effective redirected assessment with the existing assessment, which is not downgraded; (d) resolve `enabled` and `research_case_id` under criterion 10; (e) set the resulting assessment under criterion 13; (f) build the comment list as the existing comments in their stored order, followed by all comments of the Redirected_Candidate with their original dates and in their original order, followed by the redirect comment of criterion 4, followed by the explanatory comment of criterion 13 where one is required; (g) archive the Redirected_Candidate in the Merge_History_Entry with its full original content, including its original assessment, `enabled`, `research_case_id`, id and comments. The existing candidate SHALL keep its `id` and SHALL change only in assessment under criterion 13, `research_case_id` under criterion 10 and appended comments.
7. THE Merge_Engine SHALL NOT delete any Merge_Candidate other than by archiving it in Merge_History, and every candidate removed from the active `merge_candidates` collection SHALL be present in the Merge_History_Entry of that merge.
8. IF a redirect would produce a Merge_Candidate whose two person ids are equal, THEN THE Merge_Engine SHALL archive the candidate in Merge_History with its full original content instead of redirecting it, and SHALL NOT add it to the active `merge_candidates` collection.
9. WHEN a merge completes, THE Merge_Engine SHALL apply criteria 2 to 8 and 13 to disabled and rejected candidates as well, so that a `rejected` Redirected_Candidate remains `rejected`, a disabled Redirected_Candidate remains disabled (`enabled` false), and a disabled Redirected_Candidate with assessment `confirmed` becomes disabled with assessment `possible`; a combination of `rejected` and `confirmed` cannot occur because a Merge_Candidate holds a single assessment.
10. IF the existing candidate and the Redirected_Candidate differ in `enabled`, THEN THE Merge_Engine SHALL keep the `enabled` value of the existing candidate and SHALL record both `enabled` values in the explanatory comment of criterion 13 and in the archive; IF they differ in `research_case_id`, THEN THE Merge_Engine SHALL keep the existing `research_case_id` unless it is empty, in which case the Merge_Engine SHALL adopt the `research_case_id` of the Redirected_Candidate, and SHALL record the value that was not kept in the explanatory comment and in the archive.
11. IF the merge fails or is rolled back before completion, THEN THE Merge_Engine SHALL leave every Merge_Candidate in the active `merge_candidates` collection unchanged, with no archived, redirected or appended content.
12. WHEN a merge completes, THE Merge_Engine SHALL ensure that no active Merge_Candidate references the Merged_Away_Person.
13. WHEN the effective redirected assessment and the existing assessment of a Collision are equal, THE Merge_Engine SHALL keep that assessment; WHEN they differ, THE Merge_Engine SHALL set the assessment of the surviving candidate to `unreviewed` and SHALL append one explanatory comment dated with the merge date, in Swedish, naming both original assessments and both candidate ids, for example "Sammanslagning av <id> in i <id>: bedömningarna <bedömning A> (<kandidat-id A>) och <bedömning B> (<kandidat-id B>) stämde inte överens. Bedömningen återställd till Ej granskad." WHEN `enabled` or `research_case_id` differ, THE Merge_Engine SHALL include the differing values of both candidates in an explanatory comment, appended as the same single comment when one is already required.
14. THE Merge_Engine SHALL NOT silently retain one assessment as authoritative when the assessments of a Collision conflict, and SHALL always leave a trace of both original assessments in the surviving candidate's comments and in the archive.
15. THE Merge_Engine SHALL give the same result for the same input of a Collision regardless of the order in which candidates are stored in `merge_candidates`, and SHALL be testable by example tests for each combination of the two assessments (16 combinations), each `enabled` combination and each `research_case_id` combination, and by a property test that the comment list always equals existing comments, then redirected comments, then redirect and explanatory comments.

### Requirement 30: GEDCOM Identity Preservation

**User Story:** As a genealogist who re-imports from a GEDCOM file, I want a merged duplicate never to reappear, so that my cleanup is not undone by the next import.

#### Acceptance Criteria

1. WHEN a Person_Merge completes, THE Merge_Engine SHALL redirect every `PersonMapping` whose `app_id` equals the Retired_Person_ID to the Surviving_Person, either by changing `app_id` or by keeping the entry as an Identity_Alias, as the design chooses, and SHALL keep the `gedcom_id` and `fingerprint` of each mapping unchanged.
2. THE Translation_Data persisted format SHALL represent Identity_Alias entries so that reading and then writing `translation/persons.json` produces content equal to the original, including all Identity_Alias entries (round-trip property).
3. WHEN `translation/persons.json` written before this feature (containing no Identity_Alias entries) is loaded, THE Translation_Data loader SHALL load all existing mappings with unchanged values and SHALL NOT report an error.
4. WHEN a later import contains a record whose xref or fingerprint matches a mapping redirected to the Surviving_Person, THE GEDCOM_Importer SHALL treat the record as a match to the Surviving_Person, SHALL NOT create a `Person` with the Retired_Person_ID, and SHALL NOT create any new person for that record.
5. WHEN a matched record carries values that differ from the Surviving_Person's merged data, THE GEDCOM_Importer SHALL leave every field of the Surviving_Person unchanged and SHALL list the record in the import result as a match to a merged identity, identifying the Surviving_Person and each differing field, for user review.
6. WHEN the same GEDCOM file is imported a second or later time after a merge, THE GEDCOM_Importer SHALL NOT repeat the merge, SHALL leave the count of events and families unchanged compared with the state before that import, and SHALL NOT recreate the Merged_Away_Person.
7. IF a GEDCOM record could resolve to more than one active person through the redirected mappings, THEN THE GEDCOM_Importer SHALL flag the record in the import result for user review, SHALL NOT assign the record to any person, and SHALL leave all persons unchanged by that record.
8. WHEN an import runs, THE GEDCOM_Importer SHALL leave all research references, Merge_Candidates and Merge_History entries unchanged in content and count.
9. THE Merge_Engine SHALL write the update of `translation/persons.json` and of any other translation file the merge changes as part of the Merge_Transaction of Requirement 27, so that after a failed or interrupted Person_Merge the content of each of those files equals its content before the merge, and after a completed Person_Merge the project file and those files are consistent with each other (Requirement 27 criterion 18); where recovery is refused under Requirement 27 criterion 25, this criterion does not apply and all files and recovery artifacts are preserved as found.
10. WHEN a Person_Merge merges the Surviving_Person of an earlier merge into a third person, THE Merge_Engine SHALL redirect every Identity_Alias created by earlier merges to the final Surviving_Person, so that no mapping or alias refers to a retired person ID.
11. THE test suite SHALL contain regression tests that import a GEDCOM file, merge two imported persons, re-import the same file and an edited variant, and assert that the retired person is not recreated, that the person count is unchanged by the re-imports, and that the event count is unchanged by the re-imports.
12. WHEN a GEDCOM export runs, THE GEDCOM_Exporter SHALL export every active person and SHALL NOT export the Merged_Away_Person.
13. WHEN the Merge_Preview is shown, THE Merge_Preview SHALL display a Swedish warning that a later GEDCOM update import may overwrite the names, notes, title and occupation of the Surviving_Person, and that the user should review such an import carefully. The warning exists as a temporary limitation, only until the non-destructive GEDCOM update handling of criterion 14 exists.
14. BEFORE Släktbusken version 1.0 is released, THE GEDCOM_Importer SHALL handle an update import non-destructively: an update import SHALL NOT silently overwrite user-edited or merged data of an active person, and SHALL present each difference for user review before any change is applied. This is a MANDATORY requirement for release 1.0 and is not an optional long-term enhancement.
15. THE implementation of the person-comparison-and-merge feature SHALL NOT be required to implement the non-destructive update handling of criterion 14, and the feature SHALL be considered complete without it; WHEN the handling of criterion 14 is implemented, THE Merge_Preview warning of criterion 13 SHALL be removed.

### Requirement 31: Merge Consistency Reporting

**User Story:** As a genealogist, I want a report that points out broken or notable merge data, so that I can trust the register and the history.

#### Acceptance Criteria

1. THE application SHALL provide the Merge_Consistency_Report "Sammanslagning och dubletter" as one entry in the report menu, placed directly after "Forskningskonsistens", producing a `ReportContent` through a `check_*` and `generate_*` pair following `research_consistency.py`.
2. WHEN the user opens the Merge_Consistency_Report, THE Merge_Consistency_Report SHALL list under "Fel" every one of the following findings, with one entry per affected item: a Merge_Candidate referring to a missing person; a Merge_Candidate whose two person ids are equal; duplicate Unordered_Pairs; an invalid assessment; a comment with a missing id or a malformed date; a Merge_History_Entry whose surviving person is missing or retired without a redirect; an invalid Retired_Person_ID mapping; a Redirect_Resolution cycle; a research reference, family reference or other `rewire` reference that still points to a Retired_Person_ID; a Merge_Candidate whose `research_case_id` does not resolve; and invalid relationship structures such as a parent-child cycle or a family that fails `validate_family`.
3. WHEN the user opens the Merge_Consistency_Report, THE Merge_Consistency_Report SHALL list under "Informationspunkter" every confirmed duplicate not yet merged, every disabled candidate, every rejected candidate, and every completed Merge_History entry, with one entry per item.
4. THE Merge_Consistency_Report SHALL list each finding as a Swedish message that contains the display name and the id of each affected candidate or person.
5. IF a finding refers to a person that does not exist, THEN THE Merge_Consistency_Report SHALL list that finding using the referenced id and a Swedish placeholder in place of the display name, and SHALL still produce the report.
6. THE Merge_Consistency_Report SHALL NOT delete or modify any Merge_Candidate or Merge_History entry, and the stored data SHALL be identical before and after the report is generated.
7. WHEN there are no Merge_Candidates and no Merge_History entries, THE Merge_Consistency_Report SHALL show the text "Det finns inga sammanslagningskandidater eller sammanslagningar att kontrollera." and SHALL NOT show the section texts of criterion 8.
8. WHEN a section has no findings and at least one Merge_Candidate or Merge_History entry exists, THE Merge_Consistency_Report SHALL show "Inga problem hittades." for that section.
9. IF the check or generation of the Merge_Consistency_Report fails with an unexpected error, THEN THE application SHALL show an error message in Swedish indicating that the report could not be generated, SHALL NOT show a partial report, and SHALL leave all stored data unchanged.

### Requirement 32: Regression Safety and Performance

**User Story:** As a genealogist with a large project, I want the new feature to leave existing features working and fast, so that adopting it costs nothing.

#### Acceptance Criteria

1. THE application SHALL keep person editing, family diagrams, parent-child and partner validity, research features, GEDCOM import and export, project load and save, and independent settings behaving as before for projects that contain no Merge_Candidates and no Merge_History, such that every test in the automated test suite that existed before this feature passes without modification and a project saved and reloaded without Merge_Candidates and Merge_History produces output identical to the output before this feature, except for the `version` and `format_version` fields; the compatibility and regression tests SHALL explicitly permit differences in those two fields only (Requirement 7 criterion 14) and SHALL fail on any other difference.
2. WHEN the Person_List is refreshed or a diagram is rendered, THE Candidate_Indicator computation SHALL build the candidate index exactly once for that refresh or render and SHALL perform zero scans of the whole `merge_candidates` collection per row or box.
3. WHILE a Project contains 20,000 persons and 2,000 Merge_Candidates, THE candidate index SHALL build in less than 1 second, where 1 second is the confirmed upper limit; the aim is that a typical build takes less than 0.5 seconds, and the aim is not a pass/fail condition.
4. WHEN a person is assigned to a Person_Slot WHILE a Project contains 20,000 persons and 2,000 Merge_Candidates, THE Person_Comparison_Window SHALL show both Comparison_Family_Views within 2 seconds of the assignment, where 2 seconds is the confirmed upper limit; the aim is that a typical assignment completes in less than 1 second, and the aim is not a pass/fail condition.
5. WHEN the Merge_Engine builds a Merge_Plan WHILE a Project contains 20,000 persons, THE Merge_Engine SHALL resolve every person-reference location through indexed lookups and SHALL perform zero full scans of the person-reference locations per reference.
6. THE automated test suite SHALL include property-based tests for Requirement 7 criterion 4 (round trip), Requirement 5 criterion 5 (Unordered_Pair identity), Requirement 25 criterion 4 (confluence), Requirement 27 criterion 5 (a failing merge leaves the Project equal to its state before the merge), and the invariant that a successful merge never reduces the count of events, residences, source citations, media links, DNA profiles, research links or comments, other than by documented deduplication.
7. THE automated test suite SHALL include the fault-injection tests of Requirement 27 criterion 19 and example-based tests for each scenario listed in the acceptance section of the feature description, including the two-Brita example of Requirement 24, same-named siblings, same-ID relatives in both views, the A↔B / B↔C / A↔C candidate cases, GEDCOM re-import after a merge, and the Collision and redirect cases of Requirement 29. The test groups named in Requirement 35 are mandatory.
8. IF a performance measurement in criterion 3 or 4 exceeds its stated upper limit, THEN THE automated test suite SHALL report a failing test that names the measured duration and the limit, and the Project data SHALL remain unchanged by the measurement.
9. THE benchmark for criteria 3, 4 and 10 SHALL use a Project generated deterministically from a fixed seed with realistic family structures, including multiple generations, persons with multiple partnerships, siblings, a mix of parent-child types (biological, adoptive, foster, step) and shared ancestors, and SHALL be reproducible from the seed.
10. THE benchmark SHALL record the Merge_Plan build time for a Person_Merge in a Project of 20,000 persons as a documented measurement, and the design SHALL decide whether to set a limit for it; this requirement fixes no limit for the Merge_Plan build time.
11. THE design and the test documentation SHALL document the benchmark environment (CPU, RAM, operating system, Python version, Qt/PySide6 version), the number of measurement runs, and how the figures were measured (including whether the figure is a median, mean or maximum and how warm-up runs were treated).

### Requirement 33: Scope Limits of Version 1

**User Story:** As a maintainer, I want the boundaries of this feature stated, so that nobody adds automation that undermines the safety principle.

#### Acceptance Criteria

1. THE application SHALL start a duplicate search, a Comparison_Family_View or a Merge_Review for a pair of persons only as the direct result of an explicit user action, and SHALL NOT start any of them at application start, project open, person save or on a timer.
2. THE application SHALL NOT display any numeric similarity score, percentage, confidence value, ranking or sort order based on likelihood of identity for a pair of persons.
3. WHEN the application matches relatives across the two Comparison_Family_Views, THE application SHALL treat two relatives as the same person only if their person ids are identical, and SHALL NOT match them by name, dates, places or any other attribute.
4. THE application SHALL combine events, DNA kits, parents, partners, children and siblings only as specified in Requirements 21 to 24, and SHALL NOT merge any of them without an explicit user decision for each item in the Merge_Review.
5. THE Merge_Review SHALL accept exactly two persons per Person_Merge.
6. IF a request to merge three or more persons in one Person_Merge is made, THEN THE Merge_Review SHALL reject the request, SHALL display a message indicating that exactly two persons are required, and SHALL leave all person data unchanged.
7. THE application SHALL NOT offer rule-based merging, bulk merging, or any control that merges more than one pair of persons in a single user action.
8. THE application SHALL NOT use text generated by a language model or other text generator to propose, rank or justify identity between persons.
9. THE application SHALL NOT set a Candidate_Assessment automatically, including as a result of matching names or dates, and SHALL set a Candidate_Assessment only when the user explicitly selects a value.
10. THE following is a known limitation of this feature and NOT an optional enhancement: a later GEDCOM update import can overwrite names, notes, title and occupation of the Surviving_Person, and non-destructive GEDCOM update handling (Requirement 30 criterion 14) is mandatory before Släktbusken 1.0. THE feature SHALL NOT implement that handling in this version, and SHALL warn the user as specified in Requirement 30 criterion 13 until it exists.

### Requirement 34: Language and Code Conventions

**User Story:** As a maintainer, I want the feature to follow the project's conventions, so that it fits the codebase.

#### Acceptance Criteria

1. THE implementation SHALL use English for all identifiers, internal keys and developer comments in the new and modified modules of this feature.
2. THE implementation SHALL present every user-visible label, message, menu entry, tooltip, dialog title, error message and report heading of this feature in Swedish.
3. THE new model dataclasses SHALL live in the new module `slaktbusken/model/merge_candidate.py` and SHALL be exposed as fields on `ProjectData`.
4. THE validators for the new model dataclasses SHALL follow `slaktbusken/model/validators.py` by returning a list of Swedish error strings, and SHALL return an empty list when the validated object is valid.
5. THE services (candidate service, merge planner, merge engine) SHALL live in new modules under `slaktbusken/services` and SHALL contain no Qt imports.
6. THE services SHALL be callable from automated tests without a QApplication instance.
7. THE new UI modules SHALL reuse the existing widgets `PersonSearchWidget`, `FamilyView`, `ZoomableGraphicsView` and the `ResearchTab` patterns, and SHALL follow the existing research gateway pattern for cross-window navigation.
8. THE implementation SHALL register the merge-related id prefixes `mergecand_`, `mergecomment_` and `merge_` in `IDGenerator._PREFIXES`.
9. WHEN a project is loaded, THE implementation SHALL reconcile the id prefixes `mergecand_`, `mergecomment_` and `merge_` in the research `id_high_water_marks`, so that a newly generated id never equals an id already present in the project.

### Requirement 35: Mandatory Data-Integrity Tests

**User Story:** As a maintainer, I want the data-integrity tests of this feature to be mandatory, so that the feature cannot be declared complete while any protection against data loss is untested.

#### Acceptance Criteria

1. THE automated test suite SHALL contain each of the following Mandatory_Test_Groups, and each group SHALL include both its example-based tests and the property-based tests mapped to it in Requirement 32 criterion 6: (a) reference preservation, covering the completeness of the Person_Reference_Inventory (Requirement 1 criterion 8) and every Reference_Rule; (b) family relationship integrity, covering cycles, self-relationships, parent-child link types, synchronisation of derived foster and adoptive families, the two-Brita example and same-name siblings (Requirements 23 and 24); (c) failed merges, asserting that a failing merge leaves the project data, the translation files and the dirty flag unchanged; (d) crash recovery, with fault injection at every commit step boundary of Requirement 27 criterion 14, including the Recovery_Refusal case in which a target matches neither the expected old nor the expected new state (Requirement 27 criteria 19 and 25); (e) retired-ID preservation, asserting that a Retired_Person_ID is never reissued, including after save and reopen and when it carries the highest suffix; (f) GEDCOM re-import after a merge (Requirement 30 criteria 4 to 6 and 11).
2. THE test suite SHALL NOT skip, mark as optional, mark as expected-failure (xfail) or deselect any test in a Mandatory_Test_Group, whether by marker, configuration, command-line selection or conditional skip.
3. WHEN determining whether the implementation of this feature is complete, THE project SHALL treat a failing, skipped, xfail-ed, deselected or missing test in any Mandatory_Test_Group as an incomplete implementation.
4. THE feature SHALL be considered complete only when all tests in all Mandatory_Test_Groups pass in the continuous integration run and in a local full run of the test suite.
5. IF a test in a Mandatory_Test_Group cannot run in the environment (for example because a dependency is missing), THEN THE test run SHALL report a failure for that test and SHALL NOT report it as skipped.
6. THE property-based tests mapped to the Mandatory_Test_Groups SHALL be mandatory under criteria 2 to 5 in the same way as the example-based tests, and SHALL run with the default number of generated examples of the project's test configuration.

### Requirement 36: Merge History Completion (added after audit)

**User Story:** As a genealogist, I want to open the merge history from every place where a merge is shown, see what each merge combined, and still find a person by an id that was retired, so that I can always trace what happened to a record.

This requirement completes Requirement 28 criteria 9 and 10 and Requirements 16, 17, 19 and 20, whose Merge_History view, editor block and entry points were not delivered. It does not change Requirements 28.1 to 28.8 and 28.11. Where criterion 2 below orders the view newest first, it governs the display order of the Merge_History_Window only; the stored order and the order returned by Redirect_Resolution stay ascending as in Requirement 28 criterion 5.

#### Acceptance Criteria

1. WHEN a Person_Merge completes, THE Merge_Engine SHALL store in the same Merge_History_Entry a Merge_Summary (`summary_lines`, a list of Swedish texts) that states, derived from the confirmed Merge_Plan, the number of names, events, residences, source citations, media links, families and research links moved to the Surviving_Person and the number of decisions the user made for conflicting single-valued fields. A Merge_History_Entry without `summary_lines` SHALL load with an empty list, and `summary_lines` SHALL survive save, load and round-trip unchanged.
2. WHEN the user opens the Merge_History_Window, THE Merge_History_Window SHALL list its entries newest first, ordered by descending `merge_date` and, for equal dates, by descending numeric suffix of the entry id.
3. THE Merge_History_Window SHALL show for each entry the `merged_person_name`, `merged_person_lifespan`, `merged_person_id`, the `merge_date`, the name and id of the current Surviving_Person (resolved through Redirect_Resolution) and the Merge_Summary, and WHEN the entry has no `summary_lines` THE Merge_History_Window SHALL show the text "Ingen sammanfattning sparades."
4. WHEN the Merge_History_Window is opened for a person id, THE Merge_History_Window SHALL list the entries whose resolved Surviving_Person is that person, and WHEN it is opened without a person id, THE Merge_History_Window SHALL list every entry of the project.
5. IF the Merge_History_Window has no entry to list, THEN THE Merge_History_Window SHALL show the text "Inga sammanslagningar finns."
6. IF Redirect_Resolution returns no person for an entry, THEN THE Merge_History_Window SHALL still list the entry, SHALL show the text "Behållen person kan inte fastställas." in place of the survivor and SHALL disable the navigation action of that entry.
7. WHEN the user selects the action "Gå till behållen person" for an entry whose resolved Surviving_Person exists, THE Merge_History_Window SHALL select that person in the person list and open the Person_Editor for that person.
8. WHEN the user selects an entry, THE Merge_History_Window SHALL show in a details area the archived Merge_Candidates of the entry (the other person's name, assessment and comment count) or the text "Ingen kandidat arkiverades." when there are none.
9. WHEN the Merge_History changes while the Merge_History_Window is open, THE Merge_History_Window SHALL refresh within 500 ms, keeping the selected entry when it still exists.
10. WHILE the "Forskning" tab of the Person_Editor is displayed for a saved person, THE Person_Editor SHALL show below the section "Sammanslagningskandidater" a block "Sammanslagningshistorik" that lists the entries of Requirement 28 criterion 9 with name, lifespan and date, SHALL show "Inga sammanslagningar finns." when there are none, and SHALL provide the button "Visa sammanslagningshistorik" that opens the Merge_History_Window for the edited person.
11. THE application SHALL provide the entry points "Visa sammanslagningshistorik" in the context menu of a person in the person list (enabled only for a person with at least one entry), the button "Sammanslagningshistorik" in the Candidate_Register (opening the window without a person id, or for the person the register is filtered to), the menu item "Sammanslagningshistorik" next to "Sammanslagningskandidater" in the main menu, the grey Candidate_Indicator in the person list and in diagram person boxes, and the button "Visa sammanslagningshistorik" of the box shown after a completed merge, and each SHALL open the Merge_History_Window.
12. THE `open_history` function of the application SHALL open the Merge_History_Window and SHALL NOT show a status-bar message that the history is unavailable.
13. WHEN the user searches for a person by a Retired_Person_ID in the person search, THE application SHALL list the Surviving_Person as a result with the text "Sammanslagen med <namn> (<år–år>)" naming the Merged_Away_Person, and WHEN the user selects it THE application SHALL open the Surviving_Person.
14. WHEN a caller asks the application to open a person, a comparison or a candidate by a Retired_Person_ID, THE application SHALL redirect the request to the resolved Surviving_Person and SHALL show the status-bar text "Personen <id> slogs samman med <namn>." IF Redirect_Resolution returns no person, THEN THE application SHALL show a message naming the id and SHALL open nothing.
15. WHILE a person shown in a slot of the Person_Comparison_Window has at least one Merge_History_Entry, THE Person_Comparison_Window SHALL show a button "Sammanslagningshistorik" for that slot that opens the Merge_History_Window for that person.
16. FOR ALL valid projects and all person ids, THE rows of the Merge_History_Window for the person SHALL equal, in reverse order, the entries returned by `RedirectResolver.merged_into` for that person, and the displayed `merged_person_name`, `merged_person_lifespan`, `merged_person_id` and `merge_date` of each row SHALL equal the stored fields of its entry.
