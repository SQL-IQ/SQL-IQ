"""Unified Sample data class for all tasks."""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class Sample:
    """
    Unified sample format supporting all 6 SQL-IQ tasks.

    Attributes:
        id: Unique sample ID (integer).

        # Input fields
        input_text: User question or instruction (Text2SQL, Conversational SQL, etc.)
        input_sql: Input SQL (SQL Judge, SQL Equivalence Judge, SQL Error Classification, etc.)
        input_sql_2: Second SQL (SQL Judge, SQL Equivalence Judge)
        db_id: Database ID, used to retrieve schema from SchemaLoader.
        schema_str: Actual Schema DDL string (populated by SchemaLoader).
        evidence: External knowledge / evidence for enhancing prompt context.
        history: Conversation history list (Conversational SQL only).

        # Ground Truth
        output_sql: Ground truth SQL (Text2SQL, Conversational SQL, SQL Translation).
        output_label: Ground truth label (SQL Judge, SQL Equivalence Judge, SQL Error Classification).

        # Metadata
        db_path: Database file path (if execution is needed).
        difficulty: Difficulty level.
        dialect: SQL dialect (sqlite, postgresql, oracle, mssql, clickhouse, druid).
        metadata: Extension fields for task-specific data.
    """

    id: int

    # Input fields
    input_text: Optional[str] = None
    input_sql: Optional[str] = None
    input_sql_2: Optional[str] = None
    input_plan: Optional[str] = None
    input_plan_2: Optional[str] = None
    db_id: Optional[str] = None
    schema_str: Optional[str] = None
    evidence: Optional[str] = None
    history: List[Dict[str, str]] = field(default_factory=list)

    # Ground Truth
    output_sql: Optional[str] = None
    output_label: Optional[Any] = None

    # Metadata
    db_path: Optional[str] = None
    difficulty: Optional[str] = None
    dialect: Optional[str] = "sqlite"
    metadata: Dict[str, Any] = field(default_factory=dict)
