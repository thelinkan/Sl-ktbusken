# Släktbusken
Släktbusken är ett projekt för att se hur svårt det är att bygga ett eget släktforskningsprogram med hjälp av specdriven AI-programmering. Namnet är en ordlek med att familjesituationerna inte alltid är ett rakt växande träd bakåt, utan det kan vara anförluster genom kusingiften, fosterbarn, spermadonation med mera. Målgruppen för programmet är jag själv, så funktionerna byggs upp för att passa mig och mina behov. Om någon annan tycker att programmet verkar användbart så är det bara att ladda ner och börja använda. Om du känner att det är något som inte är riktigt som du vill är det fritt fram att ändra i källkoden hos dig.

Projektet är rätt nyskapat, så det finns ännu ingen färdig version, men det går att klona repot och testa. 

# Vad är speciellt

En orsak till att jag gör ett eget program är för att det är funktionalitet jag vill ha lite annorlunda mot de program jag provat.

## Hierarkisk struktur på platser

Alla län ska tillhöra ett land, alla socknar ska tillhöra ett län, alla kyrkor, byar, skolor etc ska tillhöra en socken. Jag vet att det finns vissa som föredrar att lagra socknar på landskap, men jag har valt att lägga upp strukturen så som jag själv vill ha den. Det här gör att det kan bli ett litet extra steg att lägga till nya platser, men jag tror det blir enklare att hantera på sikt. I alla fall så som jag vill kunna söka (tex alla platser av en viss typ i ett län eller i en socken). 

Det finns också plats för latitud och longitud i formulären. En funktion som ska kunna användas för att kartfunktionen i Arkiv Digital ska fungera på GEDCOM-filer exporterade från Släktbusken.

## Källhantering

Källor lagras med möjlig hänvisning till bilder. Så om man laddat ner en kopia av kyrkbokens sida, så kan man hänvisa till den i källan och den kommer gå att nå från alla ställen där den källan hänvisar till. Det går också att skriva kommentarer till källhänvisningar. Det här är en av de funktioner som det ännu inte är exakt klart hur de ska fungera, utan det kommer ändras utifrån tester av olika typer av källor. Men tex till källor hos arkiv digital och Sveriges Dödbok Webb så kommer iaf ha ett fält för "genväg".

## DNA-stöd

Det går att på sig själv, de man testat och andra matcher att lägga till att de har DNA-prov och därefter lägga till matcher med kvalitet mellan personer med test. Det ska så småningom också gå att lägga till trianguleringar.

Förutom själva proven så kan man lägga till personer i kluster. En person kan vara med i mer än ett kluster.

## Importdiff

En funktion jag vill ha i Släktbusken är att om jag gjort ändringar i ett annat program så ska jag kunna importera diffar till släktbusken. 


