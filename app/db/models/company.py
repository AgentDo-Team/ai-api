from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlmodel import Field, SQLModel


class Company(SQLModel, table=True):
    __tablename__ = "companies"

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, primary_key=True, autoincrement=True),
    )
    name: str | None = Field(default=None, max_length=200)  # 회사명
    contact_name: str | None = Field(default=None, max_length=100)  # 담당자 이름
    email: str | None = Field(
        default=None,
        sa_column=Column(String(255), unique=True),
    )  # 회사 이메일
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )


class CompanyProfile(SQLModel, table=True):
    __tablename__ = "company_profiles"

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, primary_key=True, autoincrement=True),
    )
    company_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        )
    )
    company_scale: str | None = Field(default=None, max_length=50)  # 기업규모 (대/중/소)
    target_techs: str | None = Field(default=None, max_length=200)  # 주력 기술/사업
    offered_solutions: str | None = Field(default=None, max_length=200)  # 보유 솔루션
    strengths_diff: str | None = Field(
        default=None, sa_column=Column(Text)
    )  # 강점과 차별점
    credit_rating: str | None = Field(default=None, max_length=50)  # 신용평가등급
    sp_grade: str | None = Field(default=None, max_length=50)  # SP등급
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        ),
    )


class CompanyProject(SQLModel, table=True):
    __tablename__ = "company_projects"

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
    title: str = Field(max_length=300, nullable=False)  # 프로젝트명
    client: str | None = Field(default=None, max_length=200)  # 고객사 이름
    domain: str | None = Field(default=None, max_length=100)  # 도메인 (국방/의료 등)
    tech_stack: str | None = Field(default=None, max_length=200)  # 사용 기술 스택
    develop_features: str | None = Field(
        default=None, sa_column=Column(Text)
    )  # 개발한 주요 기능
    content: str | None = Field(default=None, sa_column=Column(Text))
    performance: str | None = Field(
        default=None, sa_column=Column(Text)
    )  # 실적 결과 (정량적 성과)
    embedding: list[float] | None = Field(
        default=None, sa_column=Column(Vector(1024))
    )  # NULL = 미임베딩
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
