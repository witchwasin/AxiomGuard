# v0.7.0 Applied Research: Tournament-Style Rule Derivation

> **Status:** Design Complete — Ready for Implementation Review
> **Date:** 2026-03-29
> **Goal:** Solve the "blank-page problem" of BYOR by generating competing
> candidate rules from source documents, surfacing conflicts via Z3, and
> letting humans arbitrate — so the human reviews rather than authors.
> **Academic Foundation:** Resnik (2025), "Large Language Models Are Biased
> Because They Are Large Language Models", *Computational Linguistics*.

---

## 1. Problem Statement

### 1.1 The Blank-Page Problem

BYOR (Bring Your Own Rules) is AxiomGuard's core philosophy: domain experts
write YAML rules, Z3 enforces them. But in practice, domain experts face a
cold-start problem:

- They know their domain but not YAML syntax
- They miss edge cases when writing from scratch
- `generate_rules()` (Mode 2) helps, but it is **single-shot** — one LLM call,
  one set of rules, no way to know what was missed

### 1.2 The Resnik Insight

Resnik (2025) argues that bias in LLMs is **structural** — baked into the
representation space by training on human-generated text. Key implications:

1. **A single LLM extraction will inherit the LLM's blind spots.** Asking once
   from one angle produces rules shaped by whatever biases that angle triggers.
2. **LLMs cannot distinguish definitional vs. contingent vs. normatively
   unacceptable patterns.** A single-shot extraction will mix all three.
3. **RLHF does not fix underlying representations.** The LLM may generate
   surface-level "fair" rules while missing structural biases.

**Conclusion:** Single-shot rule generation is fundamentally limited. We need
a process that **deliberately extracts from multiple angles**, surfaces the
conflicts, and lets humans make normative decisions.

### 1.3 Why Tournament?

Instead of trusting one LLM response, pit multiple extraction strategies
against each other. The LLM stays in the **untrusted zone** (candidate
generator), Z3 handles **conflict detection** (mathematical proof), and
humans remain the **final authority** (normative judgment).

This is not debiasing. This is **making bias visible so humans can act on it**.

---

## 2. Architecture

### 2.1 Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Tournament Rule Derivation                        │
│                                                                     │
│  Source Document (policy PDF, guideline, regulation)                 │
│      │                                                              │
│      ▼                                                              │
│  ┌───────────────────────────────────────────┐                      │
│  │ PHASE 1: Multi-Strategy Candidate Gen     │  ← LLM (untrusted)  │
│  │                                           │                      │
│  │  Strategy A: Constraints  → 8 candidates  │                      │
│  │  Strategy B: Exceptions   → 5 candidates  │                      │
│  │  Strategy C: Definitions  → 4 candidates  │                      │
│  │  Strategy D: Boundaries   → 6 candidates  │                      │
│  │  Strategy E: Adversarial  → 7 candidates  │                      │
│  │                            ────────────   │                      │
│  │                            30 total        │                      │
│  └──────────────┬────────────────────────────┘                      │
│                 │                                                    │
│                 ▼                                                    │
│  ┌───────────────────────────────────────────┐                      │
│  │ PHASE 2: Z3 Conflict Detection            │  ← Math (trusted)   │
│  │                                           │                      │
│  │  Pairwise check: C(30,2) = 435 pairs     │                      │
│  │  → 4 contradictions found                 │                      │
│  │  → 3 redundancies found                   │                      │
│  │  → 2 subsumptions found                   │                      │
│  │  → 21 standalone (no conflict)            │                      │
│  └──────────────┬────────────────────────────┘                      │
│                 │                                                    │
│                 ▼                                                    │
│  ┌───────────────────────────────────────────┐                      │
│  │ PHASE 3: Human Arbitration                │  ← Human (authority) │
│  │                                           │                      │
│  │  9 conflicts → human picks winners        │                      │
│  │  21 standalone → human batch approve/reject│                      │
│  │                                           │                      │
│  │  Result: 22 approved, 8 rejected          │                      │
│  └──────────────┬────────────────────────────┘                      │
│                 │                                                    │
│                 ▼                                                    │
│  ┌───────────────────────────────────────────┐                      │
│  │ PHASE 4: Export                           │                      │
│  │                                           │                      │
│  │  → .axiom.yml (approved rules)            │                      │
│  │  → KnowledgeBase (ready for verification) │                      │
│  │  → audit_trail.json (full decision log)   │                      │
│  └───────────────────────────────────────────┘                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Trust Model

```
┌──────────────────────────────────────────────────────────────┐
│ UNTRUSTED                TRUSTED              AUTHORITY       │
│                                                              │
│ LLM                      Z3 SMT Solver        Human          │
│ • Generates candidates   • Proves conflicts   • Picks winner │
│ • May hallucinate        • Deterministic       • Signs off    │
│ • Has structural bias    • No bias             • Audit trail  │
│ • Replaceable            • Replaceable         • Liable       │
│                                                              │
│ Output: suggestions      Output: proof         Output: rules  │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Phase 1: Multi-Strategy Candidate Generation

### 3.1 Strategy Definitions

Each strategy adds a **focus directive** to the base `_RULE_GEN_PROMPT`
from `rule_generator.py`. The same source document is sent to each strategy
with a different extraction lens.

| Strategy | Directive | What It Catches |
|----------|-----------|-----------------|
| `constraints` | Extract every MUST, SHALL, REQUIRED, MANDATORY, PROHIBITED | Hard requirements, prohibitions |
| `exceptions` | Extract every UNLESS, EXCEPT, PROVIDED THAT, NOTWITHSTANDING | Carve-outs that modify constraints |
| `definitions` | Extract every "X is defined as Y", "X means Y", "X refers to" | Entity boundaries, term scope |
| `boundaries` | Extract every number, date, percentage, threshold, limit | Numeric constraints, deadlines |
| `adversarial` | "How could someone misinterpret this document? Write rules to prevent each misinterpretation." | Gaps, ambiguities, implicit assumptions |

### 3.2 Strategy Prompt Templates

**Base:** Reuses `_RULE_GEN_PROMPT` from `rule_generator.py` (rule type
definitions, YAML format, extraction guidelines).

**Strategy-specific suffix appended per call:**

```python
STRATEGY_DIRECTIVES = {
    "constraints": (
        "## Focus: Hard Constraints\n"
        "Extract ONLY rules that represent hard constraints — things that "
        "MUST or MUST NOT be true. Look for: must, shall, required, mandatory, "
        "prohibited, forbidden, never, always.\n"
        "Ignore soft preferences, recommendations, and optional items.\n"
        "Tag each rule name with prefix 'c_' (e.g., c_min_age)."
    ),
    "exceptions": (
        "## Focus: Exceptions & Carve-Outs\n"
        "Extract ONLY rules that represent exceptions to general rules. "
        "Look for: unless, except, provided that, notwithstanding, however, "
        "in the event that, special case, exemption.\n"
        "For each exception, also note which general rule it modifies.\n"
        "Tag each rule name with prefix 'x_' (e.g., x_guarantor_override)."
    ),
    "definitions": (
        "## Focus: Definitions & Scope\n"
        "Extract ONLY rules that define entities, establish boundaries, or "
        "clarify what terms mean. Look for: is defined as, means, refers to, "
        "includes, excludes, for the purpose of.\n"
        "Prefer 'unique' rules for single-value definitions.\n"
        "Tag each rule name with prefix 'd_' (e.g., d_applicant_scope)."
    ),
    "boundaries": (
        "## Focus: Numeric Boundaries\n"
        "Extract ONLY rules involving numbers, dates, percentages, amounts, "
        "durations, or quantities. Look for: minimum, maximum, at least, "
        "at most, no more than, within N days, percentage.\n"
        "Prefer 'range' rules for bounded values.\n"
        "Tag each rule name with prefix 'b_' (e.g., b_max_loan_amount)."
    ),
    "adversarial": (
        "## Focus: Adversarial — Misinterpretation Prevention\n"
        "Read the document and ask: 'How could a careless reader or a "
        "language model misinterpret this?' For each potential misreading, "
        "write a rule that would CATCH the incorrect interpretation.\n\n"
        "Examples of misinterpretations to look for:\n"
        "- Confusing similar terms (e.g., 'net' vs 'gross' salary)\n"
        "- Applying a rule to the wrong entity\n"
        "- Missing implicit prerequisites\n"
        "- Assuming optional steps are mandatory (or vice versa)\n"
        "- Ignoring date/version boundaries\n"
        "Tag each rule name with prefix 'a_' (e.g., a_net_vs_gross)."
    ),
}
```

### 3.3 Candidate Model

```python
class CandidateRule(BaseModel):
    """A rule generated by one strategy — not yet approved."""

    id: int                           # Auto-assigned index
    rule: Rule                        # The actual parsed rule (Pydantic)
    strategy: str                     # Which strategy generated it
    source_excerpt: str = ""          # Part of document this came from
    status: Literal[
        "pending",                    # Awaiting conflict check
        "in_conflict",                # Part of a conflict cluster
        "standalone",                 # No conflicts detected
        "approved",                   # Human approved
        "rejected",                   # Human rejected
        "merged",                     # Replaced by a rewrite
    ] = "pending"
```

### 3.4 Generation Flow

```python
def generate(self, llm_generate: Callable[[str], str]) -> None:
    """Generate candidates from all strategies."""
    for strategy_name, directive in STRATEGY_DIRECTIVES.items():
        if strategy_name not in self._strategies:
            continue

        prompt = (
            f"{_RULE_GEN_PROMPT}\n\n"
            f"{directive}\n\n"
            f"## Domain\n{self._domain}\n\n"
            f"## Source Document\n\n{self._source}\n\n"
            f"Generate the .axiom.yml file now. Return ONLY valid YAML."
        )

        raw = llm_generate(prompt)
        yaml_str = _clean_yaml_output(raw)

        try:
            _validate_yaml(yaml_str)
            ruleset = self._parser.load_string(yaml_str)
            for rule in ruleset.rules:
                self._candidates.append(CandidateRule(
                    id=len(self._candidates),
                    rule=rule,
                    strategy=strategy_name,
                ))
        except (ValueError, Exception) as e:
            self._generation_warnings.append(
                f"Strategy '{strategy_name}' produced invalid YAML: {e}"
            )
```

**Key design choice:** Each strategy call is independent — they can be
parallelized. 5 strategies = 5 LLM calls that can run concurrently.

---

## 4. Phase 2: Z3 Conflict Detection

### 4.1 Conflict Types

| Type | Z3 Signal | Meaning | Human Action |
|------|-----------|---------|--------------|
| **Contradiction** | UNSAT when both loaded | A and B cannot both be true | Pick winner, or rewrite |
| **Redundancy** | Removing B does not change satisfiability | A already covers what B says | Keep one, drop the other |
| **Subsumption** | A is strictly stronger than B | A implies B but B does not imply A | Keep A (stricter) or B (looser)? |
| **Gap** | Adversarial strategy found rule, others didn't | Area where no constraint strategy produced a rule | Confirm gap exists, add rule |

### 4.2 Pairwise Contradiction Check

The core algorithm uses `KnowledgeBase` internally:

```python
def _check_contradiction(
    self, rule_a: Rule, rule_b: Rule
) -> bool:
    """Check if two rules contradict each other using Z3.

    Approach: Create a minimal KB with both rules and a set of
    synthetic claims that exercise them. If UNSAT, they conflict.
    """
    kb = KnowledgeBase()
    kb.add_rule(rule_a)
    kb.add_rule(rule_b)

    # Generate synthetic claims that exercise both rules
    test_claims = self._synthetic_claims(rule_a, rule_b)

    result = kb.verify(
        response_claims=test_claims,
        axiom_claims=[],
        timeout_ms=500,
    )

    return result.is_hallucinating  # UNSAT = contradiction
```

### 4.3 Synthetic Claim Generation

To test if two rules conflict, we need claims that trigger both:

```python
def _synthetic_claims(self, rule_a: Rule, rule_b: Rule) -> list[Claim]:
    """Create minimal claims that exercise both rules simultaneously."""
    claims = []
    entity = "test_entity"

    for rule in (rule_a, rule_b):
        if isinstance(rule, UniqueRule):
            # Assert two different values to trigger uniqueness
            claims.append(Claim(subject=entity, relation=rule.relation, object="value_a"))
            claims.append(Claim(subject=entity, relation=rule.relation, object="value_b"))

        elif isinstance(rule, ExclusionRule):
            # Assert all excluded values
            for val in rule.values:
                claims.append(Claim(subject=entity, relation=rule.relation, object=val))

        elif isinstance(rule, DependencyRule):
            # Assert the 'when' condition but NOT the 'then' requirement
            claims.append(Claim(
                subject=entity,
                relation=rule.when.relation,
                object=rule.when.value,
            ))

        elif isinstance(rule, RangeRule):
            # Assert out-of-range value
            if rule.min is not None:
                claims.append(Claim(
                    subject=entity,
                    relation=rule.relation,
                    object=str(int(rule.min) - 1),
                ))

    return claims
```

### 4.4 Redundancy & Subsumption Detection

For redundancy, we check if removing one rule changes the verification
result across a test suite of claims:

```python
def _check_redundancy(self, rule_a: Rule, rule_b: Rule) -> str | None:
    """Check if one rule makes the other redundant.

    Returns:
        "a_subsumes_b" — A is strictly stronger, B can be dropped
        "b_subsumes_a" — B is strictly stronger, A can be dropped
        "equivalent"   — Both produce identical results
        None           — Neither subsumes the other
    """
    test_claims = self._exhaustive_claims(rule_a, rule_b)

    # Verify with only A
    kb_a = KnowledgeBase()
    kb_a.add_rule(rule_a)

    # Verify with only B
    kb_b = KnowledgeBase()
    kb_b.add_rule(rule_b)

    results_a = [kb_a.verify([c]).is_hallucinating for c in test_claims]
    results_b = [kb_b.verify([c]).is_hallucinating for c in test_claims]

    a_catches_all_b = all(
        a or not b for a, b in zip(results_a, results_b)
    )
    b_catches_all_a = all(
        b or not a for a, b in zip(results_a, results_b)
    )

    if results_a == results_b:
        return "equivalent"
    elif a_catches_all_b:
        return "a_subsumes_b"
    elif b_catches_all_a:
        return "b_subsumes_a"
    return None
```

### 4.5 Conflict Cluster Model

```python
class Conflict(BaseModel):
    """A group of candidates that interact with each other."""

    id: int
    type: Literal["contradiction", "redundancy", "subsumption", "gap"]
    candidate_ids: list[int]          # Indices into candidates list
    z3_result: str                    # "UNSAT" or subsumption type
    explanation: str                  # Human-readable summary
    resolution: ArbitrationDecision | None = None  # Filled by human
```

### 4.6 Full Conflict Detection Flow

```python
def detect_conflicts(self) -> list[Conflict]:
    """Run pairwise Z3 checks across all candidates."""
    conflicts = []

    # Group candidates by relation to reduce comparison space
    by_relation = self._group_by_relation()

    for relation, group in by_relation.items():
        for i, j in combinations(range(len(group)), 2):
            ca, cb = group[i], group[j]

            # Contradiction check
            if self._check_contradiction(ca.rule, cb.rule):
                conflicts.append(Conflict(
                    id=len(conflicts),
                    type="contradiction",
                    candidate_ids=[ca.id, cb.id],
                    z3_result="UNSAT",
                    explanation=(
                        f"'{ca.rule.name}' (strategy: {ca.strategy}) "
                        f"contradicts '{cb.rule.name}' (strategy: {cb.strategy}). "
                        f"Both cannot be true simultaneously."
                    ),
                ))
                ca.status = "in_conflict"
                cb.status = "in_conflict"
                continue

            # Redundancy check
            subsumption = self._check_redundancy(ca.rule, cb.rule)
            if subsumption:
                conflicts.append(Conflict(
                    id=len(conflicts),
                    type="redundancy" if subsumption == "equivalent" else "subsumption",
                    candidate_ids=[ca.id, cb.id],
                    z3_result=subsumption,
                    explanation=self._explain_subsumption(ca, cb, subsumption),
                ))
                ca.status = "in_conflict"
                cb.status = "in_conflict"

    # Mark non-conflicting as standalone
    for c in self._candidates:
        if c.status == "pending":
            c.status = "standalone"

    # Detect gaps (adversarial found, others didn't)
    adversarial_relations = {
        c.rule.relation for c in self._candidates if c.strategy == "adversarial"
    }
    other_relations = {
        c.rule.relation for c in self._candidates if c.strategy != "adversarial"
    }
    gaps = adversarial_relations - other_relations
    for rel in gaps:
        gap_candidates = [
            c for c in self._candidates
            if c.strategy == "adversarial" and c.rule.relation == rel
        ]
        conflicts.append(Conflict(
            id=len(conflicts),
            type="gap",
            candidate_ids=[c.id for c in gap_candidates],
            z3_result="N/A",
            explanation=(
                f"Adversarial strategy found rules for relation '{rel}' "
                f"that no other strategy produced. This may indicate a "
                f"gap in the document's explicit constraints."
            ),
        ))

    self._conflicts = conflicts
    return conflicts
```

**Optimization: Relation Grouping.** Rules about different relations cannot
contradict each other (a `unique` rule on `ceo` cannot conflict with a
`range` rule on `salary`). Grouping by relation reduces comparisons from
O(N^2) to O(sum of group_size^2), typically 10-20x fewer checks.

---

## 5. Phase 3: Human Arbitration

### 5.1 Arbitration Model

```python
class ArbitrationDecision(BaseModel):
    """A human's decision on a conflict."""

    conflict_id: int
    action: Literal[
        "pick_winner",    # One candidate wins
        "reject_both",    # Neither is correct
        "rewrite",        # Human writes a replacement
        "approve_both",   # Both are valid (for subsumption — keep both)
    ]
    winner_id: int | None = None      # For pick_winner
    rewrite_rule: dict | None = None  # For rewrite (raw YAML dict)
    reason: str                       # Why — audit trail
    decided_by: str = ""              # Who made the decision
    decided_at: str = ""              # ISO timestamp
```

### 5.2 Programmatic Arbitration API

```python
# Conflicts with Z3 proof
for conflict in tourney.conflicts():
    print(f"[{conflict.type}] {conflict.explanation}")

    for cid in conflict.candidate_ids:
        c = tourney.candidate(cid)
        print(f"  Candidate {cid} (strategy: {c.strategy}):")
        print(f"    {c.rule.name}: {c.rule.message}")

# Human decides
tourney.decide(
    conflict_id=0,
    action="pick_winner",
    winner_id=3,
    reason="Rule 3 aligns with พ.ร.บ. สินเชื่อ มาตรา 12",
)

tourney.decide(
    conflict_id=1,
    action="rewrite",
    rewrite_rule={
        "name": "combined_income_check",
        "type": "range",
        "entity": "applicant",
        "relation": "monthly_income",
        "value_type": "int",
        "min": 15000,
        "severity": "error",
        "message": "รายได้ขั้นต่ำ 15,000 บาท (ใช้รายได้สุทธิ ไม่ใช่รายได้รวม)",
    },
    reason="Both candidates confused net vs gross. Rewrote with clarification.",
)

# Standalone candidates — batch approve/reject
for c in tourney.standalone_candidates():
    tourney.approve(c.id)
    # or: tourney.reject(c.id, reason="Out of scope")
```

### 5.3 Arbitration UX Principles

1. **Conflicts first, standalone second.** Present conflicts that need
   judgment before the easy batch-approve step.
2. **Show source excerpt.** Each candidate should trace back to the
   document section it came from, so the human can verify.
3. **Show Z3 proof.** For contradictions, show WHY they conflict
   (which claims cause UNSAT), not just THAT they conflict.
4. **Default: reject.** Unapproved candidates do NOT become rules.
   This prevents rubber-stamping — the human must act.
5. **Full audit trail.** Every decision (including "approved without
   conflict") is logged with who, when, and why.

---

## 6. Phase 4: Export

### 6.1 Export Methods

```python
# Export to KnowledgeBase (ready for verification)
kb = tourney.to_knowledge_base()

# Export to YAML string
yaml_str = tourney.to_yaml()

# Export to file
tourney.to_file("rules/loan_policy.axiom.yml")

# Export audit trail
audit = tourney.audit_trail()
# → TournamentAudit with full decision log
```

### 6.2 Audit Trail Model

```python
class TournamentAudit(BaseModel):
    """Complete record of a tournament for compliance/review."""

    domain: str
    source_document_hash: str         # SHA-256 of source
    generated_at: str                 # ISO timestamp
    strategies_used: list[str]
    total_candidates: int
    total_conflicts: int
    approved_count: int
    rejected_count: int
    rewritten_count: int
    candidates: list[CandidateRule]   # All candidates with final status
    conflicts: list[Conflict]         # All conflicts with resolutions
    decisions: list[ArbitrationDecision]
    generation_warnings: list[str]
```

### 6.3 Generated YAML Header

Approved rules are exported with a header tracing their origin:

```yaml
# ═══════════════════════════════════════════════════════════
# Generated by AxiomGuard Tournament Mode
# Source: loan_policy_v3.pdf (SHA-256: a1b2c3...)
# Strategies: constraints, exceptions, boundaries, adversarial
# Candidates: 30 generated → 22 approved, 8 rejected
# Audit: tournament_audit_20260329.json
# ═══════════════════════════════════════════════════════════
axiomguard: "0.3"
domain: personal_loan

entities:
  - name: applicant
    aliases: ["ผู้กู้", "ลูกค้า", "ผู้สมัคร"]

rules:
  - name: c_min_employment
    type: dependency
    # ...
```

---

## 7. Full API Design

### 7.1 Tournament Class

```python
class Tournament:
    """Tournament-style rule derivation engine.

    Generates competing candidate rules from a source document using
    multiple extraction strategies, detects conflicts using Z3, and
    lets humans arbitrate to produce approved .axiom.yml rules.

    Example::

        tourney = Tournament(
            source="นโยบายสินเชื่อส่วนบุคคล...",
            domain="personal_loan",
        )

        tourney.generate(llm_generate=my_llm_fn)
        conflicts = tourney.detect_conflicts()

        for conflict in conflicts:
            tourney.decide(conflict.id, action="pick_winner", winner_id=0)

        for c in tourney.standalone_candidates():
            tourney.approve(c.id)

        kb = tourney.to_knowledge_base()
    """

    def __init__(
        self,
        source: str,
        domain: str = "tournament",
        strategies: list[str] | None = None,
    ) -> None: ...

    # Phase 1
    def generate(
        self,
        llm_generate: Callable[[str], str],
        parallel: bool = False,
    ) -> None: ...

    # Phase 2
    def detect_conflicts(self) -> list[Conflict]: ...

    # Phase 3
    def decide(
        self,
        conflict_id: int,
        action: str,
        winner_id: int | None = None,
        rewrite_rule: dict | None = None,
        reason: str = "",
    ) -> None: ...

    def approve(self, candidate_id: int) -> None: ...
    def reject(self, candidate_id: int, reason: str = "") -> None: ...

    # Phase 4
    def to_knowledge_base(self) -> KnowledgeBase: ...
    def to_yaml(self) -> str: ...
    def to_file(self, path: str | Path) -> Path: ...
    def audit_trail(self) -> TournamentAudit: ...

    # Accessors
    @property
    def candidate_count(self) -> int: ...
    def candidate(self, id: int) -> CandidateRule: ...
    def candidates(self, status: str | None = None) -> list[CandidateRule]: ...
    def standalone_candidates(self) -> list[CandidateRule]: ...
    def conflicts(self) -> list[Conflict]: ...

    # Stats
    def summary(self) -> dict: ...
```

---

## 8. Worked Example: Thai Personal Loan Policy

### 8.1 Source Document

```text
นโยบายสินเชื่อส่วนบุคคล (ฉบับที่ 3/2569)

1. คุณสมบัติผู้กู้
   1.1 อายุ 20-60 ปี
   1.2 สัญชาติไทย หรือมีใบอนุญาตทำงานที่ยังไม่หมดอายุ
   1.3 รายได้ขั้นต่ำ 15,000 บาท/เดือน (รายได้สุทธิ)
   1.4 อายุงานขั้นต่ำ 6 เดือน ณ ที่ทำงานปัจจุบัน

2. เงื่อนไขสินเชื่อ
   2.1 วงเงินไม่เกิน 5 เท่าของรายได้ต่อเดือน
   2.2 ระยะเวลาผ่อนชำระ 12-60 เดือน
   2.3 อัตราดอกเบี้ย 8-15% ต่อปี

3. เอกสารประกอบ
   3.1 บัตรประชาชน
   3.2 สลิปเงินเดือน 3 เดือนล่าสุด
   3.3 Statement ย้อนหลัง 6 เดือน

4. ข้อยกเว้น
   4.1 กรณีมีผู้ค้ำประกันที่มีรายได้ >= 30,000 บาท ลดอายุงานขั้นต่ำเป็น 3 เดือน
   4.2 พนักงานธนาคาร: ยกเว้นข้อ 1.4 (อายุงาน)

5. ข้อห้าม
   5.1 ห้ามอนุมัติผู้กู้ที่มีประวัติค้างชำระเกิน 90 วัน
   5.2 ห้ามอนุมัติสินเชื่อ 2 สัญญาพร้อมกัน
```

### 8.2 Strategy Results (Illustrative)

**Strategy: constraints** → 8 candidates
```yaml
- name: c_age_range
  type: range
  entity: applicant
  relation: age
  value_type: int
  min: 20
  max: 60
  message: "ผู้กู้ต้องมีอายุ 20-60 ปี"

- name: c_min_income
  type: range
  entity: applicant
  relation: monthly_income
  value_type: int
  min: 15000
  message: "รายได้ขั้นต่ำ 15,000 บาท/เดือน"

- name: c_min_employment
  type: range
  entity: applicant
  relation: employment_months
  value_type: int
  min: 6
  message: "อายุงานขั้นต่ำ 6 เดือน"

- name: c_no_delinquency
  type: dependency
  when:
    entity: applicant
    relation: delinquency_days
    value: "90"
    value_type: int
    operator: ">"
  then:
    require:
      relation: approval_status
      value: rejected
  message: "ห้ามอนุมัติผู้กู้ที่ค้างชำระเกิน 90 วัน"
# ... 4 more
```

**Strategy: exceptions** → 3 candidates
```yaml
- name: x_guarantor_override
  type: range
  entity: applicant
  relation: employment_months
  value_type: int
  min: 3
  message: "กรณีมีผู้ค้ำประกัน (รายได้ >= 30,000) ลดอายุงานขั้นต่ำเป็น 3 เดือน"

- name: x_bank_employee_exempt
  type: dependency
  when:
    entity: applicant
    relation: employer_type
    value: bank_employee
  then:
    require:
      relation: employment_waiver
      value: "true"
  message: "พนักงานธนาคาร: ยกเว้นเงื่อนไขอายุงาน"
# ... 1 more
```

**Strategy: adversarial** → 4 candidates
```yaml
- name: a_net_vs_gross
  type: unique
  entity: applicant
  relation: income_type
  value: net
  message: "ใช้รายได้สุทธิเท่านั้น (ไม่ใช่รายได้รวม) ในการคำนวณ"

- name: a_no_approval_without_docs
  type: dependency
  when:
    entity: applicant
    relation: approval_status
    value: approved
  then:
    require:
      relation: documents_verified
      value: "true"
  message: "ห้ามอนุมัติโดยไม่ตรวจสอบเอกสาร"
# ... 2 more
```

### 8.3 Conflicts Detected

**Conflict 1: Contradiction**
```
c_min_employment (min: 6 months) vs x_guarantor_override (min: 3 months)
Z3: UNSAT — both are range rules on same relation with different min values
Human decision: Both are valid in different contexts. Rewrite as:
  → Keep c_min_employment as default
  → x_guarantor_override becomes a conditional dependency
```

**Conflict 2: Gap**
```
a_no_approval_without_docs has no matching constraint strategy rule.
The document says "เอกสารประกอบ" (section 3) but no constraint strategy
extracted a rule requiring document verification before approval.
Human decision: Approve the adversarial rule — this is a real gap.
```

**Conflict 3: Redundancy**
```
c_no_dual_contracts (exclusion: cannot have 2 active loans)
is equivalent to
b_max_contracts (range: max active_loans = 1)
Human decision: Keep exclusion version — clearer semantics.
```

---

## 9. Relationship to Existing Codebase

### 9.1 Modules Reused (No Changes Needed)

| Module | How Tournament Uses It |
|--------|----------------------|
| `parser.py` | Validate candidate YAML → Pydantic Rule models |
| `knowledge_base.py` | Z3 conflict detection (pairwise verify) |
| `rule_generator.py` | `_RULE_GEN_PROMPT`, `_clean_yaml_output()`, `_validate_yaml()`, `_get_default_llm()` |
| `models.py` | `Claim` for synthetic test claims |
| `resolver.py` | Entity normalization during conflict check |

### 9.2 New Module: `tournament.py`

Single new file containing:
- `STRATEGY_DIRECTIVES` (dict of prompt suffixes)
- `CandidateRule`, `Conflict`, `ArbitrationDecision`, `TournamentAudit` (Pydantic)
- `Tournament` class (main engine)

### 9.3 Integration with Axiom Studio (v0.7.0)

Tournament is designed as a **headless engine** with a programmatic API.
Axiom Studio (Streamlit) wraps it with a visual UI:

```
Axiom Studio (Streamlit)
├── Tab 1: Manual Editor (existing plan)
├── Tab 2: Tournament Mode (NEW)
│   ├── Step 1: Upload document / paste text
│   ├── Step 2: Select strategies (checkboxes)
│   ├── Step 3: Click "Generate" → shows candidates
│   ├── Step 4: Review conflicts → pick winners
│   ├── Step 5: Batch approve/reject standalone
│   └── Step 6: Download .axiom.yml + audit trail
└── Tab 3: Rule Tester (existing plan)
```

The Tournament engine does not depend on Streamlit — it can be used
purely from Python, CLI, or any other frontend.

---

## 10. Resnik Paper Alignment

| Resnik Argument | Tournament Response |
|-----------------|---------------------|
| LLMs cannot distinguish definitional vs contingent vs normative | Strategy "definitions" extracts definitions separately; "adversarial" surfaces normative edge cases; human classifies |
| RLHF is like squeezing a balloon | Tournament does not debias — it deliberately extracts from multiple bias angles, making conflicts visible |
| Bias is structural, not a bug | Tournament treats LLM output as structurally biased by design — that is why it generates multiple competing interpretations |
| Need to re-think foundational assumptions | LLM stays untrusted; Z3 provides mathematical proof; human makes normative decisions |
| Norms change faster than LLM releases | Re-run tournament when policy document updates — YAML rules update instantly without retraining |
| Current mitigation is whack-a-mole | Tournament surfaces conflicts proactively rather than waiting for failures in production |

---

## 11. Performance Considerations

### 11.1 LLM Calls

- 5 strategies = 5 LLM calls (parallelizable)
- Each call: ~1-4K tokens input, ~1-2K tokens output
- Estimated cost: ~$0.05-0.15 total (using Haiku/mini)
- One-time cost per document (not per verification)

### 11.2 Z3 Conflict Detection

- Pairwise checks: O(N^2) in worst case, reduced by relation grouping
- Each check: ~1-5ms (single Z3 solve)
- 30 candidates → ~435 pairs → ~1-2 seconds total
- 100 candidates → ~4,950 pairs → ~5-25 seconds total

### 11.3 Scalability Limits

- Documents producing >100 candidates: split by section and run
  separate tournaments, then merge approved rules
- Very large policy documents (100+ pages): chunk and run per-chapter
  tournaments, then cross-validate

---

## 12. Implementation Checklist

- [ ] `CandidateRule`, `Conflict`, `ArbitrationDecision`, `TournamentAudit` models
- [ ] `STRATEGY_DIRECTIVES` — 5 prompt templates
- [ ] `Tournament.__init__()` — setup with source, domain, strategies
- [ ] `Tournament.generate()` — multi-strategy candidate generation
- [ ] `Tournament._check_contradiction()` — Z3 pairwise UNSAT check
- [ ] `Tournament._check_redundancy()` — subsumption detection
- [ ] `Tournament._synthetic_claims()` — test claim generation per rule type
- [ ] `Tournament.detect_conflicts()` — full conflict detection pipeline
- [ ] `Tournament.decide()` / `approve()` / `reject()` — arbitration API
- [ ] `Tournament.to_knowledge_base()` / `to_yaml()` / `to_file()` — export
- [ ] `Tournament.audit_trail()` — compliance export
- [ ] Unit tests: generation, conflict detection, arbitration, export
- [ ] Integration test: end-to-end with real LLM on sample document
- [ ] Example script: `examples/tournament_loan_policy.py`
