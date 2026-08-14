import React, { useEffect, useState } from 'react';

type GameSummary = {
  game: string;
  record_count: number;
  first_draw_date: string;
  latest_draw_date: string;
  source_file: string;
};

type MasterDataSummary = {
  status: string;
  dataset: {
    game_count: number;
    record_count: number;
    generated_at_utc: string;
  };
  games: GameSummary[];
};

type GameDetail = {
  game: GameSummary;
  recent_records: Array<{
    draw_date: string;
    draw_numbers: number[];
  }>;
};

const MasterDataPage: React.FC = () => {
  const [summary, setSummary] = useState<MasterDataSummary | null>(null);
  const [detail, setDetail] = useState<GameDetail | null>(null);
  const [selectedGame, setSelectedGame] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    const loadSummary = async () => {
      try {
        const response = await fetch('/api/master-data/summary');
        const payload = (await response.json()) as MasterDataSummary & { message?: string };
        if (!response.ok || payload.status !== 'success') {
          throw new Error(payload.message || 'Unable to load canonical MASTER_DATA.');
        }
        setSummary(payload);
        setSelectedGame(payload.games[0]?.game || '');
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : 'Unable to load MASTER_DATA.');
      }
    };
    void loadSummary();
  }, []);

  useEffect(() => {
    if (!selectedGame) return;
    const loadDetail = async () => {
      try {
        const response = await fetch(`/api/master-data/games/${encodeURIComponent(selectedGame)}`);
        const payload = (await response.json()) as GameDetail & { status?: string; message?: string };
        if (!response.ok || payload.status !== 'success') {
          throw new Error(payload.message || 'Unable to load game details.');
        }
        setDetail(payload);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : 'Unable to load game details.');
      }
    };
    void loadDetail();
  }, [selectedGame]);

  return (
    <div className="operational-page">
      <section className="operational-page-header">
        <div>
          <p className="operational-eyebrow">CANONICAL DATASET</p>
          <h1>MASTER_DATA</h1>
          <p>Read-only status and game summaries from the canonical normalized dataset.</p>
        </div>
        <span className={`operational-status ${summary ? 'is-success' : 'is-error'}`}>
          {summary ? 'Connected' : error ? 'Unavailable' : 'Loading'}
        </span>
      </section>

      {error && <section className="operational-error">{error}</section>}

      {summary && (
        <>
          <section className="operational-metrics">
            <div><span>Games available</span><strong>{summary.dataset.game_count}</strong></div>
            <div><span>Canonical records</span><strong>{summary.dataset.record_count}</strong></div>
            <div><span>Last normalized</span><strong>{new Date(summary.dataset.generated_at_utc).toLocaleString()}</strong></div>
          </section>

          <section className="operational-toolbar">
            <label>
              Game
              <select value={selectedGame} onChange={event => setSelectedGame(event.target.value)}>
                {summary.games.map(game => <option key={game.game} value={game.game}>{game.game}</option>)}
              </select>
            </label>
          </section>

          {detail && (
            <section className="operational-card">
              <div className="operational-card-heading"><h2>{detail.game.game}</h2><span>{detail.game.record_count} records</span></div>
              <div className="operational-metadata">
                <div><span>Earliest draw</span><strong>{detail.game.first_draw_date}</strong></div>
                <div><span>Latest draw</span><strong>{detail.game.latest_draw_date}</strong></div>
                <div><span>Source file</span><strong>{detail.game.source_file}</strong></div>
                <div><span>Schema</span><strong>Validated canonical data</strong></div>
              </div>
              <h3>Recent official draws</h3>
              <div className="operational-record-list">
                {detail.recent_records.map(record => (
                  <div key={record.draw_date}><span>{record.draw_date}</span><strong>{record.draw_numbers.join(', ')}</strong></div>
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
};

export default MasterDataPage;
