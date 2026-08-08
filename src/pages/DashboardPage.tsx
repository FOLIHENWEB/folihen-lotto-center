// src/pages/DashboardPage.tsx
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
