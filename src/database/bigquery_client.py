"""BigQuery client for executing SQL queries."""

from typing import Optional, List, Dict, Any
from google.cloud import bigquery
from google.api_core import exceptions as gcp_exceptions
from ..config import settings
from ..utils import BigQueryError, ValidationError, setup_logger

logger = setup_logger(__name__)


class BigQueryClient:
    """Client for interacting with Google BigQuery."""

    def __init__(
        self,
        project_id: Optional[str] = None,
        dataset: Optional[str] = None,
        location: Optional[str] = None,
        credentials_path: Optional[str] = None,
    ):
        """Initialize BigQuery client.

        Args:
            project_id: GCP project ID (defaults to config)
            dataset: Default dataset name (defaults to config)
            location: BigQuery location (defaults to config)
            credentials_path: Path to service account JSON (optional)

        Raises:
            BigQueryError: If initialization fails
        """
        # Get configuration
        bq_config = settings.bigquery

        self.project_id = project_id or bq_config["project_id"]
        self.dataset = dataset or bq_config["dataset"]
        self.location = location or bq_config.get("location", "US")
        self.query_timeout = bq_config.get("query_timeout", 300)

        # Initialize client
        try:
            if credentials_path or bq_config.get("credentials_path"):
                # from google.oauth2 import service_account
                # creds_path = credentials_path or bq_config["credentials_path"]
                # credentials = service_account.Credentials.from_service_account_file(
                #     creds_path
                # )
                self.client = bigquery.Client(
                    project=self.project_id,
                    # credentials=credentials,
                    location=self.location,
                )
            else:
                # Use default credentials (e.g., from environment)
                self.client = bigquery.Client(
                    project=self.project_id,
                    location=self.location,
                )

            logger.info(
                f"Initialized BigQuery client for project: {self.project_id}, "
                f"dataset: {self.dataset}"
            )

        except Exception as e:
            raise BigQueryError(f"Failed to initialize BigQuery client: {str(e)}") from e

    def execute_query(
        self,
        sql: str,
        timeout: Optional[int] = None,
        max_results: Optional[int] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Execute a SQL query and return results.

        Args:
            sql: SQL query to execute
            timeout: Query timeout in seconds (uses default if None)
            max_results: Maximum number of results to return
            dry_run: If True, validate query without executing

        Returns:
            Dictionary containing:
                - success: bool
                - rows: List of result rows (if successful)
                - row_count: Number of rows returned
                - bytes_processed: Bytes processed by query
                - error: Error message (if failed)

        Raises:
            BigQueryError: If query execution fails
        """
        timeout = timeout or self.query_timeout

        # Log the query (with masking if needed)
        logger.info(f"Executing BigQuery SQL (dry_run={dry_run}):\n{sql[:500]}...")

        try:
            # Configure job
            job_config = bigquery.QueryJobConfig(
                use_query_cache=True,
                use_legacy_sql=False,
                dry_run=dry_run,
            )

            # Execute query
            query_job = self.client.query(
                sql,
                job_config=job_config,
                location=self.location,
            )

            if dry_run:
                # For dry run, just return validation info
                return {
                    "success": True,
                    "dry_run": True,
                    "bytes_processed": query_job.total_bytes_processed,
                    "is_valid": True,
                }

            # Wait for query to complete
            results = query_job.result(timeout=timeout)

            # Fetch results
            rows = []
            if max_results:
                rows = [dict(row) for row in results.take(max_results)]
            else:
                rows = [dict(row) for row in results]

            result = {
                "success": True,
                "rows": rows,
                "row_count": len(rows),
                "total_rows": results.total_rows,
                "bytes_processed": query_job.total_bytes_processed,
                "schema": [{"name": field.name, "type": field.field_type} for field in results.schema],
            }

            logger.info(
                f"Query successful: {result['row_count']} rows returned, "
                f"{result['bytes_processed']} bytes processed"
            )

            return result

        except gcp_exceptions.Forbidden as e:
            error_msg = f"Permission denied: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "error_type": "PermissionError",
            }

        except gcp_exceptions.BadRequest as e:
            error_msg = f"Invalid SQL query: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "error_type": "SyntaxError",
            }

        except gcp_exceptions.DeadlineExceeded as e:
            error_msg = f"Query timeout after {timeout}s: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "error_type": "TimeoutError",
            }

        except Exception as e:
            error_msg = f"Query execution failed: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "error_type": type(e).__name__,
            }

    def validate_query(self, sql: str) -> Dict[str, Any]:
        """Validate SQL query without executing it.

        Args:
            sql: SQL query to validate

        Returns:
            Dictionary with validation results
        """
        logger.info("Validating SQL query")
        return self.execute_query(sql, dry_run=True)

    def get_table_info(self, table_name: str, dataset: Optional[str] = None) -> Dict[str, Any]:
        """Get information about a table.

        Args:
            table_name: Name of the table
            dataset: Dataset name (uses default if None)

        Returns:
            Dictionary with table information

        Raises:
            BigQueryError: If table info retrieval fails
        """
        dataset = dataset or self.dataset
        table_ref = f"{self.project_id}.{dataset}.{table_name}"

        try:
            table = self.client.get_table(table_ref)

            info = {
                "project": table.project,
                "dataset": table.dataset_id,
                "table": table.table_id,
                "num_rows": table.num_rows,
                "num_bytes": table.num_bytes,
                "created": table.created.isoformat() if table.created else None,
                "modified": table.modified.isoformat() if table.modified else None,
                "schema": [
                    {
                        "name": field.name,
                        "type": field.field_type,
                        "mode": field.mode,
                        "description": field.description,
                    }
                    for field in table.schema
                ],
            }

            logger.info(f"Retrieved info for table: {table_ref}")
            return info

        except gcp_exceptions.NotFound:
            raise BigQueryError(f"Table not found: {table_ref}")
        except Exception as e:
            raise BigQueryError(f"Failed to get table info: {str(e)}") from e

    def list_tables(self, dataset: Optional[str] = None) -> List[str]:
        """List all tables in a dataset.

        Args:
            dataset: Dataset name (uses default if None)

        Returns:
            List of table names

        Raises:
            BigQueryError: If listing fails
        """
        dataset = dataset or self.dataset
        dataset_ref = f"{self.project_id}.{dataset}"

        try:
            tables = self.client.list_tables(dataset_ref)
            table_names = [table.table_id for table in tables]

            logger.info(f"Listed {len(table_names)} tables in dataset: {dataset}")
            return table_names

        except gcp_exceptions.NotFound:
            raise BigQueryError(f"Dataset not found: {dataset_ref}")
        except Exception as e:
            raise BigQueryError(f"Failed to list tables: {str(e)}") from e

    def estimate_query_cost(self, sql: str) -> Dict[str, Any]:
        """Estimate the cost of running a query (bytes to be processed).

        Args:
            sql: SQL query

        Returns:
            Dictionary with cost estimation
        """
        result = self.validate_query(sql)

        if result.get("success"):
            bytes_processed = result.get("bytes_processed", 0)
            # BigQuery pricing: $5 per TB (as of 2024)
            estimated_cost_usd = (bytes_processed / (1024**4)) * 5

            return {
                "success": True,
                "bytes_processed": bytes_processed,
                "estimated_cost_usd": estimated_cost_usd,
                "readable_size": self._format_bytes(bytes_processed),
            }
        else:
            return result

    def _format_bytes(self, bytes: int) -> str:
        """Format bytes in human-readable format.

        Args:
            bytes: Number of bytes

        Returns:
            Formatted string (e.g., "1.5 GB")
        """
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes < 1024.0:
                return f"{bytes:.2f} {unit}"
            bytes /= 1024.0
        return f"{bytes:.2f} PB"

    def close(self):
        """Close the BigQuery client connection."""
        if hasattr(self, 'client'):
            self.client.close()
            logger.info("Closed BigQuery client connection")


# Global BigQuery client instance
bigquery_client = BigQueryClient()
