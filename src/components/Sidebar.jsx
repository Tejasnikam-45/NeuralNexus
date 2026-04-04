import React from 'react';
import { 
  LayoutDashboard, Zap, ShieldAlert, Network, 
  FlaskConical, BarChart3, Settings, Bell, Activity, Cpu
} from 'lucide-react';

const NAV_ITEMS = [
  { id: 'dashboard',   icon: LayoutDashboard, label: 'Dashboard',         badge: null },
  { id: 'live',        icon: Zap,             label: 'Live Feed',         badge: '3' },
  { id: 'ato',         icon: ShieldAlert,     label: 'ATO Chains',        badge: '2' },
  { id: 'graph',       icon: Network,         label: 'Fraud Graph',       badge: null },
  { id: 'analyst',     icon: Activity,        label: 'Analyst Review',    badge: '5' },
  { id: 'simulator',   icon: FlaskConical,    label: 'Fraud Simulator',   badge: null },
  { id: 'architecture',icon: Cpu,             label: 'System Architecture',badge: null },
  { id: 'performance', icon: BarChart3,       label: 'Model Performance', badge: null },
];

export default function Sidebar({ active, onNav }) {
  return (
    <aside className="sidebar">
      {/* Logo */}
      <div className="sidebar-logo">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 10,
            background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 4px 15px rgba(99,102,241,0.4)',
            fontSize: 18
          }}>⚡</div>
          <div>
            <div style={{ fontWeight: 800, fontSize: 15, letterSpacing: '-0.02em' }}>NeuralNexus</div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>Fraud Intelligence</div>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav style={{ flex: 1, padding: '12px 0', overflowY: 'auto' }}>
        <div style={{ padding: '8px 16px 4px', fontSize: 10, color: 'var(--text-muted)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
          Operations
        </div>
        {NAV_ITEMS.map(({ id, icon: Icon, label, badge }) => (
          <button
            key={id}
            className={`nav-item ${active === id ? 'active' : ''}`}
            onClick={() => onNav(id)}
            style={{ width: 'calc(100% - 16px)', background: 'none', border: active === id ? undefined : 'none' }}
          >
            <Icon size={16} />
            {label}
            {badge && <span className="nav-badge">{badge}</span>}
          </button>
        ))}
      </nav>

      {/* Bottom */}
      <div style={{ padding: '16px', borderTop: '1px solid var(--border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 32, height: 32, borderRadius: '50%',
            background: 'linear-gradient(135deg, #8b5cf6, #06b6d4)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 13, fontWeight: 700
          }}>A</div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600 }}>Analyst Tejas</div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>Senior Investigator</div>
          </div>
          <Settings size={14} style={{ marginLeft: 'auto', color: 'var(--text-muted)', cursor: 'pointer' }} />
        </div>
      </div>
    </aside>
  );
}
