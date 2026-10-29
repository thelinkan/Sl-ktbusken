# Implementation Plan

## Overview

This plan fixes two confirmed residence-periods defects. Both "bug condition exploration tests" already exist as failing property tests, so no new exploration tests are written — the fixes must make those existing tests pass unchanged:

- Bug 1: `tests/test_model/test_residence_gedcom_roundtrip_property.py::TestGedcomRoundTripProperty::test_residence_fact_survives_gedcom_round_trip` (Property 27, Requirement 12.9).
- Bug 2: `tests/test_services/test_residence_query_property.py::TestResidentsQuery::test_residents_query_property` (Property 19, Requirements 8.2, 8.3, 8.4, 8.9).

The property tests encode the correct behavior and must not be weakened. These are implementation (coding) tasks only.

## Tasks

- [ ] 1. Fix the place-translation hierarchy to preserve repeated-name levels
  - In `slaktbusken/gedcom/translation/place_translation.py`, change `_find_existing_by_name_and_type` so a nested level (when `parent_id` is provided) is matched only to an existing place with the same `(name, type, parent_place_id)` — do NOT fall back to the parent-insensitive `match_without_parent` for nested levels, as that fallback collapses a repeated-name level ("Ed" under "Ed") onto a shallower standalone "Ed".
  - Keep the name+type reuse for top-level resolution (`parent_id is None`) and for distinct-name levels, so distinct-name de-duplication and bare single-level reuse are unchanged.
  - Verify in `slaktbusken/gedcom/importer.py` `_resolve_place` that the string-keyed `_place_cache` and `PlaceMapping` persistence no longer cause "Ed" and "Ed, Ed" to converge once the builder keeps the levels distinct; adjust the importer only if resolution still collapses after the builder fix.
  - Do NOT modify the exporter or the round-trip property test.
  - _Bug_Condition: isBugCondition(plac_string) — N>=2 levels with a repeated name and an identically-named place at a different level_
  - _Expected_Behavior: an N-level PLAC string round-trips to an N-level chain; "Ed, Ed" resolves to a child "Ed" under a distinct parent "Ed"_
  - _Preservation: distinct-name hierarchies de-duplicate; a bare single-level name yields exactly one parentless place_
  - _Requirements: 1.1, 1.2, 2.1, 2.2, 3.1, 3.2, 3.3_

- [ ] 2. Fix `residents_of_place` labelling so unbounded-both overrides core overlap
  - In `slaktbusken/services/residence_query.py` `residents_of_place`, check `span.is_unbounded_both()` before applying the core-overlap rule: when the Possible_Span is unbounded in both directions, label the entry `LABEL_POSSIBLE` unconditionally; otherwise keep the existing `LABEL_CERTAIN if core overlaps else LABEL_POSSIBLE` rule.
  - Leave `undated` (already derived from `span.is_unbounded_both()`) and the sort key (undated entries last) as they are.
  - Fold the unbounded-both decision into the existing per-bounds-quadruple cached `(label, interval)` computation so the cache stays valid (the decision is a function of the same four bounds).
  - This implements the product-owner decision that Requirement 8.9 takes precedence over Requirement 8.2 for a fact with a non-empty core and an unbounded-both span (see design.md).
  - _Bug_Condition: isBugCondition(fact, year) — span.is_unbounded_both() AND core overlaps the queried year_
  - _Expected_Behavior: such an entry is "möjlig" (LABEL_POSSIBLE) with undated=True and sorts after bounded entries, regardless of core overlap_
  - _Preservation: bounded-span overlapping-core facts stay "säker"; empty-core facts stay "möjlig"; ordering and the bounds-quadruple cache stay correct_
  - _Requirements: 4.1, 4.2, 5.1, 5.2, 5.3, 6.1, 6.2, 6.3, 6.4_

- [ ] 3. Run the property tests and the broader residence suites to confirm green with no regressions
  - Run the two authoritative property tests unchanged (single-run, not watch mode):
    - `tests/test_model/test_residence_gedcom_roundtrip_property.py::TestGedcomRoundTripProperty::test_residence_fact_survives_gedcom_round_trip`
    - `tests/test_services/test_residence_query_property.py::TestResidentsQuery::test_residents_query_property`
  - Run the broader residence GEDCOM round-trip / import suites and the residence query suites to confirm no regressions.
  - If the Bug 2 query test's expected-label helper does not yet encode the 8.9-over-8.2 precedence, align that expected-label computation with the precedence (a test-expectation clarification, not a weakening — see design.md); do not relax any assertion.
  - _Requirements: 2.1, 2.2, 3.3, 5.1, 5.2, 5.3, 6.1, 6.2, 6.3, 6.4_

## Notes

- Both exploration tests already exist and fail on the current code — this confirms the bugs. Do not write new exploration tests and do not weaken the existing property tests.
- Each fix is targeted to one function; keep the blast radius minimal to protect the preservation criteria.

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "tasks": ["1", "2"],
      "description": "Fix the two defects independently (different modules)"
    },
    {
      "wave": 2,
      "tasks": ["3"],
      "description": "Run the property tests and residence suites to confirm green with no regressions"
    }
  ]
}
```
