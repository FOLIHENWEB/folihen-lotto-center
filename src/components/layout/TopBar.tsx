// src/components/layout/TopBar.tsx
import React from 'react';
import { Menu, Sun, Moon, Bell, User, List } from 'lucide-react';
import { useTheme } from '../../contexts/ThemeContext';
import { useNotifications } from '../../contexts/NotificationContext';

interface TopBarProps {
  onMenuClick: () => void;
  onNotificationClick: () => void;
  onLogClick: () => void;
}

const TopBar: React.FC<TopBarProps> = ({ onMenuClick, onNotificationClick, onLogClick }) => {
  const { theme, toggleTheme } = useTheme();
  const { notifications } = useNotifications();

  const unreadCount = notifications.length;

  return (
    <header className="topbar">
      <div className="topbar-left">
        <button className="menu-btn" onClick={onMenuClick} aria-label="Toggle sidebar">
          <Menu size={24} />
        </button>
        <div className="topbar-title">Theresa Operations Center</div>
      </div>
      <div className="topbar-right">
        <button className="icon-btn" onClick={toggleTheme} aria-label="Toggle theme">
          {theme === 'light' ? <Moon size={20} /> : <Sun size={20} />}
        </button>
        <button className="icon-btn log-btn" onClick={onLogClick} aria-label="Execution logs">
          <List size={20} />
        </button>
        <button className="icon-btn notification-btn" onClick={onNotificationClick} aria-label="Notifications">
          <Bell size={20} />
          {unreadCount > 0 && <span className="badge">{unreadCount}</span>}
        </button>
        <button className="icon-btn" aria-label="User">
          <User size={20} />
        </button>
      </div>
    </header>
  );
};

export default TopBar;
