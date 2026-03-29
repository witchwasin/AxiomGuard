#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════
MARS ROVER AUTONOMOUS NAVIGATION — EDGE SAFETY SYSTEM
═══════════════════════════════════════════════════════════════════════════

Demonstrates AxiomGuard as a formal verification layer for an onboard
quantized LLM (e.g., Gemma-2B-Q4 on Jetson Orin) generating navigation
plans for a Martian rover.

The LLM generates a traverse plan. AxiomGuard intercepts the plan and
verifies it against NASA flight rules using Z3 theorem proving — entirely
offline, no cloud, no network, deterministic.

This demo shows 3 simultaneous constraint violations:
  1. Solar recharge timeout (14h since last charge, limit is 12h)
  2. Route through permanently shadowed region (prohibited)
  3. Terrain confidence too low (0.45, minimum is 0.85)

Requirements:
  pip install axiomguard==0.6.1

Usage:
  python3 rover_edge_system.py
═══════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from axiomguard import (
    Claim,
    KnowledgeBase,
    audit_extraction_bias,
    filter_low_confidence,
    score_claim_confidence,
    verify_structured,
)

# ═════════════════════════════════════════════════════════════════════
# MISSION CONSTANTS
# ═════════════════════════════════════════════════════════════════════

SOL_DURATION_S = 88775  # 1 Martian sol in seconds
MISSION_NAME = "ARES-7"
ROVER_ID = "MSL-PATHFINDER-04"
UPLINK_DELAY = "14m 22s"  # Earth-Mars light delay

# ═════════════════════════════════════════════════════════════════════
# SIMULATED ONBOARD LLM OUTPUT
# ═════════════════════════════════════════════════════════════════════
# This is what a quantized Gemma-2B model running on the rover's
# edge compute module would produce as a navigation plan.
# The LLM has hallucinated: it chose a shortcut through a crater
# (permanently shadowed region) to save time, ignoring physics.

LLM_NAV_PLAN = {
    "model": "gemma-2b-q4-mars-nav-v3",
    "sol": 847,
    "timestamp_utc": "2026-03-30T06:00:00+00:00",
    "task": "traverse_to_waypoint_delta_7",
    "plan": {
        "description": "Optimal route to Waypoint Delta-7 via Jezero South Crater shortcut",
        "estimated_distance_m": 2340,
        "estimated_duration_h": 4.2,
        "terrain_confidence": 0.45,
        "route_segments": [
            "ridge_alpha_east",
            "crater_rim_descent",
            "permanently_shadowed_region",  # <-- VIOLATION: PSR no-go zone
            "crater_floor_traverse",
            "ascent_to_delta_7",
        ],
        "battery_level_pct": 67,
        "time_since_last_charge_h": 14.0,  # <-- VIOLATION: >12h limit
    },
    "llm_reasoning": (
        "Taking the crater shortcut saves 1.8km vs the ridge route. "
        "Terrain appears stable based on orbital imagery. "  # <-- "appears" = hedge
        "Solar exposure along the route is probably sufficient."  # <-- "probably" = hedge
    ),
}


# ═════════════════════════════════════════════════════════════════════
# TERMINAL OUTPUT FORMATTING
# ═════════════════════════════════════════════════════════════════════

RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
DIM = "\033[2m"
BG_RED = "\033[41m"

SEP = f"{DIM}{'─' * 72}{RESET}"
SEP_HEAVY = f"{BOLD}{'═' * 72}{RESET}"


def log(level: str, msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
    colors = {
        "INFO": CYAN,
        "WARN": YELLOW,
        "CRIT": RED,
        "PASS": GREEN,
        "SYS": DIM,
    }
    c = colors.get(level, RESET)
    print(f"  {DIM}[{ts}]{RESET} {c}[{level}]{RESET} {msg}")


# ═════════════════════════════════════════════════════════════════════
# MAIN: ROVER SAFETY VERIFICATION PIPELINE
# ═════════════════════════════════════════════════════════════════════

def main() -> int:
    print()
    print(SEP_HEAVY)
    print(f"  {BOLD}AXIOMGUARD EDGE SAFETY SYSTEM{RESET}")
    print(f"  {DIM}Mars Rover Navigation Constraint Verification{RESET}")
    print(f"  {DIM}Mission: {MISSION_NAME}  |  Rover: {ROVER_ID}  |  Uplink delay: {UPLINK_DELAY}{RESET}")
    print(SEP_HEAVY)
    print()

    # ─── Phase 1: Load Flight Rules ─────────────────────────────────
    print(f"  {BOLD}PHASE 1: LOADING FLIGHT RULES{RESET}")
    print(SEP)

    rules_path = Path(__file__).parent / "rover_safety_policy.axiom.yml"
    kb = KnowledgeBase()
    ruleset = kb.load(rules_path)

    log("SYS", f"Loaded {kb.rule_count} flight rules from {rules_path.name}")
    for rule in ruleset.rules:
        log("SYS", f"  Rule: {rule.name} (type: {rule.type}, severity: {rule.severity})")
    print()

    # ─── Phase 2: Receive LLM Navigation Plan ──────────────────────
    print(f"  {BOLD}PHASE 2: RECEIVING LLM NAVIGATION PLAN{RESET}")
    print(SEP)

    plan = LLM_NAV_PLAN["plan"]
    log("INFO", f"Model: {LLM_NAV_PLAN['model']}")
    log("INFO", f"Sol: {LLM_NAV_PLAN['sol']}  |  Task: {LLM_NAV_PLAN['task']}")
    log("INFO", f"Route: {' -> '.join(plan['route_segments'])}")
    log("INFO", f"Distance: {plan['estimated_distance_m']}m  |  Duration: {plan['estimated_duration_h']}h")
    log("INFO", f"Battery: {plan['battery_level_pct']}%  |  Last charge: {plan['time_since_last_charge_h']}h ago")
    log("INFO", f"Terrain confidence: {plan['terrain_confidence']}")
    log("INFO", f"LLM reasoning: \"{LLM_NAV_PLAN['llm_reasoning'][:80]}...\"")
    print()

    # ─── Phase 3: Convert LLM Output to Structured Claims ──────────
    print(f"  {BOLD}PHASE 3: EXTRACTING STRUCTURED CLAIMS (NO LLM){RESET}")
    print(SEP)

    # System time: current time
    # Last charge time: 14 hours ago
    now_epoch = int(datetime.now(timezone.utc).timestamp())
    charge_hours_ago = plan["time_since_last_charge_h"]
    last_charge_epoch = now_epoch - int(charge_hours_ago * 3600)

    claims = [
        # Temporal: when was the last charge?
        Claim(
            subject="rover",
            relation="last_charge_time",
            object=str(last_charge_epoch),
        ),
        # Route segments — each one is a claim
        *[
            Claim(
                subject="rover",
                relation="planned_route",
                object=segment,
            )
            for segment in plan["route_segments"]
        ],
        # Terrain confidence (float)
        Claim(
            subject="rover",
            relation="terrain_confidence",
            object=str(plan["terrain_confidence"]),
        ),
        # Battery level
        Claim(
            subject="rover",
            relation="battery_level",
            object=str(plan["battery_level_pct"]),
        ),
    ]

    log("SYS", f"Extracted {len(claims)} structured claims from LLM output")
    for i, c in enumerate(claims):
        log("SYS", f"  [{i}] {c.subject}.{c.relation} = {c.object}")
    print()

    # ─── Phase 4: Confidence Scoring (Hedge Detection) ──────────────
    print(f"  {BOLD}PHASE 4: CONFIDENCE SCORING{RESET}")
    print(SEP)

    # Score the LLM's reasoning text as a meta-claim
    reasoning_claim = Claim(
        subject="llm_reasoning",
        relation="assessment",
        object=LLM_NAV_PLAN["llm_reasoning"],
    )
    scored = score_claim_confidence(reasoning_claim)

    if scored.confidence < 0.5:
        log("WARN", f"LLM reasoning confidence: {scored.confidence} (LOW)")
        log("WARN", f"Hedge words detected in: \"{scored.object[:60]}...\"")
    else:
        log("PASS", f"LLM reasoning confidence: {scored.confidence}")

    # Also check terrain confidence against our threshold
    terrain_conf = plan["terrain_confidence"]
    if terrain_conf < 0.85:
        log("WARN", f"Terrain confidence {terrain_conf} < 0.85 autonomous threshold")
    print()

    # ─── Phase 5: Extraction Bias Audit ─────────────────────────────
    print(f"  {BOLD}PHASE 5: EXTRACTION BIAS AUDIT{RESET}")
    print(SEP)

    bias_warnings = audit_extraction_bias(claims)
    if bias_warnings:
        for w in bias_warnings:
            log("WARN", f"Bias flag: {w}")
    else:
        log("PASS", "No protected attribute bias detected in claims")
    print()

    # ─── Phase 6: Z3 FORMAL VERIFICATION ────────────────────────────
    print(f"  {BOLD}PHASE 6: Z3 FORMAL VERIFICATION{RESET}")
    print(SEP)

    log("SYS", "Invoking Z3 SMT solver...")
    log("SYS", f"System time (epoch): {now_epoch}")
    log("SYS", f"Last charge (epoch): {last_charge_epoch} ({charge_hours_ago}h ago)")

    t0 = time.perf_counter()
    result = verify_structured(
        response_claims=claims,
        kb=kb,
        system_time=now_epoch,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000

    log("SYS", f"Z3 completed in {elapsed_ms:.1f}ms")
    print()

    # ─── Phase 7: VERDICT ───────────────────────────────────────────
    if result.is_hallucinating:
        print(f"  {BG_RED}{BOLD} EMERGENCY HALT — CONSTRAINTS VIOLATED {RESET}")
        print(SEP)
        print()
        log("CRIT", f"Z3 VERDICT: UNSAT (mathematical proof of violation)")
        log("CRIT", f"Confidence: {result.confidence}")
        log("CRIT", f"Contradicted claims: {result.contradicted_claims}")
        print()

        print(f"  {BOLD}{RED}VIOLATED FLIGHT RULES:{RESET}")
        print(SEP)
        for i, rule in enumerate(result.violated_rules, 1):
            severity = rule.get("severity", "error").upper()
            name = rule.get("name", "Unknown")
            message = rule.get("message", "").strip()
            print()
            print(f"  {RED}[{severity} #{i}] {name}{RESET}")
            for line in message.split("\n"):
                line = line.strip()
                if line:
                    print(f"    {line}")

        print()
        print(SEP)
        print(f"  {BOLD}{RED}ACTION: Navigation plan REJECTED.{RESET}")
        print(f"  {RED}Rover entering SAFE MODE. Awaiting Mission Control uplink.{RESET}")
        print(f"  {DIM}Uplink delay: {UPLINK_DELAY}  |  Next comm window: TBD{RESET}")
        print(SEP)
        print()

        # Escalation payload — what gets queued for uplink
        escalation = {
            "event": "NAVIGATION_PLAN_REJECTED",
            "mission": MISSION_NAME,
            "rover": ROVER_ID,
            "sol": LLM_NAV_PLAN["sol"],
            "violations": [
                {
                    "rule": r["name"],
                    "severity": r["severity"],
                    "message": r["message"].strip(),
                }
                for r in result.violated_rules
            ],
            "llm_model": LLM_NAV_PLAN["model"],
            "z3_result": "UNSAT",
            "z3_latency_ms": round(elapsed_ms, 1),
            "action": "SAFE_MODE",
        }

        print(f"  {BOLD}ESCALATION PAYLOAD (queued for uplink):{RESET}")
        print(SEP)
        print(json.dumps(escalation, indent=2, ensure_ascii=False))
        print()

        return 1  # Non-zero exit = blocked

    else:
        print(f"  {GREEN}{BOLD} ALL CONSTRAINTS SATISFIED {RESET}")
        print(SEP)
        log("PASS", "Z3 VERDICT: SAT (all flight rules satisfied)")
        log("PASS", "Navigation plan APPROVED for autonomous execution.")
        print()

        return 0


if __name__ == "__main__":
    sys.exit(main())
