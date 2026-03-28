"""
AxiomGuard Entity Resolver — Canonicalization Pipeline (Method C)

From v0.2.0 Research (Section 2.3):
  "We do NOT use embedding-based thresholds. AxiomGuard's value proposition
   is provable truth, not probability. Introducing a threshold turns every
   verification into a probabilistic claim."

Pipeline:
  1. Unicode normalize (NFKC) + lowercase + strip
  2. Alias dictionary lookup
  3. Conservative fallback: unknown mentions stay distinct

No embeddings. No probabilities. Deterministic.
"""

from __future__ import annotations

import unicodedata

from axiomguard.models import Claim


# =====================================================================
# Default Alias Dictionary
# =====================================================================
# Users extend this with domain-specific aliases via add_aliases().
# Keys are stored in normalized form (lowercase, NFKC).

DEFAULT_ALIASES: dict[str, str] = {
    # --- Bangkok ---
    "bkk": "Bangkok",
    "กรุงเทพ": "Bangkok",
    "กรุงเทพมหานคร": "Bangkok",
    "กทม": "Bangkok",
    "กทม.": "Bangkok",
    "krung thep": "Bangkok",
    "krung thep maha nakhon": "Bangkok",
    # --- Chiang Mai ---
    "cnx": "Chiang Mai",
    "เชียงใหม่": "Chiang Mai",
    "chiangmai": "Chiang Mai",
    # --- Thailand ---
    "th": "Thailand",
    "ไทย": "Thailand",
    "ประเทศไทย": "Thailand",
    "siam": "Thailand",
    # --- Common entity synonyms ---
    "headquarters": "company",
    "hq": "company",
    "head office": "company",
    "main office": "company",
    "the firm": "company",
    "the organization": "company",
    "the organisation": "company",
    "ceo": "CEO",
    "chief executive": "CEO",
    "chief executive officer": "CEO",
    "cto": "CTO",
    "chief technology officer": "CTO",
    "cfo": "CFO",
    "chief financial officer": "CFO",
}


# =====================================================================
# EntityResolver
# =====================================================================


class EntityResolver:
    """Deterministic entity canonicalization for Z3 verification.

    Uses alias dictionaries only — no embeddings, no probabilities.
    Unknown mentions are treated as distinct entities (conservative default).

    Example::

        resolver = EntityResolver()
        resolver.resolve("BKK")          # ("Bangkok", True)
        resolver.resolve("กทม")          # ("Bangkok", True)
        resolver.resolve("Some Place")   # ("Some Place", False)

        # Add domain-specific aliases
        resolver.add_aliases({"สวนหลวง ร.9": "Suanluang Rama IX"})
    """

    def __init__(self, aliases: dict[str, str] | None = None) -> None:
        self._aliases: dict[str, str] = {
            _normalize(k): v for k, v in DEFAULT_ALIASES.items()
        }
        if aliases:
            self.add_aliases(aliases)

    def resolve(self, mention: str) -> tuple[str, bool]:
        """Resolve a mention to its canonical form.

        Returns:
            A tuple of (canonical_form, was_resolved).
            If was_resolved is False, the stripped original is returned
            and should be treated as a distinct entity in Z3.
        """
        normalized = _normalize(mention)
        if normalized in self._aliases:
            return self._aliases[normalized], True
        return mention.strip(), False

    def add_aliases(self, aliases: dict[str, str]) -> None:
        """Add domain-specific aliases at runtime.

        Args:
            aliases: Mapping of surface forms to canonical names.
                     Keys are normalized automatically.
        """
        for key, canonical in aliases.items():
            self._aliases[_normalize(key)] = canonical

    def resolve_claim(self, claim: Claim) -> tuple[Claim, list[str]]:
        """Resolve subject and object entities in a Claim.

        Returns:
            A tuple of (resolved_claim, warnings).
            Warnings list unresolved entities for transparency.
        """
        warnings: list[str] = []

        subject, subj_hit = self.resolve(claim.subject)
        obj, obj_hit = self.resolve(claim.object)

        if not subj_hit and not _looks_canonical(claim.subject):
            warnings.append(f"Unresolved subject: '{claim.subject}'")
        if not obj_hit and not _looks_canonical(claim.object):
            warnings.append(f"Unresolved object: '{claim.object}'")

        resolved = claim.model_copy(update={"subject": subject, "object": obj})
        return resolved, warnings

    def resolve_claims(self, claims: list[Claim]) -> tuple[list[Claim], list[str]]:
        """Resolve entities across a list of Claims.

        Returns:
            (resolved_claims, all_warnings)
        """
        resolved: list[Claim] = []
        all_warnings: list[str] = []
        for claim in claims:
            r, w = self.resolve_claim(claim)
            resolved.append(r)
            all_warnings.extend(w)
        return resolved, all_warnings


# =====================================================================
# Module-level helpers
# =====================================================================


def _normalize(text: str) -> str:
    """Unicode NFKC normalize + lowercase + strip."""
    return unicodedata.normalize("NFKC", text.strip().lower())


def _looks_canonical(text: str) -> bool:
    """Heuristic: short terms or proper nouns are likely canonical already.

    We consider something "canonical enough" if:
    - It's a single word (e.g., "company", "Bangkok", "CEO")
    - It's 2 words and looks like a proper noun (e.g., "Dr. Somchai")
    """
    stripped = text.strip()
    words = stripped.split()
    if len(words) <= 2:
        return True
    return False
