// src/components/layout/Sidebar.tsx
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
