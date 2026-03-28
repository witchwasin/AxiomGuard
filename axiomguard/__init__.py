from axiomguard.core import (
    extract_claims,
    get_knowledge_base,
    load_rules,
    set_entity_resolver,
    set_knowledge_base,
    set_llm_backend,
    translate_to_logic,
    verify,
    verify_with_kb,
)
from axiomguard.knowledge_base import KnowledgeBase
from axiomguard.models import Claim, ExtractionResult, VerificationResult
from axiomguard.parser import AxiomParser, RuleSet
from axiomguard.resolver import EntityResolver

__version__ = "0.3.0-dev"
__all__ = [
    "verify",
    "verify_with_kb",
    "extract_claims",
    "translate_to_logic",
    "set_llm_backend",
    "set_entity_resolver",
    "set_knowledge_base",
    "get_knowledge_base",
    "load_rules",
    "Claim",
    "ExtractionResult",
    "VerificationResult",
    "EntityResolver",
    "AxiomParser",
    "KnowledgeBase",
    "RuleSet",
]
