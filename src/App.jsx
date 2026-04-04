import React, { useState } from 'react';
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import LiveFeed from './pages/LiveFeed';
import ATOChains from './pages/ATOChains';
import FraudGraph from './pages/FraudGraph';
import AnalystReview from './pages/AnalystReview';
import FraudSimulator from './pages/FraudSimulator';
import ModelPerformance from './pages/ModelPerformance';
import Architecture from './pages/Architecture';

const PAGES = {
  dashboard:   Dashboard,
  live:        LiveFeed,
  ato:         ATOChains,
  graph:       FraudGraph,
  analyst:     AnalystReview,
  simulator:   FraudSimulator,
  performance: ModelPerformance,
  architecture: Architecture,
};

export default function App() {
  // Deep-linking: Initialize from URL (?tab=performance)
  const params = new URLSearchParams(window.location.search);
  const initialPage = params.get('tab');
  
  const [activePage, setActivePage] = React.useState(initialPage && PAGES[initialPage] ? initialPage : 'dashboard');
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
