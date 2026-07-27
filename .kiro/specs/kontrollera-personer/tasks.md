# Implementation Plan: Kontrollera Personer

## Overview

Implementerar funktionen "Kontrollera personer" som lägger till personvalideringsfunktionalitet i Släktbusken. Implementationen sker inkrementellt: först datamodeller och konfiguration, sedan check-motorns kärnlogik med individuella kontrollmoduler, därefter UI-dialogens tre flikar, och slutligen integration med app.py och main_window.py.

## Tasks

- [x] 1. Datamodeller och konfiguration
  - [x] 1.1 Skapa `PersonCheckConfig` och relaterade dataclasses i `persistence/settings_io.py`
    - Lägg till `AgeCheckThreshold`, `AgeCheckConfig`, `LogicCheckConfig` och `PersonCheckConfig` dataclasses
    - Lägg till fältet `person_check_config: PersonCheckConfig` i `ProjectSettings`
    - Utöka `_deserialize_settings()` och `_serialize_settings()` för att hantera den nya konfigurationen med fallback till defaults för saknade nycklar
    - Standardvärden enligt Requirement 5.5: Högsta ålder 130/130, Högsta ålder vid dop 1/1, Lägsta ålder vid giftermål 12/12, Högsta ålder vid giftermål 110/110, Största åldersskillnad 50, Lägsta ålder vid barnafödande 12/12, Högsta ålder vid barnafödande 80/60, Kortast tid mellan barnafödslar 240 dagar, Längsta tid mellan död och begravning 365/365
    - _Requirements: 4.6, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 7.2, 7.5, 10.1, 10.2, 10.3, 10.4_

  - [x] 1.2 Skriv property-test för settings round-trip
    - **Property 1: Settings serialization round-trip**
    - Generera slumpmässiga `PersonCheckConfig`-instanser med giltiga värden och verifiera att serialisering → deserialisering producerar ekvivalent konfiguration
    - Verifiera att partiella dict:ar med saknade nycklar fylls med defaults medan befintliga värden bevaras
    - **Validates: Requirements 4.6, 5.6, 7.2, 10.1, 10.2, 10.4**

- [x] 2. DateUtils — datumparsning och beräkningar
  - [x] 2.1 Skapa `services/checks/date_utils.py`
    - Implementera `ParsedDate` dataclass med `year`, `month`, `day`, `precision`
    - Implementera `parse_date_value(dv: DateValue) -> ParsedDate | None`
    - Implementera `age_in_years(birth, event) -> int | None`
    - Implementera `days_between(d1, d2) -> int | None`
    - Implementera `compare_dates(d1, d2) -> int | None` som jämför på gemensam precision
    - Implementera `is_valid_swedish_calendar(d: ParsedDate) -> bool` med korrekt hantering av kalenderövergången 1753
    - Skapa `services/checks/__init__.py`
    - _Requirements: 6.10, 8.8, 9.5_

  - [x] 2.2 Skriv property-test för datumprecisionsjämförelse
    - **Property 8: Date precision comparison**
    - Generera `ParsedDate`-par med varierande precision (bara år, år+månad, fullständigt) och verifiera att jämförelse sker på den mest specifika gemensamma precisionen
    - **Validates: Requirements 8.8**

  - [x] 2.3 Skriv property-test för svensk kalendervalidering
    - **Property 12: Swedish calendar validation**
    - Generera datum kring 1753-övergången och verifiera att 1753-02-18 till 1753-02-28 är ogiltiga, att julianiska regler gäller ≤1753-02-17 och gregorianska ≥1753-03-01
    - **Validates: Requirements 9.5**

- [x] 3. Checkpoint — Grundläggande datamodeller och verktyg
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Kontrollmotor: CheckFinding och PersonCheckEngine
  - [x] 4.1 Skapa `services/person_check_engine.py`
    - Implementera `CheckFinding` dataclass med `person_id`, `person_display`, `person_sex`, `message`
    - Implementera `CheckContext` dataclass med lookup-tabeller (`persons_by_id`, `events_by_person`, `families_by_person`, `parents_of`, `children_of`, `siblings_of`, `project_folder`, `main_person_id`, `current_year`)
    - Implementera `PersonCheckEngine.__init__()` som bygger `CheckContext` från `ProjectData`
    - Implementera `PersonCheckEngine.run_checks()` som itererar alla personer, anropar aktiverade kontrollmoduler, rapporterar progress och returnerar `list[CheckFinding]` grupperade per person
    - Implementera `format_person_display(person, events) -> str` med formatet "Förnamn Efternamn (YYYY–YYYY)" där saknat år ersätts med "?"
    - _Requirements: 3.2, 3.7, 4.2, 4.3, 7.3, 7.4, 11.1_

  - [x] 4.2 Skriv property-test för person display format
    - **Property 2: Person display format**
    - Generera `Person` med varierade namn/datum och verifiera att `format_person_display()` matchar mönstret `"<given> <surname> (<birth_year>–<death_year>)"`
    - **Validates: Requirements 3.2**

  - [x] 4.3 Skriv property-test för resultatgruppering
    - **Property 3: Results grouped per person**
    - Generera projektdata med kända problem, kör `run_checks()` och verifiera att alla findings för samma `person_id` är sammanhängande i listan
    - **Validates: Requirements 3.7**

- [x] 5. Ålderskontroller
  - [x] 5.1 Skapa `services/checks/age_checks.py`
    - Implementera kontroller: `check_max_age`, `check_max_age_at_baptism`, `check_min_age_at_marriage`, `check_max_age_at_marriage`, `check_max_partner_age_diff`, `check_min_age_at_childbirth`, `check_max_age_at_childbirth`, `check_min_days_between_births`, `check_max_days_death_to_burial`
    - Varje kontroll ska kontrollera att den är aktiverad, att nödvändiga datum finns, beräkna ålder/tid med DateUtils, och skapa `CheckFinding` med korrekt text enligt Req 6.1–6.9
    - Hoppa över kontroll om nödvändigt datum saknas (Req 6.10)
    - Använd rätt tröskel baserat på personens kön (male/female)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10_

  - [x] 5.2 Skriv property-test för ålderscheck-trösklar
    - **Property 4: Age check threshold comparison**
    - Generera person + event-par med kända åldrar vs tröskelvärden och verifiera att finding skapas om och endast om tröskeln överskrids
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9**

  - [x] 5.3 Skriv property-test för inaktiverade kontroller
    - **Property 5: Disabled or inapplicable checks produce no findings**
    - Generera data + config med slumpmässigt avaktiverade checks och verifiera att inga findings produceras för avaktiverade kontroller
    - **Validates: Requirements 4.2, 6.10, 7.4**

- [x] 6. Kronologiska kontroller
  - [x] 6.1 Skapa `services/checks/chronology_checks.py`
    - Implementera `check_reasonable_dates`: flagga datum före år 1000 eller efter innevarande år
    - Implementera `check_no_event_before_birth`: kontrollera att inga händelser förekommer före födelse
    - Implementera `check_burial_not_before_death`: begravning/bouppteckning ej före döden
    - Implementera `check_only_burial_after_death`: bara begravning/bouppteckning/testamente efter döden
    - Implementera `check_no_own_events_after_death`: inga egna händelser efter döden
    - Implementera `check_birth_not_after_parent_death`: födelse max 270 dagar efter förälders död
    - Implementera `check_no_event_before_parent_birth`: inga händelser före förälders födelse
    - Alla kontroller ska använda `compare_dates` med precisionshänsyn (Req 8.8)
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8_

  - [x] 6.2 Skriv property-test för rimliga datum
    - **Property 6: Reasonable date range**
    - Generera `DateValue` med år innanför/utanför intervallet [1000, current_year] och verifiera korrekt finding-generering
    - **Validates: Requirements 8.1**

  - [x] 6.3 Skriv property-test för kronologiska ordningsbrott
    - **Property 7: Chronological order violations**
    - Generera person med födelse/döds-datum och händelser före/efter dessa, verifiera korrekta findings
    - **Validates: Requirements 8.2, 8.3, 8.4, 8.5, 8.6, 8.7**

- [x] 7. Strukturella kontroller
  - [x] 7.1 Skapa `services/checks/structure_checks.py`
    - Implementera `check_incest`: kontrollera om partners delar förälder eller om en partner är förälder till den andre
    - Implementera `check_must_have_relations`: flagga personer utan familjerelationer
    - Implementera `check_no_ancestor_cycle`: BFS uppåt via `parents_of` med visited-set för cykeldetektering
    - Implementera `check_connected_to_main_person`: BFS från huvudpersonen genom familjerelationer, flagga onåbara personer
    - Hoppa över kopplingscheck om ingen huvudperson definierad (Req 9.7)
    - _Requirements: 9.1, 9.2, 9.3, 9.6, 9.7_

  - [x] 7.2 Skriv property-test för incestdetektering
    - **Property 9: Incest detection**
    - Generera familjegraf med/utan syskon-/förälderrelation bland partners och verifiera korrekt finding
    - **Validates: Requirements 9.1**

  - [x] 7.3 Skriv property-test för isolerade personer
    - **Property 10: Isolated person detection**
    - Generera person + familjer med/utan kopplingar och verifiera korrekt finding
    - **Validates: Requirements 9.2**

  - [x] 7.4 Skriv property-test för cykeldetektion
    - **Property 11: Ancestor cycle detection**
    - Generera riktad graf med/utan cykler och verifiera korrekt finding
    - **Validates: Requirements 9.3**

  - [x] 7.5 Skriv property-test för koppling till huvudperson
    - **Property 13: Connectivity to main person**
    - Generera familjegraf + huvudperson, verifiera att onåbara personer flaggas och nåbara inte flaggas
    - **Validates: Requirements 9.6**

- [x] 8. Kalenderkontroller och filer
  - [x] 8.1 Skapa `services/checks/calendar_checks.py`
    - Implementera `check_valid_swedish_calendar`: validera alla datum mot `is_valid_swedish_calendar()`
    - Implementera `check_media_files_exist`: kontrollera att mediaobjektets fil existerar på angiven sökväg, skapa finding kopplad till personen (eller utan personkoppling om ingen person)
    - _Requirements: 9.4, 9.5_

- [x] 9. Checkpoint — All kontrolllogik implementerad
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. QThread worker
  - [x] 10.1 Skapa `ui/workers/check_worker.py`
    - Skapa katalogen `ui/workers/` med `__init__.py`
    - Implementera `CheckWorker(QThread)` med `progress_updated = Signal(int)` och `finished = Signal(list)`
    - Implementera `run()` som skapar `PersonCheckEngine` och anropar `run_checks()` med progress-callback
    - Kontrollera `isInterruptionRequested()` i loopen för att hantera avbrytning vid dialogstängning
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

- [x] 11. UI: KontrolleraPersonerDialog
  - [x] 11.1 Skapa `ui/dialogs/kontrollera_personer_dialog.py` — dialogstruktur
    - Implementera `KontrolleraPersonerDialog(QDialog)` med `QTabWidget` och tre flikar
    - Skapa knappar "Stäng", "Kontrollera", "Hjälp" i `QHBoxLayout` längst ned
    - Skapa `QProgressBar` (dold initialt) ovanför knapparna
    - Sätt "Resultat"-fliken som aktiv vid öppning
    - Anslut "Stäng" till `accept()` med konfigurationsexporten
    - Anslut "Kontrollera" till worker-start
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.7, 11.1, 11.3, 11.4_

  - [x] 11.2 Implementera Resultatfliken
    - `QTableWidget` med kolumner "Person" och "Påpekande"
    - Person-kolumnen visar ikon (man/kvinna/neutral) + formaterat namn
    - `QLabel` statusrad "Antal påpekanden: 0" längst ned
    - Dubbelklick-signal som stänger dialogen och navigerar till personen
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [x] 11.3 Implementera Åldersfliken
    - Master-kryssruta "Utför kontroller" som styr `setEnabled()` på alla barnwidgets
    - `QFormLayout` med varje kontroll: kryssruta + label + `QSpinBox`-fält (Män/Kvinnor) med `setRange(0, 999)` respektive `setRange(0, 9999)` för dagar
    - Individuella kryssrutor som inaktiverar tillhörande spinboxar
    - Ladda och visa sparade eller standardvärden vid öppning
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5, 5.7, 5.8_

  - [x] 11.4 Implementera Fler kontroller-fliken
    - `QVBoxLayout` med 13 `QCheckBox` i specificerad ordning
    - Ladda och visa sparade eller standardvärden vid öppning (alla markerade som default)
    - _Requirements: 7.1, 7.5_

  - [x] 11.5 Skriv property-test för input-validering
    - **Property 14: Input validation rejects out-of-range values**
    - Generera heltal utanför/innanför tillåtna intervall och verifiera att QSpinBox korrekt begränsar värden
    - **Validates: Requirements 5.8**

- [x] 12. Integration med app.py och main_window.py
  - [x] 12.1 Koppla in menyn och dialogen
    - Lägg till `action_person_checks` QAction i `main_window.py._setup_actions()` med text "Kontrollera &personer..."
    - Lägg till action i `menu_tools` i `_setup_menu_bar()` efter `action_relationship`
    - Inaktivera/aktivera i `_update_project_actions()`
    - Implementera `show_person_checks()` i `app.py` som öppnar dialogen, sparar konfiguration efter stängning
    - Anslut dubbelklick-navigering till `diagram_panel.set_active_person(person_id)`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 3.6, 10.1_

  - [x] 12.2 Skriv enhetstester för meny-aktivering och dialogöppning
    - Testa att menyalternativet är inaktiverat utan öppet projekt
    - Testa att menyalternativet aktiveras när projekt öppnas
    - Testa att dialogen öppnas som modal
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 13. Konfigurationsbeständighet — spara och ladda
  - [x] 13.1 Implementera sparning och laddning av kontrollinställningar
    - Spara alla inställningar via `ProjectSettings` vid dialogstängning (Stäng-knapp, fönsterstängknapp, Escape)
    - Ladda senast sparade inställningar vid dialogöppning
    - Hantera felfall: visa `QMessageBox.warning` vid sparfel, stäng dialogen ändå
    - Hantera saknade nycklar med fallback till defaults (framåtkompatibilitet)
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 14. Slutlig checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The implementation uses Python (PySide6) following existing project patterns
- Hypothesis is already installed and configured in the project

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1"] },
    { "id": 1, "tasks": ["1.2", "2.2", "2.3"] },
    { "id": 2, "tasks": ["4.1"] },
    { "id": 3, "tasks": ["4.2", "4.3", "5.1", "6.1", "7.1", "8.1"] },
    { "id": 4, "tasks": ["5.2", "5.3", "6.2", "6.3", "7.2", "7.3", "7.4", "7.5", "10.1"] },
    { "id": 5, "tasks": ["11.1"] },
    { "id": 6, "tasks": ["11.2", "11.3", "11.4"] },
    { "id": 7, "tasks": ["11.5", "12.1", "13.1"] },
    { "id": 8, "tasks": ["12.2"] }
  ]
}
```
