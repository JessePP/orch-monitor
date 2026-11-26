# Orchestrator Monitor – plan budowy i przypadki testowe

·

Plan dzieli budowę aplikacji na 22 małe kroki. Każdy ma cel, kryteria akceptacji i przypadki testowe, które da się uruchomić automatycznie w pipeline. Opiera się na specyfikacji v1.1.

## Zasady

**Stos:** Python 3.12, PySide6, httpx, keyring, pydantic (modele i ustawienia), openpyxl (Excel), PyInstaller. Testy: pytest, pytest-qt (UI), respx (mock HTTP), freezegun (czas). Jakość: ruff (lint i format), mypy.

**Struktura repo**

```
orch_monitor/
  config/      ustawienia, sekret (keyring)
  api/         auth, klient OData, foldery
  services/    roboty, joby, kolejki, raporty
  refresh/     harmonogram odświeżania, snapshoty
  notify/      silnik i wyświetlanie powiadomień
  ui/          okno, zakładki, dialogi
  reports/     agregacja, eksport CSV i Excel
tests/
  unit/  ui/  fixtures/   (przykładowe odpowiedzi API jako JSON)
```

**Zasady dla pipeline**

- Jeden krok = jedna gałąź / jeden PR. Krok nie zaczyna się, dopóki kroki z kolumny „Zależy od” nie są zamknięte.
- Warstwy `api`, `services`, `notify`, `reports` nie importują PySide6. Dzięki temu ich testy działają bez ekranu.
- Testy w CI nigdy nie łączą się z prawdziwym Orchestratorem: cały HTTP mockowany przez respx na podstawie fixture w `tests/fixtures/`.
- Czas zawsze wstrzykiwany (`clock: Callable[[], datetime]`) albo zamrażany freezegunem, żeby testy granicy doby były deterministyczne.
- Identyfikatory testów: `TC-<krok>.<nr>`, np. `TC-07.3`. Nazwa testu w kodzie zawiera ten identyfikator.

**Definition of Done (każdy krok)**

1. Wszystkie przypadki testowe kroku zaimplementowane i zielone.
2. `ruff check`, `ruff format --check` i `mypy` bez błędów.
3. Wcześniejsze testy nadal zielone.
4. Pokrycie nowego kodu w `api`, `services`, `notify`, `reports` co najmniej 85%.
5. Krótka notka w `CHANGELOG.md`.

## Kolejność kroków

Kroki w obrębie etapu idą po kolei; kroki z różnymi zależnościami (np. 06, 07, 08) można robić równolegle.

| Krok | Element | Etap | Zależy od |
|---|---|---|---|
| 01 | Szkielet repo i CI | A | – |
| 02 | Ustawienia i sekret | A | 01 |
| 03 | Autoryzacja OAuth | A | 02 |
| 04 | Klient OData | A | 03 |
| 05 | Foldery | A | 04 |
| 06 | Serwis robotów | B | 05 |
| 07 | Serwis jobów (Running, Pending, Faulted) | B | 05 |
| 08 | Serwis kolejek – dziś | B | 05 |
| 09 | Szczegóły kolejki (AE/BE) | B | 08 |
| 10 | Harmonogram odświeżania i snapshot | B | 06, 07, 08 |
| 11 | Okno główne i ikona w zasobniku | C | 01 |
| 12 | Zakładka 1: statusy robotów | C | 10, 11 |
| 13 | Zakładka 2: działające i oczekujące | C | 10, 11 |
| 14 | Zakładka 3: kolejki, szczegóły, CSV | C | 09, 10, 11 |
| 15 | Okno ustawień | C | 02, 05, 11 |
| 16 | Silnik powiadomień | D | 10 |
| 17 | Wyświetlanie i wyciszenie powiadomień | D | 11, 16 |
| 18 | Raporty: agregacja | E | 07, 08 |
| 19 | Raporty: eksport CSV i Excel | E | 18 |
| 20 | Raporty: okno raportu | E | 11, 19 |
| 21 | Logi do pliku | F | 04 |
| 22 | Pakowanie .exe i test na tenancie | F | wszystkie |

## Etap A: Fundamenty

### 01. Szkielet repo i CI

- **Cel:** pusty, uruchamialny projekt z narzędziami jakości i pipeline.
- **Zakres:** `pyproject.toml`, struktura katalogów z sekcji Zasady, `orch_monitor/__main__.py`, konfiguracja ruff/mypy/pytest, plik pipeline CI.
- **Kryteria akceptacji:** `python -m orch_monitor --version` wypisuje wersję; pipeline uruchamia lint, typy i testy.

| ID | Scenariusz | Oczekiwany wynik |
|---|---|---|
| TC-01.1 | Uruchom `python -m orch_monitor --version` | Kod wyjścia 0, wypisana wersja z `pyproject.toml` |
| TC-01.2 | `ruff check` i `mypy` na czystym repo | Brak błędów |
| TC-01.3 | Import `orch_monitor.services` bez zainstalowanego środowiska graficznego | Import się udaje (warstwy bez Qt) |

### 02. Ustawienia i sekret

- **Cel:** model ustawień zapisywany w pliku TOML w profilu użytkownika oraz sekret w Windows Credential Manager.
- **Zakres:** `config/settings.py` (pydantic): organizacja, tenant, client_id, lista folderów, interwał (domyślnie 30 s), próg długiego joba (domyślnie 2 h), włączone typy powiadomień. `config/secret.py` przez keyring.
- **Kryteria akceptacji:** brak pliku = ustawienia domyślne; niepoprawne wartości odrzucane z czytelnym komunikatem; sekret nigdy nie trafia do pliku TOML.

| ID | Scenariusz | Oczekiwany wynik |
|---|---|---|
| TC-02.1 | Brak pliku ustawień | Zwrócone wartości domyślne: interwał 30 s, próg 2 h |
| TC-02.2 | Zapis i ponowny odczyt ustawień | Odczytane wartości identyczne z zapisanymi |
| TC-02.3 | Interwał = 0 lub ujemny | Błąd walidacji z nazwą pola |
| TC-02.4 | Zapis sekretu (keyring zamockowany) | Sekret w keyring, brak go w pliku TOML |
| TC-02.5 | Uszkodzony plik TOML | Czytelny błąd, aplikacja nie pada; można wrócić do domyślnych |

### 03. Autoryzacja OAuth

- **Cel:** pobieranie i odświeżanie tokenu z Automation Cloud (client credentials).
- **Zakres:** `api/auth.py`: POST na `https://cloud.uipath.com/identity_/connect/token`, cache tokenu w pamięci, odświeżanie 60 s przed wygaśnięciem.
- **Kryteria akceptacji:** jeden token współdzielony przez wszystkie zapytania; błędne dane logowania dają jasny wyjątek `AuthError`.

| ID | Scenariusz | Oczekiwany wynik |
|---|---|---|
| TC-03.1 | Poprawna odpowiedź 200 z tokenem | Zwrócony token, wysłane `grant_type=client_credentials` i zakresy |
| TC-03.2 | Dwa wywołania przed wygaśnięciem | Tylko jedno zapytanie HTTP |
| TC-03.3 | Wywołanie 30 s przed wygaśnięciem (freezegun) | Pobrany nowy token |
| TC-03.4 | Odpowiedź 400/401 | `AuthError` z komunikatem, sekret nie pojawia się w komunikacie |
| TC-03.5 | Timeout połączenia | `AuthError` typu sieciowego, bez zawieszenia |

### 04. Klient OData

- **Cel:** wspólny klient do wszystkich zapytań Orchestratora.
- **Zakres:** `api/client.py`: bazowy URL `https://cloud.uipath.com/{org}/{tenant}/orchestrator_/odata/`, nagłówek `Authorization`, nagłówek `X-UIPATH-OrganizationUnitId` per folder, stronicowanie (`$top`/`$skip`, `@odata.nextLink`), `$count`, ponowienia z wydłużającym się odstępem.
- **Kryteria akceptacji:** 429 i 5xx ponawiane maks. 3 razy z respektowaniem `Retry-After`; 401 wymusza nowy token i jedno ponowienie.

| ID | Scenariusz | Oczekiwany wynik |
|---|---|---|
| TC-04.1 | Zapytanie z folderem 123 | Wysłany nagłówek `X-UIPATH-OrganizationUnitId: 123` i token |
| TC-04.2 | Wynik na 3 stronach | Zwrócona połączona lista wszystkich rekordów |
| TC-04.3 | Odpowiedź 429 z `Retry-After: 2`, potem 200 | Jedno ponowienie po 2 s (czas zamockowany), wynik poprawny |
| TC-04.4 | Cztery razy 503 | Wyjątek `ApiError` po 3 ponowieniach |
| TC-04.5 | 401, potem 200 | Odświeżony token i udane ponowienie |
| TC-04.6 | `count()` na zapytaniu z filtrem | Zwrócona liczba z endpointu `$count`, filtr poprawnie zakodowany w URL |

### 05. Foldery

- **Cel:** lista folderów do wyboru w ustawieniach i mapowanie nazwa → id.
- **Zakres:** `api/folders.py`: `GET /odata/Folders`.
- **Kryteria akceptacji:** zwraca nazwę, pełną ścieżkę i id; folder z ustawień, którego już nie ma, jest zgłaszany, a nie powoduje błędu.

| ID | Scenariusz | Oczekiwany wynik |
|---|---|---|
| TC-05.1 | Odpowiedź z 3 folderami | 3 obiekty z nazwą, ścieżką i id |
| TC-05.2 | Ustawienia wskazują folder, którego nie ma | Folder pominięty, zwrócone ostrzeżenie z jego nazwą |
| TC-05.3 | Pusta lista folderów | Pusta lista, bez wyjątku |

## Etap B: Warstwa danych

### 06. Serwis robotów

- **Cel:** lista robotów ze statusem dla zakładki 1.
- **Zakres:** `services/robots.py`: `GET /odata/Sessions?$expand=Robot` w każdym folderze → `RobotStatus` (nazwa, maszyna, status, folder, ostatni heartbeat, typ) + podsumowanie liczby robotów per status.
- **Kryteria akceptacji:** roboty Disconnected i Unresponsive na początku listy; robot widoczny w kilku folderach występuje raz.

| ID | Scenariusz | Oczekiwany wynik |
|---|---|---|
| TC-06.1 | Fixture z 4 sesjami (Available, Busy, Disconnected, Unresponsive) | 4 obiekty z poprawnie zmapowanymi polami |
| TC-06.2 | Sortowanie | Disconnected i Unresponsive pierwsze, potem Busy, potem Available, w grupie alfabetycznie |
| TC-06.3 | Ten sam robot (to samo `Robot.Id`) w 2 folderach | Jeden wpis, oba foldery w polu folder |
| TC-06.4 | Podsumowanie | Poprawne liczniki per status |
| TC-06.5 | Jeden z 2 folderów zwraca 500 | Dane z drugiego folderu + błąd przypisany do folderu, bez wyjątku |

### 07. Serwis jobów

- **Cel:** joby Running i Pending dla zakładki 2 oraz joby Faulted dla powiadomień.
- **Zakres:** `services/jobs.py`: `running()`, `pending()`, `faulted_since(ts)` na `GET /odata/Jobs` z filtrami `State`; czas trwania i czas oczekiwania liczone z wstrzykniętego zegara.
- **Kryteria akceptacji:** flaga `is_long` gdy czas trwania > próg z ustawień (domyślnie 2 h); Running sortowane od najdłużej działającego.

| ID | Scenariusz | Oczekiwany wynik |
|---|---|---|
| TC-07.1 | Job wystartowany 2 h 1 min temu | `is_long = True` |
| TC-07.2 | Job wystartowany 1 h 59 min temu | `is_long = False` |
| TC-07.3 | Zmiana progu w ustawieniach na 30 min | Job 45 min ma `is_long = True` |
| TC-07.4 | `pending()` | Filtr `State eq 'Pending'`, czas oczekiwania od `CreationTime` |
| TC-07.5 | `faulted_since(12:00:00Z)` | Filtr `State eq 'Faulted' and EndTime gt 2026-11-26T12:00:00Z` |
| TC-07.6 | Czasy z API w UTC | Wynik w Europe/Warsaw |

### 08. Serwis kolejek – dziś

- **Cel:** wiersz zakładki 3 dla każdej kolejki.
- **Zakres:** `services/queues.py`: lista `QueueDefinitions` per folder; dla dziś i wczoraj zapytania `QueueItems/$count` z filtrami statusu, typu wyjątku i okna `EndProcessing`; % sukcesu i zmiana w punktach procentowych.
- **Kryteria akceptacji:** doba liczona od 00:00 Europe/Warsaw, przeliczona na UTC; elementy `Retried` nie są liczone (liczy się tylko ostateczny wynik); kolejki bez ruchu mają zera i % = brak.

| ID | Scenariusz | Oczekiwany wynik |
|---|---|---|
| TC-08.1 | 26.11, 10:00 czasu PL | Okno dziś: od 2026-11-25T23:00:00Z |
| TC-08.2 | Dzień zmiany czasu (29.03.2026) | Okno od 2026-03-28T23:00:00Z, doba ma 23 h |
| TC-08.3 | 8 sukcesów, 1 AE, 1 BE | % sukcesu = 80 |
| TC-08.4 | Dziś 80%, wczoraj 75% | Zmiana = +5 pp |
| TC-08.5 | Kolejka bez elementów dziś | Wiersz z zerami, % = `None`, zmiana = `None` |
| TC-08.6 | Filtry zapytań | AE: `Status eq 'Failed' and ProcessingExceptionType eq 'ApplicationException'`; BE analogicznie; żaden filtr nie obejmuje `Retried` |
| TC-08.7 | Element zakończony 25.11 o 23:59 czasu PL | Nie liczony do dziś, liczony do wczoraj |

### 09. Szczegóły kolejki

- **Cel:** lista dzisiejszych elementów z AE/BE po kliknięciu w kolejkę.
- **Zakres:** `services/queue_details.py`: `GET /odata/QueueItems` ze `Status eq 'Failed'`, oknem dziś i `$select` (referencja, typ wyjątku, `ProcessingException.Reason`, `EndProcessing`, robot); maks. 500 pozycji.
- **Kryteria akceptacji:** sortowanie od najnowszych; filtr AE / BE / oba.

| ID | Scenariusz | Oczekiwany wynik |
|---|---|---|
| TC-09.1 | 3 AE i 2 BE | 5 pozycji z typem i treścią błędu, od najnowszej |
| TC-09.2 | Filtr tylko AE | 3 pozycje |
| TC-09.3 | Więcej niż 500 elementów | Zwrócone 500 + flaga `truncated = True` |
| TC-09.4 | Brak `ProcessingException.Reason` | Pole puste, bez wyjątku |

### 10. Harmonogram odświeżania i snapshot

- **Cel:** cykliczne pobieranie wszystkiego w tle i jeden spójny stan danych dla UI i powiadomień.
- **Zakres:** `refresh/scheduler.py`: obiekt `Snapshot` (roboty, joby Running/Pending, kolejki, czas pobrania, błędy per źródło); odświeżanie co interwał z ustawień w osobnym wątku; subskrypcja zmian (callback).
- **Kryteria akceptacji:** nieudane pobranie zachowuje ostatni dobry snapshot z flagą `stale`; kolejne odświeżenie nie startuje, zanim skończy się poprzednie.

| ID | Scenariusz | Oczekiwany wynik |
|---|---|---|
| TC-10.1 | Udane odświeżenie | Subskrybent dostaje nowy snapshot z czasem pobrania |
| TC-10.2 | Drugie odświeżenie kończy się błędem sieci | Ostatni dobry snapshot, `stale = True`, błąd zapisany |
| TC-10.3 | Odświeżenie trwa dłużej niż interwał | Brak równoległego drugiego odświeżenia |
| TC-10.4 | Zmiana interwału w ustawieniach na 60 s | Kolejne odświeżenie po 60 s |
| TC-10.5 | Zatrzymanie harmonogramu | Wątek kończy się w ciągu 2 s |

## Etap C: Interfejs

Testy UI uruchamiane przez pytest-qt z `QT_QPA_PLATFORM=offscreen`, więc działają w pipeline bez ekranu. Widoki dostają gotowy `Snapshot` (fixture), nie wołają API.

### 11. Okno główne i ikona w zasobniku

- **Cel:** okno z trzema pustymi zakładkami, pasek stanu i ikona w zasobniku.
- **Zakres:** `ui/main_window.py`, `ui/tray.py`; zamknięcie okna chowa je do zasobnika, „Zakończ” w menu ikony zamyka aplikację.
- **Kryteria akceptacji:** pasek stanu pokazuje „Ostatnia aktualizacja: HH:MM:SS” i ostrzeżenie przy `stale`.

| ID | Scenariusz | Oczekiwany wynik |
|---|---|---|
| TC-11.1 | Start okna | 3 zakładki w kolejności: Roboty, Działające, Kolejki |
| TC-11.2 | Snapshot z czasem 12:00:05 | Pasek stanu: „Ostatnia aktualizacja: 12:00:05” |
| TC-11.3 | Snapshot z `stale = True` | Widoczne ostrzeżenie o braku połączenia, dane nadal w tabelach |
| TC-11.4 | Zamknięcie okna krzyżykiem | Okno ukryte, aplikacja działa |
| TC-11.5 | „Zakończ” w menu ikony | Harmonogram zatrzymany, aplikacja zamknięta |

### 12. Zakładka 1: statusy robotów

- **Cel:** tabela robotów z kolorami, licznikami i filtrami.
- **Zakres:** `ui/tab_robots.py`: model tabeli Qt na `RobotStatus`, liczniki per status, filtr folderu i statusu, wyszukiwanie po nazwie.
- **Kryteria akceptacji:** kolory: zielony Available, niebieski Busy, czerwony Disconnected/Unresponsive; odświeżenie zachowuje filtr i zaznaczenie.

| ID | Scenariusz | Oczekiwany wynik |
|---|---|---|
| TC-12.1 | Snapshot z 5 robotami | 5 wierszy, kolumny: Robot, Maszyna, Status, Folder, Ostatni heartbeat, Typ |
| TC-12.2 | Robot Disconnected | Wiersz na górze, kolor czerwony |
| TC-12.3 | Wpisanie „BOT0” w wyszukiwarce | Tylko roboty z „BOT0” w nazwie |
| TC-12.4 | Filtr „Busy”, potem nowy snapshot | Filtr nadal aktywny |
| TC-12.5 | Liczniki | Np. „3 Available · 1 Busy · 1 Disconnected” |

### 13. Zakładka 2: działające i oczekujące

- **Cel:** tabela jobów Running oraz osobna tabela Pending.
- **Zakres:** `ui/tab_jobs.py`: kolumny Robot, Proces, Maszyna, Start, Czas trwania, Źródło, Folder; sekcja Pending: Proces, Dodany, Czas oczekiwania, Folder.
- **Kryteria akceptacji:** czas trwania odświeżany co sekundę bez zapytania do API; joby powyżej progu wyróżnione.

| ID | Scenariusz | Oczekiwany wynik |
|---|---|---|
| TC-13.1 | 2 Running, 1 Pending | 2 wiersze w górnej tabeli, 1 w sekcji Pending, liczniki „2 działa · 1 czeka” |
| TC-13.2 | Job z `is_long = True` | Wiersz wyróżniony (kolor ostrzegawczy) |
| TC-13.3 | Upływ 1 s (zegar zamockowany) | Kolumna Czas trwania zwiększona o 1 s |
| TC-13.4 | Brak jobów | Komunikat „Nic teraz nie działa” zamiast pustej tabeli |

### 14. Zakładka 3: kolejki, szczegóły, CSV

- **Cel:** tabela kolejek z dzisiejszymi wynikami, okno szczegółów i eksport.
- **Zakres:** `ui/tab_queues.py`, `ui/queue_details_dialog.py`, `reports/csv_export.py` (wspólny z raportami).
- **Kryteria akceptacji:** znaczniki AE/BE (czerwony gdy > 0, szary gdy 0); % sukcesu „–” dla kolejek bez ruchu; zmiana względem wczoraj ze strzałką; CSV w UTF-8 z BOM i separatorem `;` (otwiera się poprawnie w polskim Excelu).

| ID | Scenariusz | Oczekiwany wynik |
|---|---|---|
| TC-14.1 | Kolejka z AE = 3 | Znacznik „AE: 3” czerwony |
| TC-14.2 | Kolejka bez ruchu | Zera, % = „–”, brak strzałki |
| TC-14.3 | Zmiana +5 pp | „▲ 5 pp” |
| TC-14.4 | Dwuklik na wierszu (serwis szczegółów zamockowany) | Otwiera się okno z listą elementów AE/BE tej kolejki |
| TC-14.5 | Eksport CSV do pliku tymczasowego | Plik `kolejki_2026-11-26.csv`, nagłówek + 1 wiersz na kolejkę, kodowanie UTF-8 z BOM, separator `;` |
| TC-14.6 | Nazwa kolejki z „;” i polskimi znakami | Wartość poprawnie w cudzysłowie, znaki zachowane |

### 15. Okno ustawień

- **Cel:** edycja wszystkich ustawień bez ręcznej edycji pliku.
- **Zakres:** `ui/settings_dialog.py`: dane połączenia (organizacja, tenant, client_id, sekret), wybór folderów z listy z API, interwał, próg długiego joba, typy powiadomień; przycisk „Testuj połączenie”.
- **Kryteria akceptacji:** zapis od razu działa (nowy interwał, nowe foldery) bez restartu; sekret pole maskowane.

| ID | Scenariusz | Oczekiwany wynik |
|---|---|---|
| TC-15.1 | Otwarcie przy istniejących ustawieniach | Pola wypełnione aktualnymi wartościami, sekret zamaskowany |
| TC-15.2 | „Testuj połączenie”, auth zamockowany na sukces | Komunikat „Połączono” i lista folderów załadowana |
| TC-15.3 | „Testuj połączenie”, auth zwraca 401 | Komunikat o błędnych danych, bez treści sekretu |
| TC-15.4 | Zmiana interwału na 60 s i zapis | Harmonogram dostaje nowy interwał |
| TC-15.5 | Interwał = 0 | Przycisk Zapisz nieaktywny, komunikat przy polu |

## Etap D: Powiadomienia

### 16. Silnik powiadomień

- **Cel:** wykrywanie zdarzeń przez porównanie poprzedniego i nowego snapshotu, bez zależności od Qt.
- **Zakres:** `notify/engine.py`: `diff(prev, curr) -> list[Notification]`. Zdarzenia: robot przeszedł w Disconnected/Unresponsive, nowe AE w kolejce, nowe BE w kolejce, nowe joby Faulted. Grupowanie per kolejka i per robot. Typy włączane w ustawieniach (domyślnie: robot, AE, Faulted włączone; BE wyłączone). Wyciszenie do podanej godziny.
- **Kryteria akceptacji:** pierwszy snapshot po starcie nie daje powiadomień; to samo zdarzenie nie jest zgłaszane dwa razy; o północy (nowa doba, liczniki od zera) nie ma fałszywych alarmów.

| ID | Scenariusz | Oczekiwany wynik |
|---|---|---|
| TC-16.1 | `prev = None` (start aplikacji), w danych są AE | Brak powiadomień |
| TC-16.2 | AE w kolejce X: 2 → 5 | Jedno powiadomienie „X: 3 nowe AE” |
| TC-16.3 | AE bez zmian (5 → 5) | Brak powiadomień |
| TC-16.4 | BE: 0 → 1, BE wyłączone w ustawieniach | Brak powiadomień |
| TC-16.5 | BE: 0 → 1, BE włączone | „X: 1 nowe BE” |
| TC-16.6 | Robot Available → Disconnected | „Robot BOT01 rozłączony” |
| TC-16.7 | Robot Disconnected w dwóch kolejnych snapshotach | Tylko jedno powiadomienie |
| TC-16.8 | Nowy job Faulted | „Proces Raport_dzienny: Faulted” |
| TC-16.9 | Przejście przez północ: AE 5 → 0 | Brak powiadomień |
| TC-16.10 | Wyciszenie do 14:00, zdarzenie o 13:30 | Brak powiadomienia; po 14:00 nowe zdarzenia znowu zgłaszane, stare nie |
| TC-16.11 | Zmiany w 3 kolejkach naraz | 3 osobne powiadomienia (po jednym na kolejkę) |

### 17. Wyświetlanie i wyciszenie powiadomień

- **Cel:** pokazanie powiadomień Windows i menu wyciszenia.
- **Zakres:** `ui/notifier.py`: `QSystemTrayIcon.showMessage`; kliknięcie otwiera okno na właściwej zakładce. Menu ikony: „Wycisz na 30 min / 1 h / 4 h / do końca dnia” oraz „Włącz powiadomienia”.
- **Kryteria akceptacji:** ikona zmienia się przy aktywnym wyciszeniu; wyciszenie nie przetrwa restartu aplikacji (założenie).

| ID | Scenariusz | Oczekiwany wynik |
|---|---|---|
| TC-17.1 | Powiadomienie typu AE (tray zamockowany) | `showMessage` wywołane z tytułem i treścią |
| TC-17.2 | Kliknięcie w powiadomienie AE | Okno widoczne, aktywna zakładka Kolejki |
| TC-17.3 | Kliknięcie w powiadomienie o robocie | Aktywna zakładka Roboty |
| TC-17.4 | „Wycisz na 1 h” o 10:00 | Silnik dostaje wyciszenie do 11:00, ikona w stanie wyciszonym |
| TC-17.5 | „Do końca dnia” o 15:20 | Wyciszenie do 23:59:59 czasu PL |
| TC-17.6 | „Włącz powiadomienia” | Wyciszenie usunięte, zwykła ikona |

## Etap E: Raporty

### 18. Raporty: agregacja

- **Cel:** dane raportu za dowolny okres, pobierane z API Orchestratora (bez lokalnej bazy).
- **Zakres:** `reports/builder.py`: `build_report(start, end, folders) -> Report`. Okresy: dzień, tydzień (pon–niedz), miesiąc, własny zakres. Sekcje: podsumowanie z werdyktem, procesy (uruchomienia, Successful, Faulted, Stopped, średni czas), kolejki (sukcesy, AE, BE, %), dni (werdykt per dzień), błędy (Faulted i AE z treścią).
- **Kryteria akceptacji:** werdykt „Bez błędów” gdy 0 Faulted i 0 AE; BE nie zmienia werdyktu; kolejki liczone przez `$count`, joby pobierane stronami z `$select`.

| ID | Scenariusz | Oczekiwany wynik |
|---|---|---|
| TC-18.1 | Okres „tydzień” dla 26.11.2026 | Od pon. 23.11 00:00 do niedz. 29.11 23:59:59 czasu PL |
| TC-18.2 | Okres „miesiąc” dla 26.11.2026 | 01.11–30.11, 30 wierszy w sekcji Dni |
| TC-18.3 | 0 Faulted, 0 AE, 4 BE | Werdykt „Bez błędów”, BE = 4 widoczne w podsumowaniu |
| TC-18.4 | 1 Faulted we wtorek | Werdykt okresu „Z błędami”, w sekcji Dni tylko wtorek z błędem |
| TC-18.5 | Proces z 3 uruchomieniami (10, 20, 30 min) | Średni czas 20 min |
| TC-18.6 | Job Faulted z komunikatem w `Info` | Pozycja w sekcji Błędy z procesem, godziną i treścią |
| TC-18.7 | Okres z miesiącem, w którym jest zmiana czasu (marzec) | Każdy dzień liczony od 00:00 czasu PL, brak dziury ani nakładania |
| TC-18.8 | Pusty okres (brak danych) | Raport z zerami i werdyktem „Bez błędów”, bez wyjątku |

### 19. Raporty: eksport CSV i Excel

- **Cel:** zapis raportu do pliku.
- **Zakres:** `reports/csv_export.py` (ten sam co w kroku 14), `reports/xlsx_export.py` (openpyxl): arkusze Podsumowanie, Procesy, Kolejki, Dni, Błędy.
- **Kryteria akceptacji:** CSV: osobny plik na sekcję albo jeden plik z sekcją Kolejki (założenie: jeden plik ZIP z 5 plikami CSV); Excel: nagłówki pogrubione, daty jako daty, procenty jako procenty, werdykt kolorowany.

| ID | Scenariusz | Oczekiwany wynik |
|---|---|---|
| TC-19.1 | Eksport Excel raportu z fixture | Plik z 5 arkuszami o nazwach jak wyżej |
| TC-19.2 | Odczyt pliku Excel przez openpyxl | Komórki dat mają typ daty, % sukcesu format procentowy |
| TC-19.3 | Werdykt „Z błędami” | Komórka werdyktu z czerwonym wypełnieniem |
| TC-19.4 | Eksport CSV | 5 plików CSV, UTF-8 z BOM, separator `;` |
| TC-19.5 | Nazwa pliku | `raport_2026-11-23_2026-11-29.xlsx` dla tygodnia |

### 20. Raporty: okno raportu

- **Cel:** wybór okresu, podgląd i zapis raportu z aplikacji.
- **Zakres:** `ui/report_dialog.py`: wybór Dzień / Tydzień / Miesiąc / Zakres, kalendarz, foldery (domyślnie z ustawień), przycisk Generuj, podgląd sekcji w zakładkach, przyciski „Zapisz CSV” i „Zapisz Excel”. Generowanie w tle z paskiem postępu.
- **Kryteria akceptacji:** okno nie blokuje się podczas generowania; można anulować.

| ID | Scenariusz | Oczekiwany wynik |
|---|---|---|
| TC-20.1 | Wybór „Tydzień” i daty 26.11 | Pokazany zakres 23.11–29.11 |
| TC-20.2 | Generuj (builder zamockowany) | Podgląd z werdyktem i sekcjami |
| TC-20.3 | Generowanie trwa 5 s | Pasek postępu widoczny, okno reaguje |
| TC-20.4 | Anuluj w trakcie | Generowanie przerwane, brak błędu |
| TC-20.5 | Zakres z datą „do” wcześniejszą niż „od” | Przycisk Generuj nieaktywny, komunikat |
| TC-20.6 | Błąd API podczas generowania | Czytelny komunikat, można spróbować ponownie |

## Etap F: Logi, pakowanie i test na tenancie

### 21. Logi do pliku

- **Cel:** diagnostyka błędów u użytkownika.
- **Zakres:** `logging_setup.py`: plik w `%LOCALAPPDATA%\OrchMonitor\logs`, rotacja 5 × 1 MB; logowane wywołania API (metoda, ścieżka, status, czas odpowiedzi) i błędy.
- **Kryteria akceptacji:** w logach nigdy nie ma tokenu ani sekretu; menu „Otwórz folder logów”.

| ID | Scenariusz | Oczekiwany wynik |
|---|---|---|
| TC-21.1 | Udane zapytanie API | Wpis z metodą, ścieżką, statusem 200 i czasem w ms |
| TC-21.2 | Zapytanie z nagłówkiem `Authorization` | Token nie występuje w żadnym wpisie |
| TC-21.3 | Błąd autoryzacji | Wpis ERROR bez wartości sekretu |
| TC-21.4 | Przekroczenie 1 MB | Nowy plik, maks. 5 plików |

### 22. Pakowanie .exe i test na tenancie

- **Cel:** jeden plik `OrchMonitor.exe` gotowy do przekazania developerom oraz potwierdzenie działania na prawdziwym Orchestratorze.
- **Zakres:** spec PyInstaller (jeden plik, ikona, bez konsoli); job w pipeline budowany na runnerze Windows; smoke test uruchomionego .exe; ręczna lista kontrolna na tenancie testowym.
- **Kryteria akceptacji:** .exe startuje na czystym Windows bez zainstalowanego Pythona; wszystkie testy automatyczne zielone; lista kontrolna przeszła.

| ID | Scenariusz | Oczekiwany wynik |
|---|---|---|
| TC-22.1 | Build PyInstaller w pipeline (Windows) | Artefakt `OrchMonitor.exe` |
| TC-22.2 | `OrchMonitor.exe --version` | Kod wyjścia 0, poprawna wersja |
| TC-22.3 | `OrchMonitor.exe --self-test` (sprawdza importy Qt, keyring, openpyxl) | Kod wyjścia 0 |
| TC-22.4 | Ręcznie: połączenie z tenantem testowym | Zakładki 1–3 pokazują dane zgodne z Orchestratorem |
| TC-22.5 | Ręcznie: robot testowy wymuszony do AE | Powiadomienie w ciągu ok. 30 s, licznik AE wzrósł |
| TC-22.6 | Ręcznie: raport za ostatni tydzień, zapis do Excela | Liczby zgodne z widokiem w Orchestratorze |

Testy TC-22.4–22.6 wymagają prawdziwego tenanta i nie uruchamiają się w zwykłym pipeline; oznaczone markerem `@pytest.mark.live` albo jako lista ręczna.

## Założenia i otwarte punkty

- Założenie: Python 3.12 i Windows 10/11 na komputerach developerów.
- Założenie: pipeline ma runner Windows (potrzebny do kroku 22); kroki 01–21 mogą działać na Linuksie.
- Założenie: jest tenant lub folder testowy w Orchestratorze do testów ręcznych z kroku 22.
- Założenie: eksport CSV raportu to jeden plik ZIP z 5 plikami CSV (po jednym na sekcję).
- Założenie: wyciszenie powiadomień nie przetrwa restartu aplikacji.
- Założenie: retencja danych w Orchestratorze obejmuje co najmniej miesiąc (raporty miesięczne).
- Nazwy endpointów i pól (np. `ProcessingExceptionType`, `ReportingTime`) warto potwierdzić na Swaggerze Waszego tenanta (`/orchestrator_/swagger`) przed krokiem 06; fixture w testach powinny być zrzutami prawdziwych odpowiedzi.

