import React from 'react';

export function RiskScoreBadge({ score }) {
  const getDecision = (s) => {
    if (s < 40) return { label: 'APPROVE', cls: 'badge-approve' };
    if (s < 70) return { label: 'MFA', cls: 'badge-mfa' };
    return { label: 'BLOCK', cls: 'badge-block' };
  };
  const { label, cls } = getDecision(score);
  return <span className={`badge ${cls}`}>{label}</span>;
}

export function ScoreBar({ score }) {
  const color = score >= 70 ? '#f43f5e' : score >= 40 ? '#f59e0b' : '#10b981';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 120 }}>
      <div className="progress-bar" style={{ flex: 1 }}>
        <div
          className="progress-fill"
          style={{ width: `${score}%`, background: color, boxShadow: `0 0 8px ${color}60` }}
        />
      </div>
      <span
        className="mono"
        style={{ color, fontWeight: 700, fontSize: 13, minWidth: 24 }}
      >{score}</span>
    </div>
  );
}

export function StatCard({ label, value, delta, deltaUp, icon, color }) {
  return (
    <div className="glass glass-hover stat-card">
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <span className="label">{label}</span>
        <div style={{
          width: 34, height: 34, borderRadius: 8, display: 'flex',
          alignItems: 'center', justifyContent: 'center', fontSize: 16,
          background: `${color}18`, border: `1px solid ${color}30`
        }}>{icon}</div>
      </div>
      <div className="value" style={{ color }}>{value}</div>
      {delta && (
        <div className={`delta ${deltaUp ? 'delta-up' : 'delta-down'}`}>
          {deltaUp ? '▲' : '▼'} {delta}
        </div>
      )}
    </div>
  );
}

export function AlertSeverityDot({ severity }) {
  const map = {
    critical: '#f43f5e',
    high:     '#fb923c',
    medium:   '#f59e0b',
    info:     '#6366f1',
  };
  return (
    <div style={{
      width: 8, height: 8, borderRadius: '50%',
      background: map[severity] || '#64748b',
      flexShrink: 0,
      boxShadow: severity === 'critical' ? `0 0 6px ${map.critical}` : 'none',
    }} />
  );
}
