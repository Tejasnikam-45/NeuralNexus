import React from 'react';
import Topbar from '../components/Topbar';

export default function Architecture() {
  return (
    <div>
      <Topbar title="System Architecture" subtitle="Real-time Execution & Decision Flow" />
      <div className="page" style={{ height: 'calc(100vh - 80px)', display: 'flex', flexDirection: 'column' }}>
        
        {/* Pitch Instructions / Legend Banner */}
        <div style={{
          padding: '14px 20px',
          background: 'linear-gradient(135deg, rgba(99,102,241,0.1), rgba(139,92,246,0.08))',
          border: '1px solid rgba(99,102,241,0.2)',
          borderRadius: 12, fontSize: 13, color: 'var(--text-secondary)',
          display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16
        }}>
          <span style={{ fontSize: 20 }}>🧠</span>
          <span>
            <b style={{ color: 'var(--text-primary)' }}>Pre-Authorization Security:</b> This live animation demonstrates our core value proposition. 
            When a transaction hits the API, we evaluate <b style={{ color: '#818cf8' }}>Redis Velocity</b>, run <b style={{ color: '#facc15' }}>Hybrid Rules</b>, 
            and execute our <b style={{ color: '#34d399' }}>ML Ensemble</b> to explicitly abort fraud <b>before</b> it reaches the Core Banking Ledger.
          </span>
        </div>

        {/* Embedded Animation Frame */}
        <div className="glass" style={{ flex: 1, padding: 0, overflow: 'hidden', borderRadius: 12 }}>
          <iframe 
            src="/data_flow_animation.html" 
            style={{ width: '100%', height: '100%', border: 'none', background: '#0f172a' }}
            title="NeuralNexus Data Flow Animation"
          />
        </div>

      </div>
    </div>
  );
}
