// src/types/index.ts
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
