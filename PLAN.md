# PLAN.md – realizacja Orchestrator Monitor

Źródło: `docs/plan_budowy.md` (22 kroki, przypadki TC-xx.y) i `docs/specyfikacja.md` (spec v1.2).
Kroki są pogrupowane w zadania dla pipeline'u (jedno zadanie = jeden subagent). Pełna treść kroku,
kryteria akceptacji i przypadki testowe są w `docs/plan_budowy.md` pod nagłówkiem `### NN.`.

Weryfikacja wspólna (Definition of Done) dla każdego zadania:
```
cd /home/user/orch-monitor
.venv: /home/user/.venv-om/bin
ruff check . && ruff format --check . && mypy orch_monitor
QT_QPA_PLATFORM=offscreen pytest -q
pytest -q -k "TC_NN"   # testy danego kroku
```
plus pokrycie >= 85% dla `api`, `services`, `notify`, `reports`, wpis w `CHANGELOG.md`.

| ID | Tytuł | Kroki | Model | Zależy od | Status |
|---|---|---|---|---|---|
| T1 | Fundamenty: szkielet, ustawienia, OAuth, klient OData, foldery | 01–05 | sonnet | – | ✅ |
| T2 | Warstwa danych: roboty, joby, kolejki, szczegóły, harmonogram | 06–10 | sonnet | T1 | ☐ |
| T3 | Interfejs: okno, zasobnik, 3 zakładki, ustawienia, CSV | 11–15 | sonnet | T2 | ☐ |
| T4 | Silnik powiadomień, raporty (agregacja + eksport), logi | 16, 18, 19, 21 | sonnet | T2 | ☐ |
| T5 | UI powiadomień i raportu, menu logów, pakowanie .exe | 17, 20, 21 (menu), 22 | sonnet | T3, T4 | ☐ |
| T6 | Dokumentacja: CLAUDE.md, README, CHANGELOG | – | haiku | T5 | ☐ |
| T7 | Weryfikacja końcowa (pełne testy, diff, zgodność z planem) | – | opus | T6 | ☐ |

T3 i T4 idą równolegle: T3 rusza tylko `ui/`, T4 tylko `notify/`, `reports/`, `logging_setup.py`.
`reports/csv_export.py` tworzy T4 (krok 19 wymaga go szerzej); T3 dla eksportu zakładki 3
tworzy własną funkcję w `reports/csv_export.py` TYLKO jeśli plik nie istnieje – aby uniknąć kolizji,
T3 umieszcza zapis CSV zakładki w `orch_monitor/reports/csv_queues.py` (TC-14.5/14.6), a T4
w `csv_export.py` może go reużyć.

Krok 22: budowa .exe wymaga Windows. W tym środowisku (Linux) powstaje spec PyInstallera, flaga
`--self-test`, job CI na `windows-latest`; TC-22.1–22.3 sprawdzane buildem linuksowym jako smoke,
TC-22.4–22.6 to lista ręczna / marker `live`.

## Log eskalacji
(brak)
