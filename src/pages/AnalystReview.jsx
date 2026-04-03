import React, { useState } from 'react';
import Topbar from '../components/Topbar';
import { TRANSACTIONS, SHAP_FEATURES } from '../data/mockData';
import { RiskScoreBadge, ScoreBar } from '../components/UIKit';
import { CheckCircle, XCircle, RotateCcw, MessageSquare } from 'lucide-react';
import { fetchFeedbackQueue, submitFeedback } from '../api';

function ShapBar({ feature }) {
  const max = 0.45;
  const pct = (Math.abs(feature.value) / max) * 100;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0' }}>
      <span style={{ fontSize: 11, color: 'var(--text-secondary)', width: 175, flexShrink: 0 }}>{feature.name}</span>
      <div style={{ flex: 1, height: 7, background: 'rgba(255,255,255,0.05)', borderRadius: 4, overflow: 'hidden' }}>
        <div style={{
          width: `${pct}%`, height: '100%', borderRadius: 4,
          background: feature.positive
            ? 'linear-gradient(90deg,#f43f5e,#fb7185)'
            : 'linear-gradient(90deg,#10b981,#34d399)'
        }} />
      </div>
      <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: feature.positive ? '#fb7185' : '#34d399', width: 40, textAlign: 'right' }}>
        {feature.positive ? '+' : ''}{feature.value.toFixed(2)}
      </span>
    </div>
  );
}

export default function AnalystReview() {
  const [queue, setQueue] = useState([]);
  const [current, setCurrent] = useState(null);
  const [note, setNote] = useState('');
  const [actionLog, setActionLog] = useState([]);
  
  React.useEffect(() => {
    fetchFeedbackQueue().then(resp => {
      const qs = resp.queue.map(q => ({
        id: q.transaction_id,
        user: q.user_id,
        score: Math.round(q.score),
        amount: q.amount_usd,
        merchant: "Reason: " + q.shap_reasons?.[0]?.text?.substring(0,25) || "Unspecified",
        type: q.decision,
        flags: q.rule_triggers || [],
        device: "Unknown", location: "Unknown",
        time: new Date(q.timestamp_utc * 1000).toLocaleTimeString('en-US', { hour12: false }),
        raw: q
      }));
      setQueue(qs);
      setCurrent(qs[0] || null);
    }).catch(console.error);
  }, []);

  const handleAction = async (action) => {
    if (!current) return;
    const label = action === 'safe' ? 'false_positive' : action === 'fraud' ? 'true_fraud' : 'needs_review';
    const logLabel = action === 'safe' ? '✅ Marked Safe' : action === 'fraud' ? '❌ Confirmed Fraud' : '🔄 Queued for Retraining';
    
    try {
      await submitFeedback({
        transaction_id: current.id,
        analyst_id: 'analyst_demo',
        label,
        analyst_note: note,
        override_decision: action === 'safe' ? 'approve' : 'block',
        timestamp_utc: new Date().toISOString()
      });
      
      setActionLog(prev => [{
        id: current.id, user: current.user, score: current.score,
        action: logLabel, time: new Date().toLocaleTimeString('en-US', { hour12: false }), note
      }, ...prev.slice(0, 9)]);
      
      const remaining = queue.filter(t => t.id !== current.id);
      setQueue(remaining);
      setCurrent(remaining[0] || null);
      setNote('');
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div>
      <Topbar title="Analyst Review" subtitle="Human-in-the-loop decisioning & feedback for adaptive retraining" />
      <div className="page">

        <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr 320px', gap: 20 }}>

          {/* Queue List */}
          <div className="glass" style={{ padding: '16px', overflowY: 'auto', maxHeight: 680 }}>
            <div className="section-title" style={{ marginBottom: 12 }}>Review Queue ({queue.length})</div>
            {queue.map(txn => (
              <div
                key={txn.id}
                onClick={() => setCurrent(txn)}
                className="glass-hover"
                style={{
                  padding: '10px 12px', borderRadius: 8, marginBottom: 6, cursor: 'pointer',
                  background: current?.id === txn.id ? 'rgba(99,102,241,0.15)' : 'rgba(255,255,255,0.03)',
                  border: `1px solid ${current?.id === txn.id ? 'rgba(99,102,241,0.4)' : 'var(--border)'}`,
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                  <span className="mono" style={{ fontSize: 11, color: '#818cf8' }}>{txn.id}</span>
                  <RiskScoreBadge score={txn.score} />
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{txn.user}</div>
                <div style={{ fontSize: 12, fontWeight: 600, marginTop: 3 }}>${txn.amount.toLocaleString()}</div>
                {txn.ato && <span className="badge badge-ato" style={{ marginTop: 4, fontSize: 9 }}>ATO</span>}
              </div>
            ))}
            {queue.length === 0 && (
              <div style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center', padding: '30px 0' }}>
                ✅ Queue empty — all transactions reviewed
              </div>
            )}
          </div>

          {/* Transaction Detail */}
          {current ? (
            <div className="glass" style={{ padding: '24px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                    <span style={{ fontWeight: 800, fontSize: 18 }}>{current.id}</span>
                    <RiskScoreBadge score={current.score} />
                    {current.ato && <span className="badge badge-ato">ATO Chain</span>}
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{current.user} · {current.merchant}</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 28, fontWeight: 900, color: current.score >= 70 ? '#f43f5e' : '#f59e0b' }}>
                    ${current.amount.toLocaleString()}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{current.type}</div>
                </div>
              </div>

              {/* Signal grid */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, marginBottom: 24 }}>
                {[
                  { l: 'Risk Score', v: `${current.score}/100`, c: current.score >= 70 ? '#f43f5e' : '#f59e0b' },
                  { l: 'Location', v: current.location, c: 'var(--text-primary)' },
                  { l: 'Device', v: current.device, c: current.device === 'New Device' ? '#f43f5e' : '#10b981' },
                  { l: 'Time', v: current.time, c: 'var(--text-primary)' },
                  { l: 'Type', v: current.type, c: 'var(--text-secondary)' },
                  { l: 'Merchant', v: current.merchant, c: 'var(--text-secondary)' },
                ].map(item => (
                  <div key={item.l} style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)', borderRadius: 8, padding: '10px 12px' }}>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{item.l}</div>
                    <div style={{ fontSize: 12, fontWeight: 600, color: item.c }}>{item.v}</div>
                  </div>
                ))}
              </div>

              {/* Risk flags */}
              {current.flags.length > 0 && (
                <div style={{ marginBottom: 20 }}>
                  <div className="section-title" style={{ marginBottom: 8 }}>Active Risk Flags</div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {current.flags.map(f => (
                      <span key={f} style={{ fontSize: 11, background: 'rgba(244,63,94,0.1)', color: '#fca5a5', border: '1px solid rgba(244,63,94,0.25)', borderRadius: 6, padding: '3px 10px' }}>
                        ⚠ {f}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* SHAP */}
              <div style={{ marginBottom: 20 }}>
                <div className="section-title" style={{ marginBottom: 10 }}>SHAP Feature Importance</div>
                {SHAP_FEATURES.map(f => <ShapBar key={f.name} feature={f} />)}
              </div>

              {/* Score bar */}
              <div style={{ marginBottom: 24 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>
                  <span>Risk Score Gauge</span>
                  <span>Thresholds: &lt;40 Approve · 40-70 MFA · &gt;70 Block</span>
                </div>
                <div style={{ height: 10, background: 'linear-gradient(90deg, #10b981 40%, #f59e0b 40% 70%, #f43f5e 70%)', borderRadius: 5, position: 'relative' }}>
                  <div style={{
                    position: 'absolute', top: -3, width: 16, height: 16,
                    background: '#fff', borderRadius: '50%', border: '3px solid #6366f1',
                    left: `calc(${current.score}% - 8px)`, transition: 'left 0.4s',
                    boxShadow: '0 0 10px rgba(99,102,241,0.5)'
                  }} />
                </div>
              </div>

              {/* Analyst Note */}
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>Analyst Note (optional)</div>
                <textarea
                  value={note}
                  onChange={e => setNote(e.target.value)}
                  placeholder="Document reason for decision..."
                  style={{
                    width: '100%', background: 'rgba(255,255,255,0.03)',
                    border: '1px solid var(--border)', borderRadius: 8,
                    color: 'var(--text-primary)', padding: '10px 12px', fontSize: 12,
                    fontFamily: 'Inter, sans-serif', resize: 'vertical', minHeight: 70, outline: 'none'
                  }}
                />
              </div>

              {/* Action Buttons */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
                <button className="btn btn-success" style={{ justifyContent: 'center' }} onClick={() => handleAction('safe')}>
                  <CheckCircle size={14} /> Mark Safe
                </button>
                <button className="btn btn-danger" style={{ justifyContent: 'center' }} onClick={() => handleAction('fraud')}>
                  <XCircle size={14} /> Confirm Fraud
                </button>
                <button className="btn btn-ghost" style={{ justifyContent: 'center' }} onClick={() => handleAction('retrain')}>
                  <RotateCcw size={14} /> Retrain Queue
                </button>
              </div>
            </div>
          ) : (
            <div className="glass" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 300 }}>
              <div style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
                <div style={{ fontSize: 48, marginBottom: 12 }}>✅</div>
                <div style={{ fontSize: 14 }}>All transactions reviewed</div>
              </div>
            </div>
          )}

          {/* Action Log */}
          <div className="glass" style={{ padding: '16px 20px', overflowY: 'auto', maxHeight: 680 }}>
            <div className="section-title" style={{ marginBottom: 12 }}>Action Log</div>
            {actionLog.length === 0 && (
              <div style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center', padding: '20px 0' }}>
                No actions yet. Start reviewing transactions.
              </div>
            )}
            {actionLog.map((log, i) => (
              <div key={i} style={{
                padding: '10px 12px', background: 'rgba(255,255,255,0.03)',
                border: '1px solid var(--border)', borderRadius: 8, marginBottom: 8
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span className="mono" style={{ fontSize: 11, color: '#818cf8' }}>{log.id}</span>
                  <span className="mono" style={{ fontSize: 10, color: 'var(--text-muted)' }}>{log.time}</span>
                </div>
                <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 2 }}>{log.action}</div>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{log.user} · ${log.score} risk</div>
                {log.note && <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4, fontStyle: 'italic' }}>"{log.note}"</div>}
              </div>
            ))}

            {actionLog.length >= 3 && (
              <div style={{
                marginTop: 12, padding: '10px 12px',
                background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.25)',
                borderRadius: 8, fontSize: 12, color: '#818cf8'
              }}>
                🔄 <b>{actionLog.length} labels queued.</b> Model retraining will trigger automatically after 10 labels or in 1 hour.
              </div>
            )}
          </div>
        </div>

      </div>
    </div>
  );
}
