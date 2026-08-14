// src/pages/PredictionEnginesPage.tsx

import React, { useEffect, useMemo, useState } from 'react';
import { useNotifications } from '../contexts/NotificationContext';

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
  message?: string;

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

const formatBanker = (
  value?: number | string | null,
): string => {
  if (
    value === undefined ||
    value === null ||
    value === ''
  ) {
    return 'Not returned';
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
    return 'Not returned';
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

type EnginePredictionPanelProps = {
  engineName: 'Kadija' | 'Desmond';
  version: string;
  icon: string;
  result: EngineResult | null;
};

const EnginePredictionPanel: React.FC<
  EnginePredictionPanelProps
> = ({ engineName, version, icon, result }) => {
  const prediction = result?.prediction ?? null;

  const numberList = (
    values?: Array<number | string>,
  ) => {
    if (!Array.isArray(values) || values.length === 0) {
      return (
        <span className="engine-prediction-not-returned">
          Not returned
        </span>
      );
    }

    return (
      <div className="theresa-number-list">
        {values.map((value, index) => (
          <span
            key={`${engineName}-${value}-${index}`}
            className="theresa-number-chip"
          >
            {String(value).padStart(2, '0')}
          </span>
        ))}
      </div>
    );
  };

  const predictionCard = (
    label: string,
    title: string,
    values?: Array<number | string>,
    primary = false,
  ) => (
    <article
      className={`theresa-prediction-card${
        primary ? ' theresa-prediction-card--primary' : ''
      }`}
    >
      <div className="theresa-card-heading">
        <span>{label}</span>
        <h3>{title}</h3>
      </div>
      {numberList(values)}
    </article>
  );

  return (
    <section className="engine-prediction-panel">
      <div className="engine-output-header">
        <div>
          <span className="engine-output-icon">{icon}</span>
          <div>
            <h2>{engineName}</h2>
            <p>Prediction Engine {version}</p>
          </div>
        </div>
        <span className="engine-output-badge">Independent</span>
      </div>

      <div className="engine-output-state">
        <strong>
          {result?.status === 'success'
            ? 'Structured output available'
            : result?.status === 'error'
              ? 'Engine output unavailable'
              : 'Engine ready'}
        </strong>
        <span>
          {prediction
            ? `${engineName} prediction data was returned by the engine API.`
            : result?.message ||
              `Run the prediction engines to display ${engineName} output.`}
        </span>
      </div>

      <div className="engine-prediction-meta">
        <div>
          <span>Banker</span>
          <strong>{formatBanker(prediction?.banker)}</strong>
        </div>
        <div>
          <span>Confidence</span>
          <strong>{formatConfidence(prediction?.confidence)}</strong>
        </div>
      </div>

      <div className="theresa-primary-grid">
        {predictionCard('PRIMARY', 'Top 5', prediction?.top5, true)}
        {predictionCard('FOCUSED', 'Top 2', prediction?.top2)}
        {predictionCard('CORE', 'Top 10', prediction?.top10)}
      </div>

      <div className="theresa-extended-grid">
        {predictionCard('EXTENDED', 'Top 20', prediction?.top20)}
        {predictionCard('EXTENDED', 'Top 30', prediction?.top30)}
      </div>

      {predictionCard('FULL RANGE', 'Top 60', prediction?.top60)}

      {result?.prediction_artifact && (
        <div className="engine-output-artifact">
          <span>Prediction artifact</span>
          <code>{result.prediction_artifact}</code>
        </div>
      )}
    </section>
  );
};

/* ============================================================
  PAGE
  ============================================================ */

const PredictionEnginesPage: React.FC = () => {
  const { addNotification } = useNotifications();
  const [games, setGames] = useState<GameOption[]>([]);
  const [selectedGame, setSelectedGame] =
    useState<string>('');

  const [runData, setRunData] =
    useState<PredictionRunResponse | null>(null);
  useEffect(() => {
  const eventName =
    'theresa:prediction-engines-complete';

  const loadLatestResult = async () => {
    try {
      const response = await fetch(
        '/api/prediction-engines/latest',
        {
          method: 'GET',
          headers: {
            Accept: 'application/json',
          },
        },
      );

      if (response.status === 404) {
        return;
      }

      const payload =
        (await response.json()) as PredictionRunResponse;

      if (!response.ok || payload.status !== 'success') {
        throw new Error(
          payload.message ||
            `Could not load latest prediction (${response.status}).`,
        );
      }

      setRunData(payload);
    } catch (error) {
      console.error(
        'Unable to load latest prediction result:',
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

  void loadLatestResult();

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
          const message =
            err instanceof Error
              ? err.message
              : 'Unable to load prediction games.';

          setError(message);
          addNotification('error', message);
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

      setRunData(payload);

      if (!response.ok || payload.status !== 'success') {
        const message =
          payload.message ||
          `Prediction request failed (${response.status}).`;

        setError(message);
        addNotification(
          payload.status === 'partial_failure'
            ? 'warning'
            : 'error',
          message,
        );
        return;
      }

      localStorage.setItem(
        'theresa:lastPredictionEngineRun',
        JSON.stringify(payload),
      );
      window.dispatchEvent(
        new CustomEvent(
          'theresa:prediction-engines-complete',
          { detail: payload },
        ),
      );
      addNotification(
        'success',
        payload.message ||
          `Prediction engines completed for ${gameName}.`,
      );
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

      <EnginePredictionPanel
        engineName="Kadija"
        version="v4"
        icon="♟️"
        result={kadija}
      />

      <EnginePredictionPanel
        engineName="Desmond"
        version="v2"
        icon="🔮"
        result={desmond}
      />

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