// src/components/dashboard/StatusCard.tsx
import React from 'react';
import type { ReactNode } from 'react';

interface StatusCardProps {
  title: string;
  value: string | number;
  icon: ReactNode;
  description?: string;
  status?: 'online' | 'offline' | 'coming-soon' | 'mock' | 'ready';
}

const StatusCard: React.FC<StatusCardProps> = ({ title, value, icon, description, status }) => {
  const statusClass = status ? `status-${status}` : '';
  return (
    <div className={`stat-card ${statusClass}`}>
      <div className="stat-icon">{icon}</div>
      <div className="stat-content">
        <div className="stat-title">{title}</div>
        <div className="stat-value">{value}</div>
        {description && <div className="stat-description">{description}</div>}
      </div>
    </div>
  );
};

export default StatusCard;
