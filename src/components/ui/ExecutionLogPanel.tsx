// src/components/ui/ExecutionLogPanel.tsx
import React from 'react';
import { X, Clock } from 'lucide-react';
import { useLogs } from '../../contexts/LogContext';

interface ExecutionLogPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

const ExecutionLogPanel: React.FC<ExecutionLogPanelProps> = ({ isOpen, onClose }) => {
  const { logs, clearLogs } = useLogs();

  const [renderTime] = React.useState(() => Date.now());
  const formatTime = (ts: number) => {
    const diff = renderTime - ts;
    if (diff < 60000) return 'just now';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return new Date(ts).toLocaleDateString();
  };

  if (!isOpen) return null;

  return (
    <div className="panel-overlay" onClick={onClose}>
      <div className="panel-overlay-content" onClick={(e) => e.stopPropagation()}>
        <div className="panel-header">
          <h3>Execution Log</h3>
          <div className="panel-actions">
            {logs.length > 0 && (
              <button className="panel-action-btn" onClick={clearLogs}>Clear</button>
            )}
            <button className="panel-close-btn" onClick={onClose}><X size={20} /></button>
          </div>
        </div>
        <div className="panel-body">
          {logs.length === 0 ? (
            <div className="empty-state">No log entries</div>
          ) : (
            <ul className="log-list">
              {logs.map((log) => (
                <li key={log.id} className="log-item">
                  <Clock size={14} className="log-time-icon" />
                  <div className="log-content">
                    <span className="log-message">{log.message}</span>
                    <span className="log-source">{log.source ? ` (${log.source})` : ''}</span>
                    <span className="log-time">{formatTime(log.timestamp)}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
};

export default ExecutionLogPanel;
