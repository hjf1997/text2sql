# Schema Format Documentation

## Overview

The Text-to-SQL Agent loads database schema from a **directory containing multiple Excel files**, where:
- **Each Excel file represents ONE table**
- **Filename (without .xlsx) = Table name in BigQuery**
- Each file contains table metadata and column definitions

## Directory Structure

```
schema_directory/
├── Customers.xlsx          # Table name: Customers
├── Orders.xlsx             # Table name: Orders
├── Products.xlsx           # Table name: Products
├── Transactions.xlsx       # Table name: Transactions
└── ...
```

## Excel File Format

Each Excel file should contain **two sheets**:

### Sheet 1: "General Information" (Optional)

Contains table-level metadata. The system will look for these columns:

| Column Name | Required | Description |
|-------------|----------|-------------|
| Description | No | Table description |
| Business Context | No | Business context information |

**Example:**

| Description | Business Context |
|-------------|------------------|
| Customer master data containing all customer information | Primary customer table for CRM operations |

### Sheet 2: "Variables" (Required)

Contains column-level metadata. The system expects these columns:

| Column Name | Required | Description | Example Values |
|-------------|----------|-------------|----------------|
| Name | **Yes** | Column name | customer_id, order_date |
| Attribute Business Name | No | Business-friendly name | Customer ID, Order Date |
| Description | No | Column description | Unique identifier for customer |
| TYPE | **Yes** | Data type | STRING, INTEGER, DATE, FLOAT, BOOLEAN |
| PII | No | Is PII? | Y/N |
| Entitlement | No | Access control info | Public, Restricted |
| MANDATORY | No | Is mandatory? | Y/N |
| PARTITION | No | Is partition key? | Y/N |
| PRIMARY | No | Is primary key? | Y/N |

**Note:** The "Table Name" column is **NOT needed** in the Variables sheet, as the table name comes from the filename.

## Example: Customers.xlsx

### Sheet 1: General Information

| Description | Business Context |
|-------------|------------------|
| Customer master data | Core customer information for all business operations |

### Sheet 2: Variables

| Name | Attribute Business Name | Description | TYPE | PII | PRIMARY | MANDATORY |
|------|------------------------|-------------|------|-----|---------|-----------|
| customer_id | Customer ID | Unique customer identifier | INTEGER | N | Y | Y |
| customer_name | Customer Name | Full name of the customer | STRING | Y | N | Y |
| email | Email Address | Customer email | STRING | Y | N | N |
| region | Geographic Region | Customer's region | STRING | N | N | N |
| created_date | Account Creation Date | Date when account was created | DATE | N | N | Y |
| is_active | Active Status | Is customer active? | BOOLEAN | N | N | Y |

## Supported Data Types

The system recognizes these BigQuery data types:

- **STRING**: VARCHAR, TEXT, CHAR
- **INTEGER**: INT, INT64, BIGINT
- **FLOAT**: FLOAT64, DOUBLE, REAL
- **BOOLEAN**: BOOL
- **DATE**: DATE
- **DATETIME**: DATETIME
- **TIMESTAMP**: TIMESTAMP
- **NUMERIC**: NUMERIC, DECIMAL

## Configuration

Set the schema directory in your environment:

```bash
export SCHEMA_DIRECTORY=/path/to/your/schema_directory
```

Or in `.env` file:

```
SCHEMA_DIRECTORY=/path/to/your/schema_directory
```

## Loading Schema in Code

```python
from src import schema_loader

# Load all tables from directory
schema = schema_loader.load_from_excel(
    schema_dir="/path/to/schema_directory"
)

# Access tables
print(f"Loaded {len(schema.tables)} tables")
for table_name, table in schema.tables.items():
    print(f"  - {table_name}: {len(table.columns)} columns")
```

## Benefits of This Approach

1. **Clear Organization**: One file per table is easy to maintain
2. **No Ambiguity**: Filename = table name (used in BigQuery)
3. **Independent Updates**: Can update individual tables without affecting others
4. **Version Control Friendly**: Each table file can be tracked separately
5. **Scalable**: Easy to add new tables by adding new files

## Migration from Single-File Format

If you previously had a single Excel file with multiple tables:

1. Create a directory (e.g., `schema_tables/`)
2. For each table:
   - Create a new Excel file named `{table_name}.xlsx`
   - Copy the "General Information" row for that table to the new file's Sheet 1
   - Copy all "Variables" rows for that table to the new file's Sheet 2
   - Remove the "Table Name" column from Variables (not needed)
3. Update `SCHEMA_DIRECTORY` to point to the new directory

## Validation

The system will:
- ✓ Skip temporary Excel files (starting with `~$`)
- ✓ Validate that Variables sheet exists
- ✓ Warn if columns are missing required fields
- ✓ Use filename as the authoritative table name
- ✓ Cache the parsed schema for performance

## Troubleshooting

**Problem**: "No Excel files found in directory"
- **Solution**: Ensure Excel files have `.xlsx` or `.xls` extension

**Problem**: "Failed to read 'Variables' sheet"
- **Solution**: Ensure each Excel file has a sheet named "Variables"

**Problem**: Table name doesn't match BigQuery
- **Solution**: Rename the Excel file (filename = table name)

**Problem**: Columns missing
- **Solution**: Check that "Name" column exists in Variables sheet
