import React, { useState } from 'react';
import Topbar from '../components/Topbar';
import { ATO_CHAIN_EVENTS } from '../data/mockData';
import { ShieldAlert, Link, UserX, CreditCard, ChevronDown, ChevronUp } from 'lucide-react';

const MOCK_CHAINS = [
  {
    id: 'ATO-001', user: 'usr_tom_b', risk: 95, status: 'active',
    summary: 'SIM swap → Profile hijack → $5,600 NFT transaction',
    events: ATO_CHAIN_EVENTS,
    linkedAccounts: ['usr_tom_b', 'usr_alex92'],
    device: 'device_A7F',
    ip: '185.220.x.x (TOR)',
    startTime: '13:58:02', endTime: '14:01:38', duration: '3m 36s',
  },
  {
    id: 'ATO-002', user: 'usr_james_w', risk: 82, status: 'active',
    summary: 'Credential stuffing → New device login → $3,100 FX trade',
    events: ATO_CHAIN_EVENTS.slice(0, 3),
    linkedAccounts: ['usr_james_w'],
    device: 'device_B9K',
    ip: '194.33.x.x (VPN)',
    startTime: '14:02:10', endTime: '14:02:19', duration: '9s',
  },
];

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

function ChainCard({ chain }) {
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
              <button className="btn btn-danger" style={{ justifyContent: 'center', fontSize: 12 }}>🔒 Lock Account</button>
              <button className="btn btn-ghost" style={{ justifyContent: 'center', fontSize: 12 }}>📋 Escalate to L2</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ATOChains() {
  return (
    <div>
      <Topbar title="ATO Chain Detector" subtitle="Account Takeover → Transaction abuse linkage" />
      <div className="page">

        {/* Stats */}
        <div className="grid-4">
          {[
            { label: 'Active Chains', val: '2', color: '#f43f5e', icon: '🔗' },
            { label: 'Accounts at Risk', val: '3', color: '#fb923c', icon: '👤' },
            { label: 'Avg Chain Duration', val: '1m 58s', color: '#f59e0b', icon: '⏱️' },
            { label: 'Auto-Blocked Today', val: '7', color: '#10b981', icon: '🛡️' },
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
            NeuralNexus opens a <b style={{ color: '#818cf8' }}>30-second chain window</b>. Any subsequent transaction from that account
            automatically receives an elevated risk signal — independent of the ML score — and triggers step-up MFA or immediate block.
          </span>
        </div>

        {/* Chain Cards */}
        {MOCK_CHAINS.map(chain => <ChainCard key={chain.id} chain={chain} />)}

      </div>
    </div>
  );
}
