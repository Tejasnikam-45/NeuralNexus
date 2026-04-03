import React, { useState, useEffect } from 'react';
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend
} from 'recharts';
import { TrendingUp, TrendingDown, Shield, AlertTriangle, CheckCircle, Clock } from 'lucide-react';
import Topbar from '../components/Topbar';
import { StatCard, RiskScoreBadge, ScoreBar, AlertSeverityDot } from '../components/UIKit';
import { HOURLY_VOLUME, SCORE_DISTRIBUTION, TRANSACTIONS, RECENT_ALERTS } from '../data/mockData';

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="custom-tooltip">
      <div style={{ fontWeight: 600, marginBottom: 6, color: 'var(--text-primary)' }}>{label}</div>
      {payload.map(p => (
        <div key={p.dataKey} style={{ color: p.color, fontSize: 12 }}>
          {p.name}: <b>{p.value.toLocaleString()}</b>
        </div>
      ))}
    </div>
  );
}

export default function Dashboard() {
  const [txns, setTxns] = useState(TRANSACTIONS);

  // simulate new transaction streaming in
  useEffect(() => {
    const int = setInterval(() => {
      const newTxn = {
        ...TRANSACTIONS[Math.floor(Math.random() * TRANSACTIONS.length)],
        id: `TXN-${Math.floor(8900 + Math.random() * 100)}`,
        time: new Date().toLocaleTimeString('en-US', { hour12: false }),
      };
      setTxns(prev => [newTxn, ...prev.slice(0, 9)]);
    }, 4000);
    return () => clearInterval(int);
  }, []);

  return (
    <div>
      <Topbar title="Operations Dashboard" subtitle="Real-time fraud intelligence — pre-transaction decisioning" />
      <div className="page">

        {/* STAT CARDS */}
        <div className="grid-4">
          <StatCard label="Transactions Today"  value="18,472"  delta="12.4% vs yesterday" deltaUp={true}  icon="💳" color="#6366f1" />
          <StatCard label="Blocked (Fraud)"     value="342"     delta="↑ 8 in last hour"   deltaUp={false} icon="🛡️" color="#f43f5e" />
          <StatCard label="MFA Challenged"      value="891"     delta="4.8% of volume"     deltaUp={null}  icon="🔐" color="#f59e0b" />
          <StatCard label="Avg Decision Time"   value="43ms"    delta="SLA: <100ms ✓"      deltaUp={true}  icon="⚡" color="#10b981" />
        </div>

        {/* CHARTS ROW */}
        <div className="grid-2">
          {/* Transaction Volume */}
          <div className="glass" style={{ padding: '20px 24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <span className="section-title">Transaction Volume</span>
              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Today by hour</span>
            </div>
            <ResponsiveContainer width="100%" height={210}>
              <AreaChart data={HOURLY_VOLUME}>
                <defs>
                  <linearGradient id="gradApproved" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#6366f1" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="gradBlocked" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#f43f5e" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#f43f5e" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                <XAxis dataKey="hour" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip content={<CustomTooltip />} />
                <Area type="monotone" dataKey="approved" stroke="#6366f1" strokeWidth={2} fill="url(#gradApproved)" name="Approved" />
                <Area type="monotone" dataKey="blocked"  stroke="#f43f5e" strokeWidth={2} fill="url(#gradBlocked)"  name="Blocked" />
                <Area type="monotone" dataKey="mfa"      stroke="#f59e0b" strokeWidth={2} fill="none"               name="MFA" strokeDasharray="4 2" />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Score Distribution */}
          <div className="glass" style={{ padding: '20px 24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <span className="section-title">Risk Score Distribution</span>
              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>All transactions</span>
            </div>
            <ResponsiveContainer width="100%" height={210}>
              <BarChart data={SCORE_DISTRIBUTION} barSize={18}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                <XAxis dataKey="range" tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="count" name="Transactions" radius={[4, 4, 0, 0]}>
                  {SCORE_DISTRIBUTION.map((entry, i) => (
                    <rect key={i} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* LIVE FEED + ALERTS */}
        <div className="grid-auto">
          {/* Live Transaction Table */}
          <div className="glass" style={{ overflow: 'hidden' }}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div className="live-dot" />
                <span className="section-title" style={{ fontSize: 12 }}>Live Transaction Feed</span>
              </div>
              <span className="mono" style={{ color: 'var(--text-muted)' }}>{txns.length} active</span>
            </div>
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
                    <th>Time</th>
                  </tr>
                </thead>
                <tbody>
                  {txns.slice(0, 8).map((txn, i) => (
                    <tr key={txn.id + i} className="animate-in" style={{ animationDelay: `${i * 30}ms` }}>
                      <td>
                        <span className="mono" style={{ color: 'var(--accent-indigo)' }}>{txn.id}</span>
                        {txn.ato && <span className="badge badge-ato" style={{ marginLeft: 6, fontSize: 9 }}>ATO</span>}
                      </td>
                      <td><span className="mono" style={{ color: 'var(--text-secondary)' }}>{txn.user}</span></td>
                      <td><span style={{ fontWeight: 600 }}>${txn.amount.toLocaleString()}</span></td>
                      <td><span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{txn.merchant}</span></td>
                      <td><ScoreBar score={txn.score} /></td>
                      <td><RiskScoreBadge score={txn.score} /></td>
                      <td><span className="mono" style={{ color: 'var(--text-muted)' }}>{txn.time}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* System Alerts */}
          <div className="glass" style={{ padding: '16px 20px' }}>
            <div style={{ marginBottom: 16 }}>
              <span className="section-title">System Alerts</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {RECENT_ALERTS.map(alert => (
                <div key={alert.id} className="glass glass-hover" style={{ padding: '12px 14px', borderRadius: 10 }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                    <AlertSeverityDot severity={alert.severity} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 12, fontWeight: 500, lineHeight: 1.4 }}>{alert.msg}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 3 }}>{alert.time}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Mini KPIs */}
            <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--border)' }}>
              <span className="section-title" style={{ marginBottom: 12, display: 'block' }}>Model Health</span>
              {[
                { label: 'Precision', val: '96.5%', color: '#10b981' },
                { label: 'Recall', val: '94.7%', color: '#6366f1' },
                { label: 'F1 Score', val: '95.6%', color: '#8b5cf6' },
                { label: 'Model Ver', val: 'v2.4.1', color: '#06b6d4' },
              ].map(kpi => (
                <div key={kpi.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0' }}>
                  <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{kpi.label}</span>
                  <span style={{ fontSize: 12, fontWeight: 700, color: kpi.color, fontFamily: 'var(--font-mono)' }}>{kpi.val}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
