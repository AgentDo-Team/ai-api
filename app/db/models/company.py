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
    email: str = Field(
        sa_column=Column(String(255), unique=True, nullable=False),
    )  
    hashed_password: str = Field(
        sa_column=Column(String(255), nullable=False),
    ) 
    name: str | None = Field(default=None, max_length=200)  
    contact_name: str | None = Field(default=None, max_length=100)  
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )


class Partner(SQLModel, table=True):

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
    name: str = Field(max_length=200, nullable=False)  
    email: str | None = Field(default=None, max_length=255)  
    domain: str | None = Field(default=None, max_length=100) 
    tech_stack: str | None = Field(default=None, max_length=200) 
    description: str | None = Field(default=None, sa_column=Column(Text))  
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
    )
    target_techs: str | None = Field(default=None, max_length=200)  
    offered_solutions: str | None = Field(default=None, max_length=200)  
    strengths_diff: str | None = Field(
        default=None, sa_column=Column(Text)
    )  
    credit_rating: CreditRating = Field(
        default = CreditRating.A_PLUS,
        sa_column=Column(SAEnum(CreditRating))
    )
    sp_grade: SpGrade = Field(
        default = SpGrade.GRADE_3,
        sa_column=Column(SAEnum(SpGrade))
    )  
    embedding: list[float] | None = Field(
        default=None, sa_column=Column(Vector(1024))
    ) 
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
    title: str = Field(max_length=300, nullable=False) 
    client: str | None = Field(default=None, max_length=200) 
    domain: str | None = Field(default=None, max_length=100) 
    tech_stack: str | None = Field(default=None, max_length=200) 
    develop_features: str | None = Field(
        default=None, sa_column=Column(Text)
    )
    content: str | None = Field(default=None, sa_column=Column(Text))
    performance: str | None = Field(
        default=None, sa_column=Column(Text)
    )  
    embedding: list[float] | None = Field(
        default=None, sa_column=Column(Vector(1024))
    ) 
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
