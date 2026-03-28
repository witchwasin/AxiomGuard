"""
AxiomGuard Integration — Selective Verification for RAG Pipelines

Sits post-reranking / pre-synthesis in a RAG pipeline:
  Vector Retrieval → Reranking → ★ AxiomGuard verify_chunks ★ → LLM Synthesis

The Selective Verification Algorithm:
  1. Extract claims from each chunk's text
  2. Axiom-Relation Overlap Filter (skip irrelevant claims) → 60-80% reduction
  3. Dedup across chunks → 10-30% reduction
  4. Z3 verify remaining claims → 5-50ms
  5. Annotate or filter chunks

Usage:
    from axiomguard import KnowledgeBase
    from axiomguard.integration import verify_chunks

    kb = KnowledgeBase()
    kb.load("rules/medical.axiom.yml")

    chunks = [
        {"text": "Drug A treats condition X", "score": 0.95},
        {"text": "Patient can take Warfarin and Aspirin together", "score": 0.88},
    ]

    verified = verify_chunks(chunks, kb=kb, mode="annotate")
    # Each chunk now has ["_axiomguard"] metadata
"""

from __future__ import annotations

import hashlib
from typing import Literal

from axiomguard.knowledge_base import KnowledgeBase
from axiomguard.models import Claim


# =====================================================================
# verify_chunks — The Standalone RAG Integration API
# =====================================================================


def verify_chunks(
    chunks: list[dict],
    kb: KnowledgeBase,
    mode: Literal["annotate", "filter", "strict"] = "annotate",
    text_field: str = "text",
    axiom_claims: list[Claim] | None = None,
) -> list[dict]:
    """Verify retrieved chunks against a KnowledgeBase.

    Implements the Selective Verification Algorithm from v0.4.0 research:
    extract → filter by axiom relations → dedup → Z3 verify → annotate.

    Args:
        chunks: List of chunk dicts. Each must have a text field.
                Expected shape: {"text": "...", "score": 0.9, "metadata": {...}}
        kb: A loaded KnowledgeBase with compiled YAML rules.
        mode: How to handle verification results:
              - "annotate": Keep all chunks, add _axiomguard metadata (default).
              - "filter": Remove chunks with contradictions.
              - "strict": Remove chunks with ANY unverifiable claims.
        text_field: Key in chunk dict containing the document text.
        axiom_claims: Optional ground-truth facts to verify against.

    Returns:
        List of chunk dicts (modified in-place for annotate mode).
    """
    from axiomguard.core import _extract

    if not chunks:
        return []

    relevant_relations = kb.axiom_relations()

    # === Stage 1: Extract claims from each chunk ===
    chunk_claims: list[list[Claim]] = []
    for chunk in chunks:
        text = chunk.get(text_field, "")
        if not text:
            chunk_claims.append([])
            continue
        claims = _extract(text)
        resolved, _ = kb.resolver.resolve_claims(claims)
        chunk_claims.append(resolved)

    # === Stage 2: Axiom-Relation Overlap Filter ===
    # Only keep claims whose relation matches a loaded rule
    filtered_claims: list[list[Claim]] = []
    for claims in chunk_claims:
        relevant = [c for c in claims if c.relation in relevant_relations]
        filtered_claims.append(relevant)

    # === Stage 3: Dedup across all chunks ===
    seen_keys: set[tuple[str, str, str]] = set()
    deduped_claims: list[list[Claim]] = []
    for claims in filtered_claims:
        unique: list[Claim] = []
        for c in claims:
            key = (c.subject.lower(), c.relation.lower(), c.object.lower())
            if key not in seen_keys:
                seen_keys.add(key)
                unique.append(c)
        deduped_claims.append(unique)

    # === Stage 4: Z3 Verify each chunk's claims ===
    results: list[dict] = []
    output: list[dict] = []

    for i, (chunk, claims) in enumerate(zip(chunks, deduped_claims)):
        if not claims:
            # No verifiable claims — pass through
            ag_meta = {
                "status": "pass",
                "violated_rules": [],
                "verified_claims": 0,
                "total_claims": len(chunk_claims[i]),
                "skipped_claims": len(chunk_claims[i]),
            }
        else:
            result = kb.verify(claims, axiom_claims)
            ag_meta = {
                "status": "fail" if result.is_hallucinating else "pass",
                "violated_rules": [
                    {"name": r["name"], "severity": r["severity"], "message": r["message"]}
                    for r in result.violated_rules
                ],
                "verified_claims": len(claims),
                "total_claims": len(chunk_claims[i]),
                "skipped_claims": len(chunk_claims[i]) - len(claims),
                "reason": result.reason if result.is_hallucinating else None,
                "confidence": result.confidence,
            }

        # === Stage 5: Apply mode ===
        if mode == "annotate":
            chunk.setdefault("metadata", {})
            chunk["metadata"]["_axiomguard"] = ag_meta
            output.append(chunk)

        elif mode == "filter":
            if ag_meta["status"] != "fail":
                output.append(chunk)

        elif mode == "strict":
            # Strict: only pass chunks where ALL claims were verified and passed
            if ag_meta["status"] == "pass" and ag_meta["skipped_claims"] == 0:
                output.append(chunk)
            elif ag_meta["total_claims"] == 0:
                output.append(chunk)  # no claims = nothing to verify

    return output


# =====================================================================
# Stats helper
# =====================================================================


def verification_stats(chunks: list[dict]) -> dict:
    """Summarize verification results across annotated chunks.

    Args:
        chunks: Chunks that were processed by verify_chunks(mode="annotate").

    Returns:
        Dict with aggregate stats.
    """
    total = len(chunks)
    passed = 0
    failed = 0
    total_claims = 0
    verified_claims = 0
    skipped_claims = 0
    all_violated: list[dict] = []

    for chunk in chunks:
        meta = chunk.get("metadata", {}).get("_axiomguard", {})
        if meta.get("status") == "pass":
            passed += 1
        elif meta.get("status") == "fail":
            failed += 1
        total_claims += meta.get("total_claims", 0)
        verified_claims += meta.get("verified_claims", 0)
        skipped_claims += meta.get("skipped_claims", 0)
        all_violated.extend(meta.get("violated_rules", []))

    return {
        "total_chunks": total,
        "passed": passed,
        "failed": failed,
        "total_claims": total_claims,
        "verified_claims": verified_claims,
        "skipped_claims": skipped_claims,
        "violated_rules": all_violated,
    }
