# Requirements Document

## Introduction

Omarbetning av fotohanteringen i Släktbusken. Fotoredigering flyttas från inline-sektioner i "Redigera person – Foton"-fliken till ett dedikerat fönster ("Redigera foto"). Fönstret samlar all metadata, personkopplingar, datumfält, anteckningar samt taggning mot händelser och platser. Platsredigeraren och Redigera händelse får egna fotosektioner som använder samma delade logik.

## Glossary

- **Applikationen**: Släktbusken-skrivbordsapplikationen byggd med PySide6.
- **Fotofönstret**: Det nya modala QDialog-fönstret "Redigera foto" som öppnas för att redigera ett valt foto.
- **FotoTab**: Den befintliga widgeten i "Redigera person – Foton"-fliken som visar en persons kopplade foton.
- **MediaItem**: Dataklassen som representerar ett medieobjekt (foto, dokument, etc.) i projektdatan.
- **Platsredigeraren**: Dialogfönstret för att hantera platser (PlaceEditor).
- **Händelseredigeraren**: Dialogfönstret för att redigera händelser (EventEditor).
- **Fotodatum**: Ett datumfält som stödjer partiell precision: enbart år, år och månad, eller fullständigt datum.
- **Händelsetagg**: En koppling mellan ett foto och en händelse via LinkedEntity.
- **Platstagg**: En koppling mellan ett foto och en plats via LinkedEntity.
- **Annan_media**: Icke-foto medieobjekt kopplade till en händelse (t.ex. vigselkort, inbjudningar).

## Requirements

### Requirement 1: Dedikerat fotoredigeringsfönster

**User Story:** Som användare vill jag redigera foton i ett eget fönster, så att jag får bättre överblick och plats för all fotoinformation.

#### Acceptance Criteria

1. WHEN användaren klickar på "Redigera foto"-knappen, THE Applikationen SHALL öppna Fotofönstret som en modal QDialog och populera samtliga sektioner med det valda fotots befintliga data från MediaItem-objektet.
2. THE Fotofönstret SHALL visa sektionerna i följande ordning uppifrån och ned: "Titel och typ", "Fotodatum", "Personer på fotot", "Händelser", "Platser" och "Anteckningar".
3. WHEN användaren klickar "Spara" längst ned i Fotofönstret, THE Applikationen SHALL validera alla sektioner och, om valideringen lyckas, spara ändringarna till MediaItem-objektet och stänga fönstret.
4. IF användaren klickar "Spara" och valideringen misslyckas, THEN THE Fotofönstret SHALL förbli öppet och visa valideringsfelet vid den aktuella sektionen utan att förändra MediaItem-objektet.
5. WHEN användaren klickar "Avbryt" eller stänger Fotofönstret via fönstrets stängningsknapp (X), THE Applikationen SHALL stänga fönstret utan att spara ändringar till MediaItem-objektet.

### Requirement 2: Knappordning i FotoTab

**User Story:** Som användare vill jag ha en "Redigera foto"-knapp för att snabbt öppna det nya fotofönstret, så att jag slipper leta i menyer.

#### Acceptance Criteria

1. THE FotoTab SHALL visa knappar i ordningen "Lägg till foto", "Redigera foto", "Ta bort foto" från vänster till höger i knappraden.
2. THE FotoTab SHALL alltid hålla knappen "Lägg till foto" aktiverad oavsett markering i fotolistan.
3. WHILE inget foto är markerat i fotolistan, THE FotoTab SHALL inaktivera knapparna "Redigera foto" och "Ta bort foto".
4. WHEN användaren markerar ett foto i fotolistan, THE FotoTab SHALL aktivera knapparna "Redigera foto" och "Ta bort foto".
5. WHEN användaren klickar "Redigera foto" med ett foto markerat, THE Applikationen SHALL öppna Fotofönstret med det markerade fotots MediaItem laddat.

### Requirement 3: Sektion "Titel och typ"

**User Story:** Som användare vill jag kunna ange titel och typ för ett foto, så att jag kan kategorisera mina bilder.

#### Acceptance Criteria

1. THE Fotofönstret SHALL visa sektionen "Titel och typ" med ett textfält för titel och en rullgardinsmeny för fototyp med alternativen: "Porträtt", "Gruppfoto", "Familjefoto", "Bröllopsfoto", "Konfirmationsfoto", "Dopfoto", "Skolfoto", "Militärfoto", "Arbetsfoto", "Begravningsfoto", "Gravfoto", "Övrigt foto".
2. THE Fotofönstret SHALL INTE visa en separat "Spara ändringar"-knapp i sektionen "Titel och typ".
3. WHEN användaren sparar hela Fotofönstret, THE Applikationen SHALL spara titeln och fototypen till MediaItem.title-fältet i formatet "[Fototyp] Titel" (t.ex. "[Porträtt] Barnfoto").
4. IF användaren försöker spara med en titel som är tom eller längre än 200 tecken, THEN THE Fotofönstret SHALL visa ett valideringsfel och förhindra sparning.
5. WHEN Fotofönstret öppnas med ett befintligt foto, THE Applikationen SHALL fylla i textfältet med den befintliga titeln och välja motsvarande fototyp i rullgardinsmenyn baserat på MediaItem.title-fältets format.

### Requirement 4: Fotodatum med flexibel precision

**User Story:** Som användare vill jag kunna ange ett ungefärligt eller exakt datum för när ett foto togs, så att jag kan tidsbestämma mina bilder.

#### Acceptance Criteria

1. THE Fotofönstret SHALL visa sektionen "Fotodatum" med inmatningsfält för år (numeriskt, 1–9999), månad (1–12) och dag (1–31).
2. THE Fotofönstret SHALL tillåta att enbart år anges (månad och dag tomma).
3. THE Fotofönstret SHALL tillåta att år och månad anges (dag tom).
4. THE Fotofönstret SHALL tillåta att fullständigt datum anges (år, månad och dag).
5. THE Fotofönstret SHALL tillåta att alla datumfält lämnas tomma (inget fotodatum angivet).
6. IF användaren anger månad utan år, THEN THE Fotofönstret SHALL visa ett valideringsmeddelande intill datumfälten som anger att år krävs.
7. IF användaren anger dag utan månad eller år, THEN THE Fotofönstret SHALL visa ett valideringsmeddelande intill datumfälten som anger att år och månad krävs.
8. IF användaren anger en dag som inte är giltig för den angivna månaden och året (t.ex. 30 februari), THEN THE Fotofönstret SHALL visa ett valideringsmeddelande som anger att datumet är ogiltigt.
9. WHEN användaren sparar Fotofönstret med giltigt fotodatum, THE Applikationen SHALL lagra fotodatumet på MediaItem-objektet med den precisionsnivå användaren angett (enbart år, år och månad, eller fullständigt datum).
10. WHEN användaren sparar Fotofönstret med alla datumfält tomma, THE Applikationen SHALL lagra fotodatumet som tomt (inget datum) på MediaItem-objektet.

### Requirement 5: Sektion "Personer på fotot"

**User Story:** Som användare vill jag kunna lägga till och ta bort personer som syns på ett foto, så att jag kan dokumentera vilka som är med.

#### Acceptance Criteria

1. THE Fotofönstret SHALL visa sektionen "Personer på fotot" med en lista över kopplade personer.
2. THE Fotofönstret SHALL visa knapparna "Lägg till person" och "Ta bort" i ordningen "Lägg till person" till vänster om "Ta bort".
3. WHILE ingen person är markerad i listan "Personer på fotot", THE Fotofönstret SHALL inaktivera knappen "Ta bort".
4. WHEN användaren klickar "Lägg till person", THE Applikationen SHALL öppna en dialogruta för val av person.
5. THE dialogrutan för personval SHALL tillåta val av person från databasen eller inmatning av ett fritext-namn (max 200 tecken) för personer utanför databasen.
6. WHEN användaren bekräftar personvalet, THE Applikationen SHALL lägga till personen i listan "Personer på fotot" om personen inte redan finns i listan.
7. IF användaren försöker lägga till en person som redan finns i listan, THEN THE Applikationen SHALL inte lägga till en dubblett och ska visa ett meddelande som anger att personen redan är kopplad till fotot.
8. WHEN användaren markerar en person och klickar "Ta bort", THE Applikationen SHALL ta bort personen från listan.

### Requirement 6: Anteckningsfält

**User Story:** Som användare vill jag kunna skriva anteckningar om ett foto, så att jag kan dokumentera kontext och detaljer.

#### Acceptance Criteria

1. THE Fotofönstret SHALL visa sektionen "Anteckningar" med ett flerradigt textfält som visar minst 3 rader och tillåter maximalt 2000 tecken.
2. WHEN användaren öppnar Fotofönstret för ett foto som har befintlig anteckningstext, THE Applikationen SHALL fylla textfältet med den lagrade anteckningstexten från MediaItem-objektet.
3. WHEN användaren sparar Fotofönstret, THE Applikationen SHALL lagra det aktuella innehållet i anteckningsfältet på MediaItem-objektet, inklusive tom text om fältet rensats.

### Requirement 7: Händelsetaggning av foton

**User Story:** Som användare vill jag kunna koppla ett foto till händelser, så att jag kan organisera bilder per livshändelse.

#### Acceptance Criteria

1. THE Fotofönstret SHALL visa sektionen "Händelser" med en lista över kopplade händelser och knapparna "Lägg till" och "Ta bort" i ordningen "Lägg till" till vänster om "Ta bort".
2. WHILE ingen händelse är markerad i händelselistan, THE Fotofönstret SHALL inaktivera knappen "Ta bort".
3. WHEN användaren klickar "Lägg till" i händelsesektionen, THE Applikationen SHALL visa en dialogruta med en lista av valbara händelser.
4. THE dialogrutan SHALL enbart visa händelser där minst en av personerna kopplade till fotot via "Personer på fotot" förekommer som deltagare (Participant) i händelsen, exklusive händelser som redan är kopplade till fotot.
5. IF inga personer är kopplade till fotot via "Personer på fotot", THEN THE dialogrutan SHALL visa en tom lista utan valbara händelser.
6. WHEN användaren väljer en händelse och bekräftar, THE Applikationen SHALL skapa en LinkedEntity med entity_type "event" och entity_id satt till den valda händelsens id på MediaItem-objektet.
7. WHEN användaren markerar en händelse och klickar "Ta bort", THE Applikationen SHALL ta bort motsvarande LinkedEntity från MediaItem-objektet.

### Requirement 8: Platstaggning av foton

**User Story:** Som användare vill jag kunna koppla ett foto till platser, så att jag kan organisera bilder geografiskt.

#### Acceptance Criteria

1. THE Fotofönstret SHALL visa sektionen "Platser" med en lista över kopplade platser och knapparna "Lägg till" och "Ta bort" i ordningen "Lägg till" till vänster om "Ta bort".
2. WHILE ingen plats är markerad i platslistan, THE Fotofönstret SHALL inaktivera knappen "Ta bort".
3. WHEN användaren klickar "Lägg till" i platssektionen, THE Applikationen SHALL visa en dialogruta med projektets platser att välja från, exklusive platser som redan är kopplade till fotot.
4. WHEN användaren väljer en plats och bekräftar, THE Applikationen SHALL skapa en LinkedEntity med entity_type "place" och entity_id satt till den valda platsens id på MediaItem-objektet.
5. WHEN användaren markerar en plats och klickar "Ta bort", THE Applikationen SHALL ta bort motsvarande LinkedEntity från MediaItem-objektet.

### Requirement 9: Fotosektion i Platsredigeraren

**User Story:** Som användare vill jag se vilka foton som är kopplade till en plats direkt i Platsredigeraren, så att jag kan navigera till relevanta bilder.

#### Acceptance Criteria

1. THE Platsredigeraren SHALL visa en sektion "Foton" som listar alla MediaItem-objekt med type "photo" som har en LinkedEntity med entity_type "place" och entity_id matchande den valda platsen, där varje rad visar fotots titel.
2. THE fotosektionen i Platsredigeraren SHALL visa knapparna i ordningen "Visa foto", "Redigera foto", "Lägg till foto".
3. WHILE inget foto är markerat i listan, THE Platsredigeraren SHALL inaktivera knapparna "Visa foto" och "Redigera foto".
4. WHEN användaren klickar "Visa foto", THE Applikationen SHALL öppna en modal dialogruta som visar det markerade fotots bildfil.
5. WHEN användaren klickar "Redigera foto", THE Applikationen SHALL öppna Fotofönstret med det markerade fotot.
6. WHEN användaren klickar "Lägg till foto", THE Applikationen SHALL öppna en fildialogruta filtrerad till bildformat (PNG, JPG, JPEG, BMP, GIF, TIFF), och vid bekräftat filval skapa ett nytt MediaItem med type "photo" och en LinkedEntity med entity_type "place" och entity_id satt till den valda platsen, samt lägga till det nya fotot i listan.
7. IF användaren avbryter fildialogen vid "Lägg till foto", THEN THE Applikationen SHALL stänga dialogen utan att skapa något MediaItem och lämna listan oförändrad.

### Requirement 10: Uppdelad mediasektion i Händelseredigeraren

**User Story:** Som användare vill jag att foton och annan media hanteras separat i Händelseredigeraren, så att jag kan skilja på fotografier och andra dokument.

#### Acceptance Criteria

1. THE Händelseredigeraren SHALL visa två separata sektioner: "Foton" och "Annan media" istället för en enda "Händelsemedia"-sektion.
2. THE sektionen "Foton" i Händelseredigeraren SHALL visa en fotolista samt knapparna "Lägg till foto", "Redigera foto" och "Ta bort foto" i den ordningen.
3. WHILE inget foto är markerat i "Foton"-sektionens lista, THE Händelseredigeraren SHALL inaktivera knapparna "Redigera foto" och "Ta bort foto".
4. WHEN ett foto läggs till via "Foton"-sektionen, THE Applikationen SHALL skapa ett MediaItem med type "photo" och en LinkedEntity med entity_type "event" och entity_id matchande den aktuella händelsen.
5. THE sektionen "Annan media" SHALL visa en lista över kopplade icke-foto-medieobjekt samt knapparna "Lägg till media" och "Ta bort media".
6. WHILE inget mediaobjekt är markerat i "Annan media"-sektionens lista, THE Händelseredigeraren SHALL inaktivera knappen "Ta bort media".
7. WHEN media läggs till via "Annan media"-sektionen, THE Applikationen SHALL skapa ett MediaItem med en type som inte är "photo" och en LinkedEntity med entity_type "event" och entity_id matchande den aktuella händelsen.

### Requirement 11: Borttagning av inline-redigeringssektioner

**User Story:** Som användare vill jag att den gamla inline-redigeringen tas bort, så att det bara finns ett sätt att redigera foton och gränssnittet förenklas.

#### Acceptance Criteria

1. THE FotoTab SHALL INTE visa sektionen "Redigera foto" (nu "Titel och typ") som inline-gruppbox.
2. THE FotoTab SHALL INTE visa "Spara ändringar"-knappen i inline-redigeringssektionen.
3. THE FotoTab SHALL INTE visa "Spara personlista"-knappen eller personlistan som inline-sektion; all personhantering sker enbart i Fotofönstret.
4. WHEN användaren markerar ett foto i FotoTab-listan, THE Applikationen SHALL aktivera knapparna "Redigera foto" och "Ta bort foto" utan att visa några inline-redigeringssektioner, medan knappen "Lägg till foto" förblir alltid aktiv.
5. WHEN användaren dubbelklickar på ett foto i FotoTab-listan, THE Applikationen SHALL öppna Fotofönstret med det dubbelklickade fotot.
