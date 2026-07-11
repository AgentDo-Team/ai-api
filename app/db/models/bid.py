from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class BidNotice(SQLModel, table=True):  # 입찰공고
    __tablename__ = "bid_notices"

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, primary_key=True, autoincrement=True),
    )
    notice_no: str = Field(max_length=50, nullable=False)  # 나라장터 입찰공고번호
    title: str = Field(max_length=500, nullable=False)  # 공고 이름
    demand_org: str | None = Field(default=None, max_length=200)  # 수요 기관
    budget_krw: int | None = Field(
        default=None, sa_column=Column(BigInteger)
    )  # 사업 금액
    bid_deadline: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )  # 마감일자
    rfp_file_url: str | None = Field(
        default=None, max_length=1000
    )  # 제안요청서 다운로드 url
    parse_status: str | None = Field(default=None, max_length=20)  # 파싱 상태 (Enum)
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )


class Chunk(SQLModel, table=True):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("bid_notice_id", "chunk_index", name="uq_chunks_notice_index"),
    )

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, primary_key=True, autoincrement=True),
    )
    bid_notice_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("bid_notices.id", ondelete="CASCADE"),
            nullable=False,
        )
    )  # 어느 공고의 RFP에서 나왔는지 (1:n)
    chunk_index: int = Field(
        sa_column=Column(Integer, nullable=False)
    )  # 문서에서 몇 번째 청크인지
    lexical_weights: dict[str, float] | None = Field(
        default=None, sa_column=Column(JSONB)
    )  # 희소 벡터
    page_no: int | None = Field(default=None, sa_column=Column(Integer))  # 문서 번호
    chunk_metadata: dict | None = Field(
        default=None, sa_column=Column("metadata", JSONB)
    )  # 메타데이터 (Enum) - 어떤 내용에 대한 청크인지
    token_count: int | None = Field(
        default=None, sa_column=Column(Integer)
    )  # 토큰 수 (디버깅용)
    content: str | None = Field(default=None, sa_column=Column(Text))  # 원문 텍스트
    embedding: list[float] | None = Field(
        default=None, sa_column=Column(Vector(1024))
    )  # NULL = 미임베딩
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
