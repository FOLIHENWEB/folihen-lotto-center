// src/app/AppRouter.tsx
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
