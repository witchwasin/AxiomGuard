# v0.7.0 Applied Research: Advanced Rules & Ecosystem Integration

> **Status:** Outline — Pending v0.6.0 Completion
> **Date:** 2026-03-28 (updated 2026-03-29)
> **Goal:** Cover the full range of enterprise constraints and integrate with
> the LLM ecosystem (LangChain, LlamaIndex, Axiom Studio).
>
> **Related:** [Tournament-Style Rule Derivation](v070_tournament_rule_derivation.md)
> — a separate research doc covering multi-strategy candidate generation,
> Z3 conflict detection, and human arbitration. Tournament mode is a v0.7.0
> feature that transforms Axiom Studio from a rule editor into a full
> rule derivation platform.

---

## 1. Advanced Rule Types

### 1.1 Comparison Rules

**Problem:** "Loan amount must be <= 5x salary" requires cross-relation arithmetic.

**Proposed YAML:**

```yaml
- name: Loan-to-income ratio
  type: comparison
  entity: applicant
  left:
    relation: loan_amount
    value_type: int
  operator: "<="
  right:
    relation: salary
    multiplier: 5
    value_type: int
  severity: error
  message: "Loan amount must not exceed 5x monthly salary."
```

**Z3:** `ForAll([s], attr_loan(s) <= 5 * attr_salary(s))`

### 1.2 Cardinality Constraints

**Problem:** "A patient can have at most 2 primary diagnoses."

**Proposed YAML:**

```yaml
- name: Max 2 primary diagnoses
  type: cardinality
  entity: patient
  relation: primary_diagnosis
  at_most: 2
  severity: error
  message: "A patient can have at most 2 primary diagnoses."
```

```yaml
- name: At least 1 emergency contact
  type: cardinality
  entity: employee
  relation: emergency_contact
  at_least: 1
  severity: warning
  message: "Every employee should have at least 1 emergency contact."
```

**Z3:** Bounded counting via `z3.AtMost()` / `z3.AtLeast()` over tracked literals.

### 1.3 Rule Composition (AND/OR/NOT)

**Problem:** Complex policies: "If age > 60 AND has_diabetes, then require annual_checkup."

**Proposed YAML:**

```yaml
- name: Elderly diabetic checkup
  type: dependency
  when:
    all_of:
      - entity: patient
        relation: age
        operator: ">"
        value: "60"
        value_type: int
      - entity: patient
        relation: condition
        value: diabetes
  then:
    require:
      relation: annual_checkup
      value: required
  severity: error
  message: "Elderly patients with diabetes must have annual checkups."
```

Combinators:
- `all_of: [...]` → AND
- `any_of: [...]` → OR
- `none_of: [...]` → NOT(OR(...))

**Z3:** `Implies(And(cond1, cond2, ...), then_expr)`

### 1.4 Conditional Chains

**Problem:** Multi-step: If A → B → C (transitive dependency).

**Proposed YAML:**

```yaml
- name: Loan approval chain
  type: dependency
  when:
    entity: applicant
    relation: credit_score
    operator: "<"
    value: "600"
    value_type: int
  then:
    require:
      relation: approval_status
      value: manual_review
  chain:
    - when:
        relation: approval_status
        value: manual_review
      then:
        require:
          relation: reviewer_assigned
          value: required
```

---

## 2. LangChain Integration

### 2.1 Goal

Drop-in component for LangChain RAG pipelines.

### 2.2 API Design

```python
from axiomguard.integrations.langchain import AxiomGuardChain

# As a chain
chain = AxiomGuardChain(
    llm=ChatAnthropic(model="claude-sonnet-4-5-20250514"),
    knowledge_base=kb,
    max_retries=2,
)
result = chain.invoke({"query": "What is the company policy?"})

# As a retriever wrapper
from axiomguard.integrations.langchain import AxiomGuardRetriever

retriever = AxiomGuardRetriever(
    base_retriever=vectorstore.as_retriever(),
    knowledge_base=kb,
)
# Returns only verified chunks
```

### 2.3 Package

```bash
pip install "axiomguard[langchain]"
```

### 2.4 Implementation

New file: `axiomguard/integrations/langchain.py`

- `AxiomGuardChain` — wraps `generate_with_guard()` as a LangChain Runnable
- `AxiomGuardRetriever` — wraps `verify_chunks()` as a BaseRetriever
- `AxiomGuardOutputParser` — verifies parsed output against rules

---

## 3. LlamaIndex Integration

> **Same priority as LangChain** — enterprise clients use both.

### 3.1 API Design

```python
from axiomguard.integrations.llamaindex import AxiomGuardPostprocessor

# As a node postprocessor
postprocessor = AxiomGuardPostprocessor(
    knowledge_base=kb,
    mode="filter",  # "filter" | "annotate" | "strict"
)

# In query engine
query_engine = index.as_query_engine(
    node_postprocessors=[postprocessor],
)
```

```python
from axiomguard.integrations.llamaindex import AxiomGuardQueryEngine

# Full verified query engine
engine = AxiomGuardQueryEngine(
    base_engine=index.as_query_engine(),
    knowledge_base=kb,
    max_retries=2,
)
response = engine.query("Tell me about the patient's medication")
# response.metadata["axiomguard"] = {status, attempts, violated_rules}
```

### 3.2 Package

```bash
pip install "axiomguard[llamaindex]"
```

### 3.3 Implementation

New file: `axiomguard/integrations/llamaindex.py`

- `AxiomGuardPostprocessor` — implements `BaseNodePostprocessor`
- `AxiomGuardQueryEngine` — wraps base engine with self-correction loop

---

## 4. Axiom Studio (UI)

### 4.1 Vision

A visual rule **editor** (NOT generator) where domain experts:
1. **Write YAML rules** with syntax highlighting and validation
2. **Edit rules** visually (add/remove/modify via forms)
3. **Test rules** against sample inputs with live Z3 verification
4. **Export** `.axiom.yml` files
5. **Import** existing `.axiom.yml` files for editing

> **BYOR principle:** Axiom Studio helps humans write correct YAML.
> It does NOT auto-generate rules from documents.

### 4.2 Technology

**Streamlit** (chosen over Gradio for):
- Already used in `demo_app.py` — team knows it
- Better for form-based UIs
- Easier file download/upload

### 4.3 UI Layout

```
┌──────────────────────────────────────────────────┐
│  Axiom Studio                             [Dark] │
├──────────────────────────────────────────────────┤
│                                                  │
│  📝 Rule Editor              📋 YAML Preview     │
│  ┌───────────────────┐      ┌─────────────────┐ │
│  │ Name: [________]  │      │ axiomguard: "0.7"│ │
│  │ Type: [unique ▾]  │  →   │ domain: ...      │ │
│  │ Entity: [_______] │      │ rules:           │ │
│  │ Message: [______] │      │   - name: ...    │ │
│  └───────────────────┘      └─────────────────┘ │
│                                                  │
│  [Add Rule]                 [Download YAML]      │
│                                                  │
│  ─────────────────────────────────────────────── │
│                                                  │
│  🧪 Test Your Rules                              │
│  ┌───────────────────────────────────────────┐  │
│  │ Enter a claim to test: __________________ │  │
│  │                                           │  │
│  │ Result: ✅ SAT — No hallucination         │  │
│  │ or                                        │  │
│  │ Result: ❌ UNSAT — Violated: rule_name    │  │
│  └───────────────────────────────────────────┘  │
│                                                  │
│  📊 Rule Summary                                 │
│  ┌───────────────────────────────────────────┐  │
│  │ Total: 5 rules | 3 unique | 1 exclusion  │  │
│  │ | 1 range                                 │  │
│  └───────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

### 4.4 Implementation Plan

New file: `axiom_studio.py` (root level, like `demo_app.py`)

```python
import streamlit as st
from axiomguard import generate_rules, generate_rules_to_kb, KnowledgeBase, Claim

st.set_page_config(page_title="Axiom Studio", layout="wide")

# Left column: Input
# Right column: Generated YAML
# Bottom: Test section
```

**Features for v0.7.0 (foundational):**
- [x] Natural language → YAML generation
- [x] YAML preview + download
- [x] Single claim testing
- [ ] Visual rule editor (v0.8.0+)
- [ ] Batch testing from CSV (v0.8.0+)

### 4.5 Package

```bash
pip install "axiomguard[studio]"  # includes streamlit
```

---

## 5. REST API Wrapper (FastAPI)

### 5.1 Goal

Language-agnostic verification — JavaScript, Go, Java clients can call AxiomGuard via HTTP.

### 5.2 API Endpoints

```
POST /verify
  Body: { "response": "...", "axioms": ["..."] }
  Returns: { "is_hallucinating": true, "reason": "..." }

POST /verify-with-rules
  Body: { "response": "...", "rules_yaml": "..." }
  Returns: VerificationResult

POST /generate-rules
  Body: { "text": "...", "domain": "..." }
  Returns: { "yaml": "..." }

GET /health
  Returns: { "status": "ok", "version": "0.7.0" }
```

### 5.3 Implementation

New file: `axiomguard/server.py`

```python
from fastapi import FastAPI
from axiomguard import verify, KnowledgeBase, generate_rules

app = FastAPI(title="AxiomGuard API", version="0.7.0")

@app.post("/verify")
async def verify_endpoint(request: VerifyRequest):
    result = verify(request.response, request.axioms)
    return result
```

**Run:**

```bash
pip install "axiomguard[server]"  # includes fastapi + uvicorn
uvicorn axiomguard.server:app --port 8000
```

---

## 6. Implementation Order

```
Phase 1 (Rule Types):
  ├── Comparison rules
  ├── Cardinality constraints
  └── Rule composition (AND/OR/NOT)

Phase 2 (Tournament — see v070_tournament_rule_derivation.md):
  ├── tournament.py — core engine (generate, detect, arbitrate, export)
  ├── Strategy prompt templates (5 strategies)
  └── Pairwise Z3 conflict detection

Phase 3 (Ecosystem — parallelizable):
  ├── LangChain integration
  ├── LlamaIndex integration
  └── REST API (FastAPI)

Phase 4 (UI):
  └── Axiom Studio (Streamlit)
      ├── Tab 1: Manual Editor
      ├── Tab 2: Tournament Mode
      └── Tab 3: Rule Tester

Phase 5 (Quality):
  └── Tests (~40 new), examples, docs

Phase 6 (Release):
  └── Version bump 0.7.0, CHANGELOG, PyPI
```

---

## 7. New Package Extras

```toml
[project.optional-dependencies]
langchain = ["langchain-core>=0.3.0"]
llamaindex = ["llama-index-core>=0.11.0"]
server = ["fastapi>=0.100.0", "uvicorn>=0.20.0"]
studio = ["streamlit>=1.30.0"]
all = [
    "anthropic>=0.39.0",
    "openai>=1.0.0",
    "chromadb>=0.4.0",
    "qdrant-client>=1.7.0",
    "langchain-core>=0.3.0",
    "llama-index-core>=0.11.0",
    "fastapi>=0.100.0",
    "uvicorn>=0.20.0",
    "streamlit>=1.30.0",
]
```

---

*This outline will be expanded into a full research document after v0.6.0 is complete.*
