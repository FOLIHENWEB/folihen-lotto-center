import React, { useEffect, useState } from 'react';

type IntelligencePrediction = {
  game: string;
  generated?: string;
  banker: number;
  two_sure_pairs: number[][];
  top5: number[];
  top10: number[];
  confidence: number;
  risk: number;
  consensus: string[];
  registry_id?: number;
  runtime?: string;
  research_version?: string;
  research_commit?: string;
  source_artifact?: string;
};

const TheresaIntelligencePage: React.FC = () => {
  const [prediction, setPrediction] =
    useState<IntelligencePrediction | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');

  const readApiJson = async <T,>(response: Response): Promise<T> => {
    const text = await response.text();
    const contentType = response.headers.get('content-type') || '';
    if (!contentType.includes('application/json') || !text.trim()) {
      throw new Error('Theresa Intelligence API returned an invalid response.');
    }
    try {
      return JSON.parse(text) as T;
    } catch {
      throw new Error('Theresa Intelligence API returned invalid JSON.');
    }
  };

  const loadLatest = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await fetch(
        '/api/theresa-intelligence/latest',
      );
      const payload = await readApiJson<{
        status?: string;
        message?: string;
        prediction?: IntelligencePrediction;
      }>(response);
      if (response.status === 404 && payload.status === 'empty') {
        setPrediction(null);
        return;
      }
      if (!response.ok || payload.status !== 'success') {
        throw new Error(payload.message || 'Unable to load Theresa Intelligence.');
      }
      setPrediction(payload.prediction ?? null);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Unable to load Theresa Intelligence.',
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadLatest();
    const handleIntelligenceComplete = () => {
      void loadLatest();
    };
    window.addEventListener(
      'theresa:intelligence-complete',
      handleIntelligenceComplete,
    );
    return () => {
      window.removeEventListener(
        'theresa:intelligence-complete',
        handleIntelligenceComplete,
      );
    };
  }, []);

  const runIntelligence = async () => {
    if (!prediction?.game) {
      setError('Select a game from the Run Theresa Intelligence action.');
      return;
    }
    setRunning(true);
    setError('');
    try {
      const response = await fetch('/api/theresa-intelligence/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ game: prediction.game }),
      });
      const payload = await readApiJson<{
        message?: string;
        prediction?: IntelligencePrediction;
      }>(response);
      if (!response.ok || !payload.prediction) {
        throw new Error(payload.message || 'Theresa Intelligence did not complete.');
      }
      setPrediction(payload.prediction);
      window.dispatchEvent(new CustomEvent('theresa:intelligence-complete'));
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Unable to run Theresa Intelligence.',
      );
    } finally {
      setRunning(false);
    }
  };

  const chips = (numbers: number[]) => (
    <div className="theresa-number-list">
      {numbers.map((number, index) => (
        <span className="theresa-number-chip" key={`${number}-${index}`}>
          {String(number).padStart(2, '0')}
        </span>
      ))}
    </div>
  );

  return (
    <div className="theresa-page">
      <section className="theresa-page-header">
        <div>
          <p className="theresa-eyebrow">THERESA INTELLIGENCE</p>
          <h1>Historical Intelligence / Tier 2</h1>
          <p>Latest persisted Theresa Research Platform prediction.</p>
        </div>
        <div className="theresa-header-actions">
          <button
            type="button"
            className="theresa-refresh-btn"
            disabled={loading || running}
            onClick={() => void loadLatest()}
          >
            {loading ? 'Loading...' : 'Refresh'}
          </button>
          <button
            type="button"
            className="theresa-refresh-btn"
            disabled={!prediction || running}
            onClick={() => void runIntelligence()}
          >
            {running ? 'Running...' : 'Run Intelligence'}
          </button>
        </div>
      </section>

      {error && (
        <section className="theresa-state-card theresa-state-card--error">
          <strong>Theresa Intelligence unavailable</strong>
          <span>{error}</span>
        </section>
      )}

      {!loading && !error && !prediction && (
        <section className="theresa-state-card">
          <strong>No Theresa Intelligence prediction available.</strong>
          <span>Run Theresa Intelligence for a selected game to create a persisted result.</span>
        </section>
      )}

      {!loading && prediction && (
        <>
          <section className="theresa-prediction-meta">
            <div><span>Game</span><strong>{prediction.game}</strong></div>
            <div><span>Generated</span><strong>{prediction.generated || 'Not recorded'}</strong></div>
            <div><span>Banker</span><strong className="theresa-banker-value">{prediction.banker}</strong></div>
            <div><span>Confidence</span><strong>{prediction.confidence.toFixed(6)}</strong></div>
            <div><span>Risk</span><strong>{prediction.risk.toFixed(6)}</strong></div>
            <div><span>Consensus</span><strong>{prediction.consensus.join(', ')}</strong></div>
          </section>

          <section className="theresa-primary-grid">
            <article className="theresa-prediction-card theresa-prediction-card--primary">
              <div className="theresa-card-heading"><div><span>PRIMARY</span><h2>Top 5</h2></div></div>
              {chips(prediction.top5)}
            </article>
            <article className="theresa-prediction-card">
              <div className="theresa-card-heading"><div><span>PAIRS</span><h2>Two-Sure Pairs</h2></div></div>
              <div className="theresa-number-list">
                {prediction.two_sure_pairs.map((pair, index) => (
                  <span className="theresa-number-chip" key={`${pair.join('-')}-${index}`}>
                    {pair.map(number => String(number).padStart(2, '0')).join(' - ')}
                  </span>
                ))}
              </div>
            </article>
            <article className="theresa-prediction-card">
              <div className="theresa-card-heading"><div><span>CORE</span><h2>Top 10</h2></div></div>
              {chips(prediction.top10)}
            </article>
          </section>

          <section className="theresa-state-card">
            <strong>{prediction.runtime || 'Theresa_Research_Platform'}</strong>
            <span>Registry ID: {prediction.registry_id ?? 'Not recorded'} | Version: {prediction.research_version || 'Not recorded'}</span>
            <span>Artifact: {prediction.source_artifact || 'Not recorded'}</span>
          </section>
        </>
      )}
    </div>
  );
};

export default TheresaIntelligencePage;
