# Bugfix Requirements Document

## Introduction

Two different ArkivDigital reference string formats that refer to the same source produce different Source records. The colon variant (`Bild: N Sida: N`) and the slash variant (`Bild N / sid N (AID: ..., NAD: ...)`) can both arrive through any input method (GEDCOM import or paste/search), but the reference parser and import pipeline don't normalize them to equivalent output. Additionally, an "ArkivDigital:" prefix is not stripped during GEDCOM import, and the Referenstext field incorrectly includes machine-readable AID/NAD identifiers that should only be stored in the arkivreferenser table.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a reference string has an "ArkivDigital:" prefix (e.g., `ArkivDigital: Karlstads stadsförsamling (S) AIIa:7 (1906-1910) Bild: 300 Sida: 16`) and enters via GEDCOM import THEN the system does not strip the prefix, does not assign the correct Leverantör ID ("Arkiv Digital"), and does not assign the correct Källtyp ID (derived from the series code via CHURCH_BOOK_SERIES_LABELS)

1.2 WHEN a reference string with "ArkivDigital:" prefix enters via GEDCOM import THEN the system does not populate any arkivreferenser entries on the Source, even when AID/NAD values could be derived from the text

1.3 WHEN a reference string contains a `(AID: ..., NAD: ...)` parenthesis THEN the system stores the full string including that parenthesis in the Referenstext field, regardless of input method

1.4 WHEN the same archival source is represented in two format variants — colon variant `Ed (S) AI:16 (1866-1870) Bild: 58 Sida: 51` and slash variant `Ed (S) AI:16 (1866-1870) Bild 58 / sid 51 (AID: v10726.b58.s51, NAD: SE/VA/13090)` — THEN the system produces Source records with different Leverantör, Källtyp, and title values regardless of which input method is used, because the two formats are not normalized to the same output

### Expected Behavior (Correct)

2.1 WHEN a reference string has an "ArkivDigital:" prefix (regardless of input method) THEN the system SHALL strip the prefix, parse the remaining text through the reference parser, and assign the Leverantör ID corresponding to "Arkiv Digital" and the Källtyp ID derived from the series code via CHURCH_BOOK_SERIES_LABELS

2.2 WHEN any ArkivDigital reference string is parsed (either format variant) THEN the system SHALL generate a formatted title using `format_source_title()` (e.g., "Karlstads stadsförsamling AIIa:7 Sida: 16") — both format variants referencing the same source SHALL produce the same title

2.3 WHEN a reference string contains explicit AID and/or NAD values (in a `(AID: ..., NAD: ...)` parenthesis or equivalent) THEN the system SHALL store arkivreferenser entries: one for "Arkiv Digital" with the AID value, and one for "Nationell Arkivdatabas" with the NAD value; IF neither AID nor NAD is present in the text THEN no arkivreferenser entries SHALL be created

2.4 WHEN a reference string contains a `(AID: ..., NAD: ...)` or `(AID: ...)` parenthesis THEN the system SHALL store only the text preceding that parenthesis (trimmed) as the Referenstext field value, regardless of input method

2.5 WHEN both format variants of the same archival source are processed (colon variant and slash variant) THEN the system SHALL produce Source records with equivalent Leverantör, Källtyp, and formatted title values — the only difference being that the slash variant may additionally include arkivreferenser entries if AID/NAD values are present

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a GEDCOM file contains a non-ArkivDigital source (no "ArkivDigital:" prefix and not detected as ArkivDigital) THEN the system SHALL CONTINUE TO import it without modifying Leverantör or Källtyp assignment

3.2 WHEN a clipboard/paste reference matches the existing full pattern with AID and NAD THEN the system SHALL CONTINUE TO correctly extract aid_ref and nad_ref into structured_fields and arkivreferenser

3.3 WHEN a clipboard/paste reference matches the existing short pattern (AID only, no NAD) THEN the system SHALL CONTINUE TO parse it correctly with a single arkivreferens entry for "Arkiv Digital"

3.4 WHEN a clipboard/paste reference matches the census pattern (rX.pXXXXX) THEN the system SHALL CONTINUE TO parse it as Leverantör "Arkiv Digital" and Källtyp "Folkräkning"

3.5 WHEN a GEDCOM source is detected as Sveriges Dödbok Webb (SDB pattern) THEN the system SHALL CONTINUE TO assign Leverantör "Rötter.se" and Källtyp "Sveriges Dödbok Webb"

3.6 WHEN a reference string does not match any known pattern THEN the system SHALL CONTINUE TO leave it unmodified for manual handling
