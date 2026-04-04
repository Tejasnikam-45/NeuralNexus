import React, { useState, useEffect } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, AreaChart, Area
} from 'recharts';
import Topbar from '../components/Topbar';
import { MODEL_PERFORMANCE, LATENCY_DATA } from '../data/mockData';
import { fetchModelPerformance, fetchStats } from '../api';

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="custom-tooltip">
      <div style={{ fontWeight: 600, marginBottom: 6 }}>{label}</div>
      {payload.map(p => (
        <div key={p.dataKey} style={{ color: p.color, fontSize: 12 }}>
          {p.name}: <b>{p.value}%</b>
        </div>
      ))}
    </div>
  );
}

export default function ModelPerformance() {
  const [perf, setPerf] = useState(null);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetchModelPerformance().catch(() => null),
      fetchStats().catch(() => null),
    ]).then(([perfData, statsData]) => {
      setPerf(perfData);
      setStats(statsData);
      setLoading(false);
    });
  }, []);

  // Derived real values
  const aucpr = perf?.eval_metrics?.aucpr;
  const rocAuc = perf?.eval_metrics?.roc_auc;
  const bestF1 = perf?.eval_metrics?.best_f1;
  const modelVer = perf?.model_version;
  const evalDate = perf?.eval_metrics?.evaluated_at
    ? new Date(perf.eval_metrics.evaluated_at).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    : null;
  const avgLatency = stats?.avg_latency_ms;
  const totalScored = stats?.total_scored;

  // Build live MLflow table — first row from real model, rest are demo history
  const MLFLOW_RUNS = [
    {
      version: modelVer || 'v1.0.0',
      date: evalDate || '2026-04-03 13:02',
      precision: aucpr != null ? (aucpr * 100).toFixed(1) : '—',
      recall: rocAuc != null ? (rocAuc * 100).toFixed(1) : '—',
      f1: bestF1 != null ? (bestF1 * 100).toFixed(1) : '—',
      trigger: `${totalScored ?? '—'} transactions scored`,
      status: 'active',
    },
    { version: 'v0.9.0', date: '2026-04-03 10:12', precision: 95.8, recall: 93.8, f1: 94.8, trigger: 'Scheduled retrain', status: 'archived' },
    { version: 'v0.8.0', date: '2026-04-02 22:30', precision: 95.1, recall: 93.4, f1: 94.2, trigger: 'Analyst labels (8)', status: 'archived' },
    { version: 'v0.7.0', date: '2026-04-02 15:01', precision: 94.6, recall: 92.9, f1: 93.7, trigger: 'Scheduled retrain', status: 'archived' },
  ];

  const fmt = (v, digits = 2) => (v != null ? `${(v * 100).toFixed(digits)}%` : '...');
  const fmtRaw = (v, digits = 4) => (v != null ? v.toFixed(digits) : '...');

  const topKPIs = [
    {
      label: 'AUC-PR',
      val: fmtRaw(aucpr),
      sub: 'Area under precision-recall curve',
      color: '#10b981',
      live: aucpr != null,
    },
    {
      label: 'ROC-AUC',
      val: fmtRaw(rocAuc),
      sub: 'Classifier separability score',
      color: '#6366f1',
      live: rocAuc != null,
    },
    {
      label: 'F1 Score',
      val: fmt(bestF1, 1),
      sub: `Threshold: ${perf?.eval_metrics?.best_threshold ?? '—'}`,
      color: '#8b5cf6',
      live: bestF1 != null,
    },
    {
      label: 'Avg Latency',
      val: avgLatency != null ? `${avgLatency}ms` : '...',
      sub: `SLA target: <100ms · ${totalScored ?? '—'} scored`,
      color: avgLatency != null && avgLatency < 100 ? '#06b6d4' : '#f59e0b',
      live: avgLatency != null,
    },
  ];

  return (
    <div>
      <Topbar title="Model Performance" subtitle="MLflow versioning · Adaptive retraining loop · XGBoost + IsoForest + AE ensemble" />
      <div className="page">

        {/* Live model badge */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '10px 16px', background: 'rgba(99,102,241,0.08)',
          border: '1px solid rgba(99,102,241,0.2)', borderRadius: 10, marginBottom: 4
        }}>
          <div className="live-dot" />
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
            Showing <b style={{ color: '#818cf8' }}>live</b> metrics from{' '}
            <span style={{ fontFamily: 'var(--font-mono)', color: '#c4b5fd' }}>{modelVer || '...'}</span>
            {' '}· Evaluated{' '}
            <span style={{ color: 'var(--text-muted)' }}>{evalDate || '...'}</span>
            {' '}· {perf?.feature_count ?? '—'} features
          </span>
        </div>

        {/* Metrics Row */}
        <div className="grid-4">
          {topKPIs.map(m => (
            <div key={m.label} className="glass" style={{ padding: '20px 24px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{m.label}</div>
                {m.live
                  ? <span style={{ fontSize: 9, background: 'rgba(16,185,129,0.15)', color: '#10b981', border: '1px solid rgba(16,185,129,0.25)', borderRadius: 999, padding: '2px 6px' }}>LIVE</span>
                  : <span style={{ fontSize: 9, color: 'var(--text-muted)' }}>loading…</span>
                }
              </div>
              <div style={{ fontSize: 32, fontWeight: 900, color: m.color, lineHeight: 1 }}>{m.val}</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>{m.sub}</div>
            </div>
          ))}
        </div>

        {/* Ensemble weights — real from backend */}
        {perf?.ensemble_weights && (
          <div className="glass" style={{ padding: '14px 20px', display: 'flex', alignItems: 'center', gap: 24 }}>
            <span style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Ensemble Weights</span>
            {Object.entries(perf.ensemble_weights).map(([model, weight]) => (
              <div key={model} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ width: 60, height: 6, background: 'rgba(255,255,255,0.06)', borderRadius: 3, overflow: 'hidden' }}>
                  <div style={{ width: `${weight * 100}%`, height: '100%', background: model === 'xgb' ? '#6366f1' : model === 'iso' ? '#f59e0b' : '#8b5cf6', borderRadius: 3 }} />
                </div>
                <span style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase' }}>
                  {model} <b style={{ color: 'var(--text-primary)' }}>{(weight * 100).toFixed(0)}%</b>
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Charts */}
        <div className="grid-2">
          {/* Model Performance Over Time — demo chart, real anchor point */}
          <div className="glass" style={{ padding: '20px 24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
              <span className="section-title">Performance Over 7 Days</span>
              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Historical trend (demo)</span>
            </div>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={MODEL_PERFORMANCE}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                <XAxis dataKey="day" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis domain={[90, 100]} tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip content={<CustomTooltip />} />
                <Legend wrapperStyle={{ fontSize: 11, color: 'var(--text-secondary)' }} />
                <Line type="monotone" dataKey="precision" stroke="#10b981" strokeWidth={2.5} dot={{ fill: '#10b981', r: 4 }} name="Precision" />
                <Line type="monotone" dataKey="recall" stroke="#6366f1" strokeWidth={2.5} dot={{ fill: '#6366f1', r: 4 }} name="Recall" />
                <Line type="monotone" dataKey="f1" stroke="#8b5cf6" strokeWidth={2.5} dot={{ fill: '#8b5cf6', r: 4 }} name="F1 Score" strokeDasharray="5 2" />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Latency */}
          <div className="glass" style={{ padding: '20px 24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
              <span className="section-title">API Latency (ms)</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <div className="live-dot" />
                <span style={{ fontSize: 11, color: '#10b981', fontFamily: 'var(--font-mono)' }}>
                  {avgLatency != null ? `${avgLatency}ms avg` : 'Live'}
                </span>
              </div>
            </div>
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={LATENCY_DATA}>
                <defs>
                  <linearGradient id="latencyGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                <XAxis dataKey="t" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis domain={[0, 120]} tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip content={({ active, payload }) => active && payload?.length ? (
                  <div className="custom-tooltip">{payload[0].value}ms</div>
                ) : null} />
                <Area type="monotone" dataKey="ms" stroke="#06b6d4" strokeWidth={2.5} fill="url(#latencyGrad)" name="Latency" />
              </AreaChart>
            </ResponsiveContainer>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8 }}>
              <div style={{ width: 20, height: 2, background: '#f43f5e', borderTop: '2px dashed #f43f5e' }} />
              <span style={{ fontSize: 11, color: '#f43f5e' }}>100ms SLA threshold</span>
            </div>
          </div>
        </div>

        {/* MLflow Runs Table */}
        <div className="glass" style={{ overflow: 'hidden' }}>
          <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span className="section-title">MLflow Run History</span>
            <span style={{
              fontSize: 11, padding: '3px 10px', borderRadius: 999,
              background: 'rgba(16,185,129,0.1)', color: '#10b981',
              border: '1px solid rgba(16,185,129,0.2)'
            }}>Auto-retraining: ON</span>
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Version</th>
                <th>Retrain Date</th>
                <th>Trigger</th>
                <th>AUC-PR</th>
                <th>ROC-AUC</th>
                <th>F1 Score</th>
                <th>Status</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {MLFLOW_RUNS.map((run) => (
                <tr key={run.version}>
                  <td><span className="mono" style={{ color: '#818cf8', fontWeight: 600 }}>{run.version}</span></td>
                  <td><span className="mono" style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{run.date}</span></td>
                  <td><span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{run.trigger}</span></td>
                  <td><span style={{ fontWeight: 700, color: '#10b981', fontFamily: 'var(--font-mono)' }}>{run.precision}%</span></td>
                  <td><span style={{ fontWeight: 700, color: '#6366f1', fontFamily: 'var(--font-mono)' }}>{run.recall}%</span></td>
                  <td><span style={{ fontWeight: 700, color: '#8b5cf6', fontFamily: 'var(--font-mono)' }}>{run.f1}%</span></td>
                  <td>
                    {run.status === 'active' ? (
                      <span className="badge badge-approve">● Active</span>
                    ) : (
                      <span className="badge" style={{ background: 'rgba(100,116,139,0.15)', color: '#64748b', border: '1px solid rgba(100,116,139,0.2)' }}>Archived</span>
                    )}
                  </td>
                  <td>
                    {run.status !== 'active' && (
                      <button className="btn btn-ghost" style={{ fontSize: 11, padding: '4px 10px' }}>Rollback</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Model Architecture Info */}
        <div className="grid-3">
          {[
            {
              title: 'XGBoost Classifier',
              role: `Primary scorer · ${perf?.ensemble_weights?.xgb ? `${(perf.ensemble_weights.xgb * 100).toFixed(0)}% weight` : '60% weight'}`,
              detail: `Trained on ${perf?.feature_count ?? 46} engineered features. Provides base risk score + SHAP values for human-readable explanations.`,
              color: '#6366f1', icon: '🌲'
            },
            {
              title: 'Isolation Forest',
              role: `Anomaly detection · ${perf?.ensemble_weights?.iso ? `${(perf.ensemble_weights.iso * 100).toFixed(0)}% weight` : '25% weight'}`,
              detail: 'Unsupervised outlier detection for novel fraud patterns not in training data. Flags behavioral anomalies.',
              color: '#f59e0b', icon: '🔬'
            },
            {
              title: 'Autoencoder (AE)',
              role: `Reconstruction error · ${perf?.ensemble_weights?.ae ? `${(perf.ensemble_weights.ae * 100).toFixed(0)}% weight` : '15% weight'}`,
              detail: 'Neural network reconstructs normal behavior. High reconstruction error = anomalous transaction pattern.',
              color: '#8b5cf6', icon: '🧠'
            },
          ].map(m => (
            <div key={m.title} className="glass glass-hover" style={{ padding: '20px 22px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                <div style={{ fontSize: 24 }}>{m.icon}</div>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 13, color: m.color }}>{m.title}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{m.role}</div>
                </div>
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>{m.detail}</div>
            </div>
          ))}
        </div>

      </div>
    </div>
  );
}
