# AI-Generated Rules

Turn natural language documents into `.axiom.yml` rules automatically using an LLM.

!!! tip "The killer feature"
    Instead of writing YAML by hand, send your 5-page policy document to Claude and get verified rules back in seconds.

## Basic Usage

```python
from axiomguard import generate_rules

yaml_str = generate_rules(
    text="""
    Company Policy:
    1. HQ is in Bangkok
    2. CEO is Somchai
    3. Maximum loan is 500,000 THB
    4. Minimum salary is 15,000 THB
    """,
    domain="company_policy",
)

print(yaml_str)  # Valid .axiom.yml YAML
```

## Direct to KnowledgeBase

Skip the YAML file — go straight to verification:

```python
from axiomguard import generate_rules_to_kb

kb = generate_rules_to_kb(
    text="ผู้กู้ต้องมีอายุ 20-60 ปี เงินเดือนขั้นต่ำ 15,000 บาท",
    domain="loan_policy",
)

# Ready to verify immediately
result = kb.verify(claims)
```

## Save to File

```python
from axiomguard import generate_rules_to_file

path = generate_rules_to_file(
    text="...",
    output_path="rules/company.axiom.yml",
    domain="company_policy",
)
```

## Custom LLM Backend

Pass any `(str) -> str` callable:

```python
def my_llm(prompt: str) -> str:
    # Call your preferred LLM
    return call_my_api(prompt)

yaml_str = generate_rules(
    text="...",
    llm_generate=my_llm,
)
```

## Thai Language Support

Works with Thai documents out of the box:

```python
yaml_str = generate_rules(
    text="""
    นโยบายสินเชื่อส่วนบุคคล บริษัท AxiomFinance
    1. ผู้กู้ต้องมีอายุระหว่าง 20-60 ปี
    2. เงินเดือนขั้นต่ำ 15,000 บาทต่อเดือน
    3. อายุงานปัจจุบันไม่น้อยกว่า 6 เดือน
    4. ห้ามมีประวัติค้างชำระเกิน 30 วัน
    """,
    domain="personal_loan",
)
```

The generated YAML will include Thai messages and aliases.

## Best Practices

1. **Review generated rules** — AI-generated rules are a starting point. Review them before production use.
2. **Version control** — Save generated YAML to `.axiom.yml` files and commit to git.
3. **Iterate** — Generate, review, edit, test. Use `kb.run_examples()` to validate.
4. **Mix modes** — Use AI to generate the initial set, then fine-tune manually.

!!! warning "Requires API key"
    Set `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` environment variable. See [API Key Setup](../getting-started/api-keys.md).
