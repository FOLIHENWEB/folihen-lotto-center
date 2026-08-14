# TOC Project State

## Current Phase

Phase 3 integration is stabilized to the extent verified in the current repository and runtime checks. The local React/Vite frontend and Flask backend are connected, canonical MASTER_DATA is available, Kadijja and Desmond execute through the Prediction Engines flow, Theresa Tier 1 executes through its existing output stream, and read-only MASTER_DATA, History, and Reports views consume real persisted/canonical data.

This document records current implementation state; it is not a substitute for re-verifying behavior after later changes.

## Working Components

| Component | Current implemented state |
| --- | --- |
| Dashboard | Implemented visual operational landing page. It contains explanatory status/workspace content; the StatusBar is the API-derived connection surface. |
| MASTER_DATA | Implemented read-only canonical data page. Displays connection state, game count, canonical record count, normalization time, all canonical games, selected-game metadata, and ten recent draws. |
| Prediction Engines | Implemented canonical game selection, real running state, API execution, backend persistence reload, notifications, and independent full-output panels. |
| Kadijja | Integrated as an independent subprocess through the Flask API. Its artifact data is parsed into ordered prediction tiers. |
| Desmond | Integrated as an independent subprocess through the Flask API. Its stdout/artifact data is parsed into ordered prediction tiers. |
| Theresa | Integrated as an independent Tier 1 subprocess. Health, latest persisted JSON, selected-game run confirmation, notifications, and result rendering are implemented. |
| Theresa Intelligence | Intentionally a placeholder. It is not the Theresa Tier 1 execution system and is not implemented in TOC. |
| History | Implemented read-only persisted-operation view with game/operation filters and expandable details. |
| Reports | Implemented read-only independent source reports with game/source filters. |
| System | Intentional future placeholder. |
| Settings | Intentional future placeholder. |
| About | Intentional future placeholder. |
| Notifications / running indicators | NotificationContext backs the bell. BottomActionBar sends running/success/warning/error notifications only around real API activity. StatusBar performs backend-derived availability checks. |

## MASTER_DATA

- Canonical source architecture: external MASTER_DATA DOCX documents are discovered and read by `backend/master_data_reader.py`. The configured location is derived from the current user Documents directory; do not place a machine-specific absolute path in new frontend code or documentation.
- Normalization: `backend/normalized_data.py` validates the source and atomically writes `backend/data/normalized_master_data.json`.
- Canonical service: `backend/engine_data_service.py` validates and exposes immutable game metadata and records to engines and API routes.
- Expected games: 19.
- Current verified canonical dataset after safe normalization refresh: 19 games and 2,541 records.
- Read endpoints: `GET /api/master-data/games`, `GET /api/master-data/summary`, and `GET /api/master-data/games/<game>`.
- Update workflow: `POST /api/master-data/update` runs the existing normalizer. `POST /api/master-data/add-draw` is the guarded official-draw write path with validation, backup, normalization, and rollback behavior.
- Integrity rules: never silently change a source DOCX; do not create competing readers/parsers; use the engine data service for canonical game and record access; do not run destructive official-draw tests against live MASTER_DATA.

## Prediction Engines

- Frontend page: `src/pages/PredictionEnginesPage.tsx`.
- Shared operational control: `src/components/layout/BottomActionBar.tsx`.
- API routes: `POST /api/prediction-engines/run` and `GET /api/prediction-engines/latest`.
- The API validates the selected canonical game, resolves Kadijja's internal game ID only for Kadijja execution, runs both real engines, captures output, enriches returned results, rejects unusable engine output, and persists a full successful run in `backend/data/latest_prediction_engines.json`.
- Partial failure retains and returns individual engine results. Full failure returns an error state. Success requires usable Top 5, Top 2, banker, and confidence for both engines.
- Result shape: each engine is a separate element of `results[]` with `engine`, `status`, `return_code`, `prediction`, optional `prediction_artifact`, stdout/stderr, and an error message when applicable.
- `prediction` currently exposes ordered `top2`, `top5`, `top10`, `top20`, `top30`, `top60`, `banker`, and `confidence` for both verified engines.
- The page renders each engine in a separate full panel. It never merges values, changes order, or uses values from the other engine as fallback.

### Kadijja

- Engine: `backend/engines/kadija/kadija_engine_toc.py`.
- Invocation: Flask supplies Kadijja's required internal game ID.
- Result source: reported Kadijja JSON artifact, normalized from ranked number objects into ordered tier arrays.
- Verified runtime behavior: returned usable banker, confidence, Top 2 through Top 60, and artifact path for a real selected-game run.

### Desmond

- Engine: `backend/engines/desmond/desmond_engine_toc.py`.
- Invocation: Flask supplies the canonical selected game name.
- Result source: real stdout and, where printed, JSON artifact path.
- Verified runtime behavior: returned usable banker, confidence, Top 2 through Top 60, and artifact path for a real selected-game run.

## Theresa

- Frontend: `src/pages/TheresaPage.tsx`; operational trigger: `BottomActionBar`.
- API: `GET /api/theresa/health`, `GET /api/theresa/latest`, and `POST /api/theresa/run`.
- Backend execution: `backend/theresa/theresa_api.py` calls `run_theresa`, which invokes `backend/theresa/theresa_engine_toc.py` and reads the existing resulting `Theresa_*.json` artifact.
- The run action uses the canonical game selector, sends the explicit selected game, shows a real running state, and emits success only after a successful backend response.
- TheresaPage checks health, loads the latest persisted prediction, and refreshes after the existing `theresa:run-complete` event. It renders the actual Theresa game, generated timestamp, banker, confidence, Top 2/5/10/20/30/60, and its existing Tier 1 presentation.
- Verified runtime behavior: a real `fortune thursday` run returned HTTP 200 with a Theresa-owned prediction, banker, confidence, and prediction tiers.

## Theresa Intelligence

Theresa Intelligence Analyzer remains intentionally deferred at `/theresa-intelligence`. It is distinct from ordinary Theresa Tier 1 prediction execution. No Intelligence Analyzer backend route, stored output source, or calculation implementation was verified in this repository, and none was invented.

## History

- Frontend: `src/pages/HistoryPage.tsx`.
- API: `GET /api/history`, with optional `game` and `operation` filters.
- Real sources: the latest usable persisted Prediction Engines payload and existing Theresa `Theresa_*.json` artifacts.
- The view is newest-first, read-only, and expandable. It does not rerun engines or manufacture records.
- Current limitation: MASTER_DATA update/add-draw operations are not represented because the repository has no persistent operation-event store for those actions.

## Reports

- Frontend: `src/pages/ReportsPage.tsx`.
- API: `GET /api/reports`, with optional `game` and `source` filters.
- Real sources: the same persisted latest Prediction Engines payload and Theresa JSON artifacts used by History.
- Each report row is source-specific: Kadijja, Desmond, or Theresa. It shows returned banker, confidence, tiers, status, timestamp, and artifact/reference; unavailable fields display `Not returned`.
- No consensus row or recalculated prediction is created.

## Important Decisions

1. MASTER_DATA is authoritative for available games. The game selector uses the canonical data service, not Kadijja's internal registry.
2. The normalized data service is the common read boundary for engines and API consumers.
3. Kadijja, Desmond, and Theresa remain independent systems. Presentation is standardized into clear tiered layouts without combining outputs.
4. Backend success is stricter than a child-process exit code: prediction success requires usable renderable fields.
5. The API owns file access, artifacts, engine invocation, persistence, and response shaping. React owns selection, running state, rendering, and notifications.
6. History and Reports are thin read-only consumers of existing persisted outputs, not alternate engine runners or synthetic data stores.

## Known Limitations / Remaining Issues

- Theresa Intelligence Analyzer is intentionally not implemented in TOC.
- System, Settings, and About are intentionally future placeholders.
- History and Reports only have sources that the repository currently persists: latest usable Prediction Engines output and Theresa artifact files. There is no durable event history for MASTER_DATA operations or a separate Theresa Intelligence source.
- Prediction Engines persistence currently retains the latest successful combined run rather than a durable full run archive. Theresa artifacts provide a broader file-backed history.
- The active Pylance analysis environment may report `flask` as unresolved even though the project Python interpreter compiled and served the Flask application during verification. Re-check the selected interpreter before treating that editor diagnostic as a runtime defect.

## Next Major Development

The next major intelligence development will **not** be performed inside TOC initially.

Theresa Tier 2 will first be completed and validated inside the dedicated Theresa project/repository. After Theresa Tier 2 is independently stable and validated, it can be integrated into TOC.

Theresa Tier 2 analyzes **Theresa's predictions/intelligence only**. It must not analyze Kadijja, Desmond, Max, or future engines. Equivalent independent intelligence analyzers may later be created for other engines.

## Resume Instructions

At the beginning of every future TOC development session:

1. Read `.github/copilot-instructions.md`.
2. Read `docs/PROJECT_STATE.md`.
3. Inspect `git status`.
4. Inspect recent relevant commits when necessary.
5. Confirm the requested task against the current architecture.
6. Do not recreate components already marked complete without first verifying a defect.
7. Update `PROJECT_STATE.md` whenever a meaningful project milestone or architectural decision changes.
8. Never silently change the permanent architecture rules.

## Verified Commands

```powershell
npm run build
python -m py_compile backend\theresa\theresa_api.py
python backend\normalized_data.py --dry-run
python backend\theresa\theresa_api.py
npm run dev
```

Runtime validation during the Phase 3 state recorded here confirmed the Vite proxy, 19 canonical games, the refreshed 2,541-record canonical dataset, real Kadijja/Desmond output display, real Theresa output display, and the read-only MASTER_DATA, History, and Reports pages.
