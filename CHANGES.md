# Schema Format Changes

## Summary

The schema format has been updated to use **a directory of Excel files** (one per table) instead of a single Excel file containing multiple tables.

## What Changed

### Before (Single File)
```
schema.xlsx
├── Sheet: "General Information"  (multiple tables listed)
└── Sheet: "Variables"             (all columns for all tables)
```

### After (Directory of Files)
```
schema_directory/
├── Customers.xlsx      # Table: Customers
│   ├── Sheet: "General Information"
│   └── Sheet: "Variables"
├── Orders.xlsx         # Table: Orders
│   ├── Sheet: "General Information"
│   └── Sheet: "Variables"
└── Products.xlsx       # Table: Products
    ├── Sheet: "General Information"
    └── Sheet: "Variables"
```

## Benefits

1. ✅ **Clear Table Names**: Filename = table name (no ambiguity)
2. ✅ **Easier Maintenance**: Update one table without touching others
3. ✅ **Better Organization**: Each table is self-contained
4. ✅ **Version Control**: Track changes per table
5. ✅ **Scalability**: Easy to add/remove tables

## Configuration Changes

### Environment Variable
- **Before**: `SCHEMA_EXCEL_PATH=/path/to/schema.xlsx`
- **After**: `SCHEMA_DIRECTORY=/path/to/schema_directory`

### Config File (config.yaml)
- **Before**: `schema.excel_path`
- **After**: `schema.schema_directory`

## Code Changes

### Loading Schema
```python
# Code remains the same - just point to directory instead of file
from src import schema_loader

schema = schema_loader.load_from_excel(
    schema_dir="/path/to/schema_directory"  # Directory instead of file
)
```

## Excel File Format Changes

### "Variables" Sheet
- **Removed**: "Table Name" column (not needed - filename is table name)
- **Kept**: All other columns remain the same

### Example: Customers.xlsx

**Sheet: Variables**

| Name | Description | TYPE | PII | PRIMARY |
|------|-------------|------|-----|---------|
| customer_id | Customer identifier | INTEGER | N | Y |
| customer_name | Customer name | STRING | Y | N |
| region | Geographic region | STRING | N | N |

**Note**: No "Table Name" column needed - the filename `Customers.xlsx` defines the table name as `Customers`.

## Migration Steps

If you have an existing single Excel file:

1. **Create directory**:
   ```bash
   mkdir schema_directory
   ```

2. **For each table**:
   - Create new file: `{table_name}.xlsx`
   - Copy table's row from "General Information" sheet to new file
   - Copy table's columns from "Variables" sheet to new file
   - **Remove** "Table Name" column from Variables sheet

3. **Update configuration**:
   ```bash
   # In .env file
   SCHEMA_DIRECTORY=schema_directory
   ```

4. **Test**:
   ```python
   from src import schema_loader
   schema = schema_loader.load_from_excel()
   print(f"Loaded {len(schema.tables)} tables")
   ```

## Example Migration

### Original File: schema.xlsx

**Sheet: General Information**
| Table Name | Description |
|-----------|-------------|
| Customers | Customer data |
| Orders | Order data |

**Sheet: Variables**
| Name | Table Name | TYPE |
|------|-----------|------|
| customer_id | Customers | INTEGER |
| customer_name | Customers | STRING |
| order_id | Orders | INTEGER |
| customer_id | Orders | INTEGER |

### After Migration

**File: Customers.xlsx**
- Sheet: General Information
  | Description |
  |-------------|
  | Customer data |

- Sheet: Variables
  | Name | TYPE |
  |------|------|
  | customer_id | INTEGER |
  | customer_name | STRING |

**File: Orders.xlsx**
- Sheet: General Information
  | Description |
  |-------------|
  | Order data |

- Sheet: Variables
  | Name | TYPE |
  |------|------|
  | order_id | INTEGER |
  | customer_id | INTEGER |

## Validation

After migration, the system will:
- ✅ Read all `.xlsx` files in the directory
- ✅ Use filename as table name
- ✅ Parse each file independently
- ✅ Combine into a single Schema object
- ✅ Cache for performance

## Troubleshooting

**Problem**: Schema not loading
- Check `SCHEMA_DIRECTORY` environment variable
- Ensure directory exists and contains `.xlsx` files
- Check file permissions

**Problem**: Table names incorrect
- Verify filenames match desired BigQuery table names
- Remove any special characters from filenames

**Problem**: Missing columns
- Check that each Excel file has "Variables" sheet
- Verify "Name" column exists in Variables sheet

## Documentation

See complete schema format documentation in:
- [SCHEMA_FORMAT.md](SCHEMA_FORMAT.md) - Detailed format specification
- [README.md](README.md) - Quick start guide
- [examples/](examples/) - Usage examples
