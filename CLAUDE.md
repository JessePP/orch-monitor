# CLAUDE.md – Orchestrator Monitor

## Brief
Desktopowa aplikacja Windows (Python + PySide6) tylko do odczytu, monitorująca UiPath Orchestrator
(Automation Cloud, v24) dla developerów RPA. Trzy zakładki (Roboty, Działające, Kolejki), powiadomienia
na pulpicie z wyciszeniem, raporty dzień/tydzień/miesiąc do CSV i Excel. Odświeżanie co ~30 s.
Pełne wymagania: `docs/specyfikacja.md`. Plan kroków i przypadki testowe: `docs/plan_budowy.md`.
Zadania pipeline'u i status: `PLAN.md`.

## Stack
Python >= 3.12 (lokalnie 3.13), PySide6, httpx, keyring, pydantic v2, openpyxl, tzdata, PyInstaller.
Testy: pytest, pytest-qt, pytest-cov, respx, freezegun. Jakość: ruff (lint + format), mypy.

## Środowisko i komendy
- Katalog projektu: `/home/user/orch-monitor`. Virtualenv: `/home/user/.venv-om` (wszystko zainstalowane;
  doinstalowanie: `/home/user/.venv-om/bin/pip install ...` i dopisanie do `pyproject.toml`).
- Lint/format: `/home/user/.venv-om/bin/ruff check . && /home/user/.venv-om/bin/ruff format --check .`
- Typy: `/home/user/.venv-om/bin/mypy orch_monitor`
- Testy: `QT_QPA_PLATFORM=offscreen /home/user/.venv-om/bin/pytest -q`
- Pokrycie: `... pytest --cov=orch_monitor --cov-report=term-missing`
- Uruchomienie: `python -m orch_monitor` (`--version`, `--self-test`).

## Konwencje (obowiązkowe)
- Pakiet `orch_monitor/`: `config/`, `api/`, `services/`, `refresh/`, `notify/`, `reports/`, `ui/`.
- Warstwy `config`, `api`, `services`, `refresh`, `notify`, `reports` NIE importują PySide6
  (test TC-01.3 tego pilnuje). Qt tylko w `ui/` i `app.py`.
- Czas zawsze wstrzykiwany: `clock: Callable[[], datetime]` (zwraca aware UTC). Nigdy `datetime.now()`
  bez strefy w logice. Strefa wyświetlania: `Europe/Warsaw` (`zoneinfo`). API zwraca UTC.
- Testy nigdy nie łączą się z prawdziwym Orchestratorem: HTTP mockowany przez `respx`, fixture JSON
  w `tests/fixtures/`. Testy jednostkowe w `tests/unit/`, testy UI w `tests/ui/` (pytest-qt, offscreen).
- Każdy przypadek z planu ma test, którego nazwa zawiera ID w formie `TC_NN_M`,
  np. `def test_TC_07_3_threshold_change(...)`.
- Sekret (client secret) tylko w keyring, nigdy w pliku ustawień, logach ani komunikatach błędów.
- Typowanie pełne (mypy w trybie `strict` dla pakietu, z wyjątkiem ignorowania braków stubów).
- Teksty UI po polsku.
- Każde zadanie dopisuje krótką notkę do `CHANGELOG.md`.

## Status
- Wszystkie 22 kroki zaimplementowane. 161 testów automatycznych zielonych (+3 `live` pomijane), pokrycie ~91%.
- Zostaje: build .exe na Windows w CI (job `build-windows`), ręczna lista kontrolna
  `docs/lista_kontrolna_tenant.md` (TC-22.4–22.6), potwierdzenie nazw pól API na Swaggerze tenanta.
- Szczegóły zadań: `PLAN.md`.

## Log decyzji
- 2026-11-26 — Repo lokalne w `/home/user/orch-monitor`, kopia w `/mnt/project-files/orch-monitor/` — brak repozytorium GitHub.
- 2026-11-26 — Krok 22 (.exe) budowany w CI na runnerze Windows; tutaj tylko spec i smoke na Linuksie — środowisko jest linuksowe.
- 2026-11-26 — Pusta lista folderów = wszystkie foldery — wygodny start bez konfiguracji.
- 2026-11-26 — Wczorajsze liczniki kolejek cache'owane per doba — mniej zapytań co 30 s.
- 2026-11-26 — Eksport CSV raportu jako ZIP z 5 plikami — założenie z planu.
- 2026-11-26 — Wyciszenie powiadomień tylko w pamięci — założenie z planu.
- 2026-11-26 — Helpery testów UI w `tests/ui/helpers.py` zamiast `conftest.py` — conftest w `tests/ui` przesłaniał importy testów unit.

## Znane pułapki
- PySide6 na Linuksie wymaga libEGL/libGL; testy UI z `QT_QPA_PLATFORM=offscreen`. Tray niedostępny
  offscreen (`QSystemTrayIcon.isSystemTrayAvailable() == False`) – testy mockują tray.
- Zmiana czasu (marzec/październik): granice doby liczyć w Europe/Warsaw, potem konwertować na UTC.
- Aplikacja windowed (PyInstaller, `console=False`) nie ma stdout: `--version` i `--self-test` sprawdzać kodem wyjścia, nie tekstem.
- Ikona `packaging/orch_monitor.ico` ma tylko 32×32 px.
- Nazwy pól OData (`ProcessingExceptionType`, `ReportingTime`) przyjęte z dokumentacji — potwierdzić na Swaggerze tenanta.
