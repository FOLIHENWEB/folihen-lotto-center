// src/components/layout/AppShell.tsx
import React, { useState } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import TopBar from './TopBar';
import StatusBar from './StatusBar';
import BottomActionBar from './BottomActionBar';
import NotificationCenter from '../ui/NotificationCenter';
import ExecutionLogPanel from '../ui/ExecutionLogPanel';

const AppShell: React.FC = () => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [notifPanelOpen, setNotifPanelOpen] = useState(false);
  const [logPanelOpen, setLogPanelOpen] = useState(false);

  const toggleSidebar = () => setSidebarOpen(prev => !prev);
  const closeSidebar = () => setSidebarOpen(false);

  const toggleNotifPanel = () => setNotifPanelOpen(prev => !prev);
  const toggleLogPanel = () => setLogPanelOpen(prev => !prev);

  return (
    <div className="app-shell">
      <Sidebar isOpen={sidebarOpen} onClose={closeSidebar} />
      <div className="main-content">
        <TopBar
          onMenuClick={toggleSidebar}
          onNotificationClick={toggleNotifPanel}
          onLogClick={toggleLogPanel}
        />
        <main className="page-content">
          <Outlet />
        </main>
        <StatusBar />
        <BottomActionBar />
      </div>
      <NotificationCenter isOpen={notifPanelOpen} onClose={() => setNotifPanelOpen(false)} />
      <ExecutionLogPanel isOpen={logPanelOpen} onClose={() => setLogPanelOpen(false)} />
    </div>
  );
};

export default AppShell;
