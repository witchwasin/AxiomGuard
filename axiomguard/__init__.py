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
from axiomguard.integration import verify_chunks, verification_stats
from axiomguard.knowledge_base import KnowledgeBase
from axiomguard.models import Claim, CorrectionAttempt, CorrectionResult, ExtractionResult, VerificationResult
from axiomguard.parser import AxiomParser, RangeRule, RuleSet
from axiomguard.resolver import EntityResolver

__version__ = "0.4.0-dev"
__all__ = [
    "verify",
    "verify_with_kb",
    "verify_chunks",
    "generate_with_guard",
    "verification_stats",
    "extract_claims",
    "translate_to_logic",
    "set_llm_backend",
    "set_entity_resolver",
    "set_knowledge_base",
    "get_knowledge_base",
    "load_rules",
    "Claim",
    "CorrectionAttempt",
    "CorrectionResult",
    "ExtractionResult",
    "VerificationResult",
    "EntityResolver",
    "AxiomParser",
    "KnowledgeBase",
    "RangeRule",
    "RuleSet",
]
