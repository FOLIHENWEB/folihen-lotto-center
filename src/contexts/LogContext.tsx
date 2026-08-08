/* eslint-disable react-refresh/only-export-components */
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
