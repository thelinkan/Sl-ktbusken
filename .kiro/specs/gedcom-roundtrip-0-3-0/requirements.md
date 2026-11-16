# Requirements Document

## Introduction

This spec fixes data loss in the GEDCOM 5.5.1 export and in the export-then-import round trip of Släktbusken (release 0.3.0, branch Features0.3.0). It follows the spec `data-integrity-0-3-0`, whose record identity (Event_Origin, Residence origins, Origin_Group), import atomicity and import-abort rules stay in force.

The findings come from a comparison by the user of `MergeTest.json` (original project), its GEDCOM export (`exporttest.ged`) and the project imported from that file (`exporttest.json`). The three files are not yet in the repository. They are to be added under `tests/fixtures/gedcom_roundtrip/`.

Confirmed losses:

1. One of six marriage events is not exported, because the Exporter writes family events only from `Family.event_ids`.
2. Person notes and titles are not exported.
3. Name types are lost, and the Importer assigns them by position.
4. HUSB and WIFE follow the partner list order, and partner roles collapse to husband and wife on import.
5. Date-level citations return as event-level citations with quality "secondary" and no aspects, and the Exporter writes source text as `3 TEXT` under the citation.
6. Residences lose observation periods, observation quality, `start.earliest`, `end.latest`, exact endpoints and endpoint event links.
7. Media, repositories, provider, source type, structured reference value types and place type are lost or changed.

Package 2 (advanced person filtering) is out of scope. No requirement here touches filtering. Releases of Släktbusken keep reading old project files and old GEDCOM files.

## Glossary

- **GEDCOM_Exporter**: The class `GEDCOMExporter` in `slaktbusken/gedcom/exporter.py`, called by `ExportService.run`.
- **GEDCOM_Importer**: The class `GEDCOMImporter` in `slaktbusken/gedcom/importer.py`.
- **Project_Data**: The in-memory `ProjectData` of a Släktbusken project.
- **SLK_Tag**: A GEDCOM custom tag whose name starts with `_SLK_`. Every SLK_Tag is listed in the Tag_Registry.
- **Tag_Registry**: The table in design.md that lists, for every SLK_Tag, its parent tag, value, meaning and standard fallback.
- **SLK_Marker**: The HEAD line `1 _SLK_VERS 1`, written by the GEDCOM_Exporter, which states that the file follows the Tag_Registry.
- **Family_Event_Type**: One of `marriage`, `divorce`, `engagement`, `divorce_filed` and `custom_family_event`.
- **Orphan_Family_Event**: An Event of a Family_Event_Type that is listed in no `Family.event_ids`.
- **Individual_Fallback**: The representation of an Orphan_Family_Event as one `1 EVEN` structure with the SLK_Tags `_SLK_EVTYPE` and `_SLK_EID` on the INDI record of each participant.
- **Event_Token**: The value of `_SLK_EID`, a text token that names one Event inside one GEDCOM file.
- **Citation_Context**: One of `event`, `date`, `place` and `from_place`, as defined by `CitationContext` in `slaktbusken/model/event_citations.py`.
- **Hash_Profile**: The rule set that `record_hash` in `slaktbusken/gedcom/translation/record_identity.py` uses to build the canonical form. `legacy` is the current rule set. `slk1` is the rule set for files that carry the SLK_Marker.
- **Export_Log**: The list `ExportResult.warnings` and the map `ExportResult.omitted_elements`, shown to the user after an export.
- **Stable_View**: A representation of Project_Data that contains genealogical content and no generated ids, used to compare two projects.
- **Difference_Class**: One of A (missing from the GEDCOM output), B (present in the GEDCOM but lost or changed by the GEDCOM_Importer), C (not representable in GEDCOM 5.5.1 without extensions) and D (Släktbusken-only data that is not to be exported).
- **Fixture_Set**: The files `MergeTest.json`, `exporttest.ged` and `exporttest.json` under `tests/fixtures/gedcom_roundtrip/`.
- **Roundtrip_Group**: The new mandatory test group "GEDCOM-rundresa" in `tests/mandatory_groups.py`.
- **Dataskydd_Group**: The existing mandatory test group "Dataskydd".
- **Round_Trip**: Export of Project_Data to a GEDCOM file and import of that file into an empty project.

## Requirements

### Requirement 1: Every family event is exported exactly once

**User Story:** As a researcher, I want every marriage in my project to appear in the GEDCOM file, so that no marriage disappears when I move data between programs.

#### Acceptance Criteria

1. THE GEDCOM_Exporter SHALL write each Event of a Family_Event_Type exactly once per export.
2. WHEN an Event of a Family_Event_Type is listed in `Family.event_ids` of one or more families, THE GEDCOM_Exporter SHALL write the Event in the first such family in project order.
3. WHEN an Orphan_Family_Event has a participant person-id set that equals the partner person-id set of exactly one family, THE GEDCOM_Exporter SHALL write the Event in that family.
4. IF an Orphan_Family_Event matches no family or more than one family, THEN THE GEDCOM_Exporter SHALL write the Event as an Individual_Fallback and SHALL add an Export_Log warning that names the event type, the date and the participants.
5. THE GEDCOM_Exporter SHALL leave Project_Data unchanged and SHALL create no family record that has no counterpart in Project_Data.
6. WHEN the GEDCOM_Importer reads a family event that carries `_SLK_PART` entries, THE GEDCOM_Importer SHALL create the Event with the participants and roles of those entries.
7. WHEN the GEDCOM_Importer reads a family event without `_SLK_PART` entries, THE GEDCOM_Importer SHALL create the Event with the participants and the role "spouse" as before.
8. WHEN the GEDCOM_Importer reads `1 EVEN` structures with `_SLK_EVTYPE` and the same Event_Token on several INDI records of one file, THE GEDCOM_Importer SHALL create one Event that has one participant per INDI record.

### Requirement 2: Person notes and titles are exported and imported

**User Story:** As a researcher, I want person notes and titles to survive an export, so that my commentary is not lost.

#### Acceptance Criteria

1. WHEN `Person.notes` is not empty, THE GEDCOM_Exporter SHALL write `1 NOTE` on the INDI record, with one `CONT` line per line break and `CONC` lines so that no output line is longer than 255 characters.
2. WHEN `Person.title` is not empty, THE GEDCOM_Exporter SHALL write `1 TITL` on the INDI record, and WHEN `Person.occupation` is not empty, THE GEDCOM_Exporter SHALL write `1 OCCU`.
3. THE GEDCOM_Exporter SHALL write a text value that starts with `@` with a doubled leading `@`, and THE GEDCOM_Importer SHALL read a doubled leading `@` in a text value as one `@`.
4. THE GEDCOM_Importer SHALL read `TITL` on an INDI record as `Person.title` and SHALL read `TITL` on a SOUR record as `Source.title`.
5. FOR ALL notes, titles and residence notes, exporting then importing SHALL produce a text equal to the original, including line breaks, leading and trailing spaces inside lines, `@` and non-ASCII characters (round-trip property).
6. WHEN the GEDCOM_Exporter writes `ResidenceFact.notes`, `ResidenceFact.role_in_household` or any other free text that may contain line breaks, THE GEDCOM_Exporter SHALL write the text with the same CONT and CONC rule as criterion 1.

### Requirement 3: Name types are exported and imported

**User Story:** As a researcher, I want married names to stay married names, so that name history stays correct after a round trip.

#### Acceptance Criteria

1. THE GEDCOM_Exporter SHALL write `2 TYPE` under every `1 NAME`, with the mapping `birth` to `birth`, `married` to `married`, `alias` to `aka`, `adopted` to `adopted` and `other` to `other`.
2. WHEN a `NAME` record has a `TYPE` of `birth` or `maiden`, THE GEDCOM_Importer SHALL create a Name of type `birth`.
3. WHEN a `NAME` record has a `TYPE` of `married`, `aka`, `adopted` or `other`, THE GEDCOM_Importer SHALL create a Name of type `married`, `alias`, `adopted` or `other` respectively.
4. WHEN a `NAME` record has a `TYPE` that is not in criteria 2 and 3, THE GEDCOM_Importer SHALL create a Name of type `other`.
5. WHILE no `NAME` record of an INDI record has a `TYPE`, THE GEDCOM_Importer SHALL apply the existing positional rule (first name `birth`, later names `other`).
6. WHILE at least one `NAME` record of an INDI record has a `TYPE`, THE GEDCOM_Importer SHALL assign the type `other` to a `NAME` record without `TYPE` and SHALL NOT infer a type from the position.
7. WHEN the GEDCOM_Importer updates an existing person from a file in which no `NAME` record has a `TYPE`, THE GEDCOM_Importer SHALL keep the type of each existing Name that has the same given name and surname as an incoming name.
8. WHEN a Name has `event_id`, THE GEDCOM_Exporter SHALL write `3 _SLK_EREF` with the Event_Token of that Event under the `NAME` record, and THE GEDCOM_Importer SHALL restore `Name.event_id` once all events of the file exist.
9. IF an Event_Token under a `NAME` record resolves to no Event of the import, THEN THE GEDCOM_Importer SHALL leave `Name.event_id` empty and SHALL add a warning to the Import_Log.

### Requirement 4: Partners keep sex-based slots, roles and order

**User Story:** As a researcher, I want husband and wife slots to follow the persons' sex, and partner roles to survive, so that families look the same after a round trip.

#### Acceptance Criteria

1. WHEN a family has two partners whose sex is `M` and `F`, THE GEDCOM_Exporter SHALL write the partner of sex `M` as HUSB and the partner of sex `F` as WIFE, regardless of role and list order.
2. WHEN a family has one partner of sex `M` or `F` and one partner of another sex, THE GEDCOM_Exporter SHALL write the partner of known sex in the slot that matches the sex and the other partner in the free slot.
3. WHEN a family has partners whose sex does not decide the slots (same sex, or sex `U` or `X`), THE GEDCOM_Exporter SHALL fill HUSB and then WIFE in partner list order, and SHALL never write two HUSB lines or two WIFE lines in one family.
4. WHEN a family has at least one partner, THE GEDCOM_Exporter SHALL write one `1 _SLK_PARTNER <xref>` entry per partner in partner list order, each with `2 _SLK_ROLE` holding the stored role text.
5. WHEN a FAM record has `_SLK_PARTNER` entries that reference exactly the persons given by HUSB and WIFE, THE GEDCOM_Importer SHALL create the partners in the order of the `_SLK_PARTNER` entries with the stored roles.
6. WHEN a FAM record has no `_SLK_PARTNER` entries, THE GEDCOM_Importer SHALL create the partners with the roles `husband` and `wife` as before.
7. IF the `_SLK_PARTNER` entries of a FAM record do not reference exactly the persons given by HUSB and WIFE, THEN THE GEDCOM_Importer SHALL ignore the entries and SHALL add a warning to the Import_Log.
8. WHEN `Person.sex` is `X`, THE GEDCOM_Exporter SHALL write `1 SEX U` and `2 _SLK_SEX X`, and WHEN `_SLK_SEX X` is present, THE GEDCOM_Importer SHALL set the sex to `X`.
9. WHEN `Person.sex` is `U`, THE GEDCOM_Exporter SHALL write `1 SEX U`.
10. WHEN the GEDCOM_Importer updates an existing family and the incoming partner person set equals the existing partner person set, THE GEDCOM_Importer SHALL keep the roles of the existing partners.

### Requirement 5: Parentage types and foster families round-trip

**User Story:** As a researcher, I want foster, adoptive, step and other parentage to survive an export, so that complex families are not turned into biological ones.

#### Acceptance Criteria

1. THE GEDCOM_Exporter SHALL keep the existing output for foster and adoptive parentage: `2 PEDI foster` and `2 PEDI adopted` under `FAMC`, `1 EVEN` with `2 TYPE Fosterhem` and `2 FAMC`, and `1 ADOP` with `2 FAMC`.
2. WHEN a family has a ParentChildLink with a parentage type other than `biological`, THE GEDCOM_Exporter SHALL write `2 _SLK_PLINK <parent xref>` with `3 TYPE <parentage_type>` under the `FAMC` of the child, one entry per link in link order.
3. WHEN a ParentChildLink has no parent, THE GEDCOM_Exporter SHALL write `2 _SLK_PLINK` without a value and with the same `3 TYPE`.
4. WHEN a `FAMC` record has `_SLK_PLINK` entries, THE GEDCOM_Importer SHALL create one ParentChildLink per entry with the stored parentage type and SHALL NOT apply the `PEDI` value to the parents covered by an entry.
5. WHEN a `FAMC` record has no `_SLK_PLINK` entry, THE GEDCOM_Importer SHALL derive the parentage type from `PEDI` as before.
6. THE GEDCOM_Importer SHALL create the same foster and adoptive families, placement events and paired end events from a file written before this spec as before this spec.

### Requirement 6: Citation semantics survive the round trip

**User Story:** As a researcher, I want a citation to keep its context, quality, note and aspects, so that my evidence assessment is not rewritten by an export.

#### Acceptance Criteria

1. WHEN the GEDCOM_Exporter writes a SourceRef, THE GEDCOM_Exporter SHALL write `3 QUAY` with the value 3 for `primary`, 2 for `secondary` and 1 for `tertiary`, and `3 _SLK_QUAL <text>` for any other quality text.
2. WHEN the SourceRef has a context other than `event`, THE GEDCOM_Exporter SHALL write `3 _SLK_CTX` with the value `date`, `place` or `from_place`.
3. WHEN the SourceRef has a note, THE GEDCOM_Exporter SHALL write `3 NOTE` with the note text under the citation of an event.
4. WHEN the SourceRef has aspects, THE GEDCOM_Exporter SHALL write one `3 _SLK_ASP` per aspect, in order.
5. THE GEDCOM_Exporter SHALL keep writing `3 TEXT` with the citation text under the citation of an event, until a migration of stored record hashes exists (design decision OQ-6).
6. WHEN the GEDCOM_Importer reads a citation, THE GEDCOM_Importer SHALL set the quality from `_SLK_QUAL`, else from `QUAY` (3 to `primary`, 2 to `secondary`, 1 and 0 to `tertiary`), else to `secondary`.
7. WHEN the GEDCOM_Importer reads a citation with `_SLK_CTX date` and the event has a date, THE GEDCOM_Importer SHALL store the SourceRef in `DateValue.source_refs`, and WHEN the event has no date, THE GEDCOM_Importer SHALL store the SourceRef at event level.
8. WHEN the GEDCOM_Importer reads a citation with `_SLK_CTX place` and the event has a place, THE GEDCOM_Importer SHALL store the SourceRef in `PlaceRef.source_refs`, and WHEN the event has no place, THE GEDCOM_Importer SHALL store the SourceRef at event level.
9. WHEN the GEDCOM_Importer reads a citation with `_SLK_CTX from_place` and the event has a `from_place`, THE GEDCOM_Importer SHALL store the SourceRef in the `source_refs` of `from_place`, and WHEN the event has none, THE GEDCOM_Importer SHALL store the SourceRef at event level.
10. WHEN the GEDCOM_Importer reads a citation with `NOTE` and `_SLK_ASP` children, THE GEDCOM_Importer SHALL store the note and the aspects in the SourceRef.
11. WHEN the GEDCOM_Exporter writes a flytt event with a `from_place`, THE GEDCOM_Exporter SHALL write `2 _SLK_FROMPLAC` with the place hierarchy text, and WHEN the GEDCOM_Importer reads `_SLK_FROMPLAC`, THE GEDCOM_Importer SHALL resolve it to `Event.from_place` with the same place resolution as `PLAC`.
12. THE GEDCOM_Exporter SHALL write `3 _SLK_CTX from_place` citations for a flytt event and SHALL no longer skip them.

### Requirement 7: Residences round-trip with structured data

**User Story:** As a researcher, I want residence periods, observations and links to events to survive an export, so that my residence research is not reduced to a rough date.

#### Acceptance Criteria

1. WHEN a ResidenceFact is exported, THE GEDCOM_Exporter SHALL write `2 _SLK_START` and `2 _SLK_END`, each with the children `3 _SLK_EARLIEST`, `3 _SLK_LATEST`, `3 _SLK_PREC`, `3 _SLK_EREF` and `3 _SLK_NOTE` for the values that are present.
2. THE GEDCOM_Exporter SHALL keep writing the existing `DATE`, `PLAC` and Swedish `NOTE` lines of a RESI structure unchanged.
3. WHEN a ResidenceFact has `role_in_household` or `notes`, THE GEDCOM_Exporter SHALL write `2 _SLK_HHROLE` and `2 _SLK_RNOTES` with the values.
4. WHEN an Observation is exported, THE GEDCOM_Exporter SHALL write under its `2 SOUR` the citation lines of Requirement 6 criteria 1 and 4, `3 _SLK_NOTE` with the note of the SourceRef, `3 PAGE` with `page_note`, `3 _SLK_OBSFROM` with `observed_from` and `3 _SLK_OBSTO` with `observed_to`, and SHALL keep the existing `3 NOTE Observation:` line.
5. WHEN a RESI record has `_SLK_START` or `_SLK_END`, THE GEDCOM_Importer SHALL create the endpoint from the children of that tag and SHALL ignore the `DATE` line and the Swedish `NOTE` lines for that endpoint.
6. WHEN a RESI record has neither `_SLK_START` nor `_SLK_END`, THE GEDCOM_Importer SHALL create the endpoints from the `DATE` line as before.
7. WHEN a RESI record from a Släktbusken file without SLK_Marker has `NOTE` lines that start with `Tidigast början:`, `Senast slut:` or `Roll:`, THE GEDCOM_Importer SHALL read them into `start.earliest`, `end.latest` and `role_in_household` (design decision OQ-9).
8. WHEN a RESI record has an observation with `_SLK_OBSFROM`, `_SLK_OBSTO` or `PAGE`, THE GEDCOM_Importer SHALL create the Observation with those values, the quality of Requirement 6 criterion 6 and the aspects and note of the citation.
9. WHEN all events of a file exist, THE GEDCOM_Importer SHALL set `Endpoint.event_id` from each `_SLK_EREF` that resolves to an Event of the import, and SHALL add a warning to the Import_Log for each `_SLK_EREF` that resolves to none.
10. THE GEDCOM_Importer SHALL keep `ResidenceFact.origins`, the Origin_Group behaviour and the idempotence of repeated imports of requirement 22 of `data-integrity-0-3-0`.
11. WHEN the GEDCOM_Importer matches a RESI record against a legacy residence, THE GEDCOM_Importer SHALL compute the fingerprint of the incoming residence from the same fields as `residence_fingerprint`, with `event_id` of both endpoints left out of the comparison.

### Requirement 8: Events keep roles and types, and every event type is exported

**User Story:** As a researcher, I want participant roles and every event type to survive an export, so that no event is silently dropped.

#### Acceptance Criteria

1. WHEN the GEDCOM_Exporter writes an event of an INDI record whose participant role is not `subject`, THE GEDCOM_Exporter SHALL write `2 _SLK_ROLE <role>` and THE GEDCOM_Importer SHALL create the participant with that role.
2. THE GEDCOM_Exporter SHALL NOT write `_SLK_ROLE` for placement events (`foster_home`, `adoption`), because the GEDCOM_Importer derives their roles.
3. WHEN an Event has a type that has a tag in the importer tables `_INDI_EVENT_TAGS` or `_FAM_EVENT_TAGS`, THE GEDCOM_Exporter SHALL write that tag.
4. WHEN an Event has a type `custom_individual_event` or `custom_family_event`, THE GEDCOM_Exporter SHALL write `1 EVEN` with `2 TYPE <custom_type_name>`.
5. WHEN an Event has any other type, THE GEDCOM_Exporter SHALL write `1 EVEN` with `2 TYPE` holding the type text and `2 _SLK_EVTYPE <type>`.
6. WHEN the GEDCOM_Importer reads `_SLK_EVTYPE` with a type that is a known event type, THE GEDCOM_Importer SHALL create an Event of that type.
7. WHEN the GEDCOM_Importer reads `_SLK_EVTYPE` with an unknown type, THE GEDCOM_Importer SHALL create a `custom_individual_event` and SHALL add a warning to the Import_Log.
8. WHEN the GEDCOM_Exporter writes an Event that another record refers to, THE GEDCOM_Exporter SHALL write `2 _SLK_EID <token>`, where the token is the id of the Event in the exported project.
9. WHEN the GEDCOM_Importer creates or matches an Event that has `_SLK_EID`, THE GEDCOM_Importer SHALL remember the Event for the token during that import.

### Requirement 9: Sources, repositories and provider survive an export

**User Story:** As a researcher, I want source type, provider, repository and reference fields to survive an export, so that sources are not reclassified by guesswork.

#### Acceptance Criteria

1. WHEN a Source is exported, THE GEDCOM_Exporter SHALL write `1 _SLK_STYPE` with `source_type`, `1 _SLK_PROV` with `provider` when it is not empty, `1 _SLK_LEV` and `1 _SLK_KTYP` with the names of the Leverantör and Källtyp when they exist, and `1 _SLK_SREF` with one child `2 _SLK_FLD` per structured reference field.
2. THE GEDCOM_Exporter SHALL write the value of a `_SLK_FLD` as JSON (`"12"`, `12` or `null`) so that the value type is kept.
3. WHEN a SOUR record has `_SLK_STYPE` with a valid source type, THE GEDCOM_Importer SHALL use it and SHALL NOT run the keyword detection of `detect_source_type`.
4. WHEN a SOUR record has `_SLK_SREF`, THE GEDCOM_Importer SHALL create the structured reference from the `_SLK_FLD` entries, and WHEN it has none, THE GEDCOM_Importer SHALL parse the reference text as before.
5. WHEN a SOUR record has `_SLK_PROV`, THE GEDCOM_Importer SHALL set `Source.provider` to its value.
6. WHEN a SOUR record has `_SLK_LEV` and `_SLK_KTYP` that name an existing Leverantör and Källtyp of the project, THE GEDCOM_Importer SHALL set `leverantor_id` and `kalltyp_id`.
7. WHEN a Source has RepositoryRefs, THE GEDCOM_Exporter SHALL write one `0 @Rn@ REPO` record per used Repository with `NAME`, and `1 REPO @Rn@` with `2 CALN` under the SOUR record for each RepositoryRef.
8. WHEN the GEDCOM_Importer reads `1 REPO` on a SOUR record that points to a REPO record, THE GEDCOM_Importer SHALL find a Repository with the same name or create one, and SHALL add a RepositoryRef with the call number.
9. WHEN a SOUR record from a file without SLK_Marker is imported, THE GEDCOM_Importer SHALL map the source as before.

### Requirement 10: Data that is not exported is reported

**User Story:** As a researcher, I want the export log to say what a GEDCOM file does not contain, so that I know when I need another form of backup.

#### Acceptance Criteria

1. THE GEDCOM_Exporter SHALL NOT export DNA data, clusters, research notes, cases, hypotheses and actions, merge candidates, merge history or `connection_overrides`.
2. WHEN Project_Data contains media items, THE GEDCOM_Exporter SHALL report the count in `omitted_elements` and SHALL add a warning that states that media files and links are not exported.
3. WHEN Project_Data contains place types, THE GEDCOM_Exporter SHALL report in the Export_Log that place types are not exported (deferred, design section "Scope for 0.3.0 versus deferred").
4. WHEN an export writes any SLK_Tag, THE GEDCOM_Exporter SHALL write the SLK_Marker in the HEAD record.
5. WHEN an export falls back to an Individual_Fallback or drops a value, THE GEDCOM_Exporter SHALL add a Swedish warning to the Export_Log for that case.

### Requirement 11: Custom tags are documented, tolerated and tested

**User Story:** As a maintainer, I want every custom tag documented and tested, and the Importer to survive unknown tags, so that the format can evolve without aborting imports.

#### Acceptance Criteria

1. THE GEDCOM_Exporter SHALL write only SLK_Tags that are listed in the Tag_Registry.
2. FOR EACH SLK_Tag in the Tag_Registry, THE test suite SHALL contain at least one regression test that imports a GEDCOM file with that tag and asserts the imported value.
3. WHEN the GEDCOM_Importer reads a tag that starts with `_SLK_` and is not in the Tag_Registry, THE GEDCOM_Importer SHALL ignore the tag and its children and SHALL NOT abort the import.
4. IF an SLK_Tag has a value that the GEDCOM_Importer cannot interpret, THEN THE GEDCOM_Importer SHALL use the default of the corresponding standard tag, SHALL add a warning to the Import_Log and SHALL continue the import.
5. THE GEDCOM_Importer SHALL treat an uninterpretable SLK_Tag value as a Recoverable_Input_Problem of `data-integrity-0-3-0` and SHALL treat any other exception as an abort of the import.
6. WHEN a GEDCOM file contains unknown tags below INDI, FAM, RESI and event records, THE GEDCOM_Importer SHALL import the known data of those records unchanged.

### Requirement 12: Record identity stays stable across versions

**User Story:** As a researcher, I want an old export and a new export of the same project to import without duplicates, so that upgrading Släktbusken does not double my events and residences.

#### Acceptance Criteria

1. WHEN a GEDCOM file has no SLK_Marker, THE GEDCOM_Importer SHALL compute the record hash with Hash_Profile `legacy`, which is the current canonical form, so that all stored hashes keep their meaning.
2. WHEN a GEDCOM file has the SLK_Marker, THE GEDCOM_Importer SHALL compute the record hash with Hash_Profile `slk1`, which first removes from the record every `_SLK_` node, every `QUAY`, `PAGE`, `DATA` and `OBJE` child of a `SOUR` line, and every `NOTE` child of a `SOUR` line whose value does not start with `Observation:`.
3. THE golden vectors of `record_identity_golden.py` for Hash_Profile `legacy` SHALL stay unchanged, and THE test suite SHALL contain new golden vectors for Hash_Profile `slk1`.
4. WHEN a project was imported from an old export and the new export of the same data is imported into it, THE GEDCOM_Importer SHALL create only the events and residences that the old export did not contain, and SHALL create no second copy of an event or residence that the old file contained.
5. WHEN a project was imported from a new export and the old export of the same data is imported into it, THE GEDCOM_Importer SHALL create no event and no residence.
6. WHEN the same new export is imported twice, THE GEDCOM_Importer SHALL create no event, no residence and no person in the second import.
7. WHEN the GEDCOM_Importer imports a record whose hash is equal to a stored hash but whose SLK_Tag content differs from the stored object, THE GEDCOM_Importer SHALL leave the stored object unchanged (requirement 10.14 of `data-integrity-0-3-0`).
8. THE GEDCOM_Exporter SHALL keep every line of an event or RESI record that the exporter wrote before this spec, byte for byte, except lines that Requirement 6 criterion 5 and Requirement 7 criterion 2 name as kept.

### Requirement 13: Backward compatibility

**User Story:** As a researcher, I want old projects and old GEDCOM files to keep working, so that the update does not break what I have.

#### Acceptance Criteria

1. THE GEDCOM_Importer SHALL import `exporttest.ged` and all files in `tests/fixtures/gedcom/` without abort and with the same persons, families, events and residences as before this spec, apart from the behaviour that Requirements 2 to 9 name.
2. WHEN the GEDCOM_Importer imports a file from another program, THE GEDCOM_Importer SHALL apply only the rules of this spec that concern the standard tags `QUAY`, `TYPE` under `NAME`, `NOTE`, `TITL` and `REPO`.
3. THE persistence layer SHALL keep project format 0.5 and SHALL add no field to any dataclass in `slaktbusken/model/`.
4. THE GEDCOM_Exporter SHALL write a file that other GEDCOM 5.5.1 programs can read, where every SLK_Tag is an underscore tag.
5. THE GEDCOM_Exporter SHALL write an output that is byte-identical for the same Project_Data across two exports.

### Requirement 14: Automated round-trip verification and difference classification

**User Story:** As a maintainer, I want a repeatable comparison of original, GEDCOM and re-import, so that every loss is found, classified and either fixed or documented.

#### Acceptance Criteria

1. THE test suite SHALL compare Project_Data before and after a Round_Trip through the Stable_View, which contains no generated ids.
2. THE Stable_View SHALL contain: person and family counts; event counts per type with participants (by person key and role); birth, death, marriage and foster relationships; notes, titles and name types; citations with context, quality, note and aspects; residence periods, endpoints, observations and event links; unknown sex and partner roles.
3. THE comparison SHALL report each difference with a code from a difference catalog and with a Difference_Class A, B, C or D.
4. THE test suite SHALL fail IF a difference has no catalog entry, and SHALL fail IF a difference whose catalog status is `fixed` occurs.
5. THE test suite SHALL list every difference whose catalog status is `deferred` or `app_only` in the report, together with its Difference_Class.
6. THE test suite SHALL run the comparison on the Fixture_Set, on a synthetic project that has the same shape as the findings (heterosexual, same-sex, unknown-sex and foster families; an Orphan_Family_Event; date-level citations; residences with event links), and on generated projects (property test, at least 100 examples).
7. WHEN `exporttest.ged` is imported, THE test suite SHALL assert that the result equals `exporttest.json` in the Stable_View apart from differences that are in the catalog.
8. WHEN `MergeTest.json` is exported and imported twice, THE test suite SHALL assert that the second import creates no event, no residence and no person.
9. IF a file of the Fixture_Set is missing, THEN THE test suite SHALL fail with a message that names the missing file.
10. THE script `scripts/gedcom_roundtrip_report.py` SHALL write the classified difference report of the Fixture_Set as Markdown, with the counts per Difference_Class and status.

### Requirement 15: Mandatory test group and no weaker tests

**User Story:** As a maintainer, I want the round-trip tests to be mandatory and existing integrity tests to stay at least as strict, so that data loss cannot return unnoticed.

#### Acceptance Criteria

1. THE Roundtrip_Group SHALL be registered in `tests/mandatory_groups.py` with modules under `tests/test_gedcom_roundtrip/` and the required tests of this spec (design decision OQ-8).
2. THE script `scripts/run_mandatory_tests.py` SHALL run the Roundtrip_Group together with the Dataskydd_Group and SHALL print one line for each group.
3. THE Roundtrip_Group tests SHALL be neither skipped, nor `xfail`, nor deselected.
4. THE ordinary properties of the Roundtrip_Group SHALL run with at least 100 examples, and THE guard in `tests/reduced_example_counts.py` SHALL check this for `tests/test_gedcom_roundtrip/`.
5. THE test suite SHALL keep every test of the Dataskydd_Group, and SHALL change an assertion of that group only when the assertion states a documented limitation that this spec removes, and SHALL replace it by a stronger assertion on the corrected behaviour.
6. WHEN the Dataskydd_Group and the Roundtrip_Group run, THE result SHALL show no regression in the Dataskydd_Group.
