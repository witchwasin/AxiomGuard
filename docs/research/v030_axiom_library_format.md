# v0.3.0 Applied Research: Axiom Library Format (`.axiom.yml`)

> **Status:** Design Complete — Ready for Implementation Review
> **Date:** 2026-03-28
> **Goal:** A declarative YAML format that lawyers, doctors, and domain experts can
> write without knowing Z3 or Python.

---

## 1. Design Philosophy

### 1.1 The Problem

Today, adding rules to AxiomGuard means writing Python:

```python
# Only a developer can write this
axioms = [
    {"subject": "company", "relation": "location", "object": "Bangkok"},
]
result = verify(response, axioms)
```

This excludes the people who actually *know* the rules — lawyers, doctors,
compliance officers, auditors. They think in terms like:

> "A patient cannot take Warfarin and Aspirin at the same time."
> "A company can only have one registered address."
> "An insurance claim is only valid if the incident date is after the policy start date."

### 1.2 Design Principles

| # | Principle | Rationale |
|---|-----------|-----------|
| 1 | **Read like English, compile to Z3** | The YAML is the human interface. Z3 is the machine interface. |
| 2 | **Domain words, not logic words** | Say `unique`, `excludes`, `requires` — not `ForAll`, `Implies`, `Not(And(...))` |
| 3 | **Flat over nested** | Max 4 levels of YAML indentation. If you need more, the rule is too complex — split it. |
| 4 | **Metadata is mandatory** | Every rule has `name`, `severity`, `message`. Unnamed rules are unmaintainable. |
| 5 | **Testable by design** | Inline `examples` with expected pass/fail, so rules can be unit-tested without Python. |
| 6 | **Escape hatch exists** | For the 20% of rules that can't be expressed in YAML sugar, allow raw Z3 expressions. |

### 1.3 Prior Art Considered

| System | What We Took | What We Avoided |
|--------|-------------|-----------------|
| NeMo Guardrails (Colang) | Natural-language-like readability | Flow-based model (too chatbot-specific) |
| OPA (Rego) | Implicit AND within rules, OR across rules | Datalog syntax (too CS-academic) |
| Drools | when/then structure | Rete complexity, Java dependency |
| JSON Schema | `if/then`, `minimum/maximum` | Deep `allOf/anyOf` nesting |
| SHACL | Severity levels, cardinality constraints | RDF/Turtle syntax |
| CQL (Healthcare) | Domain vocabulary, clinician readability | FHIR-specific bindings |

---

## 2. File Format Specification

### 2.1 File Convention

```
rules/
├── company.axiom.yml       ← corporate governance rules
├── medical.axiom.yml       ← drug interaction rules
├── insurance.axiom.yml     ← claims processing rules
└── _aliases.yml            ← shared entity aliases (optional)
```

Extension: `.axiom.yml` — instantly recognizable, IDE-friendly.

### 2.2 Top-Level Structure

```yaml
# Every .axiom.yml file has these three sections
axiomguard: "0.3"          # format version (for future migrations)
domain: "healthcare"        # human label for this rule set

entities: [...]             # entity definitions + aliases
rules: [...]                # the actual constraints
```

### 2.3 Full Schema Overview

```yaml
axiomguard: "0.3"
domain: string              # "healthcare", "legal", "finance", etc.

entities:                   # OPTIONAL — define entities and aliases
  - name: string
    aliases: [string, ...]
    description: string     # optional

rules:                      # REQUIRED — at least one rule
  - name: string            # REQUIRED — human-readable identifier
    description: string     # optional — longer explanation
    type: string            # REQUIRED — "unique" | "exclusion" | "dependency"
    severity: string        # optional — "error" | "warning" | "info" (default: "error")
    message: string         # optional — custom violation message (supports {placeholders})
    ...                     # type-specific fields (see Section 3)
    examples:               # optional — inline test cases
      - input: string
        expect: "pass" | "fail"
```

---

## 3. Rule Types

### 3.1 Type: `unique` — Cardinality / Uniqueness Rules

**Human concept:** "A thing can only have ONE value for this property."

**Schema:**

```yaml
- name: string
  type: unique
  entity: string            # the subject (e.g., "company", "patient")
  relation: string          # the property that must be unique (e.g., "headquarters")
  message: string           # optional
```

**Example — Corporate:**

```yaml
- name: One headquarters per company
  type: unique
  entity: company
  relation: headquarters
  severity: error
  message: "A company can only have one headquarters. Found '{old}' and '{new}'."

  examples:
    - input: "The company headquarters is in Bangkok"
      axioms: ["The company headquarters is in Bangkok"]
      expect: pass

    - input: "The company headquarters is in Chiang Mai"
      axioms: ["The company headquarters is in Bangkok"]
      expect: fail
```

**Example — Healthcare:**

```yaml
- name: One blood type per patient
  type: unique
  entity: patient
  relation: blood_type
  severity: error
  message: "Patient cannot have two blood types."
```

**Z3 Compilation (conceptual):**

```python
# unique(entity="company", relation="headquarters")
# ↓ compiles to ↓

s = z3.Const("s", StringSort)
o1 = z3.Const("o1", StringSort)
o2 = z3.Const("o2", StringSort)

solver.add(
    z3.ForAll([s, o1, o2],
        z3.Implies(
            z3.And(
                Relation(StringVal("headquarters"), s, o1),
                Relation(StringVal("headquarters"), s, o2),
            ),
            o1 == o2
        )
    )
)
```

**Note:** This is already what v0.2.0's `EXCLUSIVE_RELATIONS` does — but hardcoded.
The YAML format makes it **configurable per domain** without touching Python.

---

### 3.2 Type: `exclusion` — Conflict / Mutual Exclusivity Rules

**Human concept:** "These things cannot coexist for the same entity."

**Schema:**

```yaml
- name: string
  type: exclusion
  entity: string            # the subject
  relation: string          # the shared relation
  values: [string, ...]     # the conflicting values (2 or more)
  message: string           # optional
```

**Example — Drug Interaction:**

```yaml
- name: Warfarin-Aspirin interaction
  type: exclusion
  entity: patient
  relation: takes
  values: [Warfarin, Aspirin]
  severity: error
  message: "Patient cannot take {values[0]} and {values[1]} simultaneously — risk of bleeding."

  examples:
    - input: "Patient takes Aspirin"
      axioms: ["Patient takes Warfarin"]
      expect: fail

    - input: "Patient takes Paracetamol"
      axioms: ["Patient takes Warfarin"]
      expect: pass
```

**Example — Contract Status:**

```yaml
- name: Contract cannot be active and terminated
  type: exclusion
  entity: contract
  relation: status
  values: [active, terminated, suspended]
  severity: error
  message: "Contract status must be exactly one of: {values}."
```

**Example — N-way Exclusion (Allergy group):**

```yaml
- name: Penicillin allergy group
  type: exclusion
  entity: patient
  relation: prescribed
  values: [Amoxicillin, Ampicillin, Penicillin V]
  severity: error
  message: "Patient allergic to penicillin group — cannot prescribe any of: {values}."
```

**Z3 Compilation (conceptual):**

```python
# exclusion(entity="patient", relation="takes", values=["Warfarin", "Aspirin"])
# ↓ compiles to ↓

s = z3.Const("s", StringSort)

# Pairwise exclusion for all value combinations
solver.add(
    z3.ForAll([s],
        z3.Not(z3.And(
            Relation(StringVal("takes"), s, StringVal("Warfarin")),
            Relation(StringVal("takes"), s, StringVal("Aspirin")),
        ))
    )
)

# For N values, generate all pairs:
# (Warfarin, Aspirin), (Warfarin, Penicillin), (Aspirin, Penicillin), ...
```

**Why this is different from `unique`:**
- `unique` says: "one value only, but any value is fine."
- `exclusion` says: "these SPECIFIC values cannot appear together."

A patient can take multiple drugs (not unique), but these particular
drugs conflict (exclusion).

---

### 3.3 Type: `dependency` — Requirement / Implication Rules

**Human concept:** "If condition A is true, then condition B must also be true."

**Schema:**

```yaml
- name: string
  type: dependency
  when:                     # the condition (IF)
    entity: string
    relation: string
    value: string           # optional — specific value to match
    operator: string        # optional — "=", "!=", ">", "<", ">=", "<="
  then:                     # the requirement (THEN)
    require:                # what must be true
      relation: string
      value: string         # optional
      operator: string      # optional
  message: string           # optional
```

**Example — Insurance:**

```yaml
- name: Claim requires active policy
  type: dependency
  when:
    entity: claim
    relation: type
    value: insurance_claim
  then:
    require:
      relation: policy_status
      value: active
  severity: error
  message: "Cannot process insurance claim without an active policy."

  examples:
    - input: "Claim type is insurance_claim"
      axioms: ["Claim policy_status is active"]
      expect: pass

    - input: "Claim type is insurance_claim"
      axioms: ["Claim policy_status is expired"]
      expect: fail
```

**Example — Medical Protocol:**

```yaml
- name: Chemotherapy requires blood test
  type: dependency
  when:
    entity: patient
    relation: treatment
    value: chemotherapy
  then:
    require:
      relation: blood_test
      value: completed
  severity: error
  message: "Chemotherapy cannot proceed without a completed blood test."
```

**Example — Legal Compliance:**

```yaml
- name: Contract above 2M requires board approval
  type: dependency
  when:
    entity: contract
    relation: value_thb
    operator: ">"
    value: "2000000"
  then:
    require:
      relation: board_approval
      value: "true"
  severity: error
  message: "Contracts exceeding 2M THB require board approval per regulation §12.3."
```

**Z3 Compilation (conceptual):**

```python
# dependency(when={entity="claim", relation="type", value="insurance_claim"},
#            then={require={relation="policy_status", value="active"}})
# ↓ compiles to ↓

s = z3.Const("s", StringSort)

solver.add(
    z3.ForAll([s],
        z3.Implies(
            Relation(StringVal("type"), s, StringVal("insurance_claim")),
            Relation(StringVal("policy_status"), s, StringVal("active")),
        )
    )
)

# With operator ">" (numeric comparison):
# Requires extending Z3 model to use IntSort/RealSort for numeric relations
# (v0.4.0 scope — see Section 6)
```

---

## 4. Real-World Domain Examples

### 4.1 Healthcare — `medical.axiom.yml`

```yaml
axiomguard: "0.3"
domain: healthcare

entities:
  - name: patient
    aliases: ["ผู้ป่วย", "client", "pt"]
  - name: drug
    aliases: ["medication", "ยา", "medicine"]

rules:
  - name: One blood type per patient
    type: unique
    entity: patient
    relation: blood_type
    severity: error

  - name: Warfarin-Aspirin interaction
    type: exclusion
    entity: patient
    relation: takes
    values: [Warfarin, Aspirin]
    severity: error
    message: "CRITICAL: Warfarin + Aspirin = bleeding risk."

  - name: Penicillin allergy cross-reactivity
    type: exclusion
    entity: patient
    relation: prescribed
    values: [Amoxicillin, Ampicillin, Penicillin V, Piperacillin]
    severity: error
    message: "Patient with penicillin allergy — all beta-lactams contraindicated."

  - name: Chemotherapy requires CBC
    type: dependency
    when:
      entity: patient
      relation: treatment
      value: chemotherapy
    then:
      require:
        relation: cbc_test
        value: completed
    severity: error
    message: "Cannot start chemo without Complete Blood Count results."

  - name: Opioid requires pain assessment
    type: dependency
    when:
      entity: patient
      relation: prescribed
      value: morphine
    then:
      require:
        relation: pain_score
        value: documented
    severity: warning
    message: "Pain assessment should be documented before prescribing opioids."
```

### 4.2 Legal / Contract — `legal_contract.axiom.yml`

```yaml
axiomguard: "0.3"
domain: legal

entities:
  - name: contract
    aliases: ["สัญญา", "agreement", "MOU"]
  - name: party
    aliases: ["คู่สัญญา", "signatory"]

rules:
  - name: One governing law per contract
    type: unique
    entity: contract
    relation: governing_law
    severity: error
    message: "Contract cannot be governed by two jurisdictions simultaneously."

  - name: Cannot be both plaintiff and defendant
    type: exclusion
    entity: party
    relation: role
    values: [plaintiff, defendant]
    severity: error

  - name: Arbitration excludes litigation
    type: exclusion
    entity: contract
    relation: dispute_resolution
    values: [arbitration, litigation]
    severity: error
    message: "Contract must choose either arbitration or litigation, not both."

  - name: Termination requires notice period
    type: dependency
    when:
      entity: contract
      relation: action
      value: terminate
    then:
      require:
        relation: notice_period
        value: served
    severity: error
    message: "Contract cannot be terminated without serving the notice period."
```

### 4.3 Finance / Insurance — `insurance.axiom.yml`

```yaml
axiomguard: "0.3"
domain: insurance

entities:
  - name: claim
    aliases: ["เคลม", "insurance claim"]
  - name: policy
    aliases: ["กรมธรรม์", "insurance policy"]

rules:
  - name: One beneficiary per life policy
    type: unique
    entity: policy
    relation: primary_beneficiary
    severity: warning
    message: "Life insurance policy should have exactly one primary beneficiary."

  - name: Cannot claim on lapsed and active simultaneously
    type: exclusion
    entity: policy
    relation: status
    values: [active, lapsed, cancelled, suspended]
    severity: error

  - name: Claim requires active policy
    type: dependency
    when:
      entity: claim
      relation: type
      value: insurance_claim
    then:
      require:
        relation: policy_status
        value: active
    severity: error
    message: "Claim denied: policy is not active."

  - name: High-value claim requires investigation
    type: dependency
    when:
      entity: claim
      relation: category
      value: high_value
    then:
      require:
        relation: investigation
        value: completed
    severity: error
    message: "Claims above threshold require completed investigation before payout."
```

---

## 5. Entity Aliases Integration

### 5.1 Inline Aliases (per file)

```yaml
entities:
  - name: patient
    aliases: ["ผู้ป่วย", "client", "pt"]
```

At parse time, these merge into `EntityResolver.add_aliases()`:

```python
# "ผู้ป่วย" → "patient", "client" → "patient", "pt" → "patient"
```

### 5.2 Shared Aliases File (`_aliases.yml`)

For aliases shared across multiple `.axiom.yml` files:

```yaml
# rules/_aliases.yml
axiomguard: "0.3"

aliases:
  Bangkok: ["BKK", "กรุงเทพ", "กทม", "Krung Thep"]
  Chiang Mai: ["CNX", "เชียงใหม่", "Chiangmai"]
  Thailand: ["TH", "ไทย", "ประเทศไทย"]
```

Loaded first, then each `.axiom.yml` file's `entities` extend it.

---

## 6. The Inline Test Story

Every rule can carry its own test cases:

```yaml
- name: Warfarin-Aspirin interaction
  type: exclusion
  entity: patient
  relation: takes
  values: [Warfarin, Aspirin]

  examples:
    - input: "Patient takes Aspirin"
      axioms: ["Patient takes Warfarin"]
      expect: fail
      description: "Both blood thinners — must contradict"

    - input: "Patient takes Paracetamol"
      axioms: ["Patient takes Warfarin"]
      expect: pass
      description: "No interaction between these drugs"

    - input: "Patient takes Warfarin"
      axioms: ["Patient takes Warfarin"]
      expect: pass
      description: "Same drug stated twice — no contradiction"
```

**CLI usage (future):**

```bash
$ axiomguard test rules/medical.axiom.yml

  medical.axiom.yml
    ✓ Warfarin-Aspirin interaction (3 examples)
    ✓ One blood type per patient (2 examples)
    ✓ Chemotherapy requires CBC (2 examples)

  7/7 examples passed
```

---

## 7. Conceptual Parse Pipeline

```
.axiom.yml file
      │
      ▼
[1. YAML Parse] ──── PyYAML / ruamel.yaml
      │
      ▼
[2. Schema Validate] ── Pydantic models (RuleSet, Rule, Example)
      │
      ▼
[3. Entity Merge] ──── entities → EntityResolver.add_aliases()
      │
      ▼
[4. Rule Compile] ──── Each rule type → Z3 ForAll expression
      │                 unique    → ForAll + Implies + o1 == o2
      │                 exclusion → ForAll + Not(And(...))
      │                 dependency → ForAll + Implies(when, then)
      ▼
[5. Solver Load] ───── solver.add(compiled_rules)
      │
      ▼
Ready for verify()
```

### 7.1 Rule Compile — Type Dispatch

```python
# Pseudocode — NOT the actual implementation yet

def compile_rule(rule: Rule, Relation, StringSort) -> z3.ExprRef:
    s = z3.Const("s", StringSort)

    if rule.type == "unique":
        o1 = z3.Const("o1", StringSort)
        o2 = z3.Const("o2", StringSort)
        return z3.ForAll([s, o1, o2],
            z3.Implies(
                z3.And(
                    Relation(z3.StringVal(rule.relation), s, o1),
                    Relation(z3.StringVal(rule.relation), s, o2),
                ),
                o1 == o2
            )
        )

    elif rule.type == "exclusion":
        # Generate pairwise Not(And(...)) for all value combinations
        from itertools import combinations
        exprs = []
        for v1, v2 in combinations(rule.values, 2):
            exprs.append(
                z3.ForAll([s],
                    z3.Not(z3.And(
                        Relation(z3.StringVal(rule.relation), s, z3.StringVal(v1)),
                        Relation(z3.StringVal(rule.relation), s, z3.StringVal(v2)),
                    ))
                )
            )
        return z3.And(*exprs) if len(exprs) > 1 else exprs[0]

    elif rule.type == "dependency":
        return z3.ForAll([s],
            z3.Implies(
                Relation(
                    z3.StringVal(rule.when["relation"]),
                    s,
                    z3.StringVal(rule.when["value"]),
                ),
                Relation(
                    z3.StringVal(rule.then["require"]["relation"]),
                    s,
                    z3.StringVal(rule.then["require"]["value"]),
                ),
            )
        )
```

---

## 8. Limitations & Future Extensions

### 8.1 What v0.3.0 Supports

| Feature | Supported |
|---------|-----------|
| String equality (`value: "Bangkok"`) | Yes |
| Uniqueness constraints | Yes |
| Pairwise exclusion (2+ values) | Yes |
| Simple dependency (if A then B) | Yes |
| Entity aliases from YAML | Yes |
| Inline test examples | Yes |
| Severity levels (error/warning/info) | Yes |

### 8.2 What Requires v0.4.0+ (Numeric / Temporal)

| Feature | Blocked By | Plan |
|---------|-----------|------|
| Numeric comparison (`>`, `<`, `>=`) | Z3 currently uses StringSort for all objects | Add IntSort/RealSort support in z3_engine |
| Date comparison (`date > policy_start`) | Dates are strings, not comparable | Parse dates → IntSort (epoch) at compile time |
| Range constraints (`between: [0, 100]`) | Same as numeric | Same as numeric |
| Aggregation (`count of X > 3`) | Requires counting ground instances | Significant Z3 modeling extension |

### 8.3 Escape Hatch (Advanced Users)

For the 20% of rules that can't be expressed in YAML sugar:

```yaml
- name: Custom complex rule
  type: raw
  z3_expression: |
    ForAll([s, o],
      Implies(
        And(Relation("role", s, o), o == "admin"),
        Exists([t], Relation("mfa_verified", s, t))
      )
    )
  severity: error
  message: "Admin users must have MFA verification."
```

The `raw` type passes the expression string directly to `eval()` in a
sandboxed Z3 context. **Security note:** only load `.axiom.yml` files
from trusted sources.

---

## 9. Implementation Checklist for v0.3.0

Based on this design:

- [ ] Pydantic models for `.axiom.yml` schema (`RuleSet`, `UniqueRule`, `ExclusionRule`, `DependencyRule`)
- [ ] YAML parser: load `.axiom.yml` → validated `RuleSet`
- [ ] Rule compiler: `RuleSet` → list of Z3 `ForAll` expressions
- [ ] Entity merge: `entities` section → `EntityResolver.add_aliases()`
- [ ] `axiomguard.load_rules("rules/medical.axiom.yml")` public API
- [ ] Inline example runner: parse `examples` → run `verify()` → compare with `expect`
- [ ] 1 real domain PoC file: `examples/medical.axiom.yml` with drug interactions
- [ ] Integration test: load YAML → compile → verify → correct results

---

## References

- NVIDIA NeMo Guardrails — Colang 2.0 format
- Open Policy Agent — Rego language specification
- Drools — DRL format and decision tables
- JSON Schema — Draft 2020-12 (`if/then/else`, `oneOf`)
- W3C SHACL — Shapes Constraint Language
- HL7 CQL — Clinical Quality Language specification
- Z3 Python API — z3-solver documentation
