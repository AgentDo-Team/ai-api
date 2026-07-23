from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class AnalysisResult(SQLModel, table=True):
    __tablename__ = "analysis_results"
    __table_args__ = (
        UniqueConstraint(
            "search_set_id", "bid_notice_id", name="uq_analysis_searchset_notice"
        ),
        Index("ix_analysis_bid_notice", "bid_notice_id"),
    )

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, primary_key=True, autoincrement=True),
    )
    search_set_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("search_sets.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    bid_notice_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("bid_notices.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    is_hard_passed: bool | None = Field(default=None, sa_column=Column(Boolean))
    soft_score: int | None = Field(default=None, sa_column=Column(Integer))  
    chunk_judgments: list[dict[str, Any]] | None = Field(
        default=None, sa_column=Column(JSONB)
    )  
    recommend_reason: list[dict[str, Any]] | None = Field(
        default=None, sa_column=Column(JSONB)
    )  
    weaknesses: list[dict[str, Any]] | None = Field(
        default=None, sa_column=Column(JSONB)
    )  
    summary: str | None = Field(default=None, sa_column=Column(Text))  # 공고 요약
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, primary_key=True, autoincrement=True),
    )
    search_set_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("search_sets.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    role: str = Field(max_length=20, nullable=False)  
    content: str | None = Field(default=None, sa_column=Column(Text))
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
