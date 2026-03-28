"""
AxiomGuard Correction Engine — Feedback Prompt Builder for Self-Healing Loop

Translates Z3 UNSAT proofs + violated YAML rules into structured correction
prompts that guide the LLM to fix specific errors without regression.

Research basis: v050_self_correction_strategy.md
  - Specific feedback (50-70% fix rate) vs vague "try again" (10-20%)
  - "What to preserve" section prevents regression
  - Assertion-style language for non-negotiable constraints

Usage:
    from axiomguard.correction import build_correction_prompt

    prompt = build_correction_prompt(
        original_prompt="What drugs for a heart patient?",
        response="Patient takes Warfarin and Aspirin daily.",
        claims=extracted_claims,
        verification=unsat_result,
    )
    # → Structured prompt with error details + preserve list
"""

from __future__ import annotations

from axiomguard.models import Claim, VerificationResult


# =====================================================================
# Correction Prompt Template
# =====================================================================

CORRECTION_PROMPT = """\
Your previous response failed formal verification by AxiomGuard.

## WHAT WENT WRONG

{violation_details}

## RULES THAT WERE VIOLATED

{rule_list}

## WHAT WAS CORRECT (preserve these)

{verified_claims}

## YOUR TASK

Regenerate your response to the original question, fixing ONLY the identified \
errors while preserving all correct information.

Do NOT apologize or explain the error — just provide the corrected response.

Original question: {original_prompt}\
"""

# Escalation prompt for final retry — more urgent, summarized context
FINAL_RETRY_PROMPT = """\
FINAL ATTEMPT — previous {prev_attempts} attempts all failed formal verification.

## ERRORS THAT KEEP OCCURRING

{violation_summary}

## MANDATORY CONSTRAINTS

{rule_list}

## YOUR TASK

This is your LAST chance. Produce a response to the question below that \
satisfies ALL constraints. If the constraints are impossible to satisfy, \
say so explicitly rather than guessing.

Original question: {original_prompt}\
"""


# =====================================================================
# Prompt Builder
# =====================================================================


def build_correction_prompt(
    original_prompt: str,
    response: str,
    claims: list[Claim],
    verification: VerificationResult,
    attempt_number: int = 1,
    max_attempts: int = 3,
) -> str:
    """Build a structured correction prompt from Z3 verification results.

    Uses YAML custom messages when available, falls back to Z3 proof details.
    Includes a "preserve" section listing verified-correct claims to prevent
    regression on retry.

    Args:
        original_prompt: The user's original question/instruction.
        response: The LLM's response text that failed verification.
        claims: Extracted claims from the response.
        verification: The VerificationResult (must be is_hallucinating=True).
        attempt_number: Current attempt (1-based). Used for escalation logic.
        max_attempts: Total configured attempts. Used for final-retry escalation.

    Returns:
        A formatted correction prompt string ready to send to the LLM.
    """
    # Build violation details (specific per claim)
    violation_details = _build_violation_details(claims, verification)

    # Build rule list from violated YAML rules
    rule_list = _build_rule_list(verification)

    # Build verified claims list (what to preserve)
    verified_claims = _build_verified_claims(claims, verification)

    # Use escalation template for the final attempt
    if attempt_number >= max_attempts - 1 and attempt_number > 1:
        return FINAL_RETRY_PROMPT.format(
            prev_attempts=attempt_number,
            violation_summary=violation_details,
            rule_list=rule_list,
            original_prompt=original_prompt,
        )

    return CORRECTION_PROMPT.format(
        violation_details=violation_details,
        rule_list=rule_list,
        verified_claims=verified_claims,
        original_prompt=original_prompt,
    )


# =====================================================================
# Component Builders
# =====================================================================


def _build_violation_details(
    claims: list[Claim],
    verification: VerificationResult,
) -> str:
    """Build the 'WHAT WENT WRONG' section.

    Maps each contradicted claim index to a human-readable error line
    using the verification reason and violated rule messages.
    """
    if not verification.contradicted_claims:
        return f"Logical contradiction detected: {verification.reason}"

    parts: list[str] = []
    for idx in verification.contradicted_claims:
        if idx < len(claims):
            claim = claims[idx]
            claim_str = f"{claim.subject} {claim.relation} {claim.object}"
            if claim.negated:
                claim_str = f"NOT ({claim_str})"

            # Find the specific rule message for this claim
            rule_msg = _find_rule_message_for_claim(claim, verification)

            parts.append(
                f"- You stated: \"{claim_str}\"\n"
                f"  This is WRONG: {rule_msg}"
            )
        else:
            parts.append(f"- Claim at index {idx} violates constraints.")

    return "\n".join(parts) if parts else f"Contradiction: {verification.reason}"


def _find_rule_message_for_claim(
    claim: Claim,
    verification: VerificationResult,
) -> str:
    """Find the most relevant rule message for a specific failed claim."""
    for rule in verification.violated_rules:
        if rule.get("message"):
            return rule["message"]

    # Fallback to the general reason
    reason = verification.reason
    # Strip the "Z3 proved contradiction (UNSAT): " prefix for readability
    if "UNSAT): " in reason:
        reason = reason.split("UNSAT): ", 1)[1]
    return reason


def _build_rule_list(verification: VerificationResult) -> str:
    """Build the 'RULES THAT WERE VIOLATED' section.

    Numbers each rule with severity tag and custom message.
    """
    if not verification.violated_rules:
        # Fallback: use the reason string
        return f"1. {verification.reason}"

    parts: list[str] = []
    for i, rule in enumerate(verification.violated_rules, 1):
        severity = rule.get("severity", "error").upper()
        name = rule.get("name", "Unknown rule")
        message = rule.get("message", name)
        parts.append(f"{i}. [{severity}] {name}: {message}")

    return "\n".join(parts)


def _build_verified_claims(
    claims: list[Claim],
    verification: VerificationResult,
) -> str:
    """Build the 'WHAT WAS CORRECT' section.

    Lists claims that were NOT in the contradicted set — these should
    be preserved by the LLM on retry to prevent regression.
    """
    contradicted_set = set(verification.contradicted_claims)
    verified: list[str] = []

    for i, claim in enumerate(claims):
        if i not in contradicted_set:
            claim_str = f"{claim.subject} {claim.relation} {claim.object}"
            if claim.negated:
                claim_str = f"NOT ({claim_str})"
            verified.append(f"- {claim_str}")

    if not verified:
        return "No claims were verified as correct — regenerate entirely."

    return "\n".join(verified)
