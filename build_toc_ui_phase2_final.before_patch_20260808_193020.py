#!/usr/bin/env python3
# Syntax and runtime validated with placeholder generation test
"""
TOC Phase 2 Final Safety Correction

This script builds the complete Theresa Operations Center UI foundation
with all safety fixes:
- No dangerous temp cleanup; only tracks its own temp files
- Temp files created in destination parent directory for atomic replace
- Central atomic_write_text function with full exception safety
- Rollback uses existing_before to determine which files to delete
- Vite starter CSS detection with multiple signatures
- Fixed dark mode sidebar text
- Full command reporting with stdout/stderr/return code
- Baseline build and lint before any changes
- Rollback on any failure
- No sys.exit() in helper functions
- Safe placeholder page generation without .format() interfering with JSX braces
- Removed unused React imports from App.tsx and main.tsx

It works with Vite + React + TypeScript projects.

Usage: python build_toc_ui_phase2_final.py
"""

import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Set, Tuple
import tempfile

# ---- Helper Functions ----

def find_project_root() -> Optional[Path]:
    """Find the project root by looking for package.json."""
    current = Path.cwd()
    while current != current.parent:
        if (current / "package.json").exists():
            return current
        current = current.parent
    return None

def verify_project(root: Path) -> bool:
    """Check that this is the TOC project by package.json name."""
    pkg_path = root / "package.json"
    if not pkg_path.exists():
        print("Error: package.json not found.")
        return False
    with open(pkg_path, "r", encoding="utf-8") as f:
        pkg = json.load(f)
    name = pkg.get("name", "")
    if name != "theresa-operations-center":
        print(f"Error: package.json name is '{name}', expected 'theresa-operations-center'.")
        return False
    return True

def run_command(cmd: str, cwd: Path) -> Tuple[int, str, str]:
    """Run a shell command and return (returncode, stdout, stderr)."""
    print("\n--------------------------------------------------")
    print(f"Command: {cmd}")
    print(f"Working Directory: {cwd}")
    proc = subprocess.Popen(
        cmd, shell=True, cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    stdout, stderr = proc.communicate()
    print(f"Return Code: {proc.returncode}")
    print("STDOUT:")
    print(stdout if stdout else "(empty)")
    print("STDERR:")
    print(stderr if stderr else "(empty)")
    print("--------------------------------------------------")
    return proc.returncode, stdout or "", stderr or ""

def run_build_and_lint(root: Path, phase: str = "after") -> None:
    """
    Run npm run build and npm run lint.
    Raises RuntimeError if either command fails.
    """
    print(f"\n--- Running npm run build ({phase}) ---")
    ret, out, err = run_command("npm run build", root)
    if ret != 0:
        raise RuntimeError(f"Build failed ({phase}) with exit code {ret}")

    print(f"\n--- Running npm run lint ({phase}) ---")
    ret, out, err = run_command("npm run lint", root)
    if ret != 0:
        raise RuntimeError(f"Lint failed ({phase}) with exit code {ret}")

def get_dependency_missing(root: Path, dep: str) -> bool:
    """Check if a dependency is missing from both dependencies and devDependencies."""
    pkg_path = root / "package.json"
    with open(pkg_path, "r", encoding="utf-8") as f:
        pkg = json.load(f)
    deps = pkg.get("dependencies", {})
    dev_deps = pkg.get("devDependencies", {})
    return dep not in deps and dep not in dev_deps

def install_deps(root: Path) -> str:
    """
    Install required dependencies if missing.
    Returns status string.
    Raises RuntimeError if npm install fails.
    """
    missing = []
    for dep in ["react-router-dom", "lucide-react"]:
        if get_dependency_missing(root, dep):
            missing.append(dep)
    if missing:
        print(f"Installing missing dependencies: {', '.join(missing)}")
        ret, out, err = run_command(f"npm install {' '.join(missing)} --save", root)
        if ret != 0:
            raise RuntimeError("npm install failed")
        print("Dependencies installed.")
        return "Installed successfully"
    else:
        print("All required dependencies are already installed.")
        return "Already installed"

def cleanup_temp_files(temp_files: Set[Path]) -> None:
    """Delete only the temporary files tracked by this script."""
    for tmp_path in list(temp_files):
        try:
            if tmp_path.exists() and tmp_path.is_file():
                tmp_path.unlink()
                temp_files.discard(tmp_path)
                print(f"Cleaned up temp file: {tmp_path}")
            else:
                # If it doesn't exist or is not a file, remove from set
                temp_files.discard(tmp_path)
        except Exception as e:
            print(f"Failed to delete temp file {tmp_path}: {e}")
            # Keep it in set to report failure, but we'll remove it below
            # Actually, we want to keep it if deletion failed to report later.
            # But we'll just leave it; we'll report count.
            pass
    print(f"Tracked temporary files remaining: {len(temp_files)}")

def rollback(
    root: Path,
    backup_dir: Path,
    backed_up: Set[Path],
    existing_before: Set[Path],
    target_files: List[Path],
) -> None:
    """
    Restore all backed-up files and delete newly created files.
    Uses existing_before to determine which files are new.
    Continues even if individual restorations fail.
    """
    print("\n--- Rolling back changes ---")
    restored_count = 0
    deleted_count = 0
    failure_count = 0

    # Restore backed-up files if backup directory exists
    if backup_dir.exists():
        for rel_path in backed_up:
            src_path = root / rel_path
            backup_src = backup_dir / rel_path
            if backup_src.exists():
                try:
                    # Ensure parent directory exists
                    src_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup_src, src_path)
                    print(f"Restored {rel_path}")
                    restored_count += 1
                except Exception as e:
                    print(f"Failed to restore {rel_path}: {e}")
                    failure_count += 1
            else:
                print(f"Warning: backup for {rel_path} not found, skipping.")
    else:
        print("Warning: backup directory does not exist. Skipping restoration.")

    # Delete newly created files (those that did not exist before)
    for rel_path in target_files:
        if rel_path not in existing_before:
            file_path = root / rel_path
            if file_path.exists() and file_path.is_file():
                try:
                    file_path.unlink()
                    print(f"Deleted new file {rel_path}")
                    deleted_count += 1
                except Exception as e:
                    print(f"Failed to delete {rel_path}: {e}")
                    failure_count += 1
            elif file_path.exists() and file_path.is_dir():
                print(f"Warning: {rel_path} is a directory, not deleting.")
            else:
                # File doesn't exist, nothing to do
                pass

    print(f"Rollback summary: restored {restored_count} file(s), deleted {deleted_count} new file(s), {failure_count} failure(s).")

# ---- CORRECTED atomic_write_text FUNCTION ----
def atomic_write_text(
    destination: Path,
    content: str,
    temp_files: Set[Path],
) -> None:
    """
    Atomically write text content to destination.

    The temporary file is fully closed before os.replace() runs,
    which prevents WinError 32 on Windows.
    """
    tmp_path: Optional[Path] = None

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
        ) as tmp:
            tmp_path = Path(tmp.name)
            temp_files.add(tmp_path)

            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())

        # The temporary file is now closed.

        if tmp_path.stat().st_size == 0:
            raise ValueError(
                f"Generated temporary file is empty: {destination}"
            )

        os.replace(tmp_path, destination)
        temp_files.discard(tmp_path)

    except Exception:
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

        if tmp_path is not None:
            temp_files.discard(tmp_path)

        raise

def is_vite_starter_css(css: str) -> bool:
    """Detect if the CSS is the standard Vite starter stylesheet."""
    signatures = [
        "color-scheme: light dark",
        "font-synthesis: none",
        "text-rendering: optimizeLegibility",
        "button:focus-visible",
        "@media (prefers-color-scheme: light)",
        "place-items: center",
    ]
    count = sum(1 for sig in signatures if sig in css)
    return count >= 3

# ---- File Content Definitions ----
# All component contents are defined as strings with type-only imports and stable keys.

# types/index.ts
TYPES_INDEX = """// src/types/index.ts
export type Theme = 'light' | 'dark';

export interface Notification {
  id: string;
  type: 'info' | 'success' | 'warning' | 'error';
  message: string;
  timestamp: number;
}

export interface LogEntry {
  id: string;
  message: string;
  timestamp: number;
  source?: string;
}

export interface SystemStatus {
  label: string;
  status: 'Ready' | 'Connected' | 'Not connected' | 'Coming soon';
}
"""

# contexts/ThemeContext.tsx (with ESLint disable)
THEME_CONTEXT = """/* eslint-disable react-refresh/only-export-components */
// src/contexts/ThemeContext.tsx
import React, { createContext, useContext, useState, useEffect } from 'react';
import type { ReactNode } from 'react';
import type { Theme } from '../types';

interface ThemeContextType {
  theme: Theme;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export const ThemeProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [theme, setTheme] = useState<Theme>(() => {
    const stored = localStorage.getItem('toc-theme');
    if (stored === 'dark' || stored === 'light') return stored;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });

  useEffect(() => {
    localStorage.setItem('toc-theme', theme);
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => prev === 'light' ? 'dark' : 'light');
  };

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = (): ThemeContextType => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};
"""

# contexts/NotificationContext.tsx
NOTIFICATION_CONTEXT = """/* eslint-disable react-refresh/only-export-components */
// src/contexts/NotificationContext.tsx
import React, { createContext, useContext, useState } from 'react';
import type { ReactNode } from 'react';
import type { Notification } from '../types';

interface NotificationContextType {
  notifications: Notification[];
  addNotification: (type: Notification['type'], message: string) => void;
  clearNotification: (id: string) => void;
  clearAll: () => void;
}

const NotificationContext = createContext<NotificationContextType | undefined>(undefined);

export const NotificationProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [notifications, setNotifications] = useState<Notification[]>([]);

  const addNotification = (type: Notification['type'], message: string) => {
    const id = Date.now().toString() + Math.random().toString(36).slice(2, 8);
    setNotifications(prev => [{ id, type, message, timestamp: Date.now() }, ...prev]);
  };

  const clearNotification = (id: string) => {
    setNotifications(prev => prev.filter(n => n.id !== id));
  };

  const clearAll = () => {
    setNotifications([]);
  };

  return (
    <NotificationContext.Provider value={{ notifications, addNotification, clearNotification, clearAll }}>
      {children}
    </NotificationContext.Provider>
  );
};

export const useNotifications = (): NotificationContextType => {
  const context = useContext(NotificationContext);
  if (!context) {
    throw new Error('useNotifications must be used within a NotificationProvider');
  }
  return context;
};
"""

# contexts/LogContext.tsx
LOG_CONTEXT = """/* eslint-disable react-refresh/only-export-components */
// src/contexts/LogContext.tsx
import React, { createContext, useContext, useState } from 'react';
import type { ReactNode } from 'react';
import type { LogEntry } from '../types';

interface LogContextType {
  logs: LogEntry[];
  addLog: (message: string, source?: string) => void;
  clearLogs: () => void;
}

const LogContext = createContext<LogContextType | undefined>(undefined);

export const LogProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [logs, setLogs] = useState<LogEntry[]>([]);

  const addLog = (message: string, source?: string) => {
    const id = Date.now().toString() + Math.random().toString(36).slice(2, 8);
    setLogs(prev => [{ id, message, timestamp: Date.now(), source }, ...prev]);
  };

  const clearLogs = () => {
    setLogs([]);
  };

  return (
    <LogContext.Provider value={{ logs, addLog, clearLogs }}>
      {children}
    </LogContext.Provider>
  );
};

export const useLogs = (): LogContextType => {
  const context = useContext(LogContext);
  if (!context) {
    throw new Error('useLogs must be used within a LogProvider');
  }
  return context;
};
"""

# components/layout/Sidebar.tsx
SIDEBAR = """// src/components/layout/Sidebar.tsx
import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, Database, Cpu, Brain, Lightbulb, History, FileText,
  Settings, Info, Server, Boxes
} from 'lucide-react';

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

const Sidebar: React.FC<SidebarProps> = ({ isOpen, onClose }) => {
  const navItems = [
    { to: '/', label: 'Dashboard', icon: LayoutDashboard },
    { to: '/master-data', label: 'MASTER_DATA', icon: Database },
    { to: '/prediction-engines', label: 'Prediction Engines', icon: Cpu },
    { to: '/theresa', label: 'Theresa', icon: Brain },
    { to: '/theresa-intelligence', label: 'Theresa Intelligence', icon: Lightbulb },
    { to: '/history', label: 'History', icon: History },
    { to: '/reports', label: 'Reports', icon: FileText },
    { to: '/system', label: 'System', icon: Server },
    { to: '/settings', label: 'Settings', icon: Settings },
    { to: '/about', label: 'About', icon: Info },
  ];

  return (
    <>
      {isOpen && <div className="sidebar-overlay" onClick={onClose} />}
      <nav className={`sidebar ${isOpen ? 'open' : ''}`}>
        <div className="sidebar-brand">
          <Boxes size={28} />
          <span>TOC</span>
        </div>
        <ul className="sidebar-nav">
          {navItems.map(item => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                className={({ isActive }) => isActive ? 'active' : ''}
                onClick={() => { if (window.innerWidth < 768) onClose(); }}
              >
                <item.icon size={20} />
                <span>{item.label}</span>
              </NavLink>
            </li>
          ))}
        </ul>
        <div className="sidebar-footer">
          <div className="status-indicator">
            <span className="dot"></span>
            <span>Interface Ready</span>
          </div>
        </div>
      </nav>
    </>
  );
};

export default Sidebar;
"""

# components/layout/TopBar.tsx
TOPBAR = """// src/components/layout/TopBar.tsx
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
"""

# components/layout/StatusBar.tsx
STATUSBAR = """// src/components/layout/StatusBar.tsx
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
"""

# components/layout/BottomActionBar.tsx
BOTTOM_ACTION_BAR = """// src/components/layout/BottomActionBar.tsx
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
"""

# components/layout/AppShell.tsx
APPSHELL = """// src/components/layout/AppShell.tsx
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
"""

# components/ui/NotificationCenter.tsx
NOTIFICATION_CENTER = """// src/components/ui/NotificationCenter.tsx
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

  const getIcon = (type: Notification['type']) => {
    switch (type) {
      case 'success': return <CheckCircle size={16} color="#4ade80" />;
      case 'error': return <AlertCircle size={16} color="#f87171" />;
      case 'warning': return <AlertTriangle size={16} color="#fbbf24" />;
      default: return <Info size={16} color="#60a5fa" />;
    }
  };

  const formatTime = (ts: number) => {
    const diff = Date.now() - ts;
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
"""

# components/ui/ExecutionLogPanel.tsx
EXECUTION_LOG_PANEL = """// src/components/ui/ExecutionLogPanel.tsx
import React from 'react';
import { X, Clock } from 'lucide-react';
import { useLogs } from '../../contexts/LogContext';

interface ExecutionLogPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

const ExecutionLogPanel: React.FC<ExecutionLogPanelProps> = ({ isOpen, onClose }) => {
  const { logs, clearLogs } = useLogs();

  const formatTime = (ts: number) => {
    const diff = Date.now() - ts;
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
"""

# components/dashboard/StatusCard.tsx
STATUS_CARD = """// src/components/dashboard/StatusCard.tsx
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
"""

# components/dashboard/RecentActivity.tsx
RECENT_ACTIVITY = """// src/components/dashboard/RecentActivity.tsx
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
"""

# components/dashboard/QuickActions.tsx
QUICK_ACTIONS = """// src/components/dashboard/QuickActions.tsx
import React from 'react';
import { useNotifications } from '../../contexts/NotificationContext';
import { useLogs } from '../../contexts/LogContext';

const QuickActions: React.FC = () => {
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
    <div className="panel quick-actions">
      <h3>Quick Actions</h3>
      <div className="actions-grid">
        {actions.map((action) => (
          <button key={action.id} className="action-btn" onClick={() => handleAction(action.label)}>
            <span className="action-icon">{action.icon}</span>
            <span className="action-label">{action.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
};

export default QuickActions;
"""

# components/dashboard/SystemOverview.tsx
SYSTEM_OVERVIEW = """// src/components/dashboard/SystemOverview.tsx
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
"""

# pages/DashboardPage.tsx
DASHBOARD_PAGE = """// src/pages/DashboardPage.tsx
import React from 'react';
import { Cpu, Brain, Database, Calendar, Activity, Lightbulb } from 'lucide-react';
import StatusCard from '../components/dashboard/StatusCard';
import RecentActivity from '../components/dashboard/RecentActivity';
import QuickActions from '../components/dashboard/QuickActions';
import SystemOverview from '../components/dashboard/SystemOverview';

const DashboardPage: React.FC = () => {
  return (
    <div className="dashboard-page">
      <div className="stats-grid">
        <StatusCard
          title="Prediction Engines"
          value="Not connected"
          icon={<Cpu size={24} />}
          description="Status: Not connected"
          status="offline"
        />
        <StatusCard
          title="Theresa"
          value="Not connected"
          icon={<Brain size={24} />}
          description="Status: Not connected"
          status="offline"
        />
        <StatusCard
          title="MASTER_DATA"
          value="Not connected"
          icon={<Database size={24} />}
          description="Status: Not connected"
          status="offline"
        />
        <StatusCard
          title="Today's Predictions"
          value="0"
          icon={<Calendar size={24} />}
          description="Interface placeholder"
          status="mock"
        />
        <StatusCard
          title="System Health"
          value="Interface ready"
          icon={<Activity size={24} />}
          description="Status: Ready"
          status="ready"
        />
        <StatusCard
          title="Theresa Intelligence"
          value="Coming soon"
          icon={<Lightbulb size={24} />}
          description="Status: Coming soon"
          status="coming-soon"
        />
      </div>
      <div className="panels-grid">
        <RecentActivity />
        <QuickActions />
        <SystemOverview />
      </div>
    </div>
  );
};

export default DashboardPage;
"""

# Placeholder page template using safe tokens
PLACEHOLDER_PAGE = """// src/pages/__COMPONENT_NAME__.tsx
import React from 'react';

const __COMPONENT_NAME__: React.FC = () => {
  return (
    <div className="placeholder-page">
      <h1>__DISPLAY_NAME__</h1>
      <p>This is the __DISPLAY_NAME__ placeholder page. Content coming soon.</p>
      <p><em>Interface ready – no backend connected.</em></p>
    </div>
  );
};

export default __COMPONENT_NAME__;
"""

def make_placeholder_page(name: str, display: str) -> str:
    """Generate a placeholder TSX page without interpreting JSX braces."""
    return (
        PLACEHOLDER_PAGE
        .replace("__COMPONENT_NAME__", name)
        .replace("__DISPLAY_NAME__", display)
    )

# app/AppRouter.tsx
APP_ROUTER = """// src/app/AppRouter.tsx
import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AppShell from '../components/layout/AppShell';
import DashboardPage from '../pages/DashboardPage';
import MasterDataPage from '../pages/MasterDataPage';
import PredictionEnginesPage from '../pages/PredictionEnginesPage';
import TheresaPage from '../pages/TheresaPage';
import TheresaIntelligencePage from '../pages/TheresaIntelligencePage';
import HistoryPage from '../pages/HistoryPage';
import ReportsPage from '../pages/ReportsPage';
import SystemPage from '../pages/SystemPage';
import SettingsPage from '../pages/SettingsPage';
import AboutPage from '../pages/AboutPage';

const AppRouter: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="master-data" element={<MasterDataPage />} />
          <Route path="prediction-engines" element={<PredictionEnginesPage />} />
          <Route path="theresa" element={<TheresaPage />} />
          <Route path="theresa-intelligence" element={<TheresaIntelligencePage />} />
          <Route path="history" element={<HistoryPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="system" element={<SystemPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="about" element={<AboutPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
};

export default AppRouter;
"""

# App.tsx - removed unused React import
APP_TSX = """// src/App.tsx
import { ThemeProvider } from './contexts/ThemeContext';
import { NotificationProvider } from './contexts/NotificationContext';
import { LogProvider } from './contexts/LogContext';
import AppRouter from './app/AppRouter';

function App() {
  return (
    <ThemeProvider>
      <NotificationProvider>
        <LogProvider>
          <AppRouter />
        </LogProvider>
      </NotificationProvider>
    </ThemeProvider>
  );
}

export default App;
"""

# main.tsx - removed unused React import
MAIN_TSX = """// src/main.tsx
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
"""

# index.css - full styles with markers (dark mode fix applied)
INDEX_CSS = """/* TOC_PHASE2_START */
/* src/index.css - Complete TOC UI Styles */

/* ----- Reset & Base ----- */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

:root {
  /* Light theme variables */
  --bg-primary: #f8fafc;
  --bg-secondary: #ffffff;
  --bg-sidebar: #1e293b;
  --bg-topbar: #ffffff;
  --bg-statusbar: #f1f5f9;
  --bg-card: #ffffff;
  --bg-panel: #ffffff;
  --bg-action: #f1f5f9;
  --bg-hover: #e2e8f0;
  --text-primary: #0f172a;
  --text-secondary: #475569;
  --text-inverse: #f8fafc;
  --border-color: #e2e8f0;
  --shadow: 0 4px 12px rgba(0,0,0,0.05);
  --shadow-hover: 0 8px 24px rgba(0,0,0,0.12);
  --transition: 0.2s ease;
  --sidebar-width: 250px;
  --topbar-height: 60px;
  --statusbar-height: 40px;
  --bottombar-height: 64px;
  --panel-width: 360px;
}

[data-theme="dark"] {
  --bg-primary: #0f172a;
  --bg-secondary: #1e293b;
  --bg-sidebar: #0f172a;
  --bg-topbar: #1e293b;
  --bg-statusbar: #1e293b;
  --bg-card: #1e293b;
  --bg-panel: #1e293b;
  --bg-action: #334155;
  --bg-hover: #475569;
  --text-primary: #f1f5f9;
  --text-secondary: #94a3b8;
  --text-inverse: #f8fafc;
  --border-color: #334155;
  --shadow: 0 4px 12px rgba(0,0,0,0.3);
  --shadow-hover: 0 8px 24px rgba(0,0,0,0.5);
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
  background: var(--bg-primary);
  color: var(--text-primary);
  transition: background var(--transition), color var(--transition);
  margin: 0;
  padding: 0;
  height: 100vh;
  overflow: hidden;
}

#root {
  height: 100%;
}

/* ----- App Shell ----- */
.app-shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--bg-primary);
  position: relative;
}

/* ----- Sidebar ----- */
.sidebar {
  position: fixed;
  top: 0;
  left: 0;
  width: var(--sidebar-width);
  height: 100vh;
  background: var(--bg-sidebar);
  color: var(--text-inverse);
  display: flex;
  flex-direction: column;
  transition: transform 0.3s ease;
  z-index: 1000;
  transform: translateX(-100%);
}

.sidebar.open {
  transform: translateX(0);
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem 1.5rem;
  font-size: 1.25rem;
  font-weight: 700;
  border-bottom: 1px solid rgba(255,255,255,0.1);
}

.sidebar-nav {
  flex: 1;
  list-style: none;
  padding: 1rem 0;
  overflow-y: auto;
}

.sidebar-nav li {
  margin: 0.25rem 0;
}

.sidebar-nav a {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.6rem 1.5rem;
  color: rgba(255,255,255,0.7);
  text-decoration: none;
  transition: background 0.2s, color 0.2s;
  border-left: 3px solid transparent;
}

.sidebar-nav a:hover {
  background: rgba(255,255,255,0.05);
  color: #ffffff;
}

.sidebar-nav a.active {
  background: rgba(255,255,255,0.1);
  color: #ffffff;
  border-left-color: #3b82f6;
}

.sidebar-footer {
  padding: 1rem 1.5rem;
  border-top: 1px solid rgba(255,255,255,0.1);
  font-size: 0.875rem;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: rgba(255,255,255,0.7);
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #4ade80;
  display: inline-block;
}

.sidebar-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0,0,0,0.5);
  z-index: 999;
  display: block;
}

/* ----- TopBar ----- */
.topbar {
  height: var(--topbar-height);
  background: var(--bg-topbar);
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 1.5rem;
  flex-shrink: 0;
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.menu-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-primary);
  padding: 0.25rem;
  display: flex;
  align-items: center;
  justify-content: center;
}

.topbar-title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.icon-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-secondary);
  padding: 0.4rem;
  border-radius: 0.375rem;
  position: relative;
  transition: background 0.2s;
}

.icon-btn:hover {
  background: var(--bg-hover);
}

.notification-btn .badge {
  position: absolute;
  top: 0;
  right: 0;
  background: #ef4444;
  color: white;
  border-radius: 50%;
  width: 18px;
  height: 18px;
  font-size: 0.65rem;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* ----- Page Content ----- */
.page-content {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem;
  background: var(--bg-primary);
}

/* ----- StatusBar ----- */
.statusbar {
  height: var(--statusbar-height);
  background: var(--bg-statusbar);
  border-top: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  padding: 0 1.5rem;
  gap: 2rem;
  flex-shrink: 0;
  font-size: 0.875rem;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.status-label {
  color: var(--text-secondary);
}

.status-value {
  font-weight: 500;
}

/* ----- Bottom Action Bar ----- */
.bottom-action-bar {
  height: var(--bottombar-height);
  background: var(--bg-topbar);
  border-top: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: space-around;
  padding: 0 0.5rem;
  flex-shrink: 0;
  gap: 0.5rem;
}

.bottom-action-bar .action-btn {
  background: var(--bg-action);
  border: none;
  border-radius: 0.5rem;
  padding: 0.4rem 0.8rem;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  cursor: pointer;
  transition: background 0.2s, transform 0.1s;
  color: var(--text-primary);
  font-size: 0.75rem;
  flex: 1;
  justify-content: center;
  max-width: 150px;
}

.bottom-action-bar .action-btn:hover {
  background: var(--bg-hover);
  transform: scale(1.02);
}

.bottom-action-bar .action-icon {
  font-size: 1.2rem;
}

/* ----- Overlay Panels (Notifications & Logs) ----- */
.panel-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0,0,0,0.4);
  z-index: 2000;
  display: flex;
  justify-content: flex-end;
  animation: fadeIn 0.2s ease;
}

.panel-overlay-content {
  width: var(--panel-width);
  max-width: 90%;
  height: 100%;
  background: var(--bg-secondary);
  box-shadow: -4px 0 20px rgba(0,0,0,0.1);
  display: flex;
  flex-direction: column;
  animation: slideInRight 0.25s ease;
  border-left: 1px solid var(--border-color);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.panel-header h3 {
  margin: 0;
  font-size: 1.1rem;
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.panel-action-btn {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 0.8rem;
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
  transition: background 0.2s;
}

.panel-action-btn:hover {
  background: var(--bg-hover);
}

.panel-close-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-secondary);
  padding: 0.25rem;
  display: flex;
  align-items: center;
}

.panel-close-btn:hover {
  color: var(--text-primary);
}

.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 0.5rem 1rem;
}

.empty-state {
  color: var(--text-secondary);
  text-align: center;
  padding: 2rem 0;
  font-size: 0.95rem;
}

/* Notification List */
.notification-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.notification-item {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.75rem 0;
  border-bottom: 1px solid var(--border-color);
}

.notification-item:last-child {
  border-bottom: none;
}

.notification-icon {
  margin-top: 0.15rem;
}

.notification-content {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.notification-message {
  font-size: 0.9rem;
  color: var(--text-primary);
}

.notification-time {
  font-size: 0.7rem;
  color: var(--text-secondary);
  margin-top: 0.2rem;
}

.notification-dismiss {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-secondary);
  padding: 0.2rem;
  margin-top: 0.1rem;
}

.notification-dismiss:hover {
  color: var(--text-primary);
}

/* Log List */
.log-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.log-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--border-color);
  font-size: 0.85rem;
}

.log-item:last-child {
  border-bottom: none;
}

.log-time-icon {
  color: var(--text-secondary);
  flex-shrink: 0;
}

.log-content {
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.3rem 0.6rem;
}

.log-message {
  color: var(--text-primary);
}

.log-source {
  color: var(--text-secondary);
  font-size: 0.75rem;
}

.log-time {
  color: var(--text-secondary);
  font-size: 0.7rem;
  margin-left: auto;
}

/* Dashboard Stats Grid */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.stat-card {
  background: var(--bg-card);
  border-radius: 0.75rem;
  padding: 1.25rem 1.5rem;
  box-shadow: var(--shadow);
  display: flex;
  align-items: center;
  gap: 1rem;
  transition: transform 0.2s, box-shadow 0.2s;
  border-left: 4px solid #3b82f6;
}

.stat-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-hover);
}

.stat-icon {
  font-size: 2rem;
  line-height: 1;
  color: var(--text-primary);
}

.stat-content {
  display: flex;
  flex-direction: column;
}

.stat-title {
  font-size: 0.875rem;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: 500;
}

.stat-value {
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--text-primary);
}

.stat-description {
  font-size: 0.75rem;
  color: var(--text-secondary);
  margin-top: 0.25rem;
}

/* Status colors */
.stat-card.status-offline {
  border-left-color: #f87171;
}
.stat-card.status-offline .stat-value {
  color: #f87171;
}

.stat-card.status-ready {
  border-left-color: #4ade80;
}
.stat-card.status-ready .stat-value {
  color: #4ade80;
}

.stat-card.status-mock {
  border-left-color: #fbbf24;
}
.stat-card.status-mock .stat-value {
  color: #fbbf24;
}

.stat-card.status-coming-soon {
  border-left-color: #a78bfa;
}
.stat-card.status-coming-soon .stat-value {
  color: #a78bfa;
}

/* Panels Grid */
.panels-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 1.5rem;
  margin-top: 2rem;
}

.panel {
  background: var(--bg-panel);
  border-radius: 0.75rem;
  padding: 1.5rem;
  box-shadow: var(--shadow);
  transition: box-shadow 0.2s;
}

.panel h3 {
  font-size: 1.125rem;
  font-weight: 600;
  margin-top: 0;
  margin-bottom: 1rem;
  color: var(--text-primary);
}

/* Recent Activity */
.activity-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.activity-item {
  display: flex;
  justify-content: space-between;
  padding: 0.75rem 0;
  border-bottom: 1px solid var(--border-color);
}

.activity-item:last-child {
  border-bottom: none;
}

.activity-action {
  color: var(--text-primary);
}

.activity-time {
  color: var(--text-secondary);
  font-size: 0.875rem;
}

.activity-item.success .activity-action {
  color: #4ade80;
}
.activity-item.warning .activity-action {
  color: #fbbf24;
}
.activity-item.info .activity-action {
  color: #60a5fa;
}

/* Quick Actions */
.actions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 0.75rem;
}

.action-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 0.75rem 0.5rem;
  background: var(--bg-action);
  border: none;
  border-radius: 0.5rem;
  color: var(--text-primary);
  transition: background 0.2s, transform 0.1s;
  cursor: pointer;
  font-family: inherit;
  font-size: inherit;
}

.action-btn:hover {
  background: var(--bg-hover);
  transform: scale(1.02);
}

.action-btn:focus-visible {
  outline: 2px solid #3b82f6;
  outline-offset: 2px;
}

.action-icon {
  font-size: 1.5rem;
  margin-bottom: 0.25rem;
}

.action-label {
  font-size: 0.75rem;
  font-weight: 500;
  text-align: center;
}

/* System Overview */
.system-states {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.5rem 1.5rem;
}

.system-state {
  display: flex;
  justify-content: space-between;
  padding: 0.4rem 0;
  border-bottom: 1px solid var(--border-color);
}

.system-state:last-child {
  border-bottom: none;
}

.state-label {
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.state-status {
  font-weight: 500;
  font-size: 0.875rem;
}

/* Placeholder Pages */
.placeholder-page {
  padding: 2rem;
}

.placeholder-page h1 {
  font-size: 2rem;
  margin-bottom: 1rem;
}

.placeholder-page p {
  color: var(--text-secondary);
  line-height: 1.6;
}

/* Animations */
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideInRight {
  from { transform: translateX(100%); }
  to { transform: translateX(0); }
}

.dashboard-page {
  animation: fadeInUp 0.5s ease-out;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Responsive */
@media (min-width: 768px) {
  .sidebar {
    transform: translateX(0);
    position: relative;
  }
  .sidebar-overlay {
    display: none !important;
  }
  .menu-btn {
    display: none;
  }
}

@media (max-width: 767px) {
  .topbar-title {
    font-size: 1rem;
  }
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 0.75rem;
  }
  .stat-card {
    padding: 0.75rem 1rem;
    flex-direction: column;
    align-items: flex-start;
  }
  .stat-icon {
    font-size: 1.5rem;
  }
  .stat-value {
    font-size: 1.25rem;
  }
  .panels-grid {
    grid-template-columns: 1fr;
  }
  .actions-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .system-states {
    grid-template-columns: 1fr 1fr;
  }
  .bottom-action-bar .action-btn {
    font-size: 0.65rem;
    padding: 0.3rem 0.4rem;
    flex-direction: column;
    gap: 0.2rem;
  }
  .bottom-action-bar .action-icon {
    font-size: 1rem;
  }
  .bottom-action-bar .action-label {
    font-size: 0.6rem;
  }
  .panel-overlay-content {
    width: 100%;
    max-width: 100%;
  }
}

@media (min-width: 768px) and (max-width: 1024px) {
  .stats-grid {
    grid-template-columns: repeat(3, 1fr);
  }
  .panels-grid {
    grid-template-columns: 1fr 1fr;
  }
}
/* TOC_PHASE2_END */
"""

# ---- Main script ----
def main():
    print("TOC Phase 2 Final Safety Correction")
    root = find_project_root()
    if root is None:
        print("Error: Could not find project root (no package.json).")
        sys.exit(1)

    print(f"Project root: {root}")

    if not verify_project(root):
        sys.exit(1)

    # ----- Baseline build and lint check -----
    print("Running baseline build and lint before changes...")
    try:
        run_build_and_lint(root, phase="baseline")
    except RuntimeError as e:
        print(f"Baseline build or lint failed: {e}")
        sys.exit(1)

    # ----- Define all target files (relative to root) -----
    target_files = [
        Path("src/types/index.ts"),
        Path("src/contexts/ThemeContext.tsx"),
        Path("src/contexts/NotificationContext.tsx"),
        Path("src/contexts/LogContext.tsx"),
        Path("src/components/layout/Sidebar.tsx"),
        Path("src/components/layout/TopBar.tsx"),
        Path("src/components/layout/StatusBar.tsx"),
        Path("src/components/layout/BottomActionBar.tsx"),
        Path("src/components/layout/AppShell.tsx"),
        Path("src/components/ui/NotificationCenter.tsx"),
        Path("src/components/ui/ExecutionLogPanel.tsx"),
        Path("src/components/dashboard/StatusCard.tsx"),
        Path("src/components/dashboard/RecentActivity.tsx"),
        Path("src/components/dashboard/QuickActions.tsx"),
        Path("src/components/dashboard/SystemOverview.tsx"),
        Path("src/pages/DashboardPage.tsx"),
        Path("src/pages/MasterDataPage.tsx"),
        Path("src/pages/PredictionEnginesPage.tsx"),
        Path("src/pages/TheresaPage.tsx"),
        Path("src/pages/TheresaIntelligencePage.tsx"),
        Path("src/pages/HistoryPage.tsx"),
        Path("src/pages/ReportsPage.tsx"),
        Path("src/pages/SystemPage.tsx"),
        Path("src/pages/SettingsPage.tsx"),
        Path("src/pages/AboutPage.tsx"),
        Path("src/app/AppRouter.tsx"),
        Path("src/App.tsx"),
        Path("src/main.tsx"),
        Path("src/index.css"),
        Path("package.json"),
        Path("package-lock.json"),
    ]

    # ----- Record which files exist before modifications -----
    existing_before = {
        rel_path for rel_path in target_files
        if (root / rel_path).exists()
    }

    # ----- Backup all existing target files -----
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = root / "_backups" / f"phase2_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backed_up = set()
    for rel_path in target_files:
        src_path = root / rel_path
        if src_path.exists():
            dest = backup_dir / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dest)
            backed_up.add(rel_path)
    print(f"Backed up {len(backed_up)} files to {backup_dir}")

    # ----- Prepare file content map (excluding package.json and package-lock.json handled separately) -----
    file_contents = {
        Path("src/types/index.ts"): TYPES_INDEX,
        Path("src/contexts/ThemeContext.tsx"): THEME_CONTEXT,
        Path("src/contexts/NotificationContext.tsx"): NOTIFICATION_CONTEXT,
        Path("src/contexts/LogContext.tsx"): LOG_CONTEXT,
        Path("src/components/layout/Sidebar.tsx"): SIDEBAR,
        Path("src/components/layout/TopBar.tsx"): TOPBAR,
        Path("src/components/layout/StatusBar.tsx"): STATUSBAR,
        Path("src/components/layout/BottomActionBar.tsx"): BOTTOM_ACTION_BAR,
        Path("src/components/layout/AppShell.tsx"): APPSHELL,
        Path("src/components/ui/NotificationCenter.tsx"): NOTIFICATION_CENTER,
        Path("src/components/ui/ExecutionLogPanel.tsx"): EXECUTION_LOG_PANEL,
        Path("src/components/dashboard/StatusCard.tsx"): STATUS_CARD,
        Path("src/components/dashboard/RecentActivity.tsx"): RECENT_ACTIVITY,
        Path("src/components/dashboard/QuickActions.tsx"): QUICK_ACTIONS,
        Path("src/components/dashboard/SystemOverview.tsx"): SYSTEM_OVERVIEW,
        Path("src/pages/DashboardPage.tsx"): DASHBOARD_PAGE,
        Path("src/pages/MasterDataPage.tsx"): make_placeholder_page("MasterDataPage", "MASTER_DATA"),
        Path("src/pages/PredictionEnginesPage.tsx"): make_placeholder_page("PredictionEnginesPage", "Prediction Engines"),
        Path("src/pages/TheresaPage.tsx"): make_placeholder_page("TheresaPage", "Theresa"),
        Path("src/pages/TheresaIntelligencePage.tsx"): make_placeholder_page("TheresaIntelligencePage", "Theresa Intelligence"),
        Path("src/pages/HistoryPage.tsx"): make_placeholder_page("HistoryPage", "History"),
        Path("src/pages/ReportsPage.tsx"): make_placeholder_page("ReportsPage", "Reports"),
        Path("src/pages/SystemPage.tsx"): make_placeholder_page("SystemPage", "System"),
        Path("src/pages/SettingsPage.tsx"): make_placeholder_page("SettingsPage", "Settings"),
        Path("src/pages/AboutPage.tsx"): make_placeholder_page("AboutPage", "About"),
        Path("src/app/AppRouter.tsx"): APP_ROUTER,
        Path("src/App.tsx"): APP_TSX,
        Path("src/main.tsx"): MAIN_TSX,
    }

    # Handle index.css separately with preservation logic
    css_path = root / "src/index.css"
    existing_css = ""
    if css_path.exists():
        with open(css_path, "r", encoding="utf-8") as f:
            existing_css = f.read()

    marker_start = "/* TOC_PHASE2_START */"
    marker_end = "/* TOC_PHASE2_END */"
    new_css = INDEX_CSS

    # Check for both markers in correct order
    start_idx = existing_css.find(marker_start)
    end_idx = existing_css.find(marker_end)
    if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
        # Replace block between markers
        before = existing_css[:start_idx]
        after = existing_css[end_idx + len(marker_end):]
        new_css = before + new_css + after
    elif is_vite_starter_css(existing_css):
        # Replace entire file with our CSS
        new_css = new_css
    else:
        # Append at the end with two newlines
        if existing_css:
            new_css = existing_css.rstrip("\n") + "\n\n" + new_css
        else:
            new_css = new_css

    # Initialize temp_files before dependency installation for consistency
    temp_files: Set[Path] = set()

    # ----- Install dependencies (protected) -----
    try:
        dependency_status = install_deps(root)
    except RuntimeError as e:
        print(f"Dependency installation failed: {e}")
        cleanup_temp_files(temp_files)
        rollback(root, backup_dir, backed_up, existing_before, target_files)
        sys.exit(1)

    # ----- Write all files atomically using atomic_write_text -----
    written_files = []
    try:
        for rel_path, content in file_contents.items():
            destination = root / rel_path
            atomic_write_text(destination, content, temp_files)
            written_files.append(rel_path)

        # Write index.css
        destination = root / "src/index.css"
        atomic_write_text(destination, new_css, temp_files)
        written_files.append(Path("src/index.css"))

        print("All files written atomically.")

    except Exception as e:
        print(f"Error writing files: {e}")
        cleanup_temp_files(temp_files)
        rollback(root, backup_dir, backed_up, existing_before, target_files)
        sys.exit(1)

    # ---- Run build and lint after changes ----
    print("\nAll files written. Running build and lint after changes...")
    try:
        run_build_and_lint(root, phase="after")
    except RuntimeError as e:
        print(f"Build or lint failed after changes: {e}")
        cleanup_temp_files(temp_files)
        rollback(root, backup_dir, backed_up, existing_before, target_files)
        sys.exit(1)

    # Clean up any remaining temp files (should be none)
    cleanup_temp_files(temp_files)

    print("\n--- Phase 2 Final Safety Correction Successful ---")
    print(f"Backup directory: {backup_dir}")
    print(f"Files backed up: {len(backed_up)}")
    print(f"Files written: {len(written_files)}")
    print(f"Dependency status: {dependency_status}")
    print("Final build status: PASSED")
    print("Final lint status: PASSED")
    print("Phase 2 is complete.")
    print("Phase 3 was not started.")
    print("You can now start the development server with 'npm run dev'.")

if __name__ == "__main__":
    main()
