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
        # 하나의 입찰공고에는 하나의 분석만 존재해야 함
        UniqueConstraint(
            "search_set_id", "bid_notice_id", name="uq_analysis_searchset_notice"
        ),
        # bid_notices RESTRICT 삭제 시 역참조 조회용
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
            # 공유 리소스 → 삭제 제한
            ForeignKey("bid_notices.id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    is_hard_passed: bool | None = Field(default=None, sa_column=Column(Boolean))
    soft_score: int | None = Field(default=None, sa_column=Column(Integer))  # 점수
    chunk_judgments: list[dict[str, Any]] | None = Field(
        default=None, sa_column=Column(JSONB)
    )  # [{chunk_id, project_id, similarity, verdict, reason}]
    recommend_reason: str | None = Field(
        default=None, sa_column=Column(Text)
    )  # 추천이유
    weaknesses: str | None = Field(
        default=None, sa_column=Column(Text)
    )  # 보완할 점 (약점)
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
    role: str = Field(max_length=20, nullable=False)  # user / assistant / system
    content: str | None = Field(default=None, sa_column=Column(Text))
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
