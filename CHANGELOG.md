# Changelog

## 0.1.0 (nieopublikowane)

### T1: fundamenty (kroki 01-05)
- Szkielet repo, pyproject, CI (ruff, mypy, pytest z pokryciem), `python -m orch_monitor --version`.
- `clock.py`: `utc_now`, `WARSAW`, `day_window`, `to_local`.
- Ustawienia (TOML, pydantic) i sekret w keyring.
- `api.auth.TokenProvider` (OAuth client credentials, cache, odswiezanie 60 s przed wygasnieciem).
- `api.client.OrchestratorClient` (naglowki, stronicowanie, `$count`, ponowienia 429/5xx, 401).
- `api.folders`: lista folderow i dopasowanie folderow z ustawien.

### T2: warstwa danych (kroki 06-10)
- `services/robots.py`: statusy robotow z `Sessions`, sortowanie, deduplikacja, podsumowanie.
- `services/jobs.py`: Running (`is_long`), Pending, Faulted od zadanego czasu.
- `services/queues.py`: dzisiejsze liczniki kolejek, % sukcesu, zmiana vs wczoraj (bez `Retried`).
- `services/queue_details.py`: dzisiejsze elementy AE/BE (limit 500, flaga `truncated`).
- `refresh/snapshot.py` (`Snapshot`, `DataFetcher`) i `refresh/scheduler.py` (`RefreshScheduler` w watku).

### T3: interfejs (kroki 11-15)
- Okno główne z zakładkami Roboty, Działające, Kolejki; pasek stanu z ostrzeżeniem o braku połączenia; ikona w zasobniku.
- `app.py` jako composition root; przebudowa klienta i interwału po zapisie ustawień, bez restartu.
- Okno ustawień (test połączenia, wybór folderów, walidacja), szczegóły kolejki AE/BE, eksport kolejek do CSV (UTF-8 z BOM, `;`).

### T4: powiadomienia, raporty, logi (kroki 16, 18, 19, 21)
- `notify/engine.py`: wykrywanie nowych AE/BE, rozłączonych robotów i nowych Faulted, grupowanie, wyciszenie.
- `reports/`: okresy dzień/tydzień/miesiąc/zakres, `build_report`, eksport ZIP z 5 CSV i Excel (5 arkuszy).
- `logging_setup.py`: log do pliku z rotacją 5 × 1 MB, maskowanie tokenów i sekretów.
