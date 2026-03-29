"""
AxiomGuard Core — Neuro-Symbolic Verification Engine

v0.2.0 Pipeline:
  1. Extract claims from text (LLM backend → validation pipeline)
  2. Resolve entities (EntityResolver — deterministic canonicalization)
  3. Prove contradictions (Z3 SMT solver with Assumptions API)

The LLM backend is pluggable: swap via set_llm_backend() for real API clients.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from axiomguard.models import Claim, CorrectionAttempt, CorrectionResult, VerificationResult
from axiomguard.resolver import EntityResolver


# =====================================================================
# Module-level state
# =====================================================================

_entity_resolver = EntityResolver()
_knowledge_base = None  # set via set_knowledge_base() or load_rules()


# =====================================================================
# LLM Backend — Pluggable Interface (v0.2.0: returns list[Claim])
# =====================================================================


def _mock_llm_extract(text: str) -> list[Claim]:
    """Rule-based mock that simulates LLM multi-claim extraction.

    Handles common sentence patterns to keep the PoC running without
    API calls. Designed to be replaced by a real LLM backend.
    """
    normalized = text.strip().rstrip(".").lower()

    # Detect negation
    negated = False
    for neg in ["is not ", "isn't ", "not the ", "never "]:
        if neg in normalized:
            negated = True
            normalized = normalized.replace(neg, "is " if "is not " in neg or "isn't " in neg else "")
            break

    # Pattern: "X is in Y" / "X is located in Y" / "X is based in Y"
    for prep in ["is located in", "is based in", "located in", "based in", "is in"]:
        if prep in normalized:
            parts = normalized.split(prep, 1)
            subject = _extract_subject(parts[0].strip())
            obj = parts[1].strip().title()
            return [Claim(subject=subject, relation="location", object=obj, negated=negated)]

    # Pattern: "X is Y" (identity / attribute)
    if " is " in normalized:
        parts = normalized.split(" is ", 1)
        subject = _extract_subject(parts[0].strip())
        obj = parts[1].strip()
        # Preserve original casing from the raw text for the object
        raw_obj = text.strip().rstrip(".").split(" is ", 1)
        if len(raw_obj) == 2:
            obj_original = raw_obj[1].strip()
            # Remove negation words from the preserved casing version
            for neg in ["not ", "NOT ", "Not "]:
                obj_original = obj_original.replace(neg, "")
            obj = obj_original.strip()
        return [Claim(subject=subject, relation="identity", object=obj, negated=negated)]

    # Fallback
    return [Claim(subject="unknown", relation="states", object=normalized)]


def _extract_subject(raw: str) -> str:
    """Normalize a subject phrase to a canonical entity name."""
    for prefix in ["the ", "our ", "a ", "an ", "their ", "its "]:
        if raw.startswith(prefix):
            raw = raw[len(prefix):]

    synonyms = {
        "headquarters": "company",
        "hq": "company",
        "head office": "company",
        "main office": "company",
        "company headquarters": "company",
        "firm": "company",
        "organization": "company",
        "office": "company",
    }
    return synonyms.get(raw, raw)


# Active backend
_llm_backend: Callable[[str], list[Claim]] = _mock_llm_extract


def set_llm_backend(backend: Callable) -> None:
    """Replace the mock LLM with a real API client.

    The backend should be a function that takes a text string and returns
    a list[Claim]. For backward compatibility, backends returning a single
    dict with "subject"/"relation"/"object" keys are auto-wrapped.

    Example::

        from axiomguard.backends.anthropic_llm import create_anthropic_extractor
        set_llm_backend(create_anthropic_extractor())
    """
    global _llm_backend
    _llm_backend = backend


def set_entity_resolver(resolver: EntityResolver) -> None:
    """Replace the default EntityResolver with a custom one.

    Example::

        resolver = EntityResolver(aliases={"กทม": "Bangkok", "สยาม": "Thailand"})
        set_entity_resolver(resolver)
    """
    global _entity_resolver
    _entity_resolver = resolver


def load_rules(path: str) -> None:
    """Load an .axiom.yml file into the global KnowledgeBase (v0.3.0).

    Creates a new KnowledgeBase if one doesn't exist. Entity aliases
    from the YAML are automatically merged into the global EntityResolver.

    Example::

        import axiomguard
        axiomguard.load_rules("rules/medical.axiom.yml")
        result = axiomguard.verify_with_kb(
            response="Patient takes Aspirin",
            axioms=["Patient takes Warfarin"],
        )
    """
    from axiomguard.knowledge_base import KnowledgeBase

    global _knowledge_base, _entity_resolver
    if _knowledge_base is None:
        _knowledge_base = KnowledgeBase(resolver=_entity_resolver)
    _knowledge_base.load(path)
    # Sync resolver (KB may have added aliases from YAML entities)
    _entity_resolver = _knowledge_base.resolver


def set_knowledge_base(kb) -> None:
    """Set the global KnowledgeBase directly (v0.3.0).

    Example::

        from axiomguard.knowledge_base import KnowledgeBase
        kb = KnowledgeBase()
        kb.load_string(yaml_content)
        set_knowledge_base(kb)
    """
    global _knowledge_base, _entity_resolver
    _knowledge_base = kb
    if kb is not None:
        _entity_resolver = kb.resolver


def get_knowledge_base():
    """Get the current global KnowledgeBase (or None)."""
    return _knowledge_base


# =====================================================================
# Internal — Extraction with backward-compat wrapping
# =====================================================================


def _extract(text: str) -> list[Claim]:
    """Call the active backend and normalize the result to list[Claim].

    Handles v0.1.0 backends that return a single dict.
    """
    result = _llm_backend(text)

    # v0.1.0 compat: single dict → wrap in list[Claim]
    if isinstance(result, dict):
        return [Claim(
            subject=result["subject"],
            relation=result["relation"],
            object=result["object"],
            negated=result.get("negated", False),
        )]

    return result


# =====================================================================
# Public API — Logic Translation
# =====================================================================


def translate_to_logic(text: str) -> dict:
    """Translate natural language to a Subject-Relation-Object triple.

    v0.1.0 compatibility: returns the FIRST extracted claim as a dict.
    For multi-claim extraction, use extract_claims() instead.
    """
    claims = _extract(text)
    c = claims[0]
    return {"subject": c.subject, "relation": c.relation, "object": c.object}


def extract_claims(text: str) -> list[Claim]:
    """Extract all claims from natural language text (v0.2.0).

    Uses the active LLM backend to extract structured claims,
    then resolves entities via the active EntityResolver.

    Args:
        text: A natural language statement.

    Returns:
        A list of resolved Claim objects.
    """
    claims = _extract(text)
    resolved, _ = _entity_resolver.resolve_claims(claims)
    return resolved


# =====================================================================
# Public API — Verification
# =====================================================================


def verify(response: str, axioms: list[str]) -> VerificationResult:
    """Verify an LLM response against a set of ground-truth axioms.

    v0.2.0 Pipeline:
      1. Extract claims from each axiom and the response (LLM layer).
      2. Resolve entities (EntityResolver — deterministic).
      3. Z3 SMT solver with Assumptions API (Math layer).
      4. Return result with confidence level and transparency warnings.

    Args:
        response: The LLM-generated text to verify.
        axioms: Ground-truth statements the response must not contradict.

    Returns:
        VerificationResult with confidence ("proven" or "uncertain")
        and extraction_warnings for full transparency.
    """
    from axiomguard.z3_engine import check_claims

    all_warnings: list[str] = []

    # Step 1: Extract claims from axioms
    axiom_claims: list[Claim] = []
    for axiom in axioms:
        claims = _extract(axiom)
        resolved, warnings = _entity_resolver.resolve_claims(claims)
        axiom_claims.extend(resolved)
        all_warnings.extend(warnings)

    # Step 2: Extract claims from response
    response_claims = _extract(response)
    response_claims, warnings = _entity_resolver.resolve_claims(response_claims)
    all_warnings.extend(warnings)

    # Step 3: Z3 formal contradiction check
    is_hallucinating, reason, contradicted = check_claims(
        axiom_claims, response_claims
    )

    # Step 4: Determine confidence
    # Z3 UNSAT = mathematical proof → always "proven"
    # Z3 SAT/unknown with warnings → "uncertain"
    if is_hallucinating:
        confidence = "proven"  # UNSAT is a proof, period
    elif all_warnings:
        confidence = "uncertain"  # SAT but extraction had issues
    else:
        confidence = "proven"  # SAT with clean extraction

    return VerificationResult(
        is_hallucinating=is_hallucinating,
        reason=reason,
        confidence=confidence,
        extraction_warnings=all_warnings,
        contradicted_claims=contradicted,
    )


def verify_with_kb(
    response: str,
    axioms: list[str] | None = None,
    kb=None,
) -> VerificationResult:
    """Verify an LLM response using the KnowledgeBase rule engine (v0.3.0).

    Uses YAML rules for constraint checking. When a contradiction is found,
    the result includes violated_rules with custom messages from the YAML.

    Pipeline:
      1. Extract claims from response and axioms (LLM layer).
      2. Resolve entities (EntityResolver — from YAML aliases + defaults).
      3. KnowledgeBase.verify() — YAML rules + Z3 (Math layer).
      4. Return result with violated_rules and custom messages.

    Args:
        response: The LLM-generated text to verify.
        axioms: Optional ground-truth statements (natural language).
        kb: Optional KnowledgeBase override. Uses global KB if None.

    Returns:
        VerificationResult with violated_rules, custom messages, and proof trace.

    Raises:
        RuntimeError: If no KnowledgeBase is loaded and none is provided.
    """
    active_kb = kb or _knowledge_base
    if active_kb is None:
        raise RuntimeError(
            "No KnowledgeBase loaded. Call load_rules() or pass a KnowledgeBase."
        )

    all_warnings: list[str] = []

    # Step 1: Extract claims from response
    response_claims = _extract(response)
    response_claims, warnings = active_kb.resolver.resolve_claims(response_claims)
    all_warnings.extend(warnings)

    # Step 2: Extract claims from axioms (optional)
    axiom_claims: list[Claim] = []
    if axioms:
        for axiom in axioms:
            claims = _extract(axiom)
            resolved, warnings = active_kb.resolver.resolve_claims(claims)
            axiom_claims.extend(resolved)
            all_warnings.extend(warnings)

    # Step 3: KB verification (YAML rules + Z3)
    result = active_kb.verify(response_claims, axiom_claims)

    # Merge extraction warnings
    result.extraction_warnings = all_warnings + result.extraction_warnings

    return result


# =====================================================================
# Extraction Bias Audit (v0.6.0)
# =====================================================================

# Default protected attributes — users can override via audit_extraction_bias()
DEFAULT_PROTECTED_ATTRIBUTES = frozenset({
    "gender", "male", "female", "man", "woman", "boy", "girl",
    "race", "white", "black", "asian", "hispanic", "latino", "latina",
    "religion", "muslim", "christian", "jewish", "hindu", "buddhist",
    "age", "elderly", "young", "old",
    "disability", "disabled", "handicapped",
    "ethnicity", "ethnic",
    "sexual orientation", "gay", "lesbian", "transgender",
})


def audit_extraction_bias(
    claims: List[Claim],
    protected_attributes: Optional[frozenset] = None,
) -> List[str]:
    """Check extracted claims for protected attribute leakage (v0.6.0).

    Deterministic keyword check — no LLM involved. Scans claim subjects
    and objects for protected attribute terms that may indicate bias
    was encoded during extraction.

    This does NOT block verification — it adds warnings to the audit trail
    so humans can review flagged claims.

    Args:
        claims: Extracted claims to audit.
        protected_attributes: Set of lowercase terms to flag.
            Defaults to DEFAULT_PROTECTED_ATTRIBUTES.

    Returns:
        List of warning strings for flagged claims.

    Example::

        claims = extract_claims("The female applicant was recommended for secretary.")
        warnings = audit_extraction_bias(claims)
        # → ["Claim 0: protected attribute 'female' detected in
        #     'female applicant identity secretary'"]
    """
    attrs = protected_attributes or DEFAULT_PROTECTED_ATTRIBUTES
    warnings: List[str] = []

    for i, claim in enumerate(claims):
        claim_text = f"{claim.subject} {claim.relation} {claim.object}".lower()
        for attr in attrs:
            if attr in claim_text:
                warnings.append(
                    f"Claim {i}: protected attribute '{attr}' detected in "
                    f"'{claim.subject} {claim.relation} {claim.object}'"
                )
                break  # One warning per claim is enough

    return warnings


# =====================================================================
# Public API — Structured Input Path (v0.6.0)
# =====================================================================


def verify_structured(
    response_claims: List[Union[Claim, Dict[str, Any]]],
    axiom_claims: Optional[List[Union[Claim, Dict[str, Any]]]] = None,
    kb=None,
    system_time=None,
) -> VerificationResult:
    """Verify pre-structured claims directly — no LLM extraction (v0.6.0).

    This is the "structured input path" that bypasses the LLM extractor
    entirely. Use this when your upstream system already produces structured
    claims (e.g., from constrained decoding, form inputs, or database queries).

    Accepts claims as Claim objects or plain dicts with subject/relation/object keys.

    Pipeline:
      1. Parse input → list[Claim] (no LLM)
      2. Resolve entities (EntityResolver — deterministic)
      3. KnowledgeBase.verify() — YAML rules + Z3 (Math layer)

    Args:
        response_claims: Claims to verify. Each item is either a Claim object
            or a dict with keys: subject, relation, object, and optionally negated.
        axiom_claims: Optional ground-truth claims (same format as response_claims).
        kb: KnowledgeBase to verify against. Uses global KB if None.
        system_time: For temporal rules — str (ISO), datetime, int (epoch), or None.

    Returns:
        VerificationResult with violated_rules, custom messages, and proof trace.

    Raises:
        RuntimeError: If no KnowledgeBase is loaded and none is provided.
        ValueError: If claims cannot be parsed.

    Example::

        from axiomguard import verify_structured, Claim

        # With Claim objects
        result = verify_structured(
            response_claims=[
                Claim(subject="patient", relation="takes", object="Aspirin"),
            ],
            axiom_claims=[
                Claim(subject="patient", relation="takes", object="Warfarin"),
            ],
            kb=kb,
        )

        # With plain dicts (e.g., from JSON API)
        result = verify_structured(
            response_claims=[
                {"subject": "patient", "relation": "takes", "object": "Aspirin"},
            ],
            axiom_claims=[
                {"subject": "patient", "relation": "takes", "object": "Warfarin"},
            ],
            kb=kb,
        )
    """
    active_kb = kb or _knowledge_base
    if active_kb is None:
        raise RuntimeError(
            "No KnowledgeBase loaded. Call load_rules() or pass a KnowledgeBase."
        )

    # Parse claims
    parsed_response = _parse_claim_inputs(response_claims)
    parsed_axioms = _parse_claim_inputs(axiom_claims) if axiom_claims else None

    # Resolve entities
    resolved_response, warnings = active_kb.resolver.resolve_claims(parsed_response)
    resolved_axioms = None
    if parsed_axioms:
        resolved_axioms, ax_warnings = active_kb.resolver.resolve_claims(parsed_axioms)
        warnings.extend(ax_warnings)

    # Verify with Z3
    result = active_kb.verify(
        resolved_response,
        resolved_axioms,
        system_time=system_time,
    )
    result.extraction_warnings = warnings + result.extraction_warnings
    return result


def _parse_claim_inputs(
    claims: List[Union[Claim, Dict[str, Any]]],
) -> List[Claim]:
    """Convert mixed Claim/dict inputs to a list of Claim objects."""
    parsed: List[Claim] = []
    for i, item in enumerate(claims):
        if isinstance(item, Claim):
            parsed.append(item)
        elif isinstance(item, dict):
            try:
                parsed.append(Claim(
                    subject=item["subject"],
                    relation=item["relation"],
                    object=item["object"],
                    negated=item.get("negated", False),
                ))
            except (KeyError, TypeError) as e:
                raise ValueError(
                    f"Claim at index {i} is missing required keys "
                    f"(subject, relation, object): {e}"
                ) from e
        else:
            raise ValueError(
                f"Claim at index {i} must be a Claim object or dict, "
                f"got {type(item).__name__}"
            )
    return parsed


# =====================================================================
# Public API — Self-Correction Loop (v0.5.0)
# =====================================================================


def generate_with_guard(
    prompt: str,
    kb,
    llm_generate: Callable,
    axiom_claims: list[Claim] | None = None,
    max_retries: int = 2,
    timeout_seconds: float = 30.0,
    mode: str = "correct",
    on_escalate: Callable | None = None,
) -> CorrectionResult:
    """Generate an LLM response with automated guardrails (v0.5.0, v0.6.0).

    Three modes of operation:

      mode="correct" (default, v0.5.0):
        Retry loop — if Z3 returns UNSAT, build correction prompt and retry.
        Best for general-purpose chatbot use cases.

      mode="block" (v0.6.0):
        Block-and-halt — if Z3 returns UNSAT, immediately stop and return
        a deterministic blocked result. No retries. Best for high-stakes
        domains (medical, finance) where optimizing-to-pass is dangerous.

      mode="escalate" (v0.6.0):
        Block-and-escalate — same as "block", but also calls on_escalate
        callback with the blocked result for external routing (webhook,
        human review queue, incident system). Requires on_escalate parameter.

    Args:
        prompt: The user's original question/instruction.
        kb: Loaded KnowledgeBase with domain rules.
        llm_generate: Function (str) -> str that calls any LLM.
        axiom_claims: Optional ground-truth facts to verify against.
        max_retries: Maximum correction attempts (default: 2). Ignored in block/escalate mode.
        timeout_seconds: Wall-clock timeout for all attempts (default: 30s).
        mode: "correct" | "block" | "escalate" (default: "correct").
        on_escalate: Callback (CorrectionResult) -> None for escalate mode.

    Returns:
        CorrectionResult with status, final response, and full attempt history.

    Raises:
        ValueError: If mode is invalid or escalate mode lacks on_escalate callback.
    """
    if mode not in ("correct", "block", "escalate"):
        raise ValueError(
            f"Invalid mode '{mode}'. Must be 'correct', 'block', or 'escalate'."
        )
    if mode == "escalate" and on_escalate is None:
        raise ValueError("mode='escalate' requires an on_escalate callback.")

    import time
    from axiomguard.correction import build_correction_prompt

    # In block/escalate mode, only 1 attempt (no retries)
    if mode in ("block", "escalate"):
        max_attempts = 1
    else:
        max_attempts = 1 + max_retries

    history: list[CorrectionAttempt] = []
    current_prompt = prompt
    deadline = time.monotonic() + timeout_seconds

    for attempt_num in range(1, max_attempts + 1):
        # --- Timeout check ---
        if time.monotonic() > deadline:
            break

        # --- Step 1: Generate ---
        response_text = llm_generate(current_prompt)

        # --- Step 2: Extract claims ---
        response_claims = _extract(response_text)
        resolved_claims, _ = kb.resolver.resolve_claims(response_claims)

        # --- Step 3: Verify ---
        if not resolved_claims:
            attempt = CorrectionAttempt(
                attempt_number=attempt_num,
                response=response_text,
                claims=[],
                verification=None,
                correction_prompt=current_prompt if attempt_num > 1 else None,
            )
            history.append(attempt)
            return CorrectionResult(
                status="unverifiable",
                response=response_text,
                attempts=attempt_num,
                max_attempts=max_attempts,
                history=history,
                final_verification=None,
            )

        verification = kb.verify(resolved_claims, axiom_claims)

        # --- Step 4: Record attempt ---
        attempt = CorrectionAttempt(
            attempt_number=attempt_num,
            response=response_text,
            claims=list(resolved_claims),
            verification=verification,
            correction_prompt=current_prompt if attempt_num > 1 else None,
        )
        history.append(attempt)

        # --- Step 5: Check result ---
        if not verification.is_hallucinating:
            status = "verified" if attempt_num == 1 else "corrected"
            return CorrectionResult(
                status=status,
                response=response_text,
                attempts=attempt_num,
                max_attempts=max_attempts,
                history=history,
                final_verification=verification,
            )

        # --- Step 6: Mode-specific handling of UNSAT ---
        if mode in ("block", "escalate"):
            result = CorrectionResult(
                status="blocked",
                response=response_text,
                attempts=1,
                max_attempts=1,
                history=history,
                final_verification=verification,
            )
            if mode == "escalate" and on_escalate is not None:
                on_escalate(result)
            return result

        # mode="correct" — build correction prompt for next attempt
        if attempt_num < max_attempts and time.monotonic() < deadline:
            current_prompt = build_correction_prompt(
                original_prompt=prompt,
                response=response_text,
                claims=resolved_claims,
                verification=verification,
                attempt_number=attempt_num,
                max_attempts=max_attempts,
            )

    # --- All attempts exhausted (only reachable in "correct" mode) ---
    if len(history) >= 2:
        violation_sets = []
        for h in history:
            if h.verification and h.verification.violated_rules:
                names = frozenset(r["name"] for r in h.verification.violated_rules)
                violation_sets.append(names)
        if violation_sets and all(vs == violation_sets[0] for vs in violation_sets):
            status = "constraint_conflict"
        else:
            status = "failed"
    else:
        status = "failed"

    last_verification = history[-1].verification if history else None

    return CorrectionResult(
        status=status,
        response=history[-1].response if history else "",
        attempts=len(history),
        max_attempts=max_attempts,
        history=history,
        final_verification=last_verification,
    )
