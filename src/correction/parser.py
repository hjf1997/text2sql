"""Parser for user corrections."""

import re
from typing import Union, Dict, Any
from .models import (
    Correction,
    CorrectionType,
    JoinClarification,
    ColumnMapping,
    NaturalLanguageCorrection,
)
from ..utils import CorrectionError, setup_logger

logger = setup_logger(__name__)


class CorrectionParser:
    """Parses user corrections into structured format."""

    @staticmethod
    def parse(user_input: str) -> Correction:
        """Parse user correction input into a Correction object.

        Args:
            user_input: User's correction text

        Returns:
            Parsed Correction object

        Raises:
            CorrectionError: If parsing fails
        """
        user_input = user_input.strip()

        # Try to detect structured correction types
        correction = (
            CorrectionParser._try_parse_join(user_input)
            or CorrectionParser._try_parse_column_mapping(user_input)
            or CorrectionParser._parse_natural_language(user_input)
        )

        logger.info(f"Parsed correction type: {correction.correction_type.value}")
        return correction

    @staticmethod
    def parse_dict(correction_dict: Dict[str, Any]) -> Correction:
        """Parse correction from dictionary format.

        Args:
            correction_dict: Dictionary containing correction data

        Returns:
            Parsed Correction object

        Raises:
            CorrectionError: If parsing fails
        """
        try:
            corr_type = correction_dict.get("type", "").lower()

            if corr_type == "join" or corr_type == "join_clarification":
                return JoinClarification(
                    tables=correction_dict.get("tables", []),
                    join_condition=correction_dict.get("join_condition", ""),
                    description=correction_dict.get("description"),
                )

            elif corr_type == "column" or corr_type == "column_mapping":
                return ColumnMapping(
                    user_term=correction_dict.get("user_term", ""),
                    actual_column=correction_dict.get("actual_column", ""),
                    description=correction_dict.get("description"),
                )

            else:
                # Treat as natural language
                return NaturalLanguageCorrection(
                    correction_text=correction_dict.get("correction", ""),
                    description=correction_dict.get("description"),
                )

        except Exception as e:
            raise CorrectionError(f"Failed to parse correction dictionary: {str(e)}") from e

    @staticmethod
    def _try_parse_join(user_input: str) -> Union[JoinClarification, None]:
        """Try to parse as join clarification.

        Patterns:
        - "join A.id with B.a_id"
        - "use A.id = B.a_id"
        - "join tables A and B on A.id = B.a_id"
        """
        # Pattern 1: "join A.col with B.col"
        pattern1 = r"join\s+(\w+)\.(\w+)\s+(?:with|to|and)\s+(\w+)\.(\w+)"
        match = re.search(pattern1, user_input, re.IGNORECASE)
        if match:
            table1, col1, table2, col2 = match.groups()
            return JoinClarification(
                tables=[table1, table2],
                join_condition=f"{table1}.{col1} = {table2}.{col2}",
            )

        # Pattern 2: "use A.col = B.col"
        pattern2 = r"use\s+(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)"
        match = re.search(pattern2, user_input, re.IGNORECASE)
        if match:
            table1, col1, table2, col2 = match.groups()
            return JoinClarification(
                tables=[table1, table2],
                join_condition=f"{table1}.{col1} = {table2}.{col2}",
            )

        # Pattern 3: Direct join condition "A.col = B.col"
        pattern3 = r"(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)"
        match = re.search(pattern3, user_input, re.IGNORECASE)
        if match and ("join" in user_input.lower() or "=" in user_input):
            table1, col1, table2, col2 = match.groups()
            return JoinClarification(
                tables=[table1, table2],
                join_condition=f"{table1}.{col1} = {table2}.{col2}",
            )

        return None

    @staticmethod
    def _try_parse_column_mapping(user_input: str) -> Union[ColumnMapping, None]:
        """Try to parse as column mapping.

        Patterns:
        - "region means Table.column"
        - "map region to Table.column"
        - "use Table.column for region"
        """
        # Pattern 1: "X means Table.column"
        pattern1 = r"(\w+)\s+means\s+(\w+)\.(\w+)"
        match = re.search(pattern1, user_input, re.IGNORECASE)
        if match:
            user_term, table, column = match.groups()
            return ColumnMapping(
                user_term=user_term,
                actual_column=f"{table}.{column}",
            )

        # Pattern 2: "map X to Table.column"
        pattern2 = r"map\s+(\w+)\s+to\s+(\w+)\.(\w+)"
        match = re.search(pattern2, user_input, re.IGNORECASE)
        if match:
            user_term, table, column = match.groups()
            return ColumnMapping(
                user_term=user_term,
                actual_column=f"{table}.{column}",
            )

        # Pattern 3: "use Table.column for X"
        pattern3 = r"use\s+(\w+)\.(\w+)\s+for\s+(\w+)"
        match = re.search(pattern3, user_input, re.IGNORECASE)
        if match:
            table, column, user_term = match.groups()
            return ColumnMapping(
                user_term=user_term,
                actual_column=f"{table}.{column}",
            )

        return None

    @staticmethod
    def _parse_natural_language(user_input: str) -> NaturalLanguageCorrection:
        """Parse as natural language correction (fallback).

        Args:
            user_input: User's correction text

        Returns:
            NaturalLanguageCorrection object
        """
        return NaturalLanguageCorrection(correction_text=user_input)
