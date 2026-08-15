import React, {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';

type TheresaHealth = {
  status: string;
  engine_exists: boolean;
  engine_path: string;
  output_dir: string;
  output_dir_exists: boolean;
};

type TheresaPrediction = {
  game?: string;
  target_game?: string;
  generated_at?: string;
  timestamp?: string;
  banker?: number;
  confidence?: number;
  top60?: number[];
  top30?: number[];
  top20?: number[];
  top10?: number[];
  top5?: number[];
  top2?: number[];
  [key: string]: unknown;
};

const TheresaPage: React.FC = () => {
  const [health, setHealth] =
    useState<TheresaHealth | null>(null);

  const [prediction, setPrediction] =
    useState<TheresaPrediction | null>(null);

  const [loading, setLoading] =
    useState(true);

  const [refreshing, setRefreshing] =
    useState(false);

  const [error, setError] =
    useState('');

  const readJson = async <T,>(
    response: Response,
  ): Promise<T> => {
    const text =
      await response.text();

    if (!text.trim()) {
      throw new Error(
        `Empty response from ${response.url}`,
      );
    }

    try {
      return JSON.parse(text) as T;
    } catch {
      throw new Error(
        `Invalid JSON response from ${response.url}`,
      );
    }
  };

  const loadTheresa =
    useCallback(
      async (
        mode:
          | 'initial'
          | 'refresh' = 'initial',
      ) => {
        if (mode === 'initial') {
          setLoading(true);
        } else {
          setRefreshing(true);
        }

        setError('');

        try {
          const healthResponse =
            await fetch(
              '/api/theresa/health',
              {
                method: 'GET',
                headers: {
                  Accept:
                    'application/json',
                },
              },
            );

          if (
            !healthResponse.ok
          ) {
            throw new Error(
              `Theresa health check failed: HTTP ${healthResponse.status}`,
            );
          }

          const healthData =
            await readJson<TheresaHealth>(
              healthResponse,
            );

          setHealth(
            healthData,
          );

          const predictionResponse =
            await fetch(
              '/api/theresa/latest',
              {
                method: 'GET',
                headers: {
                  Accept:
                    'application/json',
                },
              },
            );

          if (
            predictionResponse.ok
          ) {
            const predictionData =
              await readJson<{
                prediction?:
                  TheresaPrediction | null;
              }>(
                predictionResponse,
              );

            setPrediction(
              predictionData.prediction ??
                null,
            );
          } else if (
            predictionResponse.status ===
            404
          ) {
            setPrediction(
              null,
            );
          } else {
            throw new Error(
              `Theresa prediction request failed: HTTP ${predictionResponse.status}`,
            );
          }
        } catch (err) {
          setError(
            err instanceof Error
              ? err.message
              : 'Unable to connect to Theresa.',
          );
        } finally {
          setLoading(false);
          setRefreshing(false);
        }
      },
      [],
    );

  useEffect(() => {
    void loadTheresa(
      'initial',
    );

    const handleTheresaComplete = () => {
      void loadTheresa('refresh');
    };

    window.addEventListener(
      'theresa:run-complete',
      handleTheresaComplete,
    );

    return () => {
      window.removeEventListener(
        'theresa:run-complete',
        handleTheresaComplete,
      );
    };
  }, [
    loadTheresa,
  ]);

  const isConnected =
    Boolean(
      health &&
        health.status === 'ok' &&
        health.engine_exists &&
        health.output_dir_exists,
    );

  const gameName =
    prediction?.game ??
    prediction?.target_game ??
    '—';

  const generatedAt =
    prediction?.generated_at ??
    prediction?.generated ??
    prediction?.timestamp ??
    '—';

  const confidenceText =
    useMemo(() => {
      if (
        prediction?.confidence ===
          undefined ||
        prediction?.confidence ===
          null
      ) {
        return '—';
      }

      const value =
        Number(
          prediction.confidence,
        );

      if (
        !Number.isFinite(
          value,
        )
      ) {
        return '—';
      }

      return value.toFixed(6);
    }, [
      prediction?.confidence,
    ]);

  const numberList = (
    values?: number[],
  ) => {
    if (
      !values ||
      values.length === 0
    ) {
      return (
        <span className="theresa-empty-value">
          —
        </span>
      );
    }

    return (
      <div className="theresa-number-list">
        {values.map(
          (
            value,
            index,
          ) => (
            <span
              key={`${value}-${index}`}
              className="theresa-number-chip"
            >
              {String(
                value,
              ).padStart(
                2,
                '0',
              )}
            </span>
          ),
        )}
      </div>
    );
  };

  return (
    <div className="theresa-page">
      {/* =====================================================
          HEADER
          ===================================================== */}

      <section className="theresa-page-header">
        <div>
          <p className="theresa-eyebrow">
            THERESA
          </p>

          <h1>
            Latest Prediction
          </h1>

          <p>
            Theresa Tier 1 output for the
            most recently completed run.
          </p>
        </div>

        <div className="theresa-header-actions">
          <span
            className={`theresa-connection-badge ${
              isConnected
                ? 'is-connected'
                : 'is-offline'
            }`}
          >
            {isConnected
              ? 'Connected'
              : 'Unavailable'}
          </span>

          <button
            type="button"
            className="theresa-refresh-btn"
            disabled={
              loading ||
              refreshing
            }
            onClick={() =>
              void loadTheresa(
                'refresh',
              )
            }
          >
            {refreshing
              ? 'Refreshing...'
              : 'Refresh'}
          </button>
        </div>
      </section>

      {/* =====================================================
          LOADING
          ===================================================== */}

      {loading && (
        <section className="theresa-state-card">
          <strong>
            Connecting to Theresa...
          </strong>

          <span>
            Loading engine status and
            latest prediction.
          </span>
        </section>
      )}

      {/* =====================================================
          ERROR
          ===================================================== */}

      {!loading &&
        error && (
          <section className="theresa-state-card theresa-state-card--error">
            <strong>
              Theresa connection failed
            </strong>

            <span>
              {error}
            </span>

            <button
              type="button"
              onClick={() =>
                void loadTheresa(
                  'refresh',
                )
              }
            >
              Retry
            </button>
          </section>
        )}

      {/* =====================================================
          MAIN CONTENT
          ===================================================== */}

      {!loading &&
        !error &&
        health && (
          <>
            {/* STATUS STRIP */}

            <section
              className="theresa-status-strip"
              aria-label="Theresa system status"
            >
              <div>
                <span>
                  Status
                </span>

                <strong>
                  {isConnected
                    ? 'Connected'
                    : 'Unavailable'}
                </strong>
              </div>

              <div>
                <span>
                  Engine
                </span>

                <strong>
                  {health.engine_exists
                    ? 'Ready'
                    : 'Not found'}
                </strong>
              </div>

              <div>
                <span>
                  Output system
                </span>

                <strong>
                  {health.output_dir_exists
                    ? 'Ready'
                    : 'Not found'}
                </strong>
              </div>

              <div>
                <span>
                  Tier
                </span>

                <strong>
                  Tier 1
                </strong>
              </div>
            </section>

            {!prediction ? (
              <section className="theresa-state-card">
                <strong>
                  No saved Theresa prediction
                </strong>

                <span>
                  Run Theresa for a selected
                  game and the latest result
                  will appear here.
                </span>
              </section>
            ) : (
              <>
                {/* META */}

                <section className="theresa-prediction-meta">
                  <div>
                    <span>
                      Game
                    </span>

                    <strong>
                      {String(
                        gameName,
                      )}
                    </strong>
                  </div>

                  <div>
                    <span>
                      Generated
                    </span>

                    <strong>
                      {String(
                        generatedAt,
                      )}
                    </strong>
                  </div>

                  <div>
                    <span>
                      Banker
                    </span>

                    <strong className="theresa-banker-value">
                      {prediction.banker ??
                        '—'}
                    </strong>
                  </div>

                  <div>
                    <span>
                      Confidence
                    </span>

                    <strong>
                      {confidenceText}
                    </strong>
                  </div>

                </section>

                {/* PRIMARY OUTPUT */}

                <section className="theresa-primary-grid">
                  <article className="theresa-prediction-card theresa-prediction-card--primary">
                    <div className="theresa-card-heading">
                      <div>
                        <span>
                          PRIMARY
                        </span>

                        <h2>
                          Top 5
                        </h2>
                      </div>
                    </div>

                    {numberList(
                      prediction.top5,
                    )}
                  </article>

                  <article className="theresa-prediction-card">
                    <div className="theresa-card-heading">
                      <div>
                        <span>
                          FOCUSED
                        </span>

                        <h2>
                          Top 2
                        </h2>
                      </div>
                    </div>

                    {numberList(
                      prediction.top2,
                    )}
                  </article>

                  <article className="theresa-prediction-card">
                    <div className="theresa-card-heading">
                      <div>
                        <span>
                          CORE
                        </span>

                        <h2>
                          Top 10
                        </h2>
                      </div>
                    </div>

                    {numberList(
                      prediction.top10,
                    )}
                  </article>
                </section>

                {/* EXTENDED OUTPUT */}

                <section className="theresa-extended-grid">
                  <article className="theresa-prediction-card">
                    <div className="theresa-card-heading">
                      <div>
                        <span>
                          EXTENDED
                        </span>

                        <h2>
                          Top 20
                        </h2>
                      </div>
                    </div>

                    {numberList(
                      prediction.top20,
                    )}
                  </article>

                  <article className="theresa-prediction-card">
                    <div className="theresa-card-heading">
                      <div>
                        <span>
                          EXTENDED
                        </span>

                        <h2>
                          Top 30
                        </h2>
                      </div>
                    </div>

                    {numberList(
                      prediction.top30,
                    )}
                  </article>
                </section>

                {/* FULL RANGE */}

                <section className="theresa-prediction-card theresa-prediction-card--full">
                  <div className="theresa-card-heading">
                    <div>
                      <span>
                        FULL RANGE
                      </span>

                      <h2>
                        Top 60
                      </h2>
                    </div>
                  </div>

                  {numberList(
                    prediction.top60,
                  )}
                </section>

              </>
            )}
          </>
        )}
    </div>
  );
};

export default TheresaPage;