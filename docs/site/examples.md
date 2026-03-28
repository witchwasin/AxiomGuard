# Examples

Runnable example scripts are in the [`examples/`](https://github.com/witchwasin/AxiomGuard/tree/main/examples) directory.

## Basic Usage

**File:** `examples/basic_usage.py`

The simplest possible AxiomGuard demo. No API key needed.

```bash
python examples/basic_usage.py
```

```python
from axiomguard import verify

axioms = ["The company is in Bangkok", "The CEO is Somchai"]

result = verify("The company is in Chiang Mai", axioms)
print(result.is_hallucinating)  # True
```

---

## Loan Approval Demo

**File:** `examples/loan_approval_demo.py`

Shows `RuleBuilder` creating rules programmatically, then verifying claims.

```bash
python examples/loan_approval_demo.py
```

Demonstrates:

- Building rules with `RuleBuilder` (range, unique)
- Thai entity aliases
- Salary/age validation
- Exporting rules to YAML

---

## Medical Bot Safety Guard

**File:** `examples/medical_bot_guard.py` + `examples/medical_rules.axiom.yml`

Catches dangerous medical hallucinations using YAML rules.

```bash
python examples/medical_bot_guard.py
```

Scenarios covered:

- Drug interaction (Warfarin + Aspirin)
- Dosage violation (Paracetamol > 4000mg)
- Blood type contradiction
- Allergy cross-reactivity (Penicillin → Amoxicillin)

---

## Document to Rules Demo

**File:** `examples/document_to_rules_demo.py`

Shows Mode 2 (AI-Generated) and Mode 3 (Programmatic) rule creation.

```bash
# Without API key (uses mock LLM)
python examples/document_to_rules_demo.py

# With real LLM
export ANTHROPIC_API_KEY="sk-ant-..."
python examples/document_to_rules_demo.py
```

Demonstrates:

- Converting a Thai loan policy document into YAML rules
- `generate_rules()` and `generate_rules_to_kb()`
- Fallback to mock when no API key is available
- Comparison between AI-generated and programmatic approaches

---

## Real LLM Usage

**File:** `examples/real_llm_usage.py`

Full pipeline with Anthropic Claude API.

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
python examples/real_llm_usage.py
```

---

## YAML Rule Files

| File | Domain | Rules |
|------|--------|-------|
| `examples/loan_rules.axiom.yml` | Personal loan (Thai) | Salary floor, employment minimum |
| `examples/medical_rules.axiom.yml` | Medical safety | Drug interactions, dosage limits, blood type |
