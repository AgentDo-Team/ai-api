from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Enum as SAEnum,
    String,
    Text,
    func,
)
from sqlmodel import Field, SQLModel, Column
from app.core.enums import CompanyScale, CreditRating, SpGrade


class Company(SQLModel, table=True):
    __tablename__ = "companies"

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, primary_key=True, autoincrement=True),
    )
    # 계정 = 회사. 로그인 이메일/비밀번호를 이 테이블이 직접 갖는다.
    email: str = Field(
        sa_column=Column(String(255), unique=True, nullable=False),
    )  # 로그인 이메일 (중복 불가)
    hashed_password: str = Field(
        sa_column=Column(String(255), nullable=False),
    )  # bcrypt 해시 (평문 저장 금지)
    name: str | None = Field(default=None, max_length=200)  # 회사명
    contact_name: str | None = Field(default=None, max_length=100)  # 담당자 이름
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )


class Partner(SQLModel, table=True):
    """회사가 보유한 협력사(회사당 N건).

    공고 분석의 약점(weakness)을 이 협력사가 해결해줄 수 있는지 LLM 이 판단할 때
    근거로 사용된다. CRUD 단계에서는 임베딩하지 않는다(tool 기반 텍스트 판단).
    """

    __tablename__ = "partners"

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
    name: str = Field(max_length=200, nullable=False)  # 협력사명
    domain: str | None = Field(default=None, max_length=100)  # 사업 분야
    tech_stack: str | None = Field(default=None, max_length=200)  # 보유 기술스택
    description: str | None = Field(default=None, sa_column=Column(Text))  # 상세 설명
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
    company_scale: CompanyScale = Field(
        default=CompanyScale.MIDDLE,
        sa_column=Column(SAEnum(CompanyScale))
    )  # 기업규모 (대/중/소)
    target_techs: str | None = Field(default=None, max_length=200)  # 주력 기술/사업
    offered_solutions: str | None = Field(default=None, max_length=200)  # 보유 솔루션
    strengths_diff: str | None = Field(
        default=None, sa_column=Column(Text)
    )  # 강점과 차별점
    credit_rating: CreditRating = Field(
        default = CreditRating.A_PLUS,
        sa_column=Column(SAEnum(CreditRating))
    )  # 신용평가등급
    sp_grade: SpGrade = Field(
        default = SpGrade.GRADE_3,
        sa_column=Column(SAEnum(SpGrade))
    )  # SP등급
    # 소프트 필터링용 dense 벡터. 전송 시점에 지연 임베딩 (NULL = 미임베딩)
    # 렉시컬(정확 용어) 매칭은 chunks.content BM25 인덱스가 담당 → 희소벡터 컬럼 불필요
    embedding: list[float] | None = Field(
        default=None, sa_column=Column(Vector(1024))
    )  # 밀집 벡터 (dense), NULL = 미임베딩
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
    # 소프트 필터링용 dense 벡터. 전송 시점에 지연 임베딩 (NULL = 미임베딩)
    # 렉시컬(정확 용어) 매칭은 chunks.content BM25 인덱스가 담당 → 희소벡터 컬럼 불필요
    embedding: list[float] | None = Field(
        default=None, sa_column=Column(Vector(1024))
    )  # 밀집 벡터 (dense), NULL = 미임베딩
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
