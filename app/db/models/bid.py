from datetime import datetime
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
from sqlmodel import Field, SQLModel
import enum
from datetime import datetime
from typing import Optional

import sqlmodel

class ParseStatus(str, enum.Enum):
    PENDING = "PENDING"  # 파싱 완료, 청킹 대기 중
    CHUNKED = "CHUNKED"  # 청킹 및 벡터 DB 저장 완료
    EMBEDDED = "EMBEDDED" # 임베딩 완료
    ERROR = "ERROR"      # 파싱 또는 처리 중 에러 발생


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
    parse_status: ParseStatus = sqlmodel.Field(
        default=ParseStatus.PENDING,
        sa_column=Column(SAEnum(ParseStatus))
        ) # 파싱 상태 (Enum)
    raw_md_text: Optional[str] = sqlmodel.Field(default=None) # 마크다운 원본 전체 텍스트  
    # 하드 필터링용 정형 메타데이터 (나라장터 API가 공고 단위로 제공)
    procurement_clsfc_no: str | None = Field(
        default=None, max_length=50
    )  # 공공조달 분류번호 (도메인 코드, 예: 81111513) - pubPrcrmntClsfcNo
    procurement_clsfc_nm: str | None = Field(
        default=None, max_length=200
    )  # 공공조달 분류명 (예: 클라우드서비스) - pubPrcrmntClsfcNm
    joint_venture_method: str | None = Field(
        default=None, max_length=50
    )  # 공동수급 방식명 (값 존재 = 공동수급 가능) - cmmnSpldmdMethdNm
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
