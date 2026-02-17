"""Unit tests for schema parser."""

import pytest
from pathlib import Path
from src.schema.parser import ExcelSchemaParser
from src.schema.models import Schema, Table, Column, ColumnType
from src.utils import SchemaError


class TestExcelSchemaParser:
    """Test cases for Excel schema parser."""

    def test_parser_initialization(self, tmp_path):
        """Test parser can be initialized with valid path."""
        # Create a dummy Excel file
        excel_file = tmp_path / "test_schema.xlsx"
        excel_file.touch()

        # This will fail because it's not a real Excel file, but tests the path logic
        with pytest.raises(SchemaError):
            parser = ExcelSchemaParser(str(excel_file))

    def test_parser_invalid_path(self):
        """Test parser raises error for non-existent file."""
        with pytest.raises(SchemaError, match="Schema file not found"):
            parser = ExcelSchemaParser("nonexistent.xlsx")

    def test_column_type_parsing(self):
        """Test column type string parsing."""
        parser = ExcelSchemaParser.__new__(ExcelSchemaParser)

        # Test various type strings
        assert parser._parse_column_type("STRING") == ColumnType.STRING
        assert parser._parse_column_type("VARCHAR") == ColumnType.STRING
        assert parser._parse_column_type("INTEGER") == ColumnType.INTEGER
        assert parser._parse_column_type("INT64") == ColumnType.INTEGER
        assert parser._parse_column_type("FLOAT") == ColumnType.FLOAT
        assert parser._parse_column_type("BOOLEAN") == ColumnType.BOOLEAN
        assert parser._parse_column_type("DATE") == ColumnType.DATE
        assert parser._parse_column_type("UNKNOWN_TYPE") == ColumnType.UNKNOWN

    def test_extract_column_data(self):
        """Test column data extraction from row."""
        import pandas as pd

        parser = ExcelSchemaParser.__new__(ExcelSchemaParser)

        # Create a sample row
        row = pd.Series({
            "Name": "customer_id",
            "Table Name": "Customers",
            "Description": "Customer identifier",
            "TYPE": "INTEGER",
            "PII": "N",
            "PRIMARY": "Y",
        })

        col_data = parser._extract_column_data(row)

        assert col_data is not None
        assert col_data["name"] == "customer_id"
        assert col_data["table_name"] == "Customers"
        assert col_data["description"] == "Customer identifier"
        assert col_data["data_type"] == "INTEGER"
        assert col_data["is_pii"] == False
        assert col_data["is_primary"] == True

    def test_extract_column_data_missing_name(self):
        """Test column extraction fails gracefully without name."""
        import pandas as pd

        parser = ExcelSchemaParser.__new__(ExcelSchemaParser)

        row = pd.Series({
            "Table Name": "Customers",
            "Description": "Some description",
        })

        col_data = parser._extract_column_data(row)
        assert col_data is None

    def test_create_column(self):
        """Test column object creation."""
        parser = ExcelSchemaParser.__new__(ExcelSchemaParser)

        col_data = {
            "name": "customer_id",
            "table_name": "Customers",
            "business_name": "Customer ID",
            "description": "Unique customer identifier",
            "data_type": "INTEGER",
            "is_pii": False,
            "is_primary": True,
            "is_mandatory": True,
        }

        column = parser._create_column(col_data)

        assert isinstance(column, Column)
        assert column.name == "customer_id"
        assert column.table_name == "Customers"
        assert column.business_name == "Customer ID"
        assert column.data_type == ColumnType.INTEGER
        assert column.is_primary == True
        assert column.is_pii == False


class TestSchemaModels:
    """Test cases for schema data models."""

    def test_column_creation(self):
        """Test Column model creation."""
        col = Column(
            name="test_col",
            data_type=ColumnType.STRING,
            description="Test column",
            is_primary=True,
        )

        assert col.name == "test_col"
        assert col.data_type == ColumnType.STRING
        assert col.is_primary == True

    def test_column_full_name(self):
        """Test column full name generation."""
        col = Column(name="col1", table_name="Table1")
        assert col.get_full_name() == "Table1.col1"

        col2 = Column(name="col2")
        assert col2.get_full_name() == "col2"

    def test_table_creation(self):
        """Test Table model creation."""
        table = Table(
            name="TestTable",
            description="A test table"
        )

        assert table.name == "TestTable"
        assert table.description == "A test table"
        assert len(table.columns) == 0

    def test_table_add_column(self):
        """Test adding columns to table."""
        table = Table(name="TestTable")

        col1 = Column(name="col1", data_type=ColumnType.STRING)
        col2 = Column(name="col2", data_type=ColumnType.INTEGER)

        table.add_column(col1)
        table.add_column(col2)

        assert len(table.columns) == 2
        assert table.columns[0].table_name == "TestTable"
        assert table.columns[1].table_name == "TestTable"

    def test_table_get_column(self):
        """Test getting column by name."""
        table = Table(name="TestTable")
        col = Column(name="test_col", data_type=ColumnType.STRING)
        table.add_column(col)

        found = table.get_column("test_col")
        assert found is not None
        assert found.name == "test_col"

        not_found = table.get_column("nonexistent")
        assert not_found is None

    def test_table_get_primary_keys(self):
        """Test getting primary key columns."""
        table = Table(name="TestTable")

        col1 = Column(name="id", data_type=ColumnType.INTEGER, is_primary=True)
        col2 = Column(name="name", data_type=ColumnType.STRING, is_primary=False)

        table.add_column(col1)
        table.add_column(col2)

        pks = table.get_primary_keys()
        assert len(pks) == 1
        assert pks[0].name == "id"

    def test_schema_creation(self):
        """Test Schema model creation."""
        schema = Schema(
            project_id="test-project",
            dataset="test_dataset"
        )

        assert schema.project_id == "test-project"
        assert schema.dataset == "test_dataset"
        assert len(schema.tables) == 0

    def test_schema_add_table(self):
        """Test adding tables to schema."""
        schema = Schema(dataset="test_dataset")

        table1 = Table(name="Table1")
        table2 = Table(name="Table2")

        schema.add_table(table1)
        schema.add_table(table2)

        assert len(schema.tables) == 2
        assert "Table1" in schema.tables
        assert "Table2" in schema.tables

    def test_schema_get_table(self):
        """Test getting table by name (case-insensitive)."""
        schema = Schema()
        table = Table(name="TestTable")
        schema.add_table(table)

        found = schema.get_table("TestTable")
        assert found is not None

        found_lower = schema.get_table("testtable")
        assert found_lower is not None

        not_found = schema.get_table("NonExistent")
        assert not_found is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
