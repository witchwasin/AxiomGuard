#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════
ELECTRONIC HEALTH RECORD — AI MEDICATION SAFETY SYSTEM
═══════════════════════════════════════════════════════════════════════════

Demonstrates AxiomGuard as a formal verification layer for an AI Nursing
Assistant that recommends medication administration.

Problem (James's observation):
  "LLMs don't have an internal clock. They might hallucinate the time
   and administer medication too early or skip it entirely, which can
   be fatal."

Solution:
  Z3 theorem prover handles ALL temporal calculations mathematically.
  The LLM never estimates elapsed time. AxiomGuard computes:
    system_time - last_dose_time >= 14400 (4 hours in seconds)
  This is a mathematical proof, not a probability.

Scenario:
  AI recommends 5mg Morphine for pain management. However:
  1. Last dose was only 2 hours ago (minimum interval: 4 hours)
  2. AI confidence in reading physician handwriting: 0.80 (threshold: 0.95)
  3. Vitals were checked 45 minutes ago (threshold: 30 minutes)

All 3 violations are caught by Z3 — deterministic, offline, provable.

Requirements:
  pip install axiomguard==0.6.2

Usage:
  python3 ehr_medication_system.py
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
# HOSPITAL CONFIGURATION
# ═════════════════════════════════════════════════════════════════════

HOSPITAL_NAME = "Bangkok Metropolitan Medical Center"
WARD = "ICU-3 (Cardiac)"
SYSTEM_ID = "AxiomGuard-EHR-v0.6.2"

# ═════════════════════════════════════════════════════════════════════
# SIMULATED AI NURSING ASSISTANT OUTPUT
# ═════════════════════════════════════════════════════════════════════
# The AI assistant analyzed the patient chart and recommends Morphine.
# However, it lacks temporal awareness and doesn't realize the last
# dose was only 2 hours ago.

PATIENT = {
    "mrn": "MRN-2026-044817",
    "name": "Somchai K.",
    "age": 58,
    "weight_kg": 72,
    "ward": WARD,
    "primary_dx": "Acute MI (STEMI), post-PCI Day 2",
    "allergies": ["Penicillin"],
    "active_medications": ["Aspirin", "Clopidogrel", "Atorvastatin", "Heparin"],
}

AI_RECOMMENDATION = {
    "model": "medgemma-2b-q4-ehr-v2",
    "timestamp_utc": "2026-03-30T08:00:00+00:00",
    "recommendation": {
        "action": "administer_medication",
        "medication": "Morphine Sulfate",
        "dosage_mg": 5.0,
        "route": "IV Push",
        "indication": "Chest pain management, pain score 7/10",
        "ocr_confidence": 0.80,  # <-- LOW: read from handwritten order
        "patient_pain_score": 7,
        "last_dose_hours_ago": 2.0,   # <-- VIOLATION: only 2h, minimum 4h
        "last_vitals_minutes_ago": 45, # <-- VIOLATION: 45min, max 30min
    },
    "ai_reasoning": (
        "Patient reports pain score 7/10 consistent with post-PCI discomfort. "
        "Morphine 5mg IV appears appropriate based on the physician's order. "
        "The handwriting on the order form is somewhat unclear but probably "
        "reads '5mg'. Previous dose was given earlier today."
    ),
}


# ═════════════════════════════════════════════════════════════════════
# TERMINAL OUTPUT — HOSPITAL EHR STYLE
# ═════════════════════════════════════════════════════════════════════

RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
WHITE = "\033[97m"
DIM = "\033[2m"
BG_RED = "\033[41m"
BG_GREEN = "\033[42m"
BG_YELLOW = "\033[43m"
BG_BLUE = "\033[44m"

THIN = f"{DIM}{'.' * 68}{RESET}"
LINE = f"{DIM}{'─' * 68}{RESET}"
DLINE = f"{BOLD}{'═' * 68}{RESET}"


def ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def header(title: str, bg: str = BG_BLUE) -> None:
    padded = f" {title} "
    print(f"\n  {bg}{BOLD}{WHITE}{padded}{RESET}")
    print(f"  {LINE}")


def field(label: str, value: str, warn: bool = False) -> None:
    color = YELLOW if warn else RESET
    print(f"  {DIM}{label + ':':<28}{RESET}{color}{value}{RESET}")


def status(icon: str, msg: str) -> None:
    print(f"  {icon}  {msg}")


# ═════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════

def main() -> int:
    print()
    print(f"  {DLINE}")
    print(f"  {BG_BLUE}{BOLD}{WHITE} {HOSPITAL_NAME} {RESET}")
    print(f"  {DIM}Electronic Health Record — Medication Safety Module{RESET}")
    print(f"  {DIM}System: {SYSTEM_ID}  |  Ward: {WARD}  |  {ts()} UTC{RESET}")
    print(f"  {DLINE}")

    # ─── Patient Banner ─────────────────────────────────────────────
    header("PATIENT IDENTIFICATION", BG_BLUE)
    field("MRN", PATIENT["mrn"])
    field("Name", PATIENT["name"])
    field("Age/Weight", f"{PATIENT['age']}y / {PATIENT['weight_kg']}kg")
    field("Ward", PATIENT["ward"])
    field("Primary Dx", PATIENT["primary_dx"])
    field("Allergies", ", ".join(PATIENT["allergies"]))
    field("Active Meds", ", ".join(PATIENT["active_medications"]))

    # ─── AI Recommendation ──────────────────────────────────────────
    rec = AI_RECOMMENDATION["recommendation"]
    header("AI NURSING ASSISTANT RECOMMENDATION", BG_BLUE)
    field("Model", AI_RECOMMENDATION["model"])
    field("Medication", f"{rec['medication']} {rec['dosage_mg']}mg {rec['route']}")
    field("Indication", rec["indication"])
    field("Pain Score", f"{rec['patient_pain_score']}/10")
    field("Last Dose", f"{rec['last_dose_hours_ago']} hours ago", warn=True)
    field("Last Vitals", f"{rec['last_vitals_minutes_ago']} minutes ago", warn=True)
    field("OCR Confidence", f"{rec['ocr_confidence']}", warn=True)
    print(f"  {DIM}AI Reasoning: \"{AI_RECOMMENDATION['ai_reasoning'][:70]}...\"{RESET}")

    # ─── Load Safety Rules ──────────────────────────────────────────
    header("SAFETY RULES ENGINE", BG_BLUE)
    rules_path = Path(__file__).parent / "ehr_medication_policy.axiom.yml"
    kb = KnowledgeBase()
    ruleset = kb.load(rules_path)
    print(f"  {DIM}Loaded {kb.rule_count} medication safety rules{RESET}")
    for rule in ruleset.rules:
        print(f"  {DIM}  [{rule.severity.upper()}] {rule.name}{RESET}")

    # ─── Confidence Scoring ─────────────────────────────────────────
    header("PRE-FLIGHT: CONFIDENCE CHECK", BG_YELLOW)

    reasoning_claim = Claim(
        subject="ai_reasoning",
        relation="assessment",
        object=AI_RECOMMENDATION["ai_reasoning"],
    )
    scored = score_claim_confidence(reasoning_claim)
    if scored.confidence < 0.5:
        status(f"{YELLOW}!{RESET}", f"AI reasoning confidence: {BOLD}{scored.confidence}{RESET} {YELLOW}(hedge words detected){RESET}")
    else:
        status(f"{GREEN}*{RESET}", f"AI reasoning confidence: {scored.confidence}")

    if rec["ocr_confidence"] < 0.95:
        status(f"{RED}!{RESET}", f"OCR confidence: {BOLD}{rec['ocr_confidence']}{RESET} {RED}(below 0.95 threshold for controlled substances){RESET}")
    else:
        status(f"{GREEN}*{RESET}", f"OCR confidence: {rec['ocr_confidence']}")

    # ─── Build Structured Claims ────────────────────────────────────
    header("CLAIM EXTRACTION (STRUCTURED — NO LLM)", BG_BLUE)

    now_epoch = int(datetime.now(timezone.utc).timestamp())
    last_dose_epoch = now_epoch - int(rec["last_dose_hours_ago"] * 3600)
    last_vitals_epoch = now_epoch - int(rec["last_vitals_minutes_ago"] * 60)

    claims = [
        # Temporal: last morphine dose
        Claim(
            subject="patient",
            relation="morphine_dose_time",
            object=str(last_dose_epoch),
        ),
        # Temporal: last vitals check
        Claim(
            subject="patient",
            relation="last_vitals_check",
            object=str(last_vitals_epoch),
        ),
        # Range: dosage
        Claim(
            subject="patient",
            relation="morphine_dosage_mg",
            object=str(rec["dosage_mg"]),
        ),
        # Range: OCR confidence
        Claim(
            subject="patient",
            relation="ocr_confidence",
            object=str(rec["ocr_confidence"]),
        ),
        # Pain score (informational)
        Claim(
            subject="patient",
            relation="pain_score",
            object=str(rec["patient_pain_score"]),
        ),
    ]

    for i, c in enumerate(claims):
        print(f"  {DIM}[{i}] {c.subject}.{c.relation} = {c.object}{RESET}")

    # ─── Bias Audit ─────────────────────────────────────────────────
    bias_warnings = audit_extraction_bias(claims)
    if bias_warnings:
        for w in bias_warnings:
            status(f"{YELLOW}!{RESET}", f"Bias flag: {w}")

    # ─── Z3 Formal Verification ────────────────────────────────────
    header("Z3 FORMAL VERIFICATION", BG_BLUE)

    print(f"  {DIM}Invoking Z3 SMT solver...{RESET}")
    print(f"  {DIM}System time: {now_epoch} ({datetime.fromtimestamp(now_epoch, tz=timezone.utc).isoformat()}){RESET}")
    print(f"  {DIM}Last dose:   {last_dose_epoch} ({rec['last_dose_hours_ago']}h ago){RESET}")
    print(f"  {DIM}Last vitals: {last_vitals_epoch} ({rec['last_vitals_minutes_ago']}min ago){RESET}")

    t0 = time.perf_counter()
    result = verify_structured(
        response_claims=claims,
        kb=kb,
        system_time=now_epoch,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000

    print(f"  {DIM}Z3 completed in {elapsed_ms:.1f}ms{RESET}")

    # ─── VERDICT ────────────────────────────────────────────────────
    if result.is_hallucinating:
        print()
        print(f"  {BG_RED}{BOLD}{WHITE}                                                    {RESET}")
        print(f"  {BG_RED}{BOLD}{WHITE}   !! CRITICAL MEDICAL ALERT — ORDER BLOCKED !!      {RESET}")
        print(f"  {BG_RED}{BOLD}{WHITE}                                                    {RESET}")
        print()
        print(f"  {LINE}")
        print(f"  {RED}{BOLD}Z3 Verdict:{RESET} UNSAT (mathematical proof of violation)")
        print(f"  {RED}{BOLD}Confidence:{RESET} {result.confidence} (this is a proof, not a probability)")
        print(f"  {RED}{BOLD}Contradicted claims:{RESET} {result.contradicted_claims}")
        print(f"  {LINE}")

        print(f"\n  {RED}{BOLD}VIOLATED SAFETY RULES:{RESET}\n")

        for i, rule in enumerate(result.violated_rules, 1):
            severity = rule.get("severity", "error").upper()
            name = rule.get("name", "Unknown")
            message = rule.get("message", "").strip()
            print(f"  {RED}{BOLD}[{severity} #{i}] {name}{RESET}")
            for line in message.split("\n"):
                line = line.strip()
                if line:
                    print(f"    {line}")
            print()

        print(f"  {LINE}")
        print(f"  {RED}{BOLD}MEDICATION ORDER:  B L O C K E D{RESET}")
        print(f"  {LINE}")
        print()
        print(f"  {BOLD}Required Actions:{RESET}")
        print(f"  {YELLOW}1.{RESET} DO NOT administer Morphine to patient {PATIENT['mrn']}")
        print(f"  {YELLOW}2.{RESET} Notify attending physician immediately")
        print(f"  {YELLOW}3.{RESET} Document safety alert in patient chart")
        print(f"  {YELLOW}4.{RESET} Await physician re-evaluation and new order")
        print()

        # Structured alert payload for EHR integration
        alert = {
            "alert_type": "MEDICATION_ORDER_BLOCKED",
            "alert_level": "CRITICAL",
            "patient_mrn": PATIENT["mrn"],
            "patient_name": PATIENT["name"],
            "ward": PATIENT["ward"],
            "medication": rec["medication"],
            "dosage_mg": rec["dosage_mg"],
            "route": rec["route"],
            "violations": [
                {
                    "rule": r["name"],
                    "severity": r["severity"],
                    "message": r["message"].strip(),
                }
                for r in result.violated_rules
            ],
            "ai_model": AI_RECOMMENDATION["model"],
            "z3_result": "UNSAT",
            "z3_latency_ms": round(elapsed_ms, 1),
            "action": "ORDER_BLOCKED",
            "requires": [
                "Attending physician notification",
                "Pharmacist review",
                "Chart documentation",
            ],
        }

        header("EHR INTEGRATION PAYLOAD (HL7/FHIR compatible)", BG_RED)
        print(json.dumps(alert, indent=2, ensure_ascii=False))
        print()

        return 1

    else:
        print()
        print(f"  {BG_GREEN}{BOLD}{WHITE}                                                    {RESET}")
        print(f"  {BG_GREEN}{BOLD}{WHITE}   ALL SAFETY CHECKS PASSED — ORDER APPROVED         {RESET}")
        print(f"  {BG_GREEN}{BOLD}{WHITE}                                                    {RESET}")
        print()
        print(f"  {GREEN}Medication may be administered per physician order.{RESET}")
        print(f"  {DIM}Document administration in MAR (Medication Administration Record).{RESET}")
        print()

        return 0


if __name__ == "__main__":
    sys.exit(main())
