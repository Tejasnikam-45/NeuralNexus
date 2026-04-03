import React, { useState, useRef } from 'react';
import Topbar from '../components/Topbar';
import { RiskScoreBadge, ScoreBar } from '../components/UIKit';
import { simulateTransactions } from '../api';
import { Play, Square, RotateCcw, Zap } from 'lucide-react';

const SCENARIOS = [
  { id: 'ato_attack',    label: 'Full ATO Attack',     desc: 'Login hijack → profile change → high-value crypto buy', icon: '🔐', duration: '3.6s' },
  { id: 'card_fraud',    label: 'Card Fraud Burst',    desc: '10 transactions in 60s from new location', icon: '💳', duration: '8s' },
  { id: 'fraud_ring',    label: 'Fraud Ring Probe',    desc: '3 accounts, 1 shared device, coordinated NFT purchases', icon: '🕸️', duration: '5s' },
  { id: 'legit_spike',   label: 'Legit User Spike',    desc: 'High volume normal user — ensure no false positives', icon: '✅', duration: '4s' },
  { id: 'sim_swap',      label: 'SIM Swap + Bypass',   desc: 'MFA bypassed via SIM swap, unusual wire transfer', icon: '📱', duration: '2.1s' },
];

function generateTxns(scenario) {
  const base = { device: 'New Device', location: 'Lagos, NG', flags: ['ATO chain', 'new device'] };
  const txns = [];
  const count = scenario === 'card_fraud' ? 8 : scenario === 'fraud_ring' ? 6 : 4;
  for (let i = 0; i < count; i++) {
    txns.push({
      id: `SIM-${1000 + i}`,
      user: `sim_user_${['A','B','C'][i % 3]}`,
      amount: Math.floor(500 + Math.random() * 5000),
      merchant: ['NFT Marketplace','Crypto Exchange','Wire Transfer','FX Trader'][i % 4],
      type: scenario,
      score: Math.floor(45 + Math.random() * 50),
      decision: ['approve','mfa','block'][Math.floor(Math.random() * 3)],
      device: i === 0 ? 'New Device' : 'Known',
      location: base.location,
      time: new Date(Date.now() + i * 800).toLocaleTimeString('en-US', { hour12: false }),
      ato: scenario === 'ato_attack' || scenario === 'sim_swap',
      flags: i < 2 ? base.flags : [],
    });
  }
  return txns;
}

export default function FraudSimulator() {
  const [selected, setSelected] = useState(SCENARIOS[0]);
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState([]);
  const [speed, setSpeed] = useState(600);
  const intRef = useRef(null);

  const runSimulation = async () => {
    setRunning(true);
    setResults([]);
    
    // Map scenario to fraud_pct and count for the API
    const count = selected.id === 'card_fraud' ? 8 : selected.id === 'fraud_ring' ? 6 : 4;
    const fraudPct = selected.id === 'legit_spike' ? 0.0 : 0.8;
    
    try {
      const resp = await simulateTransactions(count, fraudPct);
      const txns = resp.results;
      
      let i = 0;
      intRef.current = setInterval(() => {
        if (i >= txns.length) {
          clearInterval(intRef.current);
          setRunning(false);
          return;
        }
        const t = txns[i];
        setResults(prev => [...prev, {
          id: t.transaction_id,
          user: t.user_id,
          amount: t.amount_usd,
          merchant: selected.id === 'legit_spike' ? 'Online Store' : 'Suspicious Merchant',
          score: Math.round(t.score),
          decision: t.decision,
          ato: t.simulated_fraud,
          time: new Date().toLocaleTimeString('en-US', { hour12: false })
        }]);
        i++;
      }, speed);
    } catch (err) {
      console.error(err);
      setRunning(false);
    }
  };

  const stop = () => {
    clearInterval(intRef.current);
    setRunning(false);
  };

  const reset = () => {
    stop();
    setResults([]);
  };

  const blocked  = results.filter(r => r.score >= 70).length;
  const mfa      = results.filter(r => r.score >= 40 && r.score < 70).length;
  const approved = results.filter(r => r.score < 40).length;

  return (
    <div>
      <Topbar title="Fraud Simulator" subtitle="Replay attack scenarios against the live model" />
      <div className="page">

        <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: 20 }}>

          {/* Scenario Panel */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div className="glass" style={{ padding: '18px 20px' }}>
              <div className="section-title" style={{ marginBottom: 14 }}>Attack Scenarios</div>
              {SCENARIOS.map(s => (
                <div
                  key={s.id}
                  onClick={() => !running && setSelected(s)}
                  style={{
                    padding: '12px 14px', borderRadius: 8, marginBottom: 8, cursor: 'pointer',
                    background: selected.id === s.id ? 'rgba(99,102,241,0.15)' : 'rgba(255,255,255,0.02)',
                    border: `1px solid ${selected.id === s.id ? 'rgba(99,102,241,0.4)' : 'var(--border)'}`,
                    transition: 'all 0.2s',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <span style={{ fontSize: 18 }}>{s.icon}</span>
                    <span style={{ fontWeight: 600, fontSize: 13 }}>{s.label}</span>
                    <span className="mono" style={{ fontSize: 10, color: 'var(--text-muted)', marginLeft: 'auto' }}>{s.duration}</span>
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginLeft: 26 }}>{s.desc}</div>
                </div>
              ))}
            </div>

            <div className="glass" style={{ padding: '18px 20px' }}>
              <div className="section-title" style={{ marginBottom: 12 }}>Simulation Speed</div>
              <div style={{ display: 'flex', gap: 8 }}>
                {[{ label: 'Slow', ms: 1200 }, { label: 'Normal', ms: 600 }, { label: 'Fast', ms: 200 }].map(opt => (
                  <button
                    key={opt.ms}
                    onClick={() => setSpeed(opt.ms)}
                    className="btn"
                    style={{
                      flex: 1, justifyContent: 'center', fontSize: 11,
                      background: speed === opt.ms ? 'rgba(99,102,241,0.2)' : 'transparent',
                      border: `1px solid ${speed === opt.ms ? 'rgba(99,102,241,0.4)' : 'var(--border)'}`,
                      color: speed === opt.ms ? '#818cf8' : 'var(--text-secondary)'
                    }}
                  >{opt.label}</button>
                ))}
              </div>

              <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
                {!running ? (
                  <button className="btn btn-primary" style={{ flex: 1, justifyContent: 'center' }} onClick={runSimulation}>
                    <Play size={13} /> Run Scenario
                  </button>
                ) : (
                  <button className="btn btn-danger" style={{ flex: 1, justifyContent: 'center' }} onClick={stop}>
                    <Square size={13} /> Stop
                  </button>
                )}
                <button className="btn btn-ghost" onClick={reset}><RotateCcw size={14} /></button>
              </div>
            </div>

            {/* Live KPIs */}
            {results.length > 0 && (
              <div className="glass" style={{ padding: '18px 20px' }}>
                <div className="section-title" style={{ marginBottom: 12 }}>Live Results</div>
                {[
                  { label: 'Transactions', val: results.length, color: '#6366f1' },
                  { label: 'Blocked', val: blocked, color: '#f43f5e' },
                  { label: 'MFA Challenged', val: mfa, color: '#f59e0b' },
                  { label: 'Approved', val: approved, color: '#10b981' },
                  { label: 'Avg Score', val: Math.round(results.reduce((a, r) => a + r.score, 0) / results.length), color: 'var(--text-primary)' },
                ].map(kpi => (
                  <div key={kpi.label} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--border)', fontSize: 12 }}>
                    <span style={{ color: 'var(--text-secondary)' }}>{kpi.label}</span>
                    <span style={{ fontWeight: 700, color: kpi.color, fontFamily: 'var(--font-mono)' }}>{kpi.val}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Results Feed */}
          <div className="glass" style={{ overflow: 'hidden' }}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 10 }}>
              {running && <div className="live-dot" />}
              <span className="section-title">
                {running ? 'Simulation Running…' : results.length > 0 ? 'Simulation Complete' : 'Awaiting Simulation'}
              </span>
              {running && (
                <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                  {results.length} events
                </span>
              )}
            </div>

            {results.length === 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 380, color: 'var(--text-muted)' }}>
                <div style={{ fontSize: 48, marginBottom: 12 }}>{selected.icon}</div>
                <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>{selected.label}</div>
                <div style={{ fontSize: 12, maxWidth: 280, textAlign: 'center' }}>{selected.desc}</div>
                <button className="btn btn-primary" style={{ marginTop: 20 }} onClick={runSimulation}>
                  <Zap size={13} /> Start Simulation
                </button>
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>TXN ID</th>
                      <th>User</th>
                      <th>Amount</th>
                      <th>Merchant</th>
                      <th>Risk Score</th>
                      <th>Decision</th>
                      <th>Latency</th>
                      <th>Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...results].reverse().map((txn, i) => (
                      <tr key={txn.id + i} className="animate-in">
                        <td>
                          <span className="mono" style={{ color: '#818cf8' }}>{txn.id}</span>
                          {txn.ato && <span className="badge badge-ato" style={{ marginLeft: 6, fontSize: 9 }}>ATO</span>}
                        </td>
                        <td><span className="mono" style={{ fontSize: 11 }}>{txn.user}</span></td>
                        <td><span style={{ fontWeight: 700 }}>${txn.amount.toLocaleString()}</span></td>
                        <td style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{txn.merchant}</td>
                        <td><ScoreBar score={txn.score} /></td>
                        <td><RiskScoreBadge score={txn.score} /></td>
                        <td><span className="mono" style={{ color: '#10b981', fontSize: 11 }}>{Math.floor(35 + Math.random() * 25)}ms</span></td>
                        <td><span className="mono" style={{ color: 'var(--text-muted)', fontSize: 11 }}>{txn.time}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

      </div>
    </div>
  );
}
