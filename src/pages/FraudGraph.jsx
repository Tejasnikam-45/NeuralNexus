import React, { useState, useEffect, useMemo } from 'react';
import Topbar from '../components/Topbar';
import { fetchTransactionsRecent } from '../api';

const typeColor = { user: '#6366f1', device: '#f43f5e', ip: '#f59e0b', merchant: '#10b981' };
const typeBg    = { user: 'rgba(99,102,241,0.2)', device: 'rgba(244,63,94,0.2)', ip: 'rgba(245,158,11,0.15)', merchant: 'rgba(16,185,129,0.15)' };
const typeIcon  = { user: '👤', device: '💻', ip: '🌐', merchant: '🏪' };

export default function FraudGraph() {
  const [hovered, setHovered] = useState(null);
  const [selected, setSelected] = useState(null);
  const [rawTxns, setRawTxns] = useState([]);
  const [loading, setLoading] = useState(true);

  // Poll for recent transactions
  useEffect(() => {
    const load = () => {
      fetchTransactionsRecent(300).then(data => {
        setRawTxns(data.transactions || []);
        setLoading(false);
      }).catch(err => {
        console.error(err);
        setLoading(false);
      });
    };
    load();
    const intv = setInterval(load, 5000); // refresh every 5s
    return () => clearInterval(intv);
  }, []);

  // Compute True Graph Data dynamically
  const { NODES, EDGES, ringStats } = useMemo(() => {
    if (rawTxns.length === 0) return { NODES: [], EDGES: [], ringStats: {} };

    // 1. Identify suspicious transactions (or take recent ones to demonstrate the graph)
    let suspicious = rawTxns.filter(t => t.score >= 65);
    
    // If no suspicious exist, just map the 4 most recent to show the active entities
    if (suspicious.length === 0) {
      suspicious = rawTxns.slice(0, 4);
    } else {
      // Find shared devices/IPs from suspicious set to expose the "ring"
      const suspiciousDevices = new Set(suspicious.map(t => t.device_id));
      const suspiciousIps = new Set(suspicious.map(t => t.ip_address));
      // Bring in other transactions that share these identifiers
      const ring = rawTxns.filter(t => suspiciousDevices.has(t.device_id) || suspiciousIps.has(t.ip_address));
      suspicious = ring;
    }

    // Sort to keep graph small & focused
    suspicious = suspicious.sort((a, b) => b.score - a.score).slice(0, 15);

    const nodesMap = new Map();
    const edgesArray = [];

    const addNode = (id, type, label, risk) => {
      if (!id || id.includes('unknown') || id === 'Online Store') return null; // skip generic
      if (!nodesMap.has(id)) {
        nodesMap.set(id, { id, type, label, risk, icon: typeIcon[type] });
      } else {
        const existing = nodesMap.get(id);
        if (risk > existing.risk) existing.risk = risk; // keep max risk
      }
      return id;
    };

    const addEdge = (from, to) => {
      if (from && to) edgesArray.push({ from, to });
    };

    suspicious.forEach(t => {
      const u = addNode(t.user_id, 'user', t.user_id, t.score);
      const d = addNode(t.device_id, 'device', (t.device_id || '').substring(0, 12), t.score);
      const i = addNode(t.ip_address, 'ip', t.ip_address, t.score);
      const m = addNode(t.merchant_id, 'merchant', (t.merchant_id || '').substring(0, 12), t.score);

      addEdge(u, d);
      addEdge(u, i);
      addEdge(u, m);
    });

    // 2. Assign coordinates in layered approach for visual clarity
    const layers = { user: [], device: [], ip: [], merchant: [] };
    const nodesList = Array.from(nodesMap.values());
    nodesList.forEach(n => layers[n.type].push(n));

    const yOffsets = { user: 80, device: 190, ip: 300, merchant: 410 };
    
    const finalNodes = [];
    Object.keys(layers).forEach(type => {
      const arr = layers[type];
      const items = arr.length;
      if (items === 0) return;
      
      const width = document.querySelector('.glass')?.clientWidth || 700;
      const step = Math.min(180, (width - 100) / items);
      const startX = (width - ((items - 1) * step)) / 2;

      arr.forEach((n, idx) => {
        n.x = startX + idx * step;
        n.y = yOffsets[type];
        
        // slight staggering to avoid exact straight vertical lines
        if (idx % 2 !== 0) n.y += 25; 
        
        finalNodes.push(n);
      });
    });

    // Calculate Ring Stats based on this subset
    const compromisedUsers = layers.user.filter(u => u.risk >= 80).length;
    const maxScore = Math.max(0, ...finalNodes.map(n => n.risk));
    const sharedDevices = layers.device.filter(d => edgesArray.filter(e => e.to === d.id).length > 1).length;

    return { 
      NODES: finalNodes, 
      EDGES: edgesArray,
      ringStats: {
        nodes: finalNodes.length,
        edges: edgesArray.length,
        sharedDevices,
        compromisedUsers,
        maxScore
      }
    };
  }, [rawTxns]);

  const getNode = (id) => NODES.find(n => n.id === id);

  const hoveredNode = hovered ? getNode(hovered) : null;
  const selectedNode = selected ? getNode(selected) : null;
  const displayNode = selectedNode || hoveredNode;

  const connectedEdges = hovered
    ? EDGES.filter(e => e.from === hovered || e.to === hovered)
    : [];
  const connectedIds = new Set(connectedEdges.flatMap(e => [e.from, e.to]));

  return (
    <div>
      <Topbar title="Fraud Graph" subtitle="Entity relationship graph — live mapping from real-time transaction stream" />
      <div className="page" style={{ paddingTop: 20 }}>
        
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 20 }}>
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

        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 280px', gap: 20 }}>
          
          <div className="glass" style={{ padding: 0, overflow: 'hidden', minHeight: 460, position: 'relative' }}>
            {loading && <div style={{ position: 'absolute', top: 20, left: 20, color: 'var(--text-muted)' }}>Loading live stream...</div>}
            
            {!loading && NODES.length === 0 && (
              <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', textAlign: 'center', color: 'var(--text-muted)' }}>
                <div style={{ fontSize: 40, marginBottom: 12 }}>✨</div>
                <div>No active fraud entities detected.</div>
                <div style={{ fontSize: 12, marginTop: 4 }}>Graph will render automatically when data flows.</div>
              </div>
            )}

            {NODES.length > 0 && (
              <svg width="100%" height="520" style={{ display: 'block' }}>
                <defs>
                  <filter id="glow">
                    <feGaussianBlur stdDeviation="3" result="coloredBlur" />
                    <feMerge><feMergeNode in="coloredBlur" /><feMergeNode in="SourceGraphic" /></feMerge>
                  </filter>
                </defs>

                {EDGES.map((edge, i) => {
                  const from = getNode(edge.from);
                  const to = getNode(edge.to);
                  if (!from || !to) return null;
                  const isHighlighted = hovered && connectedEdges.includes(edge);
                  return (
                    <line
                      key={`${edge.from}-${edge.to}-${i}`}
                      x1={from.x} y1={from.y} x2={to.x} y2={to.y}
                      stroke={isHighlighted ? '#f43f5e' : 'rgba(148,163,184,0.12)'}
                      strokeWidth={isHighlighted ? 2 : 1}
                      strokeDasharray={isHighlighted ? 'none' : '4 3'}
                      style={{ transition: 'stroke 0.2s, stroke-width 0.2s' }}
                    />
                  );
                })}

                {NODES.map(node => {
                  const color = typeColor[node.type];
                  const bg = typeBg[node.type];
                  const isActive = hovered === node.id || selected === node.id;
                  const isDimmed = hovered && !connectedIds.has(node.id) && hovered !== node.id;
                  return (
                    <g
                      key={node.id}
                      transform={`translate(${node.x}, ${node.y})`}
                      style={{ cursor: 'pointer', opacity: isDimmed ? 0.2 : 1, transition: 'all 0.3s ease' }}
                      onMouseEnter={() => setHovered(node.id)}
                      onMouseLeave={() => setHovered(null)}
                      onClick={() => setSelected(selected === node.id ? null : node.id)}
                    >
                      {node.risk >= 80 && !isDimmed && (
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
                      <text y={30} textAnchor="middle" fontSize={9} fill={color} fontFamily="Inter" fontWeight={600}>
                        {node.label.length > 15 ? node.label.slice(0, 15) + '…' : node.label}
                      </text>
                      <text y={42} textAnchor="middle" fontSize={9} fill={node.risk >= 80 ? '#fca5a5' : 'rgba(255,255,255,0.4)'} fontFamily="JetBrains Mono">
                        {node.risk > 0 ? node.risk : ''}
                      </text>
                    </g>
                  );
                })}
              </svg>
            )}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
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
                      <div style={{ fontWeight: 700, fontSize: 13, wordBreak: 'break-all' }}>{displayNode.label}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'capitalize' }}>{displayNode.type}</div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderTop: '1px solid var(--border)' }}>
                    <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Max Detected Risk</span>
                    <span style={{ fontWeight: 700, color: displayNode.risk >= 80 ? '#f43f5e' : '#10b981', fontFamily: 'var(--font-mono)' }}>{displayNode.risk}</span>
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
                      ⚠️ High-risk entity detected in anomalous cluster.
                    </div>
                  )}
                </div>
              ) : (
                <div style={{ fontSize: 12, color: 'var(--text-muted)', paddingTop: 8 }}>
                  Hover over or click a node to inspect its connections and risk profile.
                </div>
              )}
            </div>

            <div className="glass" style={{ padding: '18px 20px' }}>
              <span className="section-title" style={{ marginBottom: 12, display: 'block' }}>Ring Summary</span>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {[
                  { label: 'Active Nodes', val: ringStats.nodes },
                  { label: 'Connections', val: ringStats.edges },
                  { label: 'Shared Devices', val: ringStats.sharedDevices, color: ringStats.sharedDevices > 0 ? '#f59e0b' : '' },
                  { label: 'Compromised Users', val: ringStats.compromisedUsers, color: ringStats.compromisedUsers > 0 ? '#f43f5e' : '' },
                  { label: 'Cluster Risk', val: ringStats.maxScore >= 80 ? `${ringStats.maxScore} / CRITICAL` : `${ringStats.maxScore || 0} / NORMAL`, color: ringStats.maxScore >= 80 ? '#f43f5e' : '#10b981' },
                ].map(item => (
                  <div key={item.label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, padding: '4px 0', borderBottom: '1px solid var(--border)' }}>
                    <span style={{ color: 'var(--text-secondary)' }}>{item.label}</span>
                    <span style={{ fontWeight: 600, color: item.color || 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{item.val || 0}</span>
                  </div>
                ))}
              </div>
              <button disabled={ringStats.maxScore < 80} className="btn btn-danger" style={{ width: '100%', justifyContent: 'center', marginTop: 16, fontSize: 12, opacity: ringStats.maxScore < 80 ? 0.3 : 1 }}>
                🚨 Block Entity Cluster
              </button>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
