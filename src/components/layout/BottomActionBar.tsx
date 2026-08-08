// src/components/layout/BottomActionBar.tsx
import React from 'react';
import { useNotifications } from '../../contexts/NotificationContext';
import { useLogs } from '../../contexts/LogContext';

const BottomActionBar: React.FC = () => {
  const { addNotification } = useNotifications();
  const { addLog } = useLogs();

  const handleAction = (label: string) => {
    const msg = `Mock action: ${label}`;
    addLog(msg, 'UI');
    addNotification('info', msg);
  };

  const actions = [
    { id: 'update-master', label: 'Update MASTER_DATA', icon: '📊' },
    { id: 'run-prediction', label: 'Run Prediction Engines', icon: '🔮' },
    { id: 'run-theresa', label: 'Run Theresa', icon: '🤖' },
    { id: 'run-cycle', label: 'Run Daily Cycle', icon: '🔄' },
  ];

  return (
    <div className="bottom-action-bar">
      {actions.map((action) => (
        <button key={action.id} className="action-btn" onClick={() => handleAction(action.label)}>
          <span className="action-icon">{action.icon}</span>
          <span className="action-label">{action.label}</span>
        </button>
      ))}
    </div>
  );
};

export default BottomActionBar;
