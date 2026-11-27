# Orchestrator Monitor – specyfikacja funkcjonalna i techniczna (v1.2)

·

## 1. Cel i zakres

Aplikacja to tylko do odczytu panel monitoringu: pobiera dane z Orchestratora i pokazuje w trzech zakładkach stan robotów oraz dzisiejsze przetwarzanie kolejek. Nie uruchamia, nie zatrzymuje ani nie zmienia niczego w Orchestratorze.

**W zakresie (v1)**

- Zakładka 1: statusy wszystkich robotów na żywo.
- Zakładka 2: roboty, które w tej chwili wykonują proces, oraz joby czekające na robota (Pending).
- Zakładka 3: wszystkie kolejki z dzisiejszymi sukcesami, AE i BE, procentem sukcesu i porównaniem z wczoraj; podgląd elementów z błędami i eksport do CSV.
- Powiadomienia na pulpicie o problemach, z możliwością czasowego wyciszenia (sekcja 6).
- Raporty za wybrany dzień, tydzień lub miesiąc: co działało i czy bez błędów (sekcja 7).

**Poza zakresem (v1)**

- Sterowanie robotami i jobami (start, stop, kill).
- Alerty mailem lub w Teams (w v1 tylko powiadomienia na pulpicie).

**Założenia (do potwierdzenia)**

- Potwierdzone: **źródłem danych jest UiPath Orchestrator w Automation Cloud, wersja 24 (2024.x)**, a aplikacja desktopowa pobiera dane przez jego REST/OData API co ok. 30 s.
- Potwierdzone: „AP/BE” to wyjątki: **Application Exception (AE)** i **Business Exception (BE)**, czyli dwa typy błędów elementu kolejki w UiPath. W dalszej części dokumentu używam skrótów AE/BE.
- Założenie: „dzisiaj” to doba kalendarzowa od 00:00 w strefie czasowej użytkowników (Europe/Warsaw).

## 2. Użytkownicy i scenariusze

**P****otwierdz****one:** z panelu korzystają developerzy RPA. Pozostałe role w tabeli to propozycje na później.

| Kto | Po co otwiera panel | Zakładka |
|---|---|---|
| Wsparcie RPA (dyżur) | Szybko zobaczyć, czy któryś robot jest rozłączony lub nie odpowiada | 1 |
| Wsparcie RPA / developer | Sprawdzić, co się teraz wykonuje i od jak dawna | 2 |
| Wsparcie RPA / właściciel procesu | Ocenić dzisiejsze przetwarzanie: ile sukcesów, czy były AE/BE | 3 |
| Kierownik / biznes (opcjonalnie) | Rzut oka na stan dnia bez logowania do Orchestratora | 3 |

## 3. Zakładka 1: Statusy robotów (na żywo)

Tabela wszystkich robotów z bieżącym stanem, odświeżana automatycznie. Roboty w stanie problemowym (Disconnected, Unresponsive) są na górze i wyróżnione kolorem.

**Kolumny**

| Kolumna | Opis | Źródło (UiPath, założenie) |
|---|---|---|
| Robot | Nazwa robota | `Sessions` → `Robot.Name` |
| Maszyna | Nazwa maszyny / hosta | `Sessions` → `HostMachineName` |
| Status | Available, Busy, Disconnected, Unresponsive | `Sessions` → `State` |
| Folder | Folder Orchestratora | nagłówek `X-UIPATH-OrganizationUnitId` / `Folders` |
| Ostatni heartbeat | Kiedy robot ostatnio się zgłosił | `Sessions` → `ReportingTime` |
| Typ | Attended / Unattended | `Robot.Type` |

**Zachowanie**

- Licznik na górze: ile robotów w każdym statusie (np. 12 Available, 3 Busy, 1 Disconnected).
- Kolory: zielony Available, niebieski Busy, czerwony Disconnected i Unresponsive.
- Filtr po folderze i statusie, wyszukiwanie po nazwie.
- Widoczny znacznik „ostatnia aktualizacja: HH:MM:SS”. Jeśli pobranie danych się nie uda, panel pokazuje ostatnie dane z ostrzeżeniem, a nie pusty ekran.

## 4. Zakładka 2: Działające roboty

Lista jobów w stanie Running, czyli robotów, które w tej chwili wykonują proces. Domyślnie sortowana od najdłużej działającego.

**Kolumny**

| Kolumna | Opis | Źródło (UiPath, założenie) |
|---|---|---|
| Robot | Robot wykonujący job | `Jobs` → `Robot.Name` |
| Proces | Nazwa procesu | `Jobs` → `ReleaseName` |
| Maszyna | Host | `Jobs` → `HostMachineName` |
| Start | Godzina rozpoczęcia | `Jobs` → `StartTime` |
| Czas trwania | Liczony na bieżąco od startu | wyliczany w aplikacji |
| Źródło uruchomienia | Manual, Trigger (harmonogram), kolejka | `Jobs` → `Source` |
| Folder | Folder Orchestratora | kontekst zapytania |

Zapytanie: `GET /odata/Jobs?$filter=State eq 'Running'&$expand=Robot`.

**Zachowanie**

- Licznik: ile jobów działa teraz i ile czeka.
- Wyróżnienie jobu, który działa dłużej niż 2 godziny (próg zmieniany w ustawieniach).
- Osobna sekcja **Oczekujące (Pending)**: joby czekające na wolnego robota, z procesem, czasem dodania i czasem oczekiwania. Zapytanie: `GET /odata/Jobs?$filter=State eq 'Pending'`.
- Osobna sekcja **Dziś zakończone błędem (Faulted)**: proces, robot, godzina końca, informacja o błędzie, folder i liczba notatek. Lista pobierana raz od północy, potem dopisywana z tego samego zapytania co powiadomienia (bez dodatkowych zapytań co 30 s).

**Notatki do błędów (wspólne dla zespołu)**

- Dwuklik na jobie Faulted (zakładka 2) albo na elemencie AE/BE w szczegółach kolejki (zakładka 3) otwiera okno notatek: lista notatek (autor = login Windows, data, tekst), dopisanie nowej, usunięcie własnej, „Odśwież”.
- Notatki leżą we wspólnym folderze sieciowym zespołu (ustawienie „Folder notatek zespołu”), w podfolderze tenanta i błędu; każda notatka to osobny plik JSON, więc jednoczesne pisanie nie nadpisuje cudzych notatek. Pusty folder = notatki lokalne.
- Notatki nie są zapisywane w Orchestratorze; aplikacja dalej tylko czyta z Orchestratora.

## 5. Zakładka 3: Dzisiejsze kolejki

Jeden wiersz na każdą kolejkę w monitorowanych folderach, także gdy dziś nic nie przetworzyła (wtedy same zera; potwierdzone). Dla każdej kolejki: liczba sukcesów oraz czy (i ile) było AE i BE.

**Kolumny**

| Kolumna | Opis | Jak liczone (UiPath) |
|---|---|---|
| Kolejka | Nazwa kolejki | `QueueDefinitions` → `Name` |
| Folder | Folder Orchestratora | kontekst zapytania |
| Sukcesy | Elementy zakończone sukcesem dziś | `Status eq 'Successful'` |
| AE | Czy były Application Exceptions + liczba | `Status eq 'Failed'` i `ProcessingExceptionType eq 'ApplicationException'` |
| BE | Czy były Business Exceptions + liczba | `Status eq 'Failed'` i `ProcessingExceptionType eq 'BusinessException'` |
| % sukcesu | Sukcesy / (sukcesy + AE + BE) | wyliczany w aplikacji |
| vs wczoraj | Zmiana % sukcesu względem wczoraj, np. „▲ 3 pp” | te same zapytania dla wczorajszej doby |
| W toku / Nowe | Ile jeszcze czeka lub jest przetwarzanych | `Status eq 'InProgress'` / `'New'` |
| Ostatnie przetworzenie | Godzina ostatniego zakończonego elementu | max `EndProcessing` |

**Definicja „dzisiaj”**

Potwierdzone: aplikacja pobiera elementy kolejek, a element trafia do zakładki w chwili zakończenia przetwarzania (np. z AE), przy najbliższym odświeżeniu. Liczy się do dzisiejszego dnia, jeśli jego `EndProcessing` jest od 00:00 czasu Europe/Warsaw (API zwraca czas w UTC, więc aplikacja przelicza granicę doby). Nie liczymy po dacie dodania do kolejki (`CreationTime`); to zmieniałoby wynik dla elementów dodanych wczoraj, a przetworzonych dziś.

**Zachowanie**

- AE i BE pokazane jako znacznik tak/nie z liczbą, np. „AE: 3” na czerwono, „BE: 0” szaro.
- Elementy ponawiane (Retried): liczymy tylko ostateczny wynik, żeby jeden element nie był policzony jako AE i jako sukces. Potwierdzone.
- Kolejka bez elementów dziś: % sukcesu pokazany jako „–”, bez porównania.
- **Szczegóły kolejki:** kliknięcie w wiersz otwiera listę dzisiejszych elementów z AE/BE: referencja, typ wyjątku, treść błędu (`ProcessingException.Reason`), godzina, robot.
- **Eksport CSV:** przycisk zapisuje bieżącą tabelę (wszystkie kolumny) do pliku CSV z datą w nazwie.

Alternatywa techniczna: UiPath ma gotowy endpoint ze statystykami kolejek (`QueueProcessingRecords/UiPathODataSvc.RetrieveQueuesProcessingStatus`), ale on podaje stan ogólny, nie „tylko dziś”. Dlatego dla dzisiejszych liczb proponuję zliczanie `QueueItems` z filtrem dat i `$count`.

## 6. Powiadomienia na pulpicie

**Potwierdzone:** aplikacja wysyła powiadomienia. Poniżej ustawienia domyślne; każdy typ można zmienić w aplikacji.

| Zdarzenie | Treść przykładowa | Domyślnie |
|---|---|---|
| Robot przechodzi w Disconnected lub Unresponsive | „Robot BOT01 rozłączony” | włączone |
| Nowe AE w kolejce od ostatniego odświeżenia | „Faktury_IN: 3 nowe AE” | włączone |
| Nowe BE w kolejce | „Faktury_IN: 1 nowe BE” | wyłączone (BE to często oczekiwany wynik) |
| Job zakończony błędem (Faulted) | „Proces Raport_dzienny: Faulted” | włączone (potwierdzone) |

- Powiadomienie systemowe Windows z ikony w zasobniku; kliknięcie otwiera aplikację na właściwej zakładce.
- Zdarzenia z jednego odświeżenia są grupowane per kolejka lub robot, żeby nie zasypać użytkownika.
- Po uruchomieniu aplikacji pierwsze pobranie danych nie generuje powiadomień; liczy się dopiero zmiana.
- Każdy typ powiadomienia można włączyć lub wyłączyć w ustawieniach.
- **Wyciszenie:** z menu ikony w zasobniku można wyciszyć wszystkie powiadomienia na 30 min, 1 h, 4 h albo do końca dnia (np. na czas planowanej przerwy). Ikona pokazuje, że wyciszenie jest aktywne. Zdarzenia z tego czasu nie są wysyłane później, ale widać je w zakładkach.
- Joby Faulted wykrywane zapytaniem `GET /odata/Jobs?$filter=State eq 'Faulted' and EndTime gt {czas poprzedniego odświeżenia}`, w każdym monitorowanym folderze.

## 7. Raporty za dzień, tydzień lub miesiąc

Użytkownik wybiera okres (dzień, tydzień, miesiąc albo własny zakres dat) i foldery, a aplikacja generuje raport: co działało w tym okresie i czy działało bez błędów. Raport generowany jest na żądanie, z osobnego okna lub zakładki „Raporty”.

**Zawartość raportu**

| Część | Co pokazuje | Źródło (UiPath) |
|---|---|---|
| Podsumowanie | Werdykt „Bez błędów” / „Z błędami” dla całego okresu, liczba jobów, liczba elementów kolejek, łącznie AE, BE i Faulted | wyliczane z poniższych |
| Procesy | Per proces: liczba uruchomień, Successful, Faulted, Stopped, średni czas trwania | `Jobs` z filtrem `EndTime` w okresie |
| Kolejki | Per kolejka: sukcesy, AE, BE, % sukcesu | `QueueItems/$count` z filtrem `EndProcessing` w okresie |
| Dni | Dla tygodnia i miesiąca: jeden wiersz na dzień z werdyktem, żeby od razu widać było, które dni miały problemy | jak wyżej, per dzień |
| Błędy | Lista jobów Faulted i elementów z AE z treścią błędu | `Jobs.Info`, `ProcessingException.Reason` |

**Definicja „bez błędów”** (potwierdzone): w okresie nie było żadnego joba Faulted ani elementu z AE. BE nie jest błędem, tylko wyjątkiem, w którym element celowo nie jest przetwarzany; raport pokazuje BE osobno, ale nie psują one werdyktu.

**Format** (potwierdzone): podgląd w aplikacji oraz zapis do CSV i do Excela (.xlsx, biblioteka openpyxl). Bez PDF.

**Historia danych** (potwierdzone): Orchestrator trzyma historię, więc raporty pobierają dane bezpośrednio z API, bez lokalnej bazy. Założenie: retencja obejmuje co najmniej ostatni miesiąc.

**Wydajność:** dla kolejek aplikacja używa zapytań `$count`, a nie pobiera wszystkich elementów; joby pobiera stronami po 1000 z ograniczonym zestawem pól (`$select`).

## 8. Architektura i integracja

**P****otwierdzone:** to aplikacja na pulpit. Sama odpytuje API Orchestratora co ok. 30 s, bez osobnego serwera, a sekret i listę folderów trzyma w lokalnej konfiguracji. Przy kilku developerach to kilka niezależnych źródeł zapytań, co jest w porządku; gdyby użytkowników było dużo więcej, warto wrócić do wspólnego backendu z cache.

**Uwierzytelnienie (zależy od wersji Orchestratora)**

- Orchestrator działa w **Automation Cloud** (potwierdzone), więc aplikacja korzysta z aplikacji zewnętrznej (External Application) typu confidential, z przepływem OAuth client credentials.
- Token pobierany z `https://cloud.uipath.com/identity_/connect/token`, zapytania idą na `https://cloud.uipath.com/{organizacja}/{tenant}/orchestrator_/odata/...`.
- Zakresy tylko do odczytu, np. `OR.Robots.Read`, `OR.Jobs.Read`, `OR.Queues.Read`, `OR.Folders.Read`. Aplikację zakłada administrator organizacji w Admin → External Applications.

**Zapytania (UiPath, założenie)**

| Zakładka | Endpoint | Odświeżanie |
|---|---|---|
| 1. Statusy robotów | `GET /odata/Sessions?$expand=Robot` | co 30 s |
| 2. Działające roboty | `GET /odata/Jobs?$filter=State eq 'Running'` | co 30 s |
| 3. Dzisiejsze kolejki | `GET /odata/QueueDefinitions` + `GET /odata/QueueItems/$count` z filtrami statusu, typu wyjątku i daty | co 30 s |

Interwał 30 s to wartość domyślna, zmieniana w ustawieniach.

**Foldery**

**Potwierdzone:** lista monitorowanych folderów to ustawienie aplikacji. W UiPath każde zapytanie dotyczy jednego folderu (nagłówek `X-UIPATH-OrganizationUnitId`), więc aplikacja odpytuje każdy wybrany folder osobno i łączy wyniki. Lista do wyboru pochodzi z `GET /odata/F``older``s`.

**Technologia**

**Potwierdzone:** Python. Wybrany stos:

| Element | Propozycja | Dlaczego |
|---|---|---|
| Interfejs | PySide6 (Qt) | Natywne okno z zakładkami i tabelami, ikona w zasobniku i powiadomienia w jednej bibliotece |
| Zapytania do API | httpx | Prosty klient HTTP z obsługą timeoutów i ponowień |
| Sekret | keyring | Zapisuje sekret w Windows Credential Manager |
| Ustawienia | plik TOML lub JSON w profilu użytkownika | Foldery, interwał, typy powiadomień |
| Dystrybucja | PyInstaller (jeden plik .exe) | Developerzy nie muszą instalować Pythona |

Potwierdzone: komputery z Windows.

## 9. Wymagania niefunkcjonalne

| Obszar | Wymaganie (propozycja) |
|---|---|
| Aktualność danych | Dane we wszystkich zakładkach opóźnione maks. ok. 30 s (interwał w ustawieniach) |
| Obciążenie Orchestratora | Każda kopia aplikacji odpytuje API sama, więc liczba zapytań rośnie z liczbą użytkowników; respektowanie limitów API (odpowiedź 429 → wydłużenie interwału) |
| Bezpieczeństwo | Sekret OAuth zapisany w bezpiecznym magazynie systemu (np. Windows Credential Manager), nie w zwykłym pliku; uprawnienia tylko do odczytu; v1 używana wewnętrznie, dostęp z sieci firmowej; logowanie (np. konto firmowe) możliwe w kolejnej wersji |
| Odporność | Brak połączenia z Orchestratorem nie czyści ekranu: widoczne ostatnie dane i czas ostatniej udanej aktualizacji |
| Strefa czasowa | Wszystkie godziny wyświetlane w Europe/Warsaw |
| Logowanie | Aplikacja loguje lokalnie błędy wywołań API i czas odpowiedzi |

## 10. Ustalenia

Wszystkie pytania mają odpowiedź.

- Raporty: „bez błędów” = brak Faulted i AE; BE to nie błąd (potwierdzone).
- Raporty: formaty CSV i Excel (potwierdzone).
- Historia: Orchestrator ją trzyma, raporty bez lokalnej bazy (potwierdzone).
- Orchestrator: UiPath Automation Cloud, wersja 24.
- Użytkownicy: developerzy.
- AP/BE: Application Exception i Business Exception.
- Zakładka 3: element pojawia się po zakończeniu przetwarzania (liczone po EndProcessing).
- Zakładka 3: pokazuje wszystkie kolejki, także z zerami; % sukcesu, porównanie z wczoraj, szczegóły AE/BE, eksport CSV.
- Zakładka 3: elementy ponawiane liczone tylko po ostatecznym wyniku.
- Zakładka 2: wyróżnienie jobów działających dłużej niż 2 h; sekcja Pending.
- Logowanie: na razie użytek wewnętrzny, logowanie możliwe później.
- Odświeżanie: co ok. 30 s.
- Foldery: ustawienie w aplikacji.
- Aplikacja na pulpit, Windows, Python z PySide6.
- Powiadomienia: tak, w tym joby Faulted; z czasowym wyciszeniem.
- Raporty za dzień, tydzień lub miesiąc.
- Notatki do błędów: wspólny folder sieciowy zespołu (wybrane 2026-11-27 zamiast Storage Bucket w Orchestratorze, listy SharePoint czy własnego serwera), bez nowych uprawnień w Orchestratorze.

