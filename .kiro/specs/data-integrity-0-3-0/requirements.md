# Requirements Document

## Introduction

This spec is "Package 1: Data Integrity and Loss Prevention" of release 0.3.0 (branch `Features0.3.0`) of Släktbusken, a Python 3 / PySide6 genealogy application. The project file format is currently "0.4"; the application is pre-1.0 and not in production.

The document has three parts:

- **Part A, Confirmed bugs (Requirements 1-11).** Each bug was verified in code and, where stated, reproduced headless. Every Part A requirement ends with a mandatory acceptance test. No test for a confirmed bug is optional.
- **Part B, Model improvements (Requirements 12-22).** These add the structure the fixes need: event-level citations, structured date qualifiers, a single change-marking API, durable GEDCOM identity for events and for residences, import atomicity including a conflict-safe, crash-consistent save, and format version 0.5.
- **Part C, Mandatory test group (Requirement 23).** A new mandatory group "Dataskydd" collects all tests of this spec.

Bug-to-requirement map:

| Bug | Requirement | Summary |
|---|---|---|
| B1 | 1 | Person editor "Avbryt" leaves live data mutated |
| B5 | 2 | Nested editors create places/sources that survive Avbryt |
| B2 | 3, 20 | GEDCOM import does not mark the project dirty |
| B3 | 4 | Place deletion does not mark dirty |
| B4 | 5 | Place translation editor "skapa platser" does not mark dirty |
| B6 | 6 | Event editor drops citations when the date is empty |
| B7 | 7 | Event editor hides and drops place citations |
| B8 | 8 | Event editor drops `from_place` on save |
| B9 | 9, 11 | GEDCOM date import silently drops or distorts dates |
| B10 | 10, 19 | Dateless events with same type and place are conflated on re-import; family events are deleted and recreated on update import |
| (former limitation, now in scope) | 22 | Residences are duplicated on every update import because `GEDCOM_Importer._create_residence` always appends a ResidenceFact |

Binding user decisions D1 to D7, the approved answers OQ1 to OQ7 and the approvals AP1 to AP5 are referenced where they apply. AP1 (origin on legacy events by one-to-one content match), AP2 (staged translation data with a write-ahead intent file, extended by hash verification and a conflict refusal), AP3 (the "Från plats" selector) and AP5 (family events kept on update import) are approved as designed. AP4 changed: residence duplication is fixed in this package (Requirement 22). Package 2 (Advanced Person Filtering) is out of scope. The only link to it is that the date qualifiers of Requirement 14 are structured so that Package 2 can build on them.

All UI text quoted in this document is Swedish. All documents are written in English.

### Known limitations

These behaviours are deliberate or pre-existing and are not changed by this spec. Each is pinned by a test or recorded so that a later change is a conscious decision.

1. **Deleted imported events reappear.** When the user deletes an imported event and the same GEDCOM record is imported again, the event is created again, because no deletion record is kept. Requirement 10.13 pins this.
2. **Deleted imported residences reappear.** When the user deletes an imported residence and the same `RESI` record is imported again, the residence is created again, for the same reason. Requirement 22.17 pins this. The former limitation "residences are duplicated on update import" is closed by Requirement 22.
3. **Legacy records are claimed only on exact content.** Events and residences created before format 0.5 have no origin. The importer claims such a record only when its content equals what the importer would create from the incoming record (Requirements 19.7 and 22.6). A legacy record that differs in any compared field (for example because the user edited it, or because the 0.3.0 date parser reads the date differently than the older parser did) is not claimed; the import then creates a new record and adds a review notice. Residence duplicates that earlier imports created are kept and never merged automatically; the import log reports them (Requirement 22.16).
4. **Update import overwrites existing person fields.** Name, sex, title, occupation and notes of a matched person are replaced from the GEDCOM record. This spec does not change that.
5. **Swedish calendar dates are preserved, not converted.** The Swedish calendar of 1 March 1700 to 30 February 1712 is not modelled. Dates in that window keep their text and have unknown comparison bounds (Requirement 15.6).
6. **Dual-year dates are preserved as original text.** Expressions such as `1700/01` become Unparsed_Dates (Requirement 9.7).
7. **Translation editors wait for the save.** While an import is waiting for the project to be saved, the translation editors refuse to open (Requirement 20.12).
8. **A conflict blocks the project until the user resolves it by hand.** When an unfinished import save finds a file that was changed outside Släktbusken, the project does not open, as after a refused merge recovery. There is no read-only open mode in the application (Requirements 20.17 and 20.18).

## Glossary

- **Project_Data**: The in-memory `ProjectData` object that holds all persons, families, events, places, sources, media, repositories, residences, DNA data, research data, merge data and related collections.
- **Project_Service**: The `ProjectService` class in `slaktbusken/services/project_service.py`. It owns the `Project_Data` instance, the dirty state and the revision counters.
- **Dirty_State**: The Project_Service flag that says the project has unsaved changes.
- **Content_Revision**: The in-memory counter `content_revision` that the Project_Service increments for every content change.
- **Change_Marker**: The single public Project_Service method `mark_changed` introduced by Requirement 17.
- **Mutation_Path**: One user-reachable code path that changes Project_Data (for example "remove event in the person editor" or "GEDCOM import").
- **Canonical_Form**: The deterministic serialization of Project_Data (the project JSON produced by the persistence serializer, with keys sorted) used to decide whether two states are identical.
- **Edit_Session**: A scope created by the Project_Service when the Person_Editor opens. It records a full snapshot of Project_Data and ends in either commit or rollback.
- **Session_Start_Conditions**: The conditions of Requirement 1.9 under which an Edit_Session must not start.
- **Person_Editor**: The dialog `slaktbusken/ui/editors/person_editor.py`.
- **Event_Editor**: The dialog `slaktbusken/ui/editors/event_editor.py`.
- **Residence_Editor**: The dialog that creates and edits Residence facts, including "flytt" events.
- **Place_Editor**: The dialog `slaktbusken/ui/editors/place_editor.py`.
- **Place_Translation_Editor** and **Source_Translation_Editor**: The dialogs `slaktbusken/ui/editors/place_translation_editor.py` and `slaktbusken/ui/editors/source_translation_editor.py`.
- **Nested_Editor**: Any editor opened from the Person_Editor, the Event_Editor or the Residence_Editor (for example Place_Editor, Source_Editor, media editors).
- **Editor_Registry**: The `EditorRegistry` in `slaktbusken/services/editor_registry.py` that tracks open editors with unsaved changes. Each editor has a Swedish `editor_title`, for example "Personredigerare: Anna Svensson (person_12)".
- **Source_Reference**: A `SourceRef` (source id, quality, note, aspects).
- **Citation_Context**: The location of a Source_Reference on an event. One of `event`, `date`, `place`, `from_place`.
- **Citation_Helper**: The single module-level function set in `slaktbusken/model/event_citations.py` introduced by Requirement 13. Its main function is `event_citations(event)`, which returns `(Citation_Context, Source_Reference)` pairs.
- **Identical_Reference**: Two Source_References with equal source id, quality, note and aspects (aspects compared as ordered lists).
- **Date_Value**: The `DateValue` dataclass of an event date.
- **Date_Qualifier**: The new `DateValue.qualifier` field. Allowed values: `exact`, `about`, `estimated`, `calculated`, `before`, `after`, `between`, `from_to`, `from`, `to`, `interpreted`, `unparsed`.
- **Original_Text**: The new `DateValue.original_text` field that holds the original GEDCOM date expression.
- **Unparsed_Date**: A Date_Value with qualifier `unparsed`, an empty `value` and a non-empty Original_Text.
- **Date_Semantics**: The new module `slaktbusken/model/date_semantics.py` that validates, bounds and formats Date_Values.
- **Swedish_Calendar_Window**: The months 1700-02 to 1712-02 inclusive. During this window Sweden used a calendar one day ahead of the Julian calendar, and 30 February 1712 existed.
- **GEDCOM_Importer**: The class in `slaktbusken/gedcom/importer.py`.
- **GEDCOM_Exporter**: The class in `slaktbusken/gedcom/exporter.py`.
- **Import_Service**: The `ImportService` in `slaktbusken/services/import_service.py`.
- **Import_Log**: The list of Swedish warnings and notices returned in the import result and shown to the user.
- **Working_Copy**: A deep copy of Project_Data on which an import runs before the result is adopted.
- **Translation_Files**: The files `translation/persons.json`, `translation/places.json` and `translation/sources.json` of a project.
- **Staged_Translation**: The translation data an import produced in memory. The import never writes it.
- **Pending_Translation**: The Staged_Translation together with its Translation_Base. The Project_Service holds it until the next successful project save or until the project is closed.
- **Translation_Base**: The SHA-256 digest of the bytes of each of the three Translation_Files (or the marker `absent` for a missing file) as they were when the import that produced the Pending_Translation read them. A second import that starts from a Pending_Translation keeps the Translation_Base of the first.
- **Disk_Digest**: The SHA-256 digest of the project file bytes as the Project_Service last read them at open or last wrote them at save (or the marker `absent` when the file does not exist).
- **Translation_Intent**: The write-ahead file `<project file name>.import-intent.json` beside the project file. It is created by writing a temporary file and replacing the intent file with it, so it is either absent or complete. It holds the old and the new SHA-256 digest of the project file, and for each changed Translation_File its name, its old digest, its new digest and its new content.
- **Digest_Verification**: The comparison of the actual SHA-256 digest of a file on disk with its expected old digest and its expected new digest. A file is in state OLD, NEW or OTHER (content equal to neither).
- **Conflict_Refusal**: The refusal of a save or of a project open because Digest_Verification found a file in state OTHER, or an unreadable Translation_Intent. Nothing is overwritten and the Translation_Intent and its temporary files stay on disk.
- **Import_Save_Unfinished**: The Project_Service state after a save that replaced the project file but could not finish the Translation_Files. The Translation_Intent stays on disk. Saving, importing and the translation editors are refused until the project has been reopened.
- **Event_Origin**: The new `Event.origin` record (owner kind, owner id, owner xref, tag key, occurrence index, record hash, optional uid) that identifies the GEDCOM record an event was created from.
- **Residence_Origin**: The same record type as Event_Origin, stored in the new `ResidenceFact.origins` list. The owner kind is `INDI` and the tag key is `RESI`. The dataclass is `RecordOrigin` in `slaktbusken/model/record_origin.py`, shared by both uses.
- **Owner_Id**: The App_JSON person id or family id that the GEDCOM_Importer resolved for the owner record when it created the event or residence.
- **Event_Identity_Matcher**: The component that decides, during update import, whether an incoming GEDCOM event record corresponds to an existing event.
- **Residence_Identity_Matcher**: The same matching function as the Event_Identity_Matcher, applied to incoming `RESI` records and to existing ResidenceFacts.
- **Person_Reference_Inventory**: The table `PERSON_REFERENCE_INVENTORY` in `slaktbusken/services/person_reference_index.py` that lists every place where a person id is stored and the merge rule for it.
- **Merged_Identity_Record**: A GEDCOM person record whose xref or fingerprint resolves through an identity alias to a person that a merge retired.
- **Migration_Manager**: The `MigrationManager` in `slaktbusken/persistence/migration.py`.
- **Dataskydd_Group**: The new mandatory test group (key `data_protection`, Swedish title "Dataskydd") in `tests/mandatory_groups.py`.

## Requirements

## Part A: Confirmed bugs

### Requirement 1: Person editor Avbryt rolls back every change (B1, D1, OQ3, OQ7)

**User Story:** As a researcher, I want "Avbryt" in the person editor to undo everything I did in that editing session, so that cancelling never leaves half-edited data in my project.

#### Acceptance Criteria

1. WHEN the Person_Editor opens, THE Project_Service SHALL start one Edit_Session that records a full snapshot of every persistent field of Project_Data (every list collection, the project metadata and `connection_overrides`).
2. WHEN the user chooses "Avbryt" or closes the Person_Editor without saving, THE Project_Service SHALL roll back the Edit_Session so that the Canonical_Form of Project_Data equals the Canonical_Form recorded when the Edit_Session started.
3. WHEN an Edit_Session is rolled back, THE Project_Service SHALL restore each entity that existed at session start in place, so that Python references to those entities and to the Project_Data collection lists remain valid.
4. WHEN an Edit_Session is rolled back, THE Project_Service SHALL leave Dirty_State, Content_Revision and the clean content revision unchanged.
5. WHEN an Edit_Session is rolled back, THE Project_Service SHALL notify revision listeners once so that open views refresh.
6. WHEN the user saves in the Person_Editor and the Canonical_Form differs from the session-start Canonical_Form, THE Project_Service SHALL commit the Edit_Session by calling the Change_Marker exactly once.
7. WHEN the user saves in the Person_Editor and the Canonical_Form equals the session-start Canonical_Form, THE Project_Service SHALL commit the Edit_Session without changing Dirty_State or Content_Revision.
8. WHILE an Edit_Session is active, THE Project_Service SHALL refuse to start a second Edit_Session and SHALL refuse GEDCOM import, person merge and person deletion with a Swedish message that names the open person editor by its `editor_title`.
9. IF any of the Session_Start_Conditions holds, THEN THE Project_Service SHALL refuse to start an Edit_Session, THE Person_Editor SHALL NOT open, and THE refusal message SHALL be Swedish; the Session_Start_Conditions are: (a) another Edit_Session is active, (b) the Editor_Registry reports a registered editor with unsaved changes, (c) a merge is in progress or a Merge_Journal or recovery refusal is pending for the project, or an import save is unfinished (Import_Save_Unfinished; the design lists it as condition c2 with its own message), (d) a GEDCOM import is running, (e) no project is open, (f) the snapshot cannot be created.
10. IF the Editor_Registry reports an editor with unsaved changes at session start, THEN THE refusal message SHALL name that editor by its Swedish `editor_title` and SHALL tell the user to save or close it first, in the form "Spara eller stäng "{editor_title}" innan du öppnar personredigeraren.".
11. IF the Content_Revision at rollback differs from the Content_Revision recorded at session start or at the last session-owned change, THEN THE Project_Service SHALL refuse the automatic rollback, keep the Person_Editor open and offer "Spara" or "Behåll redigeraren öppen" without overwriting any data.
12. WHEN an Edit_Session is started and rolled back on a generated project with 10,000 persons, THE mandatory test SHALL measure and report the elapsed time, and SHALL fail only when the elapsed time exceeds 10 seconds; the figure 1.5 seconds is a reported goal and SHALL NOT change the snapshot scope.
13. THE Edit_Session SHALL NOT snapshot only part of Project_Data; a reduced-scope snapshot MAY be introduced only after a test shows that its rollback result equals the full-snapshot result for every mutation sequence the Nested_Editors can perform, including nested creations and modifications, and after the user has approved the change.
14. THE Dataskydd_Group SHALL contain the acceptance tests `test_cancel_after_remove_event_restores_event`, `test_cancel_after_delete_residence_restores_residence`, `test_cancel_after_parent_family_edit_restores_families`, `test_cancel_after_new_family_removes_family`, `test_cancel_restores_identity_of_entities`, `test_cancel_leaves_dirty_and_revision_unchanged`, `test_save_unchanged_does_not_mark_dirty`, `test_second_session_refused`, `test_conflict_detected_refuses_rollback`, `test_session_start_refused_when_unsafe`, `test_session_snapshot_covers_every_project_data_field` and `test_edit_session_10k_persons_reports_time_within_bound`.

### Requirement 2: Nested creations are rolled back with the outer dialog (B5, D1)

**User Story:** As a researcher, I want places, sources and media that I create from inside an event or residence dialog to disappear when I cancel the person editor, so that cancelling leaves no orphans.

#### Acceptance Criteria

1. WHEN a Nested_Editor creates a place, source, media item, repository, family or any other Project_Data entity while an Edit_Session is active, THE Project_Service SHALL include that creation in the Edit_Session.
2. WHEN the Person_Editor is cancelled after nested creations, THE Project_Service SHALL remove every entity created during the Edit_Session from Project_Data.
3. WHEN the Person_Editor is cancelled, THE Project_Service SHALL restore every place, source, media item and other entity that a Nested_Editor edited or deleted during the Edit_Session.
4. WHEN the Person_Editor is cancelled, THE Project_Service SHALL leave the id counters used for new entities in a state that never re-issues an id already referenced in saved data.
5. WHEN the user saves the Person_Editor after nested creations, THE Project_Service SHALL keep the created entities and SHALL mark the project changed once.
6. THE Dataskydd_Group SHALL contain the acceptance tests `test_cancel_removes_nested_created_place`, `test_cancel_removes_nested_created_source`, `test_cancel_restores_nested_deleted_place`, `test_cancel_removes_nested_created_media` and `test_save_keeps_nested_created_entities`.

### Requirement 3: GEDCOM import marks the project changed (B2)

**User Story:** As a researcher, I want the application to know that a GEDCOM import changed my project, so that closing the application asks me to save.

#### Acceptance Criteria

1. WHEN a new-project GEDCOM import or an update import adds or changes project data or translation data, THE Import_Service SHALL cause exactly one Change_Marker call, which sets Dirty_State and increments Content_Revision once.
2. WHEN a GEDCOM import adds or changes neither project data nor translation data, THE Import_Service SHALL leave Dirty_State, Content_Revision and Pending_Translation unchanged.
3. WHEN the import changes translation data only (for example a changed xref in a person mapping), THE Import_Service SHALL still cause the Change_Marker call, so that the next save writes the Translation_Files.
4. WHEN the user closes the application after a data-changing import without saving, THE application SHALL show the unsaved-changes prompt.
5. WHEN an import changes data, THE Project_Service SHALL notify merge listeners once.
6. THE Dataskydd_Group SHALL contain the acceptance tests `test_import_marks_dirty_and_bumps_revision`, `test_noop_import_does_not_mark_dirty`, `test_import_notifies_listeners_once`, `test_close_after_import_prompts_to_save` and `test_translation_only_change_marks_dirty`.

### Requirement 4: Place deletion marks the project changed (B3)

**User Story:** As a researcher, I want deleting a place to mark my project as changed, so that the deletion is saved.

#### Acceptance Criteria

1. WHEN the user deletes a place in the Place_Editor, THE Project_Service SHALL remove the place through a Project_Service method that calls the Change_Marker once.
2. IF a place is still referenced by an event, residence or other place, THEN THE Place_Editor SHALL keep the existing refusal behaviour and THE Project_Service SHALL leave Dirty_State and Content_Revision unchanged.
3. THE Dataskydd_Group SHALL contain the acceptance tests `test_place_delete_marks_dirty_and_bumps_revision` and `test_place_delete_refused_does_not_mark_dirty`.

### Requirement 5: "Skapa platser" marks the project changed (B4)

**User Story:** As a researcher, I want places created by the place translation editor to mark my project as changed, so that they are saved.

#### Acceptance Criteria

1. WHEN the Place_Translation_Editor creates one or more places through "skapa platser", THE Project_Service SHALL add them through a Project_Service method that calls the Change_Marker once for the whole operation.
2. WHEN "skapa platser" creates no place, THE Project_Service SHALL leave Dirty_State and Content_Revision unchanged.
3. THE Dataskydd_Group SHALL contain the acceptance tests `test_create_places_marks_dirty_once` and `test_create_places_none_created_stays_clean`.

### Requirement 6: Citations survive an empty or removed date (B6, D2)

**User Story:** As a researcher, I want source citations to survive when I clear or never fill in an event date, so that I never lose evidence.

#### Acceptance Criteria

1. WHEN the user saves an event whose date text is empty and the Källor table has rows, THE Event_Editor SHALL store the rows as event-level Source_References.
2. WHEN the user clears the date of an event whose Date_Value has Source_References, THE Event_Editor SHALL ask "Flytta till händelsen" or "Ta bort källhänvisningarna" or "Avbryt".
3. WHEN the user chooses "Flytta till händelsen", THE Event_Editor SHALL move every Source_Reference of the removed date to the event-level Source_References with source id, quality, note and aspects unchanged.
4. WHEN the user chooses "Ta bort källhänvisningarna", THE Event_Editor SHALL remove the links and SHALL leave the Source records unchanged.
5. WHEN the user chooses "Avbryt", THE Event_Editor SHALL keep the date and all its Source_References as they were.
6. THE Event_Editor SHALL preselect "Flytta till händelsen" as the default button of the prompt.
7. WHEN Source_References are moved to another Citation_Context, THE Event_Editor SHALL skip a moved reference only when an Identical_Reference already exists in the target Citation_Context, and SHALL keep every other reference, so that the set of distinct (source id, quality, note, aspects) tuples of the event is the same before and after the move.
8. THE Event_Editor SHALL NOT merge, reorder or deduplicate references that already exist in a Citation_Context and are not moved.
9. THE Dataskydd_Group SHALL contain the acceptance tests `test_empty_date_keeps_citations_as_event_level`, `test_clear_date_prompt_move_preserves_all_fields`, `test_clear_date_prompt_remove_keeps_source_record`, `test_clear_date_prompt_cancel_preserves_state`, `test_prompt_default_is_move`, `test_move_dedupes_only_exact_identical_references` and `test_move_keeps_distinct_citation_details`.

### Requirement 7: Place citations are shown and preserved (B7, D2)

**User Story:** As a researcher, I want citations attached to an event's place or from-place to be visible and to survive saving, and I want to be asked before a change or removal of the place detaches them, so that evidence is never silently lost or silently attributed to the wrong place.

#### Acceptance Criteria

1. WHEN the Event_Editor loads an event, THE Event_Editor SHALL show the Source_References of the event, its date, its place and its from_place in the Källor table with a "Gäller" column that names the Citation_Context in Swedish ("Händelse", "Datum", "Plats", "Från plats").
2. WHEN the Event_Editor saves an event, THE Event_Editor SHALL write each Source_Reference back to the Citation_Context shown in its row.
3. WHEN the user opens and saves an event without changing the date, place or from_place, THE Event_Editor SHALL keep every Source_Reference in its Citation_Context and SHALL show no prompt.
4. WHEN the user removes the place or the from_place of an event and the Källor table has rows for that Citation_Context, THE Event_Editor SHALL ask "Flytta till händelsen" or "Ta bort källhänvisningarna" or "Avbryt".
5. WHEN the user changes the place or the from_place of an event to a different place and the Källor table has rows for that Citation_Context, THE Event_Editor SHALL ask "Behåll för nya platsen" or "Flytta till händelsen" or "Ta bort källhänvisningarna" or "Avbryt".
6. WHEN the user chooses "Behåll för nya platsen", THE Event_Editor SHALL attach the rows unchanged to the new place reference of the same Citation_Context.
7. WHEN the user chooses "Flytta till händelsen" for a place or from_place, THE Event_Editor SHALL apply the move rules of Requirement 6.3, 6.7 and 6.8.
8. WHEN the user chooses "Ta bort källhänvisningarna" or "Avbryt" for a place or from_place, THE Event_Editor SHALL apply the rules of Requirement 6.4 and 6.5.
9. THE Event_Editor SHALL preselect "Flytta till händelsen" as the default button of both the removal prompt and the change prompt, because moving to the event keeps the evidence without claiming that it supports the new place.
10. IF several prompts are needed for one save (date, place, from_place), THEN THE Event_Editor SHALL ask them in that order, SHALL change nothing until all are answered, and SHALL abort the whole save without any change when the user chooses "Avbryt" in any of them.
11. THE Event_Editor SHALL NOT delete any Source record, whatever the user chooses.
12. THE Dataskydd_Group SHALL contain the acceptance tests `test_place_citations_shown_in_table_with_context`, `test_place_citations_survive_save`, `test_open_save_unchanged_event_no_prompt`, `test_remove_place_prompt_move_to_event`, `test_remove_place_prompt_remove_links`, `test_remove_place_prompt_cancel_preserves_state`, `test_remove_from_place_prompt_move_to_event`, `test_change_place_prompt_keep_for_new_place`, `test_change_place_prompt_move_to_event`, `test_change_place_prompt_remove_links`, `test_change_place_prompt_cancel_preserves_state`, `test_change_from_place_prompt_choices`, `test_change_place_prompt_default_is_move`, `test_change_place_without_citations_no_prompt`, `test_multiple_prompts_cancel_changes_nothing` and `test_no_prompt_choice_deletes_a_source_record`.

### Requirement 8: Flytt events keep from_place (B8, AP3 approved)

**User Story:** As a researcher, I want the origin of a move to survive every save, so that flytt events never lose where the person came from.

#### Acceptance Criteria

1. WHEN the Event_Editor saves an event, THE Event_Editor SHALL pass the `from_place` value, including its Source_References, to the event it builds.
2. WHEN the Residence_Editor creates or saves a flytt event, THE Residence_Editor SHALL preserve the `from_place` of that event.
3. WHEN a flytt event is opened and saved without edits in the Event_Editor, THE Project_Data SHALL keep the same Canonical_Form.
4. WHILE the event type of the edited event is `flytt`, THE Event_Editor SHALL show a "Från plats" selector that lists the places of the project and holds the current `from_place`.
5. WHEN the user selects a place in the "Från plats" selector and saves, THE Event_Editor SHALL store that place as `from_place`, and WHEN the user clears the selector and saves, THE Event_Editor SHALL store `from_place` as absent.
6. THE Event_Editor SHALL keep the Source_References of `from_place` in their own Citation_Context "Från plats" and SHALL apply Requirement 7.4 to 7.10, including the prompts, to them. THE Event_Editor SHALL NOT merge them into the Citation_Context "Plats".
7. WHEN the event type is changed from `flytt` to another type and the event has a `from_place`, THE Event_Editor SHALL keep `from_place` and its Source_References unchanged and SHALL show the "Från plats" selector only while the type is `flytt`.
8. THE Dataskydd_Group SHALL contain the acceptance tests `test_event_editor_save_preserves_from_place`, `test_residence_editor_save_preserves_from_place`, `test_open_save_without_edit_is_identity_for_flytt`, `test_clear_from_place_stores_none`, `test_from_place_selector_shown_only_for_flytt`, `test_from_place_selector_sets_from_place`, `test_from_place_citations_keep_separate_context` and `test_type_change_away_from_flytt_keeps_from_place`.

### Requirement 9: GEDCOM date import never loses or distorts a date (B9, D3, D7, OQ2)

**User Story:** As a researcher, I want every GEDCOM date to be imported correctly or stored as original text, so that no date is silently dropped or turned into a wrong exact date.

#### Acceptance Criteria

1. WHEN a GEDCOM event date is `BET x AND y`, THE GEDCOM_Importer SHALL create a Date_Value with qualifier `between`, `value` x and `value_to` y.
2. WHEN a GEDCOM event date is `FROM x TO y`, THE GEDCOM_Importer SHALL create a Date_Value with qualifier `from_to`, `value` x and `value_to` y.
3. WHEN a GEDCOM event date is `FROM x` or `TO y`, THE GEDCOM_Importer SHALL create a Date_Value with qualifier `from` or `to` respectively.
4. WHEN a GEDCOM event date begins with `BEF`, `AFT`, `ABT`, `EST` or `CAL`, THE GEDCOM_Importer SHALL create a Date_Value with qualifier `before`, `after`, `about`, `estimated` or `calculated` respectively.
5. WHEN a GEDCOM event date has the form `INT x (text)`, THE GEDCOM_Importer SHALL create a Date_Value with qualifier `interpreted`, the value of x and the full expression as Original_Text.
6. WHEN a GEDCOM event date carries the calendar escape `@#DJULIAN@` before each of its endpoints (or once before the whole expression) and every endpoint is a real Julian date, THE GEDCOM_Importer SHALL create a Date_Value with `calendar` set to `julian` and every endpoint stored as written, without any conversion.
7. WHEN a GEDCOM event date has a dual year such as `1700/01`, THE GEDCOM_Importer SHALL create an Unparsed_Date with the expression as Original_Text and SHALL add a Swedish warning to the Import_Log, because the dual year has no single historically reliable interpretation.
8. WHEN a GEDCOM event date uses a Swedish month name (JAN, FEB, MARS, APR, MAJ, JUNI, JULI, AUG, SEP, OKT, NOV, DEC) or an ISO date or a dotted date such as `05.03.1850`, THE GEDCOM_Importer SHALL create the corresponding exact Date_Value and keep the expression as Original_Text.
9. IF a GEDCOM event date cannot be interpreted (for example `(okänt)`, a calendar escape other than Julian and Gregorian, a range whose endpoints use different calendars, a reversed range, or a day that does not exist in the stated calendar such as `32 JAN 1900`, `31 FEB 1900` or `30 FEB 1712`), THEN THE GEDCOM_Importer SHALL create an Unparsed_Date with the expression as Original_Text and SHALL add a Swedish warning to the Import_Log.
10. WHEN a Julian expression lies in the Swedish_Calendar_Window, THE GEDCOM_Importer SHALL store it as written with `calendar` set to `julian`, and Date_Semantics SHALL report unknown comparison bounds for it (Requirement 14.8).
11. WHEN an expression without calendar escape names a day that does not exist in the Gregorian calendar but exists in the Julian calendar (for example `29 FEB 1700`), THE GEDCOM_Importer SHALL create an Unparsed_Date with the expression as Original_Text, because the calendar of the writer is unknown.
12. THE GEDCOM_Importer SHALL create a Date_Value for every event or family event with a non-empty DATE line, so that no DATE line is dropped without a stored Original_Text.
13. THE GEDCOM_Importer SHALL apply the same date interpretation to events, family events and residence facts.
14. THE GEDCOM_Importer SHALL store Original_Text when the GEDCOM expression, after whitespace and case normalization, differs from the expression the GEDCOM_Exporter would write for the structured fields.
15. THE Dataskydd_Group SHALL contain the acceptance tests `test_import_between_and`, `test_import_from_to`, `test_import_from_only_and_to_only`, `test_import_before_after_about_estimated_calculated`, `test_import_int_phrase`, `test_import_julian_as_written`, `test_import_julian_escape_per_endpoint`, `test_import_julian_swedish_window_kept_as_written`, `test_import_dual_year_becomes_unparsed`, `test_import_swedish_month_names`, `test_import_iso_and_dotted_dates`, `test_import_invalid_dates_become_unparsed`, `test_import_exceptional_swedish_dates_become_unparsed`, `test_import_mixed_calendar_range_becomes_unparsed`, `test_import_unknown_phrase_becomes_unparsed_with_warning`, `test_import_residence_dates_use_same_interpretation`, `test_no_date_line_is_ever_dropped` and `test_from_to_never_becomes_exact_year`.

### Requirement 10: Re-import never conflates, duplicates or deletes events (B10, D4, OQ1)

**User Story:** As a researcher, I want repeated imports of the same GEDCOM file to keep my events as they are, so that I get neither merged events, nor duplicates, nor lost edits.

#### Acceptance Criteria

1. THE GEDCOM_Importer SHALL NOT treat two events as the same because they share event type and place, or because they share a tag and an occurrence index.
2. WHEN the same GEDCOM file is imported again into a project in which no imported event was deleted and no GEDCOM record changed, THE GEDCOM_Importer SHALL create no event, SHALL modify no event and SHALL leave every `Family.event_ids` list unchanged.
3. WHEN a person has several dateless events of the same type and place in the GEDCOM file, THE GEDCOM_Importer SHALL create one event per record on first import and SHALL create no additional event on re-import.
4. THE GEDCOM_Importer SHALL NOT remove, merge or modify any existing event during update import, with one exception: adding Event_Origin to a legacy event under Requirement 19.7.
5. WHEN the records of one owner are reordered in the GEDCOM file with unchanged content, THE GEDCOM_Importer SHALL create no event and SHALL modify no event.
6. WHEN one record is inserted into the records of an owner, THE GEDCOM_Importer SHALL create exactly one event for the inserted record and SHALL leave every other event unchanged.
7. WHEN a record is removed from the GEDCOM file, THE GEDCOM_Importer SHALL keep the corresponding existing event unchanged.
8. WHEN an owner has k identical incoming records and m existing events with that record hash, THE GEDCOM_Importer SHALL treat min(k, m) of them as unchanged and SHALL create max(k - m, 0) new events.
9. WHEN the user edited an imported event in the application and its GEDCOM record is unchanged, THE GEDCOM_Importer SHALL leave the event unchanged and SHALL create no event.
10. IF an incoming record has no `_UID` match and no equal record hash among the events of its owner, THEN THE GEDCOM_Importer SHALL create a new event, SHALL leave every existing event unchanged and, WHERE unclaimed existing events of the same owner and tag exist, SHALL add a Swedish notice to the Import_Log that names the new event and those candidate events.
11. IF an incoming record has a `_UID` equal to the uid of an existing event but a different record hash, THEN THE GEDCOM_Importer SHALL leave the event unchanged and SHALL add a Swedish notice to the Import_Log.
12. WHEN a record is a Merged_Identity_Record, THE GEDCOM_Importer SHALL create no event and modify no event for it, as it does for the person today.
13. WHEN the user deleted an imported event and the same GEDCOM record is imported again, THE GEDCOM_Importer SHALL create the event again (known limitation 1).
14. WHEN a family already exists and its FAM record is imported again, THE GEDCOM_Importer SHALL NOT delete any event, SHALL apply the Event_Identity_Matcher to the family event records, and SHALL keep every id of `Family.event_ids` and append the ids of newly created events.
15. WHEN a GEDCOM file that contains `RESI` records is imported, THE GEDCOM_Importer SHALL apply Requirement 22 to the residences in the same run, so that criteria 10.2 to 10.14 and the corresponding residence criteria of Requirement 22 hold together for one import, and the repeated-import properties 16 and 17 SHALL be generated from files that contain `RESI` records.
16. THE Dataskydd_Group SHALL contain the acceptance tests `test_dateless_same_type_place_events_stay_distinct`, `test_reimport_identical_file_creates_no_events`, `test_reimport_is_idempotent_property`, `test_reimport_reordered_records_creates_no_events`, `test_reimport_inserted_record_creates_one_event`, `test_reimport_removed_record_keeps_event`, `test_reimport_identical_records_pair_by_count`, `test_reimport_after_user_edit_leaves_event_unchanged`, `test_reimport_changed_record_creates_new_with_notice`, `test_reimport_uid_match_changed_record_reports_without_modifying`, `test_reimport_never_removes_existing_events`, `test_reimport_family_events_preserved`, `test_family_event_ids_never_dropped`, `test_deleted_imported_event_reappears_known_limitation` and `test_ambiguous_event_creates_new_with_review_notice`.

### Requirement 11: GEDCOM export keeps date information (B9 export side, D3, OQ6)

**User Story:** As a researcher, I want exported GEDCOM files to keep my date qualifiers and ranges, so that a round trip through GEDCOM does not weaken my data.

#### Acceptance Criteria

1. WHEN the GEDCOM_Exporter writes a Date_Value with qualifier `about`, `estimated`, `calculated`, `before` or `after`, THE GEDCOM_Exporter SHALL write `ABT`, `EST`, `CAL`, `BEF` or `AFT` respectively.
2. WHEN the GEDCOM_Exporter writes a Date_Value with qualifier `between`, `from_to`, `from` or `to`, THE GEDCOM_Exporter SHALL write `BET x AND y`, `FROM x TO y`, `FROM x` or `TO y` respectively.
3. WHEN a Date_Value has `calendar` set to `julian`, THE GEDCOM_Exporter SHALL write the `@#DJULIAN@` escape before each endpoint.
4. WHEN a Date_Value has Original_Text and the Original_Text interprets to the stored structured fields, THE GEDCOM_Exporter SHALL write the Original_Text verbatim.
5. WHEN a Date_Value is an Unparsed_Date, THE GEDCOM_Exporter SHALL write its Original_Text verbatim.
6. IF a Date_Value has Original_Text that does not interpret to the stored structured fields, THEN THE GEDCOM_Exporter SHALL write the date from the structured fields and SHALL add a Swedish warning to the export log.
7. THE GEDCOM_Exporter SHALL write ordinary events and placement events with the same date formatting rules.
8. THE GEDCOM_Exporter SHALL write `ABT` for precision `approximate` only when the effective qualifier is `about`, so that a `before`, `after` or range date is never exported as `ABT`.
9. THE Dataskydd_Group SHALL contain the acceptance tests `test_export_qualifiers`, `test_export_ranges`, `test_export_julian_escape`, `test_export_original_text_verbatim`, `test_export_unparsed_verbatim`, `test_export_stale_original_text_uses_structured`, `test_export_before_never_abt` and `test_gedcom_date_round_trip_property`.

## Part B: Model improvements

### Requirement 12: Event-level source citations (M1)

**User Story:** As a researcher, I want to cite a source for an event as a whole, independent of its date and place, so that evidence has a home even when the date or place is unknown.

#### Acceptance Criteria

1. THE Event model SHALL have a field `source_refs` that holds a list of Source_References and defaults to an empty list.
2. THE persistence serializer SHALL write `source_refs` of an event only when the list is non-empty.
3. WHEN the Event_Editor saves an event, THE Event_Editor SHALL keep all existing date, place and from_place Source_References unchanged unless the user edited that row or answered a prompt of Requirement 6 or 7.
4. WHEN the GEDCOM_Importer reads a SOUR line directly under an event record, THE GEDCOM_Importer SHALL store it as an event-level Source_Reference, independent of whether the event has a date.
5. WHEN the GEDCOM_Exporter writes an event with event-level Source_References, THE GEDCOM_Exporter SHALL write a SOUR line directly under the event record.
6. WHEN the user adds a citation in the Event_Editor without choosing a context, THE Event_Editor SHALL store it as an event-level Source_Reference.
7. THE Dataskydd_Group SHALL contain the acceptance tests `test_event_source_refs_serialize_only_when_non_empty`, `test_event_source_refs_round_trip`, `test_importer_event_level_sour_without_date`, `test_exporter_event_level_sour` and `test_editor_add_citation_defaults_to_event_level`.

### Requirement 13: One shared helper for event citations (M1)

**User Story:** As a maintainer, I want one helper to read event citations, so that no report, count or check forgets a citation location.

#### Acceptance Criteria

1. THE Citation_Helper SHALL provide `event_citations(event)` that returns every Source_Reference of the event, its date, its place and its from_place exactly once, each paired with its Citation_Context.
2. THE Citation_Helper SHALL provide a function that returns the set of source ids cited by an event and a function that tells whether an event cites a given source id.
3. THE following consumers SHALL read event citations only through the Citation_Helper: `reports/kallrapport.py`, `reports/ansedel.py`, `services/source_stats.py` (`event_cited_sources`, `compute_usage_stats`), `ui/dialogs/usage_detail_dialog.py`, the usage list and delete check in `ui/editors/source_editor.py`, `services/validation_service.py`, `gedcom/exporter.py`, `services/comparison_session.py`, the has-source icon logic of the Person_Editor lists, and the merge planner and merge engine source-reference counting.
4. WHEN the user deletes a source that is cited from any Citation_Context of any event, THE Source_Editor SHALL refuse the deletion and SHALL list the citing events.
5. WHEN a unique-source report lists the sources of a person, THE report SHALL list each source id once and SHALL keep every distinct citation context (Citation_Context, quality, note, aspects) under that source.
6. WHEN the Validation_Service finds a Source_Reference with an unknown source id, THE Validation_Service SHALL report the Citation_Context in the message.
7. WHEN the merge planner counts "Källhänvisningar flyttade", THE merge planner SHALL count event-level Source_References.
8. THE test suite SHALL contain a guard test that fails when a module other than the model, the persistence serializer and the Citation_Helper reads `.source_refs` of a Date_Value, a PlaceRef or an Event.
9. THE Dataskydd_Group SHALL contain the acceptance tests `test_event_citations_returns_all_locations_once`, `test_consumers_agree_on_cited_sources`, `test_source_delete_refused_for_every_context`, `test_unique_source_report_keeps_distinct_contexts`, `test_validation_reports_context`, `test_merge_counts_event_level_refs`, `test_comparison_uses_all_citation_contexts` and `test_guard_no_direct_source_refs_reads`.

### Requirement 14: Structured date qualifiers, range endpoints, bounds and original text (M2, D3, OQ5, OQ6)

**User Story:** As a researcher, I want dates to keep their qualifier, range end, calendar and original wording, so that dates export faithfully and later filtering can use them.

#### Acceptance Criteria

1. THE Date_Value SHALL have the fields `qualifier` (default `exact`), `value_to` (default none), `calendar` (default `gregorian`) and `original_text` (default none) in addition to the existing `value`, `precision` and `source_refs`; a `calendar` value `gregorian` means that the date is used as written and is not converted.
2. WHERE the qualifier is `exact`, THE Date_Value SHALL have precision `day`, `month` or `year`, with one exception: a Date_Value read from a file written before format 0.5 may have qualifier `exact` and precision `approximate`.
3. WHERE the qualifier is not `exact`, THE Date_Value SHALL have precision `approximate` for compatibility, and THE Date_Semantics module SHALL derive the granularity of each endpoint from the length of its ISO string and the meaning of the date from the qualifier alone.
4. WHERE the qualifier is `between` or `from_to`, THE Date_Value SHALL have a `value_to` that is a valid ISO partial date not earlier than `value`, in the same calendar.
5. WHERE the qualifier is `unparsed`, THE Date_Value SHALL have an empty `value`, no `value_to` and a non-empty Original_Text.
6. WHEN a Date_Value has qualifier `exact` and precision `approximate`, THE Date_Semantics module SHALL treat its effective qualifier as `about`; WHEN the qualifier is any other value, THE effective qualifier SHALL equal the qualifier whatever the precision is, so that `before 1850` is never read as about 1850.
7. THE persistence serializer SHALL write `qualifier`, `value_to`, `calendar` and `original_text` only when they differ from their defaults.
8. THE Date_Semantics module SHALL provide a function that returns the earliest and latest day a Date_Value can denote, with an open bound for `before`, `after`, `from` and `to`, unknown bounds for `unparsed` and for any Julian endpoint in the Swedish_Calendar_Window, and, for other Julian dates, bounds that contain both the as-written span and the span converted to the proleptic Gregorian calendar.
9. THE Date_Semantics module SHALL provide a function that formats a Date_Value in Swedish (for example "ca 1850", "uppskattat 1850", "beräknat 1850", "tolkat 1850", "före 1850", "efter 1850", "mellan 1850 och 1855", "från 1850 till 1855", "från 1850", "till 1855", and "1700-02-15 (julianskt)" for a Julian date).
10. WHEN a consumer needs the first day or the year of a Date_Value for a derivation (sorting excepted), THE consumer SHALL use the Date_Semantics accessors and SHALL skip every Date_Value that is not exact.
11. THE Dataskydd_Group SHALL contain the acceptance tests `test_date_value_defaults_and_validation`, `test_date_value_serialization_omits_defaults`, `test_legacy_exact_approximate_is_about`, `test_explicit_before_never_about`, `test_date_bounds_per_qualifier`, `test_julian_bounds_conservative`, `test_swedish_window_bounds_unknown`, `test_swedish_date_formatting`, `test_unparsed_validation` and `test_consumers_treat_qualified_dates_as_not_exact`.

### Requirement 15: Real calendar validation (D3, OQ2)

**User Story:** As a researcher, I want impossible dates rejected or stored as text, so that the data never claims a date that did not exist.

#### Acceptance Criteria

1. THE Date_Semantics module SHALL accept a day date only when it is a real date in its calendar.
2. WHERE the calendar is `gregorian`, THE Date_Semantics module SHALL apply the Gregorian leap-year rule (divisible by 4, except centuries not divisible by 400).
3. WHERE the calendar is `julian`, THE Date_Semantics module SHALL apply the Julian leap-year rule (divisible by 4).
4. THE Date_Semantics module SHALL convert a Julian date to the proleptic Gregorian calendar only to compute comparison bounds, and SHALL NOT change the stored `value`.
5. WHEN the Event_Editor or the GEDCOM_Importer receives a date that is not a real date in its calendar, THE Event_Editor SHALL reject it with a Swedish error message and THE GEDCOM_Importer SHALL store an Unparsed_Date.
6. THE Date_Semantics module SHALL NOT convert, shift or reinterpret any date of the Swedish_Calendar_Window and SHALL NOT model the Swedish calendar of 1700 to 1712 or the 1753 switch.
7. THE existing `is_valid_swedish_calendar` check SHALL remain unchanged; it models only the 1753 switch.
8. THE Date_Semantics module SHALL provide its own calendar-aware day validation, because `date_span.is_valid_iso` uses the Gregorian calendar and reports a Julian-only day such as `1700-02-29` as absent.
9. THE Dataskydd_Group SHALL contain the acceptance tests `test_leap_year_rules_gregorian`, `test_leap_year_rules_julian`, `test_julian_to_gregorian_conversion_round_trip`, `test_invalid_day_rejected_in_editor`, `test_invalid_day_unparsed_in_import`, `test_date_validity_property` and `test_swedish_calendar_not_modelled_by_date_semantics`.

### Requirement 16: Uninterpreted dates are visible and preserved (D7)

**User Story:** As a researcher, I want to see when a GEDCOM date was not interpreted and keep it intact, so that I can fix it deliberately.

#### Acceptance Criteria

1. WHEN the Event_Editor loads an event with an Unparsed_Date, THE Event_Editor SHALL show the Original_Text read-only together with the text "Tolkades inte vid import" and a Swedish explanation that the original date is preserved unchanged until the user enters a new date.
2. WHEN the user saves an event with an Unparsed_Date without replacing the date, THE Event_Editor SHALL keep the Date_Value, including Original_Text and Source_References, unchanged.
3. WHEN the user enters a new date for an event with an Unparsed_Date, THE Event_Editor SHALL replace the Date_Value and clear the Original_Text.
4. WHEN the user changes the date of any event whose Date_Value has Original_Text, THE Event_Editor SHALL clear the Original_Text; WHEN the user edits any other field, THE Event_Editor SHALL keep it.
5. WHEN a project with an Unparsed_Date is saved and reopened, THE persistence layer SHALL return an equal Date_Value.
6. THE Dataskydd_Group SHALL contain the acceptance tests `test_unparsed_date_shown_read_only_with_explanation`, `test_unparsed_date_preserved_by_unrelated_edit`, `test_unparsed_date_replaced_only_by_explicit_new_date`, `test_original_text_cleared_when_date_changed` and `test_unparsed_date_save_reopen_round_trip`.

### Requirement 17: One change-marking API (M3)

**User Story:** As a maintainer, I want a single method to mark the project changed, so that no code path forgets the dirty flag or the revision counter.

#### Acceptance Criteria

1. THE Project_Service SHALL provide a public method `mark_changed(reason)` that sets Dirty_State, increments Content_Revision and notifies merge listeners once.
2. WHILE an Edit_Session is active, THE Project_Service SHALL defer `mark_changed` calls made by the session's editors and SHALL apply them as one call at commit.
3. THE application code in `slaktbusken/app.py`, `slaktbusken/services/delete_service.py` and `slaktbusken/ui` SHALL call `mark_changed` instead of assigning `project_service._dirty`.
4. THE Project_Service SHALL provide methods for the mutations that today are done as raw list operations by the Place_Editor (delete place), the Place_Translation_Editor (create places) and the Import_Service (adopt import), each calling `mark_changed` exactly once.
5. THE setter `Project_Service._dirty` SHALL remain only for internal use by the Project_Service.
6. THE Dataskydd_Group SHALL contain the acceptance tests `test_mark_changed_sets_dirty_bumps_revision_notifies_once`, `test_mark_changed_deferred_in_edit_session`, `test_service_methods_for_place_delete_and_create_call_mark_changed_once` and `test_no_external_dirty_assignment`.

### Requirement 18: Change-path coverage and guard (M3)

**User Story:** As a maintainer, I want automated proof that every mutation path marks the project changed exactly when data changed, so that this class of bug cannot return unnoticed.

#### Acceptance Criteria

1. THE test suite SHALL contain a change-path registry that lists every confirmed Mutation_Path and every other known Mutation_Path of the Person_Editor, Event_Editor, Residence_Editor, Place_Editor, Place_Translation_Editor, Source_Editor, GEDCOM import and delete service.
2. FOR EACH Mutation_Path in the registry, THE coverage test SHALL assert that Content_Revision increases by one and Dirty_State is true when the Canonical_Form changed, and that both stay unchanged when it did not.
3. THE coverage test SHALL compute "data changed" from the Canonical_Form before and after the path, not from a flag set by the path.
4. THE test suite SHALL contain a static guard test that parses `slaktbusken/app.py`, `slaktbusken/ui` and `slaktbusken/services` with the `ast` module and fails on an assignment to an attribute `_dirty` whose target object is not `self`.
5. THE static guard test SHALL fail on an `append`, `extend`, `insert`, `remove`, `pop`, `clear`, `del` or slice assignment on a Project_Data collection attribute outside the allow-list `tests/test_dataskydd/change_path_allowlist.py`.
6. THE allow-list SHALL name each permitted module and function, and a reason, and SHALL contain only paths that run inside an Edit_Session, inside a Project_Service method, or inside a Working_Copy.
7. THE Dataskydd_Group SHALL contain the acceptance tests `test_every_registered_path_marks_exactly_when_changed`, `test_change_path_registry_covers_known_paths`, `test_guard_no_external_dirty_assignment` and `test_guard_no_unlisted_collection_mutation`.

### Requirement 19: Durable GEDCOM event identity (M4, D4, OQ1, AP1 and AP5 approved)

**User Story:** As a researcher, I want the importer to recognise events it created earlier, even after I edited them or merged persons, so that updates are safe and repeated imports are stable.

#### Acceptance Criteria

1. THE Event model SHALL have an optional field `origin` of type Event_Origin (the `RecordOrigin` dataclass) and THE persistence serializer SHALL write it only when present.
2. WHEN the GEDCOM_Importer creates an event, THE GEDCOM_Importer SHALL set Event_Origin to the owner kind (`INDI` or `FAM`), the Owner_Id, the owner xref, the tag key (the GEDCOM tag, and for `EVEN` records `EVEN:` plus the normalised TYPE value), the occurrence index among records with the same tag key under that owner, the record hash and the `_UID` of the record if present.
3. THE record hash SHALL be a SHA-256 digest over the canonical form of the event record: the tag line and all descendants, values with whitespace collapsed, `CHAN`, `_UPD`, `_CRE` and `_UID` subtrees excluded, `SOUR` pointers replaced by the resolved source id when known, other pointer values replaced by a fixed token, sibling groups ordered by tag, and the relative order of siblings with the same tag preserved.
4. THE Event_Identity_Matcher SHALL take as candidates only the events whose Event_Origin has the same owner kind and an Owner_Id equal to the id that the GEDCOM_Importer resolved for the owner record in this run, and SHALL ignore `owner_xref` and `index` when matching.
5. WHEN the Event_Identity_Matcher processes the incoming records of one owner, THE Event_Identity_Matcher SHALL apply in this order: `_UID` equality; equal tag key and record hash, paired one to one in file order against candidates ordered by their stored index; equal legacy content fingerprint (Requirement 19.7); otherwise no claim.
6. THE Event_Identity_Matcher SHALL claim each existing event at most once per import run, and SHALL NOT claim an event on the basis of tag and occurrence index, or of event type and place alone.
7. WHERE an existing event of the owner has no Event_Origin (created before format 0.5), THE Event_Identity_Matcher SHALL claim it only when a content fingerprint of type, structured date or Original_Text, place, participants and role, cause of death and custom type name is equal to that of the incoming record, one to one; WHEN such a claim happens, THE GEDCOM_Importer SHALL set Event_Origin on the claimed event, SHALL count the claim as a change of the project (the project becomes dirty), and SHALL report the number of claimed legacy events in the Import_Log with the Swedish text "{n} befintliga händelser kopplades till GEDCOM-posterna och fick ursprungsmärkning." (approval AP1).
8. WHEN the Event_Identity_Matcher claims an event as unchanged, THE GEDCOM_Importer SHALL NOT write anything to that event, including the occurrence index of its Event_Origin.
9. WHEN a person merge is executed, THE merge machinery SHALL leave every Event_Origin unchanged and SHALL keep every event, and THE Person_Reference_Inventory SHALL list `RecordOrigin.owner_id` of an event as the historical location `event.origin` (rule H) that is never rewritten.
10. WHEN a record of a surviving person is imported after a merge, THE Event_Identity_Matcher SHALL consider only events whose Owner_Id equals the surviving person id, and the events of the retired person SHALL stay untouched because the retired person's records are Merged_Identity_Records.
11. WHEN a record is a Merged_Identity_Record or an ambiguous record, THE GEDCOM_Importer SHALL NOT call the Event_Identity_Matcher for it.
12. THE Dataskydd_Group SHALL contain the acceptance tests `test_origin_serialization_round_trip`, `test_origin_set_on_import`, `test_record_hash_ignores_change_tracking_tags`, `test_record_hash_ignores_order_of_distinct_tags`, `test_record_hash_keeps_order_of_repeated_tags`, `test_record_hash_stable_under_source_renumbering`, `test_matcher_order_uid_hash_legacy`, `test_matcher_claims_once`, `test_matcher_never_claims_by_tag_and_index`, `test_matcher_legacy_fingerprint_one_to_one`, `test_matcher_never_matches_on_type_and_place_alone`, `test_matcher_property_no_duplicates_no_merges`, `test_matcher_owner_id_survives_xref_renumbering`, `test_edited_imported_event_not_modified_by_reimport`, `test_merge_preserves_event_origin`, `test_event_origin_in_person_reference_inventory`, `test_reference_rule_event_origin`, `test_record_hash_golden_vectors`, `test_legacy_event_claim_reported_in_import_log`, `test_legacy_event_claim_marks_project_changed`, `test_merged_identity_record_creates_no_events` and `test_survivor_record_matches_only_own_origin_events`.

### Requirement 20: GEDCOM import is all-or-nothing, and the save is crash-consistent and conflict-safe (Additional requirement 3, OQ4, AP2 approved with hash verification)

**User Story:** As a researcher, I want a failed, cancelled or interrupted import to change nothing, a saved import to stay consistent with my translation files, and a save never to overwrite a file that was changed outside Släktbusken, so that future imports never act on mappings that my project does not match and none of my files is silently replaced.

#### Acceptance Criteria

1. WHEN a GEDCOM import starts, THE Import_Service SHALL run the GEDCOM_Importer on a Working_Copy of Project_Data, reading the translation data from the Pending_Translation when one exists and from the Translation_Files otherwise, and, WHEN no Pending_Translation exists, SHALL record the Translation_Base from the bytes of the Translation_Files that it reads and SHALL abort the import with a Swedish message, adopting nothing, when the digests of the Translation_Files differ after the importer finished.
2. WHEN the Import_Service runs the GEDCOM_Importer, THE GEDCOM_Importer SHALL write no Translation_File and SHALL return the Staged_Translation in the import result.
3. WHEN the import succeeds and the Working_Copy differs from Project_Data in Canonical_Form or the Staged_Translation differs from the effective translation data, THE Import_Service SHALL adopt the Working_Copy into the existing Project_Data instance, SHALL store the Staged_Translation with its Translation_Base as Pending_Translation and SHALL call the Change_Marker once.
4. WHEN the import succeeds and neither differs, THE Import_Service SHALL adopt nothing and SHALL leave Dirty_State, Content_Revision and Pending_Translation unchanged.
5. IF the import fails with an error or is cancelled by the user, THEN THE Import_Service SHALL leave Project_Data, the Pending_Translation and the Translation_Files unchanged, byte for byte.
6. WHEN the user saves the project and a Pending_Translation exists, THE Project_Service SHALL encode the project once and perform in this order: Digest_Verification of the project file and the Translation_Files (criterion 7), write the Translation_Intent durably, replace the project file, replace each changed Translation_File, remove the Translation_Intent.
7. WHEN the user saves the project and a Pending_Translation exists, THE Project_Service SHALL, before it writes any file, accept the project file only in state OLD (digest equal to the Disk_Digest) and SHALL accept each Translation_File only in state OLD (digest equal to its digest in the Translation_Base) or in state NEW (digest equal to the digest of the content that this save would write).
8. IF Digest_Verification before the first write finds a file in state OTHER, THEN THE Project_Service SHALL refuse the save before it writes any file, SHALL create no Translation_Intent and no temporary file, SHALL leave the project file, the Translation_Files, the Pending_Translation, Dirty_State and Content_Revision unchanged, and SHALL show a Swedish message that names each file in state OTHER, states that the file was changed outside Släktbusken, and tells the user to restore the file and save again, or to close the project without saving and repeat the import.
9. IF writing the Translation_Intent or replacing the project file fails with an error, THEN THE Project_Service SHALL remove the Translation_Intent and its temporary files, SHALL leave the project file and the Translation_Files unchanged, SHALL keep Dirty_State and the Pending_Translation, and SHALL show a Swedish error message.
10. IF the Digest_Verification that the Project_Service repeats immediately before it replaces the project file finds the project file or a Translation_File in state OTHER, THEN THE Project_Service SHALL replace no file, SHALL remove only the Translation_Intent and the temporary files that this save created (nothing has been replaced yet), SHALL leave the Pending_Translation, Dirty_State and Content_Revision unchanged, and SHALL show the Swedish message of criterion 8.
11. WHEN the Project_Service is about to replace a Translation_File after it replaced the project file, THE Project_Service SHALL repeat Digest_Verification for that file immediately before the replace, SHALL skip a file that is already in state NEW, and, IF the file is in state OTHER, THEN SHALL NOT replace it, SHALL keep the Translation_Intent and its temporary files, SHALL enter Import_Save_Unfinished and SHALL show a Swedish message that names the file and its state.
12. WHILE a Pending_Translation exists, THE Place_Translation_Editor and the Source_Translation_Editor SHALL refuse to open with the message "Spara projektet innan du redigerar översättningarna. En import väntar på att sparas.".
13. IF the Editor_Registry reports an editor with unsaved changes or an Edit_Session is active, THEN THE Import_Service SHALL refuse the import with a Swedish message that names the editor by its `editor_title`.
14. WHEN the project is closed or another project is opened without saving, THE Project_Service SHALL discard the Pending_Translation and its Translation_Base, so that the Translation_Files stay in the state that matches the saved project.
15. WHEN a second import runs before the first one was saved, THE Import_Service SHALL start from the Pending_Translation and SHALL keep its Translation_Base, so that the mappings of both imports reach the Translation_Files together.
16. WHEN a project is opened and a Translation_Intent exists, THE Project_Service SHALL perform Digest_Verification of the project file (OLD and NEW digests from the intent) and of every Translation_File named in the intent before it writes anything, and SHALL decide: (a) project file NEW and every Translation_File OLD or NEW: write each Translation_File that is OLD from the content in the intent, remove the intent and its temporary files, and report "En avbruten sparning slutfördes."; (b) project file OLD and every Translation_File OLD: remove the intent and its temporary files, leave the Translation_Files unchanged, and report "En avbruten sparning återställdes."; (c) every other combination, including a file in state OTHER, a missing project file, a project file OLD with a Translation_File NEW, and an intent that cannot be read, has a wrong checksum or has an unknown schema: Conflict_Refusal.
17. WHEN a Conflict_Refusal occurs at open, THE Project_Service SHALL NOT open the project, SHALL change no file (including files in state OLD), SHALL keep the Translation_Intent and its temporary files, and SHALL refuse every normal save of that project path until Släktbusken is restarted, in the same way as after a refused merge recovery.
18. WHEN a Conflict_Refusal occurs at open, THE application SHALL show the message through the existing recovery-refusal dialog, and the Swedish message SHALL name the project file, the Translation_Intent and each file together with its state ("oförändrad", "ny" or "okänd, ändrad utanför Släktbusken"), and SHALL tell the user to restore the named files from a backup or from the version history, or, after checking the files, to move the Translation_Intent out of the project folder, and then to restart Släktbusken.
19. WHILE Import_Save_Unfinished holds, THE Project_Service SHALL refuse to save and to import with the message "En sparning av en import är inte avslutad. Starta om Släktbusken för att slutföra eller kontrollera filerna.", and THE translation editors SHALL refuse to open with the same message.
20. IF an error (not a conflict) occurs after the project file was replaced, THEN THE Project_Service SHALL enter Import_Save_Unfinished, keep the Translation_Intent, mark the project as saved, and show the message "Projektet är sparat. Översättningsfilerna slutförs när projektet öppnas nästa gång.".
21. WHEN a recovery at open is interrupted by an error or a crash, THE next open SHALL reach one of the decisions of criterion 16, THE recovery SHALL write each Translation_File through a temporary file and a replace after Digest_Verification, and THE recovery SHALL remove the Translation_Intent only after every Translation_File is in state NEW.
22. THE Dataskydd_Group SHALL contain the acceptance tests `test_failed_import_leaves_project_unchanged`, `test_failed_import_leaves_translation_files_byte_identical`, `test_cancelled_import_leaves_project_unchanged`, `test_import_writes_no_translation_file_before_save`, `test_successful_import_adopts_once`, `test_noop_import_adopts_nothing`, `test_import_refused_with_unsaved_editor`, `test_import_records_translation_base`, `test_save_writes_intent_project_translation_in_order`, `test_save_failure_before_project_replace_restores_state`, `test_save_fault_before_intent`, `test_save_fault_after_intent`, `test_save_fault_after_project_write`, `test_save_fault_after_each_translation_write`, `test_save_fault_before_intent_removal`, `test_save_fault_at_every_fs_call_as_exception`, `test_save_fault_at_every_fs_call_as_crash`, `test_crash_at_every_save_step_recovers_consistently`, `test_recovery_fault_at_every_fs_call`, `test_recovery_is_idempotent_after_crash`, `test_open_completes_translation_when_project_is_new`, `test_open_discards_intent_when_project_is_old`, `test_translation_file_changed_between_import_and_save_refuses_save`, `test_translation_file_already_new_is_accepted_at_save`, `test_translation_file_changed_before_commit_point_removes_own_artifacts`, `test_translation_file_changed_after_commit_point_preserves_intent`, `test_project_file_changed_between_open_and_save_refuses_save`, `test_project_file_changed_before_commit_point_removes_own_artifacts`, `test_translation_file_changed_during_import_aborts_import`, `test_translation_file_changed_before_recovery_refuses_open`, `test_project_file_changed_before_recovery_refuses_open`, `test_project_file_missing_before_recovery_refuses_open`, `test_damaged_intent_refuses_open_and_is_kept_byte_identical`, `test_conflict_messages_name_files_and_state_in_swedish`, `test_conflict_refusal_blocks_normal_save`, `test_conflict_refusal_changes_no_file`, `test_unfinished_import_save_blocks_save_import_and_translation_editors`, `test_close_without_save_discards_pending_translation`, `test_second_import_uses_pending_translation`, `test_translation_editors_refuse_while_pending` and `test_unsaved_import_then_new_person_never_aliases_mapping`.

### Requirement 21: Project format 0.5 and safe migration (D5)

**User Story:** As a researcher, I want old project files to open without loss, so that upgrading never destroys my work.

#### Acceptance Criteria

1. THE Migration_Manager and `file_io.CURRENT_VERSION` SHALL both have the value "0.5".
2. THE Migration_Manager SHALL register a migration from "0.4" to "0.5" that sets `format_version` and `version` to "0.5" and changes no other key.
3. WHEN a project file with a version below "0.5" is opened, THE file loader SHALL create the backup file `<stem>_v<old_version><suffixes>` before it migrates, as it does for earlier versions.
4. WHEN a project file with version "0.4" is opened and saved, THE persistence layer SHALL keep every event, date, place, residence and citation value equal and SHALL write no new key (`origin`, `origins`, `source_refs` of an event, `qualifier`, `value_to`, `calendar`, `original_text`) for an entity that has no new field set.
5. THE migration SHALL NOT correct, reinterpret or delete any data of a project file only because the file is opened.
6. IF a project file has a version above "0.5", THEN THE file loader SHALL refuse to open it with the existing Swedish message.
7. THE Dataskydd_Group SHALL contain the acceptance tests `test_migration_0_4_to_0_5_only_changes_version`, `test_migration_creates_backup`, `test_migration_is_idempotent`, `test_v0_4_fixture_opens_and_round_trips`, `test_v0_4_residences_round_trip_without_origins`, `test_newer_version_refused` and `test_old_precision_approximate_not_rewritten_on_open`.

### Requirement 22: Durable GEDCOM residence identity (M5, AP4 changed: included in this package)

**User Story:** As a researcher, I want repeated GEDCOM imports to leave my residences as they are, so that no residence is duplicated, my edits to imported residences survive, and no residence is merged with another only because their dates and places agree.

#### Acceptance Criteria

1. THE ResidenceFact model SHALL have a field `origins` that holds a list of Residence_Origin and defaults to an empty list, and THE persistence serializer SHALL write `origins` only when the list is non-empty.
2. WHEN the GEDCOM_Importer creates a ResidenceFact from a `RESI` record, THE GEDCOM_Importer SHALL set `origins` to one Residence_Origin with owner kind `INDI`, the Owner_Id of the person, the owner xref, the tag key `RESI`, the occurrence index among the `RESI` records of that person, the record hash and the `_UID` of the record if present.
3. THE record hash of a `RESI` record SHALL be computed with the canonical-form rules of Requirement 19.3 over the `RESI` record, so that its DATE, its PLAC (including `_ADPL` and `MAP` children), its SOUR pointers (replaced by the resolved source id) and every other child take part.
4. THE Residence_Identity_Matcher SHALL take as candidates only the pairs of a ResidenceFact and one of its Residence_Origins whose owner kind is `INDI` and whose Owner_Id equals the person id that the GEDCOM_Importer resolved for the owner record in this run, and SHALL ignore `owner_xref` and `index` when matching.
5. WHEN the Residence_Identity_Matcher processes the `RESI` records of one person, THE Residence_Identity_Matcher SHALL apply in this order: `_UID` equality; equal tag key and record hash, paired one to one in file order against candidates ordered by their stored index; equal legacy content fingerprint (criterion 6); otherwise no claim, and SHALL claim each (ResidenceFact, Residence_Origin) pair at most once per import run.
6. WHERE a ResidenceFact of the person has an empty `origins` list, THE Residence_Identity_Matcher SHALL claim it for an incoming `RESI` record only when its content equals the content that the GEDCOM_Importer would create from that record, one to one, compared over person id, place id, the `start` and `end` Endpoints (earliest, latest, event id and note; the descriptive `precision` is excluded), role in household, notes and every Observation (source id, quality, observed years, page note); WHEN such a claim happens, THE GEDCOM_Importer SHALL set `origins` on the claimed ResidenceFact to the Residence_Origin of the incoming record, SHALL count the claim as a change of the project, and SHALL report the number of claimed legacy residences in the Import_Log with the Swedish text "{n} befintliga boenden kopplades till GEDCOM-posterna och fick ursprungsmärkning." (the rule is the same as for legacy events in Requirement 19.7).
7. WHEN the Residence_Identity_Matcher claims a residence as unchanged, THE GEDCOM_Importer SHALL write nothing to the residence (including the occurrence index of its Residence_Origin), SHALL resolve no place for the record, SHALL create no place, SHALL add no place mapping, SHALL apply no coordinates and SHALL issue no id.
8. IF an incoming `RESI` record has no `_UID` match, no equal record hash and no legacy claim, THEN THE GEDCOM_Importer SHALL create a new ResidenceFact with its Residence_Origin, SHALL leave every existing residence unchanged and, WHERE unclaimed residences of the same person exist, SHALL add a Swedish notice to the Import_Log that names the new residence, at most five of those candidates and the number of further candidates.
9. IF an incoming `RESI` record has a `_UID` equal to the uid of an existing Residence_Origin of the person but a different record hash, THEN THE GEDCOM_Importer SHALL leave the residence unchanged and SHALL add a Swedish notice to the Import_Log.
10. WHEN a GEDCOM file with `RESI` records is imported again into a project in which no imported residence was deleted and no `RESI` record changed, THE GEDCOM_Importer SHALL create no residence, SHALL modify no residence, and SHALL leave the Canonical_Form of the project unchanged.
11. WHEN the `RESI` records of one person are reordered in the GEDCOM file with unchanged content, THE GEDCOM_Importer SHALL create no residence and SHALL modify no residence.
12. WHEN one `RESI` record is inserted into the records of a person, THE GEDCOM_Importer SHALL create exactly one residence for the inserted record and SHALL leave every other residence unchanged.
13. WHEN a `RESI` record is removed from the GEDCOM file, THE GEDCOM_Importer SHALL keep the corresponding residence unchanged.
14. WHEN a person has k identical incoming `RESI` records and m existing residences with that record hash, THE GEDCOM_Importer SHALL treat min(k, m) of them as unchanged and SHALL create max(k - m, 0) new residences.
15. WHEN the user edited an imported residence in the application (place, dates, role, notes, Observations or Endpoint links) and its `RESI` record is unchanged, THE GEDCOM_Importer SHALL leave the residence unchanged and SHALL create no residence.
16. WHEN the importer claims a legacy residence and other unclaimed legacy residences of the same person have content equal to it, THE GEDCOM_Importer SHALL leave them unchanged and SHALL add a Swedish notice that names the person and the number of identical residences left unchanged, with the text "{n} identiska boenden för {person} lämnades orörda. De kan vara dubbletter från tidigare importer.".
17. WHEN the user deleted an imported residence and the same `RESI` record is imported again, THE GEDCOM_Importer SHALL create the residence again (known limitation 2).
18. WHEN the GEDCOM_Importer creates a ResidenceFact from a `RESI` record with SOUR lines, THE GEDCOM_Importer SHALL derive one Observation for each SOUR line whose pointer resolves to a known source, with quality `secondary` and no observed years, as it does today.
19. IF the SOUR lines of a `RESI` record resolve to different source ids than before, THEN the record hash SHALL differ and criterion 8 SHALL apply, and WHEN the user edited the Observations of an imported residence and the record is unchanged, THE GEDCOM_Importer SHALL leave those Observations unchanged.
20. WHEN a record is a Merged_Identity_Record or an ambiguous record, THE GEDCOM_Importer SHALL create no residence and modify no residence for it.
21. WHEN a person merge is executed, THE merge machinery SHALL keep every Residence_Origin unchanged, and WHEN a record of the surviving person is imported afterwards, THE Residence_Identity_Matcher SHALL consider only residences whose Residence_Origin has the survivor as Owner_Id and, as legacy candidates, residences without origin of the survivor.
22. THE Residence_Editor, the residence edit operations (observation attach, exact start, exact end, observation removal, split and merge) and the Person_Editor residence dialog SHALL preserve `origins`: an operation that keeps the residence id keeps `origins` unchanged, a split gives both resulting residences a copy of the `origins`, and a merge gives the merged residence the `origins` of both residences, earlier residence first, without duplicates.
23. THE GEDCOM_Importer SHALL create no flytt event, SHALL set no `Endpoint.event_id` and SHALL clear no `Endpoint.event_id` on behalf of a `RESI` record.
24. WHEN an existing residence is linked to a flytt event through `Endpoint.event_id` and the residence is claimed, unchanged or left unclaimed by an import, THE GEDCOM_Importer SHALL leave the link and the flytt event unchanged; flytt events that the importer creates from `EVEN` records with TYPE Flytt follow Requirement 19.
25. THE GEDCOM_Importer SHALL NOT merge, combine, delete, reorder or modify any existing ResidenceFact during update import, with one exception: adding a Residence_Origin to a legacy residence under criterion 6.
26. THE Person_Reference_Inventory SHALL list `RecordOrigin.owner_id` of a residence as the historical location `residence.origins` (rule H) that is never rewritten.
27. THE Dataskydd_Group SHALL contain the acceptance tests `test_residence_origins_serialize_only_when_non_empty`, `test_residence_origins_round_trip`, `test_residence_origin_set_on_import`, `test_residence_record_hash_ignores_change_tracking_tags`, `test_residence_record_hash_resolves_source_pointers`, `test_residence_record_hash_sensitive_to_date_place_and_sources`, `test_residence_matcher_claims_pair_once`, `test_residence_matcher_never_matches_on_date_and_place_alone`, `test_residence_matcher_never_claims_by_tag_and_index`, `test_residence_matcher_owner_id_survives_xref_renumbering`, `test_residence_unchanged_writes_nothing_and_resolves_no_place`, `test_reimport_resi_file_creates_no_residences`, `test_reimport_resi_reordered_creates_none`, `test_reimport_resi_inserted_record_creates_one`, `test_reimport_resi_removed_record_keeps_residence`, `test_reimport_resi_identical_records_pair_by_count`, `test_reimport_resi_changed_record_creates_new_with_notice`, `test_reimport_resi_uid_changed_record_reports_without_modifying`, `test_reimport_after_user_edit_leaves_residence_unchanged`, `test_reimport_after_user_edited_observations_leaves_residence_unchanged`, `test_reimport_resi_sour_change_creates_new_residence`, `test_legacy_residence_exact_match_is_claimed_once`, `test_legacy_residence_with_different_content_is_not_claimed`, `test_legacy_residence_same_date_and_place_but_different_role_is_not_claimed`, `test_legacy_duplicates_are_kept_and_reported`, `test_legacy_claim_reported_in_import_log`, `test_legacy_claim_marks_project_changed`, `test_deleted_imported_residence_reappears_known_limitation`, `test_reimport_resi_merged_identity_record_creates_none`, `test_reimport_resi_after_person_merge_considers_only_survivor_origins`, `test_residence_merge_origin`, `test_residence_origins_survive_every_edit_operation`, `test_residence_editor_save_keeps_origins`, `test_residence_split_gives_both_halves_the_origins`, `test_residence_merge_combines_origins`, `test_guard_residence_construction_preserves_origins`, `test_import_creates_no_flytt_event_from_residence`, `test_reimport_keeps_flytt_links_between_residences`, `test_reimport_keeps_flytt_event_count_with_resi`, `test_flytt_event_edited_in_app_not_duplicated_by_reimport`, `test_no_residence_is_merged_or_removed_by_import`, `test_reference_rule_residence_origins`, `test_residence_origin_in_person_reference_inventory`, `test_edit_session_restores_residence_origins`, `test_reimport_is_idempotent_with_resi_property` and `test_residence_save_reopen_reimport_creates_none`.

## Part C: Mandatory test group

### Requirement 23: Mandatory test group "Dataskydd" (D6)

**User Story:** As a maintainer, I want all data-protection tests in a mandatory group, so that none can be skipped or removed unnoticed.

#### Acceptance Criteria

1. THE file `tests/mandatory_groups.py` SHALL contain a new `MandatoryGroup` with key `data_protection`, Swedish title "Dataskydd" and the modules and required tests named in Requirements 1 to 22; this spec explicitly authorises the change to the file that an earlier spec froze.
2. THE Dataskydd_Group SHALL contain every acceptance test named in Requirements 1 to 22 as a required test.
3. THE Dataskydd_Group SHALL contain no test marked `skip`, `skipif`, `xfail` or optional.
4. WHEN the guard test `tests/test_meta/test_mandatory_groups_guard.py` runs, THE guard test SHALL verify that every required test of the Dataskydd_Group exists and is collected.
5. WHEN `scripts/run_mandatory_tests.py` runs, THE runner SHALL run the Dataskydd_Group together with the existing groups and SHALL report it under the title "Dataskydd".
6. THE tasks of this spec that implement a confirmed bug fix and its acceptance tests SHALL NOT be marked optional.
7. THE Dataskydd_Group SHALL contain the acceptance test `test_dataskydd_group_registered_and_complete`.
