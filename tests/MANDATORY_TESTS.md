# Obligatoriska tester (Requirement 35)

Sex testgrupper för funktionen "jämför och slå ihop personer" får aldrig hoppas över,
markeras `xfail` eller väljas bort. De är:

| Grupp | Krav | Egenskaper |
|---|---|---|
| Bevarande av personreferenser | 35.1(a) | 25, 29, 30, 31 |
| Familje- och släktskapsintegritet | 35.1(b) | 32 till 35 |
| Misslyckade sammanslagningar | 35.1(c) | 39, 47 |
| Återställning efter krasch | 35.1(d) | 40, 41, 49 |
| Bevarande av pensionerade id:n | 35.1(e) | 3 |
| GEDCOM-återimport efter sammanslagning | 35.1(f) | 42, 43 |

Modulerna och de namngivna testerna står i `tests/mandatory_groups.py`, som är den enda
källan för conftest-hakarna, vakttestet och körskriptet.

## Kommandot

```
python scripts/run_mandatory_tests.py
```

Skriptet:

- sätter `QT_QPA_PLATFORM=offscreen` och `SBK_MANDATORY_STRICT=1`,
- kör `tests/test_meta` och alla moduler i grupperna med `--strict-markers -p no:randomly`
  (aldrig `-k` eller `-m`),
- läser JUnit-XML och kontrollerar per grupp att alla obligatoriska tester finns, kördes och
  gick igenom utan skip, xfail eller bortval,
- skriver en rad per grupp ("Obligatoriska testgrupper: ..."),
- på Windows (`win32`) körs även `tests/test_services/test_commit_preflight.py`, och ett
  hoppat `windows_only`-test räknas som fel (på andra plattformar får de hoppas över).

Utgångskoder:

| Kod | Betydelse |
|---|---|
| 0 | Alla grupper gröna |
| 1 | Minst ett test misslyckades eller hoppades över |
| 3 | Obligatoriska tester eller moduler saknas, eller ett har valts bort |

## Övrigt

- Hela sviten körs separat med `python -m pytest`. Det obligatoriska kommandot ersätter den inte.
- Strikt läge (`SBK_MANDATORY_STRICT=1`) gör att conftest avbryter körningen med kod 3 om ett
  obligatoriskt test saknas eller väljs bort.
- Kör man bara `python -m pytest` omvandlas hoppade eller xfail-ade obligatoriska tester ändå
  till fel av conftest.
- Det finns ingen CI-konfiguration i repot (ingen `.github/workflows`). Lägg kommandot ovan
  som ett steg vid sidan av `python -m pytest` när CI införs.
