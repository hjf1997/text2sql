"""Automated Text-to-SQL Agent Demo

This demo shows the FULLY AUTOMATED workflow where you simply:
1. Provide a natural language query
2. Get SQL and results automatically

No manual table identification or join inference needed!
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src import Text2SQLAgent, settings
from src.utils import setup_logger
import json

logger = setup_logger(__name__)


def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_result(result: dict):
    """Print query result in a formatted way."""
    if result["success"]:
        print("✅ SUCCESS!")
        print(f"\n📝 Generated SQL:")
        print("-" * 70)
        print(result["sql"])
        print("-" * 70)

        if "results" in result:
            print(f"\n📊 Results: {result.get('row_count', 0)} rows")
            if result.get("results", {}).get("rows"):
                print("\nFirst few rows:")
                for i, row in enumerate(result["results"]["rows"][:5], 1):
                    print(f"  {i}. {row}")
    else:
        print(f"❌ FAILED: {result.get('error')}")
        print(f"Message: {result.get('message')}")

        if "failure_summary" in result:
            print("\n📋 Failure Summary:")
            summary = result["failure_summary"]
            print(f"  - Identified tables: {summary.get('identified_tables', [])}")
            print(f"  - Iterations: {summary.get('attempted_iterations', 0)}")
            print(f"  - Recommendations:")
            for rec in summary.get("recommendations", []):
                print(f"    • {rec}")


def demo_basic_queries():
    """Demo 1: Basic automated queries."""
    print_section("DEMO 1: Basic Automated Queries")

    print("\n🤖 Initializing Text-to-SQL Agent...")
    print("   (This automatically loads schema from directory)")

    try:
        # Initialize agent - it loads schema automatically
        agent = Text2SQLAgent()

        print(f"\n✅ Agent initialized with {len(agent.schema.tables)} tables")
        print(f"   Tables: {list(agent.schema.tables.keys())}")

    except Exception as e:
        print(f"\n⚠️  Could not initialize agent: {e}")
        print("\n💡 To run this demo:")
        print("   1. Set SCHEMA_DIRECTORY in your .env file")
        print("   2. Place your Excel schema files in that directory")
        print("   3. Configure Azure OpenAI credentials")
        print("\nFor now, we'll show what the output would look like...")
        return

    # Example queries
    queries = [
        "Show me all customers",
        "What are the top 5 products by sales?",
        "List customers from the North region",
        "Show total revenue by month for 2024",
    ]

    for i, query in enumerate(queries, 1):
        print(f"\n\n{'─' * 70}")
        print(f"Query {i}: \"{query}\"")
        print(f"{'─' * 70}")

        try:
            # THIS IS IT - Just call query()!
            # Everything else happens automatically:
            # - Identifies tables
            # - Infers joins
            # - Generates SQL
            result = agent.query(query, execute=False)  # Set execute=True to run on BigQuery

            print_result(result)

        except Exception as e:
            print(f"❌ Error: {e}")


def demo_with_execution():
    """Demo 2: Query with actual BigQuery execution."""
    print_section("DEMO 2: Automated Query with Execution")

    print("\n🎯 This example executes the query on BigQuery")

    try:
        agent = Text2SQLAgent()

        query = "Show me the top 10 customers by total orders"
        print(f"\n💬 Query: \"{query}\"")
        print("\n🔄 Processing...")
        print("   1. Understanding query with LLM...")
        print("   2. Identifying relevant tables...")
        print("   3. Inferring joins automatically...")
        print("   4. Generating SQL...")
        print("   5. Validating SQL...")
        print("   6. Executing on BigQuery...")

        # Automatic execution
        result = agent.query(query, execute=True)

        print_result(result)

    except Exception as e:
        print(f"\n⚠️  {e}")
        print("\n💡 This requires:")
        print("   - BigQuery credentials configured")
        print("   - GCP_PROJECT_ID and BIGQUERY_DATASET set")


def demo_with_corrections():
    """Demo 3: Handling ambiguity and corrections."""
    print_section("DEMO 3: Automated Handling of Ambiguity")

    print("\n🔀 When ambiguity is detected, the agent automatically:")
    print("   1. Pauses execution")
    print("   2. Saves session state")
    print("   3. Asks for user clarification")
    print("   4. Resumes with correction")

    try:
        agent = Text2SQLAgent()

        # Query that might have ambiguous joins
        query = "Show me sales data with customer information"
        print(f"\n💬 Query: \"{query}\"")

        # First attempt
        result = agent.query(query, execute=False, return_session=True)

        if result["success"]:
            print_result(result)
        else:
            if result["error"] == "ambiguity":
                print(f"\n⚠️  Ambiguity detected!")
                print(f"Message: {result['message']}")
                print(f"\nOptions:")
                for i, option in enumerate(result.get("options", []), 1):
                    print(f"  {i}. {option}")

                # Simulate user providing correction
                print(f"\n👤 User provides correction: 'Use customer_id to join tables'")

                correction_result = agent.query_with_correction(
                    session_id=result["session_id"],
                    correction="Use customer_id to join tables",
                    execute=False
                )

                print(f"\n🔄 Reprocessing with correction...")
                print_result(correction_result)
            else:
                print_result(result)

    except Exception as e:
        print(f"\n⚠️  {e}")


def demo_session_resumption():
    """Demo 4: Session persistence and resumption."""
    print_section("DEMO 4: Session Persistence & Recovery")

    print("\n💾 Sessions are automatically saved and can be resumed")
    print("   Useful when:")
    print("   - API calls timeout")
    print("   - User wants to review before executing")
    print("   - Need to apply corrections later")

    try:
        agent = Text2SQLAgent()

        query = "Analyze customer purchase patterns"
        print(f"\n💬 Query: \"{query}\"")

        # Generate SQL without executing
        result = agent.query(query, execute=False, return_session=True)

        if result["success"]:
            print(f"\n✅ SQL generated and session saved")
            print(f"Session ID: {result['session']['session_id']}")
            print(f"\n📝 Generated SQL:")
            print(result["sql"])

            print(f"\n💡 You can now:")
            print(f"   - Review the SQL")
            print(f"   - Execute it later")
            print(f"   - Apply corrections if needed")
            print(f"\nTo execute later:")
            print(f"  result = agent.query_with_correction(")
            print(f"      session_id='{result['session']['session_id'][:16]}...',")
            print(f"      correction='',  # or provide correction")
            print(f"      execute=True")
            print(f"  )")

    except Exception as e:
        print(f"\n⚠️  {e}")


def demo_comparison():
    """Demo 5: Comparison with manual approach."""
    print_section("DEMO 5: Automated vs Manual Approach")

    print("\n🔄 BEFORE (Manual - from Jupyter notebook):")
    print("─" * 70)
    print("""
    # Step 1: Load schema (manual)
    schema = schema_loader.load_from_excel()

    # Step 2: Identify tables (manual)
    tables = ["Customers", "Orders"]  # You decide

    # Step 3: Infer joins (manual)
    joins = join_inference.infer_joins(tables[0], tables[1])

    # Step 4: Generate SQL (manual)
    sql = generate_sql(...)

    # Step 5: Execute (manual)
    result = bigquery_client.execute(sql)
    """)

    print("\n✨ AFTER (Automated - with Agent):")
    print("─" * 70)
    print("""
    # That's it - ONE line!
    agent = Text2SQLAgent()
    result = agent.query("Show me top customers by orders")

    # Everything happens automatically:
    # ✓ Schema loading
    # ✓ Table identification via LLM
    # ✓ Join inference
    # ✓ SQL generation via LLM
    # ✓ Validation & execution
    """)

    print("\n💡 The agent handles:")
    print("   ✓ Multi-table queries automatically")
    print("   ✓ Complex joins without manual specification")
    print("   ✓ Ambiguity detection and resolution")
    print("   ✓ Error recovery with retries")
    print("   ✓ Session persistence")
    print("   ✓ Correction application")


def main():
    """Run all demos."""
    print("\n" + "=" * 70)
    print("  🤖 AUTOMATED TEXT-TO-SQL AGENT DEMO")
    print("=" * 70)

    print("\nThis demo shows the FULLY AUTOMATED workflow!")
    print("No manual table identification or join inference needed.")

    # Check configuration
    try:
        settings.get("azure_openai.endpoint")
        settings.get("bigquery.project_id")
        config_ok = True
    except ValueError:
        config_ok = False

    if not config_ok:
        print("\n⚠️  Configuration incomplete")
        print("\nTo run these demos:")
        print("1. Configure .env file with:")
        print("   - AZURE_OPENAI_ENDPOINT")
        print("   - AZURE_OPENAI_API_KEY")
        print("   - GCP_PROJECT_ID")
        print("   - BIGQUERY_DATASET")
        print("   - SCHEMA_DIRECTORY")
        print("\n2. Run: python examples/automated_agent_demo.py")
        print("\nFor now, showing what the interface looks like...")

    # Run demos
    demos = [
        ("Basic Automated Queries", demo_basic_queries),
        ("Query with Execution", demo_with_execution),
        ("Ambiguity & Corrections", demo_with_corrections),
        ("Session Persistence", demo_session_resumption),
        ("Comparison: Manual vs Automated", demo_comparison),
    ]

    print("\n\n📋 Available demos:")
    for i, (name, _) in enumerate(demos, 1):
        print(f"   {i}. {name}")

    print("\n🚀 Running demos...\n")

    for name, demo_func in demos:
        try:
            demo_func()
        except Exception as e:
            print(f"\n❌ Demo '{name}' error: {e}")
            logger.exception(f"Demo failed: {name}")

    print("\n\n" + "=" * 70)
    print("  ✅ DEMO COMPLETE")
    print("=" * 70)

    print("\n📚 Key Takeaways:")
    print("   1. Agent handles EVERYTHING automatically")
    print("   2. Just provide natural language → get SQL + results")
    print("   3. Built-in error handling and recovery")
    print("   4. Session persistence for interrupted workflows")
    print("   5. Automatic ambiguity detection and correction")

    print("\n💡 Quick Start:")
    print("""
    from src import Text2SQLAgent

    agent = Text2SQLAgent()
    result = agent.query("Your natural language query here")

    print(result["sql"])      # Generated SQL
    print(result["results"])  # Query results
    """)


if __name__ == "__main__":
    main()
