// src/components/layout/StatusBar.tsx
import React from 'react';

const StatusBar: React.FC = () => {
  const statusItems = [
    { label: 'System', value: 'Interface ready', color: '#4ade80' },
    { label: 'MASTER_DATA', value: 'Not connected', color: '#f87171' },
    { label: 'Theresa', value: 'Not connected', color: '#f87171' },
    { label: 'Prediction Engines', value: 'Not connected', color: '#f87171' },
  ];

  return (
    <div className="statusbar">
      {statusItems.map((item) => (
        <div key={item.label} className="status-item">
          <span className="status-label">{item.label}</span>
          <span className="status-value" style={{ color: item.color }}>{item.value}</span>
        </div>
      ))}
    </div>
  );
};

export default StatusBar;
