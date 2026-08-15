// src/components/layout/BottomActionBar.tsx

import React, { useEffect, useState } from 'react';
import { useNotifications } from '../../contexts/NotificationContext';

type GameOption = {
  game_id?: number | string;
  game: string;
};

type ApiResponse = {
  status?: string;
  message?: string;
  return_code?: number;
  game?: string;
  game_id?: number | string;
  results?: Array<{
    engine?: string;
    status?: string;
    prediction?: unknown;
    message?: string;
  }>;
  [key: string]: unknown;
};

type DailyCycleResponse = {
  status?: string;
  message?: string;
  failed_stage?: string;
  context?: {
    game?: string;
    target_draw_date?: string;
    run_mode?: string;
    run_timestamp?: string;
  };
  stages?: Record<string, { status?: string; message?: string }>;
};

type NormalizationPreview = {
  status?: string;
  mode?: 'preview' | 'apply';
  artifacts_scanned?: number;
  safe_normalization_candidates?: number;
  already_aligned?: number;
  already_processed?: number;
  unmatched?: number;
  manual_review?: number;
  original_manual_review?: number;
  resolved_by_extended_evidence?: number;
  resolution_methods?: Record<string, number>;
  ordinary_engine_folders_discovered?: number;
  ordinary_engine_ids?: string[];
  logical_prediction_slots?: number;
  repeated_run_groups?: number;
  canonical_predictions?: number;
  superseded_runs_proposed?: number;
  true_duplicate_copies?: number;
  engine_summaries?: Record<string, {
    artifacts_scanned?: number;
    canonical_predictions?: number;
    superseded_proposed?: number;
    manual_review?: number;
    unmatched?: number;
  }>;
  theresa?: {
    artifacts_scanned?: number;
    logical_slots?: number;
    canonical_predictions?: number;
    superseded_proposed?: number;
    true_duplicates?: number;
    date_corrections_proposed?: number;
    manual_review?: number;
    unmatched?: number;
  };
  decisions?: NormalizationDecision[];
  master_data_modified?: boolean;
  message?: string;
};

type NormalizationDecision = {
  artifact_id?: string;
  engine?: string;
  canonical_game?: string;
  original_run_timestamp?: string;
  target_draw_date?: string;
  delay_days?: number;
  decision?: string;
  reason?: string;
  slot_status?: string;
  artifact_path?: string;
};

const reviewReasonCopy: Record<string, { label: string; meaning: string }> = {
  ambiguous_reliable_timestamp: { label: 'Timestamp uncertain', meaning: 'Several predictions have the same reliable run time, so the latest run cannot be chosen safely.' },
  delay_exceeds_automatic_window: { label: 'Delay exceeds automatic limit', meaning: 'The prediction is outside the automatic 0-5 day correction window and has been left untouched for safety.' },
  explicit_target_after_run: { label: 'Target date is after the run', meaning: 'The prediction metadata names a draw date after the prediction was generated.' },
  explicit_target_conflict: { label: 'Target-date conflict', meaning: 'Prediction metadata conflicts with a possible official MASTER_DATA draw.' },
  game_not_recognized: { label: 'Game not recognized', meaning: 'The exported game name could not be matched safely to a canonical MASTER_DATA game.' },
  missing_game: { label: 'Game missing', meaning: 'The export does not identify a game.' },
  missing_run_timestamp: { label: 'Timestamp missing', meaning: 'A reliable prediction run time could not be established.' },
  multiple_master_data_candidates: { label: 'Multiple possible draws', meaning: 'More than one MASTER_DATA draw could match this prediction.' },
  weak_filesystem_timestamp: { label: 'Timestamp uncertain', meaning: 'Only a filesystem timestamp was available, which is not reliable enough for automatic normalization.' },
  resolved_by_same_engine_sequence: { label: 'Resolved by same-engine sequence', meaning: 'This prediction sits between two already proven exports from the same engine, with exactly one official MASTER_DATA draw between their targets.' },
  resolved_by_cross_engine_corroboration: { label: 'Resolved by cross-engine corroboration', meaning: 'Two independent proven engines identify one compatible official draw within the same 24-hour operational period.' },
};

const displayEngineName = (engine: string) =>
  engine.replace(/[_-]+/g, ' ').replace(/\b\w/g, character => character.toUpperCase());

const PREDICTION_STORAGE_KEY =
  'theresa:lastPredictionEngineRun';

const PREDICTION_EVENT =
  'theresa:prediction-engines-complete';

const MASTER_DATA_STORAGE_KEY =
  'theresa:master-data-status';

const MASTER_DATA_EVENT =
  'theresa:master-data-updated';

const BottomActionBar: React.FC = () => {
  const { addNotification } = useNotifications();
  const [games, setGames] =
    useState<GameOption[]>([]);

  const [selectedGame, setSelectedGame] =
    useState('');

  const [showPredictionDialog, setShowPredictionDialog] =
    useState(false);

  const [showTheresaDialog, setShowTheresaDialog] =
    useState(false);

  const [showTheresaIntelligenceDialog, setShowTheresaIntelligenceDialog] =
    useState(false);

  const [showMasterDataDialog, setShowMasterDataDialog] =
    useState(false);

  const [showNormalizationDialog, setShowNormalizationDialog] =
    useState(false);

  const [showDailyCycleDialog, setShowDailyCycleDialog] =
    useState(false);

  const [showDailyCycleConfirmation, setShowDailyCycleConfirmation] =
    useState(false);

  const [dailyCycleReady, setDailyCycleReady] =
    useState(false);

  const [runningDailyCycle, setRunningDailyCycle] =
    useState(false);

  const [dailyCycleMode, setDailyCycleMode] =
    useState<'live' | 'backdated'>('live');

  const [dailyCycleTargetDate, setDailyCycleTargetDate] =
    useState('');

  const [dailyCycleResult, setDailyCycleResult] =
    useState<DailyCycleResponse | null>(null);

  const [normalizingPredictionDates, setNormalizingPredictionDates] =
    useState(false);

  const [normalizationPreview, setNormalizationPreview] =
    useState<NormalizationPreview | null>(null);

  const [showNormalizationConfirmation, setShowNormalizationConfirmation] =
    useState(false);

  const [showManualReviewDetails, setShowManualReviewDetails] =
    useState(false);

  const [drawGame, setDrawGame] =
    useState('');

  const [drawDate, setDrawDate] =
    useState('');

  const [drawNumbers, setDrawNumbers] =
    useState(['', '', '', '', '']);

  const [loadingGames, setLoadingGames] =
    useState(false);

  const [runningPredictions, setRunningPredictions] =
    useState(false);

  const [updatingMasterData, setUpdatingMasterData] =
    useState(false);

  const [runningTheresa, setRunningTheresa] =
    useState(false);

  const [runningTheresaIntelligence, setRunningTheresaIntelligence] =
    useState(false);

  const [message, setMessage] =
    useState<string | null>(null);

  const [error, setError] =
    useState<string | null>(null);

  /* =========================================================
    LOAD GAMES
    ========================================================= */

  const loadGames = async () => {
    setLoadingGames(true);

    try {
      const response = await fetch(
        '/api/master-data/games',
        {
          method: 'GET',
          headers: {
            Accept: 'application/json',
          },
        },
      );

      const payload =
        (await response.json()) as {
          status?: string;
          games?: GameOption[];
          message?: string;
        };

      if (!response.ok) {
        throw new Error(
          payload.message ||
            `Unable to load games (${response.status}).`,
        );
      }

      const availableGames =
        Array.isArray(payload.games)
          ? payload.games
          : [];

      setGames(availableGames);

      if (
        availableGames.length > 0 &&
        !selectedGame
      ) {
        setSelectedGame(
          availableGames[0].game,
        );
      }

      if (
        availableGames.length > 0 &&
        !drawGame
      ) {
        setDrawGame(
          availableGames[0].game,
        );
      }
    } catch (err) {
      console.error(
        'Unable to load games:',
        err,
      );
    } finally {
      setLoadingGames(false);
    }
  };

  useEffect(() => {
    void loadGames();
  }, []);

  useEffect(() => {
    const loadDailyCycleHealth = async () => {
      try {
        const response = await fetch('/api/daily-cycle/health', { headers: { Accept: 'application/json' } });
        const payload = await readNormalizationResponse(response);
        setDailyCycleReady(response.ok && payload.status === 'ready');
      } catch {
        setDailyCycleReady(false);
      }
    };
    void loadDailyCycleHealth();
  }, []);

  /* =========================================================
    MASTER_DATA STATUS
    ========================================================= */

  const markMasterDataConnected = (
    response: ApiResponse,
  ) => {
    const storedValue = {
      connected: true,
      updated_at:
        new Date().toISOString(),
      response,
    };

    localStorage.setItem(
      MASTER_DATA_STORAGE_KEY,
      JSON.stringify(storedValue),
    );

    window.dispatchEvent(
      new CustomEvent(
        MASTER_DATA_EVENT,
        {
          detail: storedValue,
        },
      ),
    );
  };

  /* =========================================================
    NORMALIZE MASTER_DATA
    ========================================================= */

  const normalizeMasterData = async () => {
    setUpdatingMasterData(true);
    setError(null);

    setMessage(
      'Updating MASTER_DATA...',
    );

    try {
      const response = await fetch(
        '/api/master-data/update',
        {
          method: 'POST',
          headers: {
            Accept: 'application/json',
          },
        },
      );

      const payload =
        (await response.json()) as ApiResponse;

      if (!response.ok) {
        throw new Error(
          payload.message ||
            `MASTER_DATA update failed (${response.status}).`,
        );
      }

      if (
        payload.status &&
        payload.status !== 'success'
      ) {
        throw new Error(
          payload.message ||
            'MASTER_DATA update failed.',
        );
      }

      markMasterDataConnected(
        payload,
      );

      setMessage(
        payload.message ||
          'MASTER_DATA updated successfully.',
      );
    } catch (err) {
      const text =
        err instanceof Error
          ? err.message
          : 'Unable to update MASTER_DATA.';

      setError(text);
    addNotification('error', text);
      setMessage(null);
    } finally {
      setUpdatingMasterData(false);
    }
  };

  const readNormalizationResponse = async (
    response: Response,
  ): Promise<NormalizationPreview> => {
    const text = await response.text();

    try {
      return JSON.parse(text) as NormalizationPreview;
    } catch {
      throw new Error(
        `Normalization request returned an invalid response (${response.status}).`,
      );
    }
  };

  const previewPredictionNormalization = async () => {
    setNormalizingPredictionDates(true);
    setError(null);
    setNormalizationPreview(null);

    try {
      const response = await fetch(
        '/api/normalization/preview',
        {
          method: 'POST',
          headers: { Accept: 'application/json' },
        },
      );

      const payload =
        await readNormalizationResponse(response);

      if (!response.ok) {
        throw new Error(
          payload.message ||
            `Normalization preview failed (${response.status}).`,
        );
      }

      setNormalizationPreview(payload);
    } catch (err) {
      const text = err instanceof Error
        ? err.message
        : 'Unable to preview prediction normalization.';
      setError(text);
      addNotification('error', text);
    } finally {
      setNormalizingPredictionDates(false);
    }
  };

  const applyPredictionNormalization = async () => {
    setNormalizingPredictionDates(true);
    setError(null);
    setShowNormalizationConfirmation(false);

    try {
      const response = await fetch(
        '/api/normalization/apply',
        {
          method: 'POST',
          headers: { Accept: 'application/json' },
        },
      );

      const payload =
        await readNormalizationResponse(response);

      if (!response.ok) {
        throw new Error(
          payload.message ||
            `Normalization apply failed (${response.status}).`,
        );
      }

      setNormalizationPreview(payload);
      setMessage(
        `Normalization completed: ${payload.safe_normalization_candidates ?? 0} aligned.`,
      );
      addNotification(
        'success',
        'Prediction-date normalization completed without modifying MASTER_DATA.',
      );
    } catch (err) {
      const text = err instanceof Error
        ? err.message
        : 'Unable to apply prediction normalization.';
      setError(text);
      addNotification('error', text);
    } finally {
      setNormalizingPredictionDates(false);
    }
  };

  const runDailyCycle = async () => {
    if (!selectedGame || !dailyCycleTargetDate) return;
    setRunningDailyCycle(true);
    setShowDailyCycleConfirmation(false);
    setDailyCycleResult({ status: 'running', stages: { preflight: { status: 'success' }, prediction_engines: { status: 'running' }, theresa: { status: 'not_run' }, theresa_intelligence: { status: 'not_run' }, refresh: { status: 'not_run' } } });
    try {
      const response = await fetch('/api/daily-cycle/run', { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify({ game: selectedGame, target_draw_date: dailyCycleTargetDate, run_mode: dailyCycleMode }) });
      const payload = await readNormalizationResponse(response) as DailyCycleResponse;
      setDailyCycleResult(payload);
      if (!response.ok || payload.status !== 'success') throw new Error(payload.message || `Daily Cycle failed (${response.status}).`);
      window.dispatchEvent(new CustomEvent(PREDICTION_EVENT, { detail: payload }));
      window.dispatchEvent(new CustomEvent('theresa:run-complete', { detail: payload }));
      window.dispatchEvent(new CustomEvent('theresa:intelligence-complete', { detail: payload }));
      addNotification('success', `Daily Cycle completed for ${selectedGame}.`);
    } catch (err) {
      const text = err instanceof Error ? err.message : 'Unable to run Daily Cycle.';
      setError(text);
      addNotification('error', text);
    } finally {
      setRunningDailyCycle(false);
    }
  };

  const manualReviewDecisions =
    (normalizationPreview?.decisions ?? []).filter(
      decision => decision.decision === 'manual_review',
    );

  const reviewReasons = Object.entries(
    manualReviewDecisions.reduce<Record<string, number>>(
      (counts, decision) => {
        const reason = decision.reason ?? 'unknown_reason';
        counts[reason] = (counts[reason] ?? 0) + 1;
        return counts;
      },
      {},
    ),
  );

  const reviewByEngine = Object.entries(
    manualReviewDecisions.reduce<Record<string, number>>(
      (counts, decision) => {
        const engine = decision.engine ?? 'Unknown';
        counts[engine] = (counts[engine] ?? 0) + 1;
        return counts;
      },
      {},
    ),
  );

  /* =========================================================
    ADD OFFICIAL DRAW
    ========================================================= */

  const addOfficialDraw = async () => {
    const game =
      drawGame.trim();

    const date =
      drawDate.trim();

    const numbers =
      drawNumbers.map(Number);

    if (!game) {
      setError(
        'Choose a game.',
      );
      return;
    }

    if (!date) {
      setError(
        'Enter the official draw date.',
      );
      return;
    }

    if (
      numbers.length !== 5 ||
      numbers.some(
        number =>
          !Number.isInteger(number),
      )
    ) {
      setError(
        'Enter exactly five valid draw numbers.',
      );
      return;
    }

    setUpdatingMasterData(true);
    setError(null);

    setMessage(
      `Adding official draw for ${game}...`,
    );

    try {
      const response = await fetch(
        '/api/master-data/add-draw',
        {
          method: 'POST',

          headers: {
            'Content-Type':
              'application/json',
            Accept: 'application/json',
          },

          body: JSON.stringify({
            game,
            date,
            numbers,
          }),
        },
      );

      const payload =
        (await response.json()) as ApiResponse;

      if (!response.ok) {
        throw new Error(
          payload.message ||
            `Unable to add draw (${response.status}).`,
        );
      }

      if (
        payload.status &&
        payload.status !== 'success'
      ) {
        throw new Error(
          payload.message ||
            'Unable to add official draw.',
        );
      }

      markMasterDataConnected(
        payload,
      );

      setMessage(
        payload.message ||
          'Official draw added successfully.',
      );

      setShowMasterDataDialog(false);
      setDrawDate('');
      setDrawNumbers(
        ['', '', '', '', ''],
      );
    } catch (err) {
      const text =
        err instanceof Error
          ? err.message
          : 'Unable to add official draw.';

      setError(text);
    addNotification('error', text);
      setMessage(null);
    } finally {
      setUpdatingMasterData(false);
    }
  };

  /* =========================================================
    RUN PREDICTION ENGINES
    ========================================================= */

  const runPredictionEngines = async () => {
    const game =
      selectedGame.trim();

    if (!game) {
      setError(
        'Choose a game before continuing.',
      );
      return;
    }

    /*
     Close the selector immediately once the selected game is accepted.
    */
    setShowPredictionDialog(false);
    setRunningPredictions(true);
    setError(null);

    setMessage(
      `Running prediction engines for ${game}...`,
    );
    addNotification(
      'info',
      `Running prediction engines for ${game}...`,
    );

    try {
      const response = await fetch(
        '/api/prediction-engines/run',
        {
          method: 'POST',

          headers: {
            'Content-Type':
              'application/json',
            Accept: 'application/json',
          },

          body: JSON.stringify({
            game,
          }),
        },
      );

      const payload =
        (await response.json()) as ApiResponse;

      const hasResults =
        Array.isArray(payload.results);

      if (hasResults) {
        window.dispatchEvent(
          new CustomEvent(
            PREDICTION_EVENT,
            {
              detail: payload,
            },
          ),
        );
      }

      if (!response.ok || payload.status !== 'success') {
        const text =
          payload.message ||
          `Prediction request failed (${response.status}).`;

        setError(text);
        setMessage(null);
        addNotification(
          payload.status === 'partial_failure'
            ? 'warning'
            : 'error',
          text,
        );
        return;
      }

      localStorage.setItem(
        PREDICTION_STORAGE_KEY,
        JSON.stringify(payload),
      );

      setMessage(
        payload.message ||
          'Prediction engines completed successfully.',
      );
      addNotification(
        'success',
        payload.message ||
          `Prediction engines completed for ${game}.`,
      );

    } catch (err) {
      const text =
        err instanceof Error
          ? err.message
          : 'Unable to run prediction engines.';

      setError(text);
    addNotification('error', text);
      setMessage(null);
    } finally {
      setRunningPredictions(false);
    }
  };

  /* =========================================================
    RUN THERESA
    ========================================================= */

  const runTheresa = async () => {
    const game =
      selectedGame.trim();

    if (!game) {
      setError(
        'Choose a game before running Theresa.',
      );

      setShowPredictionDialog(true);
      return;
    }

    setRunningTheresa(true);
    setError(null);
    setShowTheresaDialog(false);

    setMessage(
      `Running Theresa for ${game}...`,
    );
    addNotification(
      'info',
      `Running Theresa for ${game}...`,
    );

    try {
      const response = await fetch(
        '/api/theresa/run',
        {
          method: 'POST',

          headers: {
            'Content-Type':
              'application/json',
            Accept: 'application/json',
          },

          body: JSON.stringify({
            game,
          }),
        },
      );

      const payload =
        (await response.json()) as ApiResponse;

      if (!response.ok) {
        throw new Error(
          payload.message ||
            `Theresa request failed (${response.status}).`,
        );
      }

      if (
        payload.status &&
        payload.status !== 'success'
      ) {
        throw new Error(
          payload.message ||
            'Theresa did not complete successfully.',
        );
      }

      localStorage.setItem(
        'theresa:lastTheresaRun',
        JSON.stringify(payload),
      );

      window.dispatchEvent(
        new CustomEvent(
          'theresa:run-complete',
          {
            detail: payload,
          },
        ),
      );

      setMessage(
        payload.message ||
          'Theresa completed successfully.',
      );
      addNotification(
        'success',
        payload.message ||
          `Theresa completed for ${game}.`,
      );
    } catch (err) {
      const text =
        err instanceof Error
          ? err.message
          : 'Unable to run Theresa.';

      setError(text);
    addNotification('error', text);
      setMessage(null);
    } finally {
      setRunningTheresa(false);
    }
  };

  const runTheresaIntelligence = async () => {
    const game = selectedGame.trim();
    if (!game) {
      setError('Choose a game before running Theresa Intelligence.');
      return;
    }

    setRunningTheresaIntelligence(true);
    setError(null);
    setShowTheresaIntelligenceDialog(false);
    setMessage(`Running Theresa Intelligence for ${game}...`);

    try {
      const response = await fetch(
        '/api/theresa-intelligence/run',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json',
          },
          body: JSON.stringify({ game }),
        },
      );
      const payload = (await response.json()) as ApiResponse;
      if (!response.ok || payload.status !== 'success') {
        throw new Error(
          payload.message ||
            `Theresa Intelligence request failed (${response.status}).`,
        );
      }
      window.dispatchEvent(
        new CustomEvent('theresa:intelligence-complete', {
          detail: payload,
        }),
      );
      setMessage(`Theresa Intelligence completed for ${game}.`);
      addNotification('success', `Theresa Intelligence completed for ${game}.`);
    } catch (err) {
      const text = err instanceof Error
        ? err.message
        : 'Unable to run Theresa Intelligence.';
      setError(text);
      setMessage(null);
      addNotification('error', text);
    } finally {
      setRunningTheresaIntelligence(false);
    }
  };

  /* =========================================================
    DRAW NUMBER INPUT
    ========================================================= */

  const updateDrawNumber = (
    index: number,
    value: string,
  ) => {
    const next =
      [...drawNumbers];

    next[index] =
      value.replace(/\D/g, '');

    setDrawNumbers(next);
  };

  /* =========================================================
    RENDER
    ========================================================= */

  return (
    <>
      <div className="bottom-action-bar">

        {/* MASTER_DATA */}

        <button
          type="button"
          className="action-btn"
          disabled={updatingMasterData}
          onClick={() => {
            setError(null);
            setMessage(null);
            setShowMasterDataDialog(true);
          }}
        >
          <span className="action-icon">
            ðŸ“Š
          </span>

          <span className="action-copy">
            <span className="action-label">
              {updatingMasterData
                ? 'Updating MASTER_DATA...'
                : 'Update MASTER_DATA'}
            </span>

            <span className="action-subtitle">
              Add official draw
            </span>
          </span>
        </button>

        <button
          type="button"
          className="action-btn"
          disabled={runningTheresaIntelligence}
          onClick={() => {
            setError(null);
            setMessage(null);
            setShowTheresaIntelligenceDialog(true);
          }}
        >
          <span className="action-copy">
            <span className="action-label">
              {runningTheresaIntelligence
                ? 'Running Intelligence...'
                : 'Run Theresa Intelligence'}
            </span>
            <span className="action-subtitle">
              Historical Intelligence / Tier 2
            </span>
          </span>
        </button>

        {/* PREDICTION ENGINES */}

        <button
          type="button"
          className="action-btn action-btn--primary"
          disabled={runningPredictions}
          onClick={() => {
            setError(null);
            setMessage(null);
            setShowPredictionDialog(true);
          }}
        >
          <span className="action-icon">
            ðŸ”®
          </span>

          <span className="action-copy">
            <span className="action-label">
              {runningPredictions
                ? 'Running Engines...'
                : 'Run Prediction Engines'}
            </span>

            <span className="action-subtitle">
              Primary prediction action
            </span>
          </span>
        </button>

        {/* THERESA */}

        <button
          type="button"
          className="action-btn"
          disabled={runningTheresa}
          onClick={() => {
            setError(null);
            setMessage(null);
            setShowTheresaDialog(true);
          }}
        >
          <span className="action-icon">
            ðŸ¤–
          </span>

          <span className="action-copy">
            <span className="action-label">
              {runningTheresa
                ? 'Running Theresa...'
                : 'Run Theresa'}
            </span>

            <span className="action-subtitle">
              Tier 1 prediction
            </span>
          </span>
        </button>

        <button
          type="button"
          className="action-btn"
          disabled={normalizingPredictionDates}
          onClick={() => {
            setError(null);
            setMessage(null);
            setShowNormalizationDialog(true);
            void previewPredictionNormalization();
          }}
        >
          <span className="action-copy">
            <span className="action-label">
              {normalizingPredictionDates
                ? 'Checking Prediction Dates...'
                : 'Normalize Prediction Dates'}
            </span>

            <span className="action-subtitle">
              Preview against MASTER_DATA
            </span>
          </span>
        </button>

        {/* DAILY CYCLE */}

        <button
          type="button"
          className="action-btn"
          disabled={!dailyCycleReady || runningDailyCycle}
          title={dailyCycleReady ? 'Run all operational stages in order.' : 'Daily Cycle backend is unavailable.'}
          onClick={() => {
            setError(null);
            setDailyCycleResult(null);
            setDailyCycleTargetDate(new Date().toISOString().slice(0, 10));
            setShowDailyCycleDialog(true);
          }}
        >
          <span className="action-icon">
            âš¡
          </span>

          <span className="action-copy">
            <span className="action-label">
              {runningDailyCycle ? 'Daily Cycle Running...' : 'Run Daily Cycle'}
            </span>

            <span className="action-subtitle">
              {dailyCycleReady ? 'Kadija, Desmond, Theresa, Intelligence' : 'Backend unavailable'}
            </span>
          </span>
        </button>
      </div>

      {/* =====================================================
          MASTER_DATA MODAL
          ===================================================== */}

      {showMasterDataDialog && (
        <div className="master-data-overlay">
          <div className="master-data-modal">

            <div className="master-data-header">
              <div>
                <h2>
                  Update MASTER_DATA
                </h2>

                <p>
                  Add an official draw or normalize
                  the existing MASTER_DATA.
                </p>
              </div>

              <button
                type="button"
                className="master-data-close"
                disabled={updatingMasterData}
                onClick={() =>
                  setShowMasterDataDialog(false)
                }
              >
                Ã—
              </button>
            </div>

            <div className="master-data-field">
              <label>
                Game
              </label>

              <select
                value={drawGame}
                disabled={
                  loadingGames ||
                  updatingMasterData
                }
                onChange={event =>
                  setDrawGame(
                    event.target.value,
                  )
                }
              >
                <option value="">
                  Choose game
                </option>

                {games.map(game => (
                  <option
                    key={`${game.game_id ?? ''}-${game.game}`}
                    value={game.game}
                  >
                    {game.game}
                  </option>
                ))}
              </select>
            </div>

            <div className="master-data-field">
              <label>
                Draw date
              </label>

              <input
                type="date"
                value={drawDate}
                disabled={updatingMasterData}
                onChange={event =>
                  setDrawDate(
                    event.target.value,
                  )
                }
              />
            </div>

            <div className="master-data-field">
              <label>
                Five official numbers
              </label>

              <div className="master-number-grid">
                {drawNumbers.map(
                  (number, index) => (
                    <input
                      key={index}
                      type="text"
                      inputMode="numeric"
                      maxLength={2}
                      value={number}
                      disabled={updatingMasterData}
                      onChange={event =>
                        updateDrawNumber(
                          index,
                          event.target.value,
                        )
                      }
                    />
                  ),
                )}
              </div>

              <small>
                Enter exactly five official draw numbers.
              </small>
            </div>

            {error && (
              <div className="master-data-warning">
                {error}
              </div>
            )}

            <div className="master-data-actions">

              <button
                type="button"
                className="master-secondary-btn"
                disabled={updatingMasterData}
                onClick={() =>
                  setShowMasterDataDialog(false)
                }
              >
                Cancel
              </button>

              <button
                type="button"
                className="master-secondary-btn"
                disabled={updatingMasterData}
                onClick={() =>
                  void normalizeMasterData()
                }
              >
                Normalize Only
              </button>

              <button
                type="button"
                className="master-primary-btn"
                disabled={
                  updatingMasterData ||
                  !drawGame ||
                  !drawDate ||
                  drawNumbers.some(
                    value =>
                      value.trim() === '',
                  )
                }
                onClick={() =>
                  void addOfficialDraw()
                }
              >
                {updatingMasterData
                  ? 'Updating...'
                  : 'Add Draw'}
              </button>

            </div>
          </div>
        </div>
      )}

      {/* =====================================================
          GAME SELECTOR MODAL
          ===================================================== */}

      {showPredictionDialog && (
        <div className="game-selector-overlay">
          <div className="game-selector-modal">

            <h2>
              Run Prediction Engines
            </h2>

            <p>
              Choose the game before continuing.
            </p>

            <select
              value={selectedGame}
              disabled={
                loadingGames ||
                runningPredictions
              }
              onChange={event =>
                setSelectedGame(
                  event.target.value,
                )
              }
            >
              <option value="">
                Choose game
              </option>

              {games.map(game => (
                <option
                  key={`${game.game_id ?? ''}-${game.game}`}
                  value={game.game}
                >
                  {game.game}
                </option>
              ))}
            </select>

            {error && (
              <div className="master-data-warning">
                {error}
              </div>
            )}

            <div className="game-selector-actions">

              <button
                type="button"
                className="master-secondary-btn"
                disabled={runningPredictions}
                onClick={() =>
                  setShowPredictionDialog(false)
                }
              >
                Cancel
              </button>

              <button
                type="button"
                className="master-primary-btn"
                disabled={
                  runningPredictions ||
                  !selectedGame
                }
                onClick={() =>
                  void runPredictionEngines()
                }
              >
                {runningPredictions
                  ? 'Running...'
                  : 'Run Engines'}
              </button>

            </div>
          </div>
        </div>
      )}

      {showTheresaDialog && (
        <div className="game-selector-overlay">
          <div className="game-selector-modal">
            <h2>Run Theresa</h2>
            <p>Choose the canonical game for the Theresa Tier 1 run.</p>

            <select
              value={selectedGame}
              disabled={loadingGames || runningTheresa}
              onChange={event => setSelectedGame(event.target.value)}
            >
              <option value="">Choose game</option>
              {games.map(game => (
                <option
                  key={`theresa-${game.game_id ?? ''}-${game.game}`}
                  value={game.game}
                >
                  {game.game}
                </option>
              ))}
            </select>

            {error && (
              <div className="master-data-warning">{error}</div>
            )}

            <div className="game-selector-actions">
              <button
                type="button"
                className="master-secondary-btn"
                disabled={runningTheresa}
                onClick={() => setShowTheresaDialog(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="master-primary-btn"
                disabled={runningTheresa || !selectedGame}
                onClick={() => void runTheresa()}
              >
                {runningTheresa ? 'Running...' : 'Run Theresa'}
              </button>
            </div>
          </div>
        </div>
      )}

      {showTheresaIntelligenceDialog && (
        <div className="game-selector-overlay">
          <div className="game-selector-modal">
            <h2>Run Theresa Intelligence</h2>
            <p>Choose the canonical game for the Theresa Research Platform run.</p>
            <select
              value={selectedGame}
              disabled={loadingGames || runningTheresaIntelligence}
              onChange={event => setSelectedGame(event.target.value)}
            >
              <option value="">Choose game</option>
              {games.map(game => (
                <option
                  key={`theresa-intelligence-${game.game_id ?? ''}-${game.game}`}
                  value={game.game}
                >
                  {game.game}
                </option>
              ))}
            </select>
            <div className="game-selector-actions">
              <button
                type="button"
                className="master-secondary-btn"
                disabled={runningTheresaIntelligence}
                onClick={() => setShowTheresaIntelligenceDialog(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="master-primary-btn"
                disabled={runningTheresaIntelligence || !selectedGame}
                onClick={() => void runTheresaIntelligence()}
              >
                {runningTheresaIntelligence ? 'Running...' : 'Run Intelligence'}
              </button>
            </div>
          </div>
        </div>
      )}

      {showNormalizationDialog && (
        <div className="game-selector-overlay">
          <div className="normalization-report-modal">
            <header className="normalization-report-header">
              <div>
                <p className="normalization-report-eyebrow">Operational report</p>
                <h2>MASTER_DATA Normalization Preview</h2>
                <p className="normalization-report-status">
                  {normalizationPreview?.mode === 'apply'
                    ? 'Normalization Completed'
                    : 'Preview Complete - No Changes Applied'}
                </p>
              </div>
              <button type="button" className="normalization-report-close" aria-label="Close normalization preview" onClick={() => setShowNormalizationDialog(false)}>X</button>
            </header>

            {normalizingPredictionDates && (
              <div className="normalization-loading">Scanning saved prediction exports...</div>
            )}

            {normalizationPreview && (
              <div className="normalization-report-body">
                <section className="normalization-section">
                  <h3>Summary</h3>
                  <div className="normalization-summary-grid">
                    {[
                      ['Prediction artifacts scanned', normalizationPreview.artifacts_scanned], ['Ordinary engines discovered', normalizationPreview.ordinary_engine_folders_discovered],
                      ['Theresa artifacts', normalizationPreview.theresa?.artifacts_scanned], ['Logical prediction slots', normalizationPreview.logical_prediction_slots],
                      ['Safe to Normalize', normalizationPreview.safe_normalization_candidates], ['Already aligned', normalizationPreview.already_aligned],
                      ['Already processed', normalizationPreview.already_processed], ['Needs Manual Review', normalizationPreview.manual_review],
                      ['Original Manual Review', normalizationPreview.original_manual_review], ['Resolved by extended evidence', normalizationPreview.resolved_by_extended_evidence],
                      ['Unmatched', normalizationPreview.unmatched], ['MASTER_DATA changes', 0],
                    ].map(([label, value]) => <div className="normalization-summary-item" key={String(label)}><span>{label}</span><strong>{value ?? 0}</strong></div>)}
                  </div>
                </section>

                <section className="normalization-section">
                  <h3>Ordinary Prediction Engines</h3>
                  <div className="normalization-table-wrap"><table className="normalization-table"><thead><tr><th>Engine</th><th>Files Found</th><th>Predictions Kept</th><th>Older Runs</th><th>Manual Review</th></tr></thead><tbody>{Object.entries(normalizationPreview.engine_summaries ?? {}).map(([engine, summary]) => <tr key={engine}><td>{displayEngineName(engine)}</td><td>{summary.artifacts_scanned ?? 0}</td><td>{summary.canonical_predictions ?? 0}</td><td>{summary.superseded_proposed ?? 0}</td><td>{summary.manual_review ?? 0}</td></tr>)}</tbody></table></div>
                </section>

                <section className="normalization-section normalization-theresa-section">
                  <h3>Theresa</h3>
                  <div className="normalization-summary-grid">
                    {[
                      ['Artifacts found', normalizationPreview.theresa?.artifacts_scanned], ['Predictions to keep', normalizationPreview.theresa?.canonical_predictions],
                      ['Older predictions', normalizationPreview.theresa?.superseded_proposed], ['Exact duplicates', normalizationPreview.theresa?.true_duplicates],
                      ['Safe date corrections', normalizationPreview.theresa?.date_corrections_proposed], ['Needs manual review', normalizationPreview.theresa?.manual_review],
                    ].map(([label, value]) => <div className="normalization-summary-item" key={String(label)}><span>{label}</span><strong>{value ?? 0}</strong></div>)}
                  </div>
                </section>

                <section className="normalization-section">
                  <h3>Repeated Predictions</h3>
                  <p>When an engine produced more than one prediction for the same game and official draw, the latest reliable run is retained. Earlier runs are treated as older predictions for archive.</p>
                  <div className="normalization-summary-grid">
                    <div className="normalization-summary-item"><span>Repeated-run groups</span><strong>{normalizationPreview.repeated_run_groups ?? 0}</strong></div>
                    <div className="normalization-summary-item"><span>Predictions to keep</span><strong>{normalizationPreview.canonical_predictions ?? 0}</strong></div>
                    <div className="normalization-summary-item"><span>Older predictions proposed for archive</span><strong>{normalizationPreview.superseded_runs_proposed ?? 0}</strong></div>
                    <div className="normalization-summary-item"><span>Exact duplicate copies</span><strong>{normalizationPreview.true_duplicate_copies ?? 0}</strong></div>
                  </div>
                </section>

                <section className="normalization-section normalization-review-section">
                  <h3>Needs Manual Review <span>{normalizationPreview.manual_review ?? manualReviewDecisions.length}</span></h3>
                  <p>Original Manual Review: {normalizationPreview.original_manual_review ?? manualReviewDecisions.length}. Resolved by extended evidence: {normalizationPreview.resolved_by_extended_evidence ?? 0}. Still needs review: {normalizationPreview.manual_review ?? manualReviewDecisions.length}.</p>
                  {Object.entries(normalizationPreview.resolution_methods ?? {}).some(([, count]) => count > 0) && <div className="normalization-resolution-methods"><h4>Resolved by Extended Evidence</h4>{Object.entries(normalizationPreview.resolution_methods ?? {}).filter(([, count]) => count > 0).map(([method, count]) => <div key={method}><strong>{reviewReasonCopy[method]?.label ?? method}</strong><span>{count}</span><p>{reviewReasonCopy[method]?.meaning}</p></div>)}</div>}
                  {reviewReasons.length === 0 ? <p>No records currently need manual review.</p> : <>
                    <div className="normalization-table-wrap"><table className="normalization-table"><thead><tr><th>Reason</th><th>Number</th><th>Meaning</th></tr></thead><tbody>{reviewReasons.map(([reason, count]) => {
                      const copy = reviewReasonCopy[reason] ?? { label: 'Review required', meaning: 'This record could not be normalized safely.' };
                      return <tr key={reason}><td><strong>{copy.label}</strong><small>{reason}</small></td><td>{count}</td><td>{copy.meaning}</td></tr>;
                    })}</tbody></table></div>
                    <div className="normalization-engine-review">{reviewByEngine.map(([engine, count]) => <span key={engine}>{displayEngineName(engine)}: <strong>{count}</strong></span>)}</div>
                    <button type="button" className="normalization-details-toggle" onClick={() => setShowManualReviewDetails(value => !value)}>{showManualReviewDetails ? 'Hide Manual Review Details' : 'View Manual Review Details'}</button>
                    {showManualReviewDetails && <div className="normalization-table-wrap"><table className="normalization-table"><thead><tr><th>Engine</th><th>Game</th><th>Run time</th><th>Proposed draw</th><th>Delay</th><th>Reason</th><th>Artifact</th></tr></thead><tbody>{manualReviewDecisions.map(decision => <tr key={decision.artifact_id}><td>{displayEngineName(decision.engine ?? 'Unknown')}</td><td>{decision.canonical_game ?? '-'}</td><td>{decision.original_run_timestamp ?? '-'}</td><td>{decision.target_draw_date ?? '-'}</td><td>{decision.delay_days ?? '-'}</td><td>{reviewReasonCopy[decision.reason ?? '']?.label ?? decision.reason ?? '-'}</td><td className="normalization-artifact-path">{decision.artifact_path ?? '-'}</td></tr>)}</tbody></table></div>}
                  </>}
                </section>

                {normalizationPreview.mode === 'preview' && <section className="normalization-apply-summary">
                  <h3>What will happen if you Apply?</h3>
                  <ul><li>Safe prediction exports will be associated with their correct MASTER_DATA draw dates.</li><li>The latest reliable prediction for each engine, game, and draw will remain active.</li><li>Older or exact duplicate exports will move outside active Input Streams into the normalization archive.</li><li>The index, audit ledger, and checkpoint will be updated. Manual Review records will remain untouched.</li></ul>
                  <div className="normalization-safety-notice">MASTER_DATA WILL NOT BE MODIFIED.<br />PREDICTION NUMBERS WILL NOT BE MODIFIED.</div>
                  <p className="normalization-apply-counts">If applied now: {normalizationPreview.safe_normalization_candidates ?? 0} date corrections, {normalizationPreview.canonical_predictions ?? 0} predictions kept, {normalizationPreview.superseded_runs_proposed ?? 0} older predictions archived, {normalizationPreview.true_duplicate_copies ?? 0} duplicate copies archived, and {manualReviewDecisions.length} records left untouched.</p>
                </section>}
              </div>
            )}

            {error && (
              <div className="master-data-warning">{error}</div>
            )}

            <div className="normalization-report-actions">
              <button
                type="button"
                className="master-secondary-btn"
                disabled={normalizingPredictionDates}
                onClick={() => setShowNormalizationDialog(false)}
              >
                Close
              </button>
              <button
                type="button"
                className="master-secondary-btn"
                disabled={normalizingPredictionDates}
                onClick={() => void previewPredictionNormalization()}
              >
                Refresh Preview
              </button>
              <button
                type="button"
                className="master-primary-btn"
                disabled={
                  normalizingPredictionDates ||
                  !normalizationPreview ||
                  normalizationPreview.mode === 'apply' ||
                  (normalizationPreview.safe_normalization_candidates ?? 0) === 0
                }
                onClick={() => setShowNormalizationConfirmation(true)}
              >
                Apply Normalization
              </button>
            </div>
            {showNormalizationConfirmation && normalizationPreview && (
              <div className="normalization-confirmation" role="dialog" aria-modal="true"><div><h3>Confirm Historical Prediction Normalization</h3><p>This will normalize {normalizationPreview.safe_normalization_candidates ?? 0} safe date associations and archive {((normalizationPreview.superseded_runs_proposed ?? 0) + (normalizationPreview.true_duplicate_copies ?? 0))} older or exact duplicate exports. MASTER_DATA and prediction numbers will not be modified.</p><div><button type="button" className="master-secondary-btn" onClick={() => setShowNormalizationConfirmation(false)}>Cancel</button><button type="button" className="master-primary-btn" onClick={() => void applyPredictionNormalization()}>Confirm Apply</button></div></div></div>
            )}
          </div>
        </div>
      )}

      {showDailyCycleDialog && (
        <div className="game-selector-overlay">
          <div className="game-selector-modal">
            <h2>Run Daily Cycle</h2>
            <p>Runs Prediction Engines, Theresa Tier 1, then Theresa Intelligence. MASTER_DATA is read only.</p>
            <div className="master-data-field"><label>Game</label><select value={selectedGame} disabled={runningDailyCycle} onChange={event => setSelectedGame(event.target.value)}><option value="">Choose game</option>{games.map(game => <option key={`daily-${game.game}`} value={game.game}>{game.game}</option>)}</select></div>
            <div className="master-data-field"><label>Mode</label><select value={dailyCycleMode} disabled={runningDailyCycle} onChange={event => setDailyCycleMode(event.target.value as 'live' | 'backdated')}><option value="live">Live / Current Run</option><option value="backdated">Backdated / Missed Run</option></select></div>
            <div className="master-data-field"><label>Target draw date</label><input type="date" value={dailyCycleTargetDate} disabled={runningDailyCycle} onChange={event => setDailyCycleTargetDate(event.target.value)} /></div>
            {dailyCycleMode === 'backdated' && dailyCycleTargetDate && <div className="master-data-warning">Historical cutoff protection: Active. Target draw: {dailyCycleTargetDate}. Data visible through: {new Date(new Date(`${dailyCycleTargetDate}T00:00:00`).getTime() - 86400000).toLocaleDateString()}.</div>}
            {dailyCycleResult?.stages && <div className="master-data-warning">{Object.entries(dailyCycleResult.stages).map(([stage, result]) => <div key={stage}>{stage.replace(/_/g, ' ')}: {result.status}</div>)}</div>}
            {dailyCycleResult?.status === 'success' && <div className="master-data-warning">Daily Cycle Completed: {dailyCycleResult.context?.game} for {dailyCycleResult.context?.target_draw_date}.</div>}
            {error && <div className="master-data-warning">{error}</div>}
            <div className="game-selector-actions"><button type="button" className="master-secondary-btn" disabled={runningDailyCycle} onClick={() => setShowDailyCycleDialog(false)}>Close</button><button type="button" className="master-primary-btn" disabled={runningDailyCycle || !selectedGame || !dailyCycleTargetDate} onClick={() => setShowDailyCycleConfirmation(true)}>Continue</button></div>
            {showDailyCycleConfirmation && <div className="normalization-confirmation" role="dialog" aria-modal="true"><div><h3>Confirm Daily Cycle</h3><p>Game: {selectedGame}<br />Target draw date: {dailyCycleTargetDate}<br />Mode: {dailyCycleMode}</p><p>MASTER_DATA will not be updated. Each stage receives the same run context.</p><div><button type="button" className="master-secondary-btn" onClick={() => setShowDailyCycleConfirmation(false)}>Cancel</button><button type="button" className="master-primary-btn" onClick={() => void runDailyCycle()}>Run Daily Cycle</button></div></div></div>}
          </div>
        </div>
      )}

      {/* =====================================================
          STATUS MESSAGE
          ===================================================== */}

      {message && (
        <div className="bottom-action-message">
          {message}
        </div>
      )}

      {error &&
        !showMasterDataDialog &&
        !showPredictionDialog && (
          <div className="bottom-action-error">
            {error}
          </div>
        )}
    </>
  );
};

export default BottomActionBar;

