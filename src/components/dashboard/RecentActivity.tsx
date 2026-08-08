// src/components/dashboard/RecentActivity.tsx
import React from 'react';

const RecentActivity: React.FC = () => {
  const activities = [
    { id: 'act1', action: 'TOC project initialized', time: '2 days ago', type: 'info' },
    { id: 'act2', action: 'GitHub repository connected', time: '1 day ago', type: 'success' },
    { id: 'act3', action: 'Sprint 1 foundation completed', time: '12 hours ago', type: 'success' },
    { id: 'act4', action: 'Phase 2 dashboard preparation started', time: '4 hours ago', type: 'info' },
  ];

  return (
    <div className="panel recent-activity">
      <h3>Recent Activity</h3>
      <ul className="activity-list">
        {activities.map((act) => (
          <li key={act.id} className={`activity-item ${act.type}`}>
            <span className="activity-action">{act.action}</span>
            <span className="activity-time">{act.time}</span>
          </li>
        ))}
      </ul>
    </div>
  );
};

export default RecentActivity;
