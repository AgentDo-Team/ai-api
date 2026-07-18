from datetime import datetime
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel
from typing import Optional

class ProposalDraft(SQLModel, table=True):
    __tablename__ = "proposal_drafts"

    id: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger, primary_key=True, autoincrement=True),
    )
    
    bid_notice_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("bid_notices.id", ondelete="CASCADE"),
            nullable=False,
        )
    )  # 분석 대상 공고 (1:n)
    
    search_set_id: int = Field(
        sa_column=Column(
            BigInteger,
            # ForeignKey("companies.id", ondelete="CASCADE"), 
            nullable=False,
        )
    )  # 매칭된 결과 정보 (1:n)
    
    draft_data: dict = Field(
        sa_column=Column(JSONB, nullable=False)
    )  # Pydantic 모델(ProposalDraftData)의 model_dump() 결과가 저장될 JSONB 컬럼
    
    docx_path: Optional[str] = Field(
        default=None,
        sa_column=Column(String(500))
    )  # 생성된 Word 파일 로컬/보안망 경로

    
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )