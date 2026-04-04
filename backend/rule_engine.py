"""
============================================================
NeuralNexus — Stage S7: Rule Engine  (v2.0 — Enhanced)
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

v2.0 Changes (Mentor Feedback):
  - Added 8 new rules (R11–R18) for more granular fraud coverage
  - Improved R02 with 4-tier velocity thresholds
  - Improved R03 with "suspicious but plausible" travel tier
  - Improved R05/R08 with INR-adjusted thresholds
  - All monetary thresholds documented with reasoning

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
# INR THRESHOLDS  (India-specific UPI context)
# ─────────────────────────────────────────────
# RBI reporting threshold: ₹10,00,000 (10 lakh) for cash
# UPI per-transaction limit: ₹1,00,000 (1 lakh)
# Structuring threshold: just under ₹10,000 (common layering level)
# High-value UPI: > ₹50,000

INR_STRUCTURING_LOW  = 9_000.0   # ₹9,000 — lower bound for structuring band
INR_STRUCTURING_HIGH = 9_999.0   # ₹9,999 — upper bound (just under ₹10K)
INR_HIGH_VALUE       = 50_000.0  # ₹50,000 — high-value transaction
INR_SUSPICIOUS_LARGE = 5_000.0   # ₹5,000 — suspicious for new accounts
INR_ROUND_THRESHOLD  = 5_000.0   # ₹5,000 — round amount alert threshold
INR_MICRO_DEPOSIT    = 100.0     # ₹100 — micro-deposit probing ceiling

USD_TO_INR = 90.0  # Standard conversion factor


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

# ════════════════════════════════════════════════
#  R01: BLACKLISTED MERCHANT  (instant block)
# ════════════════════════════════════════════════

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


# ════════════════════════════════════════════════
#  R02: VELOCITY BURST  (4-tier, improved)
#  Tiers: >3/hr low, >5/hr medium, >10/hr mfa, >20/hr block
# ════════════════════════════════════════════════

def rule_velocity_burst(ctx: dict) -> RuleResult:
    """
    4-tier velocity detection based on transactions in the last hour.
    >20/hr → BLOCK (automated attack), >10 → MFA, >5 → high boost, >3 → low boost.
    """
    count_1h = int(ctx.get("txn_count_last_1h", 0))

    if count_1h > 20:
        return RuleResult(
            rule_id="R02_VELOCITY_EXTREME_BLOCK",
            triggered=True,
            action="block",
            score_boost=40.0,
            reason=f"Extreme velocity: {count_1h} txns in last hour (>20) — automated attack pattern",
            severity="critical",
        )
    elif count_1h > 10:
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
    elif count_1h > 3:
        return RuleResult(
            rule_id="R02_VELOCITY_ELEVATED",
            triggered=True,
            action=None,
            score_boost=8.0,
            reason=f"Elevated velocity: {count_1h} txns in last hour (>3)",
            severity="low",
        )
    return RuleResult(
        rule_id="R02_VELOCITY",
        triggered=False,
        action=None,
        score_boost=0.0,
        reason="",
        severity="low",
    )


# ════════════════════════════════════════════════
#  R03: IMPOSSIBLE TRAVEL  (2-tier, improved)
#  >900 km/h → MFA, 500–900 km/h → suspicious boost
# ════════════════════════════════════════════════

def rule_impossible_travel(ctx: dict) -> RuleResult:
    """
    2-tier geographic anomaly detection.
    >900 km/h (faster than aircraft) → MFA override.
    500–900 km/h (suspicious but plausible with bad geo data) → score boost.
    """
    geo_km   = float(ctx.get("geo_distance_km",    0.0))
    inter_s  = float(ctx.get("inter_txn_seconds",  9999.0))

    if inter_s <= 0 or geo_km <= 0:
        return RuleResult("R03_IMPOSSIBLE_TRAVEL", False, None, 0.0, "", "low")

    speed_kmh = (geo_km / inter_s) * 3600.0

    if speed_kmh > 900.0:
        return RuleResult(
            rule_id="R03_IMPOSSIBLE_TRAVEL",
            triggered=True,
            action="mfa",
            score_boost=30.0,
            reason=(
                f"Impossible travel: {geo_km:.0f}km in "
                f"{inter_s:.0f}s ({speed_kmh:.0f}km/h) — faster than aircraft"
            ),
            severity="high",
        )
    elif speed_kmh > 500.0:
        return RuleResult(
            rule_id="R03_SUSPICIOUS_TRAVEL",
            triggered=True,
            action=None,
            score_boost=10.0,
            reason=(
                f"Suspicious travel speed: {geo_km:.0f}km in "
                f"{inter_s:.0f}s ({speed_kmh:.0f}km/h) — unusually fast"
            ),
            severity="medium",
        )
    return RuleResult("R03_IMPOSSIBLE_TRAVEL", False, None, 0.0, "", "low")





# ════════════════════════════════════════════════
#  R05: NEW ACCOUNT + HIGH AMOUNT  (INR-adjusted)
#  Lowered threshold: ₹5,000 instead of $1,000
# ════════════════════════════════════════════════

def rule_new_account_high_amount(ctx: dict) -> RuleResult:
    """
    New accounts (<30 days old) sending large amounts are high risk.
    Thresholds: amount > 5× user mean AND account < 30 days AND amount > ₹5,000.
    INR-adjusted from original $1,000 to ₹5,000 for Indian UPI context.
    """
    age_days   = float(ctx.get("account_age_days",          30.0))
    ratio      = float(ctx.get("amount_to_user_mean_ratio",  1.0))
    amount_usd = float(ctx.get("amount_usd",                 0.0))
    amount_inr = amount_usd * USD_TO_INR

    triggered = age_days < 30 and ratio > 5.0 and amount_inr > INR_SUSPICIOUS_LARGE
    return RuleResult(
        rule_id="R05_NEW_ACCOUNT_HIGH_AMOUNT",
        triggered=triggered,
        action="mfa" if triggered else None,
        score_boost=20.0 if triggered else 0.0,
        reason=(
            f"New account ({age_days:.0f}d) sending "
            f"{ratio:.1f}× their usual amount (₹{amount_inr:,.0f})"
        ) if triggered else "",
        severity="high" if triggered else "low",
    )


# ════════════════════════════════════════════════
#  R06: HIGH-RISK MERCHANT CATEGORY  (unchanged)
# ════════════════════════════════════════════════

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


# ════════════════════════════════════════════════
#  R07: ATO CHAIN ACTIVE  (unchanged)
# ════════════════════════════════════════════════

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


# ════════════════════════════════════════════════
#  R08: ROUND LARGE AMOUNT  (INR-adjusted)
#  Lowered threshold from $10,000 to ₹5,000
# ════════════════════════════════════════════════

def rule_amount_round_large(ctx: dict) -> RuleResult:
    """
    Round amounts above ₹5,000 are a common fraud pattern (structuring/layering).
    INR-adjusted: ₹5,000 threshold for Indian UPI context (was $10,000).
    """
    amount_usd   = float(ctx.get("amount_usd", 0.0))
    amount_inr   = amount_usd * USD_TO_INR
    is_round     = bool(ctx.get("is_round_amount", False))

    # Also detect amounts that are round in thousands (INR)
    if not is_round and amount_inr > 0:
        is_round = amount_inr % 1000.0 == 0.0

    triggered    = is_round and amount_inr >= INR_ROUND_THRESHOLD

    return RuleResult(
        rule_id="R08_ROUND_LARGE_AMOUNT",
        triggered=triggered,
        action=None,
        score_boost=10.0 if triggered else 0.0,
        reason=f"Round amount ≥ ₹5,000 (₹{amount_inr:,.0f}) — structuring pattern",
        severity="medium" if triggered else "low",
    )


# ════════════════════════════════════════════════
#  R09: NEW DEVICE + NEW IP COMBINED  (unchanged)
# ════════════════════════════════════════════════

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


# ════════════════════════════════════════════════
#  R10: KNOWN FRAUD RING  (unchanged)
# ════════════════════════════════════════════════

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


# ════════════════════════════════════════════════
#  R11: UNUSUAL HOUR + HIGH AMOUNT  (NEW)
#  Late-night (midnight–5am) + high amount = classic fraud
# ════════════════════════════════════════════════

def rule_unusual_hour_high_amount(ctx: dict) -> RuleResult:
    """
    Late-night transactions (midnight–5am) with amount > 3× user mean.
    Fraudsters prefer late-night hours when victims are asleep and
    less likely to notice unauthorized transactions immediately.
    """
    hour       = int(ctx.get("hour_of_day", 12))
    ratio      = float(ctx.get("amount_to_user_mean_ratio", 1.0))
    amount_usd = float(ctx.get("amount_usd", 0.0))
    amount_inr = amount_usd * USD_TO_INR

    is_late_night = 0 <= hour <= 5
    is_high_ratio = ratio > 3.0
    is_significant = amount_inr > 2_000.0  # ₹2,000 minimum to avoid false positives

    triggered = is_late_night and is_high_ratio and is_significant

    return RuleResult(
        rule_id="R11_UNUSUAL_HOUR_HIGH_AMOUNT",
        triggered=triggered,
        action=None,
        score_boost=15.0 if triggered else 0.0,
        reason=(
            f"Late-night ({hour}:00) transaction at {ratio:.1f}× usual amount "
            f"(₹{amount_inr:,.0f}) — classic fraud timing pattern"
        ) if triggered else "",
        severity="high" if triggered else "low",
    )


# ════════════════════════════════════════════════
#  R12: DAILY VELOCITY BURST  (NEW)
#  >15 transactions in 24h → MFA
# ════════════════════════════════════════════════

def rule_daily_velocity_burst(ctx: dict) -> RuleResult:
    """
    Elevated daily transaction count (>15 in 24h) indicates potential
    automated fraud or account compromise. Normal users rarely exceed
    10–12 UPI transactions per day.
    """
    count_24h = int(ctx.get("txn_count_last_24h", 0))

    if count_24h > 25:
        return RuleResult(
            rule_id="R12_DAILY_VELOCITY_BLOCK",
            triggered=True,
            action="mfa",
            score_boost=20.0,
            reason=f"Extreme daily velocity: {count_24h} txns in last 24h (>25) — likely automated",
            severity="high",
        )
    elif count_24h > 15:
        return RuleResult(
            rule_id="R12_DAILY_VELOCITY_HIGH",
            triggered=True,
            action=None,
            score_boost=12.0,
            reason=f"High daily velocity: {count_24h} txns in last 24h (>15)",
            severity="medium",
        )
    return RuleResult("R12_DAILY_VELOCITY", False, None, 0.0, "", "low")


# ════════════════════════════════════════════════
#  R13: WEEKLY SPEND SPIKE  (NEW)
#  Total 7d spend > 10× weekly average → suspicious
# ════════════════════════════════════════════════

def rule_weekly_spend_spike(ctx: dict) -> RuleResult:
    """
    When a user's current transaction pushes their weekly spending far
    above their historical average, it signals compromised credentials.
    Trigger: current txn amount > 10× the user's mean AND >20 txns in 7d.
    """
    count_7d    = int(ctx.get("txn_count_last_7d", 0))
    ratio       = float(ctx.get("amount_to_user_mean_ratio", 1.0))
    amount_usd  = float(ctx.get("amount_usd", 0.0))
    amount_inr  = amount_usd * USD_TO_INR

    triggered = count_7d > 20 and ratio > 10.0 and amount_inr > 10_000.0

    return RuleResult(
        rule_id="R13_WEEKLY_SPEND_SPIKE",
        triggered=triggered,
        action="mfa" if triggered else None,
        score_boost=18.0 if triggered else 0.0,
        reason=(
            f"Weekly spend spike: {count_7d} txns in 7d with current txn "
            f"at {ratio:.1f}× usual (₹{amount_inr:,.0f})"
        ) if triggered else "",
        severity="high" if triggered else "low",
    )


# ════════════════════════════════════════════════
#  R14: STRUCTURING PATTERN  (NEW)
#  ≥3 transactions in 2h, each ₹9,000–₹9,999
#  (just under ₹10K reporting/alert threshold)
# ════════════════════════════════════════════════

def rule_structuring_pattern(ctx: dict) -> RuleResult:
    """
    Detects "structuring" — splitting a large transaction into smaller
    amounts just below ₹10,000 to avoid automated alerts.
    Trigger: current amount is in ₹9,000–₹9,999 range AND velocity is
    elevated (>2 txns/hr suggests multiple such transactions).

    Note: In production, this would check a sliding window of recent
    amounts, not just the current one. The velocity check is a proxy.
    """
    amount_usd = float(ctx.get("amount_usd", 0.0))
    amount_inr = amount_usd * USD_TO_INR
    count_1h   = int(ctx.get("txn_count_last_1h", 0))

    in_band   = INR_STRUCTURING_LOW <= amount_inr <= INR_STRUCTURING_HIGH
    triggered = in_band and count_1h >= 2  # current + at least 2 more in the hour

    return RuleResult(
        rule_id="R14_STRUCTURING_PATTERN",
        triggered=triggered,
        action="mfa" if triggered else None,
        score_boost=22.0 if triggered else 0.0,
        reason=(
            f"Structuring detected: ₹{amount_inr:,.0f} in ₹9K–₹10K band "
            f"with {count_1h} txns in last hour — splitting to avoid alerts"
        ) if triggered else "",
        severity="high" if triggered else "low",
    )





# ════════════════════════════════════════════════
#  R16: COUNTRY MISMATCH  (NEW)
#  IP geolocation country differs from user's home + high amount
# ════════════════════════════════════════════════

def rule_country_mismatch(ctx: dict) -> RuleResult:
    """
    Transaction originates from a different country than user's
    registered/usual location AND involves a significant amount.
    In UPI context, cross-border transactions are unusual and need scrutiny.
    """
    cc_changed = int(ctx.get("ip_country_code_changed", 0))
    amount_usd = float(ctx.get("amount_usd", 0.0))
    amount_inr = amount_usd * USD_TO_INR
    new_ip     = int(ctx.get("is_new_ip", 0))

    triggered = bool(cc_changed) and amount_inr > INR_SUSPICIOUS_LARGE and bool(new_ip)

    return RuleResult(
        rule_id="R16_COUNTRY_MISMATCH",
        triggered=triggered,
        action="mfa" if triggered else None,
        score_boost=18.0 if triggered else 0.0,
        reason=(
            f"Country mismatch: transaction from foreign IP with new IP "
            f"for ₹{amount_inr:,.0f} — unusual for domestic UPI user"
        ) if triggered else "",
        severity="high" if triggered else "low",
    )


# ════════════════════════════════════════════════
#  R17: DORMANT ACCOUNT REACTIVATION  (NEW)
#  Account inactive >60 days, now high-value transaction
# ════════════════════════════════════════════════

def rule_dormant_account_reactivation(ctx: dict) -> RuleResult:
    """
    Accounts that have been inactive for >60 days suddenly performing
    high-value transactions are a strong signal of credential theft.
    The legitimate user may have abandoned the account, but a fraudster
    who bought credentials from the dark web reactivates it.
    """
    inter_sec   = float(ctx.get("inter_txn_seconds", 0.0))
    amount_usd  = float(ctx.get("amount_usd", 0.0))
    amount_inr  = amount_usd * USD_TO_INR

    days_since_last = inter_sec / 86_400.0
    triggered = days_since_last > 60.0 and amount_inr > 10_000.0  # ₹10,000+

    return RuleResult(
        rule_id="R17_DORMANT_REACTIVATION",
        triggered=triggered,
        action="mfa" if triggered else None,
        score_boost=18.0 if triggered else 0.0,
        reason=(
            f"Dormant account reactivation: {days_since_last:.0f} days inactive, "
            f"now ₹{amount_inr:,.0f} transaction — credential theft pattern"
        ) if triggered else "",
        severity="high" if triggered else "low",
    )


# ════════════════════════════════════════════════
#  R18: MICRO-DEPOSIT PROBING  (NEW)
#  ≥5 transactions under ₹100 in 1h (testing stolen card/UPI)
# ════════════════════════════════════════════════

def rule_micro_deposit_probing(ctx: dict) -> RuleResult:
    """
    Fraudsters often test stolen UPI credentials or card details by making
    multiple tiny transactions (₹1–₹100) to verify the account is active
    before attempting a large withdrawal.
    Trigger: amount ≤ ₹100 AND ≥5 txns in the last hour.
    """
    amount_usd = float(ctx.get("amount_usd", 0.0))
    amount_inr = amount_usd * USD_TO_INR
    count_1h   = int(ctx.get("txn_count_last_1h", 0))

    triggered = amount_inr <= INR_MICRO_DEPOSIT and count_1h >= 5

    return RuleResult(
        rule_id="R18_MICRO_DEPOSIT_PROBE",
        triggered=triggered,
        action=None,
        score_boost=12.0 if triggered else 0.0,
        reason=(
            f"Micro-deposit probing: ₹{amount_inr:.0f} with {count_1h} txns "
            f"in last hour — testing stolen credentials pattern"
        ) if triggered else "",
        severity="medium" if triggered else "low",
    )


# ─────────────────────────────────────────────
# RULE REGISTRY
# Priority order: first override wins.
# ─────────────────────────────────────────────

_ALL_RULES = [
    # ── Critical overrides (block/mfa) ────────
    rule_blacklisted_merchant,       # R01 — instant block
    rule_known_fraud_graph_ring,     # R10 — instant block/mfa
    rule_ato_chain_active,           # R07 — elevate on ATO
    rule_impossible_travel,          # R03 — elevate on travel anomaly
    rule_velocity_burst,             # R02 — velocity spike (4-tier)
    rule_structuring_pattern,        # R14 — structuring detection
    rule_country_mismatch,           # R16 — foreign IP + high amount
    rule_dormant_account_reactivation,  # R17 — dormant + high value
    rule_weekly_spend_spike,         # R13 — weekly spending anomaly
    rule_daily_velocity_burst,       # R12 — daily velocity
    # ── High-severity boosts ──────────────────
    rule_new_account_high_amount,    # R05 — new account large txn
    rule_new_device_new_ip_combined, # R09 — device + IP double-new
    rule_unusual_hour_high_amount,   # R11 — late night + high amount
    # ── Medium-severity boosts ────────────────
    rule_high_risk_merchant_category,# R06 — MCC boost
    rule_amount_round_large,         # R08 — structuring pattern
    rule_micro_deposit_probing,      # R18 — card testing pattern
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
    print("\n[S7] Rule Engine Self-Test (v2.0 — 18 Rules)\n")

    # Test 1: Blacklisted merchant → block
    ctx1 = {"merchant_id": "merch_blacklisted_1"}
    out1 = evaluate_rules(ctx1)
    assert out1.override_action == "block", f"Expected block, got {out1.override_action}"
    assert out1.override_rule_id == "R01_BLACKLISTED_MERCHANT"
    print("  ✓ R01 Blacklisted merchant → block")

    # Test 2a: Velocity >20/hr → block
    ctx2a = {"txn_count_last_1h": 22}
    out2a = evaluate_rules(ctx2a)
    assert out2a.override_action == "block", f"Expected block, got {out2a.override_action}"
    print("  ✓ R02 Velocity extreme (>20) → block")

    # Test 2b: Velocity >10/hr → mfa
    ctx2b = {"txn_count_last_1h": 12}
    out2b = evaluate_rules(ctx2b)
    assert out2b.override_action == "mfa", f"Expected mfa, got {out2b.override_action}"
    print("  ✓ R02 Velocity high (>10) → mfa")

    # Test 2c: Velocity >5/hr → boost only
    ctx2c = {"txn_count_last_1h": 6}
    out2c = evaluate_rules(ctx2c)
    assert out2c.override_action is None
    assert out2c.total_boost >= 15.0, f"Expected boost >= 15, got {out2c.total_boost}"
    print(f"  ✓ R02 Velocity medium (>5) → no override, boost={out2c.total_boost:.0f}")

    # Test 2d: Velocity >3/hr → low boost
    ctx2d = {"txn_count_last_1h": 4}
    out2d = evaluate_rules(ctx2d)
    assert out2d.total_boost >= 8.0
    print(f"  ✓ R02 Velocity elevated (>3) → boost={out2d.total_boost:.0f}")

    # Test 3a: Impossible travel (>900 km/h) → mfa
    ctx3a = {
        "geo_distance_km":   1500.0,
        "inter_txn_seconds": 600.0,    # 10 minutes → 9000 km/h
    }
    out3a = evaluate_rules(ctx3a)
    assert out3a.override_action == "mfa", f"Expected mfa, got {out3a.override_action}"
    print("  ✓ R03 Impossible travel (>900 km/h) → mfa")

    # Test 3b: Suspicious travel (500–900 km/h) → boost only
    ctx3b = {
        "geo_distance_km":   500.0,
        "inter_txn_seconds": 1200.0,   # 20 minutes → 1500 km/h → no, 500/1200*3600 = 1500
    }
    # Need to recalculate: 500km / 1200s * 3600 = 1500 km/h → that's >900
    # Let's use: 200km in 600s → 1200 km/h → still >900
    # For 500-900: 300km in 1800s → 600 km/h ✓
    ctx3b = {
        "geo_distance_km":   300.0,
        "inter_txn_seconds": 1800.0,   # 30 minutes → 600 km/h
    }
    out3b = evaluate_rules(ctx3b)
    assert out3b.override_action is None
    assert out3b.total_boost >= 10.0
    print(f"  ✓ R03 Suspicious travel (500–900 km/h) → boost={out3b.total_boost:.0f}")

    # Test 4: TOR IP → score boost
    ctx4 = {"ip_address": "185.220.10.1"}
    out4 = evaluate_rules(ctx4)
    assert out4.total_boost >= 20.0
    print(f"  ✓ R04 TOR IP → boost={out4.total_boost:.0f}")

    # Test 5: New account + high amount → mfa (INR-adjusted)
    ctx5 = {
        "account_age_days":          10.0,
        "amount_to_user_mean_ratio": 8.0,
        "amount_usd":                8000.0,  # ₹8,000
    }
    out5 = evaluate_rules(ctx5)
    assert out5.override_action == "mfa", f"Expected mfa, got {out5.override_action}"
    print("  ✓ R05 New account high amount (₹8,000) → mfa")

    # Test 6: High-risk MCC
    ctx6 = {"merchant_category_encoded": 6051}
    out6 = evaluate_rules(ctx6)
    assert out6.total_boost >= 10.0
    print(f"  ✓ R06 High-risk MCC → boost={out6.total_boost:.0f}")

    # Test 7a: ATO chain active (high score) → block
    ctx7a = {"ato_chain_active": 1, "ato_chain_risk_score": 85.0}
    out7a = evaluate_rules(ctx7a)
    assert out7a.override_action == "block"
    print("  ✓ R07 ATO chain active (high) → block")

    # Test 7b: ATO chain active (medium) → mfa
    ctx7b = {"ato_chain_active": 1, "ato_chain_risk_score": 65.0}
    out7b = evaluate_rules(ctx7b)
    assert out7b.override_action == "mfa"
    print("  ✓ R07 ATO chain active (medium) → mfa")

    # Test 8: Round large amount (INR-adjusted)
    ctx8 = {"amount_usd": 10000.0, "is_round_amount": True}
    out8 = evaluate_rules(ctx8)
    assert out8.total_boost >= 10.0
    print(f"  ✓ R08 Round amount ₹10,000 → boost={out8.total_boost:.0f}")

    # Test 9: New device + new IP
    ctx9 = {"is_new_device": 1, "is_new_ip": 1}
    out9 = evaluate_rules(ctx9)
    assert out9.total_boost >= 15.0
    print(f"  ✓ R09 New device+IP → boost={out9.total_boost:.0f}")

    # Test 10: Fraud ring → block
    ctx10 = {"graph_is_in_known_ring": 1, "graph_ring_risk_score": 90.0}
    out10 = evaluate_rules(ctx10)
    assert out10.override_action == "block"
    print("  ✓ R10 Fraud ring → block")

    # Test 11: Unusual hour + high amount (NEW)
    ctx11 = {
        "hour_of_day": 3,
        "amount_to_user_mean_ratio": 5.0,
        "amount_usd": 15000.0,
    }
    out11 = evaluate_rules(ctx11)
    assert out11.total_boost >= 15.0
    # Check that R11 specifically fired
    r11_triggered = any(r.rule_id == "R11_UNUSUAL_HOUR_HIGH_AMOUNT" for r in out11.triggered_rules)
    assert r11_triggered, "R11 should have triggered"
    print(f"  ✓ R11 Unusual hour + high amount (3am, ₹15K) → boost includes +15")

    # Test 12: Daily velocity burst (NEW)
    ctx12 = {"txn_count_last_24h": 18}
    out12 = evaluate_rules(ctx12)
    r12_triggered = any(r.rule_id == "R12_DAILY_VELOCITY_HIGH" for r in out12.triggered_rules)
    assert r12_triggered, "R12 should have triggered"
    print(f"  ✓ R12 Daily velocity (18 txns/24h) → boost includes +12")

    # Test 13: Weekly spend spike (NEW)
    ctx13 = {
        "txn_count_last_7d": 25,
        "amount_to_user_mean_ratio": 12.0,
        "amount_usd": 50000.0,
    }
    out13 = evaluate_rules(ctx13)
    r13_triggered = any(r.rule_id == "R13_WEEKLY_SPEND_SPIKE" for r in out13.triggered_rules)
    assert r13_triggered, "R13 should have triggered"
    print("  ✓ R13 Weekly spend spike → mfa")

    # Test 14: Structuring pattern (NEW)
    ctx14 = {"amount_usd": 9500.0, "txn_count_last_1h": 3}
    out14 = evaluate_rules(ctx14)
    r14_triggered = any(r.rule_id == "R14_STRUCTURING_PATTERN" for r in out14.triggered_rules)
    assert r14_triggered, "R14 should have triggered"
    print("  ✓ R14 Structuring (₹9,500, 3 txns/hr) → mfa")

    # Test 15: Rapid beneficiary repeat (NEW)
    ctx15 = {"txn_count_last_1h": 5, "amount_usd": 8000.0}
    out15 = evaluate_rules(ctx15)
    r15_triggered = any(r.rule_id == "R15_RAPID_BENEFICIARY_REPEAT" for r in out15.triggered_rules)
    assert r15_triggered, "R15 should have triggered"
    print(f"  ✓ R15 Rapid beneficiary repeat → boost")

    # Test 16: Country mismatch (NEW)
    ctx16 = {
        "ip_country_code_changed": 1,
        "is_new_ip": 1,
        "amount_usd": 20000.0,
    }
    out16 = evaluate_rules(ctx16)
    r16_triggered = any(r.rule_id == "R16_COUNTRY_MISMATCH" for r in out16.triggered_rules)
    assert r16_triggered, "R16 should have triggered"
    print("  ✓ R16 Country mismatch → mfa")

    # Test 17: Dormant account reactivation (NEW)
    ctx17 = {
        "inter_txn_seconds": 90.0 * 86400,  # 90 days inactive
        "amount_usd": 50000.0,
    }
    out17 = evaluate_rules(ctx17)
    r17_triggered = any(r.rule_id == "R17_DORMANT_REACTIVATION" for r in out17.triggered_rules)
    assert r17_triggered, "R17 should have triggered"
    print("  ✓ R17 Dormant account reactivation (90d + ₹50K) → mfa")

    # Test 18: Micro-deposit probing (NEW)
    ctx18 = {"amount_usd": 10.0, "txn_count_last_1h": 6}
    out18 = evaluate_rules(ctx18)
    r18_triggered = any(r.rule_id == "R18_MICRO_DEPOSIT_PROBE" for r in out18.triggered_rules)
    assert r18_triggered, "R18 should have triggered"
    print(f"  ✓ R18 Micro-deposit probing (₹10, 6 txns/hr) → boost")

    # Test 19: Clean transaction → no override, no boost
    ctx19 = {
        "merchant_id": "merch_amazon",
        "txn_count_last_1h": 2,
        "txn_count_last_24h": 5,
        "txn_count_last_7d": 10,
        "geo_distance_km": 0.0,
        "account_age_days": 365.0,
        "amount_to_user_mean_ratio": 1.0,
        "amount_usd": 500.0,
        "ato_chain_active": 0,
        "is_new_device": 0,
        "is_new_ip": 0,
        "hour_of_day": 14,
        "inter_txn_seconds": 3600.0,
        "ip_country_code_changed": 0,
    }
    out19 = evaluate_rules(ctx19)
    assert out19.override_action is None
    assert out19.total_boost == 0.0
    print("  ✓ Clean transaction → no rules triggered")

    # Test 20: list_rules metadata
    meta = list_rules()
    assert len(meta) == len(_ALL_RULES)
    print(f"  ✓ list_rules() → {len(meta)} rules registered")

    print(f"\n✅  S7 Self-Test PASSED — {len(_ALL_RULES)} Rules (v2.0 Enhanced)\n")
