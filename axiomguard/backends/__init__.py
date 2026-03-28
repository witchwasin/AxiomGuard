"""
AxiomGuard Backends — Multi-Claim Extraction & Validation Pipeline

v0.2.0 Architecture (5-stage pipeline from research):
  LLM Output → [Parse] → [Schema] → [Semantic] → [Entity Resolve] → Z3

Stage 4 (Entity Resolution) is handled by core.py using EntityResolver,
not in this module. Backends handle Stages 1-3.
"""

from __future__ import annotations

import json
import re
import warnings
from typing import Tuple

from axiomguard.models import Claim, ExtractionResult


# =====================================================================
# System Prompt v2 — Multi-Claim with Atomic Proposition Rules
# =====================================================================

SYSTEM_PROMPT = """\
You are a Neuro-Symbolic Logic Extractor for the AxiomGuard verification engine.

Your ONLY job: read a natural language sentence and extract ALL factual claims \
as a JSON object containing a "claims" array.

## Output Format (STRICT)

Return ONLY this JSON — no markdown fences, no explanation, no preamble:
{"claims": [{"subject": "...", "relation": "...", "object": "...", "negated": false}, ...]}

## Atomic Proposition Rules (CRITICAL)

Each claim in the array MUST satisfy ALL of these rules:

1. **SINGLE-FACT:** Each triple asserts exactly ONE relationship. \
Never combine two facts into one triple.
   - WRONG: {"subject": "company", "relation": "location_and_founding", "object": "Bangkok, 2020"}
   - RIGHT: Two separate claims — one for location, one for founding year.

2. **GROUNDED:** Subject and object must be concrete entities or values. \
No descriptions or explanations.
   - WRONG: {"object": "a large city in the northern region of Thailand"}
   - RIGHT: {"object": "Chiang Mai"}

3. **NON-REDUNDANT:** Do not output the same fact in both directions. \
Pick one canonical direction.
   - If you output (Paris, capitalOf, France), do NOT also output (France, hasCapital, Paris).

4. **TEMPORALLY FLAT:** Treat all claims as present-tense assertions. \
Strip tense markers.

## Negation Handling (CRITICAL)

If the sentence contains a negation ("not", "never", "no", "isn't", etc.), \
you MUST set "negated": true on that claim.
   - Input: "Paris is NOT the capital of Germany"
   - Output: {"subject": "Paris", "relation": "capital", "object": "Germany", "negated": true}

NEVER drop negation words. A positive claim when the source is negative is \
the worst possible error.

## Entity Normalization

Normalize subjects to canonical forms:
- "The company", "Our firm", "The organization" → "company"
- "Headquarters", "HQ", "Head office" → "company"
- "The CEO", "Chief executive" → "CEO"
- Person names: "Mr. Smith", "Smith" → "John Smith" (use fullest known form)

Use lowercase for generic entities, proper casing for names and places.

## Relation Types

Use one of these standard types:
- "location" — where something is (city, country, address)
- "identity" — what something is (name, title, role, type)
- "attribute" — a property (size, color, status, description)
- "temporal" — when something happens (date, year, deadline)
- "quantity" — a numeric value (amount, count, percentage)
- "ownership" — who owns or controls something
- "membership" — who belongs to what group
- "founder" — who founded something
- "capital" — capital city relationship

## Object Values

Preserve specific values with proper casing for names/places. \
Strip determiners unless part of a proper noun.

## Examples

Input: "The company is headquartered in Bangkok and was founded in 2020 by Dr. Somchai."
Output: {"claims": [
  {"subject": "company", "relation": "location", "object": "Bangkok", "negated": false},
  {"subject": "company", "relation": "temporal", "object": "2020", "negated": false},
  {"subject": "company", "relation": "founder", "object": "Dr. Somchai", "negated": false}
]}

Input: "Paris is not the capital of Germany."
Output: {"claims": [
  {"subject": "Paris", "relation": "capital", "object": "Germany", "negated": true}
]}\
"""

# v0.1.0 prompt kept for backward-compatible single-triple backends
SYSTEM_PROMPT_V1 = """\
You are a Neuro-Symbolic Logic Extractor for the AxiomGuard verification engine.

Your ONLY job: read a natural language sentence and extract its core factual claim \
as a single JSON object with exactly three keys.

Output format (NO markdown, NO explanation, ONLY this JSON):
{"subject": "...", "relation": "...", "object": "..."}\
"""


# =====================================================================
# Stage 1: Parse — Extract JSON from raw LLM output
# =====================================================================

def parse_raw_json(raw: str) -> dict:
    """Extract and parse JSON from raw LLM output.

    Handles common LLM formatting issues:
    - Markdown code fences (```json ... ```)
    - Trailing commas
    - Leading/trailing whitespace
    """
    text = raw.strip()

    # Strip markdown fences
    if text.startswith("```"):
        # Remove opening fence (with optional language tag)
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        # Remove closing fence
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()

    # Fix trailing commas before } or ]
    text = re.sub(r",\s*([}\]])", r"\1", text)

    return json.loads(text)


# =====================================================================
# Stage 2: Schema — Validate against Pydantic models
# =====================================================================

def validate_schema(data: dict) -> ExtractionResult:
    """Validate parsed JSON against the ExtractionResult schema.

    Raises:
        pydantic.ValidationError: If the data doesn't match the schema.
    """
    return ExtractionResult.model_validate(data)


# =====================================================================
# Stage 3: Semantic — Check for logical issues in extracted claims
# =====================================================================

NEGATION_WORDS = frozenset({
    "not", "never", "no", "isn't", "wasn't", "don't", "doesn't",
    "didn't", "won't", "can't", "cannot", "neither", "nor",
    "hardly", "barely", "seldom",
})


def check_semantics(
    claims: list[Claim],
    source_text: str,
) -> tuple[list[Claim], list[str]]:
    """Semantic validation: dedup, negation check, groundedness filter.

    Args:
        claims: Validated claims from Stage 2.
        source_text: Original natural language text (for negation detection).

    Returns:
        (filtered_claims, warnings)
    """
    warn: list[str] = []

    # --- Negation check ---
    source_words = set(source_text.lower().split())
    has_negation = bool(source_words & NEGATION_WORDS)
    any_negated = any(c.negated for c in claims)

    if has_negation and not any_negated:
        warn.append(
            "Source text contains negation words but no claim is marked negated. "
            "The LLM may have dropped a negation — verify manually."
        )

    # --- Deduplication ---
    seen: set[tuple[str, str, str]] = set()
    unique: list[Claim] = []
    for claim in claims:
        key = claim.as_key()
        if key in seen:
            warn.append(f"Duplicate claim removed: {claim.subject}.{claim.relation}")
            continue
        seen.add(key)
        unique.append(claim)

    # --- Groundedness: reject overly verbose objects (likely descriptions) ---
    grounded: list[Claim] = []
    for claim in unique:
        if len(claim.object.split()) > 8:
            warn.append(
                f"Non-grounded claim filtered: object too verbose "
                f"({len(claim.object.split())} words): '{claim.object[:50]}...'"
            )
            continue
        grounded.append(claim)

    # --- Atomicity: reject compound relations ---
    final: list[Claim] = []
    for claim in grounded:
        if " and " in claim.relation or " or " in claim.relation:
            warn.append(
                f"Non-atomic relation filtered: '{claim.relation}' "
                f"(contains conjunction)"
            )
            continue
        final.append(claim)

    return final, warn


# =====================================================================
# Combined Pipeline: Stages 1-3
# =====================================================================

def validate_and_extract(
    raw: str,
    source_text: str = "",
) -> tuple[list[Claim], list[str]]:
    """Full validation pipeline: Parse → Schema → Semantic.

    Args:
        raw: Raw LLM output string (may contain markdown fences).
        source_text: Original input text (for negation detection).

    Returns:
        (validated_claims, warnings)

    Raises:
        json.JSONDecodeError: If Stage 1 (parse) fails.
        pydantic.ValidationError: If Stage 2 (schema) fails.
        ValueError: If no claims survive Stage 3 (semantic).
    """
    # Stage 1: Parse
    data = parse_raw_json(raw)

    # Stage 2: Schema validation
    extraction = validate_schema(data)

    # Stage 3: Semantic checks
    claims, warnings = check_semantics(extraction.claims, source_text)

    if not claims:
        raise ValueError(
            "All claims were filtered out during semantic validation. "
            f"Warnings: {warnings}"
        )

    return claims, warnings


# =====================================================================
# Backward Compatibility — v0.1.0 single-triple parse
# =====================================================================

def parse_response(raw: str) -> dict:
    """Parse a single SRO triple from LLM output (v0.1.0 compat).

    For new code, use validate_and_extract() instead.
    """
    return parse_raw_json(raw)
