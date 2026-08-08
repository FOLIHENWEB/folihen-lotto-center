// src/components/dashboard/SystemOverview.tsx
import React from 'react';
import type { SystemStatus } from '../../types';

const SystemOverview: React.FC = () => {
  const states: SystemStatus[] = [
    { label: 'Frontend', status: 'Ready' },
    { label: 'Git Repository', status: 'Connected' },
    { label: 'Backend', status: 'Not connected' },
    { label: 'MASTER_DATA Service', status: 'Not connected' },
    { label: 'Prediction Engines', status: 'Not connected' },
    { label: 'Theresa', status: 'Not connected' },
    { label: 'Theresa Intelligence', status: 'Coming soon' },
  ];

  const statusColor = (status: string) => {
    switch (status) {
      case 'Ready': return '#4ade80';
      case 'Connected': return '#60a5fa';
      case 'Not connected': return '#f87171';
      case 'Coming soon': return '#fbbf24';
      default: return '#9ca3af';
    }
  };

  return (
    <div className="panel system-overview">
      <h3>System Overview</h3>
      <div className="system-states">
        {states.map((item) => (
          <div key={item.label} className="system-state">
            <span className="state-label">{item.label}</span>
            <span className="state-status" style={{ color: statusColor(item.status) }}>{item.status}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default SystemOverview;
