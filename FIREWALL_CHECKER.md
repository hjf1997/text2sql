# Firewall Checker for Schema Descriptions

## Overview

The Firewall Checker is an enterprise-focused feature that automatically detects and filters schema descriptions that may be blocked by corporate content filters or firewalls.

##Problem Statement

In enterprise environments, LLM prompts containing certain descriptions can be blocked by content filtering systems. The error typically states: **"The input was rejected because it appears to violate Company policy"**.

This prevents the text-to-SQL agent from functioning properly when schema descriptions contain flagged content.

## Solution

The Firewall Checker provides:
1. **Automatic Detection**: Tests each description by sending it to the LLM
2. **Smart Marking**: Flags descriptions as checked/blocked in the schema
3. **Safe Filtering**: Automatically removes blocked descriptions from prompts
4. **Resumable Checking**: Skips already-checked descriptions if interrupted

## How It Works

### Detection Method

For each description, the checker:
1. Sends a minimal test prompt containing the description to the LLM
2. Waits for response or error (default timeout: 2 seconds)
3. If error contains "violate Company policy" → marks as BLOCKED
4. If response received → marks as PASSED
5. Otherwise → marks as NOT CHECKED

### When It Runs

**Automatically during schema loading** (enabled by default):
```python
schema = schema_loader.load_from_excel(check_firewall=True)  # Default: True
```

**Manually when needed**:
```python
from src.schema import FirewallChecker

checker = FirewallChecker()
results = checker.check_schema(schema, skip_checked=True)
```

### Resilient to Interruptions

If checking is interrupted (network issue, timeout, etc.), the system:
- Saves check results for completed descriptions
- Skips already-checked descriptions on retry
- Only checks unchecked descriptions

## Usage

### 1. Load Schema with Firewall Check (Recommended)

```python
from src import schema_loader

# Automatically checks all descriptions
schema = schema_loader.load_from_excel(
    schema_dir="/path/to/schema",
    check_firewall=True  # Default: True
)
```

### 2. Disable Firewall Check (Not Recommended)

```python
# Skip checking (use only if you know descriptions are safe)
schema = schema_loader.load_from_excel(check_firewall=False)
```

### 3. Manual Firewall Check

```python
from src.schema import FirewallChecker

checker = FirewallChecker(timeout=2.0)

# Check entire schema
results = checker.check_schema(schema, skip_checked=True)

# Check specific table
table_results = checker.check_column_descriptions(
    table.columns,
    table_name="MyTable",
    skip_checked=True
)

# Check single description
result = checker.check_description(
    description="Some text to test",
    context="table: MyTable, column: MyColumn"
)
```

### 4. View Check Status

```python
# Check status for all descriptions
for table_name, table in schema.tables.items():
    print(f"Table: {table_name}")

    # Table description
    if table.firewall_checked:
        status = "BLOCKED" if table.firewall_blocked else "PASSED"
        print(f"  Description: {status}")

    # Column descriptions
    for col in table.columns:
        if col.firewall_checked:
            status = "BLOCKED" if col.firewall_blocked else "PASSED"
            print(f"    {col.name}: {status}")
```

### 5. Use Safe Descriptions in Prompts

The system automatically filters blocked descriptions when building prompts:

```python
from src.schema import get_safe_description, filter_schema_for_prompt

# Get safe description for a single column
safe_desc = get_safe_description(
    column,
    warn_if_unchecked=True,
    context="table: Orders, column: customer_id"
)

# Filter entire schema before using in prompts
filtered_schema = filter_schema_for_prompt(schema, warn_if_unchecked=True)
```

## Schema Attributes

The checker adds these attributes to schema objects:

### Table Attributes
- `firewall_checked` (bool): Whether table description was checked
- `firewall_blocked` (bool): Whether table description is blocked

### Column Attributes
- `firewall_checked` (bool): Whether column description was checked
- `firewall_blocked` (bool): Whether column description is blocked

## Warnings and Logging

### Warnings

**Using unchecked description in prompt:**
```
⚠️  Using unchecked description in prompt: table: Orders, column: customer_id.
Consider running firewall check first.
```

**Blocked description replaced:**
```
Replacing blocked description with empty string: table: Orders, column: status
```

### Log Levels

- **INFO**: Check progress and summary
- **WARNING**: Blocked descriptions and unchecked usage
- **DEBUG**: Individual check results
- **ERROR**: Check failures

## Configuration

### Timeout Setting

Adjust timeout for slower networks:
```python
checker = FirewallChecker(timeout=3.0)  # Default: 2.0 seconds
```

### Error Pattern

Customize the blocking error pattern if needed:
```python
# Default pattern
FirewallChecker.BLOCK_ERROR_PATTERN = "violate Company policy"
```

## Best Practices

1. **Always run firewall check during schema loading** (default behavior)
2. **Review blocked descriptions** and consider updating them in source Excel files
3. **Check logs** after loading to see summary of blocked descriptions
4. **Re-run check after schema updates** if descriptions change
5. **Use `skip_checked=True`** when re-running to avoid duplicate checks

## Example Output

```
============================================================
Starting firewall check for schema with 3 tables
============================================================

============================================================
Checking table: Customers
============================================================
Checking table description: Customers
[1/5] Checking column: Customers.customer_id
  ✓ Column 'customer_id' description passed
[2/5] Checking column: Customers.customer_name
  ✓ Column 'customer_name' description passed
[3/5] Checking column: Customers.email
  ⚠️  Column 'email' description blocked by firewall
[4/5] Checking column: Customers.phone
  ✓ Column 'phone' description passed
[5/5] Checking column: Customers.status
  ✓ Column 'status' description passed

============================================================
Firewall Check Summary
============================================================
Total checks performed: 16
Total descriptions blocked: 2
Block rate: 12.5%
```

## Troubleshooting

### Issue: Check takes too long

**Solution**: Reduce timeout or check fewer descriptions at once
```python
checker = FirewallChecker(timeout=1.0)
```

### Issue: Many descriptions blocked

**Solution**: Review and update descriptions in source Excel files

### Issue: Check interrupted

**Solution**: Re-run with `skip_checked=True` to resume
```python
checker.check_schema(schema, skip_checked=True)
```

### Issue: False positives

**Solution**: Manually set firewall_checked and firewall_blocked
```python
column.firewall_checked = True
column.firewall_blocked = False
```

## API Reference

### FirewallChecker

```python
class FirewallChecker:
    def __init__(self, timeout: float = 2.0)

    def check_description(
        self,
        description: str,
        context: str = ""
    ) -> Dict[str, bool]

    def check_column_descriptions(
        self,
        columns: List[Column],
        table_name: str = "Unknown",
        skip_checked: bool = True
    ) -> Dict[str, Dict]

    def check_table_description(
        self,
        table: Table,
        skip_checked: bool = True
    ) -> Dict

    def check_schema(
        self,
        schema: Schema,
        skip_checked: bool = True
    ) -> Dict[str, Dict]
```

### Utility Functions

```python
def get_safe_description(
    obj,  # Column or Table
    warn_if_unchecked: bool = True,
    context: str = ""
) -> str

def filter_schema_for_prompt(
    schema: Schema,
    warn_if_unchecked: bool = True
) -> Schema

def quick_check_description(
    description: str
) -> bool
```

## See Also

- [Schema Management](SCHEMA_FORMAT.md)
- [LLM Integration](ARCHITECTURE.md#llm-integration)
- [Error Handling](README.md#error-handling)
