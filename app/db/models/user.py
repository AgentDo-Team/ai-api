from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    String,
    func,
)
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, primary_key=True, autoincrement=True),
    )
    email: str = Field(
        sa_column=Column(String(255), unique=True, nullable=False),
    )  # 로그인 이메일 (중복 불가)
    hashed_password: str = Field(
        sa_column=Column(String(255), nullable=False),
    )  # bcrypt 해시 (평문 저장 금지)
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
