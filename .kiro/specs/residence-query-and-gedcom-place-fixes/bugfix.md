# Bugfix Requirements Document

## Introduction

During a triage of the test suite for the residence-periods feature, two property-based tests surfaced two distinct, confirmed defects. Both are reproducible from concrete falsifying examples, and both have a single established root cause. This spec fixes both.

**Bug 1 — GEDCOM round-trip collapses a repeated-name place hierarchy.** Found by `tests/test_model/test_residence_gedcom_roundtrip_property.py::TestGedcomRoundTripProperty::test_residence_fact_survives_gedcom_round_trip` (Property 27, residence-periods Requirement 12.9). A place hierarchy whose levels repeat a name — the falsifying example is "Ed, Ed" — exports correctly but imports back as a single flattened "Ed", losing the parent chain. The find-or-create logic matches a hierarchy level by name and type and falls back to any identically-named place regardless of its parent, so the nested level is merged onto an existing standalone place.

**Bug 2 — the residents query mislabels an unbounded-both ("odaterat") fact as "säker".** Found by `tests/test_services/test_residence_query_property.py::TestResidentsQuery::test_residents_query_property` (Property 19, residence-periods Requirements 8.2, 8.3, 8.4, 8.9). A Residence_Fact with a non-empty Certain_Core but a Possible_Span unbounded in both directions is labelled "säker" because the query checks only core overlap. The same entry is also marked "odaterat", producing the contradictory pairing "säker" + "odaterat". The falsifying example is a fact with `start.latest='1500'`, `end.earliest='1501'`, and both `start.earliest` and `end.latest` absent.

Both tests encode the correct behavior and fail on the current code, confirming the defects. Neither is to be weakened; the fixes make the production code satisfy them.

## Bug Analysis

### Current Behavior (Defect)

**Bug 1 — GEDCOM round-trip collapses a repeated-name place hierarchy**

1.1 WHEN a GEDCOM `PLAC` string has N comma-separated levels and two or more of those levels share the same name (e.g. "Ed, Ed"), AND an identically-named place already exists at a different level of the project (e.g. a standalone parentless "Ed"), THEN the importer resolves the nested level onto the existing standalone place, producing a flattened single-level place ("Ed") instead of the N-level chain

1.2 WHEN the export of a two-level hierarchy of two places both named "Ed" (place_2 with parent place_1, both named "Ed") is re-imported alongside at least one bare "Ed" residence, THEN the result is two flat, parentless places both named "Ed" with the parent/child relationship lost, so resolving the imported residence's place hierarchy yields "Ed" rather than "Ed, Ed"

**Bug 2 — the residents query mislabels an unbounded-both ("odaterat") fact as "säker"**

4.1 WHEN a Residence_Fact has a non-empty Certain_Core that overlaps the queried year AND a Possible_Span that is unbounded in both directions (both `start.earliest` and `end.latest` absent, as with `start.latest='1500'`, `end.earliest='1501'`), THEN `residents_of_place` labels its entry "säker" (LABEL_CERTAIN) because it checks only core overlap

4.2 WHEN such a fact is returned, THEN its entry carries both the "säker" label and `undated=True` (the "odaterat" marker), a contradictory combination, because the undated marker is derived from the Possible_Span being unbounded in both directions while the label ignores that property

### Expected Behavior (Correct)

**Bug 1 — GEDCOM round-trip collapses a repeated-name place hierarchy**

2.1 WHEN a GEDCOM `PLAC` string has N comma-separated levels, THEN the importer SHALL produce an N-level parent chain, even when two or more levels share the same name, so that a level is matched to an existing place only when that existing place sits at the same position in the parent chain

2.2 WHEN the hierarchy "Ed, Ed" is imported, THEN the importer SHALL create (or reuse) a child "Ed" whose parent is a distinct "Ed", so that `_resolve_place_hierarchy` of the imported residence's place returns "Ed, Ed"

**Bug 2 — the residents query mislabels an unbounded-both ("odaterat") fact as "säker"**

5.1 WHEN a Residence_Fact's Possible_Span is unbounded in both directions, THEN `residents_of_place` SHALL label its entry "möjlig" (LABEL_POSSIBLE) and set `undated=True`, REGARDLESS of whether the Certain_Core overlaps the queried year — Requirement 8.9 takes precedence over Requirement 8.2 for this fact shape (a product-owner decision resolving the conflict between the two criteria)

5.2 WHEN a Residence_Fact's Possible_Span is unbounded in both directions, THEN its entry SHALL be ordered after every entry whose Possible_Span is bounded in at least one direction, consistent with Requirement 8.9

5.3 WHEN a Residence_Fact's Possible_Span is bounded in at least one direction AND the queried year overlaps its Certain_Core, THEN `residents_of_place` SHALL label its entry "säker" — the Requirement 8.2 rule applies only to facts whose Possible_Span is not unbounded-both

### Unchanged Behavior (Regression Prevention)

**Bug 1 — GEDCOM round-trip collapses a repeated-name place hierarchy**

3.1 WHEN a distinct-name hierarchy is imported (e.g. "Ljusdal, Gävleborgs län, Sverige"), THEN the system SHALL CONTINUE TO de-duplicate correctly, so that a second residence citing the same full string reuses the same chain rather than creating a duplicate chain

3.2 WHEN a bare single-level place (e.g. "Ed") is imported, THEN the system SHALL CONTINUE TO create or reuse exactly one parentless place for it

3.3 WHEN the existing GEDCOM import and round-trip tests run, THEN they SHALL CONTINUE TO pass unchanged

**Bug 2 — the residents query mislabels an unbounded-both ("odaterat") fact as "säker"**

6.1 WHEN a fact has a Possible_Span bounded in at least one direction and a Certain_Core overlapping the queried year, THEN the system SHALL CONTINUE TO label its entry "säker" (Requirement 8.2 unchanged for this fact shape)

6.2 WHEN a fact has an empty Certain_Core (either core bound absent, or `start.latest` after `end.earliest`), THEN the system SHALL CONTINUE TO label its entry "möjlig" (Requirement 8.4 unchanged)

6.3 WHEN entries are ordered, THEN the system SHALL CONTINUE TO order "säker" before "möjlig", undated entries last, then by place display name in Swedish alphabetical order, then by person display name, then by ascending Residence_Fact `id`

6.4 WHEN `residents_of_place` reuses its per-bounds-quadruple cache to label many facts that share the same four stored bounds, THEN the cache SHALL CONTINUE TO produce correct labels after the fix, since the unbounded-both property is itself a function of those same four bounds
