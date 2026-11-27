# Lista kontrolna: test na tenancie testowym (krok 22)

Wykonaj na Windows 10/11, na tenancie testowym Orchestratora (Automation Cloud). Aplikacja pracuje tylko
w trybie odczytu; konto aplikacji (External Application) potrzebuje uprawnień do odczytu zasobów
Orchestratora (OR.Robots.Read, OR.Jobs.Read, OR.Queues.Read, OR.Folders.Read, OR.Execution.Read — te same co w `api/auth.py`).

## Przygotowanie
1. Pobierz `OrchMonitor.exe` z artefaktu pipeline'u (job `build-windows`) i skopiuj na komputer bez Pythona.
2. Uruchom `OrchMonitor.exe --version` i `OrchMonitor.exe --self-test` w terminalu: oczekiwany kod wyjścia 0
   (`echo %ERRORLEVEL%`).
3. Uruchom `OrchMonitor.exe`. Powinno pojawić się okno i ikona w zasobniku.

## TC-22.4 Połączenie z tenantem testowym
1. W oknie Ustawienia wpisz organizację, tenant, Client ID i Client Secret; kliknij „Testuj połączenie”.
2. Oczekiwane: komunikat „Połączono”, lista folderów. Wybierz folder testowy i zapisz.
3. W ciągu ok. 30 s zakładki Roboty, Działające i Kolejki pokazują dane.
4. Porównaj z Orchestratorem (Tenant > Roboty, Zadania, Kolejki): statusy robotów, działające joby i
   liczniki AE/BE zgodne. Zapisz rozbieżności: ______
5. Pasek stanu pokazuje aktualny czas ostatniej aktualizacji; po odcięciu sieci pojawia się ostrzeżenie.

## TC-22.5 Powiadomienie o AE
1. Upewnij się, że w Ustawieniach włączone jest powiadomienie o AE i że powiadomienia nie są wyciszone.
2. W Orchestratorze uruchom na folderze testowym proces, który dodaje element kolejki kończący się
   Application Exception (albo ustaw element jako Failed z błędem aplikacyjnym).
3. Oczekiwane: w ciągu ok. 30 s powiadomienie Windows „Kolejka …”, a licznik AE w zakładce Kolejki wzrósł.
4. Kliknij powiadomienie: okno otwiera się na zakładce Kolejki.
5. Ikona zasobnika > „Wycisz powiadomienia” > „na 30 min”: ikona zmienia wygląd, kolejne AE nie dają
   powiadomienia; „Włącz powiadomienia” przywraca zwykłą ikonę.

## TC-22.6 Raport tygodniowy do Excela
1. Ikona zasobnika > „Raporty…” (lub przycisk „Raporty…” w oknie). Wybierz „Tydzień” i datę z ostatniego tygodnia.
2. Zaznacz folder testowy, kliknij „Generuj”. Pasek postępu działa, okno nie blokuje się.
3. Oczekiwane: werdykt i zakładki Podsumowanie, Procesy, Kolejki, Dni, Błędy.
4. „Zapisz Excel”, otwórz plik w Excelu: 5 arkuszy, daty jako daty, % jako procenty.
5. Porównaj liczby (uruchomienia, Faulted, AE, BE) z widokiem w Orchestratorze za ten sam tydzień
   (Monitoring / Jobs / Queues). Rozbieżności: ______
6. „Zapisz CSV”: ZIP z 5 plikami CSV (UTF-8, separator `;`) otwiera się w Excelu poprawnie.

## Notatki do błędów (krok 24)
1. Ustawienia > „Folder notatek zespołu”: wskaż wspólny folder sieciowy, zapisz.
2. Szczegóły kolejki z AE: dwuklik na elemencie, dodaj notatkę. W kolumnie „Notatki” pojawia się „📝 1”.
3. Na drugim komputerze (inny login Windows, ten sam folder): ta sama notatka widoczna, autor = login z pkt 2.
   Dopisz notatkę, na pierwszym komputerze „Odśwież” w oknie notatek pokazuje obie.
4. Cudzej notatki nie da się usunąć („Usuń moją notatkę” nieaktywne), własną tak.
5. Job Faulted z dzisiaj widoczny w zakładce Działające w sekcji „Dziś zakończone błędem (Faulted)”; dwuklik otwiera notatki.

## Logi
- Ikona zasobnika > „Otwórz folder logów”: `%LOCALAPPDATA%\OrchMonitor\logs\orch_monitor.log`.
- Sprawdź, że w logu nie ma tokenu ani client secret.

Wynik: ☐ zaliczone ☐ uwagi: ______ Data: ______ Wykonał: ______
