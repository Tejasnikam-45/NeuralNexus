// ===== MOCK DATA for NeuralNexus UI =====

export const TRANSACTIONS = [
  { id: 'TXN-8821', user: 'usr_alex92', amount: 4820, merchant: 'Crypto Exchange XY', type: 'Crypto Purchase', score: 91, decision: 'block', device: 'New Device', location: 'Lagos, NG', time: '14:03:11', ato: true, flags: ['12x avg', 'new device', 'ATO chain'] },
  { id: 'TXN-8820', user: 'usr_sarah_k', amount: 250, merchant: 'Amazon US', type: 'E-commerce', score: 22, decision: 'approve', device: 'Known', location: 'Seattle, US', time: '14:02:58', ato: false, flags: [] },
  { id: 'TXN-8819', user: 'usr_mike99', amount: 1200, merchant: 'Wire Transfer', type: 'P2P Transfer', score: 62, decision: 'mfa', device: 'Known', location: 'London, UK', time: '14:02:44', ato: false, flags: ['unusual hour', 'velocity spike'] },
  { id: 'TXN-8818', user: 'usr_priya_m', amount: 89, merchant: 'Netflix', type: 'Subscription', score: 8, decision: 'approve', device: 'Known', location: 'Mumbai, IN', time: '14:02:31', ato: false, flags: [] },
  { id: 'TXN-8817', user: 'usr_james_w', amount: 3100, merchant: 'FX Trader Pro', type: 'FX Trade', score: 78, decision: 'block', device: 'New Device', location: 'Kiev, UA', time: '14:02:19', ato: true, flags: ['new IP', 'ATO chain', 'blacklisted merchant'] },
  { id: 'TXN-8816', user: 'usr_chen_li', amount: 450, merchant: 'Apple Store', type: 'Electronics', score: 35, decision: 'approve', device: 'Known', location: 'Shanghai, CN', time: '14:02:05', ato: false, flags: ['border velocity'] },
  { id: 'TXN-8815', user: 'usr_ana_r', amount: 720, merchant: 'Steam Gaming', type: 'Gaming', score: 54, decision: 'mfa', device: 'New Device', location: 'São Paulo, BR', time: '14:01:52', ato: false, flags: ['new device', 'moderate amount'] },
  { id: 'TXN-8814', user: 'usr_tom_b', amount: 5600, merchant: 'NFT Marketplace', type: 'NFT', score: 85, decision: 'block', device: 'New Device', location: 'Anonymous VPN', time: '14:01:38', ato: true, flags: ['VPN detected', 'ATO chain', '18x avg'] },
];

export const HOURLY_VOLUME = [
  { hour: '06:00', approved: 142, blocked: 3, mfa: 8 },
  { hour: '07:00', approved: 289, blocked: 7, mfa: 14 },
  { hour: '08:00', approved: 521, blocked: 11, mfa: 28 },
  { hour: '09:00', approved: 694, blocked: 18, mfa: 41 },
  { hour: '10:00', approved: 812, blocked: 24, mfa: 55 },
  { hour: '11:00', approved: 745, blocked: 29, mfa: 49 },
  { hour: '12:00', approved: 903, blocked: 38, mfa: 67 },
  { hour: '13:00', approved: 876, blocked: 41, mfa: 72 },
  { hour: '14:00', approved: 634, blocked: 52, mfa: 58 },
];

export const SCORE_DISTRIBUTION = [
  { range: '0-10',  count: 1420, fill: '#10b981' },
  { range: '10-20', count: 980,  fill: '#10b981' },
  { range: '20-30', count: 710,  fill: '#34d399' },
  { range: '30-40', count: 540,  fill: '#6ee7b7' },
  { range: '40-50', count: 310,  fill: '#f59e0b' },
  { range: '50-60', count: 220,  fill: '#fbbf24' },
  { range: '60-70', count: 180,  fill: '#fb923c' },
  { range: '70-80', count: 120,  fill: '#f43f5e' },
  { range: '80-90', count: 85,   fill: '#e11d48' },
  { range: '90+',   count: 42,   fill: '#9f1239' },
];

export const SHAP_FEATURES = [
  { name: 'Amount vs. User Avg', value: 0.42, positive: true },
  { name: 'New Device Fingerprint', value: 0.31, positive: true },
  { name: 'ATO Chain Signal', value: 0.28, positive: true },
  { name: 'Transaction Velocity', value: 0.19, positive: true },
  { name: 'Unusual Hour', value: 0.14, positive: true },
  { name: 'Geo Distance', value: 0.11, positive: true },
  { name: 'Merchant Category', value: -0.08, positive: false },
  { name: 'Account Age', value: -0.05, positive: false },
];

export const ATO_CHAIN_EVENTS = [
  { type: 'login_suspicious', time: '13:58:02', icon: '🔐', label: 'Suspicious Login Attempt', detail: 'New device • Kyiv, UA • Failed MFA bypassed via SIM swap', severity: 'critical' },
  { type: 'session_hijack',   time: '13:58:45', icon: '⚠️', label: 'Session Anomaly Detected', detail: 'IP changed mid-session • User-agent mismatch • Cookie replay detected', severity: 'high' },
  { type: 'profile_change',  time: '13:59:12', icon: '✏️', label: 'Profile Data Modified', detail: 'Phone number changed • Email updated • 2FA device removed', severity: 'high' },
  { type: 'transaction',     time: '14:01:38', icon: '💸', label: 'Transaction Initiated', detail: '$5,600 → NFT Marketplace • Score 85 • → BLOCKED', severity: 'blocked' },
];

export const FRAUD_RING_NODES = [
  { id: 'usr_alex92', type: 'user', risk: 91 },
  { id: 'usr_james_w', type: 'user', risk: 78 },
  { id: 'usr_tom_b', type: 'user', risk: 85 },
  { id: 'device_A7F', type: 'device', risk: 95 },
  { id: 'IP_192.x', type: 'ip', risk: 88 },
  { id: 'merchant_NFT', type: 'merchant', risk: 72 },
];

export const RECENT_ALERTS = [
  { id: 1, type: 'ato',      msg: 'ATO chain detected — usr_tom_b', time: '14:01', severity: 'critical' },
  { id: 2, type: 'ring',     msg: 'Fraud ring: 3 accounts share device A7F', time: '13:58', severity: 'high' },
  { id: 3, type: 'velocity', msg: 'Velocity spike: usr_mike99 — 8 TXNs/min', time: '13:55', severity: 'medium' },
  { id: 4, type: 'blacklist',msg: 'Blacklisted merchant flagged: FX Trader Pro', time: '13:51', severity: 'high' },
  { id: 5, type: 'model',    msg: 'Model retrained — v2.4.1 deployed (MLflow)', time: '13:45', severity: 'info' },
];

export const MODEL_PERFORMANCE = [
  { day: 'Mon', precision: 94.2, recall: 91.8, f1: 93.0 },
  { day: 'Tue', precision: 94.8, recall: 92.1, f1: 93.4 },
  { day: 'Wed', precision: 95.1, recall: 93.4, f1: 94.2 },
  { day: 'Thu', precision: 94.6, recall: 92.9, f1: 93.7 },
  { day: 'Fri', precision: 96.2, recall: 94.1, f1: 95.1 },
  { day: 'Sat', precision: 95.8, recall: 93.8, f1: 94.8 },
  { day: 'Sun', precision: 96.5, recall: 94.7, f1: 95.6 },
];

export const LATENCY_DATA = [
  { t: '1', ms: 42 }, { t: '2', ms: 38 }, { t: '3', ms: 51 },
  { t: '4', ms: 39 }, { t: '5', ms: 44 }, { t: '6', ms: 37 },
  { t: '7', ms: 48 }, { t: '8', ms: 41 }, { t: '9', ms: 35 },
  { t: '10', ms: 46 }, { t: '11', ms: 40 }, { t: '12', ms: 43 },
];
