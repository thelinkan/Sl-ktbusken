# GEDCOM Update Import Fixes — Bugfix Design

## Overview

Fem buggar i GEDCOM-uppdateringsimportflödet i Släktbusken orsakar problem med dataintegritet och användbarhet:
1. Blandad engelska/svenska i slutdialogen
2. Duplicerade händelser skapas istället för att uppdatera befintliga
3. Händelser kopplas till fel person (event-to-person-läckage mellan INDI-poster)
4. Platsvärden med ett ord tappas tyst
5. Importrapporten saknar tillräcklig detalj

Fixstrategin är att adressera varje bugg isolerat med minimala ändringar i `GEDCOMImporter` (i `slaktbusken/gedcom/importer.py`), `ImportService.format_result` (i `slaktbusken/services/import_service.py`), och `TranslationManager.map_place`/`_resolve_place` för platshantering.

## Glossary

- **Bug_Condition (C)**: Villkoren som utlöser respektive bugg vid GEDCOM-uppdateringsimport
- **Property (P)**: Önskat korrekt beteende för varje buggkondition
- **Preservation**: Befintligt beteende som INTE ska påverkas av fixarna (fullständig import, flerordiga platser, oförändrade händelser)
- **GEDCOMImporter**: Klassen i `slaktbusken/gedcom/importer.py` som orkestrerar GEDCOM-import
- **ImportResult**: Dataclass som håller importstatistik och varningar
- **TranslationManager**: Facade i `slaktbusken/gedcom/translation/__init__.py` för platsöversättning
- **_resolve_place**: Metod i GEDCOMImporter som mappar PLAC-sträng → App_JSON place_id
- **_update_person**: Metod som uppdaterar en befintlig person vid reimport
- **_create_person_events**: Metod som skapar händelser för en person från GEDCOM-poster

## Bug Details

### Bug Condition

Buggarna manifesterar vid uppdateringsimport av GEDCOM-filer i fem separata men relaterade scenarier:

1. **Språkblandning**: Valideringsvarningar i importrapporten blandar engelska platstypnamn (county, country, parish) i svenska meddelanden
2. **Dubblerade händelser**: `_update_person` anropar `_create_person_events` utan att kontrollera befintliga händelser
3. **Event-läckage**: Händelsestate läcker mellan INDI-poster vid skapande av nya personer
4. **Tappade platser**: `_resolve_place` returnerar `None` för enfrågeplatser och hoppar över dem utan varning
5. **Otillräcklig rapport**: Varningar saknar strukturerad information (xref, personnamn, händelsetyp, råvärde, anledning)

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type ImportOperation (GEDCOM file + existing project)
  OUTPUT: boolean
  
  RETURN (
    input.isUpdateImport AND (
      completionDialogContainsEnglishText(input.result)
      OR existingPersonHasMatchingEvents(input.person, input.events) AND duplicatesCreated(input)
      OR newPersonReceivedEventsFromOtherINDI(input.person, input.events)
      OR input.placValue IS single_word AND placeDropped(input.event)
      OR input.warnings.any(w => w.lacksStructuredDetail())
    )
  )
END FUNCTION
```

### Examples

- **Bug 1**: Valideringsvarningen visar "En plats av typen county måste ha en överordnad plats av typen 'country'" — engelska platstypnamn (county, country, parish, church, cemetery) i ett svenskt meddelande
- **Bug 2**: Person @I5@ har redan en birth-händelse (1850-01-15, Falun). Vid reimport skapas en andra identisk birth-händelse istället för att uppdatera/hoppa över den befintliga
- **Bug 3**: @I10@ (ny person) får birth-händelsen som tillhör @I9@ eftersom händelsestate inte nollställdes mellan INDI-poster
- **Bug 4**: GEDCOM-posten `2 PLAC Falun` resulterar i att platsen inte sparas alls — `_resolve_place` returnerar `None` och ingen varning loggas
- **Bug 5**: Varning "Rad 142: Kunde inte importera person" saknar xref (@I10@), personnamn, händelsetyp, råvärde, och anledning

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Fullständig initial import av GEDCOM-filer ska fortsätta fungera korrekt (alla personer, familjer, händelser, platser)
- Flerordiga PLAC-värden (t.ex. "Falun, Dalarna, Sverige") ska fortsätta normaliseras och sparas korrekt
- Oförändrade händelser vid update-import ska lämnas orörda
- Ny person-skapande vid update-import (för personer som inte finns i projektet) ska fortsätta fungera
- Import utan problematisk data ska ge en ren sammanfattning utan falska varningar

**Scope:**
Alla inputs som INTE involverar buggkonditionerna ovan ska vara helt opåverkade av dessa fixar. Detta inkluderar:
- Fullständig initial import (ej update)
- Händelsehantering för nya personer med korrekta poster
- Platsupplösning för flerordiga PLAC-värden
- Importlogg/rapport vid problemfria importer

## Hypothesized Root Cause

Baserat på buggbeskrivningen och kodanalys:

1. **Språkblandning (Bug 1)**: `_validate_place_hierarchy` i `slaktbusken/model/validators.py` använder de interna engelska platstypnamnen (`place.type` och `expected_parent_type`) direkt i svenska felmeddelanden. T.ex. `f"En plats av typen {place.type} måste ha en överordnad plats av typen '{expected_parent_type}'."` producerar "county" och "country" i ett svenskt meddelande. Dessa valideringsmeddelanden propageras till `ImportResult.warnings` via `ImportService.run()` → `ValidationService.validate_project()` → `_validate_place` och visas i importdialogen.

2. **Duplicerade händelser (Bug 2)**: `_update_person` (rad 994–1065 i importer.py) anropar `_create_person_events` utan att först ta bort eller matcha befintliga händelser. Kommentaren i koden bekräftar detta: "For simplicity, we add new events; a more sophisticated approach would merge/deduplicate".

3. **Event-läckage (Bug 3)**: Det finns ingen explicit nollställning av händelse-relaterad state mellan INDI-poster i `_process_persons`-loopen. Om en undantagshantering eller felaktig variabel-scoping gör att `person_id` från föregående INDI leak till nästa anrop av `_create_person_events`, hamnar händelser på fel person.

4. **Tappade platser (Bug 4)**: `_resolve_place` anropar `TranslationManager.map_place` som i sin tur anropar `map_place_to_hierarchy`. Vid enordiga platser har `GedcomPlace.levels` bara ett element. `infer_place_type` med `total_levels=1` returnerar "parish", men om `_find_existing_by_name_and_type` inte hittar matchning och `map_place_to_hierarchy` returnerar en tom lista av någon anledning, returneras `None` — platsen tappas tyst utan varning.

5. **Otillräcklig rapport (Bug 5)**: Varningarna i `self._warnings` är fria textsträngar utan strukturerad information. De inkluderar inte konsekvent xref, personnamn, händelsetyp, råvärde, eller anledning.

## Correctness Properties

Property 1: Bug Condition - Validation Warnings Swedish Only

_For any_ import that triggers place hierarchy validation warnings, the warning messages SHALL use Swedish place type names (län, land, församling, kyrka, kyrkogård, by, gård, skola) and SHALL NOT contain English type identifiers (county, country, parish, church, cemetery, village, farm, school).

**Validates: Requirements 2.1**

Property 2: Bug Condition - Event Deduplication on Update

_For any_ update import where a person already exists in the project with events matching by (person_id, event_type, date, place), the import SHALL update or skip those events rather than creating duplicates.

**Validates: Requirements 2.2**

Property 3: Bug Condition - Event Isolation Between INDI Records

_For any_ update import processing multiple INDI records, individual events extracted from INDI record N SHALL only be attached to the person represented by INDI record N, never to persons from other INDI records.

**Validates: Requirements 2.3**

Property 4: Bug Condition - Single-Word Place Preservation

_For any_ GEDCOM event with a PLAC value consisting of a single word (no commas), the import SHALL preserve the raw place string on the event (even if normalization into full hierarchy is not possible) and SHALL log a structured warning.

**Validates: Requirements 2.4**

Property 5: Bug Condition - Structured Import Warnings

_For any_ warning generated during update import, the warning entry SHALL include: GEDCOM file reference, record xref, person/family name (if available), event type (if applicable), raw GEDCOM value, reason for the warning, and action taken.

**Validates: Requirements 2.5**

Property 6: Preservation - Existing Import Behavior Unchanged

_For any_ input where the bug conditions do NOT hold (full initial imports, multi-word PLAC values, unchanged events during update, new persons with properly structured records, clean imports), the fixed code SHALL produce exactly the same result as the original code, preserving all existing functionality.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `slaktbusken/model/validators.py`

**Function**: `_validate_place_hierarchy`

**Specific Changes**:
1. **Translate place type names in error messages**: Add a `_PLACE_TYPE_SWEDISH` dictionary mapping English place type identifiers to Swedish display names (e.g., "county" → "län", "country" → "land", "parish" → "församling", "church" → "kyrka", "cemetery" → "kyrkogård", "village" → "by", "farm" → "gård", "school" → "skola"). Use this mapping in all error messages in `_validate_place_hierarchy` so that the user-facing text is entirely Swedish. E.g., `f"En plats av typen {_PLACE_TYPE_SWEDISH[place.type]} måste ha en överordnad plats av typen '{_PLACE_TYPE_SWEDISH[expected_parent_type]}'."` Additionally check `validate_place` for the `_VALID_PLACE_TYPES` error message which also exposes English type names.

---

**File**: `slaktbusken/gedcom/importer.py`

**Function**: `_update_person`

**Specific Changes**:
2. **Event deduplication**: Before calling `_create_person_events`, query existing events for the person. Match incoming events by (person_id, event_type, date, place). If a matching event exists, skip or update it. Only create truly new events.

---

**File**: `slaktbusken/gedcom/importer.py`

**Function**: `_process_persons` / `_create_person_events`

**Specific Changes**:
3. **Event isolation**: Ensure that no mutable state carrying event data leaks between iterations of the INDI-record loop. Verify `person_id` is correctly scoped to each iteration. Add explicit reset of any event-related state at the start of each INDI record processing.

---

**File**: `slaktbusken/gedcom/importer.py`

**Function**: `_resolve_place`

**Specific Changes**:
4. **Single-word place fallback**: When `_resolve_place` receives a single-word place and `map_place` returns `None` for the place_id, store the raw place string directly (either creating a minimal Place record with the raw name, or storing it as raw_place on the event). Log a structured warning including person, event type, and raw PLAC value.

---

**File**: `slaktbusken/gedcom/importer.py`

**Function**: Multiple warning-generating locations

**Specific Changes**:
5. **Structured warnings**: Introduce a `WarningEntry` dataclass (or structured format string) that includes: gedcom_file, record_xref, person_or_family_name, event_type, raw_value, reason, action_taken. Replace free-text `self._warnings.append(...)` calls with structured entries. Update `format_result` and report formatting to render these fields.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bugs on unfixed code, then verify the fixes work correctly and preserve existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bugs BEFORE implementing fixes. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write unit tests that exercise each bug scenario on the UNFIXED code to observe failures and understand the root cause.

**Test Cases**:
1. **Language Mix Test**: Call `format_result` with a populated `ImportResult` and assert all text is Swedish (will fail on unfixed code if English text is found)
2. **Duplicate Event Test**: Create a project with a person + birth event, import same GEDCOM again, assert no duplicate events (will fail on unfixed code)
3. **Event Leakage Test**: Import a GEDCOM with 3 INDI records, assert each person's events are only their own (will fail on unfixed code if leakage occurs)
4. **Single-Word Place Test**: Import a GEDCOM event with `2 PLAC Falun`, assert place is preserved on event (will fail on unfixed code — place is None)
5. **Warning Detail Test**: Trigger a warning condition, assert warning includes xref, person name, event type, raw value, reason (will fail on unfixed code)

**Expected Counterexamples**:
- English text in format_result output (Bug 1)
- Event count doubles after reimport (Bug 2)
- Events attached to wrong person_id (Bug 3)
- place_ref is None for single-word PLAC values (Bug 4)
- Warnings lack structured information (Bug 5)

### Fix Checking

**Goal**: Verify that for all inputs where the bug conditions hold, the fixed functions produce the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := importFixed(input)
  ASSERT expectedBehavior(result)
END FOR
```

Specifically:
- Bug 1: `ASSERT all_text_is_swedish(format_result(result))`
- Bug 2: `ASSERT count_events_for_person(person_id) == expected_count` (no duplicates)
- Bug 3: `ASSERT all_events_for(person_id).all(e => e.participant.person_id == person_id)`
- Bug 4: `ASSERT event.place IS NOT None OR event.raw_place == "Falun"`
- Bug 5: `ASSERT warning.xref IS NOT None AND warning.reason IS NOT None`

### Preservation Checking

**Goal**: Verify that for all inputs where the bug conditions do NOT hold, the fixed functions produce the same result as the original.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT importOriginal(input) == importFixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for non-bug inputs (full imports, multi-word places, unchanged events), then write property-based tests capturing that behavior.

**Test Cases**:
1. **Full Import Preservation**: Verify initial GEDCOM import produces identical results before and after fix
2. **Multi-Word Place Preservation**: Verify "Falun, Dalarna, Sverige" resolves correctly after fix
3. **Unchanged Event Preservation**: Verify events that haven't changed are left unmodified during update import
4. **New Person Preservation**: Verify adding entirely new persons during update import still works correctly
5. **Clean Import Report Preservation**: Verify clean imports produce no spurious warnings

### Unit Tests

- Test `format_result` returns all-Swedish text for various ImportResult configurations
- Test `_update_person` does not create duplicate events when matching events exist
- Test `_create_person_events` only attaches events to the specified person_id
- Test `_resolve_place` returns a valid place reference for single-word inputs
- Test warning generation includes all required structured fields

### Property-Based Tests

- Generate random ImportResult instances and verify `format_result` always produces Swedish output
- Generate random GEDCOM person records with events, run update import twice, verify event count is stable (no duplicates)
- Generate random sequences of INDI records and verify event isolation (each event's participant matches its source INDI)
- Generate random single-word and multi-word place strings and verify none are silently dropped
- Generate random warning scenarios and verify all warnings contain required fields

### Integration Tests

- Full round-trip: export project to GEDCOM, reimport as update, verify no duplicates or data loss
- Multi-person import with mixed new/existing persons, verify correct event attachment
- Import with mix of single-word and multi-word places, verify all are preserved
- Import with intentional errors, verify report contains actionable structured information
