import React from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, AreaChart, Area
} from 'recharts';
import Topbar from '../components/Topbar';
import { MODEL_PERFORMANCE, LATENCY_DATA } from '../data/mockData';

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

const MLFLOW_RUNS = [
  { version: 'v2.4.1', date: '2026-04-03 13:45', precision: 96.5, recall: 94.7, f1: 95.6, trigger: 'Analyst labels (12)', status: 'active' },
  { version: 'v2.4.0', date: '2026-04-03 10:12', precision: 95.8, recall: 93.8, f1: 94.8, trigger: 'Scheduled retrain', status: 'archived' },
  { version: 'v2.3.9', date: '2026-04-02 22:30', precision: 95.1, recall: 93.4, f1: 94.2, trigger: 'Analyst labels (8)', status: 'archived' },
  { version: 'v2.3.8', date: '2026-04-02 15:01', precision: 94.6, recall: 92.9, f1: 93.7, trigger: 'Scheduled retrain', status: 'archived' },
];

export default function ModelPerformance() {
  return (
    <div>
      <Topbar title="Model Performance" subtitle="MLflow versioning · Adaptive retraining loop · XGBoost + IsoForest + AE ensemble" />
      <div className="page">

        {/* Metrics Row */}
        <div className="grid-4">
          {[
            { label: 'Precision', val: '96.5%', sub: '↑ 0.7% from v2.4.0', color: '#10b981' },
            { label: 'Recall', val: '94.7%', sub: '↑ 0.9% from v2.4.0', color: '#6366f1' },
            { label: 'F1 Score', val: '95.6%', sub: 'Best ever', color: '#8b5cf6' },
            { label: 'Avg Latency', val: '42ms', sub: 'SLA target: <100ms', color: '#06b6d4' },
          ].map(m => (
            <div key={m.label} className="glass" style={{ padding: '20px 24px' }}>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>{m.label}</div>
              <div style={{ fontSize: 32, fontWeight: 900, color: m.color, lineHeight: 1 }}>{m.val}</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>{m.sub}</div>
            </div>
          ))}
        </div>

        {/* Charts */}
        <div className="grid-2">
          {/* Model Performance Over Time */}
          <div className="glass" style={{ padding: '20px 24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
              <span className="section-title">Performance Over 7 Days</span>
              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Post-retrain metrics</span>
            </div>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={MODEL_PERFORMANCE}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                <XAxis dataKey="day" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis domain={[90, 98]} tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip content={<CustomTooltip />} />
                <Legend wrapperStyle={{ fontSize: 11, color: 'var(--text-secondary)' }} />
                <Line type="monotone" dataKey="precision" stroke="#10b981" strokeWidth={2.5} dot={{ fill: '#10b981', r: 4 }} name="Precision" />
                <Line type="monotone" dataKey="recall"    stroke="#6366f1" strokeWidth={2.5} dot={{ fill: '#6366f1', r: 4 }} name="Recall" />
                <Line type="monotone" dataKey="f1"        stroke="#8b5cf6" strokeWidth={2.5} dot={{ fill: '#8b5cf6', r: 4 }} name="F1 Score" strokeDasharray="5 2" />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Latency */}
          <div className="glass" style={{ padding: '20px 24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
              <span className="section-title">API Latency (ms)</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <div className="live-dot" />
                <span style={{ fontSize: 11, color: '#10b981', fontFamily: 'var(--font-mono)' }}>Live</span>
              </div>
            </div>
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={LATENCY_DATA}>
                <defs>
                  <linearGradient id="latencyGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#06b6d4" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                <XAxis dataKey="t" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis domain={[0, 120]} tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip content={({ active, payload }) => active && payload?.length ? (
                  <div className="custom-tooltip">{payload[0].value}ms</div>
                ) : null} />
                {/* SLA line */}
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
                <th>Precision</th>
                <th>Recall</th>
                <th>F1 Score</th>
                <th>Status</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {MLFLOW_RUNS.map((run, i) => (
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
            { title: 'XGBoost Classifier', role: 'Primary scorer', detail: 'Trained on 2M+ transactions, 47 engineered features. Provides base risk score + SHAP values for explanations.', color: '#6366f1', icon: '🌲' },
            { title: 'Isolation Forest', role: 'Anomaly detection', detail: 'Unsupervised outlier detection for novel fraud patterns not in training data. Flags behavioral anomalies.', color: '#f59e0b', icon: '🔬' },
            { title: 'Autoencoder (AE)', role: 'Reconstruction error', detail: 'Neural network reconstructs normal behavior. High reconstruction error = anomalous transaction pattern.', color: '#8b5cf6', icon: '🧠' },
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
