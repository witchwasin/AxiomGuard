"""
AxiomGuard — Deterministic Neuro-Symbolic Guardrails for Enterprise AI.

Quickstart::

    from axiomguard import verify, KnowledgeBase, generate_with_guard

    result = verify("The company is in Chiang Mai", ["The company is in Bangkok"])
    assert result.is_hallucinating is True
"""

# --- Core verification API ---
from axiomguard.core import (
    extract_claims,
    generate_with_guard,
    get_knowledge_base,
    load_rules,
    set_entity_resolver,
    set_knowledge_base,
    set_llm_backend,
    translate_to_logic,
    verify,
    verify_with_kb,
)

# --- Vector DB / RAG integration ---
from axiomguard.integration import verify_chunks, verification_stats

# --- Knowledge base & rule engine ---
from axiomguard.knowledge_base import KnowledgeBase
from axiomguard.parser import AxiomParser, RangeRule, RuleSet

# --- Data models ---
from axiomguard.models import (
    Claim,
    CorrectionAttempt,
    CorrectionResult,
    ExtractionResult,
    VerificationResult,
)

# --- Rule generation (Mode 2 & 3) ---
from axiomguard.rule_generator import (
    RuleBuilder,
    generate_rules,
    generate_rules_to_file,
    generate_rules_to_kb,
)

# --- Tournament mode (Mode 4) ---
from axiomguard.tournament import Tournament

# --- Entity resolution ---
from axiomguard.resolver import EntityResolver

__version__ = "0.5.1"

__all__ = [
    # Core API
    "verify",
    "verify_with_kb",
    "verify_chunks",
    "generate_with_guard",
    "verification_stats",
    "extract_claims",
    "translate_to_logic",
    # Configuration
    "set_llm_backend",
    "set_entity_resolver",
    "set_knowledge_base",
    "get_knowledge_base",
    "load_rules",
    # Data models
    "Claim",
    "CorrectionAttempt",
    "CorrectionResult",
    "ExtractionResult",
    "VerificationResult",
    # Knowledge base
    "KnowledgeBase",
    "AxiomParser",
    "RangeRule",
    "RuleSet",
    # Rule generation
    "RuleBuilder",
    "generate_rules",
    "generate_rules_to_file",
    "generate_rules_to_kb",
    # Tournament mode
    "Tournament",
    # Entity resolution
    "EntityResolver",
]
