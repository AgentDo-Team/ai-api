
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Column, DateTime, Text, UniqueConstraint, func
from sqlmodel import Field, SQLModel


class EvalCriteriaReference(SQLModel, table=True):
    __tablename__ = "eval_criteria_references"
    __table_args__ = (UniqueConstraint("source_file", name="uq_eval_criteria_references_source_file"),)

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, primary_key=True, autoincrement=True),
    )
    source_file: str = Field(max_length=255, nullable=False) 
    content: str = Field(sa_column=Column(Text, nullable=False))  
    embedding: list[float] | None = Field(
        default=None, sa_column=Column(Vector(1024))
    )
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
