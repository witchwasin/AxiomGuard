from axiomguard.core import (
    extract_claims,
    set_entity_resolver,
    set_llm_backend,
    translate_to_logic,
    verify,
)
from axiomguard.models import Claim, ExtractionResult, VerificationResult
from axiomguard.resolver import EntityResolver

__version__ = "0.2.0-dev"
__all__ = [
    "verify",
    "extract_claims",
    "translate_to_logic",
    "set_llm_backend",
    "set_entity_resolver",
    "Claim",
    "ExtractionResult",
    "VerificationResult",
    "EntityResolver",
]
