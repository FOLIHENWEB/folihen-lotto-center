import React, { useEffect, useState } from 'react';

type ReportRow = {
  timestamp: string;
  game?: string;
  source: string;
  status: string;
  artifact?: string;
  prediction?: Record<string, unknown>;
};

const levels = ['top2', 'top5', 'top10', 'top20', 'top30', 'top60'] as const;

const ReportsPage: React.FC = () => {
  const [reports, setReports] = useState<ReportRow[]>([]);
  const [game, setGame] = useState('');
  const [source, setSource] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    const params = new URLSearchParams();
    if (game) params.set('game', game);
    if (source) params.set('source', source);
    const loadReports = async () => {
      try {
        const response = await fetch(`/api/reports?${params.toString()}`);
        const payload = (await response.json()) as { status?: string; reports?: ReportRow[]; message?: string };
        if (!response.ok || payload.status !== 'success') throw new Error(payload.message || 'Unable to load reports.');
        setReports(payload.reports || []);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : 'Unable to load reports.');
      }
    };
    void loadReports();
  }, [game, source]);

  const displayValue = (value: unknown) => Array.isArray(value) && value.length > 0 ? value.join(', ') : 'Not returned';

  return (
    <div className="operational-page">
      <section className="operational-page-header"><div><p className="operational-eyebrow">PERSISTED RESULTS</p><h1>Reports</h1><p>Independent summaries of completed Kadijja, Desmond, and Theresa outputs.</p></div></section>
      <section className="operational-toolbar">
        <label>Game<input value={game} placeholder="All games" onChange={event => setGame(event.target.value)} /></label>
        <label>Source<select value={source} onChange={event => setSource(event.target.value)}><option value="">All sources</option><option>Kadija</option><option>Desmond</option><option>Theresa</option></select></label>
      </section>
      {error && <section className="operational-error">{error}</section>}
      <section className="report-grid">
        {reports.length === 0 && <div className="operational-empty">No persisted reports match these filters.</div>}
        {reports.map((report, index) => (
          <article className="operational-card" key={`${report.source}-${report.timestamp}-${index}`}>
            <div className="operational-card-heading"><div><h2>{report.source}</h2><span>{report.game || 'Unknown game'}</span></div><span className={`history-status ${report.status}`}>{report.status}</span></div>
            <p className="report-timestamp">{report.timestamp}</p>
            <div className="operational-metadata"><div><span>Banker</span><strong>{String(report.prediction?.banker ?? 'Not returned')}</strong></div><div><span>Confidence</span><strong>{report.prediction?.confidence === undefined ? 'Not returned' : `${(Number(report.prediction.confidence) * 100).toFixed(2)}%`}</strong></div></div>
            <div className="report-levels">{levels.map(level => <div key={level}><span>{level.replace('top', 'Top ')}</span><strong>{displayValue(report.prediction?.[level])}</strong></div>)}</div>
            {report.artifact && <p className="report-artifact"><span>Artifact</span><code>{report.artifact}</code></p>}
          </article>
        ))}
      </section>
    </div>
  );
};

export default ReportsPage;
