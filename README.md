# Släktbusken

Släktbusken är ett svenskt släktforskningsprogram för Windows. Det har byggts för att se hur svårt det är att göra ett eget släktforskningsprogram med hjälp av specdriven AI-programmering. Namnet är en ordlek med att familjesituationerna inte alltid är ett rakt växande träd bakåt, utan det kan vara anförluster genom kusingiften, fosterbarn, spermadonation med mera.

Målgruppen för programmet är jag själv, så funktionerna byggs upp för att passa mig och mina behov. Om någon annan tycker att programmet verkar användbart så är det bara att ladda ner och börja använda. Om du känner att det är något som inte är riktigt som du vill är det fritt fram att ändra i källkoden hos dig.

**Status:** version 0.3.1 är en betaversion. Programmet fungerar och används, men det finns ännu ingen färdig 1.0. Ta kopior av dina projektmappar innan du uppgraderar, eftersom ett projekt som sparats i en nyare version inte går att öppna i en äldre.

# Ladda ner och kom igång

- **Färdigt program:** ladda ner den senaste versionen under *Releases* här på GitHub. Packa upp mappen och starta `Slaktbusken.exe`. Ingen installation behövs.
- **Från källkoden:** kräver Python 3.11 eller senare.

```
pip install -e .[dev]
python -m slaktbusken
```

Ett projekt består av en mapp med en komprimerad JSON-fil (`.json.gz`) och ett antal undermappar för foton och bilder på källor. Äldre projekt uppgraderas automatiskt när de öppnas. Alla referenser till foton och källbilder är relativa, så om du kopierar hela projektet till en annan dator så kommer den hitta alla filerna.

# Huvudfunktioner

## Personer, familjer och händelser

- Personer med flera namn, där varje namn har en typ (till exempel födelsenamn eller gift namn). Ett namnbyte kan kopplas till en händelse, till exempel ett bröllop, i stället för att alla efternamn skrivs på samma rad.
- Familjer med valfritt antal partner och egna roller (make, maka, partner med flera). Samkönade par och okänt kön hanteras utan att programmet gissar.
- Föräldraskap i flera slag: biologiskt, adoptiv, foster, steg, och donator.
- Händelser med datum, plats, deltagare och källor. Datum kan vara osäkra ("omkring", "före"), julianska, eller sparas som original om de inte går att tolka.
- Personlista med filter, och en detaljerad vy över den markerade personen.

## Boendeperioder

Boenden registreras som perioder på en plats, med osäkra start- och slutdatum, roll i hushållet och observationer från olika källor (till exempel flera husförhör). Du kan klistra in många observationer på en gång, slå ihop boenden och se vilka som bodde på en viss plats ett visst år (Verktyg, *Boende på plats*).

## Foster- och adoptivföräldrar

Placering i fosterhem och adoption registreras som händelser. De visas i diagram, familjevy, rapporter och släktskapsberäkningar, och du kan själv välja vilka föräldrar som visas för en person.

## Diagram och utskrift

- **Familjevy**, **antavla** (uppåt) och **ättlingar** (nedåt).
- Utskrift eller PDF av en vy, uppdelad på flera sidor när den är stor.
- Släktskapsberäknare som visar hur två personer är släkt.

<img width="989" height="764" alt="Skärmbild 2026-11-18 232746" src="https://github.com/user-attachments/assets/34860400-c4d2-4526-8189-9f901b0e09e9" />

## Hierarkisk struktur på platser

Alla län ska tillhöra ett land, alla socknar ska tillhöra ett län, alla kyrkor, byar, skolor etc ska tillhöra en socken. Jag vet att det finns vissa som föredrar att lagra socknar på landskap, men jag har valt att lägga upp strukturen så som jag själv vill ha den. Det här gör att det kan bli ett litet extra steg att lägga till nya platser, men jag tror det blir enklare att hantera på sikt. I alla fall så som jag vill kunna söka (till exempel alla platser av en viss typ i ett län eller i en socken).

<img width="903" height="517" alt="Skärmbild 2026-11-18 232949" src="https://github.com/user-attachments/assets/16adf068-6dda-43a2-a526-a39b8a5b9759" />

Platser kan också ha latitud och longitud. Det används för kartan (menyn *Karta*) och är tänkt att göra att kartfunktionen i Arkiv Digital fungerar med GEDCOM-filer som exporterats från Släktbusken.

## Källhantering

Källor kan hänvisa till bilder. Om du har laddat ner en kopia av kyrkbokens sida kan du hänvisa till den i källan, och den går att nå från alla ställen där källan används. Källor kan ha en leverantör (till exempel Arkiv Digital eller Sveriges Dödbok Webb) och en källtyp, och källhänvisningar kan ha kommentarer. Det går att filtrera personlistan på källa, och en ikon visar vilka personer som har källor. Hur källor ska fungera i detalj är fortfarande under utveckling och ändras utifrån tester med olika typer av källor.

<img width="800" height="762" alt="Skärmbild 2026-11-18 233055" src="https://github.com/user-attachments/assets/d343da6e-b6b7-4811-b87e-d9256bfe5db1" />

## Forskning

Forskningsärenden med åtgärder att göra, hypoteser och anteckningar, kopplade till personer, källor och andra poster. Ett förstoringsglas i personlistan och i diagrammen visar var det finns pågående forskning. Menyn *Forskning* har en översikt, en lista över vad som återstår att göra och alla hypoteser.

## DNA och kluster

Du kan lägga till DNA-företag och DNA-prov för dig själv, de du testat och andra matcher, och registrera matcher och segment mellan personer med test. Personer kan läggas i kluster, och en person kan vara med i flera. Trianguleringar stöds.

## Jämföra och slå ihop personer

Programmet föreslår personer som kan vara samma person och sparar förslagen i ett register. I jämförelsefönstret ser du de två personerna sida vid sida. Sammanslagningen visar varje del, konflikt och val innan något ändras, och det går att se en historik över alla sammanslagningar. Sammanslagningen körs i bakgrunden och återställs om programmet kraschar mitt i.

<img width="1404" height="831" alt="Skärmbild 2026-11-18 233232" src="https://github.com/user-attachments/assets/a5408aee-e6ca-4ce4-ab1c-ad405f6c6ecb" />


## GEDCOM

Släktbusken importerar och exporterar GEDCOM 5.5.1.

- **Import:** görs på en kopia av projektet och avbryts utan ändringar om något oväntat går fel. En ny import av samma fil skapar inga dubbletter och tar inte bort något du redan har.
- **Export:** tar med familjehändelser, anteckningar, titlar, namntyper, partnerroller, källhänvisningar, boenden, källor och arkiv. Det som inte har någon plats i standarden skrivs i egna taggar som börjar med `_SLK_`. Släktbusken läser dem vid import, men andra program hoppar vanligen över dem eller tar bort dem när de sparar filen.
- **Rundresa:** en export till GEDCOM och en import igen ska ge samma projekt. Det testas automatiskt, och skillnaderna som finns kvar är dokumenterade.

Kända begränsningar:
- Media och platstyper exporteras inte ännu.
- Andra program kan visa partner som make och hustru, även för samkönade par eller när könet är okänt.
- Äldre GEDCOM-filer från Släktbusken som saknar ordentliga nummer i vissa poster kan ge några dubbletter om de importeras tillsammans med en ny export.
- En uppdateringsimport kan i dag skriva över namn, anteckningar, titel och yrke hos en befintlig person. Att kunna granska varje skillnad innan något ändras är ett krav för 1.0 (se `docs/release-checklist.md`).

## Skydd mot dataförlust

Datan är det viktigaste i ett släktforskningsprogram, så mycket arbete har lagts på att inte tappa något:

- Säker sparning: projektet kontrolleras efter varje sparning och återställs efter en krasch. Om filen har ändrats av ett annat program skrivs den inte över.
- En avbruten redigering återställer uppgifterna som de var innan.
- Ett äldre projekt säkerhetskopieras innan det uppgraderas till ett nyare format.
- Referenser mellan personer, familjer och händelser kontrolleras, och en särskild uppsättning tester får aldrig hoppas över (se *Tester*).

## Rapporter

Menyn *Rapporter* har bland annat ansedel och källrapport, samt kontrollrapporter för geografi, media, forskning och sammanslagningar. Verktyget *Kontrollera personer* letar efter ovanliga eller saknade uppgifter.

## Utseende

Ljust, mörkt eller systemets inställning (Inställningar). Fönsterpositioner och kolumnbredder sparas mellan sessionerna.

# Planerat

Det här är sådant som jag vill ha men som inte är klart:

- **Importdiff:** om jag har gjort ändringar i ett annat program ska jag kunna importera skillnaderna till Släktbusken och godkänna dem en och en.
- Fler rapporter, bland annat antavla, ättlingar och DNA-rapporter. Flera av dem finns i menyn men är inte färdiga.
- Export av media och platstyper till GEDCOM.

# Tester

Hela sviten körs med `python -m pytest`. De obligatoriska testgrupperna (bevarande av referenser, familjeintegritet, misslyckade sammanslagningar, återställning efter krasch, pensionerade id:n, GEDCOM-återimport, dataskydd och GEDCOM-rundresa) körs strikt, utan tillåtna skip, med:

```
python scripts/run_mandatory_tests.py
```

Se `tests/MANDATORY_TESTS.md` för detaljer och utgångskoder. Skillnaderna i GEDCOM-rundresan kan skrivas ut som en rapport med `python scripts/gedcom_roundtrip_report.py`.

# Licens

Släktbusken är fri och öppen källkod under MIT-licensen. Du får använda programmet, ändra i koden och bygga egna versioner om du vill.

Se LICENSE för den fullständiga licenstexten.

Programmet är ett hobbyprojekt och tillhandahålls utan garanti. Det är byggt i första hand för mina egna behov, men om det även är användbart för andra är det bara roligt.
