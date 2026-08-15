import React, { useEffect, useState } from 'react';
import {
  Brain,
  Cpu,
  Database,
  ShieldCheck,
} from 'lucide-react';

import RecentActivity from '../components/dashboard/RecentActivity';
import SystemOverview from '../components/dashboard/SystemOverview';

type Prediction = {
  game?: string;
  target_game?: string;
  generated?: string;
  banker?: number;
  confidence?: number;
  risk?: number;
  consensus?: string[];
  top2?: number[];
  top5?: number[];
  top10?: number[];
  top20?: number[];
  top30?: number[];
  top60?: number[];
  two_sure_pairs?: number[][];
};

type EngineResult = {
  engine?: string;
  prediction?: Prediction;
};

const numberText = (numbers?: number[]) =>
  numbers?.length
    ? numbers.map(number => String(number).padStart(2, '0')).join('  ')
    : 'Not returned';

const DashboardPage: React.FC = () => {
  const [engineResults, setEngineResults] = useState<EngineResult[]>([]);
  const [theresa, setTheresa] = useState<Prediction | null>(null);
  const [intelligence, setIntelligence] = useState<Prediction | null>(null);

  useEffect(() => {
    const loadLatest = async () => {
      void fetch('/api/prediction-engines/latest')
        .then(async response => {
          if (response.ok) {
            const payload = await response.json() as { results?: EngineResult[] };
            setEngineResults(payload.results ?? []);
          }
        })
        .catch(() => undefined);
      void fetch('/api/theresa/latest')
        .then(async response => {
          if (response.ok) {
            const payload = await response.json() as { prediction?: Prediction };
            setTheresa(payload.prediction ?? null);
          }
        })
        .catch(() => undefined);
      void fetch('/api/theresa-intelligence/latest')
        .then(async response => {
          if (response.ok) {
            const payload = await response.json() as { prediction?: Prediction };
            setIntelligence(payload.prediction ?? null);
          }
        })
        .catch(() => undefined);
    };
    void loadLatest();
    window.addEventListener(
      'theresa:intelligence-complete',
      loadLatest,
    );
    return () => {
      window.removeEventListener(
        'theresa:intelligence-complete',
        loadLatest,
      );
    };
  }, []);

  const kadija = engineResults.find(
    result => result.engine?.toLowerCase() === 'kadija',
  )?.prediction;
  const desmond = engineResults.find(
    result => result.engine?.toLowerCase() === 'desmond',
  )?.prediction;

  const standardCard = (
    source: string,
    subtitle: string,
    prediction: Prediction | null | undefined,
  ) => (
    <article className="prediction-engine-card">
      <div className="prediction-card-header">
        <div><div><h2>{source}</h2><p>{subtitle}</p></div></div>
        <span className="prediction-source-badge">Independent</span>
      </div>
      {prediction ? (
        <>
          <div className="engine-prediction-meta">
            <div><span>Game</span><strong>{prediction.game || prediction.target_game}</strong></div>
            <div><span>Banker</span><strong>{prediction.banker ?? 'Not returned'}</strong></div>
            <div><span>Confidence</span><strong>{prediction.confidence?.toFixed(6) ?? 'Not returned'}</strong></div>
          </div>
          <div className="prediction-level-grid">
            <div><span>Top 2</span><strong>{numberText(prediction.top2)}</strong></div>
            <div><span>Top 5</span><strong>{numberText(prediction.top5)}</strong></div>
            <div><span>Top 10</span><strong>{numberText(prediction.top10)}</strong></div>
            <div><span>Top 20</span><strong>{numberText(prediction.top20)}</strong></div>
            <div><span>Top 30</span><strong>{numberText(prediction.top30)}</strong></div>
            <div><span>Top 60</span><strong>{numberText(prediction.top60)}</strong></div>
          </div>
        </>
      ) : (
        <div className="prediction-empty-state"><strong>No prediction available</strong><span>No saved {source} prediction is available.</span></div>
      )}
    </article>
  );

  return (
    <div className="dashboard-page dashboard-page--prediction-first">

      {/* =====================================================
          COMPACT SYSTEM STRIP
          ===================================================== */}

      <section
        className="dashboard-system-strip"
        aria-label="System status"
      >
        <div className="system-strip-item">
          <Cpu size={20} />

          <div>
            <strong>Prediction Engines</strong>
            <span>Engine control workspace</span>
          </div>
        </div>

        <div className="system-strip-item">
          <Brain size={20} />

          <div>
            <strong>Theresa</strong>
            <span>Tier 1 prediction output</span>
          </div>
        </div>

        <div className="system-strip-item">
          <Database size={20} />

          <div>
            <strong>MASTER_DATA</strong>
            <span>Official draw source</span>
          </div>
        </div>

        <div className="system-strip-item">
          <ShieldCheck size={20} />

          <div>
            <strong>TOC</strong>
            <span>Local operations interface</span>
          </div>
        </div>
      </section>

      {/* =====================================================
          PRIMARY PREDICTION WORKSPACE
          ===================================================== */}

      <section className="prediction-workspace">
        <div className="prediction-workspace-header">
          <div>
            <p className="prediction-eyebrow">
              TOC PREDICTION WORKSPACE
            </p>

            <h1>
              Predictions
            </h1>

            <p>
              Engine outputs remain separate so their
              performance can be evaluated independently.
            </p>
          </div>

          <div className="prediction-workspace-status">
            Use Prediction Engines to run a game
          </div>
        </div>

        <div className="prediction-engine-grid">
          {standardCard('Kadija', 'Prediction Engine', kadija)}
          {standardCard('Desmond', 'Prediction Engine', desmond)}
          {standardCard('Theresa', 'Tier 1 prediction', theresa)}
          <article className="prediction-engine-card prediction-engine-card--featured">
            <div className="prediction-card-header"><div><div><h2>Theresa Intelligence</h2><p>Historical Intelligence / Tier 2</p></div></div><span className="prediction-source-badge">Research</span></div>
            {intelligence ? (
              <>
                <div className="engine-prediction-meta"><div><span>Game</span><strong>{intelligence.game}</strong></div><div><span>Banker</span><strong>{intelligence.banker}</strong></div><div><span>Confidence</span><strong>{intelligence.confidence?.toFixed(6)}</strong></div><div><span>Risk</span><strong>{intelligence.risk?.toFixed(6)}</strong></div></div>
                <div className="prediction-level-grid"><div><span>Two-Sure Pairs</span><strong>{intelligence.two_sure_pairs?.map(pair => pair.join(' - ')).join('; ')}</strong></div><div><span>Top 5</span><strong>{numberText(intelligence.top5)}</strong></div><div><span>Top 10</span><strong>{numberText(intelligence.top10)}</strong></div><div><span>Consensus</span><strong>{intelligence.consensus?.join(', ')}</strong></div></div>
              </>
            ) : <div className="prediction-empty-state"><strong>No prediction available</strong><span>No saved Theresa Intelligence prediction is available.</span></div>}
          </article>
        </div>
      </section>

      {/* =====================================================
          SECONDARY INFORMATION
          ===================================================== */}

      <section className="dashboard-secondary-grid">
        <SystemOverview />
        <RecentActivity />
      </section>
    </div>
  );
};

export default DashboardPage;