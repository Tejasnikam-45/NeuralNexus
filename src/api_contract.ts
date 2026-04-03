/**
 * ============================================================
 * NeuralNexus — API Contract (Source of Truth)
 * ============================================================
 * ALL frontend data fetching must use these types.
 * ALL backend responses must conform to these shapes.
 * When the real API is ready, replace BASE_URL only.
 * ============================================================
 */

export const BASE_URL = "http://localhost:8000"; // FastAPI dev server

// ─────────────────────────────────────────────
// SHARED PRIMITIVES
// ─────────────────────────────────────────────

export type Decision = "approve" | "mfa" | "block";
export type Severity = "critical" | "high" | "medium" | "low" | "info";
export type EventType =
  | "login_suspicious"
  | "login_ok"
  | "session_hijack"
  | "profile_change"
  | "mfa_fail"
  | "mfa_ok"
  | "transaction";
export type NodeType = "user" | "device" | "ip" | "merchant";
export type ModelStatus = "active" | "archived" | "staging";

// ─────────────────────────────────────────────
// POST /score
// Score a single transaction before it completes
// ─────────────────────────────────────────────

export interface ScoreRequest {
  transaction_id: string;        // e.g. "TXN-8821"
  user_id: string;               // e.g. "usr_alex92"
  amount: number;                // raw amount in USD
  merchant_name: string;
  merchant_category: string;     // MCC code or label
  transaction_type: string;      // "crypto" | "wire" | "ecommerce" | "p2p" | ...
  device_id: string;             // hashed fingerprint
  ip_address: string;
  latitude: number;
  longitude: number;
  timestamp_utc: string;         // ISO 8601
  currency: string;              // "USD" | "GBP" etc.
  session_id: string;            // links to ATO event log
}

export interface ShapFeature {
  feature_name: string;          // human-readable label
  shap_value: number;            // positive = pushes toward fraud
  direction: "risk" | "safe";
}

export interface ScoreResponse {
  transaction_id: string;
  user_id: string;
  risk_score: number;            // 0–100
  decision: Decision;
  ato_chain_active: boolean;     // true if inside 30s ATO window
  ato_chain_id: string | null;   // e.g. "ATO-001"
  flags: string[];               // ["12x avg amount", "new device", "ATO chain"]
  shap_top3: ShapFeature[];      // top 3 contributing features
  rule_triggered: string | null; // e.g. "velocity>5" | "blacklisted_merchant" | null
  component_scores: {
    xgboost: number;             // 0–100
    isolation_forest: number;    // 0–100
    autoencoder: number;         // 0–100 (reconstruction error normalized)
  };
  latency_breakdown_ms: {
    redis_read: number;
    feature_compute: number;
    rule_engine: number;
    ml_inference: number;
    shap_compute: number;
    total: number;               // must be < 100
  };
  timestamp_utc: string;
}

// ─────────────────────────────────────────────
// POST /event
// Log a session event (login, MFA, profile change)
// Used by ATO chain detector
// ─────────────────────────────────────────────

export interface SessionEventRequest {
  event_type: EventType;
  user_id: string;
  session_id: string;
  device_id: string;
  ip_address: string;
  latitude: number;
  longitude: number;
  timestamp_utc: string;
  metadata: Record<string, string>; // e.g. { "mfa_method": "sms", "fail_reason": "timeout" }
}

export interface SessionEventResponse {
  event_id: string;
  ato_chain_opened: boolean;     // true if this event triggered a new ATO chain window
  ato_chain_id: string | null;
  risk_signal: number;           // 0–100 login-level risk
  message: string;
}

// ─────────────────────────────────────────────
// GET /profile/{user_id}
// Behavioral profile for a user (from Redis/profile store)
// ─────────────────────────────────────────────

export interface UserProfile {
  user_id: string;
  account_age_days: number;
  mean_txn_amount: number;
  std_txn_amount: number;
  txn_count_last_24h: number;
  txn_count_last_1h: number;
  txn_count_total: number;
  known_devices: string[];       // list of known device_id hashes
  known_ips: string[];
  usual_hours: number[];         // hours (0–23) commonly used
  usual_merchant_categories: string[];
  country_codes_seen: string[];
  last_txn_timestamp_utc: string;
  is_high_risk: boolean;
  synthetic_identity_score: number | null;  // S9 — null until S9 is built
  profile_last_updated_utc: string;
}

// ─────────────────────────────────────────────
// POST /feedback
// Analyst label — feeds adaptive retraining queue
// ─────────────────────────────────────────────

export type FeedbackLabel = "true_fraud" | "false_positive" | "true_legitimate" | "needs_review";

export interface FeedbackRequest {
  transaction_id: string;
  analyst_id: string;
  label: FeedbackLabel;
  analyst_note: string;          // free text, optional but stored
  override_decision: Decision | null;  // null if analyst agrees with system
  timestamp_utc: string;
}

export interface FeedbackResponse {
  feedback_id: string;
  queue_size: number;            // current retraining queue label count
  retrain_threshold: number;     // 50 — will trigger when queue_size >= this
  next_scheduled_retrain: string | null; // ISO 8601 or null
  message: string;
}

// ─────────────────────────────────────────────
// GET /transactions/live?limit=N&since_id=X
// FALLBACK ONLY — use WebSocket /ws/live as primary.
// Only use this if WebSocket is unavailable on the client.
// ─────────────────────────────────────────────

export interface LiveTransaction {
  transaction_id: string;
  user_id: string;
  amount: number;
  merchant_name: string;
  transaction_type: string;
  device_label: "known" | "new";   // derived from profile — NOT raw device_id
  location_label: string;           // "Lagos, NG" — human readable
  risk_score: number;
  decision: Decision;
  ato_flag: boolean;
  flags: string[];
  timestamp_utc: string;
}

export interface LiveFeedResponse {
  transactions: LiveTransaction[];
  total_count: number;
  last_id: string;               // use as since_id in next poll
}

// ─────────────────────────────────────────────
// WebSocket ws://localhost:8000/ws/live
// Real-time push — one ScoreResponse per transaction
// ─────────────────────────────────────────────
// Message shape = LiveTransaction (subset of ScoreResponse)
// Client connects once; server pushes on every scored transaction.

// ─────────────────────────────────────────────
// GET /ato/chains?status=active
// All active ATO chains
// ─────────────────────────────────────────────

export interface ATOChainEvent {
  event_type: EventType;
  timestamp_utc: string;
  detail: string;                // human-readable description
  severity: Severity;
}

export interface ATOChain {
  chain_id: string;              // "ATO-001"
  user_id: string;
  status: "active" | "resolved" | "false_positive";
  risk_score: number;
  summary: string;               // one-line human summary
  start_time_utc: string;
  end_time_utc: string | null;   // null if still open
  duration_seconds: number | null;
  events: ATOChainEvent[];
  linked_device_id: string;
  attacker_ip: string;
  linked_account_ids: string[];  // other accounts in the same ring
}

export interface ATOChainsResponse {
  chains: ATOChain[];
  active_count: number;
  resolved_today: number;
}

// ─────────────────────────────────────────────
// GET /graph/fraud-ring
// Entity graph for fraud ring visualization
// ─────────────────────────────────────────────

export interface GraphNode {
  node_id: string;
  node_type: NodeType;
  label: string;                 // display label
  risk_score: number;
  is_confirmed_fraud: boolean;
}

export interface GraphEdge {
  from_id: string;
  to_id: string;
  edge_type: "shared_device" | "shared_ip" | "shared_merchant" | "same_session";
  strength: number;              // 0–1 — how many shared transactions
}

export interface FraudRingResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
  ring_risk_score: number;       // highest node risk in ring
  community_id: string;          // Louvain community label
  recommended_action: "monitor" | "block_ring" | "escalate";
}

// ─────────────────────────────────────────────
// GET /synthetic-identity/suspects
// S9 — Synthetic identity detection
// ─────────────────────────────────────────────

export interface SyntheticIdentitySuspect {
  user_id: string;
  synthetic_score: number;       // 0–100
  cluster_id: string;            // which cluster this user belongs to
  similar_accounts: string[];    // user_ids with suspicious similarity
  flags: string[];               // ["new account velocity", "shared device pattern", "DOB anomaly"]
  created_at_utc: string;
}

export interface SyntheticIdentityResponse {
  suspects: SyntheticIdentitySuspect[];
  total_clusters: number;
  high_risk_count: number;
}

// ─────────────────────────────────────────────
// GET /model/performance
// Current model metrics + MLflow run history
// ─────────────────────────────────────────────

export interface ModelRun {
  version: string;               // "v2.4.1"
  run_id: string;                // MLflow run ID
  retrain_date_utc: string;
  trigger: string;               // "analyst_labels_50" | "scheduled"
  precision: number;             // 0–100
  recall: number;
  f1_score: number;
  aucpr: number;                 // Area Under Precision-Recall curve
  label_count_used: number;
  status: ModelStatus;
}

export interface ModelPerformanceResponse {
  current_version: string;
  precision: number;
  recall: number;
  f1_score: number;
  aucpr: number;
  p99_latency_ms: number;        // real p99 from last 1000 requests
  avg_latency_ms: number;
  throughput_tps: number;        // transactions per second
  retrain_queue_size: number;
  retrain_threshold: number;
  auto_retrain_enabled: boolean;
  run_history: ModelRun[];
}

// ─────────────────────────────────────────────
// GET /dashboard/stats
// Top-level KPIs for the dashboard
// ─────────────────────────────────────────────

export interface DashboardStats {
  transactions_today: number;
  transactions_last_hour: number;
  blocked_today: number;
  mfa_today: number;
  approved_today: number;
  fraud_rate_pct: number;
  avg_latency_ms: number;
  active_ato_chains: number;
  model_version: string;
  system_status: "healthy" | "degraded" | "down";
}

// ─────────────────────────────────────────────
// POST /simulator/run
// Trigger a fraud scenario through the real scoring engine
// ─────────────────────────────────────────────

export type SimulatorScenario =
  | "ato_attack"
  | "card_fraud_burst"
  | "fraud_ring_probe"
  | "legit_spike"
  | "sim_swap";

export interface SimulatorRequest {
  scenario: SimulatorScenario;
  speed_ms: number;              // delay between transactions (200 | 600 | 1200)
  count: number;                 // number of transactions to generate
}

export interface SimulatorResponse {
  run_id: string;
  results: ScoreResponse[];      // real scores from real model
  summary: {
    total: number;
    blocked: number;
    mfa: number;
    approved: number;
    avg_score: number;
    avg_latency_ms: number;
    ato_chains_triggered: number;
  };
}

// ─────────────────────────────────────────────
// POST /model/retrain
// Manual retrain trigger — bypasses label floor
// Use in demo to force a version increment live for judges
// Requires header: X-Admin-Key: nexus-dev
// ─────────────────────────────────────────────

export interface ManualRetrainRequest {
  reason: string;              // e.g. "demo", "analyst_request"
  admin_key: string;           // must match ADMIN_KEY env var
}

export interface ManualRetrainResponse {
  triggered: boolean;
  previous_version: string;    // e.g. "v1.0.0"
  new_version: string | null;  // null if quality gate rejected new model
  aucpr_delta: number | null;  // new_aucpr - old_aucpr (null if rejected)
  message: string;             // human-readable result
  mlflow_run_id: string;       // always logged, regardless of swap
}

// ─────────────────────────────────────────────
// GET /health
// System health — show as a live pill in Dashboard topbar
// Proves production-readiness to judges
// ─────────────────────────────────────────────

export interface HealthResponse {
  status: "healthy" | "degraded" | "down";
  model_version: string;       // e.g. "v1.0.1"
  uptime_ms: number;           // ms since server started
  redis_ok: boolean;           // can we read from Redis/fakeredis
  ato_chains_open: number;     // count of currently active ATO chains
  models_loaded: {
    xgboost: boolean;
    isolation_forest: boolean;
    autoencoder: boolean;
    shap_explainer: boolean;
  };
  last_scored_at: string | null;  // ISO 8601 of last transaction scored
}

// ─────────────────────────────────────────────
// ERROR SHAPE (all endpoints)
// ─────────────────────────────────────────────

export interface APIError {
  error_code: string;            // "SCORE_TIMEOUT" | "PROFILE_NOT_FOUND" | ...
  message: string;
  request_id: string;
  timestamp_utc: string;
}
