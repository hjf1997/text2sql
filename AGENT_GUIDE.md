# Automated Text-to-SQL Agent Guide

## Overview

The **Text2SQLAgent** is a fully automated system that converts natural language queries to SQL without manual intervention. Just provide a query and get SQL + results!

## Quick Start

```python
from src import Text2SQLAgent

# Initialize (automatically loads schema)
agent = Text2SQLAgent()

# Query and get results automatically
result = agent.query("Show me top 5 customers by sales")

print(result["sql"])      # Generated SQL
print(result["results"])  # Query results
```

That's it! **Everything else is automatic.**

## What Gets Automated

When you call `agent.query()`, the system automatically:

1. ✅ **Understands the query** using LLM
2. ✅ **Identifies required tables** from schema
3. ✅ **Identifies required columns**
4. ✅ **Infers joins** between tables (no foreign keys needed!)
5. ✅ **Generates SQL** using LLM
6. ✅ **Validates SQL** against BigQuery
7. ✅ **Executes query** (optional)
8. ✅ **Handles errors** with retry logic
9. ✅ **Saves session** for recovery

## Architecture

### Before: Manual Building Blocks

```python
# Manual approach (from Jupyter notebook)
schema = schema_loader.load_from_excel()
tables = ["Customers", "Orders"]  # Manual
joins = join_inference.infer_joins(tables[0], tables[1])  # Manual
sql = sql_generator.generate(...)  # Manual
result = bigquery_client.execute(sql)  # Manual
```

### After: Automated Orchestration

```python
# Automated approach (with Agent)
agent = Text2SQLAgent()
result = agent.query("Show top customers")  # Everything automatic!
```

## Agent Workflow

```
User Query
    ↓
┌──────────────────────────────────┐
│ 1. Query Understanding (LLM)    │
│    - Identify tables             │
│    - Identify columns            │
│    - Detect join requirements    │
└──────────────────────────────────┘
    ↓
┌──────────────────────────────────┐
│ 2. Join Inference (Automatic)   │
│    - Semantic matching           │
│    - LLM understanding           │
│    - Confidence scoring          │
└──────────────────────────────────┘
    ↓
┌──────────────────────────────────┐
│ 3. SQL Generation (LLM)         │
│    - Context from steps 1 & 2   │
│    - Apply constraints           │
│    - Generate BigQuery SQL       │
└──────────────────────────────────┘
    ↓
┌──────────────────────────────────┐
│ 4. Validation & Execution       │
│    - Validate syntax             │
│    - Estimate cost               │
│    - Execute on BigQuery         │
└──────────────────────────────────┘
    ↓
Results + Session Saved
```

## Initialization Options

### Option 1: Auto-load from Environment

```python
# Uses SCHEMA_DIRECTORY from .env
agent = Text2SQLAgent()
```

### Option 2: Specify Directory

```python
agent = Text2SQLAgent(
    schema_dir="/path/to/schema_directory"
)
```

### Option 3: Pre-loaded Schema

```python
from src import schema_loader

schema = schema_loader.load_from_excel(...)
agent = Text2SQLAgent(schema=schema)
```

### Option 4: Custom Configuration

```python
agent = Text2SQLAgent(
    schema_dir="/path/to/schemas",
    max_iterations=10,
    max_correction_attempts=5
)
```

## Query Methods

### Basic Query

```python
result = agent.query("Your natural language query")

# Returns:
{
    "success": True,
    "sql": "SELECT ...",
    "results": {...},  # If execute=True
    "row_count": 42
}
```

### Query Without Execution

```python
# Just generate SQL, don't execute
result = agent.query(
    "Show me sales data",
    execute=False
)

print(result["sql"])  # Review SQL before executing
```

### Query With Session

```python
# Get session for later resumption
result = agent.query(
    "Complex query here",
    execute=False,
    return_session=True
)

session_id = result["session"]["session_id"]
# Resume later or apply corrections
```

## Handling Ambiguity

When multiple valid interpretations exist:

```python
result = agent.query("Show sales with customer data")

if not result["success"] and result["error"] == "ambiguity":
    print("Ambiguity detected!")
    print(f"Options: {result['options']}")

    # User provides clarification
    result = agent.query_with_correction(
        session_id=result["session_id"],
        correction="Use customer_id to join tables"
    )
```

## Applying Corrections

### Natural Language Corrections

```python
result = agent.query_with_correction(
    session_id="abc-123",
    correction="Use customer_id from Orders table, not account_number"
)
```

### Structured Corrections

```python
correction = {
    "type": "join",
    "tables": ["Orders", "Customers"],
    "join_condition": "Orders.customer_id = Customers.id"
}

# Parse and apply
from src import CorrectionParser
parsed = CorrectionParser.parse_dict(correction)
# Corrections are automatically applied in query_with_correction
```

## Error Handling

The agent handles these scenarios automatically:

### 1. API Timeouts
- Automatic retry with exponential backoff (up to 5 attempts)
- Session saved on each attempt
- Recovery instructions provided

```python
try:
    result = agent.query("Complex query")
except RetryExhaustedError:
    # Session automatically saved
    print(f"API unavailable. Session saved for later.")
```

### 2. Ambiguous Queries
- Detects multiple valid interpretations
- Saves session and requests clarification
- Resumes with user correction

### 3. SQL Validation Errors
- Validates before execution
- Provides detailed error messages
- Suggests corrections

### 4. Maximum Iterations
- Prevents infinite loops
- Returns summary with recommendations

## Response Format

### Success Response

```python
{
    "success": True,
    "sql": "SELECT ...",
    "results": {
        "rows": [...],
        "row_count": 10,
        "total_rows": 10,
        "bytes_processed": 1024,
        "schema": [...]
    },
    "row_count": 10
}
```

### Ambiguity Response

```python
{
    "success": False,
    "error": "ambiguity",
    "message": "Multiple joins possible...",
    "options": [
        "Option 1: Orders.customer_id = Customers.id",
        "Option 2: Orders.account_id = Customers.account"
    ],
    "session_id": "abc-123"
}
```

### Failure Response

```python
{
    "success": False,
    "error": "processing_failed",
    "message": "Error details...",
    "failure_summary": {
        "user_query": "...",
        "identified_tables": [...],
        "attempted_iterations": 3,
        "recommendations": [
            "Try rephrasing the query...",
            "Specify which tables to use..."
        ]
    },
    "session_id": "abc-123"
}
```

## Advanced Usage

### Custom Prompts

The agent uses `PromptTemplates` which can be customized:

```python
from src.llm import PromptTemplates

# View or modify prompts
PromptTemplates.query_understanding(query, schema)
PromptTemplates.sql_generation(query, schema, tables, joins)
```

### Access Intermediate Results

```python
result = agent.query("...", return_session=True)

session = result["session"]
print(session.identified_tables)      # Tables found
print(session.inferred_joins)         # Joins inferred
print(session.intermediate_results)   # Step-by-step results
print(session.state_machine.current_state)  # Current state
```

### Session Management

```python
from src import session_manager

# List all sessions
sessions = session_manager.list_sessions()

# Load specific session
session = session_manager.load_session("session-id")

# Resume processing
result = agent.query_with_correction(
    session_id=session.session_id,
    correction="clarification here"
)
```

## Configuration

### Environment Variables

```bash
# LLM Provider (ConnectChain recommended for AMEX enterprise)
USE_CONNECTCHAIN=true  # or false for direct Azure OpenAI

# Required
SCHEMA_DIRECTORY=/path/to/schema_directory
GCP_PROJECT_ID=...
BIGQUERY_DATASET=...

# For ConnectChain (when USE_CONNECTCHAIN=true)
CONFIG_PATH=connectchain.config.yml
WORKDIR=.
AZURE_OPENAI_ENDPOINT=https://...

# For Direct Azure OpenAI (when USE_CONNECTCHAIN=false)
AZURE_OPENAI_ENDPOINT=https://...
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_DEPLOYMENT=gpt-4

# Optional
GOOGLE_APPLICATION_CREDENTIALS=/path/to/creds.json
```

### ConnectChain Configuration

**For AMEX enterprise deployment**, ConnectChain is recommended. It provides:
- ✅ EAS (Enterprise Auth Service) integration
- ✅ Proxy configuration support
- ✅ Certificate management

See **[CONNECTCHAIN_SETUP.md](CONNECTCHAIN_SETUP.md)** for detailed setup instructions.

### Configuration File

Edit `src/config/config.yaml`:

```yaml
llm:
  use_connectchain: true  # Enable ConnectChain

connectchain:
  config_path: "connectchain.config.yml"
  model_index: "1"
  temperature: 0.0
  max_tokens: 4000

agent:
  max_iterations: 5
  max_correction_attempts: 3
  enable_exploration_queries: true
  confidence_threshold: 0.75
```

## Examples

### Example 1: Simple Query

```python
agent = Text2SQLAgent()

result = agent.query("List all customers")
# Automatically identifies Customers table
# Generates: SELECT * FROM dataset.Customers
```

### Example 2: Aggregation

```python
result = agent.query("What's the total revenue by month?")
# Identifies Orders or Sales table
# Adds GROUP BY and aggregation
# Generates proper date extraction
```

### Example 3: Multi-Table Join

```python
result = agent.query("Show customer names with their order counts")
# Automatically:
# 1. Identifies Customers and Orders tables
# 2. Infers join on customer_id
# 3. Adds COUNT aggregation
# 4. Groups by customer name
```

### Example 4: Complex Filters

```python
result = agent.query(
    "Top 10 customers in North region with orders over $1000"
)
# Handles multiple filters and TOP N automatically
```

## Comparison: Manual vs Automated

### Manual Workflow (Jupyter Notebook)

```python
# ~15 lines of code
schema = schema_loader.load_from_excel()
understanding = query_understanding.analyze(query)
tables = understanding["tables"]  # Manual inspection

if len(tables) >= 2:
    joins = join_inference.infer_joins(tables[0], tables[1])
    if len(joins) > 1:
        # Manual choice needed
        selected_join = joins[0]

sql = sql_generator.generate(query, tables, [selected_join])
validation = bigquery_client.validate_query(sql)
if validation["success"]:
    result = bigquery_client.execute_query(sql)
```

### Automated Workflow (Agent)

```python
# 2 lines of code
agent = Text2SQLAgent()
result = agent.query("Your query here")
```

**Benefits:**
- ✅ 87% less code
- ✅ No manual decisions needed
- ✅ Automatic error handling
- ✅ Built-in recovery
- ✅ Session persistence

## Troubleshooting

### Agent fails to identify tables
- **Solution**: Rephrase query with more specific table/entity names
- **Example**: Instead of "show data", use "show customer data"

### Ambiguity errors persist
- **Solution**: Provide explicit join or column mapping
- **Example**: "join using customer_id column"

### SQL validation fails
- **Solution**: Check that table names in schema match BigQuery
- **Solution**: Verify column types in schema

### API timeouts
- **Solution**: Agent automatically retries 5 times
- **Solution**: Check Azure OpenAI service status
- **Solution**: Resume from saved session when service is restored

## Best Practices

1. **Use descriptive queries**: "Show customers from California" vs "Show data"
2. **Provide context**: Mention entity types (customers, orders, products)
3. **Review SQL first**: Use `execute=False` to review before running
4. **Monitor costs**: Use `bigquery_client.estimate_query_cost(sql)`
5. **Save important sessions**: Keep `session_id` for future reference
6. **Apply corrections iteratively**: Start general, refine with specifics

## Performance Tips

1. Schema caching is enabled by default
2. Sessions are saved incrementally
3. LLM calls use temperature=0 for consistency
4. BigQuery dry-run validates before execution
5. Exploration queries limit results to 100 rows

## Next Steps

- Try the examples: `python examples/quickstart.py`
- Read detailed demos: `python examples/automated_agent_demo.py`
- Explore the API: Check `src/agent/orchestrator.py`
- Customize prompts: See `src/llm/prompts.py`

## Summary

The **Text2SQLAgent** provides a **complete, production-ready** solution for text-to-SQL conversion:

✅ **Fully Automated** - No manual steps
✅ **Intelligent** - Uses LLM for understanding
✅ **Resilient** - Built-in error handling
✅ **Recoverable** - Session persistence
✅ **Flexible** - Handles corrections
✅ **Production-Ready** - Enterprise features

**Get started in 2 lines:**

```python
agent = Text2SQLAgent()
result = agent.query("Your query here")
```
