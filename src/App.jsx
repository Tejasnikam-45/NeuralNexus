import React, { useState } from 'react';
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import LiveFeed from './pages/LiveFeed';
import ATOChains from './pages/ATOChains';
import FraudGraph from './pages/FraudGraph';
import AnalystReview from './pages/AnalystReview';
import FraudSimulator from './pages/FraudSimulator';
import ModelPerformance from './pages/ModelPerformance';

const PAGES = {
  dashboard:   Dashboard,
  live:        LiveFeed,
  ato:         ATOChains,
  graph:       FraudGraph,
  analyst:     AnalystReview,
  simulator:   FraudSimulator,
  performance: ModelPerformance,
};

export default function App() {
  const [activePage, setActivePage] = useState('dashboard');
  const PageComponent = PAGES[activePage] || Dashboard;

  return (
    <div className="layout">
      <Sidebar active={activePage} onNav={setActivePage} />
      <main className="main-content">
        <PageComponent />
      </main>
    </div>
  );
}
