# Plan analizy wyników badań krwi — SmartDoc

> Wersja po weryfikacji: doprecyzowana pod implementację, walidację danych i bezpieczne rekomendacje.

## 1. Cel projektu

Stworzenie reusable, audytowalnego skryptu Python (`generate_report.py`) generującego interaktywny raport HTML w języku polskim, który:

- Ocenia stan zdrowia na podstawie ~75 CSV z wynikami badań krwi (2022-2026)
- Porównuje wyniki z **optymalnymi zakresami** medycyny prewencyjnej (nie tylko normami lab)
- Analizuje **trendy czasowe** — co się poprawia, co pogarsza
- Wydaje **spersonalizowane, ostrożne rekomendacje** dotyczące diety, suplementacji i stylu życia
- Wyraźnie oddziela odchylenia względem norm laboratoryjnych od odchyleń względem zakresów optymalnych i hipotez wymagających konsultacji lekarskiej

## 2. Profil pacjenta

| Parametr | Wartość |
|---|---|
| Płeć | Mężczyzna |
| Wiek | 42 lata |
| Aktywność fizyczna | 1-2h dziennie |
| Suplementacja | D3+K2, magnez, omega-3, kurkumina, probiotyki |
| Znane schorzenia | Brak |

## 3. Dane wejściowe

**Lokalizacja:** `wynki_diag/` — pliki CSV rozdzielane średnikiem (`;`)

**Format CSV:**
```
Badanie;Parametr;Kod zlecenia;Data;Wynik;Zakres referencyjny;Opis
```

**Uwagi techniczne:**
- Pliki z sufiksem `(1)`, `(2)` często są kopiami, ale nie wolno zakładać, że każdy taki plik jest duplikatem logicznym
- Ten sam marker logiczny może występować jako wartość bezwzględna, procentowa lub wskaźnik w osobnych plikach, mimo identycznej nazwy `Parametr`
- Do identyfikacji markera używać kanonicznego `marker_id`, budowanego z nazwy kanonicznej + jednostki + typu wyrażenia (`abs`, `%`, `ratio`, `calculated`) + grupy badania
- Niektóre wyniki zawierają `<` lub `>` (np. `<0.3 mg/l`) — zapisywać zarówno operator, jak i wartość liczbową
- Daty w formacie `DD-MM-YYYY HH:MM:SS`
- Zakres referencyjny bywa pusty, a czasem zmienia się między latami lub metodami — zachować zarówno zakres raw, jak i sparsowane `lab_low` / `lab_high`
- W każdym rekordzie zachować provenance: `source_file`, `Kod zlecenia`, `Badanie`, `Opis`

**Model rekordu po normalizacji (minimum):**
```
marker_id, marker_label_pl, group, expression_type, unit,
collected_at, collected_date,
raw_value, numeric_value, comparator,
lab_range_raw, lab_low, lab_high,
source_file, source_order_id, source_badanie, source_notes
```

Jeżeli `Opis` zawiera informację o zmianie metody lub wartości referencyjnych, rekord powinien dostać dodatkową flagę jakości danych.

**Polityka deduplikacji i konsolidacji:**
1. `Exact duplicate`: ten sam `marker_id`, timestamp, wynik raw i `Kod zlecenia` — zachować 1 rekord.
2. `Same-day repeat`: wiele zgodnych pomiarów tego samego dnia — w warstwie surowej zachować wszystkie, do trendu wybrać 1 rekord per dzień per marker.
3. `Same-day conflict`: wiele różnych wyników tego samego dnia — wybrać rekord raportowy deterministycznie (domyślnie najpóźniejszy timestamp), ale oznaczyć konflikt i pokazać go w sekcji jakości danych.

**Zakres dat:** od 27-06-2022 do 20-03-2026 (najnowsze pomiary)

## 4. Grupy badań i markery

Poniższe tabele są snapshotem obecnego zestawu danych i mają służyć jako referencja walidacyjna dla implementacji. Nie powinny być hardkodowane jako logika raportu.

### 4.1 Układ krążenia / Lipidogram
| Marker | Najnowszy wynik | Norma lab | Zakres optymalny | Pomiarów | Status |
|---|---|---|---|---|---|
| Cholesterol całkowity | 191.8 mg/dl | 115-190 | < 180 mg/dl | 11 | POWYŻEJ OPT |
| Cholesterol HDL | 78.7 mg/dl | >40 | > 60 mg/dl | 11 | OK |
| Cholesterol LDL | 105.6 mg/dl | <115 | < 100 mg/dl | 11 | POWYŻEJ OPT |
| Cholesterol nie-HDL | 113.1 mg/dl | <130 | < 100 mg/dl | 11 | POWYŻEJ OPT |
| Triglicerydy | 37.2 mg/dl | <100 | < 80 mg/dl | 11 | OK |
| Apo B | 0.89 g/l | 0.66-1.44 | < 0.80 g/l | 5 | POWYŻEJ OPT |
| Homocysteina | 12.8 µmol/l | <15 | < 10 µmol/l | 1 | POWYŻEJ OPT |
| D-dimer | <0.19 µg/ml | <0.5 | < 0.5 µg/ml | 3 | OK |
| hsCRP | <0.40 mg/l | <5 | < 1.0 mg/l | 1 | OK |

### 4.2 Gospodarka węglowodanowa
| Marker | Najnowszy wynik | Norma lab | Zakres optymalny | Pomiarów | Status |
|---|---|---|---|---|---|
| Glukoza | 89 mg/dl | 70-99 | < 90 mg/dl (na czczo) | 8 | GRANICA OPT |
| HbA1c | 5.7% | 4-6% | < 5.4% | 3 | POWYŻEJ OPT |

### 4.3 Hormony płciowe i przysadka
| Marker | Najnowszy wynik | Norma lab | Zakres optymalny | Pomiarów | Status |
|---|---|---|---|---|---|
| Testosteron | 894 ng/dl | 249-836 | 500-900 ng/dl | 7 | GRANICA OPT (górna) |
| Testosteron wolny | 32.8 pg/ml | 9.57-40.6 | 15-35 pg/ml | 2 | OK |
| SHBG | 66.3 nmol/l | 18.3-54.1 | 20-50 nmol/l | 1 | POWYŻEJ OPT |
| LH | 4.36 mIU/ml | 1.7-8.6 | 2-8 mIU/ml | 1 | OK |
| FSH | 2.75 mIU/ml | 1.5-12.4 | 1.5-8 mIU/ml | 1 | OK |
| Prolaktyna | 175 mIU/l | 86-324 | 85-300 mIU/l | 1 | OK |
| IGF-1 | 138 ng/ml | 94.4-223 | 120-200 ng/ml | 8 | OK |

### 4.4 Tarczyca
| Marker | Najnowszy wynik | Norma lab | Zakres optymalny | Pomiarów | Status |
|---|---|---|---|---|---|
| TSH | 2.47 µIU/ml | 0.27-4.2 | 0.5-2.0 µIU/ml | 9 | POWYŻEJ OPT |
| FT4 | 1.19 ng/dl | 0.92-1.68 | 1.1-1.5 ng/dl | 6 | OK |

### 4.5 Prostata
| Marker | Najnowszy wynik | Norma lab | Zakres optymalny | Pomiarów | Status |
|---|---|---|---|---|---|
| PSA | 0.469 ng/ml | <2 | < 1.0 ng/ml | 5 | OK |
| fPSA/PSA | 35.39% | — | > 25% | 5 | OK |

### 4.6 Wątroba
| Marker | Najnowszy wynik | Norma lab | Zakres optymalny | Pomiarów | Status |
|---|---|---|---|---|---|
| ALT | 16 U/l | <41 | < 25 U/l | 5 | OK |
| AST | 23 U/l | <40 | < 25 U/l | 5 | OK |
| Bilirubina | 0.43 mg/dl | <1.2 | 0.3-1.0 mg/dl | 5 | OK |
| GGTP | 10 U/l | 10-71 | < 30 U/l | 5 | OK |
| Fosfataza zasadowa | 40 U/l | 40-129 | 40-100 U/l | 5 | OK |

### 4.7 Nerki
| Marker | Najnowszy wynik | Norma lab | Zakres optymalny | Pomiarów | Status |
|---|---|---|---|---|---|
| Kreatynina | 1.09 mg/dl | 0.7-1.2 | 0.8-1.1 mg/dl | 7 | OK |
| eGFR | 87.44 ml/min | >=90 | > 90 ml/min | 7 | PONIŻEJ OPT |

### 4.8 Stan zapalny
| Marker | Najnowszy wynik | Norma lab | Zakres optymalny | Pomiarów | Status |
|---|---|---|---|---|---|
| CRP | <0.3 mg/l | <5 | < 1.0 mg/l | 7 | OK |
| hsCRP | <0.40 mg/l | <5 | < 1.0 mg/l | 1 | OK |

### 4.9 Minerały i elektrolity
| Marker | Najnowszy wynik | Norma lab | Zakres optymalny | Pomiarów | Status |
|---|---|---|---|---|---|
| Wapń | 2.4 mmol/l | 2.15-2.5 | 2.2-2.5 mmol/l | 8 | OK |
| Fosfor | 1.1 mmol/l | 0.81-1.45 | 0.9-1.3 mmol/l | 1 | OK |
| Magnez | 0.81 mmol/l | 0.66-1.07 | 0.85-1.0 mmol/l | 8 | PONIŻEJ OPT |
| Żelazo | 90.8 µg/dl | 33-193 | 60-150 µg/dl | 4 | OK |
| Cynk | 73 µg/dl | 46-150 | 80-120 µg/dl | 1 | PONIŻEJ OPT |
| Miedź | 82-88 µg/dl | 70-140 | 80-120 µg/dl | 1 | OK |
| Selen | 99.62 µg/L | 63.2-158 | 100-140 µg/L | 1 | GRANICA OPT |
| Sód | 139 mmol/l | 136-145 | 138-142 mmol/l | 5 | OK |
| Potas | 4.85 mmol/l | 3.5-5.1 | 4.0-4.8 mmol/l | 5 | POWYŻEJ OPT |

### 4.10 Witaminy
| Marker | Najnowszy wynik | Norma lab | Zakres optymalny | Pomiarów | Status |
|---|---|---|---|---|---|
| Witamina D3 25(OH) | 46.1 ng/ml | >30 | 40-60 ng/ml | 7 | OK |

### 4.11 Metale ciężkie
| Marker | Najnowszy wynik | Norma lab | Zakres optymalny | Pomiarów | Status |
|---|---|---|---|---|---|
| Arsen | 5.71 µg/L | <10.7 | < 5 µg/L | 1 | LEKKO POWYŻEJ OPT |
| Ołów | 8.5 µg/l | <100 | < 20 µg/L | 1 | OK |
| Kadm | 0.16 µg/l | <0.5 | < 0.3 µg/L | 1 | OK |

### 4.12 Morfologia — kluczowe nieprawidłowości
| Marker | Najnowszy wynik | Norma lab | Zakres optymalny | Pomiarów | Status |
|---|---|---|---|---|---|
| Erytrocyty | 4.43 mln/µl | 4.6-6.5 | 4.5-5.5 mln/µl | 13 | PONIŻEJ NORMY |
| Hemoglobina | 13.7 g/dl | 13.5-18 | 14-16 g/dl | 13 | PONIŻEJ OPT |
| Hematokryt | 40.3% | 40-52% | 42-48% | 13 | PONIŻEJ OPT |
| Leukocyty | 3.39 tys/µl | 4-10 | 4-7 tys/µl | 13 | PONIŻEJ NORMY |
| Neutrofile % | 42.5% | 45-70% | 45-65% | 13 | PONIŻEJ NORMY |
| Limfocyty abs | 1.3 tys/µl | 1.5-4.5 | 1.5-3.0 tys/µl | 13 | PONIŻEJ NORMY |
| Eozynofile % | 9.4% | 0-5% | 0-4% | 13 | POWYŻEJ NORMY |
| Bazofile % | 1.5% | 0-1.1% | 0-1% | 13 | POWYŻEJ NORMY |
| Monocyty % | 9.1% | 2-9% | 2-8% | 13 | LEKKO POWYŻEJ |
| MPV | 12.7 fl | 7-12 | 8-11 fl | 13 | POWYŻEJ NORMY |

## 5. Zakresy optymalne — źródła referencyjne

Zakresy optymalne powinny być kategoryzowane według jakości źródła:
- `LAB` — zakres referencyjny dostarczony przez laboratorium
- `GUIDELINE` — wytyczne towarzystw naukowych lub rekomendacje o ugruntowanym statusie
- `HEURISTIC` — zakres prewencyjny oparty na literaturze lub konsensusie eksperckim
- `EXPLORATORY` — zakres pomocniczy o niższej jakości dowodów

Preferowana hierarchia źródeł:
- **GUIDELINE:** ESC/EAS, Polskie Towarzystwo Endokrynologiczne, American Thyroid Association, wytyczne D3 2023
- **HEURISTIC:** literatura medycyny prewencyjnej, np. Peter Attia, Mark Hyman — tylko z wyraźnym oznaczeniem, że nie jest to standard opieki
- **EXPLORATORY:** zakresy biohacking / functional, np. Blueprint — wyłącznie jako materiał pomocniczy, nie domyślna podstawa statusu

Każdy wpis w katalogu markerów powinien zawierać co najmniej: `source_label`, `source_type`, `evidence_level`, `notes`, `last_reviewed_at`.

> **UWAGA:** Zakresy optymalne mają charakter orientacyjny i NIE zastępują konsultacji lekarskiej. Raport nie stanowi diagnozy medycznej. Jeżeli dla markera brak mocnego źródła, raport powinien to jawnie oznaczyć.

## 6. Kluczowe obserwacje wstępne (do rozwinięcia w raporcie)

Poniższe obserwacje są ręcznym snapshotem obecnego zbioru i powinny służyć jako test akceptacyjny raportu. Algorytm nie powinien generować rozpoznań, tylko flagi i hipotezy do omówienia.

### WYMAGAJĄCE UWAGI (poza normą laboratoryjną)
1. **Leukocyty 3.39 tys/µl** — poniżej normy (4-10). Wymaga oceny trendu i kontekstu.
2. **Erytrocyty 4.43 mln/µl** — poniżej normy (4.6-6.5). Sygnał do oceny łącznie z Hb, Hct i trendem.
3. **Neutrofile % 42.5%** — poniżej normy (45-70%). Interpretować razem z neutrofilami w wartości bezwzględnej.
4. **Limfocyty abs 1.3 tys/µl** — poniżej normy (1.5-4.5). Limfopenia łagodna.
5. **Eozynofile % 9.4%** — powyżej normy (0-5%). Sprawdzić także wartość bezwzględną i kontekst kliniczny.
6. **Bazofile % 1.5%** — powyżej normy (0-1.1%). Warto ocenić równolegle z innymi składowymi morfologii.
7. **MPV 12.7 fl** — powyżej normy (7-12). Duże płytki.
8. **SHBG 66.3 nmol/l** — powyżej normy (18.3-54.1). Może wpływać na dostępność frakcji wolnej testosteronu.

### POWYŻEJ OPTYMALNYCH ZAKRESÓW (w normie lab, ale suboptymalne)
9. **HbA1c 5.7%** — norma lab (<6%), ale optymalnie <5.4%. Prediabetyczna granica.
10. **Apo B 0.89 g/l** — norma lab, optymalnie <0.80. Marker ryzyka CV.
11. **Homocysteina 12.8 µmol/l** — optymalnie <10. Możliwy sygnał związany z podażą / metabolizmem B6, B12 i folianów.
12. **TSH 2.47 µIU/ml** — optymalnie 0.5-2.0. Do oceny razem z FT4, objawami i trendem.
13. **LDL 105.6 mg/dl** — optymalnie <100. W kontekście Apo B — warto obniżyć.
14. **eGFR 87.44** — optymalnie >90. Interpretować łącznie z kreatyniną, nawodnieniem i masą mięśniową.
15. **Magnez 0.81 mmol/l** — optymalnie 0.85-1.0. Mimo suplementacji suboptymalne.
16. **Cynk 73 µg/dl** — optymalnie 80-120.

### POZYTYWNE
- Triglicerydy 37.2 — wybitnie niskie, świetny wynik
- HDL 78.7 — bardzo dobry
- CRP / hsCRP — praktycznie niewykrywalny stan zapalny
- D-dimer — niski, brak ryzyka zakrzepowego
- Witamina D3 46.1 — optymalny zakres (suplementacja działa)
- PSA 0.469 — bardzo niski, prostata zdrowa
- Wątroba (ALT, AST, GGTP, bilirubina) — wszystko idealne
- Testosteron 894 — wysoki, dobry wynik jak na 42 lata
- Metale ciężkie — w normie (arsen minimalnie, bez znaczenia klinicznego)

## 7. Struktura raportu HTML

```
raport_zdrowotny.html
├── Nagłówek: Tytuł, data, profil pacjenta
├── Podsumowanie wykonawcze (dashboard)
│   ├── Ogólna ocena zdrowia (skala kolorystyczna)
│   ├── Lista flag: ALERT / UWAGA / OK
│   └── Top 5 priorytetów zdrowotnych
├── Jakość danych
│   ├── Liczba wczytanych plików i rekordów
│   ├── Rekordy odrzucone / scalone / konfliktowe
│   ├── Markery z pomiarami progowymi `<` / `>` oraz niskim `n`
│   └── Markery ze zmianą metody lub zakresu referencyjnego
├── Sekcje szczegółowe (po jednej na grupę 4.1-4.12)
│   ├── Tabela: marker | wynik | norma lab | zakres optymalny | status
│   ├── Wykres Plotly: trend czasowy z pasmami norma/optymalny
│   ├── Metadane: liczba pomiarów, pewność trendu, ostatnia data
│   └── Komentarz do grupy
├── Analiza trendów
│   ├── Markery z trendem poprawy (↑)
│   ├── Markery z trendem pogorszenia (↓)
│   └── Markery stabilne (→)
├── Rekomendacje
│   ├── Pilne (konsultacja lekarska)
│   ├── Dieta
│   ├── Suplementacja (uwzgl. obecną)
│   ├── Styl życia / aktywność
│   └── Badania kontrolne do powtórzenia
├── Appendix: metodologia i źródła
│   ├── Katalog markerów i źródła zakresów
│   ├── Legendy statusów i poziomów pewności
│   └── Zasady konsolidacji danych
└── Disclaimer prawny
```

## 8. Architektura skryptu

```
generate_report.py
├── load_raw_data(directory) → DataFrame
│   ├── Wczytanie wszystkich CSV z wynki_diag/
│   ├── Zachowanie nazwy pliku źródłowego
│   ├── Parsowanie dat
│   └── Walidacja schematu wejściowego
├── normalize_records(df) → DataFrame
│   ├── Parsowanie wyników (obsługa <, >, jednostek)
│   ├── Normalizacja aliasów do `marker_id`
│   ├── Rozróżnienie `abs` / `%` / `ratio` / `calculated`
│   ├── Parsowanie zakresów lab do `lab_low` / `lab_high`
│   └── Zachowanie provenance i flag jakości danych
├── consolidate_measurements(df) → DataFrame
│   ├── Usuwanie `exact duplicates`
│   ├── Konsolidacja powtórzeń z tego samego dnia
│   └── Oznaczanie konfliktów i zmian metody
├── define_marker_catalog() → dict
│   └── `marker_id` → {label, group, unit, expression_type, optimal_range, fallback_lab_range, source_type, evidence_level}
├── assess_status(row, catalog_entry) → status_info
│   └── status + severity + basis (`lab` / `optimal` / `data_quality`)
├── analyze_trends(df, marker_id) → trend_info
│   └── slope, delta_pct, direction, confidence, sample_count
├── generate_plotly_chart(df, marker_id, catalog_entry) → html_div
│   └── Liniowy z pasmami referencyjnymi i oznaczeniem pomiarów progowych
├── generate_recommendations(results, profile) → list[dict]
│   └── rekomendacja + confidence + evidence + medical_escalation
├── render_html(report_context) → str
│   └── dashboard + sekcje szczegółowe + appendix jakości danych
└── main()
    └── Orchestracja: load → normalize → consolidate → assess → trends → recommend → render → save
```

Preferowana implementacja katalogu markerów: osobny moduł konfiguracyjny `marker_catalog.py`, aby nie hardkodować logiki w template HTML.

## 9. Wymagania techniczne

```
python >= 3.10
pandas >= 2.0
plotly >= 5.18
jinja2 >= 3.1
pytest >= 8.0
```

Brak potrzeby zewnętrznych API. Wszystko generowane lokalnie.

## 10. Kolejność implementacji

Implementacja podzielona na 6 faz. Każda faza daje uruchamialny, testowalny kod przed przejściem do kolejnej.

### Faza 1 — Ingest danych i normalizacja
**Pliki:** `generate_report.py` (szkielet), `marker_catalog.py` (aliasy)
- `load_raw_data()` — wczytanie wszystkich CSV z `wynki_diag/`, parsowanie dat, walidacja schematu, śledzenie pliku źródłowego
- `normalize_records()` — parsowanie wartości liczbowych (obsługa `<`/`>`), budowa `marker_id` z nazwy kanonicznej + jednostki + typu wyrażenia, parsowanie zakresów lab do `lab_low`/`lab_high`, zachowanie provenance
- `marker_catalog.py` — mapa aliasów (nazwy `Parametr` z CSV → kanoniczny `marker_id`), zainicjowana grupami odkrytymi z danych
- **Deliverable:** DataFrame z normalizowanymi rekordami, wydruk statystyk podsumowujących. Brak HTML.

### Faza 2 — Deduplikacja i konsolidacja
**Pliki:** `generate_report.py` (rozszerzenie)
- `consolidate_measurements()` — usuwanie exact duplicates, wybór rekordu z same-day repeats, flagowanie same-day conflicts
- Flagi jakości danych (zmiany metody z `Opis`, brakujące zakresy, wartości progowe)
- **Deliverable:** Oczyszczony, skonsolidowany DataFrame, wydruk statystyk deduplikacji.

### Faza 3 — Katalog markerów i ocena statusów
**Pliki:** `marker_catalog.py` (kompletny), `generate_report.py` (rozszerzenie)
- Kompletny `marker_catalog.py` — wszystkie ~60 markerów z zakresami optymalnymi, poziomami dowodów, etykietami źródeł
- `assess_status()` — porównanie najnowszej wartości z normą lab i zakresem optymalnym, zwraca status + severity + basis
- **Deliverable:** Tabela statusów dla wszystkich markerów, zgodna z obserwacjami z sekcji 6.

### Faza 4 — Analiza trendów
**Pliki:** `generate_report.py` (rozszerzenie)
- `analyze_trends()` — nachylenie regresji liniowej, delta%, kierunek (poprawa/pogorszenie/stabilny), pewność na podstawie liczby pomiarów
- Obsługa markerów z <3 punktami danych (flaga niskiej pewności)
- **Deliverable:** Wydruk podsumowania trendów, walidacja względem znanych wzorców (np. trend TSH, trend lipidów).

### Faza 5 — Silnik rekomendacji
**Pliki:** `generate_report.py` (rozszerzenie)
- `generate_recommendations()` — silnik reguł z poziomami pewności, źródłami dowodów, flagą `medical_escalation`
- Guardrails: nigdy nie diagnozuje, zawsze flaguje wartości poza normą lab do konsultacji lekarskiej
- Uwzględnia bieżącą suplementację i profil pacjenta
- **Deliverable:** Wydruk listy rekomendacji z priorytetami.

### Faza 6 — Raport HTML z wykresami Plotly
**Pliki:** `generate_report.py` (kompletny), `report_template.html` (szablon Jinja2)
- Szablon Jinja2: dashboard, sekcja per grupa markerów, wykresy trendów, sekcja jakości danych, rekomendacje, disclaimer
- `generate_plotly_chart()` — wykresy liniowe z pasmami normy lab i zakresów optymalnych
- `render_html()` + `main()` orkiestracja → `raport_zdrowotny.html`
- **Deliverable:** Kompletny interaktywny raport HTML.

## 11. Ograniczenia i disclaimer

- Raport ma charakter **informacyjny** — NIE jest diagnozą medyczną
- Raport nie stawia rozpoznań i nie powinien używać języka kategorycznego tam, gdzie dane wskazują jedynie podwyższone prawdopodobieństwo lub hipotezę
- Zakresy optymalne bazują na literaturze medycyny prewencyjnej i mogą się różnić od zaleceń lekarza prowadzącego
- Rekomendacje suplementacyjne i dietetyczne powinny być skonsultowane z lekarzem lub dietetykiem klinicznym
- Markery z niską liczbą pomiarów, konfliktami tego samego dnia lub zmianą metody muszą być oznaczane jako niższa pewność
- Analiza trendów jest statystyczna — nie uwzględnia pełnego kontekstu klinicznego (choroba, stres, pora roku, nawodnienie, wysiłek, pora pobrania itp.)

## 12. Kryteria akceptacji

- Żaden wykres ani trend nie miesza wartości `abs`, `%`, `ratio` dla tego samego markera logicznego
- Parser poprawnie obsługuje puste zakresy, wartości progowe i zmiany referencji laboratoryjnych
- Każdy status zawiera informację, czy wynika z normy lab, zakresu optymalnego czy jakości danych
- Każda rekomendacja ma `confidence` i podstawę merytoryczną
- Raport pokazuje sekcję jakości danych oraz liczbę pomiarów dla każdego markera
- Bieżący zestaw danych reprodukuje kluczowe obserwacje z sekcji 6 bez hardkodowania wyników w kodzie
