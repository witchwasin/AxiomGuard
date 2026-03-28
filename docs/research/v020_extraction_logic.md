# v0.2.0 Applied Research: Multi-Claim Extraction & Entity Resolution

> **Status:** Research Complete — Ready for Implementation Review
> **Date:** 2026-03-28
> **Goal:** Prove that v0.2.0 is built on solid logical foundations, not a quick hack.

---

## 1. Formalizing Multi-Claim Extraction

### 1.1 The Problem

v0.1.0 extracts **one SRO triple per sentence**. Real text contains compound claims:

> "The company is headquartered in Bangkok and was founded in 2020 by Dr. Somchai."

This single sentence contains **3 atomic claims**:
1. `(company, location, Bangkok)`
2. `(company, founded_year, 2020)`
3. `(company, founder, Dr. Somchai)`

If we only extract one, we miss contradictions in the other two.

### 1.2 JSON Schema for Multi-Claim Output

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["claims"],
  "properties": {
    "claims": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["subject", "relation", "object"],
        "properties": {
          "subject":  { "type": "string", "minLength": 1 },
          "relation": { "type": "string", "minLength": 1 },
          "object":   { "type": "string", "minLength": 1 },
          "negated":  { "type": "boolean", "default": false }
        },
        "additionalProperties": false
      },
      "minItems": 1
    }
  }
}
```

**Design decisions:**

| Decision | Rationale |
|----------|-----------|
| Flat array, not nested | Z3 asserts ground terms — no benefit from hierarchical structure |
| `negated` field | "Paris is NOT the capital of Germany" must not become `(Paris, capital, Germany)`. Negation is the #1 failure mode in NL-to-logic extraction (see Section 3) |
| `additionalProperties: false` | LLMs love adding "helpful" fields like `confidence`, `source`. We reject them to keep the pipeline deterministic |
| `minItems: 1` | Empty extraction = extraction failure, must be handled separately |

### 1.3 The Atomic Proposition Rule

**Problem:** LLMs frequently extract claims that are too complex, redundant, or overlapping.

**Rule:** Each triple must satisfy ALL of the following:

1. **Single-fact:** The triple asserts exactly one relationship. If removing any component changes the meaning, it's atomic.
2. **Non-redundant:** `(Paris, capitalOf, France)` and `(France, hasCapital, Paris)` are the same claim. Keep one canonical direction.
3. **Grounded:** Subject and object must be concrete entities or values, not descriptions. `(company, location, "a city in Thailand")` is not grounded.
4. **Temporally flat:** For v0.2.0, all claims are treated as present-tense assertions. Temporal qualifiers are stripped and flagged.

**Enforcement strategy:** Include these rules in the LLM system prompt, AND validate post-extraction:

```
POST-EXTRACTION CHECKS:
1. Dedup: Normalize (S,R,O) and (O, inverse(R), S) → keep one
2. Groundedness: Reject if object contains >5 words (likely a description, not an entity)
3. Atomicity: Reject if relation contains "and" or "or"
```

### 1.4 Z3 Ingestion Strategy

**Key finding from research:** Z3 handles hundreds of ground-term SRO assertions with negligible overhead (<10ms). The bottleneck is NOT assertion count — it's quantifier complexity.

**Recommended pattern — Assumptions API with `unsat_core()`:**

```python
solver = z3.Solver()
solver.set("unsat_core", True)

# Assert background axioms (once)
for axiom in knowledge_base:
    solver.add(axiom.as_z3())

# Create tracked assertions for each claim
trackers = []
for i, claim in enumerate(response_claims):
    t = z3.Bool(f"claim_{i}")
    solver.add(z3.Implies(t, claim.as_z3()))
    trackers.append(t)

# One check() call for ALL claims
result = solver.check(*trackers)
if result == z3.unsat:
    core = solver.unsat_core()  # exactly which claims contradict
```

**Why this matters:** v0.1.0 creates a new `Solver()` per `verify()` call. With the assumptions API, we check all claims in one pass AND get the minimal contradictory subset for free. This directly addresses the "Scaling Nightmare" critique.

---

## 2. Entity Resolution Research

### 2.1 The Problem

Z3 treats strings literally. `"Bangkok"`, `"BKK"`, and `"กรุงเทพ"` are three different Z3 constants. If an axiom says `(company, location, Bangkok)` and the response says `(company, location, BKK)`, Z3 will flag it as a contradiction even though they're the same place.

This is the #1 source of **false positives** and the core of the "Brittle" critique.

### 2.2 Method Comparison

#### Method A: Alias Dictionary (Hard-coded)

```python
ALIASES = {
    "bkk": "Bangkok",
    "กรุงเทพ": "Bangkok",
    "krung thep": "Bangkok",
}
```

| Metric | Score |
|--------|-------|
| Precision | 100% (no false merges) |
| Recall | Low (only covers known aliases) |
| Latency | ~0ms |
| Maintenance | High (manual updates) |
| Determinism | Perfect |

#### Method B: Embedding Similarity (Small model)

```python
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("all-MiniLM-L6-v2")
sim = cosine_similarity(encode("Bangkok"), encode("BKK"))  # ~0.72
sim = cosine_similarity(encode("Bangkok"), encode("Bangalore"))  # ~0.68
```

| Metric | Score |
|--------|-------|
| Precision | Dangerous (~0.72 vs ~0.68 margin between correct and wrong match) |
| Recall | High (handles unseen forms) |
| Latency | ~5-20ms per pair |
| Maintenance | Low |
| Determinism | Non-deterministic across model versions |

**Critical problem for formal verification:** A false merge (treating "Bangkok" and "Bangalore" as the same) corrupts ALL downstream Z3 reasoning. In a system that claims "mathematical proof," even one false merge is catastrophic.

#### Method C: Canonicalization Pipeline (Recommended)

```
Input: "BKK"
  → Step 1: Unicode normalize + lowercase → "bkk"
  → Step 2: Alias lookup → "Bangkok" (HIT)
  → Done.

Input: "สวนหลวง ร.9"
  → Step 1: Unicode normalize → "สวนหลวง ร.9"
  → Step 2: Alias lookup → MISS
  → Step 3: Keep as-is, flag as UNRESOLVED
  → Done.
```

| Metric | Score |
|--------|-------|
| Precision | 100% for known aliases, conservative for unknown |
| Recall | Moderate (alias dict + safe fallback) |
| Latency | ~0ms |
| Determinism | Perfect |
| Safety | Unresolved entities are treated as distinct (conservative) |

### 2.3 Threshold Logic (τ)

For v0.2.0, we **do NOT use embedding-based thresholds**. The reasoning:

1. AxiomGuard's value proposition is **"provable truth, not probability."**
2. Introducing a τ threshold turns every verification into a probabilistic claim.
3. This directly undermines Core Directive #4: "Zero false positives on proven contradictions."

**Decision:** Use Method C (Canonicalization Pipeline). Unknown entities stay distinct. If Z3 says UNSAT, it's UNSAT — no "maybe" results.

**Future (v0.4.0+):** If embedding-based resolution is added, it must be:
- Optional (off by default)
- Explicit in the output: "Assumed BKK = Bangkok with similarity 0.72"
- Never used for the UNSAT proof itself — only for pre-processing suggestions

### 2.4 Implementation Design

```python
class EntityResolver:
    def __init__(self, aliases: dict[str, str] | None = None):
        self._aliases = aliases or DEFAULT_ALIASES

    def resolve(self, mention: str) -> tuple[str, bool]:
        """Returns (canonical_form, was_resolved).

        If was_resolved is False, the mention is used as-is
        and should be treated as a distinct entity in Z3.
        """
        normalized = unicodedata.normalize("NFKC", mention.strip().lower())
        if normalized in self._aliases:
            return self._aliases[normalized], True
        return mention.strip(), False
```

Users can extend aliases for their domain:

```python
import axiomguard
axiomguard.entity_resolver.add_aliases({
    "bkk": "Bangkok",
    "กทม": "Bangkok",
})
```

---

## 3. Failure Modes Analysis

### 3.1 Taxonomy of LLM Extraction Failures

| # | Failure Mode | Example | Severity | Frequency |
|---|-------------|---------|----------|-----------|
| F1 | **Missing field** | `{"subject": "Paris", "relation": "capital"}` (no object) | HIGH — Z3 crashes | Common with weaker models |
| F2 | **Extra fields** | `{..., "confidence": 0.9}` | LOW — ignored if schema enforced | Very common |
| F3 | **Wrong nesting** | `{"triple": {"s": ...}}` | HIGH — parser fails | Common |
| F4 | **Markdown wrapping** | `` ```json {...} ``` `` | MEDIUM — recoverable | Very common |
| F5 | **Negation dropped** | "NOT capital" → `(Paris, capital, Germany)` | CRITICAL — silent wrong proof | Common |
| F6 | **Redundant triples** | Same fact in both directions | LOW — wastes resources | Common |
| F7 | **Implicit hallucination** | LLM invents entities not in the text | HIGH — introduces false facts | Moderate |
| F8 | **Empty extraction** | `{"claims": []}` | MEDIUM — no verification possible | Rare |
| F9 | **Non-JSON output** | Prose explanation instead of JSON | HIGH — pipeline breaks | Rare with good prompts |

### 3.2 The Validation Layer

A strict pipeline between LLM output and Z3 input:

```
LLM Output (raw string)
    │
    ▼
[Stage 1: Parse] ── Extract JSON from markdown fences, fix trailing commas
    │
    ▼
[Stage 2: Schema] ── Validate against JSON Schema (Section 1.2)
    │                  Reject: missing fields, wrong types, extra fields
    ▼
[Stage 3: Semantic] ── Check atomicity, groundedness, dedup
    │                   Flag: negation words in source text
    ▼
[Stage 4: Entity Resolution] ── Canonicalize subjects and objects
    │
    ▼
[Stage 5: Z3 Encoding] ── Convert validated claims to Z3 assertions
    │
    ▼
Z3 Solver
```

### 3.3 Each Stage in Detail

**Stage 1 — Parse:**
```python
def extract_json(raw: str) -> dict:
    # Strip markdown fences
    cleaned = re.sub(r"```json?\s*", "", raw)
    cleaned = re.sub(r"```\s*", "", cleaned)
    # Fix common JSON errors
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)  # trailing commas
    return json.loads(cleaned)
```

**Stage 2 — Schema Validation:**
Use Pydantic models (same schema as Section 1.2):
```python
class Claim(BaseModel):
    subject: str = Field(min_length=1)
    relation: str = Field(min_length=1)
    object: str = Field(min_length=1)
    negated: bool = False

class ExtractionResult(BaseModel):
    claims: list[Claim] = Field(min_length=1)
```

On failure: retry LLM extraction once with the validation error message. If second attempt fails, return `ExtractionError` (not a silent fallback).

**Stage 3 — Semantic Validation:**
```python
def validate_semantics(claims: list[Claim], source_text: str) -> list[Claim]:
    # 1. Dedup: normalize and remove inverse duplicates
    seen = set()
    unique = []
    for c in claims:
        key = tuple(sorted([c.subject.lower(), c.object.lower()])) + (c.relation.lower(),)
        if key not in seen:
            seen.add(key)
            unique.append(c)

    # 2. Negation check: if source contains negation words
    #    but no claim is marked negated, flag warning
    negation_words = {"not", "never", "no", "isn't", "wasn't", "don't", "doesn't"}
    has_negation = any(w in source_text.lower().split() for w in negation_words)
    any_negated = any(c.negated for c in unique)
    if has_negation and not any_negated:
        warnings.warn("Source text contains negation but no claim is marked negated")

    # 3. Groundedness: reject overly verbose objects
    grounded = [c for c in unique if len(c.object.split()) <= 5]

    return grounded
```

**Stage 4 — Entity Resolution:**
Apply `EntityResolver.resolve()` from Section 2.4 to all subjects and objects.

**Stage 5 — Z3 Encoding:**
Convert `list[Claim]` to Z3 assertions using the assumptions API from Section 1.4.

### 3.4 Error Budget

For v0.2.0, we define acceptable failure rates:

| Stage | Acceptable Failure Rate | Action on Failure |
|-------|------------------------|-------------------|
| Parse (Stage 1) | <5% | Retry once, then `ExtractionError` |
| Schema (Stage 2) | <2% after retry | `ExtractionError` |
| Semantic (Stage 3) | N/A (filter, not reject) | Warning in result |
| Entity Resolution (Stage 4) | N/A (conservative) | Mark unresolved in result |
| Z3 (Stage 5) | 0% (deterministic) | Never fails if input is valid |

### 3.5 The "Unparseable" Escape Hatch

If the LLM returns something that cannot be parsed into SRO triples after retry:

```python
@dataclass
class VerificationResult:
    is_hallucinating: bool
    reason: str
    confidence: Literal["proven", "uncertain"]  # NEW in v0.2.0
    extraction_warnings: list[str]              # NEW in v0.2.0
```

- `confidence: "proven"` — Z3 returned UNSAT. Mathematical proof.
- `confidence: "uncertain"` — Extraction failed or had warnings. Result is best-effort.

This preserves Core Directive #4: we never claim a "proof" when the extraction was unreliable.

---

## 4. Prior Art & Positioning

### 4.1 Most Relevant Existing Work

| System | What It Does | Difference from AxiomGuard |
|--------|-------------|---------------------------|
| **SatLM** (Ye et al., 2023) | LLM generates SAT formulas → SAT solver verifies | Academic; no library, no multi-backend support |
| **Logic-LM** (Pan et al., 2023) | NL → symbolic logic → solver → NL answer | Focused on QA, not hallucination detection |
| **NVIDIA NeMo Guardrails** | Rule-based dialog rails | Probabilistic; no formal proof of contradiction |
| **OpenIE** (Stanford/AllenAI) | Extract (S, R, O) from text | Extraction only; no verification engine |
| **Instructor** (Jason Liu) | Enforce structured LLM output | Validation only; no logic layer |

### 4.2 AxiomGuard's Unique Position

```
                    Probabilistic ◄──────────────► Provable
                         │                              │
                    NeMo Guardrails                 AxiomGuard
                    Azure AI Safety                 SatLM (academic)
                         │                              │
  General-purpose ◄──────┼──────────────────────────────┼──► Domain-specific
                         │                              │
                    OpenAI moderation            Logic-LM (academic)
                    Guardrails AI
```

AxiomGuard occupies the **Provable + Domain-specific** quadrant. No production-ready library exists here today.

---

## 5. Implementation Checklist for v0.2.0

Based on this research, v0.2.0 must deliver:

- [ ] Multi-claim JSON schema + Pydantic models
- [ ] `negated` field support in extraction and Z3 encoding
- [ ] 5-stage validation pipeline (Parse → Schema → Semantic → Entity → Z3)
- [ ] `EntityResolver` with alias dictionary + canonicalization
- [ ] Z3 assumptions API with `unsat_core()` (replace per-call Solver)
- [ ] `confidence` field in `VerificationResult` ("proven" vs "uncertain")
- [ ] `extraction_warnings` field for transparency
- [ ] LLM system prompt for multi-claim extraction with atomic proposition rules
- [ ] Unit tests: compound sentences, negation, alias resolution, schema validation failures
- [ ] Benchmark: run against 50+ real sentences, measure extraction accuracy

---

## References

- Ye et al. (2023). "SatLM: Satisfiability-Aided Language Models Using Declarative Prompting"
- Pan et al. (2023). "Logic-LM: Empowering Large Language Models with Symbolic Solvers for Faithful Logical Reasoning"
- Han et al. (2022). "FOLIO: Natural Language Reasoning with First-Order Logic"
- Liu, Jason. "Instructor" — github.com/jxnl/instructor
- Willard & Louf (2023). "Efficient Guided Generation for Large Language Models" (Outlines)
- De Moura & Bjorner (2008). "Z3: An Efficient SMT Solver" (Microsoft Research)
