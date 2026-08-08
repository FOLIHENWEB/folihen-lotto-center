// src/components/ui/NotificationCenter.tsx
import React from 'react';
import { X, CheckCircle, AlertCircle, Info, AlertTriangle } from 'lucide-react';
import { useNotifications } from '../../contexts/NotificationContext';
import type { Notification } from '../../types';

interface NotificationCenterProps {
  isOpen: boolean;
  onClose: () => void;
}

const NotificationCenter: React.FC<NotificationCenterProps> = ({ isOpen, onClose }) => {
  const { notifications, clearNotification, clearAll } = useNotifications();

  const [renderTime] = React.useState(() => Date.now());
  const getIcon = (type: Notification['type']) => {
    switch (type) {
      case 'success': return <CheckCircle size={16} color="#4ade80" />;
      case 'error': return <AlertCircle size={16} color="#f87171" />;
      case 'warning': return <AlertTriangle size={16} color="#fbbf24" />;
      default: return <Info size={16} color="#60a5fa" />;
    }
  };

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
          <h3>Notifications</h3>
          <div className="panel-actions">
            {notifications.length > 0 && (
              <button className="panel-action-btn" onClick={clearAll}>Clear all</button>
            )}
            <button className="panel-close-btn" onClick={onClose}><X size={20} /></button>
          </div>
        </div>
        <div className="panel-body">
          {notifications.length === 0 ? (
            <div className="empty-state">No notifications</div>
          ) : (
            <ul className="notification-list">
              {notifications.map((n) => (
                <li key={n.id} className={`notification-item ${n.type}`}>
                  <div className="notification-icon">{getIcon(n.type)}</div>
                  <div className="notification-content">
                    <span className="notification-message">{n.message}</span>
                    <span className="notification-time">{formatTime(n.timestamp)}</span>
                  </div>
                  <button className="notification-dismiss" onClick={() => clearNotification(n.id)}>
                    <X size={14} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
};

export default NotificationCenter;
