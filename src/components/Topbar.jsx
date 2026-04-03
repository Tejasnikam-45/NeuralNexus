import React, { useState, useEffect } from 'react';
import { Bell, Search, RefreshCw } from 'lucide-react';

export default function Topbar({ title, subtitle }) {
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <header className="topbar">
      <div>
        <h1 style={{ fontSize: 18, fontWeight: 700, lineHeight: 1.2 }}>{title}</h1>
        {subtitle && <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>{subtitle}</p>}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        {/* Search */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border)',
          borderRadius: 8, padding: '7px 12px', minWidth: 200
        }}>
          <Search size={13} style={{ color: 'var(--text-muted)' }} />
          <input
            placeholder="Search TXN, user, IP..."
            style={{
              background: 'none', border: 'none', outline: 'none',
              color: 'var(--text-primary)', fontSize: 12,
              fontFamily: 'Inter, sans-serif', width: '100%'
            }}
          />
        </div>

        {/* Live clock */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.2)',
          borderRadius: 8, padding: '6px 12px'
        }}>
          <div className="live-dot" />
          <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: '#10b981' }}>
            LIVE {time.toLocaleTimeString('en-US', { hour12: false })}
          </span>
        </div>

        {/* Refresh */}
        <button className="btn btn-ghost" style={{ padding: '7px 10px' }}>
          <RefreshCw size={14} />
        </button>

        {/* Notifications */}
        <button style={{
          position: 'relative', background: 'rgba(255,255,255,0.04)',
          border: '1px solid var(--border)', borderRadius: 8,
          padding: '7px 10px', cursor: 'pointer', color: 'var(--text-secondary)'
        }}>
          <Bell size={16} />
          <span style={{
            position: 'absolute', top: 4, right: 4,
            width: 8, height: 8, borderRadius: '50%',
            background: '#f43f5e', border: '2px solid var(--bg-primary)'
          }} />
        </button>
      </div>
    </header>
  );
}
