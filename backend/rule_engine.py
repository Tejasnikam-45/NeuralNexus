"""
============================================================
NeuralNexus — Stage S7: Rule Engine
============================================================
Hard deterministic rules that run BEFORE the ML ensemble.

Architecture position:
    Profile Store + ATO Detector
          ↓
    [Rule Engine]   ← this file
          ↓
    ML Ensemble (XGB + IsoForest + AE)
          ↓
    Risk Score Aggregator

Rules can:
  • OVERRIDE  → force approve / MFA / block regardless of ML score
  • BOOST     → add N points to the ML score (amplifier)

Rule evaluation is O(1) per rule — total budget: 5ms.

Design principles:
  1. Rules are pure functions (no side effects, no DB writes).
  2. Each rule returns a RuleResult — never raises.
  3. Rules run in priority order; first OVERRIDE wins.
  4. Rule IDs are stable strings used in SHAP-like explanations.

Run self-test:
    python backend/rule_engine.py
============================================================
"""

from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass, field
from typing import Optional

# ── dotenv (reads ATO_WINDOW_SECONDS etc.) ─────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ─────────────────────────────────────────────
# BLACKLISTS  (extend from DB/config in prod)
# ─────────────────────────────────────────────

# Merchant category codes considered high-risk
HIGH_RISK_MERCHANT_CATS: frozenset[int] = frozenset({
    6051,   # Non-Financial Institutions (crypto exchanges)
    6211,   # Security Brokers / Dealers (FX)
    6050,   # Quasi-Cash (prepaid cards)
    7995,   # Gambling / Lotteries
    5993,   # Cigar Stores
    4829,   # Wire Transfers
    6099,   # Financial Institutions — non-classified
})

# Merchant IDs that are fully blacklisted (demo set)
BLACKLISTED_MERCHANTS: frozenset[str] = frozenset({
    "merch_blacklisted_1",
    "merch_blacklisted_2",
    "merch_crypto_scam_001",
})

# Known TOR exit nodes & VPN ranges (simplified — real list is 300K+ IPs)
# In production: load from a flat file or Redis set.
TOR_AND_VPN_PREFIXES: frozenset[str] = frozenset({
    "185.220.",   # Known TOR exit range
    "185.107.",   # Known VPN provider
    "198.96.",    # Known TOR relay
    "162.247.",   # Known TOR relay
    "176.10.",    # Known VPN provider (NordVPN cluster)
    "10.8.",      # OpenVPN default subnet (internal test)
})


# ─────────────────────────────────────────────
# RULE RESULT
# ─────────────────────────────────────────────

@dataclass
class RuleResult:
    rule_id:      str
    triggered:    bool
    action:       Optional[str]   # "block" | "mfa" | "approve" | None
    score_boost:  float           # added to ML score when triggered
    reason:       str             # human-readable SHAP-equivalent text
    severity:     str             # "critical" | "high" | "medium" | "low"


@dataclass
class RuleEngineOutput:
    """Aggregated result after running all rules."""
    override_action:  Optional[str]   # "block" | "mfa" | "approve" | None
    override_rule_id: Optional[str]   # which rule caused the override
    total_boost:      float           # sum of all triggered boosts
    triggered_rules:  list[RuleResult] = field(default_factory=list)
    all_rules:        list[RuleResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "override_action":  self.override_action,
            "override_rule_id": self.override_rule_id,
            "total_boost":      round(self.total_boost, 2),
            "triggered_rules": [
                {
                    "rule_id":     r.rule_id,
                    "reason":      r.reason,
                    "score_boost": r.score_boost,
                    "severity":    r.severity,
                }
                for r in self.triggered_rules
            ],
        }


# ─────────────────────────────────────────────
# INDIVIDUAL RULE FUNCTIONS
# Each takes a flat ctx dict and returns RuleResult.
# ─────────────────────────────────────────────

def rule_blacklisted_merchant(ctx: dict) -> RuleResult:
    """Hard block if merchant is on the blacklist."""
    triggered = ctx.get("merchant_id", "") in BLACKLISTED_MERCHANTS
    return RuleResult(
        rule_id="R01_BLACKLISTED_MERCHANT",
        triggered=triggered,
        action="block" if triggered else None,
        score_boost=100.0 if triggered else 0.0,
        reason="Merchant is on the global blacklist",
        severity="critical",
    )


def rule_velocity_burst(ctx: dict) -> RuleResult:
    """
    Boost if user has > 5 transactions in the last hour.
    Hard MFA if > 10 transactions in the last hour.
    """
    count_1h = int(ctx.get("txn_count_last_1h", 0))
    if count_1h > 10:
        return RuleResult(
            rule_id="R02_VELOCITY_EXTREME",
            triggered=True,
            action="mfa",
            score_boost=25.0,
            reason=f"Extreme velocity: {count_1h} txns in last hour (>10)",
            severity="high",
        )
    elif count_1h > 5:
        return RuleResult(
            rule_id="R02_VELOCITY_HIGH",
            triggered=True,
            action=None,
            score_boost=15.0,
            reason=f"High velocity: {count_1h} txns in last hour (>5)",
            severity="medium",
        )
    return RuleResult(
        rule_id="R02_VELOCITY",
        triggered=False,
        action=None,
        score_boost=0.0,
        reason="",
        severity="low",
    )


def rule_impossible_travel(ctx: dict) -> RuleResult:
    """
    Flag if the user has moved geographically faster than is physically possible.
    Threshold: > 900 km/h (faster than a commercial aircraft).
    """
    geo_km   = float(ctx.get("geo_distance_km",    0.0))
    inter_s  = float(ctx.get("inter_txn_seconds",  9999.0))

    if inter_s <= 0 or geo_km <= 0:
        return RuleResult("R03_IMPOSSIBLE_TRAVEL", False, None, 0.0, "", "low")

    speed_kmh = (geo_km / inter_s) * 3600.0
    triggered = speed_kmh > 900.0

    return RuleResult(
        rule_id="R03_IMPOSSIBLE_TRAVEL",
        triggered=triggered,
        action="mfa" if triggered else None,
        score_boost=30.0 if triggered else 0.0,
        reason=(
            f"Impossible travel: {geo_km:.0f}km in "
            f"{inter_s:.0f}s ({speed_kmh:.0f}km/h)"
        ) if triggered else "",
        severity="high" if triggered else "low",
    )


def rule_tor_or_vpn(ctx: dict) -> RuleResult:
    """Boost if IP matches known TOR exit nodes or VPN ranges."""
    ip = str(ctx.get("ip_address", ""))
    triggered = any(ip.startswith(prefix) for prefix in TOR_AND_VPN_PREFIXES)
    return RuleResult(
        rule_id="R04_TOR_VPN",
        triggered=triggered,
        action=None,
        score_boost=20.0 if triggered else 0.0,
        reason=f"IP {ip} matches TOR/VPN prefix list",
        severity="high" if triggered else "low",
    )


def rule_new_account_high_amount(ctx: dict) -> RuleResult:
    """
    New accounts (< 30 days old) sending large amounts are high risk.
    Threshold: amount > 5× user mean AND account < 30 days old.
    """
    age_days   = float(ctx.get("account_age_days",          30.0))
    ratio      = float(ctx.get("amount_to_user_mean_ratio",  1.0))
    amount     = float(ctx.get("amount_usd",                 0.0))

    triggered = age_days < 30 and ratio > 5.0 and amount > 1000.0
    return RuleResult(
        rule_id="R05_NEW_ACCOUNT_HIGH_AMOUNT",
        triggered=triggered,
        action="mfa" if triggered else None,
        score_boost=20.0 if triggered else 0.0,
        reason=(
            f"New account ({age_days:.0f}d) sending "
            f"{ratio:.1f}× their usual amount (${amount:,.0f})"
        ) if triggered else "",
        severity="high" if triggered else "low",
    )


def rule_high_risk_merchant_category(ctx: dict) -> RuleResult:
    """Boost for transactions to high-risk merchant category codes."""
    mcc = int(ctx.get("merchant_category_encoded", 0))
    triggered = mcc in HIGH_RISK_MERCHANT_CATS
    return RuleResult(
        rule_id="R06_HIGH_RISK_MCC",
        triggered=triggered,
        action=None,
        score_boost=10.0 if triggered else 0.0,
        reason=f"Merchant category {mcc} is in high-risk list (crypto/FX/wire/gambling)",
        severity="medium" if triggered else "low",
    )


def rule_ato_chain_active(ctx: dict) -> RuleResult:
    """
    Elevate to MFA immediately if an ATO chain is active.
    This runs before ML — if ATO is firing, we challenge regardless.
    """
    chain_active = int(ctx.get("ato_chain_active", 0))
    chain_score  = float(ctx.get("ato_chain_risk_score", 0.0))

    if not chain_active:
        return RuleResult("R07_ATO_CHAIN", False, None, 0.0, "", "low")

    action = "block" if chain_score >= 80.0 else "mfa"
    return RuleResult(
        rule_id="R07_ATO_CHAIN",
        triggered=True,
        action=action,
        score_boost=35.0,
        reason=(
            f"Active ATO chain detected (risk={chain_score:.0f}). "
            f"Suspicious login preceded this transaction."
        ),
        severity="critical" if action == "block" else "high",
    )


def rule_amount_round_large(ctx: dict) -> RuleResult:
    """
    Round amounts above $10,000 are a common fraud pattern
    (structuring / layering).
    """
    amount       = float(ctx.get("amount_usd", 0.0))
    is_round     = bool(ctx.get("is_round_amount", False))
    triggered    = is_round and amount >= 10_000.0

    return RuleResult(
        rule_id="R08_ROUND_LARGE_AMOUNT",
        triggered=triggered,
        action=None,
        score_boost=10.0 if triggered else 0.0,
        reason=f"Round amount ≥ $10,000 (${amount:,.0f}) — structuring pattern",
        severity="medium" if triggered else "low",
    )


def rule_new_device_new_ip_combined(ctx: dict) -> RuleResult:
    """
    New device AND new IP on the same transaction is a strong ATO signal
    even without a logged session event.
    """
    new_dev = int(ctx.get("is_new_device", 0))
    new_ip  = int(ctx.get("is_new_ip",     0))
    triggered = bool(new_dev and new_ip)

    return RuleResult(
        rule_id="R09_NEW_DEVICE_AND_IP",
        triggered=triggered,
        action=None,
        score_boost=15.0 if triggered else 0.0,
        reason="New device AND new IP on same transaction — strong ATO indicator",
        severity="high" if triggered else "low",
    )


def rule_known_fraud_graph_ring(ctx: dict) -> RuleResult:
    """
    Block transactions from accounts in a confirmed fraud ring
    (flag set by graph engine S10).
    """
    in_ring = int(ctx.get("graph_is_in_known_ring", 0))
    ring_score = float(ctx.get("graph_ring_risk_score", 0.0))

    if not in_ring:
        return RuleResult("R10_FRAUD_RING", False, None, 0.0, "", "low")

    action = "block" if ring_score >= 80.0 else "mfa"
    return RuleResult(
        rule_id="R10_FRAUD_RING",
        triggered=True,
        action=action,
        score_boost=40.0,
        reason=f"Account is part of a confirmed fraud ring (ring_score={ring_score:.0f})",
        severity="critical",
    )


# ─────────────────────────────────────────────
# RULE REGISTRY
# Priority order: first override wins.
# ─────────────────────────────────────────────

_ALL_RULES = [
    rule_blacklisted_merchant,       # R01 — instant block
    rule_known_fraud_graph_ring,     # R10 — instant block/mfa
    rule_ato_chain_active,           # R07 — elevate on ATO
    rule_impossible_travel,          # R03 — elevate on travel anomaly
    rule_velocity_burst,             # R02 — velocity spike
    rule_new_account_high_amount,    # R05 — new account large txn
    rule_new_device_new_ip_combined, # R09 — device + IP double-new
    rule_tor_or_vpn,                 # R04 — TOR/VPN boost
    rule_high_risk_merchant_category,# R06 — MCC boost
    rule_amount_round_large,         # R08 — structuring pattern
]

# Override-action priority (in case two rules fire)
_ACTION_PRIORITY = {"block": 3, "mfa": 2, "approve": 1, None: 0}


# ─────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────

def evaluate_rules(ctx: dict) -> RuleEngineOutput:
    """
    Run all rules against the transaction context dict.

    Args:
        ctx: flat dict containing all transaction + profile + ATO features.
             Keys are the same as FEATURE_NAMES in feature_schema.py,
             plus extra context keys (merchant_id, ip_address, etc.)

    Returns:
        RuleEngineOutput with the highest-priority override action,
        total score boost, and list of triggered rule reasons.
    """
    t0 = time.perf_counter()

    all_results: list[RuleResult] = []
    triggered:   list[RuleResult] = []

    override_action: Optional[str]  = None
    override_rule:   Optional[str]  = None
    total_boost: float = 0.0

    for rule_fn in _ALL_RULES:
        try:
            result = rule_fn(ctx)
        except Exception as exc:
            # Rules must never crash the scoring engine
            result = RuleResult(
                rule_id=getattr(rule_fn, "__name__", "UNKNOWN"),
                triggered=False, action=None, score_boost=0.0,
                reason=f"Rule error: {exc}", severity="low",
            )

        all_results.append(result)

        if result.triggered:
            triggered.append(result)
            total_boost += result.score_boost

            # Track highest-priority override action
            if _ACTION_PRIORITY.get(result.action, 0) > _ACTION_PRIORITY.get(override_action, 0):
                override_action = result.action
                override_rule   = result.rule_id

    elapsed_ms = (time.perf_counter() - t0) * 1000
    if elapsed_ms > 5.0:
        import warnings
        warnings.warn(
            f"[RuleEngine] Exceeded 5ms budget: {elapsed_ms:.1f}ms",
            RuntimeWarning,
            stacklevel=2,
        )

    return RuleEngineOutput(
        override_action=override_action,
        override_rule_id=override_rule,
        total_boost=total_boost,
        triggered_rules=triggered,
        all_rules=all_results,
    )


def list_rules() -> list[dict]:
    """Returns metadata for all registered rules. Used by GET /rules endpoint."""
    results = []
    for fn in _ALL_RULES:
        # Run with safe empty ctx to get metadata
        try:
            r = fn({})
        except Exception:
            r = RuleResult(fn.__name__, False, None, 0.0, "", "low")
        results.append({
            "rule_id":     r.rule_id,
            "severity":    r.severity,
            "description": fn.__doc__.strip().split("\n")[0] if fn.__doc__ else "",
        })
    return results


# ─────────────────────────────────────────────
# SELF-TEST
# Run: python backend/rule_engine.py
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("\n[S7] Rule Engine Self-Test\n")

    # Test 1: Blacklisted merchant → block
    ctx1 = {"merchant_id": "merch_blacklisted_1"}
    out1 = evaluate_rules(ctx1)
    assert out1.override_action == "block", f"Expected block, got {out1.override_action}"
    assert out1.override_rule_id == "R01_BLACKLISTED_MERCHANT"
    print("  ✓ R01 Blacklisted merchant → block")

    # Test 2: Velocity burst (>10/hr) → mfa
    ctx2 = {"txn_count_last_1h": 12}
    out2 = evaluate_rules(ctx2)
    assert out2.override_action == "mfa", f"Expected mfa, got {out2.override_action}"
    print("  ✓ R02 Velocity extreme → mfa")

    # Test 3: Velocity moderate (6/hr) → score boost only, no override
    ctx3 = {"txn_count_last_1h": 6}
    out3 = evaluate_rules(ctx3)
    assert out3.override_action is None
    assert out3.total_boost >= 15.0, f"Expected boost >= 15, got {out3.total_boost}"
    print(f"  ✓ R02 Velocity high → no override, boost={out3.total_boost:.0f}")

    # Test 4: Impossible travel → mfa
    ctx4 = {
        "geo_distance_km":   1500.0,   # 1500km
        "inter_txn_seconds": 600.0,    # 10 minutes → 9000 km/h  (impossible)
    }
    out4 = evaluate_rules(ctx4)
    assert out4.override_action == "mfa", f"Expected mfa, got {out4.override_action}"
    print(f"  ✓ R03 Impossible travel → mfa")

    # Test 5: TOR IP → score boost
    ctx5 = {"ip_address": "185.220.10.1"}
    out5 = evaluate_rules(ctx5)
    assert out5.total_boost >= 20.0, f"Expected boost >= 20, got {out5.total_boost}"
    print(f"  ✓ R04 TOR IP → boost={out5.total_boost:.0f}")

    # Test 6: New account + high amount → mfa
    ctx6 = {
        "account_age_days":          10.0,
        "amount_to_user_mean_ratio": 8.0,
        "amount_usd":                5000.0,
    }
    out6 = evaluate_rules(ctx6)
    assert out6.override_action == "mfa", f"Expected mfa, got {out6.override_action}"
    print("  ✓ R05 New account high amount → mfa")

    # Test 7: ATO chain active (high score) → block
    ctx7 = {
        "ato_chain_active":    1,
        "ato_chain_risk_score": 85.0,
    }
    out7 = evaluate_rules(ctx7)
    assert out7.override_action == "block", f"Expected block, got {out7.override_action}"
    print("  ✓ R07 ATO chain active (high) → block")

    # Test 8: ATO chain active (medium score) → mfa
    ctx8 = {
        "ato_chain_active":    1,
        "ato_chain_risk_score": 65.0,
    }
    out8 = evaluate_rules(ctx8)
    assert out8.override_action == "mfa", f"Expected mfa, got {out8.override_action}"
    print("  ✓ R07 ATO chain active (medium) → mfa")

    # Test 9: New device + new IP → boost only
    ctx9 = {"is_new_device": 1, "is_new_ip": 1}
    out9 = evaluate_rules(ctx9)
    assert out9.total_boost >= 15.0
    print(f"  ✓ R09 New device+IP → boost={out9.total_boost:.0f}")

    # Test 10: Fraud ring → block
    ctx10 = {"graph_is_in_known_ring": 1, "graph_ring_risk_score": 90.0}
    out10 = evaluate_rules(ctx10)
    assert out10.override_action == "block"
    print("  ✓ R10 Fraud ring block")

    # Test 11: Clean transaction → no override, no boost
    ctx11 = {
        "merchant_id": "merch_amazon",
        "txn_count_last_1h": 2,
        "geo_distance_km": 0.0,
        "account_age_days": 365.0,
        "amount_to_user_mean_ratio": 1.0,
        "amount_usd": 50.0,
        "ato_chain_active": 0,
        "is_new_device": 0,
        "is_new_ip": 0,
    }
    out11 = evaluate_rules(ctx11)
    assert out11.override_action is None
    assert out11.total_boost == 0.0
    print("  ✓ Clean transaction → no rules triggered")

    # Test 12: list_rules metadata
    meta = list_rules()
    assert len(meta) == len(_ALL_RULES)
    print(f"  ✓ list_rules() → {len(meta)} rules registered")

    print("\n✅  S7 Self-Test PASSED — Rule Engine ready for S8 (FastAPI)\n")
