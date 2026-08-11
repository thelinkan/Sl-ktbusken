# Implementation Plan: Residence Periods (Boende)

## Overview

The feature is built bottom-up in Python, following the existing package layout: a pure day-interval
algebra module, then the `ResidenceFact` model and its derivations, then validation, persistence,
the analysis services (coverage, inference, query), the pure edit operations, Swedish formatting,
GEDCOM mapping, and finally the PySide6 editor, dialogs and report channels that wire everything
together. Every layer is integrated into the Project as soon as it exists, so nothing is left
orphaned.

Property-based tests use Hypothesis (already a dev dependency) over shared strategies in
`tests/test_model/residence_strategies.py`. Each of the 37 correctness properties from the design
gets exactly one property test, in its own file, with `@settings(max_examples=100, deadline=None)`
and the project's tag-comment/docstring form.

## Tasks

- [ ] 1. Day-interval algebra and residence data model
  - [ ] 1.1 Create `slaktbusken/model/date_span.py`
    - `DaySpan` and `OpenSpan` frozen dataclasses, `is_valid_iso`, `expand_iso` (ÅÅÅÅ → 1 Jan–31 Dec, ÅÅÅÅ-MM → first–last day of month, ÅÅÅÅ-MM-DD → that day, `None` for absent/whitespace-only/malformed), `strictly_earlier`, `year_of`, `precision_of`, `overlaps`, `intersect`, `year_span`
    - `OpenSpan.contains_year`, `overlaps_year`, `is_unbounded_both`
    - Pure module: no Qt, no I/O, no model imports
    - _Requirements: 2.1, 2.15_

  - [ ] 1.2 Create `slaktbusken/model/residence.py` with entity and pure derivations
    - `Endpoint`, `Observation`, `ResidenceFact` dataclasses exactly as in the design data model, with `Optional[str]` bounds and `role_in_household: str = ""`
    - `EndpointKind` and `classify_endpoint`, `certain_core`, `possible_span`, `coverage_union`, `observation_span_years`, `core_aggregate`
    - All derivations return new values and leave the fact unchanged; `precision` participates in nothing
    - _Requirements: 1.1, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.13, 2.16, 4.1, 4.6, 5.1, 10.1_

  - [ ] 1.3 Create shared Hypothesis strategies in `tests/test_model/residence_strategies.py`
    - `iso_values()`, `endpoints()`, `observations()`, `residence_facts()`, `consistent_projects()`
    - Deliberately include whitespace-only bounds, length boundaries at 100/1000/5000 characters, 100 Observations, inverted bounds, empty cores, unbounded spans, one-sided observation spans, years outside 1500–2100, circular place parents
    - _Requirements: 2.1, 4.1, 10.1_

  - [ ] 1.4 Write property test for Endpoint classification
    - **Property 3: Endpoint classification is total, absence-driven and precision-independent**
    - **Validates: Requirements 2.1, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8**

  - [ ] 1.5 Write property test for day-interval derivations
    - **Property 4: Day-interval derivations match their definitions and mutate nothing**
    - **Validates: Requirements 2.13, 2.15, 2.16**

- [ ] 2. Project collection and identifiers
  - [ ] 2.1 Add the `residences` collection and residence id prefix
    - `ProjectData.residences: list[ResidenceFact] = field(default_factory=list)` after `events`, empty for a new Project, preserving insertion order
    - `IDGenerator._PREFIXES["residence"] = "residence_"` so ids are unique project-wide and never reused
    - _Requirements: 1.2, 1.12_

  - [ ] 2.2 Write property test for collection order and identifier uniqueness
    - **Property 6: Project order is preserved and identifiers are unique and never reused**
    - **Validates: Requirements 1.2, 1.12**

- [ ] 3. Validation: errors and warning findings
  - [ ] 3.1 Implement `validate_residence` in `slaktbusken/model/validators.py`
    - Return `list[str]` of Swedish error messages exactly per the design table, in the documented multiplicity
    - Blank `person_id`/`place_id` suppresses the missing-reference message for that same field; place type, duplicate person+place combinations and unknown `precision` values yield no error
    - _Requirements: 1.5, 1.6, 1.7, 1.11, 2.9, 2.10, 2.11, 2.12, 2.14, 4.2, 4.4, 4.5, 4.12, 10.6_

  - [ ] 3.2 Wire residence validation into `ValidationService`
    - `_validate_residence` wrapping the message list into `ValidationError` records with `entity_type="Boende"`, iterated over `project_data.residences` in `validate_project`
    - _Requirements: 1.3, 1.4, 1.10, 1.13, 16.1_

  - [ ] 3.3 Write property test for clean validation of well-formed facts
    - **Property 1: A well-formed Residence_Fact validates clean**
    - **Validates: Requirements 1.3, 1.4, 1.10, 1.13, 2.2, 2.8, 4.6, 4.11, 6.1, 10.2, 16.1, 18.3, 18.8, 18.13**

  - [ ] 3.4 Write property test for error messages and multiplicity
    - **Property 2: Every violation yields its exact Swedish message with the required multiplicity**
    - **Validates: Requirements 1.5, 1.6, 1.7, 1.11, 2.9, 2.10, 2.11, 2.12, 2.14, 4.2, 4.4, 4.5, 4.12, 10.6**

  - [ ] 3.5 Create `slaktbusken/services/residence_validation.py`
    - `ResidenceFinding` record with `severity`, `residence_findings` (start/end window overlap, duplicate source on one fact, evidence outside the recorded period), `overlap_findings` (same-person unordered pairs, strict core overlap at the coarser core precision, same-place and different-place messages, {plats A} ordering and finding order), `flytt_link_findings`
    - _Requirements: 2.17, 4.13, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 16.9, 18.10_

  - [ ] 3.6 Write property test for single-fact warning findings
    - **Property 5: Single-fact warning findings appear exactly when their condition holds**
    - **Validates: Requirements 2.17, 4.13, 6.9, 16.9**

  - [ ] 3.7 Write property test for overlap findings
    - **Property 16: Overlap findings pair, message and order deterministically**
    - **Validates: Requirements 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8**

- [ ] 4. Checkpoint - model and validation
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Flytt event type, aspects and deletion behaviour
  - [ ] 5.1 Add the `flytt` event type and `Event.from_place`
    - `INDIVIDUAL_EVENT_TYPE_LABELS["flytt"] = "Flytt"`; `from_place: Optional[PlaceRef] = None` following the `cause_of_death` pattern; absent `place`, absent `from_place` or both absent are error-free; event validator returns the same-place warning finding
    - _Requirements: 18.1, 18.2, 18.3, 18.7_

  - [ ] 5.2 Register residence and flytt source aspects
    - `ENTITY_SOURCE_ASPECTS["residence"]` = place/period/household_role/household_members with labels Plats, Period, Hushållsroll, Hushållsmedlemmar; `EVENT_SOURCE_ASPECTS["flytt"]` = date/from_place/to_place with labels Datum, Från, Till
    - _Requirements: 4.14, 18.5_

  - [ ] 5.3 Write unit tests for the constant registrations and dataclass defaults
    - Aspect lists and labels, the `flytt` label, the `from_place` field shape, `ResidenceFact`/`Endpoint`/`Observation` defaults
    - _Requirements: 1.1, 4.14, 18.1, 18.2, 18.5_

  - [ ] 5.4 Extend `slaktbusken/services/delete_service.py`
    - Person deletion removes that person's Residence_Facts with their Observations and leaves all others unchanged; Event deletion clears `event_id` on every referencing Endpoint while keeping bounds and deleting no fact; `find_residence_dependencies(place_id, data)` returns one blocking entry per referencing fact; a place referenced by a Flytt_Event `from_place` blocks as one referenced by `place`
    - _Requirements: 1.8, 1.9, 3.11, 18.17_

  - [ ] 5.5 Write property test for deletion cascade, clearing and blocking
    - **Property 7: Deletion cascades, clears and blocks as specified**
    - **Validates: Requirements 1.8, 1.9, 3.11, 18.17**

- [ ] 6. Persistence and migration
  - [ ] 6.1 Extend `slaktbusken/persistence/serialization.py` for residences
    - `"residences"` in `entity_fields` written in stored order; `_ENTITY_MAP`, `_NESTED_LIST_TYPES` and `_NESTED_OPTIONAL_TYPES` entries for `ResidenceFact`, `Observation`, `Endpoint`, `SourceRef` and `(Event, "from_place")`
    - Optional load log: unknown fields ignored and logged with the fact `id`; unresolved `person_id`, `place_id`, `source_ref.source_id`, `event_id` kept, logged and left to the validator
    - _Requirements: 13.1, 13.2, 13.5, 13.7_

  - [ ] 6.2 Handle absent, null and malformed residence sections on load
    - Missing or `null` `residences` yields zero elements with zero errors; a present non-list raises `CorruptedFileError` with "Filens boendeavsnitt har ett ogiltigt format och kunde inte läsas." before any state is replaced
    - _Requirements: 13.3, 13.6_

  - [ ] 6.3 Bump the format version and register the 0.1 → 0.2 migration
    - `MigrationManager.CURRENT_VERSION` and `file_io.CURRENT_VERSION` become "0.2"; the migration adds `residences: []` when the key is missing, leaves an existing collection unchanged, and is a no-op on already-current data; `UnsupportedVersionError` begins with "Filen skapades med en nyare version av Släktbusken och kan inte öppnas."
    - _Requirements: 13.4, 13.8_

  - [ ] 6.4 Write property test for the serialization round trip
    - **Property 28: A Residence_Fact survives a serialization round trip**
    - **Validates: Requirements 13.1, 13.2**

  - [ ] 6.5 Write property test for tolerant loading
    - **Property 29: Loading tolerates every malformed or dangling residence section**
    - **Validates: Requirements 13.3, 13.5, 13.6, 13.7**

  - [ ] 6.6 Write property test for migration idempotence
    - **Property 30: The residences migration is idempotent**
    - **Validates: Requirements 13.4**

- [ ] 7. Checkpoint - persistence
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Coverage analysis and person checks
  - [ ] 8.1 Create `slaktbusken/services/residence_coverage.py` with gap computation
    - `CoverageGap`, `OpenEndpointSuggestion`, `TimelineGap` records; `coverage_gaps` returning the maximal runs of years absent from the coverage union between the lowest `observed_from` and highest `observed_to`, ordered by first uncovered year, with `splittable`; zero gaps for zero/one Observation or a complete union; nothing mutated
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.10, 16.13_

  - [ ] 8.2 Write property test for coverage union and gaps
    - **Property 12: Coverage union and coverage gaps are exact, maximal and non-mutating**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 16.13**

  - [ ] 8.3 Implement gap suggestion phrasing and candidate volumes
    - Multi-year and single-year forms, parish and series from the `church_book` fields of the Source cited by the Observation whose covered years end immediately before the gap, absent values omitted with their separating space, at most five matching candidate Sources appended in ascending first-year order
    - _Requirements: 5.5, 5.6, 5.14_

  - [ ] 8.4 Write property test for gap suggestion phrasing
    - **Property 13: Gap suggestions are phrased and sourced as specified**
    - **Validates: Requirements 5.5, 5.6, 5.14**

  - [ ] 8.5 Implement open-endpoint suggestions, timeline gaps and `analyze_person`
    - One suggestion per open bound naming "början"/"slutet", at most two per fact; timeline gaps as the maximal runs of years contained in no Possible_Span with unbounded directions covering everything and birth/death years excluded; prebuilt indexes passed in once per run
    - _Requirements: 5.7, 5.8, 5.15_

  - [ ] 8.6 Create `slaktbusken/services/checks/residence_checks.py` and wire the check engine
    - `CheckFinding` records ordered by first uncovered year ascending with open-endpoint findings last; three new `LogicCheckConfig` flags `residence_coverage_gaps`, `residence_open_endpoints`, `residence_timeline_gaps` defaulting to `True`, registered in the Person_Check_Engine
    - _Requirements: 5.9_

  - [ ] 8.7 Write property test for suggestion completeness and ordering
    - **Property 14: Open-endpoint, timeline-gap and person-check reporting is complete and ordered**
    - **Validates: Requirements 5.7, 5.8, 5.9, 5.15**

- [ ] 9. Inferred tightening from neighbours
  - [ ] 9.1 Create `slaktbusken/services/residence_inference.py`
    - `DerivedBound`, `InferenceResult`, `infer_bounds` computing neighbour, birth and death candidates in a single pass from stored values only, resolving competitors by widest-interval comparison, returning winners in their stored ISO form, dropping contradicting candidates with the finding "Härlett värde motsäger inmatat värde.", mutating and persisting nothing
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.10, 7.12_

  - [ ] 9.2 Write property test for inference
    - **Property 17: Inference derives from stored data only, idempotently, and never contradicts**
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.10, 7.12**

- [ ] 10. Residence query service
  - [ ] 10.1 Create `slaktbusken/services/residence_query.py` with `residents_of_place`
    - `ResidentEntry` carrying person/place identifiers and displays, rendered interval, label, `role_in_household` as empty rather than omitted, `undated`, `place_chain`; one entry per matching fact with no merging; "säker"/"möjlig" labelling; both-sides-unbounded spans matching every year, labelled "möjlig" with "odaterat" and sorting last; no lifespan clamping; breadth-first descendant walk to 10 levels with a visited set; place and residence indexes built once per call
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.9, 8.11, 15.9_

  - [ ] 10.2 Implement `residence_timeline` and `residents_grouped_by_role`
    - Total, stable ordering by `start.earliest`, `start.latest`, `end.earliest`, `end.latest` with absent sorting first, then place name, then `id`; role grouping on exact stored text with empty roles in a final "Roll saknas" group; household composition derived only through this module with no household entity
    - _Requirements: 8.7, 8.8, 8.10_

  - [ ] 10.3 Write property test for the residents query
    - **Property 19: The residents query returns, labels and orders entries correctly**
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.9, 8.10**

  - [ ] 10.4 Write property test for the person residence timeline
    - **Property 20: The person residence timeline is a total, stable order**
    - **Validates: Requirements 8.7**

- [ ] 11. Checkpoint - analysis services
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Pure edit operations
  - [ ] 12.1 Create `slaktbusken/services/residence_edit_ops.py` with `prefill_span_from_years`
    - Accept a single four-digit year in 1500–2100 or two such years in ascending order separated by a hyphen or en dash with any surrounding spaces; return `None` otherwise; never write back to the Source `years` value
    - _Requirements: 4.1, 4.7, 4.8, 4.9, 4.10, 9.2_

  - [ ] 12.2 Write property test for year prefill
    - **Property 11: Year prefill parses the Source years value and never overwrites user input**
    - **Validates: Requirements 4.1, 4.7, 4.8, 4.9, 4.10, 9.2**

  - [ ] 12.3 Implement `attach_observations` and `remove_observation`
    - Append in order; tighten `start.latest` to `min(observed_from)` and `end.earliest` to `max(observed_to)` only when absent or looser; never touch `start.earliest`/`end.latest`; removal keeps survivors byte-identical and in relative order and recomputes a core bound only when it equals the pre-removal aggregate
    - _Requirements: 4.3, 9.5, 16.3, 16.4, 16.7, 16.8_

  - [ ] 12.4 Write property test for observation order
    - **Property 10: Observation order is preserved through every list operation**
    - **Validates: Requirements 4.3, 16.12**

  - [ ] 12.5 Write property test for core tightening
    - **Property 31: Observations tighten the documented core and never touch the outer bounds**
    - **Validates: Requirements 9.5, 16.3, 16.4, 16.5, 16.6, 16.9, 16.11**

  - [ ] 12.6 Write property test for observation removal
    - **Property 32: Removal preserves survivors and hand-entered bounds**
    - **Validates: Requirements 16.7, 16.8**

  - [ ] 12.7 Implement `use_as_exact_start` and `use_as_exact_end`
    - Set both start bounds to `observed_from` and both end bounds to `observed_to`; invoked only explicitly, never automatically
    - _Requirements: 16.10, 16.11_

  - [ ] 12.8 Write property test for the exact-bound actions
    - **Property 33: The exact-bound actions are the only route from an Observation to an outer bound**
    - **Validates: Requirements 16.10**

  - [ ] 12.9 Implement `split_at_gap` and `ResidenceSplitError`
    - Partition Observations by the gap, assign new ids, copy `person_id`/`place_id`/`role_in_household`/`notes`, keep the original `start` on the first and `end` on the second, set the first `end.earliest` and the second `start.latest` from the assigned Observations, leave the first `end.latest` and second `start.earliest` absent, raise with the required message when one side has no Observation
    - _Requirements: 5.10, 5.11, 5.12, 5.13, 5.16_

  - [ ] 12.10 Write property test for splitting
    - **Property 15: Splitting partitions, re-bounds and conserves**
    - **Validates: Requirements 5.10, 5.11, 5.12, 5.13, 5.16**

  - [ ] 12.11 Implement `merge` and `ResidenceMergeError`
    - Take the `start` of the timeline-earlier fact and the `end` of the other with all five Endpoint fields unchanged, union the Observations ordered by `observed_from` with none discarded, keep the earlier `role_in_household` and append the other to `notes` with the required prefix, retain both notes texts, assign a new id, remove both originals, re-derive only the core bounds, refuse on differing place or person with the required messages, and report the >10-year separation warning
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 17.8, 17.10, 17.11, 17.15_

  - [ ] 12.12 Write property test for merging
    - **Property 34: Merging composes two facts and refuses or warns as specified**
    - **Validates: Requirements 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 17.8, 17.10, 17.11, 17.15**

  - [ ] 12.13 Write property test for the split/merge inverse relation
    - **Property 35: Splitting inverts merging**
    - **Validates: Requirements 17.9, 17.12**

  - [ ] 12.14 Implement merge-offer detection and its suppression
    - Offer the merge when an attached Observation covers every separating year; withhold the offer and report no gap when a Flytt_Event of that person is dated inside the separation or another fact of that person at a different place overlaps it; declining leaves both facts unchanged apart from the new Observation
    - _Requirements: 17.13, 17.14_

  - [ ] 12.15 Write property test for merge offers and suppression
    - **Property 36: Merge offers appear and are suppressed by documented absence**
    - **Validates: Requirements 17.13, 17.14**

  - [ ] 12.16 Implement `plan_bulk_attach`
    - `BulkRequest`/`BulkPlan`; parse with `parse_multi_line` in line order, enforce the 50-line / 20 000-character / 20-person limits before doing anything with the exceeded limit named, match existing Sources on `source_type` plus the six trimmed case-insensitive `structured_reference` values with absent equal to empty, preselect per person the best-overlapping existing fact with the collection-order tie-break, collect unparsed lines and the five summary counts
    - _Requirements: 9.1, 9.3, 9.4, 9.6, 9.7, 9.8, 9.10_

  - [ ] 12.17 Write property test for bulk entry
    - **Property 21: Bulk entry applies wholly or not at all**
    - **Validates: Requirements 9.1, 9.3, 9.4, 9.6, 9.7, 9.8, 9.9, 9.10**

- [ ] 13. Checkpoint - edit operations
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 14. Swedish formatting and role storage
  - [ ] 14.1 Add the Residence_Formatter to `slaktbusken/ui/swedish_locale.py`
    - `format_residence_endpoint`, `format_residence_interval`, `format_residence_line`, `format_observation_span`; the five endpoint wordings, "okänd period" for two unknown endpoints, a single unspaced en dash U+2013 rather than `format_date_range`, stored month/day forms without truncation, role appended as ", {role}" with no separator or trailing whitespace when empty
    - _Requirements: 10.8, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.11, 11.12, 11.13_

  - [ ] 14.2 Write property test for interval rendering
    - **Property 23: The Residence_Formatter renders each classification pair distinguishably**
    - **Validates: Requirements 10.8, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.11, 11.12, 11.13**

  - [ ] 14.3 Add `normalize_role_in_household` to `slaktbusken/model/residence.py`
    - Trim leading and trailing whitespace and preserve every remaining character, internal whitespace, letter case and å/ä/ö with no capitalization, case folding, substitution or normalization; whitespace-only or empty becomes an empty value; accept exactly 100 code points after trimming
    - _Requirements: 10.1, 10.4, 10.5, 10.7_

  - [ ] 14.4 Write property test for role storage
    - **Property 22: role_in_household is stored trimmed and otherwise byte-exact**
    - **Validates: Requirements 10.1, 10.4, 10.5, 10.7**

- [ ] 15. GEDCOM export and import
  - [ ] 15.1 Write RESI structures in `slaktbusken/gedcom/exporter.py`
    - One level 1 RESI per fact under its person's INDI with at most one DATE line (FROM/TO, FROM, TO or none), a PLAC line from the existing `_resolve_place_hierarchy`, one labelled NOTE per `start.earliest`, `end.latest`, non-empty `role_in_household` and non-empty `notes`, one SOUR line per Observation whose Source resolves to an exported record each with an `observed_from`/`observed_to` NOTE, ISO→GEDCOM date conversion with the "ABT " prefix for approximate precision, and the single observation-notes log entry
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.10, 12.11_

  - [ ] 15.2 Write Flytt events in the exporter
    - `EVEN` with `TYPE Flytt`, a `DATE` line when present, the destination `PLAC` when `place` is present, the origin as a labelled `NOTE` with the structure loss recorded in the export log
    - _Requirements: 18.14, 18.15_

  - [ ] 15.3 Write property test for GEDCOM export
    - **Property 25: GEDCOM export writes the specified RESI and Flytt structures**
    - **Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.10, 12.11, 18.14, 18.15**

  - [ ] 15.4 Read RESI and Flytt structures in `slaktbusken/gedcom/importer.py`
    - Exactly one Residence_Fact and no Event per RESI regardless of header version; FROM/TO sets the core bounds, BET/AND yields a start window with an unknown end, a plain DATE sets both core bounds, a missing or uninterpretable DATE yields two unknown Endpoints while keeping the place and SOUR-derived Observations and logging the required warning; `EVEN` with case-insensitive `TYPE Flytt` becomes a `flytt` Event with resolved `place` and absent `from_place`
    - _Requirements: 12.7, 12.8, 12.12, 12.13, 18.16_

  - [ ] 15.5 Write property test for GEDCOM import
    - **Property 26: GEDCOM import maps every DATE line form to the specified Endpoints**
    - **Validates: Requirements 12.7, 12.8, 12.12, 12.13, 18.16**

  - [ ] 15.6 Write property test for the GEDCOM round trip
    - **Property 27: A Residence_Fact survives a GEDCOM round trip**
    - **Validates: Requirements 12.9**

- [ ] 16. Checkpoint - formatting and GEDCOM
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 17. Residence editor, dialogs and place deletion refusal
  - [ ] 17.1 Create `slaktbusken/ui/editors/residence_editor.py`
    - `ResidenceEditor(QWidget)` with the four bound fields labelled "Tidigast början", "Senast början", "Tidigast slut", "Senast slut" accepting the three ISO forms or being left empty; the free-text "Roll i hushållet" field with non-binding project suggestions and the over-100-character refusal keeping the entered text; the Observation table ordered by `observed_from` then `observed_to` showing source title, span and `page_note`, sized for at least 15 untruncated rows
    - _Requirements: 10.3, 10.6, 16.2, 16.12_

  - [ ] 17.2 Add the per-Endpoint Event selectors
    - Empty first choice followed by the person's Events ordered by date with undated last, labelled with the Swedish event type label plus the formatted date; dated selection writes `event_id`, `earliest`, `latest`, `precision`, undated selection writes only `event_id`, the empty choice clears only `event_id`; the date-mismatch, missing-event and wrong-side messages, with no wrong-side message for a Flytt_Event; bounds stay editable with `event_id` unchanged; "Från"/"Till" selectors for Flytt events
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 18.6, 18.9, 18.11_

  - [ ] 17.3 Write property test for Endpoint event linking
    - **Property 8: Linking an Endpoint to an Event writes exactly the specified fields**
    - **Validates: Requirements 3.3, 3.4, 3.6, 3.8, 18.9, 18.11**

  - [ ] 17.4 Write property test for the Endpoint event selector
    - **Property 9: The Endpoint Event selector lists, labels and advises correctly**
    - **Validates: Requirements 3.1, 3.2, 3.7, 3.9**

  - [ ] 17.5 Wire the edit operations and warning behaviour into the editor
    - "Dela boendet här", "Slå samman boenden", "Använd som exakt början", "Använd som exakt slut", "Skapa flytt mellan boendena" as thin wrappers over the pure operations applied to staging copies swapped in as one step; save a warning-only fact retaining every entered value and display each warning; the merge-offer and separation confirmations
    - _Requirements: 5.10, 6.9, 16.5, 16.6, 16.9, 17.1, 17.10, 17.13, 17.15, 18.12_

  - [ ] 17.6 Write property test for Flytt place citation, consistency and linking
    - **Property 37: Flytt places are cited independently, checked for consistency, and linkable in one action**
    - **Validates: Requirements 18.4, 18.7, 18.10, 18.12**

  - [ ] 17.7 Create `slaktbusken/ui/dialogs/tighten_bounds_dialog.py` and the härlett display
    - One preselected, individually deselectable row per derived bound showing endpoint, bound name, the stored value or "okänt", the proposed value and its origin; nothing written until confirmation and only selected rows written, leaving `precision`, `event_id`, `note` and Observations alone; derived values for absent bounds shown read-only with the "härlett" suffix and never saved; "Inga härledda värden att föreslå." with no dialog for zero derived bounds
    - _Requirements: 7.7, 7.8, 7.9, 7.11_

  - [ ] 17.8 Write property test for confirmed derived-bound writes
    - **Property 18: Derived bounds reach storage only through confirmed, selected rows**
    - **Validates: Requirements 7.7, 7.8, 7.9**

  - [ ] 17.9 Create `slaktbusken/ui/dialogs/residents_dialog.py`
    - Place and year query over `residents_of_place` with the role grouping view and the place chain column
    - _Requirements: 8.1, 8.5, 8.6, 8.10_

  - [ ] 17.10 Add the bulk paste panel to the residence editor
    - Paste field, candidate list with prefilled spans and unselectable incomplete candidates, the "Kunde inte tolkas" section truncated at 200 characters, atomic application of the plan through deep copies with the all-or-nothing failure message, and the Swedish summary of the five counts
    - _Requirements: 9.1, 9.2, 9.3, 9.5, 9.6, 9.8, 9.9, 9.10_

  - [ ] 17.11 Refuse place deletion with residence dependencies in the Place_Editor
    - Call `find_residence_dependencies` before the existing event warning and refuse with one blocking entry per referencing fact, leaving the place and the `residences` collection unchanged
    - _Requirements: 1.9, 18.17_

  - [ ] 17.12 Add the "Boenden" tab to the Person editor
    - Insert the `ResidenceEditor` programmatically following the `FotoTab` pattern, with the Boende list, creation of a new fact for the active person, and the residents dialog entry point
    - _Requirements: 1.1, 16.1, 16.2_

- [ ] 18. Report and map channels
  - [ ] 18.1 List residences in the Ansedel report
    - Place, interval from the formatter and `role_in_household`, ordered by `start.earliest`, then `start.latest` with absent sorting earlier, then place display name
    - _Requirements: 11.7, 11.8_

  - [ ] 18.2 List observations in the Källrapport report
    - Each Observation under its fact with the source title and its own span rendered as "1866–1870" or "1866", ordered by `observed_from`, then `observed_to`, then list position
    - _Requirements: 11.7, 11.9_

  - [ ] 18.3 Include residence places in the Geographic report and `map_data_service`
    - Each place labelled with the formatter's interval string, in the timeline order of criterion 11.10
    - _Requirements: 11.7, 11.10_

  - [ ] 18.4 Render residence intervals in the person list
    - Read the interval string from the formatter with no channel-local wording, abbreviation or truncation
    - _Requirements: 11.7_

  - [ ] 18.5 Write property test for channel consistency
    - **Property 24: Every channel renders through the formatter and orders identically**
    - **Validates: Requirements 11.7, 11.8, 11.9, 11.10**

- [ ] 19. Worked examples and performance budgets
  - [ ] 19.1 Write unit tests for the fully accounted sequence
    - Anders at Place A and Place B with the stated derivations, zero overlap and timeline findings, the single open-endpoint suggestion, the rendered strings, the empty 1850 query and the timeline order
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.8, 14.9_

  - [ ] 19.2 Write unit tests for the both-endpoints-open example
    - Brita at Place C with zero errors and findings, two open-endpoint suggestions, the rendered "senast 1840–tidigast 1846" string, the "säker"/"möjlig" query answers, the derived core and unbounded span, and zero coverage gaps
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7, 15.8, 15.9_

  - [ ] 19.3 Write timed tests for the three performance budgets
    - A check run over 10 000 Residence_Facts within 5 seconds, inference for a person with 200 facts within 1 second, and a residents query over 50 000 facts / 20 000 persons / 5 000 places within 1 second
    - _Requirements: 5.9, 7.1, 8.11_

- [ ] 20. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each of the 37 correctness properties from the design has exactly one property test task, placed
  directly after the code it validates so errors surface early
- Property tests use Hypothesis with `@settings(max_examples=100, deadline=None)` and the project's
  `Feature: residence-periods, Property {n}` tag comment plus the `**Validates: Requirements X.Y**`
  docstring line
- Test files follow the existing layout: `tests/test_model/`, `tests/test_services/`,
  `tests/test_persistence/`, `tests/test_gedcom/`, `tests/test_ui/`, `tests/test_reports/`
- Requirement 8.8 has no computable assertion; it is honoured by the absence of a household
  dataclass and by household composition being reachable only through `residence_query`
- Run the suite with `python -m pytest` (single execution, no watch mode)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "5.2"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["1.3", "3.1", "14.1"] },
    { "id": 3, "tasks": ["1.4", "1.5", "2.2", "3.2", "3.3", "3.4", "3.5", "5.1", "6.1", "8.1", "10.1", "12.1", "14.2"] },
    { "id": 4, "tasks": ["3.6", "3.7", "5.4", "6.2", "8.3", "9.1", "10.2", "12.2", "12.3", "14.3"] },
    { "id": 5, "tasks": ["5.3", "5.5", "6.3", "8.2", "8.4", "8.5", "9.2", "10.3", "10.4", "12.4", "12.7", "14.4", "15.1", "15.4", "18.1", "18.2", "18.3", "18.4"] },
    { "id": 6, "tasks": ["6.4", "6.5", "6.6", "8.6", "12.5", "12.6", "12.8", "12.9", "15.2", "15.5", "18.5"] },
    { "id": 7, "tasks": ["8.7", "12.10", "12.11", "15.3", "15.6", "17.1"] },
    { "id": 8, "tasks": ["12.12", "12.14", "17.2", "17.7", "17.9", "17.11"] },
    { "id": 9, "tasks": ["12.13", "12.15", "12.16", "17.3", "17.4", "17.5", "17.8", "17.12"] },
    { "id": 10, "tasks": ["12.17", "17.6", "17.10", "19.1", "19.2", "19.3"] }
  ]
}
```
