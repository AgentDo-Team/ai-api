from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlmodel import Field, SQLModel


class SearchSet(SQLModel, table=True):
    __tablename__ = "search_sets"

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, primary_key=True, autoincrement=True),
    )
    company_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        )
    )  # 어떤 회사의 검색 세트인지
    title: str = Field(max_length=200, nullable=False)  # 검색 세트 제목
    status: str | None = Field(default=None, max_length=40)  # 분석 상태 (Enum)
    failure_reason: str | None = Field(
        default=None, sa_column=Column(Text)
    )  # 실패 상태일 때 사용자에게 보여줄 안전한 사유
    # 3차 필터 진행률 (프론트 폴링 표시용). 채점이 끝난 공고 수 / 채점 대상 공고 수.
    # 3차 필터 시작 시 0/후보수 로 초기화되고, 공고 채점이 끝날 때마다 current 가 오른다.
    progress_current: int | None = Field(default=None)
    progress_total: int | None = Field(default=None)
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )


class HardFilter(SQLModel, table=True):
    __tablename__ = "hard_filters"

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, primary_key=True, autoincrement=True),
    )
    search_set_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("search_sets.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        )
    )  # 검색세트:하드필터 = 1:1
    domain_code: str | None = Field(
        default=None, sa_column=Column(String(50))
    )  # 도메인 분류코드 (ProcurementCategory 코드값). 한 검색당 하나만 선택 가능
    joint_venture: bool | None = Field(
        default=None, sa_column=Column(Boolean)
    )  # 공동수급여부
    budget_min_krw: int | None = Field(
        default=None, sa_column=Column(BigInteger)
    )  # 최소예산금액
    budget_max_krw: int | None = Field(
        default=None, sa_column=Column(BigInteger)
    )  # 최대예산금액
    deadline: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )  # 마감 일시
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
