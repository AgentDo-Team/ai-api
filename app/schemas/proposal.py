from pydantic import BaseModel, Field
from typing import List

# 클라이언트(프론트엔드)에서 받을 요청 데이터 모델
class DraftRequest(BaseModel):
    user_message: str
    bid_notice_id: int
    company_id: int
    
# --- 초안 데이터 (draft_data) ---
class RelatedProject(BaseModel):
    title: str = Field(description="프로젝트명")
    client: str = Field(description="고객사 이름")
    field: str = Field(description="분야 (예: 국방, 공공)")
    tech_stack: str = Field(description="사용 기술 스택")
    performance: str = Field(description="실적 결과")

class ProposalItem(BaseModel):
    problem: str = Field(description="제안요청서의 문제 및 요구사항")
    evaluation_criteria: str = Field(description="관련 평가기준")
    solution: str = Field(description="자사의 해결방안")
    differentiation: str = Field(description="타사 대비 차별점")

class ProposalDraftData(BaseModel):
    related_projects: List[RelatedProject] = Field(description="관련 성공 프로젝트 목록")
    proposal_advantage: str = Field(description="제안의 핵심 강점 요약")
    business_summary: str = Field(description="사업 이해 및 요약")
    proposal_items: List[ProposalItem] = Field(description="상세 제안 항목 목록")

# --- 참조 데이터 (references) ---
class ProposalReference(BaseModel):
    company_profile: List[str] = Field(description="참조된 자사 프로필 키워드")
    projects: List[int] = Field(description="참조된 프로젝트 ID 목록")
    bid_chunks: List[int] = Field(description="참조된 공고 청크 ID 목록")