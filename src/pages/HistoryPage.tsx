import React, { useEffect, useState } from 'react';

type HistoryRecord = {
  id: string;
  timestamp: string;
  game?: string;
  operation: string;
  source: string;
  status: string;
  summary?: string;
  artifact?: string;
  results?: Array<{ engine?: string; status?: string; prediction?: Record<string, unknown> }>;
  prediction?: Record<string, unknown>;
};

const HistoryPage: React.FC = () => {
  const [records, setRecords] = useState<HistoryRecord[]>([]);
  const [game, setGame] = useState('');
  const [operation, setOperation] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    const params = new URLSearchParams();
    if (game) params.set('game', game);
    if (operation) params.set('operation', operation);
    const loadHistory = async () => {
      try {
        const response = await fetch(`/api/history?${params.toString()}`);
        const payload = (await response.json()) as { status?: string; records?: HistoryRecord[]; message?: string };
        if (!response.ok || payload.status !== 'success') throw new Error(payload.message || 'Unable to load operation history.');
        setRecords(payload.records || []);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : 'Unable to load operation history.');
      }
    };
    void loadHistory();
  }, [game, operation]);

  return (
    <div className="operational-page">
      <section className="operational-page-header"><div><p className="operational-eyebrow">PERSISTED OPERATIONS</p><h1>History</h1><p>Chronological records from saved Prediction Engines and Theresa outputs.</p></div></section>
      <section className="operational-toolbar">
        <label>Game<input value={game} placeholder="All games" onChange={event => setGame(event.target.value)} /></label>
        <label>Operation<select value={operation} onChange={event => setOperation(event.target.value)}><option value="">All operations</option><option>Prediction Engines</option><option>Theresa</option></select></label>
      </section>
      {error && <section className="operational-error">{error}</section>}
      <section className="operational-record-list">
        {records.length === 0 && <div className="operational-empty">No persisted operation records match these filters.</div>}
        {records.map(record => (
          <details key={record.id} className="history-record">
            <summary><span>{record.timestamp}</span><strong>{record.game || 'Unknown game'}</strong><span>{record.operation}</span><span className={`history-status ${record.status}`}>{record.status}</span><span>{record.summary || record.source}</span></summary>
            <div className="history-detail">
              <p><strong>Source:</strong> {record.source}</p>
              {record.artifact && <p><strong>Artifact:</strong> <code>{record.artifact}</code></p>}
              {record.results?.map(result => <p key={result.engine}><strong>{result.engine}:</strong> {result.status} {result.prediction ? `(${Object.keys(result.prediction).join(', ')})` : ''}</p>)}
              {record.prediction && <p><strong>Available fields:</strong> {Object.keys(record.prediction).join(', ')}</p>}
            </div>
          </details>
        ))}
      </section>
    </div>
  );
};

export default HistoryPage;
