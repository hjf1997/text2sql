"""Firewall checker for schema descriptions.

This module checks if schema descriptions pass through enterprise firewall/content filters.
It sends test prompts to the LLM and detects if they are blocked by company policy.
"""

import time
from typing import Dict, List, Optional
from ..llm import llm_client
from ..utils import setup_logger

logger = setup_logger(__name__)


class FirewallChecker:
    """Checks if schema descriptions are blocked by enterprise firewall."""

    # Error message pattern that indicates firewall blocking
    BLOCK_ERROR_PATTERN = "violate Company policy"

    # Timeout for checking (seconds) - if no error within this time, consider it passed
    DEFAULT_TIMEOUT = 2.0

    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        """Initialize firewall checker.

        Args:
            timeout: Timeout in seconds to wait for response (default: 2.0)
        """
        self.timeout = timeout
        self.checked_count = 0
        self.blocked_count = 0

    def check_description(self, description: str, context: str = "") -> Dict[str, bool]:
        """Check if a single description passes the firewall.

        Args:
            description: The description text to check
            context: Optional context (e.g., "table: TableName, column: ColumnName")

        Returns:
            Dictionary with:
                - checked: True if check was completed
                - blocked: True if description is blocked by firewall
                - error: Error message if blocked
        """
        if not description or not description.strip():
            # Empty descriptions don't need checking
            return {"checked": True, "blocked": False, "error": None}

        # Create a minimal test prompt with the description
        test_prompt = f"Analyze this data field description: {description}"

        try:
            logger.debug(f"Checking description: {description[:50]}... (context: {context})")

            # Send test prompt to LLM
            start_time = time.time()
            response = llm_client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a data analyst. Respond with 'OK' if you understand."
                    },
                    {
                        "role": "user",
                        "content": test_prompt
                    }
                ],
                session=None,  # No session needed for firewall check
            )
            elapsed = time.time() - start_time

            # If we got a response, it passed the firewall
            self.checked_count += 1
            logger.debug(f"✓ Description passed firewall check (took {elapsed:.2f}s)")
            return {"checked": True, "blocked": False, "error": None}

        except Exception as e:
            error_str = str(e)

            # Check if this is a firewall block error
            if self.BLOCK_ERROR_PATTERN.lower() in error_str.lower():
                self.checked_count += 1
                self.blocked_count += 1
                logger.warning(f"✗ Description blocked by firewall: {description[:50]}...")
                return {"checked": True, "blocked": True, "error": error_str}
            else:
                # Other errors - consider as unchecked
                logger.error(f"Error during firewall check: {error_str}")
                return {"checked": False, "blocked": False, "error": error_str}

    def check_column_descriptions(
        self,
        columns: List,
        table_name: str = "Unknown",
        skip_checked: bool = True,
    ) -> Dict[str, Dict]:
        """Check firewall for all column descriptions in a table.

        Args:
            columns: List of Column objects to check
            table_name: Name of the table (for logging)
            skip_checked: Skip columns that have already been checked

        Returns:
            Dictionary mapping column names to check results
        """
        results = {}
        total = len(columns)

        logger.info(f"Starting firewall check for {total} columns in table '{table_name}'")

        for idx, column in enumerate(columns, 1):
            col_name = column.name

            # Skip if already checked and skip_checked is True
            if skip_checked and hasattr(column, 'firewall_checked') and column.firewall_checked:
                logger.debug(f"[{idx}/{total}] Skipping {col_name} (already checked)")
                results[col_name] = {
                    "checked": True,
                    "blocked": getattr(column, 'firewall_blocked', False),
                    "skipped": True
                }
                continue

            # Check description
            logger.info(f"[{idx}/{total}] Checking column: {table_name}.{col_name}")
            description = column.description or ""
            context = f"table: {table_name}, column: {col_name}"

            result = self.check_description(description, context)
            results[col_name] = result

            # Update column attributes
            column.firewall_checked = result["checked"]
            column.firewall_blocked = result["blocked"]

            if result["blocked"]:
                logger.warning(
                    f"  ⚠️  Column '{col_name}' description blocked by firewall"
                )
            elif result["checked"]:
                logger.debug(f"  ✓ Column '{col_name}' description passed")

            # Small delay between checks to avoid rate limiting
            time.sleep(0.1)

        logger.info(
            f"Firewall check complete for table '{table_name}': "
            f"{self.checked_count} checked, {self.blocked_count} blocked"
        )

        return results

    def check_table_description(self, table, skip_checked: bool = True) -> Dict:
        """Check firewall for table-level description.

        Args:
            table: Table object to check
            skip_checked: Skip if already checked

        Returns:
            Check result dictionary
        """
        # Skip if already checked
        if skip_checked and hasattr(table, 'firewall_checked') and table.firewall_checked:
            logger.debug(f"Skipping table '{table.name}' (already checked)")
            return {
                "checked": True,
                "blocked": getattr(table, 'firewall_blocked', False),
                "skipped": True
            }

        logger.info(f"Checking table description: {table.name}")
        description = table.description or ""
        context = f"table: {table.name}"

        result = self.check_description(description, context)

        # Update table attributes
        table.firewall_checked = result["checked"]
        table.firewall_blocked = result["blocked"]

        return result

    def check_schema(self, schema, skip_checked: bool = True) -> Dict[str, Dict]:
        """Check firewall for all descriptions in a schema.

        Args:
            schema: Schema object to check
            skip_checked: Skip items that have already been checked

        Returns:
            Dictionary with check results for all tables and columns
        """
        logger.info(f"Starting firewall check for schema with {len(schema.tables)} tables")

        all_results = {}

        for table_name, table in schema.tables.items():
            logger.info(f"\n{'='*60}")
            logger.info(f"Checking table: {table_name}")
            logger.info(f"{'='*60}")

            table_results = {
                "table_description": self.check_table_description(table, skip_checked),
                "columns": self.check_column_descriptions(
                    table.columns,
                    table_name,
                    skip_checked
                )
            }

            all_results[table_name] = table_results

        # Summary
        logger.info(f"\n{'='*60}")
        logger.info("Firewall Check Summary")
        logger.info(f"{'='*60}")
        logger.info(f"Total checks performed: {self.checked_count}")
        logger.info(f"Total descriptions blocked: {self.blocked_count}")
        logger.info(f"Block rate: {(self.blocked_count/self.checked_count*100) if self.checked_count > 0 else 0:.1f}%")

        return all_results


def get_safe_description(
    obj,
    warn_if_unchecked: bool = True,
    context: str = ""
) -> str:
    """Get safe description for use in prompts, filtering out blocked descriptions.

    Args:
        obj: Object with description attribute (Column or Table)
        warn_if_unchecked: Log warning if description hasn't been checked
        context: Context string for warning message

    Returns:
        Safe description string (empty if blocked or not safe)
    """
    description = getattr(obj, 'description', '') or ''

    if not description:
        return ''

    # Check if firewall check was performed
    firewall_checked = getattr(obj, 'firewall_checked', False)
    firewall_blocked = getattr(obj, 'firewall_blocked', False)

    if not firewall_checked:
        if warn_if_unchecked:
            logger.warning(
                f"⚠️  Using unchecked description in prompt: {context}. "
                f"Consider running firewall check first."
            )
        return description

    if firewall_blocked:
        logger.info(
            f"Replacing blocked description with empty string: {context}"
        )
        return ''

    return description


def filter_schema_for_prompt(schema, warn_if_unchecked: bool = True):
    """Filter schema descriptions before using in prompts.

    This function returns a modified version of the schema with:
    - Blocked descriptions replaced with empty strings
    - Warnings for unchecked descriptions

    Args:
        schema: Schema object to filter
        warn_if_unchecked: Log warnings for unchecked descriptions

    Returns:
        Filtered schema object (modifies in place and returns same object)
    """
    for table_name, table in schema.tables.items():
        # Filter table description
        safe_table_desc = get_safe_description(
            table,
            warn_if_unchecked,
            f"table: {table_name}"
        )
        table._original_description = table.description
        table.description = safe_table_desc

        # Filter column descriptions
        for column in table.columns:
            safe_col_desc = get_safe_description(
                column,
                warn_if_unchecked,
                f"table: {table_name}, column: {column.name}"
            )
            column._original_description = column.description
            column.description = safe_col_desc

    return schema


# Convenience function for quick checks
def quick_check_description(description: str) -> bool:
    """Quick check if a description is blocked by firewall.

    Args:
        description: Description text to check

    Returns:
        True if passed, False if blocked
    """
    checker = FirewallChecker()
    result = checker.check_description(description)
    return result["checked"] and not result["blocked"]
