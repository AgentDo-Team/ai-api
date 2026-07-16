"""회사 / 회사 프로필 / 회사 프로젝트 요청·응답 DTO.

Read 응답에는 embedding(1024 float) 을 싣지 않고, 임베딩이 채워졌는지만 `embedded` 로 알려준다.
CRUD 는 임베딩하지 않으므로 지금은 항상 false 이고, 나중에 추천 단계에서 채워진다.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.db.models.company import Company, CompanyProfile, CompanyProject

# --------------------------------------------------------------------------- #
# Company
# --------------------------------------------------------------------------- #


class CompanyUpdate(BaseModel):
    """부분 수정. 보낸 필드만 반영된다."""

    name: str | None = Field(default=None, max_length=200, description="회사명")
    contact_name: str | None = Field(
        default=None, max_length=100, description="담당자 이름"
    )
    email: EmailStr | None = Field(default=None, description="회사 이메일")


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="회사 ID")
    name: str | None = Field(default=None, description="회사명")
    contact_name: str | None = Field(default=None, description="담당자 이름")
    email: str | None = Field(default=None, description="회사 이메일")
    created_at: datetime | None = Field(default=None, description="생성 시각")

    @classmethod
    def of(cls, company: Company) -> "CompanyRead":
        return cls.model_validate(company)


# --------------------------------------------------------------------------- #
# CompanyProfile (회사 1건당 1개)
# --------------------------------------------------------------------------- #


class CompanyProfileCreate(BaseModel):
    company_scale: str | None = Field(
        default=None, max_length=50, description="기업규모 (대/중견/중소)", examples=["중소기업"]
    )
    target_techs: str | None = Field(
        default=None,
        max_length=200,
        description="주력 기술/사업",
        examples=["AI, RAG, LLM 애플리케이션"],
    )
    offered_solutions: str | None = Field(
        default=None,
        max_length=200,
        description="보유 솔루션",
        examples=["입찰공고 분석 SaaS"],
    )
    strengths_diff: str | None = Field(
        default=None,
        description="강점과 차별점",
        examples=["국방 도메인 RAG 구축 경험 다수"],
    )
    credit_rating: str | None = Field(
        default=None, max_length=50, description="신용평가등급", examples=["A+"]
    )
    sp_grade: str | None = Field(
        default=None, max_length=50, description="SP등급", examples=["1등급"]
    )


class CompanyProfileUpdate(CompanyProfileCreate):
    """부분 수정. 보낸 필드만 반영된다."""


class CompanyProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="프로필 ID")
    company_id: int = Field(description="소속 회사 ID")
    company_scale: str | None = None
    target_techs: str | None = None
    offered_solutions: str | None = None
    strengths_diff: str | None = None
    credit_rating: str | None = None
    sp_grade: str | None = None
    embedded: bool = Field(
        default=False,
        description="임베딩이 채워졌는지 여부. CRUD 는 임베딩하지 않으므로 추천 단계 전까지는 false.",
    )
    updated_at: datetime | None = Field(default=None, description="수정 시각")

    @classmethod
    def of(cls, profile: CompanyProfile) -> "CompanyProfileRead":
        return cls.model_validate(profile).model_copy(
            update={"embedded": profile.embedding is not None}
        )


# --------------------------------------------------------------------------- #
# CompanyProject (회사 1건당 N개)
# --------------------------------------------------------------------------- #


class CompanyProjectCreate(BaseModel):
    title: str = Field(
        max_length=300,
        description="프로젝트명",
        examples=["육군 통합 물자관리 시스템 고도화"],
    )
    client: str | None = Field(
        default=None, max_length=200, description="고객사 이름", examples=["국방부"]
    )
    domain: str | None = Field(
        default=None, max_length=100, description="도메인", examples=["국방"]
    )
    tech_stack: str | None = Field(
        default=None,
        max_length=200,
        description="사용 기술 스택",
        examples=["Python, FastAPI, PostgreSQL"],
    )
    develop_features: str | None = Field(
        default=None, description="개발한 주요 기능", examples=["재고 예측, 배치 정산"]
    )
    content: str | None = Field(default=None, description="프로젝트 상세 내용")
    performance: str | None = Field(
        default=None,
        description="실적 결과 (정량적 성과)",
        examples=["처리 속도 40% 개선"],
    )


class CompanyProjectUpdate(BaseModel):
    """부분 수정. 보낸 필드만 반영된다."""

    title: str | None = Field(default=None, max_length=300, description="프로젝트명")
    client: str | None = Field(default=None, max_length=200, description="고객사 이름")
    domain: str | None = Field(default=None, max_length=100, description="도메인")
    tech_stack: str | None = Field(default=None, max_length=200, description="사용 기술 스택")
    develop_features: str | None = Field(default=None, description="개발한 주요 기능")
    content: str | None = Field(default=None, description="프로젝트 상세 내용")
    performance: str | None = Field(default=None, description="실적 결과")


class CompanyProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="프로젝트 ID")
    company_id: int = Field(description="소속 회사 ID")
    title: str
    client: str | None = None
    domain: str | None = None
    tech_stack: str | None = None
    develop_features: str | None = None
    content: str | None = None
    performance: str | None = None
    embedded: bool = Field(
        default=False,
        description="임베딩이 채워졌는지 여부. CRUD 는 임베딩하지 않으므로 추천 단계 전까지는 false.",
    )
    created_at: datetime | None = Field(default=None, description="생성 시각")

    @classmethod
    def of(cls, project: CompanyProject) -> "CompanyProjectRead":
        return cls.model_validate(project).model_copy(
            update={"embedded": project.embedding is not None}
        )
