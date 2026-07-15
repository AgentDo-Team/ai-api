"""bid_notice에 종속되지 않는 참조 지식 베이스 모델.

하드 필터(app/rag/chunking/table_filter.py)로 평가기준표 청크를 찾지 못했을 때,
'평가기준표'가 어떤 형태인지 보여주는 실제 사례 문서를 임베딩해두고
하이브리드 검색의 세컨드 티어(semantic fallback) 쿼리로 사용한다.
"""

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
    source_file: str = Field(max_length=255, nullable=False)  # app/rag/reference_data 내 원본 파일명
    content: str = Field(sa_column=Column(Text, nullable=False))  # 평가기준표 예시 원문
    embedding: list[float] | None = Field(
        default=None, sa_column=Column(Vector(1024))
    )  # NULL = 미임베딩
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
