# Reference Format Equivalence Bugfix Design

## Overview

Two ArkivDigital reference string formats — the colon variant (`Bild: N Sida: N`) and the slash variant (`Bild N / sid N (AID: ..., NAD: ...)`) — represent the same source but produce different Source records. The fix normalizes both variants to equivalent output by: (1) stripping the "ArkivDigital:" prefix during GEDCOM import before parsing, (2) extracting AID/NAD identifiers from parentheses into `arkivreferenser` entries instead of storing them in `reference_text`, (3) assigning correct Leverantör and Källtyp IDs for prefixed sources, and (4) ensuring `format_source_title()` produces identical titles for both variants.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug — when ArkivDigital reference strings in either colon or slash variant produce non-equivalent Source records, fail to strip the "ArkivDigital:" prefix, or include AID/NAD identifiers in Referenstext
- **Property (P)**: The desired behavior — both format variants of the same source produce equivalent Leverantör, Källtyp, and formatted title; AID/NAD values are stored only in arkivreferenser; the prefix is stripped before parsing
- **Preservation**: Existing non-ArkivDigital GEDCOM import behavior, clipboard/paste parsing for full/short/census patterns, and SDB detection must remain unchanged
- **parse_reference()**: The function in `slaktbusken/parsing/reference_parser.py` that dispatches to sub-parsers (Arkiv Digital, census, Rötter.se)
- **parse_arkiv_digital()**: The function that handles both full pattern (slash variant with AID/NAD) and Bild colon pattern matching
- **map_gedcom_source()**: The function in `slaktbusken/gedcom/translation/source_translation.py` that creates Source entities from GEDCOM source records
- **_derive_reference_text()**: Helper that currently strips "ArkivDigital:" prefix but does not strip AID/NAD parentheses
- **format_source_title()**: Formats structured reference fields into a human-readable title (e.g., "Ljusdal AI:17 Sida: 32")
- **CHURCH_BOOK_SERIES_LABELS**: Mapping from series codes (AI, AIIa, CI, etc.) to Källtyp names (Husförhörslängd, Församlingsbok, etc.)
- **ArkivReferens**: Data class linking a leverantor_name to a reference_value, stored in `Source.arkivreferenser`

## Bug Details

### Bug Condition

The bug manifests in three related scenarios:

1. **Prefix not stripped during GEDCOM import**: When text has "ArkivDigital:" prefix, `map_gedcom_source()` does not assign Leverantör ID or Källtyp ID because the full pipeline (`parse_reference()`) is not invoked on the stripped text. The `_build_structured_reference()` helper strips the prefix for church book parsing but the Leverantör/Källtyp assignment path is incomplete.

2. **AID/NAD stored in Referenstext**: When a reference string contains `(AID: ..., NAD: ...)`, the `reference_text` field stores the full string including the parenthetical machine-readable identifiers, rather than trimming them off.

3. **Format variants produce different output**: The colon variant (no AID/NAD) and slash variant (with AID/NAD) produce Source records with different `reference_text` values and potentially different title formatting, even when they refer to the same archival source.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type str (reference string)
  OUTPUT: boolean
  
  has_prefix := input starts with "ArkivDigital:" (case-insensitive)
  has_aid_nad := input contains regex pattern "\(AID:\s*[^)]+\)"
  is_colon_variant := input matches _AD_BILD_COLON_PATTERN
  is_slash_variant := input matches _AD_FULL_PATTERN OR _AD_SHORT_PATTERN
  
  RETURN (has_prefix AND leverantor_id NOT assigned AND kalltyp_id NOT assigned)
         OR (has_aid_nad AND aid_nad_text IN reference_text)
         OR (is_colon_variant AND is_slash_variant reference to same source
             AND produced Source records differ in leverantor/kalltyp/title)
END FUNCTION
```

### Examples

- **Prefix not stripped**: Input `"ArkivDigital: Karlstads stadsförsamling (S) AIIa:7 (1906-1910) Bild: 300 Sida: 16"` via GEDCOM import produces a Source without Leverantör ID "Arkiv Digital" and without Källtyp ID derived from "AIIa" → "Församlingsbok". Expected: prefix stripped, Leverantör = "Arkiv Digital", Källtyp = "Församlingsbok".

- **AID/NAD in Referenstext**: Input `"Ed (S) AI:16 (1866-1870) Bild 58 / sid 51 (AID: v10726.b58.s51, NAD: SE/VA/13090)"` produces `reference_text = "Ed (S) AI:16 (1866-1870) Bild 58 / sid 51 (AID: v10726.b58.s51, NAD: SE/VA/13090)"`. Expected: `reference_text = "Ed (S) AI:16 (1866-1870) Bild 58 / sid 51"` with separate arkivreferenser entries.

- **Non-equivalent output**: Colon variant `"Ed (S) AI:16 (1866-1870) Bild: 58 Sida: 51"` produces title `"Ed AI:16 Sida: 51"` with Leverantör "Arkiv Digital" and Källtyp "Husförhörslängd". Slash variant `"Ed (S) AI:16 (1866-1870) Bild 58 / sid 51 (AID: v10726.b58.s51, NAD: SE/VA/13090)"` produces the same title `"Ed AI:16 Sida: 51"` but with different `reference_text`. Expected: both produce equivalent Source records (same title, same Leverantör, same Källtyp), with the only difference being that the slash variant additionally has arkivreferenser entries.

- **Edge case — AID only (short pattern)**: Input `"Ljusdals kyrkoarkiv (1825) Bild 10 / sid 5 (AID: v99999)"` should store `reference_text = "Ljusdals kyrkoarkiv (1825) Bild 10 / sid 5"` with one arkivreferens entry for "Arkiv Digital" with value "v99999".

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Non-ArkivDigital GEDCOM sources (no prefix, not detected as ArkivDigital) must continue to import without modifying Leverantör or Källtyp assignment
- Clipboard/paste references matching the full pattern (slash variant with AID/NAD) must continue to correctly extract `aid_ref` and `nad_ref` into structured_fields and arkivreferenser
- Clipboard/paste references matching the short pattern (AID only) must continue to parse correctly with a single arkivreferens entry
- Census pattern references (rX.pXXXXX) must continue to parse as Leverantör "Arkiv Digital" and Källtyp "Folkräkning"
- Sveriges Dödbok Webb sources (SDB pattern) must continue to assign Leverantör "Rötter.se" and Källtyp "Sveriges Dödbok Webb"
- References not matching any known pattern must remain unmodified for manual handling

**Scope:**
All inputs that do NOT involve the "ArkivDigital:" prefix, the `(AID: ..., NAD: ...)` parenthesis stripping from Referenstext, or the normalization of colon/slash variants should be completely unaffected by this fix. This includes:
- Mouse-driven UI interactions (button clicks, form submissions)
- Non-ArkivDigital GEDCOM sources
- Rötter.se / SDB sources
- Census pattern parsing
- References that don't match any known pattern

## Hypothesized Root Cause

Based on the bug description and code analysis, the most likely issues are:

1. **GEDCOM import does not invoke `parse_reference()` on prefix-stripped text**: The `map_gedcom_source()` function detects ArkivDigital sources and partially handles them (structured reference building, title formatting), but does not use the result to assign `leverantor_id` and `kalltyp_id`. The `_build_structured_reference()` strips the prefix for church book parsing but this path only populates `structured_reference.fields`, not the Source-level Leverantör/Källtyp IDs.

2. **`reference_text` does not strip AID/NAD parenthetical**: The `_derive_reference_text()` helper in `source_translation.py` strips the "ArkivDigital:" prefix but does not remove the `(AID: ..., NAD: ...)` suffix. Similarly, `parse_arkiv_digital()` in `reference_parser.py` stores the full input text as `reference_text` without trimming the AID/NAD parenthesis.

3. **No AID/NAD extraction during GEDCOM import**: When a GEDCOM source text contains AID/NAD values (in the slash variant), the GEDCOM import pipeline doesn't extract these into `arkivreferenser` entries. The `parse_reference()` function does extract them for clipboard/paste input, but `map_gedcom_source()` doesn't invoke this path or transfer its results.

4. **Format variants already produce same title**: The `format_source_title()` function correctly produces equivalent titles from structured fields (since both variants yield the same parish/series/volume/page). The divergence is in Leverantör/Källtyp/reference_text, not the title itself.

## Correctness Properties

Property 1: Bug Condition - ArkivDigital prefix stripped and Leverantör/Källtyp assigned

_For any_ reference string with an "ArkivDigital:" prefix (case-insensitive) that matches a known ArkivDigital pattern after prefix removal, the fixed import pipeline SHALL strip the prefix, parse the remaining text, assign Leverantör ID corresponding to "Arkiv Digital", and assign Källtyp ID derived from the series code via CHURCH_BOOK_SERIES_LABELS.

**Validates: Requirements 2.1, 2.2**

Property 2: Bug Condition - AID/NAD stripped from Referenstext

_For any_ reference string containing a `(AID: ..., NAD: ...)` or `(AID: ...)` parenthesis, the fixed function SHALL store only the text preceding that parenthesis (trimmed) as the `reference_text` value, and SHALL store the AID and NAD values as separate arkivreferenser entries.

**Validates: Requirements 2.3, 2.4**

Property 3: Bug Condition - Colon and slash variants produce equivalent output

_For any_ pair of reference strings representing the same archival source in colon variant and slash variant, the fixed system SHALL produce Source records with equivalent Leverantör, Källtyp, and formatted title values — the only permitted difference being that the slash variant may additionally include arkivreferenser entries when AID/NAD values are present.

**Validates: Requirements 2.2, 2.5**

Property 4: Preservation - Non-ArkivDigital sources unchanged

_For any_ input that is NOT an ArkivDigital reference string (no prefix, not detected as ArkivDigital), the fixed code SHALL produce exactly the same Source record as the original code, preserving all existing GEDCOM import behavior, SDB detection, and pattern-matching logic.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `slaktbusken/parsing/reference_parser.py`

**Function**: `parse_arkiv_digital()`

**Specific Changes**:
1. **Strip AID/NAD from reference_text**: For both full pattern and short pattern matches, set `reference_text` to the text preceding the `(AID: ...)` parenthesis (trimmed) rather than the full input string.
2. **Strip AID/NAD from Bild colon pattern too**: Ensure consistency — if a colon variant somehow includes trailing parenthetical text, strip it (defensive).

---

**File**: `slaktbusken/parsing/reference_parser.py`

**Function**: `parse_reference()`

**Specific Changes**:
3. **Strip "ArkivDigital:" prefix before parsing**: At the top of `parse_reference()`, detect and strip the "ArkivDigital:" prefix (case-insensitive) before attempting pattern matching, so that prefixed strings are normalized to the same input as non-prefixed strings.

---

**File**: `slaktbusken/gedcom/translation/source_translation.py`

**Function**: `map_gedcom_source()`

**Specific Changes**:
4. **Assign Leverantör ID and Källtyp ID for ArkivDigital sources**: When `detect_arkiv_digital()` returns True, use `parse_reference()` on the stripped text to obtain leverantor_name and kalltyp_name, then look up corresponding IDs from the provided `leverantorer` and `kalltyper` lists.
5. **Populate arkivreferenser from parsed result**: If `parse_reference()` returns arkivreferenser entries, transfer them to the Source entity.
6. **Strip AID/NAD from reference_text in GEDCOM path**: Ensure `_derive_reference_text()` also strips `(AID: ..., NAD: ...)` parentheses from the text before returning.

---

**File**: `slaktbusken/gedcom/translation/source_translation.py`

**Function**: `_derive_reference_text()`

**Specific Changes**:
7. **Remove AID/NAD parenthetical suffix**: After stripping the "ArkivDigital:" prefix, also strip any trailing `(AID: ...)` or `(AID: ..., NAD: ...)` parenthetical and trim whitespace.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that exercise `parse_reference()` and `map_gedcom_source()` with both format variants and the "ArkivDigital:" prefix. Run these tests on the UNFIXED code to observe failures and understand the root cause.

**Test Cases**:
1. **Prefix Leverantör/Källtyp Test**: Call `map_gedcom_source()` with `"ArkivDigital: Karlstads stadsförsamling (S) AIIa:7 (1906-1910) Bild: 300 Sida: 16"` and assert `leverantor_id` and `kalltyp_id` are set (will fail on unfixed code)
2. **AID/NAD in Referenstext Test**: Call `parse_reference()` with full pattern slash variant and assert `reference_text` does NOT contain "(AID:" (will fail on unfixed code)
3. **Format Equivalence Test**: Parse both `"Ed (S) AI:16 (1866-1870) Bild: 58 Sida: 51"` and `"Ed (S) AI:16 (1866-1870) Bild 58 / sid 51 (AID: v10726.b58.s51, NAD: SE/VA/13090)"`, compare titles (may already pass — confirms hypothesis about title parity)
4. **Prefix arkivreferenser Test**: Import a GEDCOM source with prefix and assert arkivreferenser are populated when AID/NAD can be derived (will fail on unfixed code)

**Expected Counterexamples**:
- `leverantor_id` and `kalltyp_id` are empty strings after GEDCOM import of prefixed source
- `reference_text` contains "(AID: v10726.b58.s51, NAD: SE/VA/13090)" verbatim
- Possible causes: `map_gedcom_source()` does not invoke `parse_reference()` for Leverantör/Källtyp assignment; `reference_text` is set from raw input without AID/NAD stripping

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := parse_reference_fixed(input)
  ASSERT result.reference_text does NOT contain "(AID:" or "(NAD:"
  ASSERT result.leverantor_name == "Arkiv Digital"
  ASSERT result.kalltyp_name IN CHURCH_BOOK_SERIES_LABELS.values() OR result.kalltyp_name == "Övrigt"
  IF input contains AID/NAD THEN
    ASSERT len(result.arkivreferenser) >= 1
  END IF
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT parse_reference_original(input) = parse_reference_fixed(input)
  ASSERT map_gedcom_source_original(input) = map_gedcom_source_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain (random non-ArkivDigital strings, SDB identifiers, census patterns)
- It catches edge cases that manual unit tests might miss (strings that partially resemble ArkivDigital patterns)
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for non-ArkivDigital sources and existing clipboard patterns, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Non-ArkivDigital GEDCOM Preservation**: Verify GEDCOM sources without "ArkivDigital:" prefix and not detected as ArkivDigital continue to import identically
2. **SDB Detection Preservation**: Verify Sveriges Dödbok Webb sources continue to assign correct Leverantör/Källtyp
3. **Census Pattern Preservation**: Verify rX.pXXXXX patterns continue to produce "Arkiv Digital" / "Folkräkning" results
4. **Existing Full Pattern Preservation**: Verify that slash variant clipboard parsing still produces correct arkivreferenser (the fix changes reference_text but arkivreferenser must remain correct)
5. **Existing Short Pattern Preservation**: Verify that AID-only short pattern parsing continues working

### Unit Tests

- Test `parse_reference()` with "ArkivDigital:"-prefixed input → correct leverantor_name/kalltyp_name
- Test `parse_reference()` with slash variant → reference_text without AID/NAD suffix
- Test `parse_reference()` with colon variant → same title as equivalent slash variant
- Test `_derive_reference_text()` stripping both prefix and AID/NAD parenthetical
- Test `map_gedcom_source()` assigning leverantor_id/kalltyp_id for detected ArkivDigital sources
- Test edge cases: prefix with extra whitespace, mixed case "arkivDigital:", trailing whitespace after AID/NAD

### Property-Based Tests

- Generate random ArkivDigital reference strings (both variants) using Hypothesis strategies and verify that reference_text never contains "(AID:" or "(NAD:"
- Generate random parish/series/volume/page combinations and verify that both colon and slash variants produce the same title via `format_source_title()`
- Generate random non-ArkivDigital strings and verify `parse_reference()` returns the same result before and after the fix (preservation)
- Generate random GEDCOM source objects without ArkivDigital markers and verify `map_gedcom_source()` output is unchanged

### Integration Tests

- Test full GEDCOM import flow: file with "ArkivDigital:"-prefixed sources → verify Source records have correct Leverantör ID, Källtyp ID, clean reference_text, and arkivreferenser entries
- Test that re-importing the same source (with content matching) finds the existing Source without creating duplicates
- Test clipboard paste of slash variant → Source creation with arkivreferenser and clean reference_text
