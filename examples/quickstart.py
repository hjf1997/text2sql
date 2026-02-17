"""Quick Start - Automated Text-to-SQL Agent

The simplest way to use the Text-to-SQL agent.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src import Text2SQLAgent

# Initialize agent (automatically loads schema from SCHEMA_DIRECTORY)
agent = Text2SQLAgent()

print(f"✓ Agent ready with {len(agent.schema.tables)} tables")
print(f"  Tables: {', '.join(agent.schema.tables.keys())}\n")

# Query 1: Simple query
print("Query 1: Show me all customers")
print("-" * 60)

result = agent.query(
    "Show me all customers",
    execute=False  # Set to True to run on BigQuery
)

if result["success"]:
    print("✓ SQL Generated:")
    print(result["sql"])
else:
    print(f"✗ Error: {result['message']}")

print("\n" + "=" * 60 + "\n")

# Query 2: More complex query with joins
print("Query 2: Top 5 customers by total order amount")
print("-" * 60)

result = agent.query(
    "Show me the top 5 customers by total order amount",
    execute=False
)

if result["success"]:
    print("✓ SQL Generated:")
    print(result["sql"])
    print("\n✓ Agent automatically:")
    print("  - Identified relevant tables")
    print("  - Inferred joins between tables")
    print("  - Generated optimized SQL")
else:
    print(f"✗ Error: {result['message']}")

print("\n" + "=" * 60 + "\n")

# Query 3: With execution (requires BigQuery setup)
print("Query 3: Execute on BigQuery")
print("-" * 60)

try:
    result = agent.query(
        "List all product categories",
        execute=True  # Actually run on BigQuery
    )

    if result["success"]:
        print("✓ SQL Generated and Executed:")
        print(result["sql"])
        print(f"\n✓ Results: {result.get('row_count', 0)} rows")

        # Show first few results
        if result.get("results", {}).get("rows"):
            print("\nFirst 5 rows:")
            for i, row in enumerate(result["results"]["rows"][:5], 1):
                print(f"  {i}. {row}")
    else:
        print(f"✗ Error: {result['message']}")

except Exception as e:
    print(f"⚠ BigQuery execution requires configuration:")
    print(f"  - GCP_PROJECT_ID")
    print(f"  - BIGQUERY_DATASET")
    print(f"  - GOOGLE_APPLICATION_CREDENTIALS")
    print(f"\nError: {e}")
