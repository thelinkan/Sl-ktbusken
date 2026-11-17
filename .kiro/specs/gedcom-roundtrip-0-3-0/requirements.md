# Requirements Document

## Introduction

This spec fixes data loss in the GEDCOM 5.5.1 export and in the export-then-import round trip of Släktbusken (release 0.3.0, branch Features0.3.0). It follows the spec `data-integrity-0-3-0`, whose record identity (Event_Origin, Residence origins, Origin_Group), import atomicity and import-abort rules stay in force.

The findings come from a comparison by the user of `MergeTest.json` (original project), its GEDCOM export (`exporttest.ged`) and the project imported from that file (`exporttest.json`). The three files are in the repository under `tests/fixtures/gedcom_roundtrip/`. The user has confirmed that `MergeTest.json` is a demo file with fictive persons only, so all three files may be committed.

The user has decided all open questions of the first draft (see "Decisions" in design.md). The decisions that change requirements are: the `_SLK_` prefix and a full Tag_Registry (decision 1); a documented HUSB/WIFE placeholder rule with enforced safeguards (decision 2); QUAY semantics (decision 3); an Individual_Fallback that the importer reconstructs by token only (decision 4); event links implemented last and isolated (decision 5); Swedish compatibility lines kept (decision 6); replacement of two loss-pinning assertions (decision 7); the mandatory group "GEDCOM-rundresa" (decision 8); exact legacy prose parsing (decision 9); and repositories now (decision 10).

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
- **Tag_Registry**: The table in design.md that lists, for every SLK_Tag, its purpose, structure (parent, children, cardinality), supported values, importer behaviour (including on bad values) and standard fallback. The same table exists as `SLK_TAG_REGISTRY` in code.
- **Partner_Placeholder**: The HUSB or WIFE line that the GEDCOM_Exporter writes for a partner. It is a structural slot that GEDCOM 5.5.1 requires for compatibility. It is not a statement about the partner's sex or role.
- **Placeholder_Conflict**: A family in which a Partner_Placeholder contradicts a known sex: a partner of sex `M` in the WIFE slot, a partner of sex `F` in the HUSB slot, or a partner of sex `X` in either slot.
- **Source_Quality**: The Släktbusken classification of a source as `primary`, `secondary` or `tertiary` (`SourceRef.quality`). It classifies the kind of source. It differs from GEDCOM QUAY, which is a certainty assessment of the evidence (design section "Citation quality: QUAY versus Source_Quality").
- **Legacy_Prose_Format**: One of the exact Swedish NOTE line formats that Släktbusken versions before this spec wrote: `Tidigast början: <ISO date>`, `Senast slut: <ISO date>`, `Roll: <text>` under RESI, and `Observation: <year>` or `Observation: <year>-<year>` under a `SOUR` line of a RESI.
- **Event_Link_Module**: The module `slaktbusken/gedcom/event_links.py` and its tests, which hold all code for `Name.event_id` and `Endpoint.event_id` (Requirement 16).
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
8. WHEN the GEDCOM_Importer reads `1 EVEN` structures with `_SLK_EVTYPE` and the same Event_Token on several INDI records of one file, THE GEDCOM_Importer SHALL create one Event that has one participant per INDI record, with the role from `_SLK_ROLE` of that record.
9. THE GEDCOM_Importer SHALL join `1 EVEN` structures into one Event by equal Event_Token within one file and by nothing else, and SHALL NOT join structures by equal date, equal place, equal type or equal participants.
10. WHEN two or more separate marriages of one file have equal date and equal place but different Event_Tokens, THE GEDCOM_Importer SHALL create one Event for each Event_Token.
11. IF one INDI record holds two `1 EVEN` structures with the same Event_Token, THEN THE GEDCOM_Importer SHALL use the first structure, SHALL ignore the second and SHALL add a warning to the Import_Log.
12. WHEN the GEDCOM_Importer creates a merged Event from several INDI records, THE GEDCOM_Importer SHALL store one RecordOrigin for each contributing INDI record on that Event, each with the file, the INDI cross-reference and the record hash of that INDI record's `1 EVEN` structure, and the origins SHALL form one Origin_Group of `data-integrity-0-3-0`.
13. WHEN a file with Individual_Fallback structures is imported a second time into the project that the first import created, THE GEDCOM_Importer SHALL create no Event, no participant and no origin, because each contributing INDI record matches its stored RecordOrigin.
14. WHEN an Event_Token of an `1 EVEN` structure is empty or occurs in only one INDI record, THE GEDCOM_Importer SHALL create an Event with that single participant and SHALL add no warning.

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
8. WHERE the Event_Link_Module is present, WHEN a Name has `event_id`, THE GEDCOM_Exporter SHALL write `2 _SLK_EREF` with the Event_Token of that Event directly under the `1 NAME` line (level 2, because level 3 under a level-1 `NAME` is invalid GEDCOM), and THE GEDCOM_Importer SHALL restore `Name.event_id` once all events of the file exist (Requirement 16).
9. WHERE the Event_Link_Module is present, IF an Event_Token under a `NAME` record resolves to no Event of the import, THEN THE GEDCOM_Importer SHALL leave `Name.event_id` empty and SHALL add a warning to the Import_Log.

### Requirement 4: Partners keep roles and order, and HUSB/WIFE are documented placeholders

**User Story:** As a researcher, I want my partner roles, partner order and sexes to survive an export unchanged, and I want the exporter never to present a guessed husband or wife as a fact, so that same-sex, gender-neutral and unknown-sex families stay correct.

The investigation in design.md (section "Partner representation in GEDCOM") found that GEDCOM 5.5.1 gives a FAM record at most one HUSB and at most one WIFE, that GEDCOM 7 states that sex, gender and roles must not be inferred from the slot, that readers that find two HUSB or two WIFE lines are not specified to keep both, and that ASSO or RELA cannot replace the slots without losing the parent link in other programs. A one-partner family writes the partner in the slot of a known sex `M` or `F` and otherwise in HUSB, because no second partner exists to order against. The exporter therefore writes HUSB and WIFE as Partner_Placeholders under the rule below, and records the real roles and order in `_SLK_PARTNER`. The criteria 11 to 16 enforce the safeguards of that compromise.

#### Acceptance Criteria

1. WHEN a family has two partners whose sexes are both known (`M` or `F`) and differ, THE GEDCOM_Exporter SHALL write the partner of sex `M` as HUSB and the partner of sex `F` as WIFE, regardless of role and list order.
2. WHEN a family has two partners and the two sexes are not both known and different (one sex is `U` or `X`, or the sexes are equal), THE GEDCOM_Exporter SHALL fill HUSB and then WIFE in partner list order and SHALL NOT use a single known sex to reorder the partners.
3. THE GEDCOM_Exporter SHALL never write two HUSB lines or two WIFE lines in one family, and SHALL treat the slot as a structural placeholder and never as a fact about sex or role.
4. WHEN a family has at least one partner, THE GEDCOM_Exporter SHALL write one `1 _SLK_PARTNER <xref>` entry per partner in partner list order, each with `2 _SLK_ROLE` holding the stored role text.
5. WHEN a FAM record has `_SLK_PARTNER` entries that reference exactly the persons given by HUSB and WIFE, THE GEDCOM_Importer SHALL create the partners in the order of the `_SLK_PARTNER` entries with the stored roles.
6. WHEN a FAM record has no `_SLK_PARTNER` entries, THE GEDCOM_Importer SHALL create the partners with the roles `husband` and `wife` as before.
7. IF the `_SLK_PARTNER` entries of a FAM record do not reference exactly the persons given by HUSB and WIFE, THEN THE GEDCOM_Importer SHALL ignore the entries and SHALL add a warning to the Import_Log.
8. WHEN `Person.sex` is `X`, THE GEDCOM_Exporter SHALL write `1 SEX U` and `2 _SLK_SEX X`, and WHEN `_SLK_SEX X` is present, THE GEDCOM_Importer SHALL set the sex to `X`.
9. WHEN `Person.sex` is `U`, THE GEDCOM_Exporter SHALL write `1 SEX U`.
10. WHEN the GEDCOM_Importer updates an existing family and the incoming partner person set equals the existing partner person set, THE GEDCOM_Importer SHALL keep the roles of the existing partners.
11. THE GEDCOM_Importer SHALL restore the partner roles and the partner order from `_SLK_PARTNER` whenever criterion 5 applies, and SHALL NOT derive a role from the HUSB or WIFE slot in that case.
12. THE GEDCOM_Importer SHALL NOT set, change or infer `Person.sex` from HUSB, WIFE, a partner role or a slot, and SHALL set `Person.sex` only from `SEX` and `_SLK_SEX` of the INDI record (confirmed for the current importer: no code path sets sex from HUSB or WIFE; a test SHALL pin this).
13. WHEN an INDI record has no `SEX` line or `SEX U`, THE GEDCOM_Importer SHALL import the sex as `U`, including when the person is HUSB or WIFE of a family.
14. WHEN a family has a Placeholder_Conflict, THE GEDCOM_Exporter SHALL add one Swedish Export_Log warning for that family, naming the family partners, the placed slot of each conflicting partner and the sentence that HUSB/WIFE is a structural placeholder and not a statement about sex, and SHALL add one such warning for every such family, not only for the first.
15. WHEN at least one Placeholder_Conflict was reported, THE GEDCOM_Exporter SHALL add one closing Swedish Export_Log line that states that programs that do not read `_SLK_PARTNER` show the placeholder slots as husband and wife (design section "Third-party compatibility limitations").
16. THE test suite SHALL cover, for the export and the Round_Trip of partners: a family of sex `M` and `F`; a same-sex family `M` and `M`; a same-sex family `F` and `F`; a family with a partner of sex `U`; a family with sex `X`; a family with the roles `make` and `maka`; a family with the role `partner` for both; a one-partner family; and a family whose list order is the reverse of the slot order, each with the assertions: roles restored exactly, order restored exactly, sex unchanged, no two lines of one slot, warning present exactly when a Placeholder_Conflict exists.
17. WHEN the Round_Trip of Släktbusken to Släktbusken is run for any family, THE partner order and roles after the import SHALL equal the partner order and roles before the export.
18. WHEN a FAM record has `_SLK_PARTNER` entries and an INDI person has `SEX M` but sits in WIFE, THE GEDCOM_Importer SHALL keep the stored role of that partner and SHALL keep the sex `M`.

### Requirement 5: Parentage types and foster families round-trip

**User Story:** As a researcher, I want foster, adoptive, step and other parentage to survive an export, so that complex families are not turned into biological ones.

#### Acceptance Criteria

1. THE GEDCOM_Exporter SHALL keep the existing output for foster and adoptive parentage: `2 PEDI foster` and `2 PEDI adopted` under `FAMC`, `1 EVEN` with `2 TYPE Fosterhem` and `2 FAMC`, and `1 ADOP` with `2 FAMC`.
2. WHEN a family has a ParentChildLink with a parentage type other than `biological`, THE GEDCOM_Exporter SHALL write `2 _SLK_PLINK <parent xref>` with `3 TYPE <parentage_type>` under the `FAMC` of the child, one entry per link in link order.
3. WHEN a ParentChildLink has no parent, THE GEDCOM_Exporter SHALL write `2 _SLK_PLINK` without a value and with the same `3 TYPE`.
4. WHEN a `FAMC` record has `_SLK_PLINK` entries, THE GEDCOM_Importer SHALL create one ParentChildLink per entry with the stored parentage type and SHALL NOT apply the `PEDI` value to the parents covered by an entry.
5. WHEN a `FAMC` record has no `_SLK_PLINK` entry, THE GEDCOM_Importer SHALL derive the parentage type from `PEDI` as before.
6. THE GEDCOM_Importer SHALL create the same foster and adoptive families, placement events and paired end events from a file written before this spec as before this spec.
7. THE GEDCOM_Importer SHALL NOT remove a child, a ParentChildLink or a partner, and SHALL NOT change a partner role or the partner order, of a family that it created or updated from a FAM record of the file, when it records a placement event after the import.
8. WHEN the family that a placement event refers to through the `FAMC` of the child is not a placement-derived family, THE GEDCOM_Importer SHALL create or reuse a separate placement-derived family for that placement event, and SHALL leave the imported family unchanged.
9. FOR ALL files written by the GEDCOM_Exporter, THE foster and adoption handling after the import SHALL keep the biological siblings, the partner roles and order restored from `_SLK_PARTNER`, and a ParentChildLink without parent of the imported family, while the foster families, placement events and paired end events of criterion 6 stay as before.

### Requirement 6: Citation semantics survive the round trip

**User Story:** As a researcher, I want a citation to keep its context, quality, note and aspects, so that my evidence assessment is not rewritten by an export.

#### Acceptance Criteria

1. WHEN the GEDCOM_Exporter writes a SourceRef, THE GEDCOM_Exporter SHALL write `3 QUAY` with the value 3 for `primary`, 2 for `secondary` and 1 for `tertiary`, and SHALL write `3 _SLK_QUAL <text>` whenever QUAY cannot hold the quality losslessly, that is for every non-empty quality text other than `primary`, `secondary` and `tertiary`, in which case THE GEDCOM_Exporter SHALL write no QUAY.
2. WHEN the SourceRef has a context other than `event`, THE GEDCOM_Exporter SHALL write `3 _SLK_CTX` with the value `date`, `place` or `from_place`.
3. WHEN the SourceRef has a note, THE GEDCOM_Exporter SHALL write `3 NOTE` with the note text under the citation of an event.
4. WHEN the SourceRef has aspects, THE GEDCOM_Exporter SHALL write one `3 _SLK_ASP` per aspect, in order.
5. THE GEDCOM_Exporter SHALL keep writing `3 TEXT` with the citation text under the citation of an event, until a migration of stored record hashes exists (design decision OQ-6).
6. WHEN the GEDCOM_Importer reads a citation, THE GEDCOM_Importer SHALL read `_SLK_QUAL` before `QUAY` and SHALL set the quality from `_SLK_QUAL`, else from `QUAY` (3 to `primary`, 2 to `secondary`, 1 and 0 to `tertiary`), else to `secondary`; IF `QUAY` holds a value other than 0, 1, 2 or 3, THEN THE GEDCOM_Importer SHALL use `secondary` and SHALL add a warning to the Import_Log.
7. WHEN the GEDCOM_Importer reads a citation with `_SLK_CTX date` and the event has a date, THE GEDCOM_Importer SHALL store the SourceRef in `DateValue.source_refs`, and WHEN the event has no date, THE GEDCOM_Importer SHALL store the SourceRef at event level.
8. WHEN the GEDCOM_Importer reads a citation with `_SLK_CTX place` and the event has a place, THE GEDCOM_Importer SHALL store the SourceRef in `PlaceRef.source_refs`, and WHEN the event has no place, THE GEDCOM_Importer SHALL store the SourceRef at event level.
9. WHEN the GEDCOM_Importer reads a citation with `_SLK_CTX from_place` and the event has a `from_place`, THE GEDCOM_Importer SHALL store the SourceRef in the `source_refs` of `from_place`, and WHEN the event has none, THE GEDCOM_Importer SHALL store the SourceRef at event level.
10. WHEN the GEDCOM_Importer reads a citation with `NOTE` and `_SLK_ASP` children, THE GEDCOM_Importer SHALL store the note and the aspects in the SourceRef.
11. WHEN the GEDCOM_Exporter writes a flytt event with a `from_place`, THE GEDCOM_Exporter SHALL write `2 _SLK_FROMPLAC` with the place hierarchy text, and WHEN the GEDCOM_Importer reads `_SLK_FROMPLAC`, THE GEDCOM_Importer SHALL resolve it to `Event.from_place` with the same place resolution as `PLAC`.
12. THE GEDCOM_Exporter SHALL write `3 _SLK_CTX from_place` citations for a flytt event and SHALL no longer skip them.
13. THE GEDCOM_Exporter SHALL NOT write `QUAY 0`.
14. THE design document SHALL state that GEDCOM QUAY is a certainty assessment of the evidence, that Source_Quality classifies the kind of source, and that the mapping of criterion 1 is a compatibility convention and not an equivalence.
15. FOR ALL SourceRefs with quality `primary`, `secondary`, `tertiary` or any other non-empty text, a Round_Trip of Släktbusken to Släktbusken SHALL return the same quality (round-trip property).
16. WHEN a foreign file has `QUAY` 0, 1, 2 or 3 without `_SLK_QUAL`, THE GEDCOM_Importer SHALL apply criterion 6 and SHALL add no warning.

### Requirement 7: Residences round-trip with structured data

**User Story:** As a researcher, I want residence periods, observations and links to events to survive an export, so that my residence research is not reduced to a rough date.

#### Acceptance Criteria

1. WHEN a ResidenceFact is exported, THE GEDCOM_Exporter SHALL write `2 _SLK_START` and `2 _SLK_END`, each with the children `3 _SLK_EARLIEST`, `3 _SLK_LATEST`, `3 _SLK_PREC`, and `3 _SLK_NOTE` for the values that are present (`3 _SLK_EREF` is written only where the Event_Link_Module is present, Requirement 16).
2. THE GEDCOM_Exporter SHALL keep writing the existing `DATE`, `PLAC` and Swedish `NOTE` lines of a RESI structure unchanged.
3. WHEN a ResidenceFact has `role_in_household` or `notes`, THE GEDCOM_Exporter SHALL write `2 _SLK_HHROLE` and `2 _SLK_RNOTES` with the values.
4. WHEN an Observation is exported, THE GEDCOM_Exporter SHALL write under its `2 SOUR` the citation lines of Requirement 6 criteria 1 and 4, `3 _SLK_NOTE` with the note of the SourceRef, `3 PAGE` with `page_note`, `3 _SLK_OBSFROM` with `observed_from` and `3 _SLK_OBSTO` with `observed_to`, and SHALL keep the existing `3 NOTE Observation:` line.
5. WHEN a RESI record has `_SLK_START` or `_SLK_END`, THE GEDCOM_Importer SHALL create the endpoint from the children of that tag and SHALL ignore the `DATE` line and the Swedish `NOTE` lines for that endpoint.
6. WHEN a RESI record has neither `_SLK_START` nor `_SLK_END`, THE GEDCOM_Importer SHALL create the endpoints from the `DATE` line as before.
7. WHEN a RESI record of a file without SLK_Marker has `NOTE` lines in a Legacy_Prose_Format, THE GEDCOM_Importer SHALL read `Tidigast början: <ISO date>` into `start.earliest`, `Senast slut: <ISO date>` into `end.latest`, `Roll: <text>` into `role_in_household` and `Observation: <year>` or `Observation: <year>-<year>` under a `SOUR` line into the observation period, and SHALL match each prefix exactly, case-sensitively and at the start of the line.
7a. IF the value after a Legacy_Prose_Format prefix is not a valid ISO date (for `Tidigast början:` and `Senast slut:`) or not a valid year or year range with start not after end (for `Observation:`), THEN THE GEDCOM_Importer SHALL leave the NOTE line as ordinary note text, SHALL ignore the value and SHALL add a warning to the Import_Log.
7b. THE GEDCOM_Importer SHALL NOT apply criterion 7 to a file with the SLK_Marker and SHALL NOT reinterpret any other free-text NOTE line as structured data; new exports carry the structured `_SLK_` metadata.
8. WHEN a RESI record has an observation with `_SLK_OBSFROM`, `_SLK_OBSTO` or `PAGE`, THE GEDCOM_Importer SHALL create the Observation with those values, the quality of Requirement 6 criterion 6 and the aspects and note of the citation.
9. WHERE the Event_Link_Module is present, THE GEDCOM_Importer SHALL set `Endpoint.event_id` as Requirement 16 states.
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
10. WHEN an Event has a non-empty `cause` (a death event and every other event type of the model that supports a cause), THE GEDCOM_Exporter SHALL write the cause as the standard `2 CAUS` line under the event, through `text_lines`, and THE GEDCOM_Importer SHALL restore `Event.cause` from `CAUS`.
11. FOR ALL events, THE Hash_Profile `slk1` SHALL skip every `CAUS` child of an event, so that a file with `CAUS` and the same file without `CAUS` give the same record hash.

### Requirement 9: Sources, repositories and provider survive an export

**User Story:** As a researcher, I want source type, provider, repository and reference fields to survive an export, so that sources are not reclassified by guesswork.

#### Acceptance Criteria

1. WHEN a Source is exported, THE GEDCOM_Exporter SHALL write `1 _SLK_STYPE` with `source_type`, `1 _SLK_PROV` with `provider` when it is not empty, `1 _SLK_LEV` and `1 _SLK_KTYP` with the names of the Leverantör and Källtyp when they exist, and `1 _SLK_SREF` with one child `2 _SLK_FLD` per structured reference field.
2. THE GEDCOM_Exporter SHALL write the value of a `_SLK_FLD` as JSON (`"12"`, `12` or `null`) so that the value type is kept.
3. WHEN a SOUR record has `_SLK_STYPE` with a valid source type, THE GEDCOM_Importer SHALL use it and SHALL NOT run the keyword detection of `detect_source_type`.
4. WHEN a SOUR record has `_SLK_SREF`, THE GEDCOM_Importer SHALL create the structured reference from the `_SLK_FLD` entries, and WHEN it has none, THE GEDCOM_Importer SHALL parse the reference text as before.
5. WHEN a SOUR record has `_SLK_PROV`, THE GEDCOM_Importer SHALL set `Source.provider` to its value.
6. WHEN a SOUR record has `_SLK_LEV` and `_SLK_KTYP` that name an existing Leverantör and Källtyp of the project, THE GEDCOM_Importer SHALL set `leverantor_id` and `kalltyp_id`.
7. WHEN a Source has RepositoryRefs, THE GEDCOM_Exporter SHALL write one `0 @Rn@ REPO` record per used Repository, first the used Repositories in order of first use, then the unreferenced Repositories in project order, with `NAME`, `ADDR`, one `PHON`, `EMAIL` and `WWW` per list entry, `NOTE`, `_SLK_RTYPE` for `Repository.type` and one `_SLK_XID` per external id, and SHALL write `1 REPO @Rn@` under the SOUR record for each RepositoryRef, with `2 CALN` for the call number and `3 MEDI` for `media_type`. THE GEDCOM_Exporter SHALL write the unreferenced (unused) Repositories as top-level REPO records too, after the used ones, in project order, and THE GEDCOM_Importer SHALL import a top-level REPO record even when no SOUR record refers to it.
8. WHEN the GEDCOM_Exporter writes a RepositoryRef, THE GEDCOM_Exporter SHALL write `2 NOTE` for `notes` and, for the values that are present, `2 _SLK_RSTYPE` (`source_type`), `2 _SLK_RIMG` (`image_number`), `2 _SLK_RPAGE` (`page_number`) and `2 _SLK_RMEDNAME` (`media_name`).
9. WHEN the GEDCOM_Importer reads `1 REPO` on a SOUR record that points to a REPO record, THE GEDCOM_Importer SHALL find the Repository with the same name, type and address or create one, and SHALL add a RepositoryRef with all values of criterion 8 that the structure holds.
10. WHEN two SOUR records point to one REPO record, THE GEDCOM_Importer SHALL create one Repository and two RepositoryRefs, and WHEN the file is imported a second time, THE GEDCOM_Importer SHALL create no second Repository and no second RepositoryRef.
11. WHEN a REPO record or a RepositoryRef comes from a file without SLK_Marker, THE GEDCOM_Importer SHALL use only the standard tags `NAME`, `ADDR`, `PHON`, `EMAIL`, `WWW`, `NOTE`, `CALN` and `MEDI`, and SHALL map the source as before for every other aspect.
12. FOR ALL Repositories and RepositoryRefs, a Round_Trip of Släktbusken to Släktbusken SHALL return equal values, and a program that ignores every SLK_Tag SHALL still see the repository name, address, contact data, call number and media type.
13. THE test suite SHALL list every Source field that is not exported (`provider_ref`, `short_note`, `free_note`, `arkivreferens`, `arkivreferenser`, `media_ids`) in the difference catalog with status `deferred` or `app_only`.
14. WHEN a SOUR record from a file without SLK_Marker is imported, THE GEDCOM_Importer SHALL map the source as before.

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
2. WHEN a GEDCOM file has the SLK_Marker, THE GEDCOM_Importer SHALL compute the record hash with Hash_Profile `slk1`, which first removes from the record every `_SLK_` node, every `QUAY`, `PAGE`, `DATA` and `OBJE` child of a `SOUR` line, every `NOTE` child of a `SOUR` line whose value does not start with `Observation:`, and every `CAUS` child of an event record.
3. THE golden vectors of `record_identity_golden.py` for Hash_Profile `legacy` SHALL stay unchanged, and THE test suite SHALL contain new golden vectors for Hash_Profile `slk1`.
4. WHEN a project was imported from an old export and the new export of the same data is imported into it, THE GEDCOM_Importer SHALL create only the events and residences that the old export did not contain, and SHALL create no second copy of an event or residence that the old file contained.
5. WHEN a project was imported from a new export and the old export of the same data is imported into it, THE GEDCOM_Importer SHALL create no event and no residence.
6. WHEN the same new export is imported twice, THE GEDCOM_Importer SHALL create no event, no residence and no person in the second import.
7. WHEN the GEDCOM_Importer imports a record whose hash is equal to a stored hash but whose SLK_Tag content differs from the stored object, THE GEDCOM_Importer SHALL leave the stored object unchanged (requirement 10.14 of `data-integrity-0-3-0`).
8. THE GEDCOM_Exporter SHALL keep every line of an event or RESI record that the exporter wrote before this spec, byte for byte, except lines that Requirement 6 criterion 5 and Requirement 7 criterion 2 name as kept, and except the `CAUS` line of Requirement 8 criterion 10.
9. WHEN the GEDCOM_Importer finishes an import, THE ImportResult SHALL report in `families_added` only the families that do not exist in the project before the import; a derived foster family that the importer rebuilds and folds back into an existing family SHALL NOT be counted, so that the re-import of the export of `MergeTest.json` reports `families_added` 0.
10. IF a file written by the GEDCOM_Exporter before this spec contains an xref of the form `@X<number>@` that the old exporter derived from the hash of an id without a numeric suffix, THEN importing that file into a project that holds the new export of the same data MAY create duplicates of the records behind those xrefs; this is a documented known limitation of criteria 4 and 5, because those xrefs varied per Python run and no matcher is added.

### Requirement 13: Backward compatibility

**User Story:** As a researcher, I want old projects and old GEDCOM files to keep working, so that the update does not break what I have.

#### Acceptance Criteria

1. THE GEDCOM_Importer SHALL import `exporttest.ged` and all files in `tests/fixtures/gedcom/` without abort and with the same persons, families, events and residences as before this spec, apart from the behaviour that Requirements 2 to 9 name.
2. WHEN the GEDCOM_Importer imports a file from another program, THE GEDCOM_Importer SHALL apply only the rules of this spec that concern the standard tags `QUAY`, `TYPE` under `NAME`, `NOTE`, `TITL` and `REPO`.
3. THE persistence layer SHALL keep project format 0.5 and SHALL add no field to any dataclass in `slaktbusken/model/`, with one approved exception: the optional field `Event.extra_origins: list[RecordOrigin]` with default empty. THE persistence layer SHALL omit `extra_origins` from the project JSON when the list is empty, so that projects without shared events from several INDI records are unchanged and old project files load unchanged.
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
5. THE test suite SHALL keep every test of the Dataskydd_Group and SHALL change an assertion of that group only when the assertion pins a documented loss that this spec removes, and SHALL replace it by an equality assertion on the corrected behaviour. The two assertions are in `tests/test_dataskydd/test_round_trips.py`: `got.date.source_refs == []` in `test_export_import_keeps_dates_citations_and_texts` and `flytt[0].from_place is None` (with the residence `event_id is None` assertion) in `test_export_import_flytt_documented_limits`. The equality assertion for the residence `event_id` is part of the Event_Link_Module tests.
6. WHEN the Dataskydd_Group and the Roundtrip_Group run, THE result SHALL show no regression in the Dataskydd_Group, and Dataskydd SHALL stay mandatory.
7. THE final checkpoint SHALL run the Dataskydd_Group, the Roundtrip_Group and the relevant regression tests, and SHALL report the third-party limitations and the remaining Round_Trip differences to the user before any commit.

### Requirement 16: Event links are isolated and implemented last

**User Story:** As a maintainer, I want the links from names and residence endpoints to events isolated in one module, so that the links can be dropped without affecting the core fixes.

#### Acceptance Criteria

1. THE GEDCOM_Exporter and THE GEDCOM_Importer SHALL implement `Name.event_id` and `Endpoint.event_id` only through functions in the Event_Link_Module, called from the exporter and importer through one hook each.
2. WHERE the Event_Link_Module is present, WHEN a Name or an Endpoint has `event_id` of an exported Event, THE GEDCOM_Exporter SHALL write `_SLK_EREF` with the Event_Token of that Event directly under the `1 NAME` line (level 2) or under `_SLK_START` or `_SLK_END` (level 3).
3. WHERE the Event_Link_Module is present, WHEN all events of a file exist, THE GEDCOM_Importer SHALL set `Name.event_id` and `Endpoint.event_id` from each `_SLK_EREF` that resolves to an Event of the import.
4. IF an `_SLK_EREF` resolves to no Event of the import, THEN THE GEDCOM_Importer SHALL leave the link empty and SHALL add a warning to the Import_Log.
5. IF `event_links.py` and its tests are removed, THEN THE GEDCOM_Exporter and THE GEDCOM_Importer SHALL still pass every other test of the Roundtrip_Group and the Dataskydd_Group, and SHALL ignore `_SLK_EREF` as an unknown tag (Requirement 11 criterion 3).
6. THE Event_Link_Module tests SHALL be in `tests/test_gedcom_roundtrip/test_event_links.py` and in no other test module.
