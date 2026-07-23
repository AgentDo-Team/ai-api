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
    )  
    title: str = Field(max_length=200, nullable=False)
    status: str | None = Field(default=None, max_length=40)  
    failure_reason: str | None = Field(
        default=None, sa_column=Column(Text)
    )  
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
    )
    domain_code: str | None = Field(
        default=None, sa_column=Column(String(50))
    ) 
    joint_venture: bool | None = Field(
        default=None, sa_column=Column(Boolean)
    )  
    budget_min_krw: int | None = Field(
        default=None, sa_column=Column(BigInteger)
    )  
    budget_max_krw: int | None = Field(
        default=None, sa_column=Column(BigInteger)
    )
    deadline: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )  
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
