 import React from 'react';
import {
  Brain,
  Cpu,
  Database,
  ShieldCheck,
} from 'lucide-react';

import RecentActivity from '../components/dashboard/RecentActivity';
import SystemOverview from '../components/dashboard/SystemOverview';

const DashboardPage: React.FC = () => {
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

        {/* ENGINE RESULTS */}

        <div className="prediction-engine-grid">

          {/* KADIJA */}

          <article className="prediction-engine-card">
            <div className="prediction-card-header">
              <div>
                <span className="prediction-engine-icon">
                  ♟️
                </span>

                <div>
                  <h2>Kadija</h2>
                  <p>Prediction Engine v4</p>
                </div>
              </div>

              <span className="prediction-source-badge">
                Engine
              </span>
            </div>

            <div className="prediction-empty-state">
              <strong>
                No prediction loaded
              </strong>

              <span>
                Run Prediction Engines and Kadija's
                latest result will appear here.
              </span>
            </div>

            <div className="prediction-level-grid">
              <div>
                <span>Top 5</span>
                <strong>—</strong>
              </div>

              <div>
                <span>Top 2</span>
                <strong>—</strong>
              </div>

              <div>
                <span>Banker</span>
                <strong>—</strong>
              </div>

              <div>
                <span>Confidence</span>
                <strong>—</strong>
              </div>
            </div>
          </article>

          {/* DESMOND */}

          <article className="prediction-engine-card prediction-engine-card--featured">
            <div className="prediction-card-header">
              <div>
                <span className="prediction-engine-icon">
                  🔮
                </span>

                <div>
                  <h2>Desmond</h2>
                  <p>Prediction Engine v2</p>
                </div>
              </div>

              <span className="prediction-source-badge">
                Engine
              </span>
            </div>

            <div className="prediction-empty-state">
              <strong>
                No prediction loaded
              </strong>

              <span>
                Run Prediction Engines and Desmond's
                latest result will appear here.
              </span>
            </div>

            <div className="prediction-level-grid">
              <div>
                <span>Top 5</span>
                <strong>—</strong>
              </div>

              <div>
                <span>Top 2</span>
                <strong>—</strong>
              </div>

              <div>
                <span>Banker</span>
                <strong>—</strong>
              </div>

              <div>
                <span>Confidence</span>
                <strong>—</strong>
              </div>
            </div>
          </article>

          {/* THERESA */}

          <article className="prediction-engine-card">
            <div className="prediction-card-header">
              <div>
                <span className="prediction-engine-icon">
                  🤖
                </span>

                <div>
                  <h2>Theresa</h2>
                  <p>Tier 1 Intelligence</p>
                </div>
              </div>

              <span className="prediction-source-badge">
                Intelligence
              </span>
            </div>

            <div className="prediction-empty-state">
              <strong>
                No Theresa output loaded
              </strong>

              <span>
                Theresa's independent recommendation
                will appear here after her run.
              </span>
            </div>

            <div className="prediction-level-grid">
              <div>
                <span>Top 5</span>
                <strong>—</strong>
              </div>

              <div>
                <span>Top 2</span>
                <strong>—</strong>
              </div>

              <div>
                <span>Banker</span>
                <strong>—</strong>
              </div>

              <div>
                <span>Confidence</span>
                <strong>—</strong>
              </div>
            </div>
          </article>
        </div>

        {/* FUTURE TIER 2 */}

        <div className="theresa-tier-two-slot">
          <div>
            <span className="tier-two-label">
              THERESA TIER 2
            </span>

            <strong>
              Historical Intelligence Layer
            </strong>

            <p>
              Reserved for the second-tier engine.
              It will run automatically after Theresa
              Tier 1 when integration is completed.
            </p>
          </div>

          <span className="tier-two-status">
            Coming later
          </span>
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