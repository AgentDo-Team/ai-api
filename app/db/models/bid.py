import enum
from datetime import datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Column,
    Enum as SAEnum,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
import sqlmodel

class ParseStatus(str, enum.Enum):
    PENDING = "PENDING"  # 파싱 완료, 청킹 대기 중
    CHUNKED = "CHUNKED"  # 청킹 및 벡터 DB 저장 완료
    ERROR = "ERROR"      # 파싱 또는 처리 중 에러 발생

class BidNotice(sqlmodel.SQLModel, table=True):  # 입찰공고
    __tablename__ = "bid_notices"

    id: int | None = sqlmodel.Field(
        default=None,
        sa_column=Column(BigInteger, primary_key=True, autoincrement=True),
    )
    notice_no: str = sqlmodel.Field(max_length=50, nullable=False)  # 나라장터 입찰공고번호
    title: str = sqlmodel.Field(max_length=500, nullable=False)  # 공고 이름
    demand_org: str | None = sqlmodel.Field(default=None, max_length=200)  # 수요 기관
    budget_krw: int | None = sqlmodel.Field(
        default=None, sa_column=Column(BigInteger)
    )  # 사업 금액
    bid_deadline: datetime | None = sqlmodel.Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )  # 마감일자
    rfp_file_url: str | None = sqlmodel.Field(
        default=None, max_length=1000
    )  # 제안요청서 다운로드 url
    parse_status: ParseStatus = sqlmodel.Field(
        default=ParseStatus.PENDING,
        sa_column=Column(SAEnum(ParseStatus))
        ) # 파싱 상태 (Enum)
    raw_md_text: Optional[str] = sqlmodel.Field(default=None) # 마크다운 원본 전체 텍스트
    created_at: datetime | None = sqlmodel.Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )


class Chunk(sqlmodel.SQLModel, table=True):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("bid_notice_id", "chunk_index", name="uq_chunks_notice_index"),
    )

    id: int | None = sqlmodel.Field(
        default=None,
        sa_column=Column(BigInteger, primary_key=True, autoincrement=True),
    )
    bid_notice_id: int = sqlmodel.Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("bid_notices.id", ondelete="CASCADE"),
            nullable=False,
        )
    )  # 어느 공고의 RFP에서 나왔는지 (1:n)
    chunk_index: int = sqlmodel.Field(
        sa_column=Column(Integer, nullable=False)
    )  # 문서에서 몇 번째 청크인지
    lexical_weights: dict[str, float] | None = sqlmodel.Field(
        default=None, sa_column=Column(JSONB)
    )  # 희소 벡터
    page_no: int | None = sqlmodel.Field(default=None, sa_column=Column(Integer))  # 문서 번호
    chunk_metadata: dict | None = sqlmodel.Field(
        default=None, sa_column=Column("metadata", JSONB)
    )  # 메타데이터 (Enum) - 어떤 내용에 대한 청크인지
    token_count: int | None = sqlmodel.Field(
        default=None, sa_column=Column(Integer)
    )  # 토큰 수 (디버깅용)
    content: str | None = sqlmodel.Field(default=None, sa_column=Column(Text))  # 원문 텍스트
    embedding: list[float] | None = sqlmodel.Field(
        default=None, sa_column=Column(Vector(1024))
    )  # NULL = 미임베딩
    created_at: datetime | None = sqlmodel.Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
