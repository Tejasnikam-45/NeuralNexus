import React, { useState } from 'react';
import Topbar from '../components/Topbar';
import { FRAUD_RING_NODES } from '../data/mockData';

// Simple SVG-based graph (no extra deps)
const NODES = [
  { id: 'usr_alex92', x: 200, y: 120, type: 'user',     label: 'usr_alex92', risk: 91, icon: '👤' },
  { id: 'usr_james_w', x: 460, y: 80,  type: 'user',    label: 'usr_james_w', risk: 78, icon: '👤' },
  { id: 'usr_tom_b',  x: 340, y: 230,  type: 'user',    label: 'usr_tom_b', risk: 85, icon: '👤' },
  { id: 'device_A7F', x: 300, y: 130,  type: 'device',  label: 'Device A7F', risk: 95, icon: '💻' },
  { id: 'IP_192',     x: 160, y: 250,  type: 'ip',      label: 'IP 185.220.x', risk: 88, icon: '🌐' },
  { id: 'IP_VPN',     x: 490, y: 200,  type: 'ip',      label: 'TOR Exit', risk: 96, icon: '🌐' },
  { id: 'merchant_NFT', x: 380, y: 330, type: 'merchant', label: 'NFT Market', risk: 72, icon: '🏪' },
  { id: 'merchant_FX',  x: 160, y: 360, type: 'merchant', label: 'FX Trader Pro', risk: 80, icon: '🏪' },
];

const EDGES = [
  { from: 'usr_alex92', to: 'device_A7F' },
  { from: 'usr_tom_b',  to: 'device_A7F' },
  { from: 'usr_james_w', to: 'device_A7F' },
  { from: 'usr_alex92', to: 'IP_192' },
  { from: 'usr_tom_b',  to: 'IP_VPN' },
  { from: 'usr_james_w', to: 'IP_VPN' },
  { from: 'usr_tom_b',  to: 'merchant_NFT' },
  { from: 'usr_alex92', to: 'merchant_NFT' },
  { from: 'usr_james_w', to: 'merchant_FX' },
  { from: 'IP_192',    to: 'merchant_FX' },
];

const typeColor = { user: '#6366f1', device: '#f43f5e', ip: '#f59e0b', merchant: '#10b981' };
const typeBg    = { user: 'rgba(99,102,241,0.2)', device: 'rgba(244,63,94,0.2)', ip: 'rgba(245,158,11,0.15)', merchant: 'rgba(16,185,129,0.15)' };

function getNode(id) { return NODES.find(n => n.id === id); }

export default function FraudGraph() {
  const [hovered, setHovered] = useState(null);
  const [selected, setSelected] = useState(null);

  const hoveredNode = hovered ? NODES.find(n => n.id === hovered) : null;
  const selectedNode = selected ? NODES.find(n => n.id === selected) : null;
  const displayNode = selectedNode || hoveredNode;

  const connectedEdges = hovered
    ? EDGES.filter(e => e.from === hovered || e.to === hovered)
    : [];
  const connectedIds = new Set(connectedEdges.flatMap(e => [e.from, e.to]));

  return (
    <div>
      <Topbar title="Fraud Graph" subtitle="Entity relationship graph — shared devices, IPs & merchants" />
      <div className="page">

        {/* Legend */}
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          {Object.entries(typeColor).map(([type, color]) => (
            <div key={type} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-secondary)' }}>
              <div style={{ width: 10, height: 10, borderRadius: '50%', background: color }} />
              {type.charAt(0).toUpperCase() + type.slice(1)}
            </div>
          ))}
          <div style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-muted)' }}>
            💡 Hover / click nodes to explore connections
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: 20 }}>
          {/* Graph Canvas */}
          <div className="glass" style={{ padding: 0, overflow: 'hidden', minHeight: 460 }}>
            <svg width="100%" height="460" style={{ display: 'block' }}>
              <defs>
                <filter id="glow">
                  <feGaussianBlur stdDeviation="3" result="coloredBlur" />
                  <feMerge><feMergeNode in="coloredBlur" /><feMergeNode in="SourceGraphic" /></feMerge>
                </filter>
              </defs>

              {/* Edges */}
              {EDGES.map((edge, i) => {
                const from = getNode(edge.from);
                const to = getNode(edge.to);
                if (!from || !to) return null;
                const isHighlighted = hovered && connectedEdges.includes(edge);
                return (
                  <line
                    key={i}
                    x1={from.x} y1={from.y} x2={to.x} y2={to.y}
                    stroke={isHighlighted ? '#f43f5e' : 'rgba(148,163,184,0.12)'}
                    strokeWidth={isHighlighted ? 2 : 1}
                    strokeDasharray={isHighlighted ? 'none' : '4 3'}
                    style={{ transition: 'stroke 0.2s, stroke-width 0.2s' }}
                  />
                );
              })}

              {/* Nodes */}
              {NODES.map(node => {
                const color = typeColor[node.type];
                const bg = typeBg[node.type];
                const isActive = hovered === node.id || selected === node.id;
                const isDimmed = hovered && !connectedIds.has(node.id) && hovered !== node.id;
                return (
                  <g
                    key={node.id}
                    transform={`translate(${node.x}, ${node.y})`}
                    style={{ cursor: 'pointer', opacity: isDimmed ? 0.3 : 1, transition: 'opacity 0.2s' }}
                    onMouseEnter={() => setHovered(node.id)}
                    onMouseLeave={() => setHovered(null)}
                    onClick={() => setSelected(selected === node.id ? null : node.id)}
                  >
                    {/* Glow ring for high risk */}
                    {node.risk >= 80 && (
                      <circle r={26} fill="rgba(244,63,94,0.08)" stroke="rgba(244,63,94,0.3)" strokeWidth={1.5}>
                        <animate attributeName="r" values="24;30;24" dur="2s" repeatCount="indefinite" />
                        <animate attributeName="opacity" values="0.6;0.1;0.6" dur="2s" repeatCount="indefinite" />
                      </circle>
                    )}
                    <circle
                      r={isActive ? 22 : 20}
                      fill={bg}
                      stroke={color}
                      strokeWidth={isActive ? 2.5 : 1.5}
                      filter={isActive ? 'url(#glow)' : 'none'}
                      style={{ transition: 'r 0.2s, stroke-width 0.2s' }}
                    />
                    <text textAnchor="middle" dominantBaseline="middle" fontSize={14}>{node.icon}</text>
                    <text
                      y={30} textAnchor="middle"
                      fontSize={9} fill={color} fontFamily="Inter" fontWeight={600}
                    >
                      {node.label.length > 12 ? node.label.slice(0, 12) + '…' : node.label}
                    </text>
                    <text y={42} textAnchor="middle" fontSize={9} fill="rgba(244,63,94,0.8)" fontFamily="JetBrains Mono">
                      {node.risk}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>

          {/* Side Panel */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Node Detail */}
            <div className="glass" style={{ padding: '18px 20px', minHeight: 200 }}>
              <span className="section-title" style={{ marginBottom: 14, display: 'block' }}>Node Inspector</span>
              {displayNode ? (
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
                    <div style={{
                      width: 40, height: 40, borderRadius: 10, fontSize: 20,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      background: typeBg[displayNode.type], border: `1px solid ${typeColor[displayNode.type]}30`
                    }}>{displayNode.icon}</div>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: 13 }}>{displayNode.label}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'capitalize' }}>{displayNode.type}</div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderTop: '1px solid var(--border)' }}>
                    <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Risk Score</span>
                    <span style={{ fontWeight: 700, color: displayNode.risk >= 80 ? '#f43f5e' : '#f59e0b', fontFamily: 'var(--font-mono)' }}>{displayNode.risk}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderTop: '1px solid var(--border)' }}>
                    <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Connections</span>
                    <span style={{ fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                      {EDGES.filter(e => e.from === displayNode.id || e.to === displayNode.id).length}
                    </span>
                  </div>
                  {displayNode.risk >= 80 && (
                    <div style={{
                      marginTop: 12, padding: '8px 10px', background: 'rgba(244,63,94,0.08)',
                      border: '1px solid rgba(244,63,94,0.2)', borderRadius: 6, fontSize: 11, color: '#fca5a5'
                    }}>
                      ⚠️ High-risk entity. Part of suspected fraud ring.
                    </div>
                  )}
                </div>
              ) : (
                <div style={{ fontSize: 12, color: 'var(--text-muted)', paddingTop: 8 }}>
                  Hover over or click a node to inspect its connections and risk profile.
                </div>
              )}
            </div>

            {/* Ring Summary */}
            <div className="glass" style={{ padding: '18px 20px' }}>
              <span className="section-title" style={{ marginBottom: 12, display: 'block' }}>Ring Summary</span>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {[
                  { label: 'Nodes', val: NODES.length },
                  { label: 'Edges', val: EDGES.length },
                  { label: 'Shared Device', val: 'device_A7F', color: '#f43f5e' },
                  { label: 'Compromised Users', val: '3', color: '#f43f5e' },
                  { label: 'Fraud Ring Score', val: '91 / CRITICAL', color: '#f43f5e' },
                ].map(item => (
                  <div key={item.label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, padding: '4px 0', borderBottom: '1px solid var(--border)' }}>
                    <span style={{ color: 'var(--text-secondary)' }}>{item.label}</span>
                    <span style={{ fontWeight: 600, color: item.color || 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{item.val}</span>
                  </div>
                ))}
              </div>
              <button className="btn btn-danger" style={{ width: '100%', justifyContent: 'center', marginTop: 16, fontSize: 12 }}>
                🚨 Block Entire Ring
              </button>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
