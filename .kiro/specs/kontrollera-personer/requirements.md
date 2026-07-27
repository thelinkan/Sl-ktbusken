# Requirements Document

## Introduction

Funktionen "Kontrollera personer" lägger till ett menyval under "Verktyg" i Släktbusken som öppnar en dialogruta för att validera personuppgifter i det aktiva projektet. Dialogen erbjuder konfiguerbara ålderskontroller och logiska kontroller (t.ex. kronologisk ordning på händelser, inceströjning, kopplingskontroller) och presenterar resultaten i en tabell med personnamn och påpekanden. Funktionen motsvarar "Kontrollera personer" i programmet Min Släkt och ger användaren möjlighet att snabbt identifiera dataproblem i sitt släktforskningsprojekt.

## Glossary

- **Applikationen**: Släktbusken-skrivbordsapplikationen byggd med PySide6.
- **Kontrollera_personer_dialogen**: Det modala QDialog-fönstret som öppnas via menyn Verktyg → Kontrollera personer.
- **Resultatfliken**: Fliken "Resultat" i Kontrollera_personer_dialogen som visar kontrollresultaten i tabellform.
- **Åldersfliken**: Fliken "Ålderskontroller" i Kontrollera_personer_dialogen med konfigurerbara åldersgränser.
- **Fler_kontroller_fliken**: Fliken "Fler kontroller" i Kontrollera_personer_dialogen med logiska och strukturella kontroller.
- **Påpekande**: En rad i resultattabellen som beskriver ett identifierat dataproblem för en specifik person.
- **Kontrollmotor**: Den tjänst som utför alla konfigurerade kontroller mot projektdatan och returnerar en lista med Påpekanden.
- **Projektet**: Det för tillfället öppna släktforskningsprojektet med dess persondata, familjedata, händelser och mediaobjekt.
- **Huvudpersonen**: Den person som angetts som projektets huvudperson (proband).
- **Svenska_kalendern**: Den svenska kalenderhistorien med julianisk kalender fram till 1753-02-17 och gregoriansk kalender från 1753-03-01.

## Requirements

### Requirement 1: Menyval i Verktyg-menyn

**User Story:** Som användare vill jag nå personkontrollerna via menyn Verktyg, så att jag snabbt kan starta en granskning av min databas.

#### Acceptance Criteria

1. THE Applikationen SHALL visa menyalternativet "Kontrollera personer" i menyn "Verktyg".
2. WHILE inget projekt är öppet, THE Applikationen SHALL inaktivera menyalternativet "Kontrollera personer" (visuellt nedtonat och ej klickbart).
3. WHEN ett projekt öppnas, THE Applikationen SHALL aktivera menyalternativet "Kontrollera personer".
4. WHEN användaren klickar på "Kontrollera personer" med ett öppet projekt, THE Applikationen SHALL öppna Kontrollera_personer_dialogen som en modal dialog centrerad över huvudfönstret.

### Requirement 2: Dialogstruktur med tre flikar

**User Story:** Som användare vill jag ha en organiserad dialog med flikar, så att jag kan konfigurera kontroller och se resultat utan att behöva öppna flera fönster.

#### Acceptance Criteria

1. THE Kontrollera_personer_dialogen SHALL visa tre flikar i ordningen "Resultat", "Ålderskontroller" och "Fler kontroller".
2. WHEN Kontrollera_personer_dialogen öppnas, THE "Resultat"-fliken SHALL vara den aktiva (synliga) fliken.
3. THE Kontrollera_personer_dialogen SHALL visa knapparna "Stäng", "Kontrollera" och "Hjälp" längst ned i dialogen, i ordningen Stäng (vänster), Kontrollera (mitten), Hjälp (höger).
4. WHEN användaren klickar "Stäng", THE Kontrollera_personer_dialogen SHALL stängas och spara kontrollinställningarna.
5. WHEN användaren klickar "Kontrollera", THE Kontrollmotorn SHALL utföra alla aktiverade kontroller mot Projektet och visa resultaten i Resultatfliken, och dialogen SHALL automatiskt byta till Resultatfliken om en annan flik är aktiv.
6. WHEN användaren klickar "Kontrollera" och inga kontroller alls är aktiverade (alla ålderskontroller avmarkerade och alla Fler_kontroller avmarkerade), THE Applikationen SHALL visa resultattabellen tom med statusraden "Antal påpekanden: 0".
7. WHEN användaren klickar "Hjälp", THE Applikationen SHALL visa hjälpinformation om hur personkontrollerna fungerar.

### Requirement 3: Resultatfliken

**User Story:** Som användare vill jag se en lista med alla identifierade problem, så att jag kan granska och åtgärda dem en i taget.

#### Acceptance Criteria

1. THE Resultatfliken SHALL visa en tabell med två kolumner: "Person" och "Påpekande".
2. THE kolumnen "Person" SHALL visa personens namn följt av födelseår och dödsår inom parentes i formatet "Förnamn Efternamn (födelseår–dödsår)", där ett okänt födelseår eller dödsår ersätts med "?" (t.ex. "Anna Svensson (?–1834)" eller "Erik Nilsson (1790–?)").
3. THE kolumnen "Person" SHALL visa en personikon som skiljer på man och kvinna, och för personer med okänt kön SHALL en könsneutral ikon visas.
4. THE Resultatfliken SHALL visa en statusrad längst ned med texten "Antal påpekanden: X" där X är antalet rader i resultattabellen.
5. WHEN inga kontroller har utförts ännu, THE Resultatfliken SHALL visa en tom tabell med statusraden "Antal påpekanden: 0".
6. WHEN användaren dubbelklickar på en rad i resultattabellen, THE Applikationen SHALL stänga Kontrollera_personer_dialogen och navigera till den berörda personen i huvudfönstrets diagramvy.
7. THE Resultatfliken SHALL visa tabellraderna i den ordning de genererades av Kontrollmotorn, grupperade per person.

### Requirement 4: Ålderskontroller — övergripande aktivering

**User Story:** Som användare vill jag kunna slå av alla ålderskontroller på en gång, så att jag kan fokusera på andra typer av kontroller.

#### Acceptance Criteria

1. THE Åldersfliken SHALL visa en kryssruta "Utför kontroller" överst som styr om ålderskontroller utförs.
2. WHILE kryssrutan "Utför kontroller" är avmarkerad, THE Kontrollmotorn SHALL hoppa över samtliga ålderskontroller vid körning oavsett individuella kryssrutors tillstånd.
3. WHILE kryssrutan "Utför kontroller" är markerad, THE Kontrollmotorn SHALL utföra de individuellt aktiverade ålderskontrollerna vid körning.
4. WHILE kryssrutan "Utför kontroller" är avmarkerad, THE Åldersfliken SHALL visa de individuella kontrollernas kryssrutor och inmatningsfält som inaktiverade (visuellt nedtonade och ej redigerbara).
5. WHEN kryssrutan "Utför kontroller" markeras, THE Åldersfliken SHALL återaktivera de individuella kontrollernas kryssrutor och inmatningsfält så att de blir redigerbara.
6. THE Åldersfliken SHALL spara tillståndet för kryssrutan "Utför kontroller" mellan sessioner via projektinställningar.

### Requirement 5: Individuella ålderskontroller

**User Story:** Som användare vill jag kunna konfigurera varje ålderskontroll separat med olika tröskelvärden för män och kvinnor, så att kontrollerna passar min forskningstidsperiod.

#### Acceptance Criteria

1. THE Åldersfliken SHALL visa följande kontroller, var och en med en egen kryssruta för aktivering: "Högsta ålder", "Högsta ålder vid dop", "Lägsta ålder vid giftermål", "Högsta ålder vid giftermål", "Största åldersskillnad mellan makar/partner", "Lägsta ålder vid barnafödande", "Högsta ålder vid barnafödande", "Kortast tid mellan barnafödslar", "Längsta tid mellan död och begravning".
2. THE kontrollerna "Högsta ålder", "Högsta ålder vid dop", "Lägsta ålder vid giftermål", "Högsta ålder vid giftermål", "Lägsta ålder vid barnafödande", "Högsta ålder vid barnafödande" och "Längsta tid mellan död och begravning" SHALL ha separata numeriska inmatningsfält för "Män" och "Kvinnor", där varje fält accepterar heltal i intervallet 0 till 999.
3. THE kontrollen "Största åldersskillnad mellan makar/partner" SHALL ha ett enda numeriskt inmatningsfält som gäller oavsett kön, med ett accepterat intervall av 0 till 999 år.
4. THE kontrollen "Kortast tid mellan barnafödslar" SHALL ha ett enda numeriskt inmatningsfält angivet i dagar, med ett accepterat intervall av 0 till 9999.
5. THE Åldersfliken SHALL använda följande standardvärden vid första användningen: "Högsta ålder" 130/130 år, "Högsta ålder vid dop" 1/1 år, "Lägsta ålder vid giftermål" 12/12 år, "Högsta ålder vid giftermål" 110/110 år, "Största åldersskillnad mellan makar/partner" 50 år, "Lägsta ålder vid barnafödande" 12/12 år, "Högsta ålder vid barnafödande" 80/60 år, "Kortast tid mellan barnafödslar" 240 dagar, "Längsta tid mellan död och begravning" 365/365 dagar.
6. THE Åldersfliken SHALL spara samtliga tröskelvärden och individuella kryssrutetillstånd mellan sessioner via projektinställningar.
7. WHEN en individuell kontrollkryssruta är avmarkerad, THE Åldersfliken SHALL inaktivera (gråa ut) tillhörande numeriska inmatningsfält för den kontrollen.
8. WHEN användaren anger ett värde utanför det tillåtna intervallet i ett numeriskt inmatningsfält, THE Åldersfliken SHALL förhindra inmatningen och behålla det senast giltiga värdet i fältet.

### Requirement 6: Exekvering av ålderskontroller

**User Story:** Som användare vill jag att kontrollmotorn identifierar orimliga åldersvärden baserat på mina konfigurerade gränser, så att jag kan hitta felaktiga datum.

#### Acceptance Criteria

1. WHEN kontrollen "Högsta ålder" är aktiverad och en person har en beräknad ålder (dödsdatum minus födelsedatum i hela år) som överstiger det konfigurerade värdet för personens kön, THE Kontrollmotorn SHALL skapa ett Påpekande med texten "Personen har en orimligt hög ålder (X år)" där X är den beräknade åldern.
2. WHEN kontrollen "Högsta ålder vid dop" är aktiverad och en person har en ålder vid dop (dopdatum minus födelsedatum i hela år) som överstiger det konfigurerade värdet för personens kön, THE Kontrollmotorn SHALL skapa ett Påpekande med texten "Äldre än Y år vid dop" där Y är det konfigurerade gränsvärdet.
3. WHEN kontrollen "Lägsta ålder vid giftermål" är aktiverad och en person har en ålder vid giftermål (vigseldatum minus födelsedatum i hela år) som understiger det konfigurerade värdet för personens kön, THE Kontrollmotorn SHALL skapa ett Påpekande med texten "Yngre än Y år vid äktenskap" där Y är det konfigurerade gränsvärdet.
4. WHEN kontrollen "Högsta ålder vid giftermål" är aktiverad och en person har en ålder vid giftermål som överstiger det konfigurerade värdet för personens kön, THE Kontrollmotorn SHALL skapa ett Påpekande med texten "Mer än Y år mellan två händelser (Vigsel och Födelse)" där Y är det konfigurerade gränsvärdet.
5. WHEN kontrollen "Största åldersskillnad mellan makar/partner" är aktiverad och åldersskillnaden mellan två makar överstiger det konfigurerade värdet, THE Kontrollmotorn SHALL skapa ett Påpekande för den yngre maken med texten "Största åldersskillnad mellan makar överstigen (X år)" där X är den faktiska skillnaden.
6. WHEN kontrollen "Lägsta ålder vid barnafödande" är aktiverad och en förälders ålder vid ett barns födelse understiger det konfigurerade värdet för förälderns kön, THE Kontrollmotorn SHALL skapa ett Påpekande med texten "Vid födelsen var föräldern yngre än Y år" där Y är gränsvärdet.
7. WHEN kontrollen "Högsta ålder vid barnafödande" är aktiverad och en förälders ålder vid ett barns födelse överstiger det konfigurerade värdet för förälderns kön, THE Kontrollmotorn SHALL skapa ett Påpekande med texten "Vid födelsen var föräldern äldre än Y år" där Y är gränsvärdet.
8. WHEN kontrollen "Kortast tid mellan barnafödslar" är aktiverad och tiden mellan två på varandra följande barns födelser (för samma moder, sorterade kronologiskt) understiger det konfigurerade värdet i dagar, THE Kontrollmotorn SHALL skapa ett Påpekande med texten "Kortare tid mellan barnafödslar än Y dagar" där Y är gränsvärdet.
9. WHEN kontrollen "Längsta tid mellan död och begravning" är aktiverad och tiden mellan en persons dödsdatum och begravningsdatum överstiger det konfigurerade värdet för personens kön, THE Kontrollmotorn SHALL skapa ett Påpekande med texten "Längre tid mellan död och begravning än Y dagar" där Y är gränsvärdet.
10. IF en ålderskontroll kräver ett datum som saknas på personen (t.ex. inget födelsedatum eller inget dödsdatum), THEN THE Kontrollmotorn SHALL hoppa över den kontrollen för den personen utan att skapa något Påpekande.

### Requirement 7: Fler kontroller — logiska och strukturella

**User Story:** Som användare vill jag kunna aktivera logiska kontroller som upptäcker kronologiskt omöjliga händelser och strukturella problem, så att jag kan rensa upp i min databas.

#### Acceptance Criteria

1. THE Fler_kontroller_fliken SHALL visa följande kontroller i angiven ordning, var och en med en egen kryssruta för aktivering: "Rimliga datum", "Ingen händelse får förekomma före Födelse", "Begravning och Bouppteckning får inte förekomma före döden", "Endast Begravning, Bouppteckning och Testamente får förekomma efter döden", "Inga egna händelser får inträffa efter döden", "Födelse får inte inträffa efter föräldrars död", "Ingen händelse får inträffa före föräldrars födelse", "En person får inte vara gift med eller ha barn med ett syskon eller förälder (incest)", "En person måste ha relationer till andra i arkivet", "En person får inte vara anfader eller anmoder till sig själv", "Bildfiler och länkade filer måste finnas", "Datum måste vara giltiga enligt den svenska kalendern", "En person måste ha en koppling till huvudpersonen".
2. WHEN användaren stänger Kontrollera_personer_dialogen, THE Fler_kontroller_fliken SHALL spara samtliga kryssrutetillstånd till projektinställningarna så att de återställs vid nästa öppning av dialogen.
3. WHEN användaren klickar "Kontrollera" och en kontroll på Fler_kontroller_fliken är markerad, THE Kontrollmotorn SHALL utföra den kontrollen mot Projektet.
4. WHEN användaren klickar "Kontrollera" och en kontroll på Fler_kontroller_fliken är avmarkerad, THE Kontrollmotorn SHALL hoppa över den kontrollen.
5. IF inga sparade kryssrutetillstånd finns för Fler_kontroller_fliken (första användningen), THEN THE Fler_kontroller_fliken SHALL markera samtliga 13 kontroller som aktiverade.

### Requirement 8: Exekvering av logiska kontroller — kronologi

**User Story:** Som användare vill jag att programmet hittar kronologiskt omöjliga händelser, så att jag kan rätta felaktiga datum i mitt träd.

#### Acceptance Criteria

1. WHEN kontrollen "Rimliga datum" är aktiverad och en persons händelse har ett datum före år 1000 eller efter innevarande år, THE Kontrollmotorn SHALL skapa ett Påpekande som anger händelsetypen och det orimliga datumet.
2. WHEN kontrollen "Ingen händelse får förekomma före Födelse" är aktiverad och en person har en händelse med datum före personens födelsedatum, THE Kontrollmotorn SHALL skapa ett Påpekande som anger vilken händelse som inträffar före födelsen.
3. WHEN kontrollen "Begravning och Bouppteckning får inte förekomma före döden" är aktiverad och en person har en begravning eller bouppteckning med datum före dödsdatumet, THE Kontrollmotorn SHALL skapa ett Påpekande som anger vilken händelse (begravning eller bouppteckning) som har datum före döden.
4. WHEN kontrollen "Endast Begravning, Bouppteckning och Testamente får förekomma efter döden" är aktiverad och en person har en händelse (inklusive händelser där personen medverkar men inte äger) efter dödsdatum som inte är Begravning, Bouppteckning eller Testamente, THE Kontrollmotorn SHALL skapa ett Påpekande som anger den felaktiga händelsetypen och dess datum.
5. WHEN kontrollen "Inga egna händelser får inträffa efter döden" är aktiverad och en person har en egen händelse (en händelse som tillhör personen, exklusive Begravning, Bouppteckning och Testamente) med datum efter dödsdatum, THE Kontrollmotorn SHALL skapa ett Påpekande som anger den egna händelsetypen och dess datum.
6. WHEN kontrollen "Födelse får inte inträffa efter föräldrars död" är aktiverad och en persons födelsedatum är mer än 270 dagar efter en förälders dödsdatum, THE Kontrollmotorn SHALL skapa ett Påpekande som anger vilken förälder som avled före barnet föddes.
7. WHEN kontrollen "Ingen händelse får inträffa före föräldrars födelse" är aktiverad och en persons händelse har ett datum före en förälders födelsedatum, THE Kontrollmotorn SHALL skapa ett Påpekande som anger händelsetypen och vilken förälder vars födelsedatum överskrids.
8. IF en datumjämförelse krävs av en kronologisk kontroll och ett eller båda datumen saknar dag- eller månadskomponent, THEN THE Kontrollmotorn SHALL utföra jämförelsen på den mest specifika gemensamma precisionen (år mot år, eller år-månad mot år-månad) och flagga händelsen enbart om den är orimlig även med den lägre precisionen.

### Requirement 9: Exekvering av logiska kontroller — struktur

**User Story:** Som användare vill jag att programmet hittar strukturella fel som incest, cirkulära släktband och isolerade personer, så att jag kan åtgärda trasig data.

#### Acceptance Criteria

1. WHEN kontrollen "En person får inte vara gift med eller ha barn med ett syskon eller förälder" är aktiverad och en person är registrerad som partner eller förälder till barn med ett eget syskon (inklusive halvsyskon som delar minst en förälder) eller en egen förälder, THE Kontrollmotorn SHALL skapa ett Påpekande som anger den otillåtna relationen.
2. WHEN kontrollen "En person måste ha relationer till andra i arkivet" är aktiverad och en person saknar alla familjerelationer (varken partner, barn eller förälder i någon familj), THE Kontrollmotorn SHALL skapa ett Påpekande.
3. WHEN kontrollen "En person får inte vara anfader eller anmoder till sig själv" är aktiverad och en cirkulär anknytning upptäcks (personen återfinns som sin egen förfader vid traversering uppåt i familjeträdet oavsett djup), THE Kontrollmotorn SHALL skapa ett Påpekande.
4. WHEN kontrollen "Bildfiler och länkade filer måste finnas" är aktiverad och ett mediaobjekt refererar till en fil som inte existerar på den angivna sökvägen, THE Kontrollmotorn SHALL skapa ett Påpekande kopplat till den person som mediaobjektet tillhör; om mediaobjektet inte är kopplat till någon person SHALL Påpekandet ange filnamnet utan personkoppling.
5. WHEN kontrollen "Datum måste vara giltiga enligt den svenska kalendern" är aktiverad och ett datum på en person eller händelse inte är giltigt enligt Svenska_kalendern, THE Kontrollmotorn SHALL skapa ett Påpekande som anger det ogiltiga datumet och vilken händelse det gäller.
6. WHEN kontrollen "En person måste ha en koppling till huvudpersonen" är aktiverad och en person inte kan nås genom att traversera familjerelationer från Huvudpersonen, THE Kontrollmotorn SHALL skapa ett Påpekande.
7. IF kontrollen "En person måste ha en koppling till huvudpersonen" är aktiverad och ingen Huvudperson är definierad i Projektet, THEN THE Kontrollmotorn SHALL hoppa över den kontrollen utan att skapa Påpekanden.

### Requirement 10: Konfigurationsbeständighet

**User Story:** Som användare vill jag att mina kontrollinställningar sparas, så att jag inte behöver konfigurera om allt varje gång jag öppnar dialogen.

#### Acceptance Criteria

1. WHEN användaren stänger Kontrollera_personer_dialogen (via "Stäng"-knappen, fönstrets stängknapp eller Escape-tangenten), THE Applikationen SHALL spara samtliga kontrollinställningar till projektinställningarna, inklusive: kryssrutan "Utför kontroller" på Åldersfliken, alla individuella kryssrutor och tröskelvärden på Åldersfliken, samt alla kryssrutor på Fler_kontroller_fliken.
2. WHEN användaren öppnar Kontrollera_personer_dialogen, THE Applikationen SHALL ladda de senast sparade kontrollinställningarna från projektinställningarna och populera alla fält med de sparade värdena, så att konfigurationen är identisk med den som gällde vid senaste stängning.
3. IF inga sparade kontrollinställningar finns (första användningen), THEN THE Applikationen SHALL använda standardvärden för tröskelvärden enligt Requirement 5 kriterium 5, markera kryssrutan "Utför kontroller" på Åldersfliken som aktiverad, samt markera alla individuella kontroller på både Åldersfliken och Fler_kontroller_fliken som aktiverade.
4. IF sparade kontrollinställningar saknar värden för en kontroll som finns i dialogen (till exempel efter en programuppdatering som lagt till nya kontroller), THEN THE Applikationen SHALL använda standardvärden för de saknade kontrollerna och bevara de befintliga sparade värdena oförändrade.
5. IF sparning av kontrollinställningar misslyckas, THEN THE Applikationen SHALL visa ett felmeddelande som indikerar att inställningarna inte kunde sparas, och dialogen SHALL fortfarande stängas.

### Requirement 11: Prestanda och användaråterkoppling

**User Story:** Som användare vill jag få återkoppling under kontrollkörningen, så att jag vet att programmet arbetar och inte har hängt sig.

#### Acceptance Criteria

1. WHEN kontrollkörningen startar, THE Applikationen SHALL visa en framstegsindikator i Kontrollera_personer_dialogen som visar hur stor andel av kontrollerna som slutförts (0–100 %).
2. WHILE kontrollkörningen pågår, THE Applikationen SHALL förbli responsiv så att användaren kan interagera med fönstret (t.ex. flytta eller stänga dialogen) utan att gränssnittet fryser i mer än 200 millisekunder.
3. WHILE kontrollkörningen pågår, THE Applikationen SHALL inaktivera knappen "Kontrollera" för att förhindra att en ny körning startas innan den pågående är klar.
4. WHEN kontrollkörningen är klar, THE Applikationen SHALL dölja framstegsindikatorn, aktivera knappen "Kontrollera" och visa resultaten i Resultatfliken.
5. THE Kontrollmotorn SHALL slutföra kontroller av ett projekt med upp till 10 000 personer inom 30 sekunder på en dator med minst 4 CPU-kärnor och 8 GB RAM.
