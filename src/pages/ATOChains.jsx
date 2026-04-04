import React, { useState, useEffect } from 'react';
import Topbar from '../components/Topbar';
import { ATO_CHAIN_EVENTS } from '../data/mockData';
import { ShieldAlert, Link, UserX, CreditCard, ChevronDown, ChevronUp } from 'lucide-react';
import { fetchATOChains, submitFeedback } from '../api';

const MOCK_CHAINS = []; // Real ones hit below

const severityColor = {
  critical: '#f43f5e',
  high: '#fb923c',
  blocked: '#8b5cf6',
};

const severityBg = {
  critical: 'rgba(244,63,94,0.12)',
  high: 'rgba(251,146,60,0.1)',
  blocked: 'rgba(139,92,246,0.12)',
};

function ChainCard({ chain, onResolve }) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="glass" style={{ overflow: 'hidden' }}>
      {/* Chain Header */}
      <div
        style={{
          padding: '16px 20px',
          background: 'rgba(244,63,94,0.06)',
          borderBottom: '1px solid rgba(244,63,94,0.15)',
          cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between'
        }}
        onClick={() => setExpanded(!expanded)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 10,
            background: 'rgba(244,63,94,0.2)', border: '1px solid rgba(244,63,94,0.4)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18
          }}>
            <ShieldAlert size={18} color="#f43f5e" />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontWeight: 700, fontSize: 14 }}>{chain.id}</span>
              <span className="badge badge-ato">{chain.status.toUpperCase()}</span>
              <span style={{
                fontSize: 11, fontWeight: 700, color: '#f43f5e',
                fontFamily: 'var(--font-mono)'
              }}>RISK {chain.risk}</span>
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>{chain.summary}</div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <div style={{ textAlign: 'right', fontSize: 11, color: 'var(--text-muted)' }}>
            <div>{chain.startTime} → {chain.endTime}</div>
            <div style={{ color: '#f43f5e' }}>Duration: {chain.duration}</div>
          </div>
          {expanded ? <ChevronUp size={16} color="var(--text-muted)" /> : <ChevronDown size={16} color="var(--text-muted)" />}
        </div>
      </div>

      {expanded && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: 0 }}>
          {/* Timeline */}
          <div style={{ padding: '20px 24px', borderRight: '1px solid var(--border)' }}>
            <div className="section-title" style={{ marginBottom: 16 }}>Attack Timeline</div>
            {chain.events.map((ev, i) => (
              <div key={i} className="chain-node">
                <div
                  className="chain-dot"
                  style={{
                    background: severityBg[ev.severity] || 'rgba(99,102,241,0.1)',
                    border: `2px solid ${severityColor[ev.severity] || '#6366f1'}`,
                    fontSize: 15,
                  }}
                >
                  {ev.icon}
                </div>
                <div style={{ flex: 1, paddingBottom: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <span style={{ fontWeight: 600, fontSize: 13 }}>{ev.label}</span>
                    <span className="mono" style={{ fontSize: 10, color: 'var(--text-muted)' }}>{ev.time}</span>
                    {ev.severity === 'blocked' && (
                      <span style={{ fontSize: 10, background: 'rgba(139,92,246,0.15)', color: '#a78bfa', border: '1px solid rgba(139,92,246,0.3)', borderRadius: 4, padding: '1px 6px' }}>BLOCKED</span>
                    )}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5 }}>{ev.detail}</div>
                </div>
              </div>
            ))}
          </div>

          {/* Meta Panel */}
          <div style={{ padding: '20px' }}>
            <div className="section-title" style={{ marginBottom: 14 }}>Chain Intelligence</div>

            {[
              { label: 'Compromised User', val: chain.user, icon: <UserX size={12} /> },
              { label: 'Attack Device', val: chain.device, icon: <Link size={12} /> },
              { label: 'Attacker IP', val: chain.ip, icon: <Link size={12} /> },
            ].map(item => (
              <div key={item.label} style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 3, display: 'flex', alignItems: 'center', gap: 4 }}>
                  {item.icon} {item.label}
                </div>
                <div className="mono" style={{ fontSize: 12, color: 'var(--text-primary)' }}>{item.val}</div>
              </div>
            ))}

            {chain.linkedAccounts.length > 1 && (
              <div style={{ marginBottom: 14 }}>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>Linked Accounts</div>
                {chain.linkedAccounts.map(acc => (
                  <div key={acc} style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: '5px 8px', background: 'rgba(244,63,94,0.06)',
                    border: '1px solid rgba(244,63,94,0.15)', borderRadius: 6, marginBottom: 4
                  }}>
                    <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#f43f5e' }} />
                    <span className="mono" style={{ fontSize: 11 }}>{acc}</span>
                  </div>
                ))}
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 16 }}>
              <button 
                className="btn btn-danger" 
                style={{ justifyContent: 'center', fontSize: 12 }}
                onClick={() => onResolve && onResolve(chain)}
              >🔒 Lock Account</button>
              <button className="btn btn-ghost" style={{ justifyContent: 'center', fontSize: 12 }}>📋 Escalate to L2</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ATOChains() {
  const [chains, setChains] = useState([]);
  const [stats, setStats] = useState({ active:0, resolved:0 });

  const [lockSuccess, setLockSuccess] = useState(null);

  const handleResolve = async (chain) => {
    try {
      // Generate a real-looking transaction ID based on chain ID
      const txnId = `ato_lock_${chain.id.toLowerCase().replace('-', '_')}_${Date.now()}`;
      await submitFeedback({
        transaction_id: txnId,
        user_id: chain.user,
        label: 'fraud',
        chain_id: chain.id,
        notes: `Account manually locked by analyst. Chain: ${chain.id} | User: ${chain.user}`
      });
      setChains(prev => prev.filter(c => c.id !== chain.id));
      setStats(prev => ({ ...prev, active: Math.max(0, prev.active - 1), resolved: prev.resolved + 1 }));
      setLockSuccess(chain.id);
      setTimeout(() => setLockSuccess(null), 3000);
    } catch (err) {
      console.error('Failed to lock account', err);
      alert(`Lock failed: ${err.message}`);
    }
  };

  useEffect(() => {
    fetchATOChains().then(resp => {
      setStats({ active: resp.active_count, resolved: resp.resolved_today });
      setChains(resp.chains.map(c => ({
        id: c.chain_id,
        user: c.user_id,
        risk: Math.round(c.risk_score || 0),
        status: c.status,
        summary: c.summary || 'Suspicious authentication sequence detected.',
        events: (c.events || []).map(e => ({
            time: new Date((e.timestamp_utc || 0) * 1000).toLocaleTimeString('en-US', { hour12: false }),
            label: e.detail || 'Event',
            detail: e.detail || '',
            severity: e.severity || 'high',
            icon: '⚠'
        })),
        linkedAccounts: c.linked_account_ids || [c.user_id],
        device: c.linked_device || 'Unknown',
        ip: c.attacker_ip || 'Unknown',
        startTime: new Date((c.start_time || Date.now()/1000) * 1000).toLocaleTimeString('en-US'),
        endTime: c.end_time ? new Date(c.end_time * 1000).toLocaleTimeString('en-US') : 'Ongoing',
        duration: c.duration_seconds ? `${c.duration_seconds}s` : '...',
      })));
    }).catch(console.error);
  }, []);

  return (
    <div>
      <Topbar title="ATO Chain Detector" subtitle="Account Takeover → Transaction abuse linkage" />
      <div className="page">

        {/* Success toast */}
        {lockSuccess && (
          <div style={{
            padding: '12px 18px', background: 'rgba(16,185,129,0.15)',
            border: '1px solid rgba(16,185,129,0.4)', borderRadius: 10,
            color: '#34d399', fontSize: 13, fontWeight: 600,
            display: 'flex', alignItems: 'center', gap: 8, animation: 'fadeInUp 0.3s ease'
          }}>
            🔒 Chain {lockSuccess} resolved — Account locked and flagged for retraining.
          </div>
        )}

        {/* Stats */}
        <div className="grid-4">
          {[
            { label: 'Active Chains', val: stats.active, color: '#f43f5e', icon: '🔗' },
            { label: 'Accounts at Risk', val: chains.length, color: '#fb923c', icon: '👤' },
            { label: 'Avg Chain Duration', val: 'Ongoing', color: '#f59e0b', icon: '⏱️' },
            { label: 'Auto-Blocked Today', val: stats.resolved, color: '#10b981', icon: '🛡️' },
          ].map(s => (
            <div key={s.label} className="glass" style={{ padding: '16px 20px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <span style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{s.label}</span>
                <span style={{ fontSize: 18 }}>{s.icon}</span>
              </div>
              <div style={{ fontSize: 26, fontWeight: 800, color: s.color }}>{s.val}</div>
            </div>
          ))}
        </div>

        {/* How it works banner */}
        <div style={{
          padding: '14px 20px',
          background: 'linear-gradient(135deg, rgba(99,102,241,0.1), rgba(139,92,246,0.08))',
          border: '1px solid rgba(99,102,241,0.2)',
          borderRadius: 12, fontSize: 13, color: 'var(--text-secondary)',
          display: 'flex', alignItems: 'center', gap: 12
        }}>
          <span style={{ fontSize: 20 }}>🧠</span>
          <span>
            <b style={{ color: 'var(--text-primary)' }}>How ATO Detection Works:</b> When a suspicious login event fires (new device, failed MFA, IP change),
            NeuralNexus opens a <b style={{ color: '#818cf8' }}>300-second chain window</b>. Any subsequent transaction from that account
            automatically receives an elevated risk signal — independent of the ML score — and triggers step-up MFA or immediate block.
          </span>
        </div>

        {/* Chain Cards */}
        {chains.map(chain => <ChainCard key={chain.id} chain={chain} onResolve={handleResolve} />)}
        {chains.length === 0 && (
            <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>No ATO chains detected currently.</div>
        )}

      </div>
    </div>
  );
}
