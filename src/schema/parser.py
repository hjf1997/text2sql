"""Excel schema parser for loading table and column metadata.

Each Excel file represents ONE table:
- Filename (without .xlsx) = table name for BigQuery
- Sheet 1 (General Information): Table-level metadata (optional)
- Sheet 2 (Variables): Column-level metadata
"""

import pandas as pd
from pathlib import Path
from typing import Optional, Dict, List
from .models import Schema, Table, Column, ColumnType
from ..utils import SchemaError, setup_logger

logger = setup_logger(__name__)


class ExcelSchemaParser:
    """Parser for extracting single table schema from an Excel file.

    Expected Excel structure:
    - Filename: table_name.xlsx (filename becomes table name in BigQuery)
    - Sheet 1 (General Information): Table-level metadata (optional)
    - Sheet 2 (Variables): Column-level metadata with columns:
      Name, Attribute Business Name, Description, TYPE, PII,
      Entitlement, MANDATORY, PARTITION, PRIMARY
    """

    def __init__(self, excel_path: str):
        """Initialize parser with path to Excel file.

        Args:
            excel_path: Path to the schema Excel file (one table per file)

        Raises:
            SchemaError: If file doesn't exist or can't be read
        """
        self.excel_path = Path(excel_path)
        if not self.excel_path.exists():
            raise SchemaError(f"Schema file not found: {excel_path}")

        try:
            self.excel_file = pd.ExcelFile(self.excel_path)
        except Exception as e:
            raise SchemaError(f"Failed to read Excel file: {str(e)}") from e

        # Extract table name from filename (without .xlsx extension)
        self.table_name = self.excel_path.stem

        logger.info(f"Loaded schema Excel file: {excel_path} (table: {self.table_name})")

    def parse(
        self,
        general_info_sheet: str = "General Information",
        variables_sheet: str = "Variables",
    ) -> Table:
        """Parse Excel file and return Table object.

        Args:
            general_info_sheet: Name of the sheet containing table information
            variables_sheet: Name of the sheet containing column information

        Returns:
            Table object with all columns

        Raises:
            SchemaError: If parsing fails
        """
        logger.info(f"Parsing table schema from {self.excel_path.name}...")

        # Parse table information (optional)
        table_info = self._parse_general_info(general_info_sheet)

        # Parse column information (required)
        columns_info = self._parse_variables(variables_sheet)

        # Build table
        table = self._build_table(table_info, columns_info)

        logger.info(
            f"Successfully parsed table '{table.name}' with {len(table.columns)} columns"
        )

        return table

    def _parse_general_info(self, sheet_name: str) -> Dict:
        """Parse general information sheet for table metadata.

        Converts the entire General Information sheet into a string description.

        Args:
            sheet_name: Name of the sheet

        Returns:
            Dictionary with table metadata
        """
        try:
            df = pd.read_excel(self.excel_file, sheet_name=sheet_name)
        except Exception as e:
            logger.warning(
                f"Failed to read '{sheet_name}' sheet: {str(e)}. "
                f"Proceeding without table-level metadata."
            )
            return {}

        # Convert the entire dataframe to a string description
        # Remove NaN values and format nicely
        description_lines = []

        for _, row in df.iterrows():
            # Convert row to string, excluding NaN values
            row_items = []
            for col_name, value in row.items():
                if pd.notna(value):
                    row_items.append(f"{col_name}: {value}")

            if row_items:
                description_lines.append("; ".join(row_items))

        # Join all rows with newlines
        description = "\n".join(description_lines) if description_lines else None

        table_info = {
            "name": self.table_name,
            "description": description,
            "business_context": None,
        }

        logger.info(f"Parsed general information for table: {self.table_name}")
        return table_info

    def _parse_variables(self, sheet_name: str) -> List[Dict]:
        """Parse variables sheet for column metadata.

        Args:
            sheet_name: Name of the sheet

        Returns:
            List of column metadata dictionaries

        Raises:
            SchemaError: If variables sheet cannot be parsed
        """
        try:
            df = pd.read_excel(self.excel_file, sheet_name=sheet_name)
        except Exception as e:
            raise SchemaError(
                f"Failed to read '{sheet_name}' sheet: {str(e)}"
            ) from e

        columns_info = []

        for _, row in df.iterrows():
            # Extract column information
            column_data = self._extract_column_data(row)
            if column_data:
                # Ensure table name matches the filename
                column_data["table_name"] = self.table_name
                columns_info.append(column_data)

        logger.info(f"Parsed {len(columns_info)} columns for table '{self.table_name}'")
        return columns_info

    def _extract_column_data(self, row: pd.Series) -> Optional[Dict]:
        """Extract column data from a row.

        Args:
            row: Pandas Series representing a row

        Returns:
            Dictionary of column data or None if invalid
        """
        # Get column name (required)
        column_name = None
        for col in ["Name", "Column Name", "name", "column_name"]:
            if col in row.index and pd.notna(row[col]):
                column_name = str(row[col]).strip()
                break

        if not column_name:
            return None

        # Build column data dictionary
        # Table name comes from filename, not from the Excel
        data = {
            "name": column_name,
            "table_name": self.table_name,
        }

        # Optional fields with flexible column names
        field_mappings = {
            "business_name": ["Attribute Business Name", "Business Name", "business_name"],
            "description": ["Description", "description"],
            "data_type": ["TYPE", "Type", "Data Type", "type", "data_type"],
            "is_pii": ["PII", "pii", "is_pii"],
            "entitlement": ["Entitlement", "entitlement"],
            "is_mandatory": ["MANDATORY", "Mandatory", "mandatory", "is_mandatory"],
            "is_partition": ["PARTITION", "Partition", "partition", "is_partition"],
            "is_primary": ["PRIMARY", "Primary", "Primary Key", "primary", "is_primary"],
        }

        for field, col_names in field_mappings.items():
            for col_name in col_names:
                if col_name in row.index and pd.notna(row[col_name]):
                    value = row[col_name]

                    # Convert boolean fields
                    if field.startswith("is_"):
                        if isinstance(value, str):
                            data[field] = value.strip().upper() in ["Y", "YES", "TRUE", "1", "T"]
                        else:
                            data[field] = bool(value)
                    else:
                        data[field] = str(value).strip() if value else None
                    break

        return data

    def _build_table(
        self,
        table_info: Dict,
        columns_info: List[Dict],
    ) -> Table:
        """Build Table object from parsed information.

        Args:
            table_info: Table metadata dictionary
            columns_info: List of column metadata

        Returns:
            Complete Table object
        """
        table = Table(
            name=self.table_name,
            description=table_info.get("description"),
            business_context=table_info.get("business_context"),
        )

        # Add columns to table
        for col_data in columns_info:
            column = self._create_column(col_data)
            table.add_column(column)

        return table

    def _create_column(self, col_data: Dict) -> Column:
        """Create Column object from column data.

        Args:
            col_data: Column metadata dictionary

        Returns:
            Column object
        """
        # Parse data type
        data_type_str = col_data.get("data_type", "").upper()
        data_type = self._parse_column_type(data_type_str)

        return Column(
            name=col_data["name"],
            business_name=col_data.get("business_name"),
            description=col_data.get("description"),
            data_type=data_type,
            is_pii=col_data.get("is_pii", False),
            entitlement=col_data.get("entitlement"),
            is_mandatory=col_data.get("is_mandatory", False),
            is_partition=col_data.get("is_partition", False),
            is_primary=col_data.get("is_primary", False),
            table_name=col_data.get("table_name"),
        )

    def _parse_column_type(self, type_str: str) -> ColumnType:
        """Parse column type string to ColumnType enum.

        Args:
            type_str: Type string from Excel

        Returns:
            ColumnType enum value
        """
        type_str = type_str.upper().strip()

        # Map common type strings to ColumnType
        type_mapping = {
            "STRING": ColumnType.STRING,
            "VARCHAR": ColumnType.STRING,
            "TEXT": ColumnType.STRING,
            "CHAR": ColumnType.STRING,
            "INTEGER": ColumnType.INTEGER,
            "INT": ColumnType.INTEGER,
            "INT64": ColumnType.INTEGER,
            "BIGINT": ColumnType.INTEGER,
            "FLOAT": ColumnType.FLOAT,
            "FLOAT64": ColumnType.FLOAT,
            "DOUBLE": ColumnType.FLOAT,
            "REAL": ColumnType.FLOAT,
            "BOOLEAN": ColumnType.BOOLEAN,
            "BOOL": ColumnType.BOOLEAN,
            "DATE": ColumnType.DATE,
            "DATETIME": ColumnType.DATETIME,
            "TIMESTAMP": ColumnType.TIMESTAMP,
            "NUMERIC": ColumnType.NUMERIC,
            "DECIMAL": ColumnType.NUMERIC,
        }

        for key, value in type_mapping.items():
            if key in type_str:
                return value

        logger.warning(f"Unknown column type '{type_str}', using UNKNOWN")
        return ColumnType.UNKNOWN
