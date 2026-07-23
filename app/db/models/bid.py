from datetime import datetime
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Enum as SAEnum,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel
from datetime import datetime
from typing import Optional
import sqlmodel
from app.core.enums import ParseStatus

class BidNotice(SQLModel, table=True):  
    __tablename__ = "bid_notices"

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, primary_key=True, autoincrement=True),
    )
    notice_no: str = Field(max_length=50, nullable=False)  
    title: str = Field(max_length=500, nullable=False)  
    demand_org: str | None = Field(default=None, max_length=200)  
    budget_krw: int | None = Field(
        default=None, sa_column=Column(BigInteger)
    ) 
    bid_deadline: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )
    rfp_file_url: str | None = Field(
        default=None, max_length=1000
    ) 
    parse_status: ParseStatus = Field(
        default=ParseStatus.PENDING,
        sa_column=Column(SAEnum(ParseStatus))
        ) 
    raw_md_text: Optional[str] = sqlmodel.Field(default=None) 
    procurement_clsfc_no: str | None = Field(
        default=None, max_length=50
    )  
    procurement_clsfc_nm: str | None = Field(
        default=None, max_length=200
    )  
    joint_venture_method: str | None = Field(
        default=None, max_length=50
    ) 
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
    )
    chunk_index: int = Field(
        sa_column=Column(Integer, nullable=False)
    ) 
    page_no: int | None = Field(default=None, sa_column=Column(Integer))  
    chunk_metadata: dict | None = Field(
        default=None, sa_column=Column("metadata", JSONB)
    )  
    token_count: int | None = Field(
        default=None, sa_column=Column(Integer)
    )  
    content: str | None = Field(default=None, sa_column=Column(Text)) 
    embedding: list[float] | None = Field(
        default=None, sa_column=Column(Vector(1024))
    )  
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
