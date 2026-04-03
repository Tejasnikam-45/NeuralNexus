import React, { useState, useEffect } from 'react';
import Topbar from '../components/Topbar';
import { RiskScoreBadge, ScoreBar } from '../components/UIKit';
import { TRANSACTIONS, SHAP_FEATURES } from '../data/mockData';
import { useLiveWebSocket } from '../api';
import { X, ChevronRight, Cpu, MapPin, Monitor, Clock, AlertOctagon } from 'lucide-react';

function ShapWaterfall({ features }) {
  const max = Math.max(...features.map(f => Math.abs(f.value)));
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {features.map(f => (
        <div key={f.name} className="shap-row">
          <span className="shap-label">{f.name}</span>
          <div className="shap-bar-wrap">
            <div
              className="shap-bar-fill"
              style={{
                width: `${(Math.abs(f.value) / max) * 100}%`,
                background: f.positive
                  ? 'linear-gradient(90deg, #f43f5e, #fb7185)'
                  : 'linear-gradient(90deg, #10b981, #34d399)',
              }}
            />
          </div>
          <span className="shap-value" style={{ color: f.positive ? '#f43f5e' : '#10b981' }}>
            {f.positive ? '+' : '-'}{Math.abs(f.value).toFixed(2)}
          </span>
        </div>
      ))}
    </div>
  );
}

function TxnDetailPanel({ txn, onClose }) {
  if (!txn) return null;
  const score = txn.score;
  const ringColor = score >= 70 ? '#f43f5e' : score >= 40 ? '#f59e0b' : '#10b981';
  const circumference = 2 * Math.PI * 52;
  const dash = (score / 100) * circumference;

  return (
    <div style={{
      position: 'fixed', right: 0, top: 0, bottom: 0, width: 440,
      background: 'rgba(9,13,26,0.97)', borderLeft: '1px solid var(--border-accent)',
      backdropFilter: 'blur(30px)', zIndex: 200, overflowY: 'auto',
      animation: 'fadeInUp 0.25s ease',
    }}>
      {/* Header */}
      <div style={{ padding: '20px 24px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: 15 }}>{txn.id}</div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>{txn.user} · {txn.time}</div>
        </div>
        <button onClick={onClose} className="btn btn-ghost" style={{ padding: '6px 8px' }}><X size={16} /></button>
      </div>

      <div style={{ padding: '24px' }}>
        {/* Score Ring */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 24, marginBottom: 28 }}>
          <div className="score-ring">
            <svg width={120} height={120}>
              <circle cx={60} cy={60} r={52} stroke="rgba(255,255,255,0.05)" strokeWidth={10} fill="none" />
              <circle
                cx={60} cy={60} r={52}
                stroke={ringColor} strokeWidth={10} fill="none"
                strokeDasharray={`${dash} ${circumference - dash}`}
                strokeLinecap="round"
                transform="rotate(-90 60 60)"
                style={{ filter: `drop-shadow(0 0 8px ${ringColor})`, transition: 'stroke-dasharray 0.5s ease' }}
              />
            </svg>
            <div style={{ position: 'absolute', textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 900, color: ringColor, lineHeight: 1 }}>{score}</div>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Risk</div>
            </div>
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ marginBottom: 8 }}><RiskScoreBadge score={score} /></div>
            <div style={{ fontSize: 22, fontWeight: 800, color: ringColor }}>
              ${txn.amount.toLocaleString()}
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>{txn.merchant}</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>{txn.type}</div>
          </div>
        </div>

        {/* Signal Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 24 }}>
          {[
            { icon: <MapPin size={13} />, label: 'Location', val: txn.location },
            { icon: <Monitor size={13} />, label: 'Device', val: txn.device },
            { icon: <Clock size={13} />, label: 'Time', val: txn.time },
            { icon: <Cpu size={13} />, label: 'Model Score', val: `${score}/100` },
          ].map(item => (
            <div key={item.label} style={{
              background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)',
              borderRadius: 8, padding: '10px 12px'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 5, color: 'var(--text-muted)', fontSize: 11, marginBottom: 4 }}>
                {item.icon} {item.label}
              </div>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{item.val}</div>
            </div>
          ))}
        </div>

        {/* Flags */}
        {txn.flags.length > 0 && (
          <div style={{ marginBottom: 24 }}>
            <div className="section-title" style={{ marginBottom: 10 }}>Risk Flags</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {txn.flags.map(flag => (
                <div key={flag} style={{
                  display: 'flex', alignItems: 'center', gap: 5,
                  background: 'rgba(244,63,94,0.1)', border: '1px solid rgba(244,63,94,0.25)',
                  borderRadius: 6, padding: '4px 10px', fontSize: 12, color: '#fb7185'
                }}>
                  <AlertOctagon size={11} /> {flag}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* SHAP Explanations */}
        <div style={{ marginBottom: 24 }}>
          <div className="section-title" style={{ marginBottom: 12 }}>SHAP Explanations — Why this score?</div>
          <div style={{
            background: 'rgba(244,63,94,0.06)', border: '1px solid rgba(244,63,94,0.15)',
            borderRadius: 8, padding: '12px 14px', marginBottom: 14, fontSize: 12, color: '#fca5a5', lineHeight: 1.6
          }}>
            🔍 Top reason: <b>{txn.merchant}</b>
          </div>
          {/* Note: In a real system, the features would be pulled out of txn.raw.shap_features. Currently using mock SHAP_FEATURES for aesthetic purposes */}
          <ShapWaterfall features={txn.raw?.shap_features || SHAP_FEATURES} />
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-success" style={{ flex: 1 }}>✓ Mark Safe</button>
          <button className="btn btn-danger" style={{ flex: 1 }}>✗ Confirm Fraud</button>
        </div>
        <button className="btn btn-ghost" style={{ width: '100%', marginTop: 8, justifyContent: 'center' }}>
          Add to Retraining Queue
        </button>
      </div>
    </div>
  );
}

export default function LiveFeed() {
  const [selected, setSelected] = useState(null);
  const [filter, setFilter] = useState('all');
  const { messages: liveTxns, isConnected } = useLiveWebSocket();

  // If no live transactions yet, use a slice of mock data as a fallback/skeleton
  const baseTxns = liveTxns.length > 0 ? liveTxns.map(msg => ({
    id: msg.transaction_id,
    user: msg.user_id,
    amount: msg.amount_usd,
    merchant: msg.top_reason || "Online Store", // mapped feature name
    type: "ecommerce", // static or derive if possible
    location: "Unknown", 
    device: "Unknown",
    score: msg.score,
    decision: msg.decision,
    flags: ["Model Flag"], // Replace with actual flags if any
    time: new Date(msg.timestamp_utc * 1000).toLocaleTimeString('en-US', { hour12: false }),
    // store raw for details
    raw: msg
  })) : TRANSACTIONS.slice(0, 5);

  const filtered = filter === 'all' ? baseTxns : baseTxns.filter(t => t.decision === filter);

  return (
    <div>
      <Topbar title="Live Transaction Feed" subtitle="Scoring in <100ms · Pre-transaction decisioning active" />
      <div className="page">

        {/* Filter Bar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {['all', 'approve', 'mfa', 'block'].map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className="btn"
              style={{
                background: filter === f ? 'rgba(99,102,241,0.2)' : 'transparent',
                border: `1px solid ${filter === f ? 'rgba(99,102,241,0.4)' : 'var(--border)'}`,
                color: filter === f ? '#818cf8' : 'var(--text-secondary)',
                textTransform: 'capitalize', padding: '7px 16px', fontSize: 12
              }}
            >
              {f === 'all' ? '🌐 All' : f === 'approve' ? '✅ Approved' : f === 'mfa' ? '🔐 MFA' : '🚫 Blocked'}
            </button>
          ))}
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
            <div className="live-dot" />
            <span style={{ fontSize: 12, color: '#10b981', fontFamily: 'var(--font-mono)' }}>Streaming live</span>
          </div>
        </div>

        {/* Full Table */}
        <div className="glass" style={{ overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>TXN ID</th>
                  <th>User</th>
                  <th>Amount</th>
                  <th>Merchant</th>
                  <th>Type</th>
                  <th>Location</th>
                  <th>Device</th>
                  <th>Risk Score</th>
                  <th>Decision</th>
                  <th>Flags</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((txn, i) => (
                  <tr
                    key={txn.id + i}
                    className="animate-in"
                    style={{ cursor: 'pointer', animationDelay: `${i * 20}ms` }}
                    onClick={() => setSelected(txn)}
                  >
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span className="mono" style={{ color: '#818cf8' }}>{txn.id}</span>
                        {txn.ato && <span className="badge badge-ato" style={{ fontSize: 9 }}>ATO</span>}
                      </div>
                    </td>
                    <td><span className="mono" style={{ fontSize: 11 }}>{txn.user}</span></td>
                    <td><span style={{ fontWeight: 700, color: txn.amount > 1000 ? '#fb923c' : 'inherit' }}>${txn.amount.toLocaleString()}</span></td>
                    <td style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{txn.merchant}</td>
                    <td style={{ color: 'var(--text-muted)', fontSize: 11 }}>{txn.type}</td>
                    <td style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{txn.location}</td>
                    <td>
                      <span style={{
                        fontSize: 11, padding: '2px 8px', borderRadius: 4, fontWeight: 500,
                        background: txn.device === 'New Device' ? 'rgba(244,63,94,0.1)' : 'rgba(16,185,129,0.08)',
                        color: txn.device === 'New Device' ? '#f43f5e' : '#10b981',
                      }}>{txn.device}</span>
                    </td>
                    <td><ScoreBar score={txn.score} /></td>
                    <td><RiskScoreBadge score={txn.score} /></td>
                    <td>
                      <div style={{ display: 'flex', gap: 4 }}>
                        {txn.flags.slice(0, 2).map(f => (
                          <span key={f} style={{
                            fontSize: 10, background: 'rgba(244,63,94,0.1)', color: '#fca5a5',
                            border: '1px solid rgba(244,63,94,0.2)', borderRadius: 4, padding: '1px 6px'
                          }}>{f}</span>
                        ))}
                        {txn.flags.length > 2 && <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>+{txn.flags.length - 2}</span>}
                      </div>
                    </td>
                    <td><span className="mono" style={{ color: 'var(--text-muted)', fontSize: 11 }}>{txn.time}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {selected && <TxnDetailPanel txn={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
