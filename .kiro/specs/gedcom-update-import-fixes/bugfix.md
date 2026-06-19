# Bugfix Requirements Document

## Introduction

Vid uppdateringsimport av GEDCOM-filer i Släktbusken uppstår flera buggar som rör språkblandning i dialogen, dubblering av händelser, felaktig koppling av händelser till fel person, tappade platsvärden med bara ett ord, samt otillräcklig detaljnivå i importrapporten. Dessa buggar påverkar dataintegritet och användbarhet vid uppdateringsimport från MinSläkt-exporterade GEDCOM-filer.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN an update import completes and validation warnings are generated for place hierarchy issues THEN the system displays English place type names (e.g. "county", "country", "parish") mixed into Swedish warning messages (e.g. "En plats av typen county måste ha en överordnad plats av typen 'country'")

1.2 WHEN a GEDCOM file is imported as update into an existing project containing persons with events THEN the system adds duplicate events for existing persons instead of detecting and updating existing events

1.3 WHEN new persons are added during update import THEN the system attaches events belonging to other persons to the newly added persons (event-to-person mapping leaks between INDI records)

1.4 WHEN a GEDCOM event has a PLAC value with only one word (e.g. "Falun") THEN the system silently drops the place entirely — no place is stored and no warning is logged

1.5 WHEN the import report is generated after update import THEN the system does not include sufficient detail (GEDCOM xref, person name, event type, raw value, reason) to investigate skipped or problematic data

### Expected Behavior (Correct)

2.1 WHEN an update import completes and validation warnings are generated for place hierarchy issues THEN the system SHALL display all place type names in Swedish (e.g. "län", "land", "församling", "kyrka", "kyrkogård", "by", "gård", "skola") instead of English identifiers

2.2 WHEN a GEDCOM file is imported as update into an existing project containing persons with events THEN the system SHALL match existing events by person/family, event type, date, place and source/citation, and update them if changed rather than creating duplicates

2.3 WHEN new persons are added during update import THEN the system SHALL only attach individual events to the person represented by the current INDI record, and family events only to the relevant family — event state SHALL be reset between INDI records

2.4 WHEN a GEDCOM event has a PLAC value with only one word (e.g. "Falun") THEN the system SHALL preserve the raw place string on the event even if normalization fails, and SHALL log a warning with person, event type, and raw PLAC value

2.5 WHEN the import report is generated after update import THEN the system SHALL include for each warning: GEDCOM file, record xref (e.g. @I10@), person/family name if available, event type, raw GEDCOM value, reason why it was not imported or normalized, and action taken

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a full initial import of a GEDCOM file is performed THEN the system SHALL CONTINUE TO import all persons, families, events, and places correctly

3.2 WHEN an update import adds entirely new persons not previously in the project THEN the system SHALL CONTINUE TO create the persons and attach their events correctly (for multi-word PLAC values and properly structured records)

3.3 WHEN a GEDCOM event has a multi-word PLAC value (e.g. "Falun, Dalarna, Sverige") THEN the system SHALL CONTINUE TO normalize and store the place correctly

3.4 WHEN an update import processes persons whose events have not changed THEN the system SHALL CONTINUE TO leave those events unmodified

3.5 WHEN a GEDCOM file contains no problematic data THEN the import report SHALL CONTINUE TO show a clean summary without spurious warnings
