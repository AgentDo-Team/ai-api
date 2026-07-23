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
    ) 
    
    search_set_id: int = Field(
        sa_column=Column(
            BigInteger,
            # ForeignKey("companies.id", ondelete="CASCADE"), 
            nullable=False,
        )
    )  
    
    company_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        )
    )  

    draft_data: dict = Field(
        sa_column=Column(JSONB, nullable=False)
    )  
    file_name: Optional[str] = Field(
        default=None,
        sa_column=Column(String(500))
    ) 
    
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )