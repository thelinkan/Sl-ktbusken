# Implementation Plan: GEDCOM export and round-trip data loss (release 0.3.0)

## Overview

The plan implements `design.md` in Python 3 (PySide6 project), with pytest and Hypothesis (profile `sbk`). Order: test harness first, then the foundations (text writer, tag registry, hash profile), then one exporter and importer pair per data area, then verification and registration of the mandatory group.

Every test sub-task is mandatory (no `*`), because the tests belong to the mandatory group "GEDCOM-rundresa" and must not be skippable. Test sub-tasks that change a pinned assertion of an existing test say so.

Preconditions and constraints:

- The user adds `MergeTest.json`, `exporttest.ged` and `exporttest.json` under `tests/fixtures/gedcom_roundtrip/` before task 13.1 runs (design OQ-10: confirm they hold test persons only).
- No task changes a model dataclass, the project format 0.5 or anything in person filtering (Package 2).
- No task commits to git.
- Tasks that depend on open questions follow the recommendations in `design.md`. If the user decides otherwise, the affected tasks are 8.x and 10.x (OQ-5), 6.x (OQ-12), 9.x (OQ-9), 11.x (OQ-11) and 14.1 (OQ-8).

## Tasks

- [ ] 1. Test harness and fixtures
  - [ ] 1.1 Create the fixture loader and presence check
    - Create `tests/test_gedcom_roundtrip/__init__.py`, `fixtures.py` and `test_fixture_set.py`.
    - `fixtures.py` loads `MergeTest.json` into `ProjectData`, and returns the paths of `exporttest.ged` and `exporttest.json`.
    - `test_fixture_set.py` fails (no skip) with a message that names each missing file.
    - _Requirements: 14.6, 14.9_

  - [ ] 1.2 Implement Stable_View, difference catalog and comparator
    - Create `stable_view.py`, `difference_catalog.py` and `comparison.py` in `tests/test_gedcom_roundtrip/`.
    - The catalog holds codes K1 to K42 of `design.md` with Difference_Class and status (`fixed`, `deferred`, `app_only`).
    - `compare(a, b)` returns `Difference` items and fails on a code without catalog entry.
    - Write unit tests for the person key, the event key and the stable ordering.
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

  - [ ] 1.3 Build the synthetic project and the Hypothesis strategies
    - Create `synthetic.py` with the fixture shape: heterosexual family, same-sex family, person with sex `U`, person with sex `X`, foster family (FAMC PEDI foster and EVEN Fosterhem with FAMC), an orphan marriage with partners `make/maka`, date-level citations with aspects, residences with endpoints linked to a birth and a marriage event.
    - Create `strategies.py` with project strategies for the properties of the design.
    - _Requirements: 14.6_

- [ ] 2. Foundations
  - [ ] 2.1 Implement the text writer and the parser unescape
    - Create `slaktbusken/gedcom/text_lines.py` with `text_lines` and `escape_text` (CONT per line break, CONC at 200 characters, doubled leading `@`).
    - Change `_parse_line` in `slaktbusken/gedcom/parser.py` so that `@@` in a non-pointer value reads as `@`.
    - _Requirements: 2.1, 2.3, 2.6_

  - [ ] 2.2 Implement the SLK tag registry and the tolerant readers
    - Create `slaktbusken/gedcom/slk_tags.py` with `SLK_TAG_REGISTRY` (all tags of the design table) and the total reader functions `read_citation`, `read_endpoint`, `read_partners`, `read_plinks`, `read_name_type` and `read_source_fields`.
    - Unknown `_SLK_` tags are skipped; bad values give a problem list and the standard fallback.
    - _Requirements: 11.1, 11.3, 11.4, 11.5_

  - [ ] 2.3 Implement Hash_Profile and SLK_Marker detection
    - In `slaktbusken/gedcom/translation/record_identity.py` add the `profile` parameter to `record_hash` and the `slk1` skip rules; add `ignore_links` to `residence_fingerprint`.
    - In `slaktbusken/gedcom/importer.py` read `_SLK_VERS` in `_import_file`, store `self._hash_profile`, and pass it from `_match_owner_events` and `_match_person_residences`.
    - Keep the `legacy` golden vectors unchanged and add `slk1` vectors to `record_identity_golden.py`.
    - _Requirements: 12.1, 12.2, 12.3, 7.11_

  - [ ] 2.4 Write foundation tests
    - Create `tests/test_gedcom_roundtrip/test_text_roundtrip.py` with **Property 2** (text round trip, line length at most 255).
    - Create `test_hash_profile.py` with **Property 12** and the golden vectors for both profiles.
    - Create `test_slk_tags.py` with the registry-coverage test and the fuzz skeleton of **Property 14**.
    - **Validates: Requirements 2.1, 2.3, 2.5, 11.3, 12.2, 12.3**

- [ ] 3. Persons
  - [ ] 3.1 Implement the exporter side for persons
    - In `_write_person` (`slaktbusken/gedcom/exporter.py`) write NAME with `TYPE`, `SEX U` and `_SLK_SEX X`, `TITL`, `OCCU` and `NOTE` through `text_lines`.
    - Write `_SLK_VERS 1` in `_write_head`.
    - _Requirements: 2.1, 2.2, 3.1, 4.8, 4.9, 10.4_

  - [ ] 3.2 Implement the importer side for persons
    - In `_extract_gedcom_person`, `_create_person` and `_update_person` (`slaktbusken/gedcom/importer.py`) read the name types, `_SLK_SEX`, and use one `_build_names` helper with the rules of Requirement 3 (positional fallback only without any TYPE, existing types kept on update).
    - _Requirements: 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 4.8, 2.4_

  - [ ] 3.3 Write person tests
    - Create `tests/test_gedcom_roundtrip/test_persons_roundtrip.py`: **Property 3** (name types), the sex part of **Property 5**, notes, title and occupation example tests, mixed-TYPE and update-keeps-types examples, `test_slk_tag_sex_x`.
    - **Validates: Requirements 2.2, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 4.8, 4.9**

- [ ] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Families
  - [ ] 5.1 Implement the exporter side for families
    - In `_write_family` and `_write_family_links` write the sex-based slots, `_SLK_PARTNER` with `_SLK_ROLE`, `_SLK_PLINK` with `TYPE`, and the family events through `_family_events_for` (listed events, unique-match orphans, written-once set).
    - Add `divorce_filed DIVF` and `custom_family_event` (`EVEN` with `TYPE`) and `_SLK_PART` participants.
    - Keep all PEDI and placement output byte-identical.
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 5.3_

  - [ ] 5.2 Implement the importer side for families
    - In `_create_family`, `_update_family` and `_process_family_events` read `_SLK_PARTNER`, `_SLK_PLINK` and `_SLK_PART` through the tolerant readers; keep roles on update for an equal partner set; keep husband/wife and PEDI for old files.
    - _Requirements: 1.6, 1.7, 4.5, 4.6, 4.7, 4.10, 5.4, 5.5, 5.6_

  - [ ] 5.3 Write family tests
    - Create `tests/test_gedcom_roundtrip/test_families_roundtrip.py`: **Property 1**, **Property 4**, the partner part of **Property 5**, **Property 6**, examples for heterosexual, same-sex, unknown-sex and foster families, old-file examples, `_SLK_PARTNER` mismatch.
    - Add one `test_slk_tag_*` for `_SLK_PARTNER`, `_SLK_PLINK`, `_SLK_PART`.
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.5, 1.6, 1.7, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.10, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6**

- [ ] 6. Events
  - [ ] 6.1 Implement the exporter side for events
    - In the event loop of `_write_person` and in `_write_event_detail` add the missing tags, `EVEN` with `_SLK_EVTYPE`, `_SLK_ROLE` (not for placement events), `_SLK_EID` on every event, the Individual_Fallback for orphan family events, and `_SLK_FROMPLAC` in `_write_flytt_event`.
    - _Requirements: 1.4, 8.1, 8.2, 8.3, 8.4, 8.5, 8.8, 6.11_

  - [ ] 6.2 Implement the importer side for events
    - In `_indi_event_spec`, `_create_person_events`, `_create_event` and `_create_family_event` read `_SLK_ROLE`, `_SLK_EVTYPE`, `_SLK_EID` (token map) and `_SLK_FROMPLAC`; merge participants of INDI events that share a token (OQ-12).
    - _Requirements: 1.8, 8.1, 8.6, 8.7, 8.9, 6.11_

  - [ ] 6.3 Write event tests
    - Create `tests/test_gedcom_roundtrip/test_events_roundtrip.py`: **Property 7**, the fallback example (orphan with several matching families), the shared-token example, `test_slk_tag_*` for `_SLK_EID`, `_SLK_EVTYPE`, `_SLK_ROLE`, `_SLK_FROMPLAC`.
    - Change `test_export_import_flytt_documented_limits` in `tests/test_dataskydd/test_round_trips.py`: replace `flytt[0].from_place is None` by equality of `from_place` (design "Testing Strategy").
    - **Validates: Requirements 1.4, 1.8, 6.11, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.9**

- [ ] 7. Citations
  - [ ] 7.1 Implement the exporter side for citations
    - Add `_write_citation` to `exporter.py` and use it in `_write_event_detail`, `_write_flytt_event` (without skipping `FROM_PLACE`) and the observation SOUR lines; keep `3 TEXT` for events.
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.12_

  - [ ] 7.2 Implement the importer side for citations
    - In `_create_event`, `_create_family_event` and `_derive_residence` build SourceRefs with `read_citation` and place them in the event, date, place or from_place carrier (event level when the carrier is absent).
    - _Requirements: 6.6, 6.7, 6.8, 6.9, 6.10_

  - [ ] 7.3 Write citation tests
    - Create `tests/test_gedcom_roundtrip/test_citations_roundtrip.py`: **Property 8**, QUAY mapping examples (3, 2, 1, 0 and absent), foreign-file QUAY example, `test_slk_tag_*` for `_SLK_QUAL`, `_SLK_CTX`, `_SLK_ASP`.
    - Change `test_export_import_keeps_dates_citations_and_texts` in `tests/test_dataskydd/test_round_trips.py`: replace `got.date.source_refs == []` by equality of citations per context.
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10, 6.12**

- [ ] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Residences
  - [ ] 9.1 Implement the exporter side for residences
    - In `_write_residence` add `_SLK_START`, `_SLK_END`, `_SLK_HHROLE`, `_SLK_RNOTES`, observation `QUAY`, `PAGE`, `_SLK_OBSFROM`, `_SLK_OBSTO`, `_SLK_NOTE`, `_SLK_ASP`; write `notes` and `role` through `text_lines`; keep every existing line.
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 2.6_

  - [ ] 9.2 Implement the importer side for residences
    - In `_derive_residence` and `_incoming_residence_fingerprint` read the structured endpoints, observations with period, quality and note, role and notes; add the legacy prose parse for old files (OQ-9); leave `event_id` out of the legacy claim comparison (`ignore_links` in `residence_fingerprint`).
    - _Requirements: 7.5, 7.6, 7.7, 7.8, 7.10, 7.11_

  - [ ] 9.3 Write residence tests
    - Create `tests/test_gedcom_roundtrip/test_residences_roundtrip.py`: **Property 9**, old-file examples (DATE only, prose NOTE lines), legacy-claim example (user-made residence exported and re-imported into the same project creates nothing), `test_slk_tag_*` for `_SLK_START`, `_SLK_END`, `_SLK_EARLIEST`, `_SLK_LATEST`, `_SLK_PREC`, `_SLK_HHROLE`, `_SLK_RNOTES`, `_SLK_OBSFROM`, `_SLK_OBSTO`, `_SLK_NOTE`.
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.10, 7.11**

- [ ] 10. Event links
  - [ ] 10.1 Implement the exporter side for event links
    - Write `_SLK_EREF` under NAME and under `_SLK_START` and `_SLK_END` with the token of the linked event; skip the link when the event does not exist in the project.
    - _Requirements: 3.8, 7.1_

  - [ ] 10.2 Implement the importer post-pass for event links
    - Add `_resolve_event_links` to `importer.py`, called after `_finalize_placement_events`; set `Name.event_id` and `Endpoint.event_id` from the token map of newly created or matched events; warn for unresolved tokens.
    - _Requirements: 3.8, 3.9, 7.9, 8.9_

  - [ ] 10.3 Write event-link tests
    - Create `tests/test_gedcom_roundtrip/test_event_links.py`: **Property 10**, unresolved-token example, `test_slk_tag_eref`.
    - Change the residence-link assertion in `test_export_import_flytt_documented_limits` (`event_id is None`) into an equality assertion.
    - **Validates: Requirements 3.8, 3.9, 7.9, 8.9**

- [ ] 11. Sources and repositories
  - [ ] 11.1 Implement the exporter side for sources
    - In `_write_source` write `_SLK_STYPE`, `_SLK_PROV`, `_SLK_LEV`, `_SLK_KTYP`, `_SLK_SREF` with `_SLK_FLD` (JSON values), `REPO` records and `1 REPO` with `CALN`.
    - _Requirements: 9.1, 9.2, 9.7_

  - [ ] 11.2 Implement the importer side for sources
    - In `_process_sources` and `map_gedcom_source` (`gedcom/translation/source_translation.py`) read the tags with `read_source_fields`; find or create a Repository by name; keep the old mapping for files without the tags.
    - _Requirements: 9.3, 9.4, 9.5, 9.6, 9.8, 9.9_

  - [ ] 11.3 Write source tests
    - Create `tests/test_gedcom_roundtrip/test_sources_roundtrip.py`: **Property 11**, old-file example (`test_source_translation.py` stays green), `test_slk_tag_*` for `_SLK_STYPE`, `_SLK_PROV`, `_SLK_LEV`, `_SLK_KTYP`, `_SLK_SREF`, `_SLK_FLD`.
    - **Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9**

- [ ] 12. Export log
  - [ ] 12.1 Implement the export log entries
    - In `_collect_omissions` and `export` add the Swedish warnings for media, place types and the Individual_Fallback; keep the omission of DNA, research, merge data and `connection_overrides`.
    - _Requirements: 1.4, 10.1, 10.2, 10.3, 10.5_

  - [ ] 12.2 Write export log tests
    - Create `tests/test_gedcom_roundtrip/test_export_log.py`: warning texts, omission counts, no DNA or research lines in the output, **Property 15** (registered tags, deterministic output, parse without warnings).
    - **Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.5, 11.1, 13.4, 13.5**

- [ ] 13. Verification
  - [ ] 13.1 Write the cross-version and backward-compatibility tests
    - Create `tests/test_gedcom_roundtrip/test_cross_version.py`: **Property 13** with `exporttest.ged` and generated old-format files; import of `tests/fixtures/gedcom/*.ged` and `exporttest.ged` without abort; `exporttest.ged` result equals `exporttest.json` apart from catalogued differences.
    - **Validates: Requirements 7.10, 12.4, 12.5, 12.6, 12.7, 12.8, 13.1, 13.2, 14.7**

  - [ ] 13.2 Write the fixture round trip, the whole-project property and the report script
    - Create `tests/test_gedcom_roundtrip/test_fixture_roundtrip.py`: the comparison of `MergeTest.json` after export and import (counts of persons, families and events per type, marriage count 6 of 6, notes, titles, name types, citations, residences), the second import creating nothing, **Property 16** over generated projects, and the catalog completeness test.
    - Create `scripts/gedcom_roundtrip_report.py` that prints the classified difference report as Markdown.
    - Add `test_slk_tag_*` for `_SLK_VERS`.
    - **Validates: Requirements 11.2, 12.1, 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.8, 14.10**

- [ ] 14. Mandatory group
  - [ ] 14.1 Register the group and extend the guards
    - In `tests/mandatory_groups.py` add the group `gedcom_roundtrip` ("GEDCOM-rundresa") with the modules of `tests/test_gedcom_roundtrip/` and the required tests (one per property and one per registry tag).
    - Extend `tests/reduced_example_counts.py` and `tests/test_meta/test_mandatory_groups_guard.py` so that the 100-example floor and the no-skip rule also cover `tests/test_gedcom_roundtrip/`.
    - Make `scripts/run_mandatory_tests.py` print the new group.
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.6_

  - [ ] 14.2 Update the mandatory test documentation
    - Add the group to the table in `tests/MANDATORY_TESTS.md` and describe the report script.
    - _Requirements: 15.1, 15.5_

- [ ] 15. Final checkpoint - Ensure all tests pass
  - Run `python scripts/run_mandatory_tests.py` and `python -m pytest`, confirm the Dataskydd group shows no regression, ask the user if questions arise.

## Notes

- Every test sub-task is mandatory because the tests are part of a mandatory group; no sub-task carries the `*` postfix.
- Each task references the acceptance criteria it implements or tests.
- Checkpoints give a stable state before the order of the next area; every exporter task and its importer task are in different files, so they can run in parallel in one wave.
- Property tests use at least 100 examples and carry the comment `Feature: gedcom-roundtrip-0-3-0, Property N: <text>`.
- Task 2.3 comes first among importer tasks, because every later exporter change depends on the hash rules of Requirement 12.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "2.1", "2.2"] },
    { "id": 1, "tasks": ["2.3", "3.1"] },
    { "id": 2, "tasks": ["2.4", "3.2", "5.1"] },
    { "id": 3, "tasks": ["3.3", "5.2", "6.1"] },
    { "id": 4, "tasks": ["5.3", "6.2", "7.1"] },
    { "id": 5, "tasks": ["6.3", "7.2", "9.1"] },
    { "id": 6, "tasks": ["7.3", "9.2", "10.1"] },
    { "id": 7, "tasks": ["9.3", "10.2", "11.1"] },
    { "id": 8, "tasks": ["10.3", "11.2", "12.1"] },
    { "id": 9, "tasks": ["11.3", "12.2", "13.1", "13.2"] },
    { "id": 10, "tasks": ["14.1", "14.2"] }
  ]
}
```
