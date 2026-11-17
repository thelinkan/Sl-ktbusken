# Implementation Plan: GEDCOM export and round-trip data loss (release 0.3.0)

## Overview

The plan implements `design.md` in Python 3 (PySide6 project), with pytest and Hypothesis (profile `sbk`). Task IDs are stable. The execution order follows the user's priority and is set by the dependency graph, not by the task numbers:

1. Test harness, tag registry and hash profile (tasks 1 and 2) come first.
2. Missing events and family roles (tasks 5 and 6).
3. Names, notes and titles (task 3).
4. Citation context, quality and aspects (task 7).
5. Residence observations and source metadata (tasks 9 and 11.1 to 11.3).
6. Repository interoperability (tasks 11.4 to 11.6). Media stays deferred.
7. Event links last, isolated in their own module and tests (task 10).

Every test sub-task is mandatory (no `*`), because the tests belong to the mandatory group "GEDCOM-rundresa" and must not be skippable. Test sub-tasks that change a pinned assertion of an existing test say so.

Preconditions and constraints:

- The fixtures `MergeTest.json`, `exporttest.ged` and `exporttest.json` are present under `tests/fixtures/gedcom_roundtrip/`. `MergeTest.json` holds fictive persons only, so the fixtures may be committed (decision OQ-10).
- All open questions are resolved (design section "Decisions"). No task waits for a decision.
- No task changes a model dataclass, the project format 0.5 or anything in person filtering (Package 2), with one approved exception: the optional field `Event.extra_origins` (added by task 6.2, omitted from the JSON when empty, registered as `event.extra_origins` in the person reference inventory with a rule test, validated in `validators.py`).
- No task commits to git. The final checkpoint reports to the user before any commit.
- Event links (task 10) live only in `slaktbusken/gedcom/event_links.py`, its two hooks and `tests/test_gedcom_roundtrip/test_event_links.py`, so task 10 can be dropped without affecting any other task.
- HUSB/WIFE are Partner_Placeholders. No task may infer sex or role from the slot (Requirement 4).

## Tasks

- [x] 1. Test harness and fixtures
  - [x] 1.1 Create the fixture loader and presence check
    - Create `tests/test_gedcom_roundtrip/__init__.py`, `fixtures.py` and `test_fixture_set.py`.
    - `fixtures.py` loads `MergeTest.json` into `ProjectData`, and returns the paths of `exporttest.ged` and `exporttest.json`.
    - `test_fixture_set.py` fails (no skip) with a message that names each missing file.
    - _Requirements: 14.6, 14.9_

  - [x] 1.2 Implement Stable_View, difference catalog and comparator
    - Create `stable_view.py`, `difference_catalog.py` and `comparison.py` in `tests/test_gedcom_roundtrip/`.
    - The catalog holds codes K1 to K43 of `design.md` with Difference_Class and status (`fixed`, `deferred`, `app_only`), including the uncovered Source fields (Requirement 9 criterion 13).
    - `compare(a, b)` returns `Difference` items and fails on a code without catalog entry.
    - Write unit tests for the person key, the event key and the stable ordering.
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 9.13_

  - [x] 1.3 Build the synthetic project and the Hypothesis strategies
    - Create `synthetic.py` with the fixture shape: heterosexual family, same-sex families (`M`+`M`, `F`+`F`), a partner with sex `U`, a partner with sex `X`, partners with roles `make/maka` and `partner`, a foster family (FAMC PEDI foster and EVEN Fosterhem with FAMC), two orphan marriages that share date and place, date-level citations with aspects and every quality, residences with endpoints, a repository shared by two sources.
    - Create `strategies.py` with project strategies for the properties of the design.
    - _Requirements: 14.6, 4.16_

- [x] 2. Foundations
  - [x] 2.1 Implement the text writer and the parser unescape
    - Create `slaktbusken/gedcom/text_lines.py` with `text_lines` and `escape_text` (CONT per line break, CONC at 200 characters, doubled leading `@`).
    - Change `_parse_line` in `slaktbusken/gedcom/parser.py` so that `@@` in a non-pointer value reads as `@`.
    - _Requirements: 2.1, 2.3, 2.6_

  - [x] 2.2 Implement the SLK tag registry and the tolerant readers
    - Create `slaktbusken/gedcom/slk_tags.py` with `SLK_TAG_REGISTRY` (every row of the design table with purpose, structure, supported values, importer behaviour and standard fallback) and the total reader functions `read_citation`, `read_endpoint`, `read_partners`, `read_plinks`, `read_name_type`, `read_source_fields`, `read_repository` and `read_legacy_prose`.
    - Unknown `_SLK_` tags are skipped; bad values give a problem list and the standard fallback.
    - `read_legacy_prose` accepts only the exact formats of Requirement 7 criteria 7 to 7b.
    - _Requirements: 11.1, 11.3, 11.4, 11.5, 7.7, 7.7a, 7.7b_

  - [x] 2.3 Implement Hash_Profile and SLK_Marker detection
    - In `slaktbusken/gedcom/translation/record_identity.py` add the `profile` parameter to `record_hash` and the `slk1` skip rules; add `ignore_links` to `residence_fingerprint`.
    - In `slaktbusken/gedcom/importer.py` read `_SLK_VERS` in `_import_file`, store `self._hash_profile`, and pass it from `_match_owner_events` and `_match_person_residences`.
    - Keep the `legacy` golden vectors unchanged and add `slk1` vectors to `record_identity_golden.py`.
    - _Requirements: 12.1, 12.2, 12.3, 7.11_

  - [x] 2.4 Write foundation tests
    - Create `tests/test_gedcom_roundtrip/test_text_roundtrip.py` with **Property 2** (text round trip, line length at most 255).
    - Create `test_hash_profile.py` with **Property 12** and the golden vectors for both profiles.
    - Create `test_slk_tags.py` with the registry-coverage test (every registry row has all five columns and a fallback) and the fuzz skeleton of **Property 14**.
    - **Validates: Requirements 2.1, 2.3, 2.5, 11.3, 12.2, 12.3**

- [x] 3. Names, notes and titles
  - [x] 3.1 Implement the exporter side for persons
    - In `_write_person` (`slaktbusken/gedcom/exporter.py`) write NAME with `TYPE`, `SEX U` and `_SLK_SEX X`, `TITL`, `OCCU` and `NOTE` through `text_lines`.
    - Write `_SLK_VERS 1` in `_write_head`.
    - _Requirements: 2.1, 2.2, 3.1, 4.8, 4.9, 10.4_

  - [x] 3.2 Implement the importer side for persons
    - In `_extract_gedcom_person`, `_create_person` and `_update_person` (`slaktbusken/gedcom/importer.py`) read the name types and `_SLK_SEX`, and use one `_build_names` helper with the rules of Requirement 3 (positional fallback only without any TYPE, existing types kept on update).
    - Keep `Person.sex` set only from `SEX` and `_SLK_SEX`.
    - _Requirements: 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 4.8, 4.12, 2.4_

  - [x] 3.3 Write person tests
    - Create `tests/test_gedcom_roundtrip/test_persons_roundtrip.py`: **Property 3** (name types), the sex part of **Property 5**, notes, title and occupation example tests, mixed-TYPE and update-keeps-types examples, `test_slk_tag_sex_x`.
    - **Validates: Requirements 2.2, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 4.8, 4.9**

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Families and partner roles
  - [x] 5.1 Implement the exporter side for families
    - In `_write_family` and `_write_family_links` implement `_assign_slots` with the placeholder rule (both sexes known and different: slot follows sex; otherwise partner list order; one partner: the slot of a known sex, else HUSB; never two lines of a slot), `_SLK_PARTNER` with `_SLK_ROLE` for every partner, `_SLK_PLINK` with `TYPE`, and the family events through `_family_events_for` (listed events, unique-match orphans, written-once set).
    - Add one Swedish Export_Log warning per family with a Placeholder_Conflict and one closing line about third-party display (Requirement 4 criteria 14 and 15).
    - Add `divorce_filed DIVF`, `custom_family_event` (`EVEN` with `TYPE`) and `_SLK_PART` participants.
    - Keep all PEDI and placement output byte-identical.
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 4.1, 4.2, 4.3, 4.4, 4.14, 4.15, 5.1, 5.2, 5.3_

  - [x] 5.2 Implement the importer side for families
    - In `_create_family`, `_update_family` and `_process_family_events` read `_SLK_PARTNER`, `_SLK_PLINK` and `_SLK_PART` through the tolerant readers; always restore roles and order from `_SLK_PARTNER` when it matches HUSB/WIFE; keep roles on update for an equal partner set; keep husband/wife and PEDI for old files.
    - Confirm and keep that no code path sets `Person.sex` from HUSB, WIFE, a role or a slot (design "Sex-inference finding").
    - _Requirements: 1.6, 1.7, 4.5, 4.6, 4.7, 4.10, 4.11, 4.12, 4.13, 4.18, 5.4, 5.5, 5.6_

  - [x] 5.3 Write family tests
    - Create `tests/test_gedcom_roundtrip/test_families_roundtrip.py`: **Property 1**, **Property 4**, the partner part of **Property 5**, **Property 6**.
    - Example tests for each case of Requirement 4 criterion 16: `M`+`F`, `M`+`M`, `F`+`F`, a `U` partner, an `X` partner, roles `make/maka`, role `partner` for both, one partner, reversed list order; each asserts roles, order and sex restored exactly, at most one line per slot, and a warning exactly when a Placeholder_Conflict exists.
    - A test that pins that the importer never sets sex from HUSB or WIFE (a `SEX M` person in WIFE without `_SLK_PARTNER` keeps `M`; a person without SEX in HUSB stays `U`).
    - Foster-family and old-file examples, `_SLK_PARTNER` mismatch, one `test_slk_tag_*` for `_SLK_PARTNER`, `_SLK_PLINK`, `_SLK_PART`.
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.5, 1.6, 1.7, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.10, 4.11, 4.12, 4.13, 4.14, 4.15, 4.16, 4.17, 4.18, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6**

  - [x] 5.4 Fix the post-import placement sync so that imported families are not rewritten
    - Owner files: `slaktbusken/gedcom/importer.py` and `slaktbusken/services/foster_sync.py`.
    - Problem (found by task 5.3): `_finalize_placement_events` records the placement event on the child's FAMC family, and `foster_sync._reconcile_derived_family` then drops biological siblings, resets partner roles and order (from `_SLK_PARTNER`) to father/mother and loses a parentless donor link.
    - Fix: when the family found for the placement is not a placement-derived family, create or reuse a separate derived family for the placement. Alternatively reconcile without removing children, links or roles that the file states. The importer never rewrites an imported family that is not itself placement-derived.
    - Keep the foster round trip intact (PEDI foster, `EVEN TYPE Fosterhem` with FAMC, paired end events); files written before this spec import as before, apart from no longer losing data.
    - Turn the two strict-xfail tests `test_foster_family_keeps_partner_roles_and_order` and `test_foster_child_does_not_remove_a_biological_sibling` in `tests/test_gedcom_roundtrip/test_families_roundtrip.py` into normal passing tests (remove the xfail marks).
    - Add regression tests for the foster cases in `tests/test_gedcom`; the existing foster tests stay green.
    - Documented limitation, not part of this task: a family with partial or missing parent-child links comes back with biological links for every partner (design "Known limitations").
    - _Requirements: 5.6, 5.7, 5.8, 5.9, 4.5, 4.11_

- [x] 6. Events and the Individual_Fallback
  - [x] 6.1 Implement the exporter side for events
    - In the event loop of `_write_person` and in `_write_event_detail` add the missing tags, `EVEN` with `_SLK_EVTYPE`, `_SLK_ROLE` (not for placement events), `_SLK_EID` on every event, the Individual_Fallback for orphan family events (one token per event, a different token for every event), and `_SLK_FROMPLAC` in `_write_flytt_event`.
    - _Requirements: 1.4, 8.1, 8.2, 8.3, 8.4, 8.5, 8.8, 6.11_

  - [x] 6.2 Implement the importer side for events
    - In `_indi_event_spec`, `_create_person_events`, `_create_event` and `_create_family_event` read `_SLK_ROLE`, `_SLK_EVTYPE`, `_SLK_EID` (token map) and `_SLK_FROMPLAC`.
    - Join `1 EVEN` structures into one Event by `(file, token)` only; never by date, place, type or participants; keep one RecordOrigin per contributing INDI record in one Origin_Group; a second import creates nothing.
    - Approved schema addition: `Event.extra_origins: list[RecordOrigin]` (optional, default empty, omitted from the JSON when empty). `origin` is the first record, the others go in `extra_origins`; the matcher pool gets one entry per origin of the owner; the field is registered as `event.extra_origins` (rule H) in the person reference inventory with a rule test, and validated in `validators.py`.
    - _Requirements: 1.8, 1.9, 1.10, 1.11, 1.12, 1.13, 1.14, 8.1, 8.6, 8.7, 8.9, 6.11_

  - [x] 6.3 Write event tests
    - Create `tests/test_gedcom_roundtrip/test_events_roundtrip.py`: **Property 7**, **Property 17**, the fallback example (orphan with several matching families), separate marriages that share date and place (never merged), duplicate token on one INDI, empty and single-INDI tokens, idempotent re-import of the fallback, `test_slk_tag_*` for `_SLK_EID`, `_SLK_EVTYPE`, `_SLK_ROLE`, `_SLK_FROMPLAC`.
    - Change the `flytt[0].from_place is None` assertion of `test_export_import_flytt_documented_limits` in `tests/test_dataskydd/test_round_trips.py` into an equality assertion of `from_place`. The residence `event_id` assertion of the same test changes in task 10.3.
    - **Validates: Requirements 1.4, 1.8, 1.9, 1.10, 1.11, 1.12, 1.13, 1.14, 6.11, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.9, 15.5**

- [x] 7. Citations
  - [x] 7.1 Implement the exporter side for citations
    - Add `_write_citation` to `exporter.py` and use it in `_write_event_detail`, `_write_flytt_event` (without skipping `FROM_PLACE`) and the observation SOUR lines; keep `3 TEXT` for events.
    - Write `QUAY` 3, 2, 1 for `primary`, `secondary`, `tertiary`; write `_SLK_QUAL` and no QUAY for any other non-empty quality; never write `QUAY 0`.
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.12, 6.13_

  - [x] 7.2 Implement the importer side for citations
    - In `_create_event`, `_create_family_event` and `_derive_residence` build SourceRefs with `read_citation` (`_SLK_QUAL` before `QUAY`, 0 read as `tertiary`) and place them in the event, date, place or from_place carrier (event level when the carrier is absent).
    - _Requirements: 6.6, 6.7, 6.8, 6.9, 6.10_

  - [x] 7.3 Write citation tests
    - Create `tests/test_gedcom_roundtrip/test_citations_roundtrip.py`: **Property 8** with every quality text (lossless Släktbusken-to-Släktbusken), QUAY mapping examples (3, 2, 1, 0 and absent), `_SLK_QUAL` read before `QUAY`, foreign-file QUAY example without warning, invalid QUAY value warning, `test_slk_tag_*` for `_SLK_QUAL`, `_SLK_CTX`, `_SLK_ASP`.
    - Change `test_export_import_keeps_dates_citations_and_texts` in `tests/test_dataskydd/test_round_trips.py`: replace `got.date.source_refs == []` by equality of citations per context.
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10, 6.12, 6.13, 6.15, 6.16, 15.5**

- [x] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Residences
  - [x] 9.1 Implement the exporter side for residences
    - In `_write_residence` add `_SLK_START`, `_SLK_END` (without `_SLK_EREF`, which task 10.1 adds), `_SLK_HHROLE`, `_SLK_RNOTES`, observation `QUAY`, `PAGE`, `_SLK_OBSFROM`, `_SLK_OBSTO`, `_SLK_NOTE`, `_SLK_ASP`; write `notes` and `role` through `text_lines`; keep every existing line.
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 2.6_

  - [x] 9.2 Implement the importer side for residences
    - In `_derive_residence` and `_incoming_residence_fingerprint` read the structured endpoints, observations with period, quality and note, role and notes; add the exact legacy prose parse for files without the SLK_Marker only (invalid values stay note text and warn); leave `event_id` out of the legacy claim comparison (`ignore_links` in `residence_fingerprint`).
    - _Requirements: 7.5, 7.6, 7.7, 7.7a, 7.7b, 7.8, 7.10, 7.11_

  - [x] 9.3 Write residence tests
    - Create `tests/test_gedcom_roundtrip/test_residences_roundtrip.py`: **Property 9**, **Property 18**, old-file examples (DATE only, prose NOTE lines in exact format, wrong prefix, wrong case, invalid date, file with the marker), legacy-claim example (a user-made residence exported and re-imported into the same project creates nothing), `test_slk_tag_*` for `_SLK_START`, `_SLK_END`, `_SLK_EARLIEST`, `_SLK_LATEST`, `_SLK_PREC`, `_SLK_HHROLE`, `_SLK_RNOTES`, `_SLK_OBSFROM`, `_SLK_OBSTO`, `_SLK_NOTE`.
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.7a, 7.7b, 7.8, 7.10, 7.11**

- [x] 10. Event links (last, isolated)
  - [x] 10.1 Implement the exporter side for event links
    - Create `slaktbusken/gedcom/event_links.py` with `export_name_link` and `export_endpoint_link`; add one hook each in the NAME writer and in the endpoint writer of `exporter.py`.
    - Write `_SLK_EREF` with the token of the linked event; skip the link when the event does not exist in the project.
    - _Requirements: 3.8, 16.1, 16.2_

  - [x] 10.2 Implement the importer post-pass for event links
    - Add `resolve_event_links` to `event_links.py` and one collection hook and one call in `importer.py` after `_finalize_placement_events`; set `Name.event_id` and `Endpoint.event_id` from the token map of newly created or matched events; warn for unresolved tokens.
    - No other function reads `_SLK_EREF`.
    - _Requirements: 3.8, 3.9, 7.9, 8.9, 16.1, 16.3, 16.4_

  - [x] 10.3 Write event-link tests
    - Create `tests/test_gedcom_roundtrip/test_event_links.py` (the only module for event links): **Property 10**, unresolved-token example, `test_slk_tag_eref`, and a test that the core exports and imports work when the module is bypassed.
    - Change the residence-link assertion (`event_id is None`) of `test_export_import_flytt_documented_limits` in `tests/test_dataskydd/test_round_trips.py` into an equality assertion.
    - **Validates: Requirements 3.8, 3.9, 7.9, 8.9, 15.5, 16.1, 16.2, 16.3, 16.4, 16.5, 16.6**

- [x] 11. Sources and repositories
  - [x] 11.1 Implement the exporter side for source metadata
    - In `_write_source` write `_SLK_STYPE`, `_SLK_PROV`, `_SLK_LEV`, `_SLK_KTYP` and `_SLK_SREF` with `_SLK_FLD` (JSON values).
    - _Requirements: 9.1, 9.2_

  - [x] 11.2 Implement the importer side for source metadata
    - In `_process_sources` and `map_gedcom_source` (`gedcom/translation/source_translation.py`) read the tags with `read_source_fields`; keep the old mapping for files without the tags.
    - _Requirements: 9.3, 9.4, 9.5, 9.6, 9.14_

  - [x] 11.3 Write source metadata tests
    - Create `tests/test_gedcom_roundtrip/test_sources_roundtrip.py`: **Property 11** (source part), old-file example (`test_source_translation.py` stays green), `test_slk_tag_*` for `_SLK_STYPE`, `_SLK_PROV`, `_SLK_LEV`, `_SLK_KTYP`, `_SLK_SREF`, `_SLK_FLD`.
    - **Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.14**

  - [x] 11.4 Implement the exporter side for repositories
    - In `_write_source` and a new `_write_repositories` write `0 @Rn@ REPO` records (`NAME`, `ADDR`, `PHON`, `EMAIL`, `WWW`, `NOTE`, `_SLK_RTYPE`, `_SLK_XID`) in order of first use, and `1 REPO @Rn@` with `2 CALN`, `3 MEDI`, `2 NOTE`, `_SLK_RSTYPE`, `_SLK_RIMG`, `_SLK_RPAGE`, `_SLK_RMEDNAME` under each SOUR. Write no `OBJE`.
    - _Requirements: 9.7, 9.8_

  - [x] 11.5 Implement the importer side for repositories
    - In `_process_sources` read `REPO` records and `1 REPO` references through `read_repository`; find a Repository by name, type and address or create one; share it between sources; a second import creates no Repository and no RepositoryRef; files without the marker use the standard tags only.
    - _Requirements: 9.9, 9.10, 9.11_

  - [x] 11.6 Write repository tests
    - Add to `test_sources_roundtrip.py`: **Property 11** (repository part), two sources sharing one REPO, repeated import, standard-tags-only foreign file, a check that a program ignoring every SLK_Tag still sees name, address, contact data, call number and media type, `test_slk_tag_*` for `_SLK_RTYPE`, `_SLK_XID`, `_SLK_RSTYPE`, `_SLK_RIMG`, `_SLK_RPAGE`, `_SLK_RMEDNAME`.
    - **Validates: Requirements 9.7, 9.8, 9.9, 9.10, 9.11, 9.12, 9.13**

- [x] 12. Export log
  - [x] 12.1 Implement the export log entries
    - In `_collect_omissions` and `export` add the Swedish warnings for media, place types and the Individual_Fallback (the placeholder warnings come from task 5.1); keep the omission of DNA, research, merge data and `connection_overrides`.
    - _Requirements: 1.4, 10.1, 10.2, 10.3, 10.5_

  - [x] 12.2 Write export log tests
    - Create `tests/test_gedcom_roundtrip/test_export_log.py`: warning texts, omission counts, no DNA or research lines in the output, **Property 15** (registered tags, deterministic output, parse without warnings).
    - **Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.5, 11.1, 13.4, 13.5**

- [ ] 13. Verification
  - [x] 13.1 Write the cross-version and backward-compatibility tests
    - Create `tests/test_gedcom_roundtrip/test_cross_version.py`: **Property 13** with `exporttest.ged` and generated old-format files; import of `tests/fixtures/gedcom/*.ged` and `exporttest.ged` without abort; `exporttest.ged` result equals `exporttest.json` apart from catalogued differences.
    - **Validates: Requirements 7.10, 12.4, 12.5, 12.6, 12.7, 12.8, 13.1, 13.2, 14.7**

  - [x] 13.2 Write the fixture round trip, the whole-project property and the report script
    - Create `tests/test_gedcom_roundtrip/test_fixture_roundtrip.py`: the comparison of `MergeTest.json` after export and import (counts of persons, families and events per type, marriage count 6 of 6, notes, titles, name types, partner roles and order, citations, residences, repositories), the second import creating nothing, **Property 16** over generated projects, and the catalog completeness test.
    - Create `scripts/gedcom_roundtrip_report.py` that prints the classified difference report as Markdown.
    - Add `test_slk_tag_*` for `_SLK_VERS`.
    - **Validates: Requirements 11.2, 12.1, 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.8, 14.10**

- [x] 14. Mandatory group
  - [x] 14.1 Register the group and extend the guards
    - In `tests/mandatory_groups.py` add the group `gedcom_roundtrip` ("GEDCOM-rundresa") with the modules of `tests/test_gedcom_roundtrip/` and the required tests (one per property and one per registry tag). The Dataskydd group stays mandatory and unchanged.
    - Extend `tests/reduced_example_counts.py` and `tests/test_meta/test_mandatory_groups_guard.py` so that the 100-example floor and the no-skip rule also cover `tests/test_gedcom_roundtrip/`.
    - Make `scripts/run_mandatory_tests.py` print the new group.
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.6_

  - [x] 14.2 Update the mandatory test documentation
    - Add the group to the table in `tests/MANDATORY_TESTS.md` and describe the report script.
    - _Requirements: 15.1, 15.5_

- [x] 16. Post-verification fixes (run before the final checkpoint 15)
  - [x] 16.1 Export death cause as CAUS
    - In `_write_event_detail` (`slaktbusken/gedcom/exporter.py`) write `2 CAUS <cause>` through `text_lines` for `Event.cause` on death events and every other event type that carries a cause. Verify that the importer already reads `CAUS` into `Event.cause` and fix it only if it does not.
    - In `record_identity.py` make the `slk1` profile skip `CAUS` children of event records; `legacy` stays unchanged and the golden vectors stay unchanged.
    - Change catalog entry K56 in `tests/test_gedcom_roundtrip/difference_catalog.py` from `deferred` to `fixed` and remove the cause exemption from `tests/test_gedcom_roundtrip/comparison.py`.
    - Add a round-trip test (export then import keeps `cause`) and a hash test (the record hash of an old event without `CAUS` equals the hash of the new event with `CAUS` under `slk1`) in `tests/test_gedcom_roundtrip/`. Keep the cross-version Property 13 green.
    - _Requirements: 8.10, 8.11, 12.2, 12.4, 12.5, 12.8, 14.3_

  - [x] 16.2 Fix the families_added counter
    - In `slaktbusken/gedcom/importer.py` count in `ImportResult.families_added` only families that do not exist before the import (exclude a derived foster family that is rebuilt and folded back into an existing family).
    - Add a test in `tests/test_gedcom_roundtrip/test_fixture_roundtrip.py` that re-imports the export of `MergeTest.json` into the project it came from and asserts `families_added == 0`.
    - _Requirements: 12.6, 12.9_

  - [x] 16.3 Catalog the old hash-based xref limitation
    - Add an entry for the old `@X<abs(hash(id)) % 99999>@` xrefs to `tests/test_gedcom_roundtrip/difference_catalog.py` (status `deferred`, Round_Trip class B) with the MergeTest duplicates (2 families, 2 marriages) as the description.
    - Adjust the comment in `tests/test_gedcom_roundtrip/test_cross_version.py` to reference this catalog entry and Requirement 12.10.
    - _Requirements: 12.4, 12.5, 12.10, 14.3_

- [x] 15. Final checkpoint - Run the mandatory groups and report
  - Run `python scripts/run_mandatory_tests.py` (Dataskydd and GEDCOM-rundresa) and the relevant regression tests (`python -m pytest tests/test_gedcom tests/test_gedcom_roundtrip tests/test_dataskydd`), confirm the Dataskydd group shows no regression.
  - Report to the user, before any commit, the third-party limitations (design table in "Partner representation in GEDCOM") and the remaining Round_Trip differences (catalog entries `deferred` and `app_only`).
  - Ask the user if questions arise. Do not commit.
  - _Requirements: 15.6, 15.7_

## Notes

- Every test sub-task is mandatory because the tests are part of a mandatory group; no sub-task carries the `*` postfix.
- Each task references the acceptance criteria it implements or tests.
- Task IDs are stable; the order of execution is the order of the dependency graph (priority order in the Overview).
- Tasks that write the same file are in different waves: `exporter.py` (5.1, 6.1, 3.1, 7.1, 9.1, 11.1, 11.4, 12.1, 10.1), `importer.py` (5.2, 6.2, 3.2, 5.4, 7.2, 9.2, 11.2, 11.5, 10.2) and `test_sources_roundtrip.py` (11.3, 11.6).
- Property tests use at least 100 examples and carry the comment `Feature: gedcom-roundtrip-0-3-0, Property N: <text>`.
- Task 2.3 comes first among importer tasks, because every later exporter change depends on the hash rules of Requirement 12.
- Task 10 is the only task that touches `Name.event_id` and `Endpoint.event_id`; dropping it needs no change in any other task except removing the references in 10.x.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "2.1", "2.2"] },
    { "id": 1, "tasks": ["2.3", "5.1"] },
    { "id": 2, "tasks": ["2.4", "5.2", "6.1"] },
    { "id": 3, "tasks": ["5.3", "6.2", "3.1"] },
    { "id": 4, "tasks": ["6.3", "3.2", "7.1"] },
    { "id": 5, "tasks": ["5.4"] },
    { "id": 6, "tasks": ["3.3", "7.2", "9.1"] },
    { "id": 7, "tasks": ["7.3", "9.2", "11.1"] },
    { "id": 8, "tasks": ["9.3", "11.2", "11.4"] },
    { "id": 9, "tasks": ["11.3", "11.5", "12.1"] },
    { "id": 10, "tasks": ["11.6", "12.2", "10.1"] },
    { "id": 11, "tasks": ["10.2"] },
    { "id": 12, "tasks": ["10.3", "13.1", "13.2"] },
    { "id": 13, "tasks": ["14.1", "14.2"] },
    { "id": 14, "tasks": ["16.1", "16.2"] },
    { "id": 15, "tasks": ["16.3"] }
  ]
}
```
