# Review implementacji i rekomendacji

Data: 2026-04-04

## Findings

1. Wysokie: eGFR jest błędnie opisane jako pojedynczy pomiar.

   Analiza trendu świadomie odrzuca rekordy progowe, a późniejsza reguła traktuje markery z jednym dokładnym punktem trendu jako `pojedynczy pomiar`. W efekcie raport generuje rekomendację powtórzenia badania, mimo że w danych wejściowych jest siedem obserwacji eGFR, z czego sześć to wartości progowe. To zawyża niepewność i wprowadza mylący opis.

2. Wysokie: strzałki trendu w raporcie przeczą znakowi zmiany procentowej.

   Kliniczny kierunek jest mapowany do stałych symboli i renderowany obok liczbowej zmiany. W rezultacie raport pokazuje np. `↓✗ +9.8%` dla LDL, `↓✗ +27.3%` dla TSH i `↓✗ +13.3%` dla potasu. Wizualnie wygląda to jak spadek, choć liczba pokazuje wzrost.

3. Średnie: rekomendacje morfologii mieszają markery bezwzględne i procentowe pod tą samą nazwą.

   Silnik rekomendacji używa wyłącznie `label_pl`, mimo że katalog rozróżnia osobne markery `abs` i `%` dla takich parametrów jak neutrofile, limfocyty czy eozynofile. W efekcie w rekomendacji medycznej pojawia się np. `Neutrofile` dwukrotnie, bez wskazania, że chodzi o dwie różne miary.

4. Średnie: tekst o cholesterolu całkowitym przeczy własnej ocenie lipidogramu.

   Reguła łagodząca komunikat stwierdza, że wynik jest mało istotny przy `prawidłowym LDL i Apo B`, ale nie sprawdza, czy LDL i Apo B rzeczywiście są prawidłowe. W tym samym raporcie Apo B i LDL są powyżej optimum, więc rekomendacja zawiera wewnętrzną sprzeczność.

## Assumptions

- Wartości progowe eGFR powinny nadal liczyć się jako historyczne obserwacje do oceny, czy marker jest jednorazowy, nawet jeśli są wyłączone z regresji liniowej.
- W rekomendacjach użytkownik powinien widzieć rozróżnienie między wariantami `abs` i `%`, gdy oba występują dla tego samego markera klinicznego.

## Summary

Pipeline działa end-to-end: parser, konsolidacja, statusy, trendy, rekomendacje i render HTML uruchamiają się bez błędów wykonania. Główne problemy dotyczą semantyki rekomendacji i spójności prezentacji trendów, nie samego uruchamiania skryptu.

## Suggested fixes

1. Rozdzielić kierunek matematyczny od interpretacji klinicznej w renderowaniu trendów.
2. Oprzeć komunikat o `pojedynczym pomiarze` na liczbie wszystkich skonsolidowanych obserwacji, nie tylko punktów użytych do regresji.
3. Rozróżniać markery `abs` i `%` w tekście rekomendacji.
4. Usunąć albo uwarunkować komunikat o `prawidłowym LDL i Apo B` rzeczywistym statusem tych markerów.