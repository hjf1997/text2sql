# Cross-Session Memory System

## Overview

The **Cross-Session Memory System** enables the Text-to-SQL Agent to learn from past queries and build institutional knowledge over time. This solves common problems like table name mismatches (e.g., `Customers` in schema vs. `PROD_Customers` in BigQuery) without manual intervention.

## Problem Solved

**Scenario**: Your company's BigQuery tables have prefixes (like `PROD_`, `DWH_`, etc.) that don't appear in the Excel schema files.

**Without Memory**:
1. User asks: "Show me all customers"
2. System generates: `SELECT * FROM Customers`
3. Error: "Table `Customers` not found" ❌
4. Manual correction needed every time

**With Memory**:
1. First time: Error occurs, user corrects or system retries with prefix
2. System learns: `Customers` → `PROD_Customers`
3. Next time: System automatically uses `PROD_Customers` ✅
4. Future queries: No errors, no manual corrections needed

## Architecture

### Two-Tier System

```
┌─────────────────────────────────────────────────────────────┐
│                     Memory System                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Tier 1: Manual Lessons                                     │
│  ├─ File: config/lessons_learned.yaml                       │
│  ├─ Confidence: 0.90-1.00 (High)                           │
│  ├─ Source: Manually configured by admins                   │
│  └─ Use Case: Known, validated patterns                     │
│                                                              │
│  Tier 2: Auto-Learned Lessons                              │
│  ├─ File: memory/learned_lessons.json                       │
│  ├─ Confidence: 0.60-0.90 (Adaptive)                       │
│  ├─ Source: Automatically extracted from queries            │
│  └─ Use Case: Discovered patterns, evolving knowledge       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Learning Sources

1. **Error Recovery**: Table not found → Added prefix → Success
2. **User Corrections**: Explicit instructions like "Use PROD_ prefix"
3. **Successful Patterns**: Reinforced through repeated successful use

## Components

### 1. Lesson Models (`src/memory/models.py`)

Four types of lessons:

```python
# Table name transformations
TableMappingLesson:
    schema_name: "Customers"
    actual_name: "PROD_Customers"
    prefix: "PROD_"
    confidence: 0.95

# Column name mappings
ColumnMappingLesson:
    table_name: "Customers"
    schema_column: "customer_id"
    actual_column: "cust_id"
    confidence: 0.85

# Error patterns and fixes
ErrorPatternLesson:
    error_pattern: "Table .* not found"
    suggested_fix: "Add 'PROD_' prefix"
    confidence: 0.90

# Successful query patterns
QueryPatternLesson:
    query_type: "customer_orders_join"
    sql_template: "SELECT ... FROM PROD_Customers ..."
    confidence: 0.85
```

### 2. Lesson Repository (`src/memory/repository.py`)

Central storage and retrieval:

```python
from src.memory import lesson_repository

# Get all lessons
all_lessons = lesson_repository.get_all_lessons()

# Get table-specific lessons
lessons = lesson_repository.get_table_mapping_lessons("Customers")

# Get relevant lessons for a query
relevant = lesson_repository.get_relevant_lessons(
    user_query="Show customers",
    identified_tables=["Customers"]
)

# Add new lesson
lesson_repository.add_lesson(new_lesson)
```

### 3. Table Mapper (`src/memory/table_mapper.py`)

Applies transformations:

```python
from src.memory import TableMapper

mapper = TableMapper()

# Transform a single table
result = mapper.transform("Customers")  # Returns: "PROD_Customers"

# Transform multiple tables
results = mapper.transform_multiple(["Customers", "Orders"])
# Returns: {"Customers": "PROD_Customers", "Orders": "PROD_Orders"}

# Preview transformations
preview = mapper.preview_transformations(["Customers"])
```

### 4. Lesson Learner (`src/memory/learner.py`)

Automatic extraction:

```python
from src.memory import LessonLearner

learner = LessonLearner()

# Learn from completed session
lessons = learner.learn_from_session(session)

# System automatically calls this after successful queries
```

## Configuration

### Manual Lessons (`config/lessons_learned.yaml`)

```yaml
table_mappings:
  # Global prefix rule
  - id: "table-prefix-prod-001"
    content: "All production tables require 'PROD_' prefix"
    pattern: ".*"  # Applies to all tables
    prefix: "PROD_"
    confidence: 0.95

  # Specific mapping
  - id: "table-sales-001"
    content: "Sales table uses DWH_ prefix"
    schema_name: "Sales"
    actual_name: "DWH_Sales"
    prefix: "DWH_"
    confidence: 1.0

column_mappings:
  - id: "col-customer-id-001"
    content: "customer_id is actually cust_id"
    table_name: "Customers"
    schema_column: "customer_id"
    actual_column: "cust_id"
    confidence: 0.95

error_patterns:
  - id: "error-table-not-found-001"
    content: "Table not found usually means missing prefix"
    error_type: "table_not_found"
    error_pattern: "Table .* not found"
    suggested_fix: "Add 'PROD_' prefix"
    confidence: 0.90
```

### Auto-Learned Lessons (`memory/learned_lessons.json`)

Automatically created and updated:

```json
[
  {
    "id": "abc-123",
    "type": "table_mapping",
    "content": "Table 'Orders' maps to 'PROD_Orders' in database",
    "schema_name": "Orders",
    "actual_name": "PROD_Orders",
    "prefix": "PROD_",
    "confidence": 0.85,
    "source": "auto_learned",
    "times_applied": 15,
    "times_successful": 14,
    "learned_from_sessions": ["session-1", "session-2"],
    "created_at": "2024-01-15T10:30:00"
  }
]
```

## Workflow Integration

### 1. Query Processing with Memory

```python
from src import Text2SQLAgent

agent = Text2SQLAgent()

# Memory is automatically applied
result = agent.query("Show me top customers")

# Behind the scenes:
# 1. Identifies tables: ["Customers"]
# 2. Applies transformations: Customers → PROD_Customers
# 3. Retrieves relevant lessons for LLM context
# 4. Generates SQL with PROD_Customers
# 5. After success, learns new patterns
```

### 2. SQL Generator Integration

```python
# In SQL Generator (automatic)
def generate(self, user_query, identified_tables, ...):
    # Apply table transformations
    if self.apply_memory:
        transformations = self.table_mapper.transform_multiple(identified_tables)
        transformed_tables = list(transformations.values())

        # Get relevant lessons
        lessons = lesson_repository.get_relevant_lessons(
            user_query=user_query,
            identified_tables=identified_tables
        )

        # Include lessons in prompt
        prompt = PromptTemplates.sql_generation(
            ...,
            transformed_tables,  # Use transformed names
            lessons=lessons,     # Include as context
        )
```

### 3. Post-Query Learning

```python
# In Text2SQLAgent (automatic)
def query(self, user_query, ...):
    # Process query...

    # After successful completion:
    if success:
        lessons_learned = self.lesson_learner.learn_from_session(session)
        if lessons_learned:
            logger.info(f"Learned {len(lessons_learned)} new patterns")
```

## Learning Examples

### Example 1: Error Recovery

**Session Flow**:
1. Query: "Show all customers"
2. Attempt 1: `SELECT * FROM Customers` → Error: "Table not found"
3. Attempt 2: `SELECT * FROM PROD_Customers` → Success ✓

**Lesson Learned**:
```python
TableMappingLesson(
    schema_name="Customers",
    actual_name="PROD_Customers",
    prefix="PROD_",
    confidence=0.80,  # Initial
    source="auto_learned"
)
```

**Next Query**: System automatically uses `PROD_Customers`

### Example 2: User Correction

**Session Flow**:
1. Query: "Show sales data"
2. Generated: `SELECT * FROM Sales`
3. User correction: "Use DWH_ prefix for sales tables"

**Lesson Learned**:
```python
TableMappingLesson(
    schema_name="Sales",
    actual_name="DWH_Sales",
    prefix="DWH_",
    confidence=0.85,
    source="correction"
)
```

### Example 3: Confidence Increase

**Over Time**:
```
Use 1: Confidence = 0.80 → Success → Confidence = 0.82
Use 2: Confidence = 0.82 → Success → Confidence = 0.84
Use 3: Confidence = 0.84 → Success → Confidence = 0.86
...
Use 10: Confidence = 0.94 → Success → Confidence = 0.96
```

**After Failure**:
```
Use 11: Confidence = 0.96 → Failure → Confidence = 0.91 (drops by 0.05)
```

## Usage

### Basic Usage (Automatic)

```python
from src import Text2SQLAgent

# Initialize agent
agent = Text2SQLAgent()

# Query - memory is automatically applied
result = agent.query("Show me all customers")

print(result["sql"])
# Output: SELECT * FROM PROD_Customers ...
```

### Inspecting Lessons

```python
from src.memory import lesson_repository

# Get all lessons
lessons = lesson_repository.get_all_lessons()
print(f"Total lessons: {len(lessons)}")

# Get table-specific lessons
customer_lessons = lesson_repository.get_table_mapping_lessons("Customers")

for lesson in customer_lessons:
    print(f"{lesson.schema_name} → {lesson.actual_name}")
    print(f"Confidence: {lesson.confidence:.0%}")
    print(f"Success Rate: {lesson.success_rate:.0%}")
```

### Adding Manual Lessons

```python
from src.memory import lesson_repository, TableMappingLesson
import uuid

# Create new lesson
lesson = TableMappingLesson(
    id=str(uuid.uuid4()),
    content="Transaction table has TXN_ prefix",
    schema_name="Transactions",
    actual_name="TXN_Transactions",
    prefix="TXN_",
    confidence=0.95,
    source="manual",
)

# Add to repository
lesson_repository.add_lesson(lesson)
```

### Updating Lesson Stats

```python
# After using a lesson
lesson_repository.update_lesson_stats(
    lesson_id="abc-123",
    successful=True  # or False if failed
)
```

## Monitoring & Maintenance

### View Learned Patterns

```bash
# Check auto-learned lessons
cat memory/learned_lessons.json | jq '.[] | {content, confidence, success_rate}'
```

### Review Low-Confidence Lessons

```python
# Get lessons with low confidence
low_conf = [
    l for l in lesson_repository.get_all_lessons()
    if l.confidence < 0.70
]

# Review and either:
# 1. Delete if incorrect
# 2. Validate and promote to manual config
# 3. Wait for more data
```

### Promote Successful Patterns

When an auto-learned lesson has:
- High confidence (>0.90)
- High success rate (>95%)
- Many successful uses (>20)

Consider promoting it to `config/lessons_learned.yaml`:

```yaml
table_mappings:
  - id: "table-orders-validated"
    content: "Orders table confirmed to use PROD_ prefix"
    schema_name: "Orders"
    actual_name: "PROD_Orders"
    prefix: "PROD_"
    confidence: 1.0  # Now manually validated
```

## Best Practices

### 1. Start with Manual Rules

Configure known patterns in `config/lessons_learned.yaml`:

```yaml
table_mappings:
  - pattern: ".*"
    prefix: "PROD_"
    confidence: 0.95
```

### 2. Monitor Auto-Learning

Check `memory/learned_lessons.json` periodically:
- Validate high-usage patterns
- Remove incorrect patterns
- Promote successful patterns to manual config

### 3. Review After Errors

When queries fail:
- Check if wrong lesson was applied
- Update confidence or remove lesson
- Add correct pattern manually if needed

### 4. Confidence Thresholds

- **High (>0.90)**: Trusted, always apply
- **Medium (0.70-0.90)**: Apply but monitor
- **Low (<0.70)**: Review before promoting

### 5. Regular Maintenance

```python
# Monthly review script
lessons = lesson_repository.get_all_lessons()

# Find candidates for promotion
promote_candidates = [
    l for l in lessons
    if l.source == "auto_learned"
    and l.confidence > 0.90
    and l.success_rate > 0.95
    and l.times_applied > 20
]

print(f"Found {len(promote_candidates)} lessons ready for promotion")
```

## Troubleshooting

### Problem: Wrong transformation applied

**Solution**: Check confidence and usage stats
```python
info = mapper.get_transformation_info("TableName")
print(info)  # See which lesson is being applied
```

### Problem: Lesson not being learned

**Solution**: Check session for errors
```python
# Verify session completed successfully
# Check session.sql_attempts for error→success pattern
```

### Problem: Too many low-confidence lessons

**Solution**: Increase learning threshold
```python
# In LessonLearner
lesson = TableMappingLesson(
    ...,
    confidence=0.85,  # Increase from 0.80
)
```

## Demo Notebook

See comprehensive demonstration in:
```
examples/memory_system_demo.ipynb
```

The notebook covers:
- Viewing current lessons
- Table mapper in action
- Learning from errors
- Learning from corrections
- End-to-end agent integration
- Monitoring and management

## Architecture Benefits

✅ **Solves table prefix problem** - Automatically maps schema to actual tables

✅ **Learns continuously** - Builds knowledge from every query

✅ **Self-improving** - Confidence adjusts based on success/failure

✅ **Transparent** - All patterns are visible and manageable

✅ **No code changes** - Works automatically with existing agent

✅ **Two-tier flexibility** - Manual rules + auto-learning

## Future Enhancements

### Phase 2 (Planned)

- **Vector similarity search** for semantic pattern matching
- **Pattern generalization** from specific to general rules
- **Conflict detection** when multiple lessons contradict
- **Lesson expiration** for outdated patterns
- **A/B testing** for competing patterns

### Phase 3 (Planned)

- **Reinforcement learning** from user feedback
- **Pattern recommendations** for manual review
- **Cross-table pattern inference** (if A→PROD_A, then B→PROD_B)
- **Confidence decay** for unused patterns

## Summary

The Cross-Session Memory System enables the Text-to-SQL Agent to:

1. **Learn from mistakes** - Errors become lessons for future queries
2. **Remember corrections** - User instructions are saved and applied
3. **Build knowledge** - Patterns accumulate over time
4. **Self-improve** - Confidence adjusts based on outcomes
5. **Work transparently** - All learning is visible and manageable

This creates a system that gets smarter with every query, reducing errors and manual corrections over time.
