import React, { useState, useEffect, useMemo } from 'react';
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend
} from 'recharts';
import { TrendingUp, TrendingDown, Shield, AlertTriangle, CheckCircle, Clock } from 'lucide-react';
import Topbar from '../components/Topbar';
import { StatCard, RiskScoreBadge, ScoreBar, AlertSeverityDot } from '../components/UIKit';
import { HOURLY_VOLUME, SCORE_DISTRIBUTION, TRANSACTIONS, RECENT_ALERTS } from '../data/mockData';
import { fetchStats, fetchModelPerformance, useLiveWebSocket } from '../api';

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
  const [stats, setStats] = useState(null);
  const [performance, setPerformance] = useState(null);
  const { messages: liveTxns, isConnected } = useLiveWebSocket();

  // Initial load
  useEffect(() => {
    fetchStats().then(setStats).catch(console.error);
    fetchModelPerformance().then(data => {
      // Backend shape: { eval_metrics: { aucpr, roc_auc, best_f1, best_threshold }, model_version }
      // Note: precision/recall are NOT saved in eval_metrics.json — use aucpr and roc_auc instead
      setPerformance({
        aucpr:           data.eval_metrics?.aucpr,
        roc_auc:         data.eval_metrics?.roc_auc,
        f1_score:        data.eval_metrics?.best_f1,
        current_version: data.model_version,
      });
    }).catch(console.error);
  }, []);

  // For charts and fallback table we keep mockData as placeholders
  const displayTxns = liveTxns.length > 0 ? liveTxns.map(msg => ({
    id: msg?.transaction_id?.slice(0, 8) || "TXN-???",
    user: msg?.user_id || "unknown",
    amount: msg?.amount_usd || 0,
    merchant: msg?.top_reason || "Online Store", 
    score: msg?.score || 0,
    decision: msg?.decision || "approve",
    time: msg?.timestamp_utc ? new Date(msg.timestamp_utc * 1000).toLocaleTimeString('en-US', { hour12: false }) : "--",
  })) : TRANSACTIONS;

  // 1. Dynamic Hourly Volume
  const hourlyData = useMemo(() => {
    if (liveTxns.length === 0) return HOURLY_VOLUME;
    // Bucket the last N transactions by short time intervals to show "recent" activity
    const buckets = {};
    liveTxns.forEach(t => {
      const date = new Date(t.timestamp_utc * 1000);
      const hour = date.getHours().toString().padStart(2, '0') + ':00';
      if (!buckets[hour]) buckets[hour] = { hour, approved: 0, blocked: 0, mfa: 0 };
      if (t.decision === 'block') buckets[hour].blocked++;
      else if (t.decision === 'mfa') buckets[hour].mfa++;
      else buckets[hour].approved++;
    });
    return Object.values(buckets).sort((a, b) => a.hour.localeCompare(b.hour));
  }, [liveTxns]);

  // 2. Dynamic Score Distribution
  const scoreDist = useMemo(() => {
    if (liveTxns.length === 0) return SCORE_DISTRIBUTION;
    const bins = [
      { range: '0-10',  min: 0, max: 10,  count: 0, fill: '#10b981' },
      { range: '10-20', min: 10, max: 20, count: 0, fill: '#10b981' },
      { range: '20-30', min: 20, max: 30, count: 0, fill: '#34d399' },
      { range: '30-40', min: 30, max: 40, count: 0, fill: '#6ee7b7' },
      { range: '40-50', min: 40, max: 50, count: 0, fill: '#f59e0b' },
      { range: '50-60', min: 50, max: 60, count: 0, fill: '#fbbf24' },
      { range: '60-70', min: 60, max: 70, count: 0, fill: '#fb923c' },
      { range: '70-80', min: 70, max: 80, count: 0, fill: '#f43f5e' },
      { range: '80-90', min: 80, max: 90, count: 0, fill: '#e11d48' },
      { range: '90+',   min: 90, max: 101,count: 0, fill: '#9f1239' },
    ];
    liveTxns.forEach(t => {
      const s = t.score;
      const bin = bins.find(b => s >= b.min && s < b.max);
      if (bin) bin.count++;
    });
    return bins;
  }, [liveTxns]);

  // 3. Dynamic Alerts
  const dynamicAlerts = useMemo(() => {
    const alerts = liveTxns
      .filter(t => t.score >= 70)
      .slice(0, 5)
      .map(t => ({
        id: t.transaction_id,
        severity: t.score >= 85 ? 'critical' : 'high',
        msg: `${t.score >= 85 ? 'Critical' : 'High'} risk for ${t.user_id} (${t.score})`,
        time: new Date(t.timestamp_utc * 1000).toLocaleTimeString('en-US', { hour12: false }),
      }));
    return alerts.length > 0 ? alerts : RECENT_ALERTS;
  }, [liveTxns]);

  return (
    <div>
      <Topbar title="Operations Dashboard" subtitle="Real-time fraud intelligence — pre-transaction decisioning" />
      <div className="page">

        {/* STAT CARDS */}
        <div className="grid-4">
          <StatCard label="Transactions Today"  value={stats?.total_scored?.toLocaleString() || "..."}  delta="Live Engine" deltaUp={true}  icon="💳" color="#6366f1" />
          <StatCard label="Blocked (Fraud)"     value={stats?.blocked?.toLocaleString() || "..."}     delta={stats?.block_rate_pct != null ? `${stats.block_rate_pct.toFixed(2)}% rate` : ""}   deltaUp={false} icon="🛡️" color="#f43f5e" />
          <StatCard label="MFA Challenged"      value={stats?.mfa?.toLocaleString() || "..."}     delta={stats?.active_ato_chains + " active ATOs"}     deltaUp={null}  icon="🔐" color="#f59e0b" />
          {(() => {
            const lat = stats?.avg_latency_ms;
            const underSLA = lat != null && lat < 100;
            const overSLA  = lat != null && lat >= 100;
            return (
              <StatCard
                label="Avg Decision Time"
                value={lat != null ? `${lat}ms` : '...'}
                delta={lat == null ? 'Awaiting data' : overSLA ? `⚠️ Over SLA (>${lat}ms)` : 'SLA: <100ms ✓'}
                deltaUp={lat == null ? null : underSLA}
                icon="⚡"
                color={overSLA ? '#f43f5e' : '#10b981'}
              />
            );
          })()}
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
              <AreaChart data={hourlyData}>
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
              <BarChart data={scoreDist} barSize={18}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                <XAxis dataKey="range" tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="count" name="Transactions" radius={[4, 4, 0, 0]}>
                  {scoreDist.map((entry, i) => (
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
              <span className="mono" style={{ color: 'var(--text-muted)' }}>{displayTxns.length} active</span>
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>TXN ID</th>
                    <th>User</th>
                    <th>Amount</th>
                    <th>Top Feature Reason</th>
                    <th>Risk Score</th>
                    <th>Decision</th>
                    <th>Time</th>
                  </tr>
                </thead>
                <tbody>
                  {displayTxns.slice(0, 8).map((txn, i) => (
                    <tr key={txn.id + i} className="animate-in" style={{ animationDelay: `${i * 30}ms` }}>
                      <td>
                        <span className="mono" style={{ color: 'var(--accent-indigo)' }}>{txn.id}</span>
                        {txn.ato && <span className="badge badge-ato" style={{ marginLeft: 6, fontSize: 9 }}>ATO</span>}
                      </td>
                      <td><span className="mono" style={{ color: 'var(--text-secondary)' }}>{txn.user}</span></td>
                      <td><span style={{ fontWeight: 600 }}>₹{txn.amount.toLocaleString()}</span></td>
                      <td><span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{txn.merchant}</span></td>
                      <td><ScoreBar score={txn.score} /></td>
                      <td><RiskScoreBadge score={txn.score} decision={txn.decision} /></td>
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
              {dynamicAlerts.map(alert => (
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
                { label: 'AUC-PR',   val: performance?.aucpr   != null ? performance.aucpr.toFixed(4)   : '...', color: '#10b981' },
                { label: 'ROC-AUC', val: performance?.roc_auc != null ? performance.roc_auc.toFixed(4) : '...', color: '#6366f1' },
                { label: 'F1 Score', val: performance?.f1_score != null ? `${(performance.f1_score * 100).toFixed(1)}%` : '...', color: '#8b5cf6' },
                { label: 'Model Ver', val: performance?.current_version || '...', color: '#06b6d4' },
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
