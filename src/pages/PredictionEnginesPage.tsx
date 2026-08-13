// src/pages/PredictionEnginesPage.tsx

import React, { useEffect, useMemo, useState } from 'react';

/* ============================================================
  TYPES
  ============================================================ */

type PredictionData = {
  banker?: number | string | null;
  confidence?: number | null;

  top2?: Array<number | string>;
  top5?: Array<number | string>;
  top10?: Array<number | string>;
  top20?: Array<number | string>;
  top30?: Array<number | string>;
  top60?: Array<number | string>;

  [key: string]: unknown;
};

type EngineResult = {
  engine?: string;
  status?: string;
  return_code?: number;

  prediction?: PredictionData | null;
  prediction_artifact?: string | null;

  stdout?: string;
  stderr?: string;

  [key: string]: unknown;
};

type PredictionRunResponse = {
  status?: string;
  message?: string;

  game?: string;
  game_id?: number | string;

  results?: EngineResult[];
};

type GameOption = {
  id?: number | string;
  name: string;
};

/* ============================================================
  HELPERS
  ============================================================ */

const formatNumbers = (
  values?: Array<number | string>,
): string => {
  if (!Array.isArray(values) || values.length === 0) {
    return '—';
  }

  return values.join(', ');
};

const formatBanker = (
  value?: number | string | null,
): string => {
  if (
    value === undefined ||
    value === null ||
    value === ''
  ) {
    return '—';
  }

  return String(value);
};

const formatConfidence = (
  value?: number | null,
): string => {
  if (
    value === undefined ||
    value === null ||
    Number.isNaN(value)
  ) {
    return '—';
  }

  /*
  * Backend currently returns confidence as a decimal,
  * e.g. 0.346154.
  *
  * Display as both percentage and raw value.
  */
  const percent = value * 100;

  return `${percent.toFixed(2)}%`;
};

const normalizeGame = (
  item: unknown,
): GameOption | null => {
  if (typeof item === 'string') {
    return {
      name: item,
    };
  }

  if (
    typeof item !== 'object' ||
    item === null
  ) {
    return null;
  }

  const candidate = item as Record<string, unknown>;

  const rawName =
    candidate.name ??
    candidate.game ??
    candidate.game_name ??
    candidate.label;

  if (
    typeof rawName !== 'string' ||
    rawName.trim() === ''
  ) {
    return null;
  }

  const rawId =
    candidate.id ??
    candidate.game_id ??
    candidate.value;

  return {
    name: rawName.trim(),
    id:
      typeof rawId === 'string' ||
      typeof rawId === 'number'
        ? rawId
        : undefined,
  };
};

/* ============================================================
  PAGE
  ============================================================ */

const PredictionEnginesPage: React.FC = () => {
  const [games, setGames] = useState<GameOption[]>([]);
  const [selectedGame, setSelectedGame] =
    useState<string>('');

  const [runData, setRunData] =
    useState<PredictionRunResponse | null>(null);
useEffect(() => {
  const storageKey =
    'theresa:lastPredictionEngineRun';

  const eventName =
    'theresa:prediction-engines-complete';

  const loadSavedResult = () => {
    const saved =
      localStorage.getItem(storageKey);

    if (!saved) {
      return;
    }

    try {
      const parsed =
        JSON.parse(saved) as PredictionRunResponse;

      setRunData(parsed);
    } catch (error) {
      console.error(
        'Unable to read saved prediction result:',
        error,
      );
    }
  };

  const handlePredictionComplete = (
    event: Event,
  ) => {
    const customEvent =
      event as CustomEvent<PredictionRunResponse>;

    if (customEvent.detail) {
      setRunData(
        customEvent.detail,
      );
    }
  };

  loadSavedResult();

  window.addEventListener(
    eventName,
    handlePredictionComplete,
  );

  return () => {
    window.removeEventListener(
      eventName,
      handlePredictionComplete,
    );
  };
}, []);

  const [loadingGames, setLoadingGames] =
    useState<boolean>(false);

  const [running, setRunning] =
    useState<boolean>(false);

  const [error, setError] =
    useState<string | null>(null);

  /* ==========================================================
    LOAD AVAILABLE GAMES
    ========================================================== */

  useEffect(() => {
    let cancelled = false;

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

        if (!response.ok) {
          throw new Error(
            `Could not load games (${response.status}).`,
          );
        }

        const payload: unknown =
          await response.json();

        let rawGames: unknown[] = [];

        if (Array.isArray(payload)) {
          rawGames = payload;
        } else if (
          typeof payload === 'object' &&
          payload !== null
        ) {
          const objectPayload =
            payload as Record<string, unknown>;

          if (Array.isArray(objectPayload.games)) {
            rawGames = objectPayload.games;
          } else if (
            Array.isArray(objectPayload.data)
          ) {
            rawGames = objectPayload.data;
          }
        }

        const normalized = rawGames
          .map(normalizeGame)
          .filter(
            (
              game,
            ): game is GameOption =>
              game !== null,
          );

        if (!cancelled) {
          setGames(normalized);

          if (
            normalized.length > 0
          ) {
            setSelectedGame(
              current =>
                current ||
                normalized[0].name,
            );
          }
        }
      } catch (err) {
        if (!cancelled) {
          console.error(
            'Unable to load prediction games:',
            err,
          );

          /*
          * Do not make the whole page unusable.
          * The user can still type/select a game
          * if the endpoint is temporarily unavailable.
          */
        }
      } finally {
        if (!cancelled) {
          setLoadingGames(false);
        }
      }
    };

    void loadGames();

    return () => {
      cancelled = true;
    };
  }, []);

  /* ==========================================================
    ENGINE RESULTS
    ========================================================== */

  const kadija = useMemo(() => {
    return (
      runData?.results?.find(
        result =>
          result.engine?.toLowerCase() ===
          'kadija',
      ) ?? null
    );
  }, [runData]);

  const desmond = useMemo(() => {
    return (
      runData?.results?.find(
        result =>
          result.engine?.toLowerCase() ===
          'desmond',
      ) ?? null
    );
  }, [runData]);

  const kadijaPrediction =
    kadija?.prediction ?? null;

  const desmondPrediction =
    desmond?.prediction ?? null;

  /* ==========================================================
    RUN ENGINES
    ========================================================== */

  const runPredictionEngines = async () => {
    const gameName =
      selectedGame.trim();

    if (!gameName) {
      setError(
        'Choose a game before running the prediction engines.',
      );

      return;
    }

    setRunning(true);
    setError(null);

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

          /*
          * Your Flask endpoint resolves the
          * game ID from the game name.
          */
          body: JSON.stringify({
            game: gameName,
          }),
        },
      );

      const payload =
        (await response.json()) as
          PredictionRunResponse;

      if (!response.ok) {
        throw new Error(
          payload.message ||
            `Prediction request failed (${response.status}).`,
        );
      }

      if (
        payload.status &&
        payload.status !== 'success'
      ) {
        throw new Error(
          payload.message ||
            'Prediction engines did not complete successfully.',
        );
      }

      setRunData(payload);
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : 'Unable to run prediction engines.';

      setError(message);
    } finally {
      setRunning(false);
    }
  };

  /* ==========================================================
    RENDER
    ========================================================== */

  return (
    <div className="prediction-engines-page">

      {/* ======================================================
          HEADER
          ====================================================== */}

      <section className="prediction-engines-header">
        <div>
          <p className="prediction-engines-eyebrow">
            PREDICTION ENGINES
          </p>

          <h1>
            Kadija &amp; Desmond
          </h1>

          <p>
            Independent engine outputs for
            separate performance evaluation.
          </p>
        </div>

        <span className="prediction-engines-status">
          {running
            ? 'Running'
            : runData
              ? 'Complete'
              : 'Ready'}
        </span>
      </section>

      {/* ======================================================
          RUN CONTROL
          ====================================================== */}

      <section className="prediction-engines-run-panel">
        <div>
          <strong>
            Run Prediction Engines
          </strong>

          <p>
            Choose the game to evaluate with
            both Kadija and Desmond.
          </p>
        </div>

        <div className="prediction-engines-run-controls">
          <select
            value={selectedGame}
            disabled={
              running ||
              loadingGames
            }
            onChange={event =>
              setSelectedGame(
                event.target.value,
              )
            }
          >
            <option value="">
              {loadingGames
                ? 'Loading games...'
                : 'Choose game'}
            </option>

            {games.map(game => (
              <option
                key={`${game.id ?? ''}-${game.name}`}
                value={game.name}
              >
                {game.name}
              </option>
            ))}
          </select>

          <button
            type="button"
            disabled={
              running ||
              !selectedGame
            }
            onClick={() =>
              void runPredictionEngines()
            }
          >
            {running
              ? 'Running...'
              : 'Run Prediction Engines'}
          </button>
        </div>
      </section>

      {/* ======================================================
          ERROR
          ====================================================== */}

      {error && (
        <section className="prediction-engines-error">
          <strong>
            Prediction run failed
          </strong>

          <p>{error}</p>
        </section>
      )}

      {/* ======================================================
          LAST RUN
          ====================================================== */}

      {runData && (
        <section className="prediction-engines-last-run">
          <strong>
            Last completed run
          </strong>

          <span>
            {runData.game || selectedGame}
            {runData.game_id !== undefined
              ? ` · Game ID ${runData.game_id}`
              : ''}
          </span>

          {runData.message && (
            <span>
              {runData.message}
            </span>
          )}
        </section>
      )}

      {/* ======================================================
          ENGINE CARDS
          ====================================================== */}

      <section className="prediction-engines-grid">

        {/* ====================================================
            KADIJA
            ==================================================== */}

        <article className="engine-output-card">
          <div className="engine-output-header">
            <div>
              <span className="engine-output-icon">
                ♟️
              </span>

              <div>
                <h2>Kadija</h2>
                <p>
                  Prediction Engine v4
                </p>
              </div>
            </div>

            <span className="engine-output-badge">
              Independent
            </span>
          </div>

          <div className="engine-output-state">
            <strong>
              {kadija?.status ===
              'success'
                ? 'Structured output available'
                : 'Engine ready'}
            </strong>

            <span>
              {kadijaPrediction
                ? 'Kadija prediction data was returned successfully by the engine API.'
                : 'Run the prediction engines to display Kadija output.'}
            </span>
          </div>

          <div className="engine-output-summary">
            <div>
              <span>Top 5</span>

              <strong>
                {formatNumbers(
                  kadijaPrediction?.top5,
                )}
              </strong>
            </div>

            <div>
              <span>Top 2</span>

              <strong>
                {formatNumbers(
                  kadijaPrediction?.top2,
                )}
              </strong>
            </div>

            <div>
              <span>Banker</span>

              <strong>
                {formatBanker(
                  kadijaPrediction?.banker,
                )}
              </strong>
            </div>

            <div>
              <span>
                Confidence
              </span>

              <strong>
                {formatConfidence(
                  kadijaPrediction?.confidence,
                )}
              </strong>
            </div>
          </div>

          {kadija?.prediction_artifact && (
            <div className="engine-output-artifact">
              <span>
                Prediction artifact
              </span>

              <code>
                {
                  kadija.prediction_artifact
                }
              </code>
            </div>
          )}
        </article>

        {/* ====================================================
            DESMOND
            ==================================================== */}

        <article className="engine-output-card engine-output-card--featured">
          <div className="engine-output-header">
            <div>
              <span className="engine-output-icon">
                🔮
              </span>

              <div>
                <h2>Desmond</h2>
                <p>
                  Prediction Engine v2
                </p>
              </div>
            </div>

            <span className="engine-output-badge">
              Independent
            </span>
          </div>

          <div className="engine-output-state">
            <strong>
              {desmond?.status ===
              'success'
                ? 'Structured output available'
                : 'Engine ready'}
            </strong>

            <span>
              {desmondPrediction
                ? 'Desmond prediction data was returned successfully by the engine API.'
                : 'Run the prediction engines to display Desmond output.'}
            </span>
          </div>

          <div className="engine-output-summary">
            <div>
              <span>Top 5</span>

              <strong>
                {formatNumbers(
                  desmondPrediction?.top5,
                )}
              </strong>
            </div>

            <div>
              <span>Top 2</span>

              <strong>
                {formatNumbers(
                  desmondPrediction?.top2,
                )}
              </strong>
            </div>

            <div>
              <span>Banker</span>

              <strong>
                {formatBanker(
                  desmondPrediction?.banker,
                )}
              </strong>
            </div>

            <div>
              <span>
                Confidence
              </span>

              <strong>
                {formatConfidence(
                  desmondPrediction?.confidence,
                )}
              </strong>
            </div>
          </div>

          {desmond?.prediction_artifact && (
            <div className="engine-output-artifact">
              <span>
                Prediction artifact
              </span>

              <code>
                {
                  desmond.prediction_artifact
                }
              </code>
            </div>
          )}
        </article>
      </section>

      {/* ======================================================
          KADIJA DETAIL
          ====================================================== */}

      {kadijaPrediction && (
        <section className="engine-detail-section">
          <div className="engine-detail-heading">
            <div>
              <span>KADIJA</span>

              <h2>
                Prediction Detail
              </h2>
            </div>
          </div>

          <article className="engine-detail-card">
            <h3>Top 5</h3>

            <span>
              {formatNumbers(
                kadijaPrediction.top5,
              )}
            </span>
          </article>

          <article className="engine-detail-card">
            <h3>Top 2</h3>

            <span>
              {formatNumbers(
                kadijaPrediction.top2,
              )}
            </span>
          </article>

          <article className="engine-detail-card">
            <h3>Banker</h3>

            <span>
              {formatBanker(
                kadijaPrediction.banker,
              )}
            </span>
          </article>

          <article className="engine-detail-card">
            <h3>Confidence</h3>

            <span>
              {formatConfidence(
                kadijaPrediction.confidence,
              )}
            </span>
          </article>
        </section>
      )}

      {/* ======================================================
          DESMOND EXTENDED OUTPUT
          ====================================================== */}

      <section className="engine-detail-section">
        <div className="engine-detail-heading">
          <div>
            <span>DESMOND</span>

            <h2>
              Extended Prediction Levels
            </h2>
          </div>
        </div>

        <article className="engine-detail-card">
          <h3>Top 10</h3>

          <span>
            {formatNumbers(
              desmondPrediction?.top10,
            )}
          </span>
        </article>

        <article className="engine-detail-card">
          <h3>Top 20</h3>

          <span>
            {formatNumbers(
              desmondPrediction?.top20,
            )}
          </span>
        </article>

        <article className="engine-detail-card">
          <h3>Top 30</h3>

          <span>
            {formatNumbers(
              desmondPrediction?.top30,
            )}
          </span>
        </article>

        <article className="engine-detail-card">
          <h3>Top 60</h3>

          <span>
            {formatNumbers(
              desmondPrediction?.top60,
            )}
          </span>
        </article>
      </section>

      {/* ======================================================
          ARCHITECTURE NOTE
          ====================================================== */}

      <section className="prediction-engines-note">
        <strong>
          No forced consensus.
        </strong>

        <p>
          Kadija and Desmond remain separate
          prediction sources. Theresa remains
          a separate intelligence layer, and
          future Theresa tiers can consume
          their outputs without replacing the
          independent engine results.
        </p>
      </section>
    </div>
  );
};

export default PredictionEnginesPage;