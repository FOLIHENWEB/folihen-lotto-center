# TOC Repository Instructions

## Purpose

TOC (Theresa Operations Center) is the local operational interface for canonical MASTER_DATA, the Kadijja and Desmond prediction engines, and the Theresa prediction system. The React UI never reads local data files or runs engines directly; it talks to the Flask API, which owns canonical data access and subprocess execution.

## Architecture

- Frontend: React 19, TypeScript, Vite, and React Router. Entry: `src/main.tsx`; application router: `src/app/AppRouter.tsx`; shared shell: `src/components/layout/AppShell.tsx`.
- Frontend development server: Vite. `vite.config.ts` proxies `/api` to the Flask backend at `http://127.0.0.1:5050`.
- Backend: Flask application and executable entry point: `backend/theresa/theresa_api.py`. It binds `127.0.0.1:5050` when run directly.
- Canonical data: MASTER_DATA DOCX files are read by `backend/master_data_reader.py`; `backend/normalized_data.py` validates and atomically produces `backend/data/normalized_master_data.json`; `backend/engine_data_service.py` is the immutable, validated engine-facing access layer.
- Data write path: `backend/master_data_writer.py` is the only supported official-draw writer. It validates, backs up, updates a source DOCX, and normalizes. Do not use it for incidental testing.

## Frontend Routes

The active application routes are:

- `/`: dashboard
- `/master-data`: canonical read-only dataset view
- `/prediction-engines`: Kadijja and Desmond execution/results
- `/theresa`: Theresa Tier 1 health and latest prediction
- `/theresa-intelligence`: intentional future placeholder
- `/history`: persisted operation history
- `/reports`: persisted independent-result reports
- `/system`, `/settings`, `/about`: intentional future placeholders

`BottomActionBar` loads canonical games and owns the operational actions for MASTER_DATA update/add-draw, Prediction Engines, and Theresa. `StatusBar` derives service availability from API checks. `NotificationContext` is the bell/notification state; `LogContext` is the in-memory execution-log infrastructure.

## API Contract

Routes currently registered in `backend/theresa/theresa_api.py`:

- `GET /api/master-data/games`: canonical game list from `engine_data_service`, not an engine registry.
- `GET /api/master-data/summary`: canonical dataset metadata and all game summaries.
- `GET /api/master-data/games/<game>`: selected game metadata and a bounded recent-record preview.
- `POST /api/master-data/update`: runs the existing normalizer.
- `POST /api/master-data/add-draw`: validated official-draw write path; never call for destructive testing.
- `GET /api/prediction-engines/latest`: latest persisted usable Kadijja/Desmond run.
- `POST /api/prediction-engines/run`: validates a canonical selected game, runs Kadijja and Desmond, parses real output, and persists only a usable full success.
- `GET /api/theresa/health`: Theresa engine/output availability.
- `GET /api/theresa/latest`: latest persisted Theresa JSON, optionally filtered by game.
- `POST /api/theresa/run`: runs existing Theresa Tier 1 with the selected game and returns the resulting prediction.
- `GET /api/history`: read-only aggregation of the persisted latest Prediction Engines run and Theresa JSON artifacts.
- `GET /api/reports`: read-only flattened, source-specific Kadijja, Desmond, and Theresa report rows.

## MASTER_DATA Rules

- MASTER_DATA is the canonical source of historical draw data.
- MASTER_DATA must not be silently modified.
- Preserve the single canonical reader/parser in `backend/master_data_reader.py`; do not create competing parsers unless explicitly justified.
- Use `engine_data_service.get_data_service()` for canonical game enumeration, metadata, records, and game-name resolution.
- The expected canonical game count is 19. Treat the normalized JSON as generated data; use the existing normalizer when a safe canonical refresh is necessary.
- Do not hard-code games in React and do not make Kadijja responsible for MASTER_DATA discovery.

## Engine Integration Rules

### Kadijja

- Engine file: `backend/engines/kadija/kadija_engine_toc.py`.
- Kadijja is an independent prediction engine. Its internal game-ID resolver is used only for Kadijja invocation.
- The API invokes it with its required game ID and parses its reported JSON artifacts. Ranked artifact objects are normalized to ordered number lists.

### Desmond

- Engine file: `backend/engines/desmond/desmond_engine_toc.py`.
- Desmond is an independent prediction engine. The API invokes it with the canonical game name and parses its real stdout/artifact output.

### Theresa

- Engine file: `backend/theresa/theresa_engine_toc.py`.
- Theresa is an independent prediction system. The API runs it through `run_theresa`, then reads its existing `Theresa_*.json` output from its configured output stream.
- The Theresa page is the authoritative UI for Theresa Tier 1 output. Its `generated`, prediction tiers, banker, and confidence are Theresa-owned fields.

### Theresa Intelligence

- Theresa Intelligence Analyzer is separate from Theresa prediction execution.
- It is intentionally not implemented in TOC at this time. Preserve the `/theresa-intelligence` placeholder; do not invent a replacement engine or route.

## Prediction Presentation and State

- Kadijja, Desmond, and Theresa presentation uses clearly structured prediction tiers while remaining independent.
- Kadijja and Desmond panels each display their own banker, confidence, Top 2, Top 5, Top 10, Top 20, Top 30, Top 60, and artifact when returned.
- Never substitute one engine's result for another. Never use one engine's result as a fallback for another.
- Never merge engine predictions unless an explicitly designed future TOC layer requires it.
- Preserve every engine's prediction ordering exactly as returned. Do not sort or deduplicate UI values.
- If a field is genuinely absent, show the explicit missing state; do not manufacture values.
- A process exit code or HTTP 200 alone is not a prediction success. A usable output must exist before success is reported.
- Connected, Running, Completed, Failed, and No Result are distinct states. Success notifications must follow confirmed backend success, not button clicks or timers.
- Do not alter engine algorithms merely to satisfy UI requirements.

## History and Reports

- History must contain real persisted system activity, not manufactured/mock history.
- Current history sources are the latest usable prediction-engine payload and existing Theresa JSON artifacts.
- Reports must consume real persisted outputs and retain source identity. Kadijja, Desmond, and Theresa are never combined into a consensus report row.
- Do not rerun an engine merely to populate History or Reports.

## Change Discipline

- Avoid placeholder/mock behavior in production operational pages.
- Prefer the smallest safe change over broad rewrites.
- Before modifying a working subsystem, trace its existing data flow first.
- Do not replace working architecture without explicit justification.
- Do not modify MASTER_DATA source files, prediction artifacts, or engine directories unless the requested feature explicitly requires it.
- Do not commit, push, merge, or tag unless the user explicitly requests it.

## Verified Commands

From the repository root:

```powershell
npm run dev
npm run build
npm run lint
python backend\theresa\theresa_api.py
python -m py_compile backend\theresa\theresa_api.py
python backend\normalized_data.py --dry-run
```

`npm run build` runs `tsc -b && vite build`. Run focused API checks through the live Flask server when changing integration behavior. Run appropriate validation before claiming completion, and never claim a feature works solely because a build or HTTP status succeeds: verify the user-visible behavior when applicable.
