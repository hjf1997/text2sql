"""Prompt templates for LLM interactions."""

from typing import List, Optional
from ..schema import Schema, JoinCandidate


class PromptTemplates:
    """Collection of prompt templates for text-to-SQL agent."""

    @staticmethod
    def query_understanding(user_query: str, schema: Schema) -> str:
        """Generate prompt for understanding user query and identifying relevant tables.

        Args:
            user_query: The user's natural language query
            schema: The database schema

        Returns:
            Formatted prompt
        """
        return f"""You are a database query analyzer. Analyze the following user query and identify the relevant tables and columns needed to answer it.

USER QUERY:
{user_query}

DATABASE SCHEMA:
{schema.to_context_string()}

TASK:
1. Identify which tables are needed to answer the query
2. Identify which columns from those tables are needed
3. Determine if any joins between tables are required
4. Identify any filters or aggregations needed

Provide your analysis in the following format:

REQUIRED TABLES: [list of table names]
REQUIRED COLUMNS: [list of table.column names]
JOINS NEEDED: [yes/no]
FILTERS: [description of any filters]
AGGREGATIONS: [description of any aggregations]
REASONING: [your reasoning for the above selections]
"""

    @staticmethod
    def join_inference(
        table1: str,
        table2: str,
        schema: Schema,
        constraints: Optional[List[str]] = None,
    ) -> str:
        """Generate prompt for inferring joins between tables.

        Args:
            table1: First table name
            table2: Second table name
            schema: The database schema
            constraints: Optional list of constraint strings from corrections

        Returns:
            Formatted prompt
        """
        table1_obj = schema.get_table(table1)
        table2_obj = schema.get_table(table2)

        constraints_str = ""
        if constraints:
            constraints_str = f"""
MANDATORY CONSTRAINTS (from user corrections):
{chr(10).join(f"- {c}" for c in constraints)}

YOU MUST follow these constraints exactly.
"""

        return f"""You are a database schema analyst. Analyze the following two tables and infer the best way to join them.

{constraints_str}

TABLE 1: {table1}
{table1_obj.to_schema_string() if table1_obj else "Table not found"}

TABLE 2: {table2}
{table2_obj.to_schema_string() if table2_obj else "Table not found"}

TASK:
Identify potential join columns by analyzing:
1. Column names (exact or similar, e.g., customer_id vs cust_id)
2. Business names and descriptions
3. Data types (must be compatible)
4. Primary key indicators

For each potential join, provide:
- LEFT_TABLE: {table1}
- RIGHT_TABLE: {table2}
- LEFT_COLUMN: [column name]
- RIGHT_COLUMN: [column name]
- CONFIDENCE: [score from 0.0 to 1.0]
- REASONING: [why this is a good join]

If multiple joins are possible, list all of them ordered by confidence (highest first).
If no valid join can be inferred, respond with "NO_JOIN_FOUND" and explain why.
"""

    @staticmethod
    def sql_generation(
        user_query: str,
        schema: Schema,
        identified_tables: List[str],
        join_conditions: Optional[List[JoinCandidate]] = None,
        constraints: Optional[List[str]] = None,
        exploration_results: Optional[dict] = None,
        lessons: Optional[List] = None,
    ) -> str:
        """Generate prompt for SQL query generation.

        Args:
            user_query: The user's query
            schema: Database schema
            identified_tables: List of tables to use
            join_conditions: Optional join conditions
            constraints: Optional constraint strings from corrections
            exploration_results: Optional results from exploration queries
            lessons: Optional lessons learned from past queries

        Returns:
            Formatted prompt
        """
        # Format schema for relevant tables only
        relevant_schema = []
        for table_name in identified_tables:
            table = schema.get_table(table_name)
            if table:
                relevant_schema.append(table.to_schema_string())

        schema_str = "\n\n".join(relevant_schema)

        # Format joins
        joins_str = ""
        if join_conditions:
            joins_str = "\nJOIN CONDITIONS:\n"
            for join in join_conditions:
                joins_str += f"- {join.to_sql_condition()} (confidence: {join.confidence:.2f})\n"

        # Format constraints
        constraints_str = ""
        if constraints:
            constraints_str = f"""
MANDATORY CONSTRAINTS (from user corrections):
{chr(10).join(f"- {c}" for c in constraints)}

YOU MUST follow these constraints exactly in your SQL query.
"""

        # Format exploration results
        exploration_str = ""
        if exploration_results:
            exploration_str = "\nEXPLORATION RESULTS:\n"
            for key, result in exploration_results.items():
                exploration_str += f"{key}: {result}\n"

        # Format lessons learned
        lessons_str = ""
        if lessons:
            lessons_str = "\n## IMPORTANT: Lessons Learned from Past Queries\n\n"
            lessons_str += "The system has learned these patterns from previous successful queries:\n\n"

            # Group lessons by type
            table_lessons = [l for l in lessons if hasattr(l, 'schema_name')]
            column_lessons = [l for l in lessons if hasattr(l, 'schema_column')]
            error_lessons = [l for l in lessons if hasattr(l, 'error_pattern')]

            if table_lessons:
                lessons_str += "### Table Name Patterns:\n"
                for lesson in table_lessons[:5]:  # Top 5
                    lessons_str += f"- {lesson.content} (confidence: {lesson.confidence:.0%})\n"
                lessons_str += "\n"

            if column_lessons:
                lessons_str += "### Column Name Patterns:\n"
                for lesson in column_lessons[:5]:  # Top 5
                    lessons_str += f"- {lesson.content} (confidence: {lesson.confidence:.0%})\n"
                lessons_str += "\n"

            if error_lessons:
                lessons_str += "### Common Error Fixes:\n"
                for lesson in error_lessons[:3]:  # Top 3
                    lessons_str += f"- {lesson.content}: {lesson.suggested_fix}\n"
                lessons_str += "\n"

        return f"""You are an expert SQL query generator for BigQuery. Generate a SQL query to answer the user's question.

USER QUERY:
{user_query}
{lessons_str}
RELEVANT SCHEMA:
{schema_str}
{joins_str}
{constraints_str}
{exploration_str}

REQUIREMENTS:
1. Use BigQuery SQL syntax
2. Use proper table references (dataset.table if needed)
3. Include necessary joins, filters, and aggregations
4. Optimize for performance
5. IMPORTANT: Apply the learned patterns from "Lessons Learned" section above
6. Return only the SQL query without explanation

Generate the SQL query:
"""

    @staticmethod
    def sql_refinement(
        user_query: str,
        schema: Schema,
        identified_tables: List[str],
        previous_sql: str,
        error_message: str,
        attempt_number: int,
        join_conditions: Optional[List[JoinCandidate]] = None,
        constraints: Optional[List[str]] = None,
        lessons: Optional[List] = None,
    ) -> str:
        """Generate prompt for refining SQL after execution error.

        Args:
            user_query: The original user query
            schema: Database schema
            identified_tables: List of tables to use
            previous_sql: The SQL that failed
            error_message: The error message from BigQuery
            attempt_number: Current attempt number
            join_conditions: Optional join conditions
            constraints: Optional constraint strings from corrections
            lessons: Optional lessons learned from past queries

        Returns:
            Formatted prompt for SQL refinement
        """
        # Format schema for relevant tables only
        relevant_schema = []
        for table_name in identified_tables:
            table = schema.get_table(table_name)
            if table:
                relevant_schema.append(table.to_schema_string())

        schema_str = "\n\n".join(relevant_schema)

        # Format joins
        joins_str = ""
        if join_conditions:
            joins_str = "\nJOIN CONDITIONS:\n"
            for join in join_conditions:
                joins_str += f"- {join.to_sql_condition()} (confidence: {join.confidence:.2f})\n"

        # Format constraints
        constraints_str = ""
        if constraints:
            constraints_str = f"""
MANDATORY CONSTRAINTS (from user corrections):
{chr(10).join(f"- {c}" for c in constraints)}

YOU MUST follow these constraints exactly.
"""

        # Format lessons learned
        lessons_str = ""
        if lessons:
            lessons_str = "\n## Lessons Learned from Past Queries\n\n"
            lessons_str += "Apply these patterns from previous successful queries:\n\n"

            # Group lessons by type
            table_lessons = [l for l in lessons if hasattr(l, 'schema_name')]
            column_lessons = [l for l in lessons if hasattr(l, 'schema_column')]
            error_lessons = [l for l in lessons if hasattr(l, 'error_pattern')]

            if table_lessons:
                lessons_str += "### Table Name Patterns:\n"
                for lesson in table_lessons[:5]:  # Top 5
                    lessons_str += f"- {lesson.content} (confidence: {lesson.confidence:.0%})\n"
                lessons_str += "\n"

            if column_lessons:
                lessons_str += "### Column Name Patterns:\n"
                for lesson in column_lessons[:5]:  # Top 5
                    lessons_str += f"- {lesson.content} (confidence: {lesson.confidence:.0%})\n"
                lessons_str += "\n"

            if error_lessons:
                lessons_str += "### Common Error Fixes:\n"
                for lesson in error_lessons[:3]:  # Top 3
                    lessons_str += f"- {lesson.content}: {lesson.suggested_fix}\n"
                lessons_str += "\n"

        return f"""You are an expert SQL query generator for BigQuery. The previous SQL query failed with an error. Analyze the error and generate a CORRECTED SQL query.

USER QUERY:
{user_query}

ATTEMPT NUMBER: {attempt_number}

PREVIOUS SQL (FAILED):
```sql
{previous_sql}
```

ERROR MESSAGE:
{error_message}
{lessons_str}
RELEVANT SCHEMA:
{schema_str}
{joins_str}
{constraints_str}

TASK:
1. Analyze the error message carefully
2. Identify what went wrong in the previous SQL
3. Generate a CORRECTED SQL query that fixes the error
4. Common issues to check:
   - Table names (check if prefix is needed, e.g., PROD_, DWH_)
   - Column names (check if they exist in the schema)
   - Syntax errors (BigQuery-specific syntax)
   - Data type mismatches
   - Missing or incorrect JOIN conditions
   - Aggregation errors

REQUIREMENTS:
1. Use BigQuery SQL syntax
2. Fix the specific error mentioned above
3. Maintain the original intent of the user query
4. Apply learned patterns from "Lessons Learned" section if present
5. Return only the CORRECTED SQL query without explanation

Generate the corrected SQL query:
"""

    @staticmethod
    def ambiguity_detection(context: str, options: List[str]) -> str:
        """Generate prompt for detecting and explaining ambiguities.

        Args:
            context: Context describing the ambiguous situation
            options: List of possible options

        Returns:
            Formatted prompt
        """
        options_str = "\n".join(f"{i+1}. {opt}" for i, opt in enumerate(options))

        return f"""You are helping to resolve an ambiguity in query generation.

SITUATION:
{context}

POSSIBLE OPTIONS:
{options_str}

TASK:
1. Explain why this situation is ambiguous
2. Describe the implications of each option
3. Suggest which option might be most appropriate (if possible)
4. Phrase a clear question to ask the user

Provide your response in the following format:

EXPLANATION: [why this is ambiguous]
IMPLICATIONS:
- Option 1: [implications]
- Option 2: [implications]
...

RECOMMENDATION: [your suggestion or "UNCLEAR"]
USER_QUESTION: [clear question to ask the user]
"""

    @staticmethod
    def failure_summary(
        user_query: str,
        attempts: List[dict],
        issues: List[str],
    ) -> str:
        """Generate prompt for creating a failure summary.

        Args:
            user_query: Original user query
            attempts: List of attempts made
            issues: List of issues encountered

        Returns:
            Formatted prompt
        """
        attempts_str = "\n".join(
            f"Attempt {i+1}: {att.get('description', 'N/A')}"
            for i, att in enumerate(attempts)
        )

        issues_str = "\n".join(f"- {issue}" for issue in issues)

        return f"""You are helping to summarize why a query generation attempt failed.

ORIGINAL USER QUERY:
{user_query}

ATTEMPTS MADE:
{attempts_str}

ISSUES ENCOUNTERED:
{issues_str}

TASK:
Create a clear, concise summary for the user explaining:
1. What we tried to do
2. What went wrong
3. What recommendations you have (e.g., clarifications needed, manual intervention)

Provide a user-friendly summary:
"""

    @staticmethod
    def system_message() -> str:
        """Get the system message for the agent.

        Returns:
            System message string
        """
        return """You are an expert database assistant that helps users query BigQuery databases using natural language. You excel at:

1. Understanding user intent from natural language queries
2. Mapping user terms to database tables and columns using semantic understanding
3. Inferring relationships between tables even without explicit foreign keys
4. Generating correct and optimized BigQuery SQL
5. Asking clarifying questions when ambiguity exists
6. Learning from user corrections to improve your responses

You follow a systematic approach:
1. Understand what the user wants
2. Identify relevant tables and columns
3. Infer necessary joins between tables
4. Generate SQL step by step, exploring data if needed
5. Ask for clarification when multiple valid interpretations exist

You always prioritize accuracy and clarity over assumptions.
"""
