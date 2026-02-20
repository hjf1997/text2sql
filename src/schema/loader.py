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

        # Check cache and identify stale files
        cached_schema = None
        stale_files = {}
        if use_cache and settings.get("schema.cache_parsed_schema", True):
            cached_schema, stale_files = self._load_from_cache(schema_dir)

        # Find all Excel files in directory
        excel_files = list(schema_path.glob("*.xlsx"))
        excel_files.extend(schema_path.glob("*.xls"))

        if not excel_files:
            raise SchemaError(f"No Excel files found in directory: {schema_dir}")

        # Determine which files need to be parsed
        if cached_schema and not stale_files:
            # Cache is complete and fresh - use it directly
            logger.info("Using complete fresh cache, no parsing needed")
            self._schema = cached_schema
            return cached_schema

        # Need to parse some or all files
        logger.info(f"Loading schema from directory: {schema_dir}")
        logger.info(f"Found {len(excel_files)} Excel files")

        # Start with cached schema or create new one
        if cached_schema:
            schema = cached_schema
            logger.info(f"Using {len(schema.tables)} cached tables as base")
        else:
            schema = Schema(
                project_id=project_id,
                dataset=dataset,
            )
            logger.info("Starting fresh schema (no cache)")

        # Track which tables were newly parsed (need firewall check)
        newly_parsed_tables = []

        # Parse each Excel file (only stale ones if cache exists)
        for excel_file in sorted(excel_files):
            # Skip temporary Excel files (start with ~$)
            if excel_file.name.startswith('~$'):
                continue

            # Skip non-stale files if using cache
            if cached_schema and excel_file.name not in stale_files:
                logger.debug(f"Skipping {excel_file.name} (using cached version)")
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

                # Add or update table in schema
                if table.name in schema.tables:
                    logger.info(f"✓ Updated table '{table.name}' with {len(table.columns)} columns")
                else:
                    logger.info(f"✓ Loaded new table '{table.name}' with {len(table.columns)} columns")

                schema.add_table(table)
                newly_parsed_tables.append(table.name)

            except Exception as e:
                logger.error(f"Failed to parse {excel_file.name}: {str(e)}")
                raise SchemaError(
                    f"Failed to parse table from {excel_file.name}: {str(e)}"
                ) from e

        logger.info(
            f"Schema ready: {len(schema.tables)} tables total, "
            f"{len(newly_parsed_tables)} newly parsed, "
            f"{len(schema.tables) - len(newly_parsed_tables)} from cache"
        )

        # Run firewall check if requested (only on newly parsed tables)
        if check_firewall:
            if newly_parsed_tables:
                logger.info("\n" + "="*60)
                logger.info(f"Starting firewall check for {len(newly_parsed_tables)} newly parsed tables...")
                logger.info("="*60)

                try:
                    from .firewall_checker import FirewallChecker
                    checker = FirewallChecker()

                    # Check only newly parsed tables
                    for table_idx, table_name in enumerate(newly_parsed_tables, 1):
                        table = schema.tables[table_name]
                        logger.info(f"\n[{table_idx}/{len(newly_parsed_tables)}] Checking table: {table_name}")

                        # Check table description (skip_checked=False for new tables)
                        checker.check_table_description(table, skip_checked=False)

                        # Check column descriptions (skip_checked=False for new columns)
                        checker.check_column_descriptions(
                            table.columns,
                            table_name,
                            skip_checked=False
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
                logger.info("No newly parsed tables - skipping firewall check")
                logger.info(f"Using {len(schema.tables)} cached tables (already firewall checked)")
        else:
            # No firewall check - just save to cache if there were changes
            if newly_parsed_tables and settings.get("schema.cache_parsed_schema", True):
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

    def _load_from_cache(self, schema_dir: str) -> tuple[Optional[Schema], dict]:
        """Load schema from cache and identify stale tables.

        Args:
            schema_dir: Path to schema directory

        Returns:
            Tuple of (cached Schema or None, dict mapping Excel filename to mtime for stale files)
        """
        cache_path = self._get_cache_path(schema_dir)

        if not cache_path.exists():
            return None, {}

        dir_path = Path(schema_dir)
        if not dir_path.exists():
            return None, {}

        # Get cache modification time
        cache_mtime = cache_path.stat().st_mtime

        # Load from cache
        try:
            with open(cache_path, 'r') as f:
                data = json.load(f)

            schema = self._schema_from_dict(data)

            # Identify which Excel files are new or modified
            excel_files = list(dir_path.glob("*.xlsx"))
            excel_files.extend(dir_path.glob("*.xls"))

            stale_files = {}
            for excel_file in excel_files:
                if excel_file.name.startswith('~$'):
                    continue

                file_mtime = excel_file.stat().st_mtime
                # Extract table name from filename (without extension)
                table_name = excel_file.stem

                # Check if file is newer than cache OR table not in cached schema
                if file_mtime > cache_mtime or table_name not in schema.tables:
                    stale_files[excel_file.name] = file_mtime
                    logger.debug(f"File is stale or new: {excel_file.name}")

            if stale_files:
                logger.info(
                    f"Loaded partial cache: {len(schema.tables)} tables cached, "
                    f"{len(stale_files)} files need reloading"
                )
            else:
                logger.info(f"Loaded complete cache: {len(schema.tables)} tables, all fresh")

            return schema, stale_files

        except Exception as e:
            logger.warning(f"Failed to load from cache: {str(e)}")
            return None, {}

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
