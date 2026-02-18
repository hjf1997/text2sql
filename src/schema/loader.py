"""Schema loader for managing schema lifecycle.

Loads schema from a directory containing multiple Excel files,
where each file represents one table (filename = table name).
"""

import json
from pathlib import Path
from typing import Optional, List
from .parser import ExcelSchemaParser
from .models import Schema
from ..config import settings
from ..utils import SchemaError, setup_logger

logger = setup_logger(__name__)


class SchemaLoader:
    """Manages schema loading, caching, and retrieval."""

    def __init__(self, cache_dir: Optional[str] = None):
        """Initialize schema loader.

        Args:
            cache_dir: Optional directory for schema cache
        """
        self.cache_dir = Path(cache_dir) if cache_dir else Path("cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._schema: Optional[Schema] = None

    def load_from_excel(
        self,
        schema_dir: Optional[str] = None,
        general_info_sheet: Optional[str] = None,
        variables_sheet: Optional[str] = None,
        project_id: Optional[str] = None,
        dataset: Optional[str] = None,
        use_cache: bool = True,
        check_firewall: bool = True,
    ) -> Schema:
        """Load schema from directory containing Excel files (one per table).

        Args:
            schema_dir: Directory containing Excel files (defaults to config)
            general_info_sheet: Sheet name for general info (defaults to config)
            variables_sheet: Sheet name for variables (defaults to config)
            project_id: GCP project ID (defaults to config)
            dataset: BigQuery dataset (defaults to config)
            use_cache: Whether to use cached schema if available
            check_firewall: Whether to check descriptions against firewall (default: True)

        Returns:
            Loaded Schema object containing all tables

        Raises:
            SchemaError: If loading fails
        """
        # Get defaults from config
        if schema_dir is None:
            schema_dir = settings.get("schema.schema_directory")
            if not schema_dir:
                raise SchemaError(
                    "No schema directory provided and none configured. "
                    "Set SCHEMA_DIRECTORY environment variable or provide schema_dir parameter."
                )

        schema_path = Path(schema_dir)
        if not schema_path.exists():
            raise SchemaError(f"Schema directory not found: {schema_dir}")

        if not schema_path.is_dir():
            raise SchemaError(f"Path is not a directory: {schema_dir}")

        if general_info_sheet is None:
            general_info_sheet = settings.get(
                "schema.general_info_sheet", "General Information"
            )

        if variables_sheet is None:
            variables_sheet = settings.get("schema.variables_sheet", "Variables")

        if project_id is None:
            project_id = settings.get("bigquery.project_id")

        if dataset is None:
            dataset = settings.get("bigquery.dataset")

        # Check cache
        if use_cache and settings.get("schema.cache_parsed_schema", True):
            cached_schema = self._load_from_cache(schema_dir)
            if cached_schema:
                logger.info("Loaded schema from cache")
                self._schema = cached_schema
                return cached_schema

        # Find all Excel files in directory
        excel_files = list(schema_path.glob("*.xlsx"))
        excel_files.extend(schema_path.glob("*.xls"))

        if not excel_files:
            raise SchemaError(f"No Excel files found in directory: {schema_dir}")

        logger.info(f"Loading schema from directory: {schema_dir}")
        logger.info(f"Found {len(excel_files)} Excel files")

        # Create schema object
        schema = Schema(
            project_id=project_id,
            dataset=dataset,
        )

        # Parse each Excel file as a separate table
        for excel_file in sorted(excel_files):
            # Skip temporary Excel files (start with ~$)
            if excel_file.name.startswith('~$'):
                continue

            try:
                logger.info(f"Parsing table from: {excel_file.name}")
                parser = ExcelSchemaParser(str(excel_file))
                table = parser.parse(
                    general_info_sheet=general_info_sheet,
                    variables_sheet=variables_sheet,
                )

                # Set dataset on table
                table.dataset = dataset
                schema.add_table(table)

                logger.info(f"✓ Loaded table '{table.name}' with {len(table.columns)} columns")

            except Exception as e:
                logger.error(f"Failed to parse {excel_file.name}: {str(e)}")
                raise SchemaError(
                    f"Failed to parse table from {excel_file.name}: {str(e)}"
                ) from e

        logger.info(
            f"Successfully loaded schema with {len(schema.tables)} tables, "
            f"{len(schema.get_all_columns())} total columns"
        )

        # Run firewall check if requested (with incremental caching)
        if check_firewall:
            logger.info("\n" + "="*60)
            logger.info("Starting firewall check for schema descriptions...")
            logger.info("="*60)

            try:
                from .firewall_checker import FirewallChecker
                checker = FirewallChecker()

                # Check each table and save to cache incrementally
                for table_idx, (table_name, table) in enumerate(schema.tables.items(), 1):
                    logger.info(f"\n[{table_idx}/{len(schema.tables)}] Checking table: {table_name}")

                    # Check table description
                    checker.check_table_description(table, skip_checked=True)

                    # Check column descriptions
                    checker.check_column_descriptions(
                        table.columns,
                        table_name,
                        skip_checked=True
                    )

                    # Save to cache after each table is checked (incremental save)
                    if settings.get("schema.cache_parsed_schema", True):
                        try:
                            self._save_to_cache(schema_dir, schema)
                            logger.debug(f"   💾 Saved schema to cache after checking {table_name}")
                        except Exception as cache_error:
                            logger.warning(f"Failed to save cache after {table_name}: {cache_error}")

                logger.info("✓ Firewall check complete")
            except Exception as e:
                logger.error(f"Firewall check failed: {str(e)}")
                logger.warning(
                    "Schema loaded but firewall check incomplete. "
                    "Descriptions may be blocked when used in prompts."
                )
                # Still save what we have
                if settings.get("schema.cache_parsed_schema", True):
                    self._save_to_cache(schema_dir, schema)
        else:
            # No firewall check - just save to cache
            if settings.get("schema.cache_parsed_schema", True):
                self._save_to_cache(schema_dir, schema)

        self._schema = schema
        return schema

    def get_schema(self) -> Optional[Schema]:
        """Get currently loaded schema.

        Returns:
            Schema object or None if not loaded
        """
        return self._schema

    def reload(self) -> Schema:
        """Reload schema from source (bypassing cache).

        Returns:
            Reloaded Schema object

        Raises:
            SchemaError: If no schema has been loaded yet
        """
        if not self._schema:
            raise SchemaError("No schema loaded yet. Call load_from_excel first.")

        return self.load_from_excel(use_cache=False)

    def _get_cache_path(self, schema_dir: str) -> Path:
        """Get cache file path for a schema directory.

        Args:
            schema_dir: Path to schema directory

        Returns:
            Path to cache file
        """
        dir_path = Path(schema_dir)
        # Use directory name as cache file name
        cache_name = f"{dir_path.name}_schema.json"
        return self.cache_dir / cache_name

    def _load_from_cache(self, schema_dir: str) -> Optional[Schema]:
        """Load schema from cache if available and fresh.

        Args:
            schema_dir: Path to schema directory

        Returns:
            Cached Schema or None if cache miss/stale
        """
        cache_path = self._get_cache_path(schema_dir)

        if not cache_path.exists():
            return None

        dir_path = Path(schema_dir)
        if not dir_path.exists():
            return None

        # Check if any Excel file is newer than cache
        cache_mtime = cache_path.stat().st_mtime

        excel_files = list(dir_path.glob("*.xlsx"))
        excel_files.extend(dir_path.glob("*.xls"))

        for excel_file in excel_files:
            if excel_file.name.startswith('~$'):
                continue
            if excel_file.stat().st_mtime > cache_mtime:
                logger.info(f"Cache is stale (newer file: {excel_file.name}), will reload")
                return None

        # Load from cache
        try:
            with open(cache_path, 'r') as f:
                data = json.load(f)

            schema = self._schema_from_dict(data)
            logger.info(f"Loaded schema from cache: {cache_path}")
            return schema

        except Exception as e:
            logger.warning(f"Failed to load from cache: {str(e)}")
            return None

    def _save_to_cache(self, schema_dir: str, schema: Schema) -> None:
        """Save schema to cache.

        Args:
            schema_dir: Path to schema directory
            schema: Schema to cache
        """
        cache_path = self._get_cache_path(schema_dir)

        try:
            with open(cache_path, 'w') as f:
                json.dump(schema.to_dict(), f, indent=2)
            logger.info(f"Saved schema to cache: {cache_path}")

        except Exception as e:
            logger.warning(f"Failed to save schema to cache: {str(e)}")

    def _schema_from_dict(self, data: dict) -> Schema:
        """Reconstruct Schema object from dictionary.

        Args:
            data: Schema dictionary

        Returns:
            Schema object
        """
        from .models import Table, Column, ColumnType

        schema = Schema(
            project_id=data.get("project_id"),
            dataset=data.get("dataset"),
            metadata=data.get("metadata", {}),
        )

        for table_name, table_data in data.get("tables", {}).items():
            table = Table(
                name=table_data["name"],
                description=table_data.get("description"),
                business_context=table_data.get("business_context"),
                dataset=table_data.get("dataset"),
                firewall_checked=table_data.get("firewall_checked", False),
                firewall_blocked=table_data.get("firewall_blocked", False),
            )

            for col_data in table_data.get("columns", []):
                column = Column(
                    name=col_data["name"],
                    business_name=col_data.get("business_name"),
                    description=col_data.get("description"),
                    data_type=ColumnType(col_data["data_type"]) if col_data.get("data_type") else ColumnType.UNKNOWN,
                    is_pii=col_data.get("is_pii", False),
                    entitlement=col_data.get("entitlement"),
                    is_mandatory=col_data.get("is_mandatory", False),
                    is_partition=col_data.get("is_partition", False),
                    is_primary=col_data.get("is_primary", False),
                    table_name=col_data.get("table_name"),
                    firewall_checked=col_data.get("firewall_checked", False),
                    firewall_blocked=col_data.get("firewall_blocked", False),
                )
                table.add_column(column)

            schema.add_table(table)

        return schema


# Global schema loader instance
schema_loader = SchemaLoader()
