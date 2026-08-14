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

  const [showMasterDataDialog, setShowMasterDataDialog] =
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

        {/* DAILY CYCLE */}

        <button
          type="button"
          className="action-btn"
          disabled
          title="Daily-cycle backend route is not connected yet."
        >
          <span className="action-icon">
            âš¡
          </span>

          <span className="action-copy">
            <span className="action-label">
              Run Daily Cycle
            </span>

            <span className="action-subtitle">
              Backend not connected
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

