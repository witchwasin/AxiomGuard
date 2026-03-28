# v0.6.0 Applied Research: Negation, Temporal Logic & Smart Extraction

> **Status:** Design Complete — Ready for Implementation Review
> **Date:** 2026-03-28
> **Goal:** Handle real-world language complexity: negation ("must NOT"),
> time-bounded rules, smarter entity resolution, and extraction confidence.

---

## 1. Negation Rule Type

### 1.1 Problem

Currently, negation is only a **claim-level property** (`Claim.negated: bool`).
There is no way for a domain expert to declare "this entity must NOT have this value"
in YAML. Workarounds like synthetic values (`Penicillin_allergy`) are fragile.

### 1.2 YAML Syntax — Human-Readable

**Form A: Single forbidden value**

```yaml
- name: No penicillin for allergic patients
  type: negation
  entity: patient
  relation: medication
  must_not_include: Penicillin
  severity: error
  message: "Patient must NOT receive Penicillin."
```

**Form B: Multiple forbidden values**

```yaml
- name: Banned substances
  type: negation
  entity: employee
  relation: substance_test
  must_not_include:
    - Methamphetamine
    - Cocaine
    - Heroin
  severity: error
  message: "Employee tested positive for a banned substance."
```

**Form C: Conditional negation (dependency + forbid)**

```yaml
- name: Allergy cross-reactivity
  type: dependency
  when:
    entity: patient
    relation: allergy
    value: Penicillin
  then:
    forbid:
      relation: medication
      values: [Amoxicillin, Ampicillin, Cephalexin]
  severity: error
  message: "Penicillin-allergic patients must NOT receive beta-lactam antibiotics."
```

> **Design rationale:** `must_not_include` reads like English policy language.
> Non-programmers (HR, Legal, Medical) can write these without understanding Z3.

### 1.3 Pydantic Model

```python
class NegationRule(_RuleBase):
    """Prohibition rule: entity must NOT have these values."""

    type: Literal["negation"]
    entity: str = Field(min_length=1)
    relation: str = Field(min_length=1)
    must_not_include: list[str] = Field(min_length=1)

    @field_validator("must_not_include", mode="before")
    @classmethod
    def normalize_to_list(cls, v):
        if isinstance(v, str):
            return [v]
        return v
```

Extension to `ThenClause` for conditional negation:

```python
class ThenForbid(BaseModel):
    """What must NOT be true when condition is met."""
    relation: str = Field(min_length=1)
    values: list[str] = Field(min_length=1)

class ThenClause(BaseModel):
    require: Optional[ThenRequirement] = None
    forbid: Optional[ThenForbid] = None
```

Update discriminated union:

```python
Rule = Annotated[
    Union[UniqueRule, ExclusionRule, DependencyRule, RangeRule, NegationRule],
    Field(discriminator="type"),
]
```

### 1.4 Z3 Compilation

```python
def _compile_negation(self, rule: NegationRule) -> list[z3.ExprRef]:
    """negation → ForAll([s], Not(Relation(rel, s, forbidden)))"""
    R = self._Relation
    s = z3.Const("s", self._StringSort)
    rel = z3.StringVal(rule.relation)

    constraints = []
    for forbidden in rule.must_not_include:
        constraints.append(
            z3.ForAll([s], z3.Not(R(rel, s, z3.StringVal(forbidden))))
        )
    return constraints
```

For conditional `forbid` in dependency:

```python
# In _compile_dependency():
if rule.then.forbid:
    for val in rule.then.forbid.values:
        forbid_expr = z3.Not(R(z3.StringVal(rule.then.forbid.relation),
                               s, z3.StringVal(val)))
        constraints.append(z3.ForAll([s], z3.Implies(when_expr, forbid_expr)))
```

### 1.5 Test Cases

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Patient takes Paracetamol, rule forbids Penicillin | SAT |
| 2 | Patient takes Penicillin, rule forbids Penicillin | UNSAT |
| 3 | Employee tests Cocaine, rule forbids [Meth, Cocaine, Heroin] | UNSAT |
| 4 | Employee clean, rule forbids [Meth, Cocaine, Heroin] | SAT |
| 5 | Allergy=Penicillin + med=Amoxicillin (conditional forbid) | UNSAT |
| 6 | Allergy=Penicillin + med=Metformin (not in forbid list) | SAT |
| 7 | Allergy=Shellfish + med=Amoxicillin (condition not met) | SAT |
| 8 | Negation + Thai entity alias resolves correctly | SAT/UNSAT |
| 9 | Empty `must_not_include` → Pydantic validation error | Error |
| 10 | Violated negation appears in `violated_rules` | Metadata |

### 1.6 Implementation Checklist

- [ ] `NegationRule` Pydantic model → `parser.py`
- [ ] `ThenForbid` model + extend `ThenClause` → `parser.py`
- [ ] Update `Rule` union → `parser.py`
- [ ] `_compile_negation()` → `knowledge_base.py`
- [ ] Extend `_compile_dependency()` for `then.forbid` → `knowledge_base.py`
- [ ] Update `add_rule()` dispatch → `knowledge_base.py`
- [ ] Update `_match_violated_rules()` → `knowledge_base.py`
- [ ] Update `axiom_relations()` → `knowledge_base.py`
- [ ] `negation()` method → `RuleBuilder` in `rule_generator.py`
- [ ] Update `_RULE_GEN_PROMPT` → `rule_generator.py`
- [ ] 10+ tests → `tests/test_v060_negation.py`
- [ ] Example in `examples/medical_rules.axiom.yml`

---

## 2. Temporal Rules (Validity Windows)

### 2.1 Problem

Rules in AxiomGuard are currently **timeless** — they apply forever. Real-world
rules have effective dates: insurance policies expire, drug approvals have windows,
employment contracts have durations, regulations have sunset dates.

v0.4.0 added `value_type: "date"` for comparison operators, but there is no concept
of "this rule is only valid during a specific time period."

### 2.2 YAML Syntax — Human-Readable

**Form A: Validity window on any rule (mixin)**

```yaml
- name: 2025 insurance policy
  type: unique
  entity: policy
  relation: coverage_type
  valid_from: "2025-01-01"
  valid_until: "2025-12-31"
  severity: error
  message: "Policy coverage valid for 2025 only."
```

**Form B: Open-ended (no expiry)**

```yaml
- name: New regulation effective March 2026
  type: negation
  entity: company
  relation: practice
  must_not_include: third_party_data_sharing
  valid_from: "2026-03-01"
  severity: error
  message: "Data sharing banned from March 2026 onward."
```

**Form C: Temporal ordering (dedicated type)**

```yaml
- name: Treatment after diagnosis
  type: temporal
  entity: patient
  relation: treatment_date
  must_be_after: diagnosis_date
  severity: error
  message: "Treatment cannot start before diagnosis."
```

**Form D: Date ordering with fixed date**

```yaml
- name: Application deadline
  type: temporal
  entity: applicant
  relation: submission_date
  must_be_before: "2026-06-30"
  severity: error
  message: "Application must be submitted before June 30, 2026."
```

> **Design rationale:** `valid_from`/`valid_until` are standard business terms.
> `must_be_after`/`must_be_before` read like contract language.
> Any existing rule type can have a validity window — no need to rewrite rules.

### 2.3 Pydantic Model

Add validity window to `_RuleBase` (applies to ALL rule types):

```python
class _RuleBase(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    severity: Literal["error", "warning", "info"] = "error"
    message: str = ""
    examples: list[TestExample] = Field(default_factory=list)
    # v0.6.0: Temporal validity window
    valid_from: Optional[str] = None    # ISO 8601 date
    valid_until: Optional[str] = None   # ISO 8601 date
```

New dedicated temporal ordering rule:

```python
class TemporalRule(_RuleBase):
    """Temporal ordering: date relation must be before/after another."""

    type: Literal["temporal"]
    entity: str = Field(min_length=1)
    relation: str = Field(min_length=1)
    must_be_after: Optional[str] = None    # relation name or ISO date
    must_be_before: Optional[str] = None   # relation name or ISO date
```

### 2.4 Z3 Compilation & Runtime Filtering

**Validity windows — runtime filter (not compile-time):**

```python
def verify(self, response_claims, axiom_claims=None,
           timeout_ms=2000, reference_date=None):
    ref = reference_date or date.today()

    # Filter to active rules only
    active_constraints = []
    for constraint, meta in zip(self._constraints, self._rule_meta):
        if self._is_active(meta, ref):
            active_constraints.append(constraint)

    solver = z3.Solver()
    for c in active_constraints:
        solver.add(c)
    # ... rest of verify()
```

```python
def _is_active(self, meta: dict, ref: date) -> bool:
    vf = meta.get("valid_from")
    vu = meta.get("valid_until")
    if vf and ref < date.fromisoformat(vf):
        return False  # not yet active
    if vu and ref > date.fromisoformat(vu):
        return False  # expired
    return True
```

**Temporal ordering — Z3 date comparison:**

```python
def _compile_temporal(self, rule: TemporalRule) -> list[z3.ExprRef]:
    s = z3.Const("s", self._StringSort)

    if rule.must_be_after:
        attr_a = self._get_numeric_attr(rule.relation, "date")
        # Check if it's a relation name or fixed date
        try:
            fixed = date.fromisoformat(rule.must_be_after).toordinal()
            return [z3.ForAll([s], attr_a(s) > z3.IntVal(fixed))]
        except ValueError:
            attr_b = self._get_numeric_attr(rule.must_be_after, "date")
            return [z3.ForAll([s], attr_a(s) > attr_b(s))]

    # Similar for must_be_before
```

> **Why runtime filter?** The same KnowledgeBase can verify claims at
> different dates without reloading rules. Just pass `reference_date`.

### 2.5 Test Cases

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Rule active, claim violates → UNSAT | UNSAT |
| 2 | Rule active, claim satisfies → SAT | SAT |
| 3 | Rule expired (valid_until past), claim violates → SAT (skipped) | SAT |
| 4 | Rule not yet active (valid_from future) → SAT (skipped) | SAT |
| 5 | No window → always active | UNSAT/SAT |
| 6 | Open-ended start (valid_until only) | Active before deadline |
| 7 | Open-ended end (valid_from only) | Active after start |
| 8 | treatment_date must_be_after diagnosis_date → correct order | SAT |
| 9 | treatment_date must_be_after diagnosis_date → wrong order | UNSAT |
| 10 | must_be_before fixed date "2026-06-30" | SAT/UNSAT |
| 11 | Custom reference_date changes result | Verified |

### 2.6 Implementation Checklist

- [ ] Add `valid_from`/`valid_until` to `_RuleBase` → `parser.py`
- [ ] Date format validator for validity fields → `parser.py`
- [ ] `TemporalRule` model → `parser.py`
- [ ] Update `Rule` union → `parser.py`
- [ ] Store `valid_from`/`valid_until` in rule metadata → `knowledge_base.py`
- [ ] Add `reference_date` param to `verify()` → `knowledge_base.py`
- [ ] Implement `_is_active()` filter → `knowledge_base.py`
- [ ] `_compile_temporal()` → `knowledge_base.py`
- [ ] Pass `reference_date` through `verify_with_kb()` → `core.py`
- [ ] `temporal()` method → `RuleBuilder`
- [ ] Update `_RULE_GEN_PROMPT` → `rule_generator.py`
- [ ] 11+ tests → `tests/test_v060_temporal.py`

---

## 3. Advanced Entity Normalization

### 3.1 Problem

`EntityResolver` uses exact alias lookup only. "Dr. Smith" ≠ "Smith",
"Bangkok Metropolitan" ≠ "Bangkok" unless explicitly aliased.

### 3.2 Three Normalization Levels

| Level | Name | What it does | Deterministic? |
|-------|------|-------------|:--------------:|
| 1 | `strict` | NFKC + lowercase + strip + exact alias (current) | Yes |
| 2 | `enhanced` | + strip titles/articles/suffixes + collapse whitespace | Yes |
| 3 | `aggressive` | + Thai romanization table + abbreviation expansion | Yes |

**All levels are 100% deterministic — no ML, no thresholds, no probabilities.**

### 3.3 YAML Configuration

```yaml
axiomguard: "0.6"
domain: medical
normalization: enhanced    # "strict" | "enhanced" | "aggressive"

entities:
  - name: patient
    aliases: ["ผู้ป่วย", "pt"]
```

### 3.4 Dictionaries

```python
_TITLES = {
    # English
    "dr", "dr.", "mr", "mr.", "mrs", "mrs.", "ms", "ms.",
    "prof", "prof.", "sir", "dame",
    # Thai
    "นพ", "นพ.", "พญ", "พญ.", "ดร", "ดร.",
    "ศ", "ศ.", "รศ", "รศ.", "ผศ", "ผศ.",
    "นาย", "นาง", "นางสาว",
}

_ARTICLES = {"the", "a", "an"}

_SUFFIXES = {
    "ltd", "ltd.", "co", "co.", "inc", "inc.",
    "corp", "corp.", "plc", "llc",
    "จำกัด", "มหาชน", "บริษัท",
}
```

### 3.5 Implementation

```python
class EntityResolver:
    def __init__(self, aliases=None,
                 normalization: Literal["strict", "enhanced", "aggressive"] = "strict"):
        self._normalization = normalization

    def _normalize_enhanced(self, text: str) -> str:
        text = _normalize(text)          # Level 1
        text = _strip_titles(text)       # "Dr. Smith" → "smith"
        text = _strip_articles(text)     # "the patient" → "patient"
        text = _strip_suffixes(text)     # "ACME Corp." → "acme"
        text = _collapse_whitespace(text)
        return text
```

### 3.6 Test Cases

| # | Input | Level | Output |
|---|-------|-------|--------|
| 1 | "Dr. Smith" | enhanced | "smith" |
| 2 | "Dr Smith" | enhanced | "smith" |
| 3 | "the patient" | enhanced | "patient" |
| 4 | "ACME Corp." | enhanced | "acme" |
| 5 | "นพ.สมชาย" | enhanced | "สมชาย" |
| 6 | "Dr. Smith" | strict | "dr. smith" (unchanged) |
| 7 | "บริษัท AxiomGuard จำกัด" | enhanced | "axiomguard" |

### 3.7 Implementation Checklist

- [ ] Add `normalization` param to `EntityResolver.__init__()`
- [ ] Implement `_strip_titles()`, `_strip_articles()`, `_strip_suffixes()`
- [ ] Thai title/suffix dictionaries
- [ ] `_normalize_enhanced()` method
- [ ] Add `normalization` field to `RuleSet` model → `parser.py`
- [ ] Wire through `KnowledgeBase._integrate()`
- [ ] 10+ tests → `tests/test_v060_normalization.py`
- [ ] Backward compatible (default = `strict`)

---

## 4. Confidence Scoring

### 4.1 Problem

All claims are treated equally in Z3 — a firm fact and a hedged guess get the same
weight. "The company IS in Bangkok" and "The company MAY be in Bangkok" both
become the same SRO triple.

### 4.2 Design

Add `confidence: float` to `Claim` (default 1.0 — fully backward compatible):

```python
class Claim(BaseModel):
    subject: str
    relation: str
    object: str
    negated: bool = False
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
```

**Pre-filter in verify():**

```python
def verify(self, response_claims, axiom_claims=None,
           min_confidence=0.0, ...):
    verifiable = [c for c in response_claims if c.confidence >= min_confidence]
    skipped = [c for c in response_claims if c.confidence < min_confidence]
    # Z3 only sees verifiable claims
```

**Hedge word detection (deterministic):**

```python
_HEDGE_WORDS = frozenset({
    "may", "might", "possibly", "perhaps", "reportedly",
    "allegedly", "supposedly", "could", "likely",
    "อาจจะ", "น่าจะ", "คาดว่า", "เป็นไปได้ว่า",
})
```

Claims from sentences containing hedge words get `confidence = 0.6` (configurable).

### 4.3 YAML Configuration

```yaml
axiomguard: "0.6"
domain: medical
confidence_threshold: 0.7    # global: ignore claims below 70%

rules:
  - name: Blood type
    type: unique
    entity: patient
    relation: blood_type
    min_confidence: 0.9    # per-rule: only high-confidence claims
```

### 4.4 Test Cases

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Default confidence 1.0 → all pass through | Backward compat |
| 2 | confidence=0.3, threshold=0.5 → skipped | Filtered |
| 3 | confidence=0.9, threshold=0.5 → verified | Normal |
| 4 | Mixed confidence, only some above threshold | Partial |
| 5 | threshold=0.0 → all pass (default) | Backward compat |
| 6 | "may be in Bangkok" → confidence < 1.0 | Hedge detected |

### 4.5 Implementation Checklist

- [ ] Add `confidence: float` to `Claim` → `models.py`
- [ ] Add `min_confidence` param to `verify()` → `knowledge_base.py`
- [ ] Pre-filter logic → `knowledge_base.py`
- [ ] Hedge word detector → `backends/__init__.py` or new `confidence.py`
- [ ] `confidence_threshold` in `RuleSet` → `parser.py`
- [ ] `min_confidence` in `_RuleBase` → `parser.py`
- [ ] Pass through `verify_with_kb()` → `core.py`
- [ ] 6+ tests → `tests/test_v060_confidence.py`
- [ ] Backward compat: default confidence=1.0, threshold=0.0

---

## 5. Multi-Platform Documentation

### 5.1 Problem

Current docs only show `export` (Unix). Windows users are left guessing.

### 5.2 Installation + API Key Setup

**Install:**

```bash
# All platforms
pip install axiomguard

# macOS — if pip not found
pip3 install axiomguard

# Windows — if pip not in PATH
python -m pip install axiomguard
```

**API Key Setup:**

```bash
# macOS / Linux
export ANTHROPIC_API_KEY="sk-ant-..."

# Windows (CMD)
set ANTHROPIC_API_KEY=sk-ant-...

# Windows (PowerShell)
$env:ANTHROPIC_API_KEY="sk-ant-..."
```

**Docker:**

```dockerfile
FROM python:3.12-slim
RUN pip install axiomguard
COPY rules/ /app/rules/
WORKDIR /app
```

### 5.3 Implementation Checklist

- [ ] Update `README.md` Installation + API Key sections
- [ ] Update `docs/site/getting-started/installation.md`
- [ ] Update `docs/site/getting-started/api-keys.md`
- [ ] Add Docker quickstart section
- [ ] Add troubleshooting section for z3-solver build issues

---

## 6. Implementation Order

```
Phase 1 (Foundation):
  └── Confidence scoring on Claim model (additive, backward-compat)

Phase 2 (Core — parallelizable):
  ├── 2a: Negation rule type (parser + knowledge_base)
  ├── 2b: Temporal rules (parser + knowledge_base)
  └── 2c: Advanced normalization (resolver)

Phase 3 (Integration):
  └── Wire through core.py, rule_generator.py, integration.py

Phase 4 (Quality):
  └── Tests (~40 new), examples, documentation

Phase 5 (Release):
  └── Version bump 0.6.0, CHANGELOG, PyPI publish
```

---

## 7. Backward Compatibility

| Feature | Breaking? | Migration |
|---------|:---------:|-----------|
| Negation rule type | No | New type, existing rules unaffected |
| `valid_from`/`valid_until` | No | Optional fields, default = always active |
| `reference_date` param | No | Optional, default = today |
| Normalization levels | No | Default = `strict` (current behavior) |
| `Claim.confidence` | No | Default = 1.0, threshold = 0.0 |
| `then.forbid` in dependency | No | Optional, `require` still works |
| Multi-platform docs | No | Documentation only |

**Zero breaking changes.** All defaults preserve v0.5.1 behavior exactly.
