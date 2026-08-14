// src/components/layout/StatusBar.tsx

import React, { useEffect, useState } from 'react';

type ConnectionState =
  | 'checking'
  | 'connected'
  | 'not-connected';

const MASTER_DATA_STORAGE_KEY =
  'theresa:master-data-status';

const MASTER_DATA_EVENT =
  'theresa:master-data-updated';

const PREDICTION_EVENT =
  'theresa:prediction-engines-complete';

const StatusBar: React.FC = () => {
  const [masterDataStatus, setMasterDataStatus] =
    useState<ConnectionState>('checking');

  const [theresaStatus, setTheresaStatus] =
    useState<ConnectionState>('checking');

  const [
    predictionEnginesStatus,
    setPredictionEnginesStatus,
  ] = useState<ConnectionState>('checking');

  /* =========================================================
    MASTER_DATA
    ========================================================= */

  const checkMasterData = async () => {
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
          `MASTER_DATA health check failed (${response.status}).`,
        );
      }

      const payload = await response.json();

      if (
        payload?.status &&
        payload.status !== 'success'
      ) {
        throw new Error(
          payload.message ||
            'MASTER_DATA is unavailable.',
        );
      }

      setMasterDataStatus('connected');
    } catch (error) {
      console.error(
        'MASTER_DATA connection check failed:',
        error,
      );

      setMasterDataStatus(
        'not-connected',
      );
    }
  };

  /* =========================================================
    THERESA
    ========================================================= */

  const checkTheresa = async () => {
    try {
      const response = await fetch(
        '/api/theresa/health',
        {
          method: 'GET',
          headers: {
            Accept: 'application/json',
          },
        },
      );

      if (!response.ok) {
        throw new Error(
          `Theresa health check failed (${response.status}).`,
        );
      }

      const payload = await response.json();

      const connected =
        payload?.status === 'ok' &&
        payload?.engine_exists === true &&
        payload?.output_dir_exists === true;

      setTheresaStatus(
        connected
          ? 'connected'
          : 'not-connected',
      );
    } catch (error) {
      console.error(
        'Theresa connection check failed:',
        error,
      );

      setTheresaStatus(
        'not-connected',
      );
    }
  };

  /* =========================================================
    PREDICTION ENGINES
    ========================================================= */

  const checkPredictionEngines = async () => {
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
        setPredictionEnginesStatus('connected');
        return;
      }

      const payload = await response.json();

      const successful =
        response.ok &&
        payload?.status === 'success' &&
        Array.isArray(payload?.results) &&
        payload.results.length === 2 &&
        payload.results.every(
          (result: {
            status?: string;
            prediction?: {
              top5?: unknown[];
              top2?: unknown[];
              banker?: unknown;
              confidence?: unknown;
            };
          }) =>
            result.status === 'success' &&
            Array.isArray(result.prediction?.top5) &&
            result.prediction.top5.length > 0 &&
            Array.isArray(result.prediction?.top2) &&
            result.prediction.top2.length > 0 &&
            result.prediction.banker !== undefined &&
            result.prediction.confidence !== undefined,
        );

      setPredictionEnginesStatus(
        successful
          ? 'connected'
          : 'not-connected',
      );
    } catch (error) {
      console.error(
        'Prediction-engine connection check failed:',
        error,
      );

      setPredictionEnginesStatus(
        'not-connected',
      );
    }
  };

  /* =========================================================
    INITIALIZE + EVENT LISTENERS
    ========================================================= */

  useEffect(() => {
    void checkMasterData();
    void checkTheresa();

    void checkPredictionEngines();

    const savedMasterData =
      localStorage.getItem(
        MASTER_DATA_STORAGE_KEY,
      );

    if (savedMasterData) {
      try {
        const parsed =
          JSON.parse(savedMasterData);

        if (
          parsed?.connected === true
        ) {
          setMasterDataStatus(
            'connected',
          );
        }
      } catch {
        // Ignore malformed stored state.
      }
    }

    const handleMasterDataUpdated =
      () => {
        setMasterDataStatus(
          'connected',
        );
      };

    const handlePredictionComplete = (event: Event) => {
      const payload = (
        event as CustomEvent<{
          status?: string;
        }>
      ).detail;

      setPredictionEnginesStatus(
        payload?.status === 'success'
          ? 'connected'
          : 'not-connected',
      );
      };

    window.addEventListener(
      MASTER_DATA_EVENT,
      handleMasterDataUpdated,
    );

    window.addEventListener(
      PREDICTION_EVENT,
      handlePredictionComplete,
    );

    return () => {
      window.removeEventListener(
        MASTER_DATA_EVENT,
        handleMasterDataUpdated,
      );

      window.removeEventListener(
        PREDICTION_EVENT,
        handlePredictionComplete,
      );
    };
  }, []);

  /* =========================================================
    DISPLAY
    ========================================================= */

  const displayStatus = (
    status: ConnectionState,
  ) => {
    switch (status) {
      case 'checking':
        return 'Checking...';

      case 'connected':
        return 'Connected';

      default:
        return 'Not connected';
    }
  };

  const statusClass = (
    status: ConnectionState,
  ) => {
    switch (status) {
      case 'connected':
        return 'status-connected';

      case 'checking':
        return 'status-checking';

      default:
        return 'status-disconnected';
    }
  };

  return (
    <div className="statusbar">

      <div className="status-item">
        <span className="status-label">
          System
        </span>

        <span className="status-value status-connected">
          Interface ready
        </span>
      </div>

      <div className="status-item">
        <span className="status-label">
          MASTER_DATA
        </span>

        <span
          className={`status-value ${statusClass(
            masterDataStatus,
          )}`}
        >
          {displayStatus(
            masterDataStatus,
          )}
        </span>
      </div>

      <div className="status-item">
        <span className="status-label">
          Theresa
        </span>

        <span
          className={`status-value ${statusClass(
            theresaStatus,
          )}`}
        >
          {displayStatus(
            theresaStatus,
          )}
        </span>
      </div>

      <div className="status-item">
        <span className="status-label">
          Prediction Engines
        </span>

        <span
          className={`status-value ${statusClass(
            predictionEnginesStatus,
          )}`}
        >
          {displayStatus(
            predictionEnginesStatus,
          )}
        </span>
      </div>

    </div>
  );
};

export default StatusBar;