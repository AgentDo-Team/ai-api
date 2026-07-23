
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.company import Partner


class PartnerCreate(BaseModel):
    name: str = Field(
        max_length=200,
        description="협력사명",
        examples=["에이전트두 보안연구소"],
    )
    email: str | None = Field(
        default=None,
        max_length=255,
        description="협력사 담당자 이메일 (협업 제안 메일 수신자)",
        examples=["contact@agentdo.co.kr"],
    )
    domain: str | None = Field(
        default=None, max_length=100, description="사업 분야", examples=["정보보안"]
    )
    tech_stack: str | None = Field(
        default=None,
        max_length=200,
        description="보유 기술스택",
        examples=["침해대응, 취약점진단, WAF"],
    )
    description: str | None = Field(
        default=None,
        description="상세 설명 (제공 가능한 역량/강점 등)",
        examples=["공공 SI 보안 관제 10년, 국방 도메인 인증 다수 보유"],
    )


class PartnerUpdate(BaseModel):

    name: str | None = Field(default=None, max_length=200, description="협력사명")
    email: str | None = Field(
        default=None, max_length=255, description="협력사 담당자 이메일 (협업 제안 메일 수신자)"
    )
    domain: str | None = Field(default=None, max_length=100, description="사업 분야")
    tech_stack: str | None = Field(
        default=None, max_length=200, description="보유 기술스택"
    )
    description: str | None = Field(default=None, description="상세 설명")


class PartnerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="협력사 ID")
    company_id: int = Field(description="소속 회사 ID")
    name: str
    email: str | None = None
    domain: str | None = None
    tech_stack: str | None = None
    description: str | None = None
    created_at: datetime | None = Field(default=None, description="생성 시각")

    @classmethod
    def of(cls, partner: Partner) -> "PartnerRead":
        return cls.model_validate(partner)
