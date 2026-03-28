# API Reference

## Core Verification

### `verify(response, axioms)`

Verify an LLM response against ground-truth axiom strings.

```python
from axiomguard import verify

result = verify(
    response="The CEO is John",
    axioms=["The CEO is Somchai"],
)
result.is_hallucinating  # True
result.reason            # "Z3 proved contradiction (UNSAT): ..."
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `response` | `str` | The LLM response to verify |
| `axioms` | `list[str]` | Ground-truth statements |

**Returns:** `VerificationResult`

---

### `verify_with_kb(response, kb)`

Verify against a KnowledgeBase with compiled YAML rules.

```python
from axiomguard import KnowledgeBase, verify_with_kb

kb = KnowledgeBase()
kb.load("rules.axiom.yml")
result = verify_with_kb("The CEO is John", kb)
```

---

### `verify_chunks(chunks, kb)`

Verify and annotate a list of RAG chunks in bulk.

```python
from axiomguard import verify_chunks

annotated = verify_chunks(chunks, kb)
```

---

### `generate_with_guard(prompt, kb, llm_generate, ...)`

Self-correcting generation loop.

```python
from axiomguard import generate_with_guard

result = generate_with_guard(
    prompt="Tell me about the company",
    kb=kb,
    llm_generate=my_llm,
    max_retries=2,
)
result.status    # "verified" | "corrected" | "failed"
result.response  # Final response text
result.attempts  # Number of attempts
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `prompt` | `str` | User prompt |
| `kb` | `KnowledgeBase` | Rules to verify against |
| `llm_generate` | `Callable[[str], str]` | LLM generation function |
| `max_retries` | `int` | Maximum correction attempts (default: 2) |

**Returns:** `CorrectionResult`

---

### `extract_claims(text)`

Extract SRO triples from natural language text.

```python
from axiomguard import extract_claims

claims = extract_claims("The company is in Bangkok and the CEO is Somchai")
# [Claim(subject="company", relation="location", object="Bangkok"),
#  Claim(subject="company", relation="ceo", object="Somchai")]
```

---

### `translate_to_logic(text)`

Translate a single sentence to an SRO triple dict.

```python
from axiomguard import translate_to_logic

triple = translate_to_logic("The company is in Bangkok")
# {"subject": "company", "relation": "location", "object": "Bangkok"}
```

---

## Rule Authoring

### `RuleBuilder`

Fluent API for building rules programmatically.

```python
from axiomguard import RuleBuilder

kb = (
    RuleBuilder(domain="test")
    .entity("company", aliases=["firm"])
    .unique("hq", entity="company", relation="location", value="Bangkok")
    .range_rule("salary", entity="employee", relation="salary", min=15000)
    .exclusion("conflict", entity="patient", relation="med", values=["A", "B"])
    .dependency("check", when={...}, then_require={...})
    .to_knowledge_base()
)
```

**Methods:** `.unique()`, `.exclusion()`, `.range_rule()`, `.dependency()`, `.entity()`, `.to_yaml()`, `.to_file()`, `.to_knowledge_base()`

---

## Configuration

### `set_llm_backend(backend)`

Swap the NL-to-Logic translator.

```python
from axiomguard import set_llm_backend
from axiomguard.backends.anthropic_llm import anthropic_translator

set_llm_backend(anthropic_translator)
```

### `set_entity_resolver(resolver)`

Set a custom entity resolver.

### `set_knowledge_base(kb)` / `get_knowledge_base()`

Set/get the default KnowledgeBase.

### `load_rules(path)`

Load `.axiom.yml` rules into the default KnowledgeBase.

---

## Data Models

### `Claim`

Pydantic model for a Subject-Relation-Object triple.

```python
from axiomguard import Claim

claim = Claim(subject="company", relation="location", object="Bangkok", negated=False)
```

| Field | Type | Description |
|-------|------|-------------|
| `subject` | `str` | Entity name |
| `relation` | `str` | Relation type |
| `object` | `str` | Value |
| `negated` | `bool` | True if negation |

### `VerificationResult`

Dataclass returned by `verify()`.

| Field | Type | Description |
|-------|------|-------------|
| `is_hallucinating` | `bool` | True if contradiction proved |
| `reason` | `str` | Human-readable explanation |
| `confidence` | `str` | `"proven"` or `"uncertain"` |
| `violated_rules` | `list[dict]` | Rule metadata for violated rules |
| `contradicted_claims` | `list[int]` | Indices of contradicting claims |

### `CorrectionResult`

Dataclass returned by `generate_with_guard()`.

| Field | Type | Description |
|-------|------|-------------|
| `status` | `str` | `"verified"`, `"corrected"`, `"failed"`, etc. |
| `response` | `str` | Final response text |
| `attempts` | `int` | Total attempts made |
| `history` | `list[CorrectionAttempt]` | Full attempt log |
| `final_verification` | `VerificationResult` | Last verification result |

### `KnowledgeBase`

Rule compiler and verification engine.

| Method | Description |
|--------|-------------|
| `load(path)` | Load `.axiom.yml` file |
| `load_string(content)` | Load from YAML string |
| `verify(claims, axioms)` | Verify claims against rules |
| `add_rule(rule)` | Add a compiled rule |
| `axiom_relations()` | Get all relations with rules |
| `run_examples()` | Run inline test examples |
| `rule_count` | Number of loaded rules |
| `constraint_count` | Number of Z3 constraints |
