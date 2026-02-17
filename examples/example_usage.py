"""Example usage of the Text-to-SQL Agent system.

This script demonstrates the main features of the system including:
- Schema loading
- Join inference
- Session management
- Error handling
- Corrections
"""

import os
from pathlib import Path

# Add parent directory to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src import (
    settings,
    schema_loader,
    bigquery_client,
    llm_client,  # ConnectChain client (enterprise requirement)
    session_manager,
    AgentState,
    JoinInference,
    CorrectionParser,
)
from src.utils import (
    RetryExhaustedError,
    FatalError,
    AmbiguityError,
    setup_logger,
)

logger = setup_logger(__name__)


def example_1_basic_schema_loading():
    """Example 1: Load and explore schema."""
    print("\n" + "="*60)
    print("EXAMPLE 1: Schema Loading")
    print("="*60)

    # Load schema from directory (one Excel file per table)
    # Make sure SCHEMA_DIRECTORY is set in your .env file
    schema = schema_loader.load_from_excel()

    print(f"\nLoaded schema with {len(schema.tables)} tables:")
    for table_name, table in schema.tables.items():
        print(f"\n  Table: {table_name}")
        print(f"    Description: {table.description or 'N/A'}")
        print(f"    Columns: {len(table.columns)}")

        # Show first 3 columns
        for col in table.columns[:3]:
            print(f"      - {col.name} ({col.data_type.value}): {col.description or 'N/A'}")

        if len(table.columns) > 3:
            print(f"      ... and {len(table.columns) - 3} more columns")


def example_2_join_inference():
    """Example 2: Semantic join inference between tables."""
    print("\n" + "="*60)
    print("EXAMPLE 2: Join Inference")
    print("="*60)

    schema = schema_loader.load_from_excel()

    # Get first two tables for demonstration
    table_names = list(schema.tables.keys())
    if len(table_names) < 2:
        print("Need at least 2 tables in schema for join inference demo")
        return

    table1, table2 = table_names[0], table_names[1]

    print(f"\nInferring joins between: {table1} and {table2}")

    join_inference = JoinInference(schema)

    try:
        joins = join_inference.infer_joins(table1, table2)

        print(f"\nFound {len(joins)} possible join(s):")
        for i, join in enumerate(joins, 1):
            print(f"\n  Option {i}:")
            print(f"    Condition: {join.to_sql_condition()}")
            print(f"    Confidence: {join.confidence:.2%}")
            print(f"    Reasoning: {join.reasoning}")

    except AmbiguityError as e:
        print(f"\nAmbiguity detected: {e}")
        print(f"Options: {e.options}")
        print("\nUser would be prompted to choose one of these options")


def example_3_session_management():
    """Example 3: Create and manage sessions."""
    print("\n" + "="*60)
    print("EXAMPLE 3: Session Management")
    print("="*60)

    # Create a new session
    user_query = "Show me total sales by customer region for Q4 2025"
    session = session_manager.create_session(user_query)

    print(f"\nCreated session: {session.session_id}")
    print(f"Query: {session.original_query}")

    # Simulate agent work
    session.add_message("user", user_query)
    session.state_machine.transition_to(
        AgentState.QUERY_UNDERSTANDING,
        reason="Starting query analysis"
    )

    # Add some intermediate results
    session.identified_tables = ["Sales", "Customers"]
    session.add_intermediate_result(
        "identified_tables",
        {"tables": ["Sales", "Customers"], "confidence": 0.95}
    )

    # Increment iteration
    session.increment_iteration()

    # Save session
    session_manager.save_session(session)
    print(f"Session saved with status: {session.status}")

    # List all sessions
    print("\nAll sessions:")
    sessions = session_manager.list_sessions(limit=5)
    for s in sessions:
        print(f"  - {s['session_id'][:8]}... : {s['query'][:50]} [{s['status']}]")

    # Resume the session
    print(f"\nResuming session {session.session_id[:8]}...")
    resumed = session_manager.load_session(session.session_id)
    print(f"Resumed at state: {resumed.state_machine.current_state.value}")
    print(f"Iteration count: {resumed.iteration_count}")

    return session


def example_4_corrections():
    """Example 4: Handle user corrections."""
    print("\n" + "="*60)
    print("EXAMPLE 4: User Corrections")
    print("="*60)

    session = session_manager.create_session("Sample query for corrections")

    # Example correction inputs
    correction_examples = [
        "join Sales.customer_id with Customers.id",
        "region means Customers.geographic_area",
        "use the customer_id field from Sales, not account_number",
    ]

    print("\nParsing different correction formats:")
    for i, correction_text in enumerate(correction_examples, 1):
        print(f"\n  Correction {i}: \"{correction_text}\"")

        correction = CorrectionParser.parse(correction_text)
        print(f"    Type: {correction.correction_type.value}")
        print(f"    Content: {correction.content}")

        # Add to session
        session.add_correction(correction)

    print(f"\n  Session now has {len(session.corrections)} corrections")
    print(f"  Hard constraints: {session.hard_constraints}")


def example_5_bigquery_operations():
    """Example 5: BigQuery operations (query, validate, estimate cost)."""
    print("\n" + "="*60)
    print("EXAMPLE 5: BigQuery Operations")
    print("="*60)

    # Simple test query
    test_query = f"""
        SELECT
            table_name,
            row_count
        FROM `{settings.get('bigquery.project_id')}.{settings.get('bigquery.dataset')}.__TABLES__`
        LIMIT 5
    """

    print("\nTest Query:")
    print(test_query)

    try:
        # Validate query first
        print("\n1. Validating query...")
        validation = bigquery_client.validate_query(test_query)
        if validation["success"]:
            print(f"   ✓ Query is valid")
            print(f"   Bytes to process: {validation.get('bytes_processed', 0):,}")

        # Estimate cost
        print("\n2. Estimating cost...")
        cost_info = bigquery_client.estimate_query_cost(test_query)
        if cost_info["success"]:
            print(f"   Estimated cost: ${cost_info['estimated_cost_usd']:.6f}")
            print(f"   Data size: {cost_info['readable_size']}")

        # Execute query
        print("\n3. Executing query...")
        result = bigquery_client.execute_query(test_query, max_results=5)

        if result["success"]:
            print(f"   ✓ Query successful")
            print(f"   Rows returned: {result['row_count']}")
            print(f"   Bytes processed: {result['bytes_processed']:,}")

            print("\n   Results:")
            for row in result["rows"]:
                print(f"     {row}")
        else:
            print(f"   ✗ Query failed: {result['error']}")

    except Exception as e:
        print(f"\n   Error: {str(e)}")
        print("   Note: Make sure BigQuery credentials are properly configured")


def example_6_llm_with_retry():
    """Example 6: LLM calls with automatic retry."""
    print("\n" + "="*60)
    print("EXAMPLE 6: LLM with Retry Logic")
    print("="*60)

    session = session_manager.create_session("Test LLM call")

    print("\nMaking LLM call with automatic retry...")

    try:
        response = llm_client.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful database assistant."
                },
                {
                    "role": "user",
                    "content": "Explain what a database join is in one sentence."
                }
            ],
            session=session,
            temperature=0.0,
        )

        print(f"\n✓ Response received:")
        print(f"  {response}")

        print(f"\nSession messages: {len(session.messages)}")

    except RetryExhaustedError as e:
        print(f"\n✗ All retry attempts failed: {e}")
        print(f"   Session {session.session_id} has been saved")
        print(f"   You can resume it later when the service is available")

    except FatalError as e:
        print(f"\n✗ Non-recoverable error: {e}")
        print(f"   Check your ConnectChain configuration")


def example_7_end_to_end_workflow():
    """Example 7: Complete end-to-end workflow."""
    print("\n" + "="*60)
    print("EXAMPLE 7: End-to-End Workflow")
    print("="*60)

    user_query = "Show me the top 5 customers by total purchase amount"

    print(f"\nUser Query: \"{user_query}\"")
    print("\nWorkflow steps:")

    # Step 1: Create session
    print("\n1. Creating session...")
    session = session_manager.create_session(user_query)
    session.add_message("user", user_query)
    print(f"   Session ID: {session.session_id}")

    # Step 2: Load schema
    print("\n2. Loading schema...")
    schema = schema_loader.load_from_excel()
    session.schema_snapshot = schema.to_dict()
    print(f"   Loaded {len(schema.tables)} tables")

    # Step 3: Identify relevant tables (simulated)
    print("\n3. Identifying relevant tables...")
    session.state_machine.transition_to(AgentState.QUERY_UNDERSTANDING)
    session.identified_tables = ["Customers", "Orders"]  # Simulated
    print(f"   Identified: {session.identified_tables}")

    # Step 4: Infer joins
    print("\n4. Inferring table joins...")
    session.state_machine.transition_to(AgentState.JOIN_INFERENCE)
    join_inference = JoinInference(schema)

    try:
        if len(session.identified_tables) >= 2:
            joins = join_inference.infer_joins(
                session.identified_tables[0],
                session.identified_tables[1],
                session=session
            )
            session.inferred_joins = [j.to_dict() for j in joins]
            print(f"   Found {len(joins)} join(s)")
            if joins:
                print(f"   Best join: {joins[0].to_sql_condition()} (confidence: {joins[0].confidence:.2f})")
    except Exception as e:
        print(f"   Join inference skipped: {str(e)}")

    # Step 5: Generate SQL (simulated)
    print("\n5. Generating SQL query...")
    session.state_machine.transition_to(AgentState.GENERATING_SQL)

    # This would normally use LLM, here we show what it would look like
    generated_sql = """
    SELECT
        c.customer_name,
        SUM(o.amount) as total_amount
    FROM Customers c
    JOIN Orders o ON c.customer_id = o.customer_id
    GROUP BY c.customer_name
    ORDER BY total_amount DESC
    LIMIT 5
    """
    print(f"   Generated SQL:\n{generated_sql}")

    session.add_sql_attempt(generated_sql, success=True)

    # Step 6: Complete
    print("\n6. Workflow complete!")
    session.state_machine.transition_to(AgentState.COMPLETED)
    session_manager.save_session(session)

    print(f"\n   Final state: {session.state_machine.current_state.value}")
    print(f"   Iterations: {session.iteration_count}")
    print(f"   SQL attempts: {len(session.sql_attempts)}")


def main():
    """Run all examples."""
    print("\n" + "="*60)
    print("TEXT-TO-SQL AGENT - USAGE EXAMPLES")
    print("="*60)

    # Check if environment is configured
    try:
        settings.get("connectchain.config_path")
        settings.get("bigquery.project_id")
    except ValueError as e:
        print(f"\n❌ Configuration Error: {e}")
        print("\nPlease configure your environment:")
        print("1. Copy .env.example to .env")
        print("2. Fill in your ConnectChain and BigQuery credentials")
        print("3. Set SCHEMA_DIRECTORY to your schema directory (one Excel file per table)")
        return

    examples = [
        ("Schema Loading", example_1_basic_schema_loading),
        ("Join Inference", example_2_join_inference),
        ("Session Management", example_3_session_management),
        ("User Corrections", example_4_corrections),
        ("BigQuery Operations", example_5_bigquery_operations),
        ("LLM with Retry", example_6_llm_with_retry),
        ("End-to-End Workflow", example_7_end_to_end_workflow),
    ]

    print("\nAvailable examples:")
    for i, (name, _) in enumerate(examples, 1):
        print(f"  {i}. {name}")

    print("\nRunning examples...")

    for name, example_func in examples:
        try:
            example_func()
        except Exception as e:
            print(f"\n❌ Example '{name}' failed: {str(e)}")
            logger.exception(f"Example failed: {name}")

    print("\n" + "="*60)
    print("EXAMPLES COMPLETE")
    print("="*60)


if __name__ == "__main__":
    main()
