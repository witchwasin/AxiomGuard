# YAML Rules Format

AxiomGuard uses `.axiom.yml` files to define domain rules. These files are designed to be **readable by non-programmers** — lawyers, doctors, compliance officers can review and edit them directly.

## File Structure

```yaml
axiomguard: "0.3"          # Format version
domain: company_facts       # Domain identifier

entities:                    # Entity definitions (optional)
  - name: company
    aliases: ["firm", "org", "บริษัท"]

rules:                       # One or more rules
  - name: rule_name
    type: unique|exclusion|dependency|range
    ...
```

## Rule Types

### `unique` — Single Value

An entity can only have **one value** for this relation. The most common rule type.

```yaml
- name: one_headquarters
  type: unique
  entity: company
  relation: location
  value: Bangkok
  severity: error
  message: "Company has exactly one HQ location."
```

**Z3 logic:** `ForAll(s, o1, o2): Rel(r, s, o1) AND Rel(r, s, o2) → o1 = o2`

**Use cases:** HQ location, CEO name, blood type, primary doctor

---

### `exclusion` — Mutual Conflict

These specific values **cannot coexist** for the same entity.

```yaml
- name: warfarin_aspirin
  type: exclusion
  entity: patient
  relation: medication
  values: [Warfarin, Aspirin]
  severity: error
  message: "Warfarin and Aspirin cannot be prescribed together."
```

**Z3 logic:** `ForAll(s): NOT(Rel(r, s, "Warfarin") AND Rel(r, s, "Aspirin"))`

**Use cases:** Drug interactions, conflicting statuses, mutually exclusive options

---

### `dependency` — If-Then

If condition A is true, then B **must** also be true.

```yaml
- name: min_employment
  type: dependency
  when:
    entity: applicant
    relation: employment_months
    value: "6"
    value_type: int
    operator: "<"
  then:
    require:
      relation: approval_status
      value: rejected
  severity: error
  message: "Applicants with < 6 months employment must be rejected."
```

**Supported operators:** `=`, `!=`, `>`, `<`, `>=`, `<=`

**Supported value types:** `string`, `int`, `float`, `date`

**Use cases:** Conditional approval, policy enforcement, eligibility checks

---

### `range` — Numeric Bounds

A numeric attribute must be **within min/max bounds**.

```yaml
- name: age_limit
  type: range
  entity: applicant
  relation: age
  value_type: int
  min: 20
  max: 60
  severity: error
  message: "Applicant must be 20-60 years old."
```

You can specify `min` only, `max` only, or both.

**Use cases:** Age limits, salary floors, dosage caps, date ranges

---

## Entities & Aliases

Define entities so AxiomGuard resolves aliases automatically:

```yaml
entities:
  - name: applicant
    aliases: ["ผู้กู้", "ลูกค้า", "ผู้สมัคร", "client"]
    description: "Loan applicant"

  - name: company
    aliases: ["firm", "org", "บริษัท"]
```

When the LLM extracts "ผู้กู้" as a subject, AxiomGuard resolves it to "applicant" before Z3 verification.

## Severity Levels

```yaml
severity: error    # Hard violation — hallucination detected
severity: warning  # Soft violation — flagged but not blocked
severity: info     # Informational only
```

## Inline Examples (Self-Testing Rules)

Embed test cases directly in your rules:

```yaml
- name: hq_location
  type: unique
  entity: company
  relation: location
  value: Bangkok
  examples:
    - input: "The company is in Bangkok"
      axioms: ["The company is in Bangkok"]
      expect: pass
    - input: "The company is in Chiang Mai"
      axioms: ["The company is in Bangkok"]
      expect: fail
```

Run tests: `kb.run_examples()` returns `(passed, total, failures)`.

## Full Example

```yaml
axiomguard: "0.3"
domain: personal_loan

entities:
  - name: applicant
    aliases: ["ผู้กู้", "ลูกค้า", "ผู้สมัคร"]

rules:
  - name: age_limit
    type: range
    entity: applicant
    relation: age
    value_type: int
    min: 20
    max: 60
    severity: error
    message: "ผู้กู้ต้องมีอายุ 20-60 ปี"

  - name: min_salary
    type: range
    entity: applicant
    relation: salary_thb
    value_type: int
    min: 15000
    severity: error
    message: "เงินเดือนขั้นต่ำ 15,000 บาท"

  - name: one_approval_status
    type: unique
    entity: applicant
    relation: approval_status
    severity: error
    message: "สถานะอนุมัติมีได้เพียงค่าเดียว"

  - name: drug_interaction
    type: exclusion
    entity: applicant
    relation: insurance_type
    values: [health, life_critical]
    severity: warning
    message: "Cannot combine health and life-critical insurance."

  - name: probation_check
    type: dependency
    when:
      entity: applicant
      relation: employment_months
      value: "6"
      value_type: int
      operator: "<"
    then:
      require:
        relation: approval_status
        value: rejected
    severity: error
    message: "อายุงานต่ำกว่า 6 เดือนต้องปฏิเสธ"
```
