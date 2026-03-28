# Programmatic Rules (RuleBuilder)

Build rules dynamically from code, databases, or APIs using the fluent `RuleBuilder` API.

## Basic Usage

```python
from axiomguard import RuleBuilder

builder = RuleBuilder(domain="hr_policy")

builder.unique("one_department", entity="employee", relation="department")
builder.range_rule("age_limit", entity="employee", relation="age", min=18, max=65)

kb = builder.to_knowledge_base()
```

## Fluent Chaining

All methods return `self` for chaining:

```python
kb = (
    RuleBuilder(domain="loan")
    .entity("applicant", aliases=["ผู้กู้", "ลูกค้า"])
    .unique("hq", entity="company", relation="location", value="Bangkok")
    .range_rule("salary", entity="applicant", relation="salary", min=15000)
    .exclusion("conflict", entity="applicant", relation="status",
               values=["approved", "blacklisted"])
    .to_knowledge_base()
)
```

## All Rule Methods

### `.unique()`

```python
builder.unique(
    "rule_name",
    entity="company",
    relation="location",
    value="Bangkok",          # optional: fixed value
    severity="error",         # error | warning | info
    message="HQ is Bangkok",  # human-readable explanation
)
```

### `.exclusion()`

```python
builder.exclusion(
    "drug_conflict",
    entity="patient",
    relation="medication",
    values=["Warfarin", "Aspirin"],
    message="Cannot prescribe together.",
)
```

### `.range_rule()`

```python
builder.range_rule(
    "age_limit",
    entity="applicant",
    relation="age",
    min=20,             # optional
    max=60,             # optional
    value_type="int",   # int | float
    message="Must be 20-60.",
)
```

### `.dependency()`

```python
builder.dependency(
    "employment_check",
    when={
        "entity": "applicant",
        "relation": "employment_months",
        "value": "6",
        "value_type": "int",
        "operator": "<",
    },
    then_require={
        "relation": "status",
        "value": "rejected",
    },
    message="< 6 months employment = rejected.",
)
```

### `.entity()`

```python
builder.entity("applicant", aliases=["ผู้กู้", "client"], description="Loan applicant")
```

## Output Options

### To KnowledgeBase (for verification)

```python
kb = builder.to_knowledge_base()
result = kb.verify(claims)
```

### To YAML string

```python
yaml_str = builder.to_yaml()
print(yaml_str)
```

### To file

```python
builder.to_file("rules/generated.axiom.yml")
```

## Dynamic Rules from Database

```python
from axiomguard import RuleBuilder

builder = RuleBuilder(domain="dynamic")

# Load rules from your database
for row in db.query("SELECT * FROM policies WHERE country = 'TH'"):
    builder.unique(
        row.name,
        entity=row.entity,
        relation=row.relation,
        value=row.value,
        message=row.description,
    )

# Different rules per user type
if user.is_premium:
    builder.range_rule("credit_limit", entity="user",
                       relation="credit", max=1000000)
else:
    builder.range_rule("credit_limit", entity="user",
                       relation="credit", max=100000)

kb = builder.to_knowledge_base()
```

## When to Use RuleBuilder vs YAML

| Use Case | RuleBuilder | YAML File |
|----------|:-----------:|:---------:|
| Rules from database/API | Best | - |
| Rules change per user/request | Best | - |
| Static compliance rules | - | Best |
| Domain expert review | - | Best |
| Version-controlled policies | - | Best |
| Rapid prototyping | Best | - |
