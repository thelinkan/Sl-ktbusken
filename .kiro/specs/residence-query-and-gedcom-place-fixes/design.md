# Residence Query and GEDCOM Place Fixes Bugfix Design

## Overview

This spec fixes two confirmed residence-periods defects, both surfaced by existing property-based tests during a test-suite triage:

- **Bug 1**: GEDCOM round-trip collapses a repeated-name place hierarchy. The place find-or-create logic matches a hierarchy level by name and type and falls back to any identically-named place regardless of its parent, so a nested level ("Ed" under "Ed") is merged onto a pre-existing standalone "Ed", flattening the chain on import.
- **Bug 2**: The residents query labels a fact "säker" whenever its Certain_Core overlaps the queried year, without first checking whether the Possible_Span is unbounded in both directions. A both-sides-unbounded fact is simultaneously marked "odaterat", yielding the contradictory "säker" + "odaterat" pair.

Both root causes are already established. The fixes are targeted and must leave the two property tests (which encode the correct behavior) passing unchanged, along with the broader residence GEDCOM and query suites.

## Glossary

- **Bug_Condition (C)**: The condition that triggers a bug. Bug 1: importing a `PLAC` string with a repeated name while an identically-named place exists at a different level. Bug 2: a Residence_Fact whose Possible_Span is unbounded in both directions while its Certain_Core overlaps the queried year.
- **Property (P)**: The desired behavior for buggy inputs. Bug 1: the N-level chain round-trips intact. Bug 2: the entry is labelled "möjlig" + "odaterat" and sorts last.
- **Preservation**: Behavior that must remain unchanged — distinct-name hierarchy de-duplication, bare single-level places, and existing GEDCOM tests (Bug 1); bounded-span "säker" labelling, empty-core "möjlig" labelling, and ordering (Bug 2).
- **F / F'**: The original (unfixed) and fixed functions.
- **PLAC string**: A GEDCOM place value, comma-separated from most specific to least specific (e.g. "Ljusdal, Gävleborgs län, Sverige").
- **map_place_to_hierarchy**: The function in `slaktbusken/gedcom/translation/place_translation.py` that builds the App_JSON Place parent chain for a GEDCOM place.
- **_find_existing_by_name_and_type**: The private helper in the same module that locates an existing Place for a given level; its parent-insensitive fallback is the Bug 1 root cause.
- **map_place / _resolve_place**: The TranslationManager facade (`.../translation/__init__.py`) and the importer method (`slaktbusken/gedcom/importer.py`) that drive place resolution and cache/persist mappings.
- **residents_of_place**: The query in `slaktbusken/services/residence_query.py` that returns, labels, and orders resident entries; its label computation is the Bug 2 root cause.
- **Certain_Core**: The documented sub-interval `start.latest` .. `end.earliest`; empty when either bound is absent or inverted.
- **Possible_Span**: The widest possible interval `start.earliest` .. `end.latest`, unbounded in any direction whose bound is absent. `is_unbounded_both()` is true when both outer bounds are absent.

## Bug Details

### Bug 1 — Bug Condition

The bug manifests when a GEDCOM `PLAC` string contains N comma-separated levels, two or more of which share the same name, and an identically-named place already exists elsewhere in the project at a different position in the parent chain. In `map_place_to_hierarchy`, each level is resolved via `_find_existing_by_name_and_type(name, place_type, parent_id, existing_places)`. That helper prefers a match on `(name, type, parent_id)` but, when none exists, falls back to the first place matching only `(name, type)` — ignoring the parent chain entirely (its `match_without_parent` return). So the nested "Ed" (parent = another "Ed") is matched to the pre-existing standalone "Ed", the parent chain is dropped, and the hierarchy flattens.

The importer compounds this at `_resolve_place`: it caches resolved IDs by the normalized place string and persists a `PlaceMapping` whose display name is `normalized.split(",")[0]`. Once the collapsed mapping is cached/persisted, both "Ed" and "Ed, Ed" can map to the same place, so the flattening persists across re-import.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type {plac_string: string, existing_places: list[Place]}
  OUTPUT: boolean

  levels := split_and_strip(input.plac_string, ",")
  RETURN count(levels) >= 2
         AND some_name_repeats_across_levels(levels)
         AND EXISTS place IN input.existing_places
             WHERE place.name == some_repeated_level_name
             AND place.parent_place_id != expected_parent_for_that_level
END FUNCTION
```

#### Examples

- **"Ed, Ed" with a pre-existing standalone "Ed"**: exporter writes `2 PLAC Ed` and `2 PLAC Ed, Ed`; import yields two parentless "Ed" places (chain lost) — expected: a child "Ed" whose parent is a distinct "Ed", resolving to "Ed, Ed".
- **"Ljusdal, Gävleborgs län, Sverige" (distinct names)**: resolves to a 3-level chain and a second identical citation reuses it — correct, no bug condition.
- **Bare "Ed" (single level)**: resolves to exactly one parentless place — correct, no bug condition.

### Bug 2 — Bug Condition

The bug manifests when a Residence_Fact has a Certain_Core that overlaps the queried year AND a Possible_Span that is unbounded in both directions. In `residents_of_place`, the label is computed as `LABEL_CERTAIN if core is not None and overlaps(core, queried_year) else LABEL_POSSIBLE`, with no check of `span.is_unbounded_both()`. The entry's `undated` field is then set from `span.is_unbounded_both()`, so an unbounded-both fact with an overlapping core is labelled "säker" and marked "odaterat" at once.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type {fact: ResidenceFact, year: int}
  OUTPUT: boolean

  span := possible_span(input.fact)
  core := certain_core(input.fact)
  RETURN span.is_unbounded_both()
         AND core IS NOT None
         AND overlaps(core, year_span(input.year))
END FUNCTION
```

#### Examples

- **`start.latest='1500'`, `end.earliest='1501'`, outer bounds absent**: core = 1500-12-31 .. 1501-01-01 (non-empty), Possible_Span unbounded both → current label "säker" + "odaterat"; expected "möjlig" + "odaterat".
- **Place C from residence-periods Requirement 10 (Certain_Core 1840–1846, Possible_Span unbounded both)**: expected "möjlig" for any queried year (criterion 5/6/7 of that requirement) — same shape, confirming the 8.9-over-8.2 resolution.
- **Bounded span with overlapping core (e.g. `start.earliest='1840'`)**: label "säker" — correct, no bug condition.
- **Empty core (`start.latest` absent)**: label "möjlig" — correct, no bug condition.

## Expected Behavior

### Preservation Requirements

**Bug 1 — unchanged behaviors:**
- Distinct-name hierarchies de-duplicate: a second residence citing the same full string reuses the same chain rather than creating a duplicate.
- A bare single-level place creates or reuses exactly one parentless place.
- Existing GEDCOM import/round-trip tests stay green.

**Bug 2 — unchanged behaviors:**
- Bounded-span facts with an overlapping core still label "säker" (Requirement 8.2 for that shape).
- Empty-core facts still label "möjlig" (Requirement 8.4).
- Ordering is unchanged: "säker" before "möjlig", undated last, then place/person/id.
- The per-bounds-quadruple cache in `residents_of_place` still yields correct labels.

**Scope:** inputs outside each bug condition must be completely unaffected. For Bug 1 this includes all single-level and distinct-name place imports; for Bug 2 this includes all facts whose Possible_Span is bounded in at least one direction.

## Hypothesized Root Cause

Both root causes are confirmed, not hypothetical:

1. **Bug 1 — parent-insensitive fallback in `_find_existing_by_name_and_type`**: the helper returns `match_without_parent` (first place matching only name+type) when no `(name, type, parent_id)` match exists. For a repeated-name level this binds the nested level to a wrong, shallower place and drops the parent chain. `map_place_to_hierarchy` therefore never creates the distinct child, and `_resolve_place`'s string-keyed cache/`PlaceMapping` persistence locks in the collapsed result.

2. **Bug 2 — label computed before the unbounded-both check in `residents_of_place`**: the label is derived solely from Certain_Core overlap; `span.is_unbounded_both()` is consulted only for the `undated` flag and for ordering, never for the label. An unbounded-both fact with an overlapping core is thus mislabelled "säker" while also being marked "odaterat".

### Requirements conflict and resolution (Bug 2)

Requirement 8.2 says a year overlapping the Certain_Core is "säker"; Requirement 8.9 says a Possible_Span unbounded in both directions is "möjlig" + "odaterat" and sorts last. For a fact that has both a non-empty core and an unbounded-both span, these conflict.

**Decision (product owner): Requirement 8.9 takes precedence.** When the Possible_Span is unbounded in both directions, the entry is always "möjlig" + "odaterat" and sorts last, regardless of core overlap. Requirement 8.2's "säker" rule applies only to facts whose Possible_Span is bounded in at least one direction. This design clarifies the two criteria accordingly; the residence-periods Requirement 10 examples (Place C) already assume this reading.

## Correctness Properties

Property 1: Bug Condition — Repeated-name place hierarchy survives GEDCOM round trip

_For any_ GEDCOM `PLAC` string with N comma-separated levels where the bug condition holds (two or more levels share a name and an identically-named place exists at a different level), the fixed place-resolution logic SHALL produce an N-level parent chain in which a level is matched to an existing place only when that place occupies the same position in the parent chain, so that "Ed, Ed" round-trips to a child "Ed" under a distinct parent "Ed".

**Validates: Requirements 2.1, 2.2**

Property 2: Preservation — Distinct-name and single-level place imports unchanged

_For any_ place import where the bug condition does NOT hold (single-level places, or multi-level hierarchies with distinct names), the fixed logic SHALL produce the same places and de-duplication as the original, reusing an existing chain for a repeated distinct-name citation and creating exactly one parentless place for a bare single-level name.

**Validates: Requirements 3.1, 3.2, 3.3**

Property 3: Bug Condition — Unbounded-both fact labelled "möjlig" + "odaterat"

_For any_ Residence_Fact whose Possible_Span is unbounded in both directions, the fixed `residents_of_place` SHALL label its entry "möjlig" (LABEL_POSSIBLE) with `undated=True` and order it after every bounded entry, regardless of whether its Certain_Core overlaps the queried year.

**Validates: Requirements 5.1, 5.2**

Property 4: Preservation — Bounded-span labelling and ordering unchanged

_For any_ Residence_Fact whose Possible_Span is bounded in at least one direction, the fixed `residents_of_place` SHALL produce the same label, `undated` flag, and ordering position as the original — "säker" when the core overlaps, "möjlig" when the core is empty — preserving Requirements 8.2, 8.4, and the overall ordering.

**Validates: Requirements 5.3, 6.1, 6.2, 6.3, 6.4**

## Fix Implementation

### Bug 1 — preserve repeated-name levels

**File**: `slaktbusken/gedcom/translation/place_translation.py`

**Function**: `_find_existing_by_name_and_type` (and its use within `map_place_to_hierarchy`)

**Specific Changes**:
1. **Stop collapsing on the parent-insensitive fallback for repeated-name chains.** When resolving a level whose expected `parent_id` is set (i.e. it is a nested level), a match must respect the parent chain: only `(name, type, parent_id)` matches may be reused. The current `match_without_parent` fallback must not bind a nested level to a shallower, differently-parented place of the same name.
2. **Preserve the fallback where it is safe.** For top-level resolution (`parent_id is None`), or where no parent collision exists, keep the existing name+type reuse so distinct-name de-duplication and single-level reuse are unchanged.
3. **Keep the importer cache/persistence correct.** Verify that `_resolve_place` in `slaktbusken/gedcom/importer.py` (string-keyed `_place_cache` and `PlaceMapping` persistence) no longer causes "Ed" and "Ed, Ed" to converge on one place once the hierarchy builder keeps them distinct. Only adjust the importer if resolution still collapses after the builder fix.

**Pseudocode for the fix (conceptual):**
```
# In _find_existing_by_name_and_type, when parent_id is provided:
#   return only a match whose parent_place_id == parent_id
#   do NOT fall back to a name+type-only match for nested levels
# When parent_id is None (top level):
#   keep existing name+type reuse (preserves de-dup and single-level reuse)
```

### Bug 2 — unbounded-both overrides core overlap

**File**: `slaktbusken/services/residence_query.py`

**Function**: `residents_of_place`

**Specific Changes**:
1. **Check `span.is_unbounded_both()` before applying the core-overlap rule.** When the Possible_Span is unbounded in both directions, label the entry `LABEL_POSSIBLE` unconditionally; only when it is bounded in at least one direction apply the existing `LABEL_CERTAIN if core overlaps else LABEL_POSSIBLE` rule.
2. **Keep ordering and `undated` as they are.** `undated` already derives from `span.is_unbounded_both()`, and the sort key already pushes undated entries last; these stay correct once the label respects the same property.
3. **Keep the per-bounds-quadruple cache.** Fold the unbounded-both decision into the cached `(label, interval)` computation keyed by the bounds quadruple; since `is_unbounded_both()` is a function of the same four bounds, the cache stays valid.

**Pseudocode for the fix (conceptual):**
```
if span.is_unbounded_both():
    label = LABEL_POSSIBLE
else:
    core = certain_core(fact)
    label = LABEL_CERTAIN if core is not None and overlaps(core, queried_year) else LABEL_POSSIBLE
```

## Testing Strategy

### Validation Approach

For both bugs the "bug condition exploration test" of the bugfix workflow is **already satisfied by the existing failing property tests** — they fail on the current code, demonstrating the defects. They are referenced here rather than re-invented, and they must pass unchanged after the fix. The property tests encode the correct behavior and must not be weakened.

### Exploratory Bug Condition Checking (already in place)

- **Bug 1**: `tests/test_model/test_residence_gedcom_roundtrip_property.py::TestGedcomRoundTripProperty::test_residence_fact_survives_gedcom_round_trip` (Property 27, Requirement 12.9). Falsifying example: "Ed, Ed" imports back as "Ed". Running it on the unfixed code fails at the place-hierarchy assertion, confirming the collapse.
- **Bug 2**: `tests/test_services/test_residence_query_property.py::TestResidentsQuery::test_residents_query_property` (Property 19, Requirements 8.2, 8.3, 8.4, 8.9). Falsifying example: `start.latest='1500'`, `end.earliest='1501'`, outer bounds absent. The test asserts an unbounded-both entry is "möjlig" (Assertion 3) while a non-empty overlapping core is present, which the current "säker" labelling violates.

**Note on the Bug 2 test expectation:** the query test computes its expected label from core overlap in one assertion and forces undated ⇒ "möjlig" in another; for the falsifying fact shape these coincide only once the 8.9-over-8.2 precedence is applied. Aligning the test's expected-label computation with that precedence (so both assertions agree) is an expectation **clarification**, not a weakening — it brings the test in line with the product-owner decision captured above. If the test already encodes 8.9 precedence in its expected-label helper, no test change is needed and the production fix alone makes it pass.

### Fix Checking

```
# Bug 1
FOR ALL plac_string WHERE isBugCondition(plac_string) DO
  round_tripped := import(export(place_from(plac_string)))
  ASSERT resolve_hierarchy(round_tripped) == plac_string
END FOR

# Bug 2
FOR ALL (fact, year) WHERE isBugCondition(fact, year) DO
  entry := residents_of_place_fixed(..., year)[fact]
  ASSERT entry.label == LABEL_POSSIBLE AND entry.undated AND sorts_after_bounded(entry)
END FOR
```

### Preservation Checking

```
# Bug 1
FOR ALL plac_string WHERE NOT isBugCondition(plac_string) DO
  ASSERT import_fixed(plac_string) == import_original(plac_string)
END FOR

# Bug 2
FOR ALL (fact, year) WHERE NOT isBugCondition(fact, year) DO
  ASSERT residents_of_place_fixed(..., year) == residents_of_place_original(..., year)
END FOR
```

Property-based testing is the primary vehicle for preservation here because both existing property tests already quantify over the full input domain; keeping them green after the fix is the preservation guarantee.

### Unit Tests

- Bug 1: import "Ed, Ed" with a pre-existing standalone "Ed" → assert a 2-level chain of two distinct "Ed" places; import a bare "Ed" → assert one parentless place; import "Ljusdal, Gävleborgs län, Sverige" twice → assert a single shared 3-level chain.
- Bug 2: query a fact with `start.latest='1500'`, `end.earliest='1501'`, outer bounds absent → assert "möjlig" + `undated=True`; query a bounded fact with overlapping core → assert "säker"; query an empty-core fact → assert "möjlig".

### Property-Based Tests

- The two existing property tests (Property 27 and Property 19) are the authoritative property tests and must pass unchanged after the fix.

### Integration Tests

- Bug 1: full export → import round trip of a project containing a repeated-name hierarchy, verifying place chains and residence place resolution.
- Bug 2: residents-of-place query over a project mixing bounded and unbounded-both facts, verifying labels, undated markers, and ordering together.
