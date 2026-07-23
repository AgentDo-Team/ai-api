from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.common.exceptions import AppException
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models.company import Company
from app.schemas.auth import LoginRequest, SignupRequest


async def signup(session: AsyncSession, data: SignupRequest) -> Company:
    existing = await session.scalar(
        select(Company).where(Company.email == data.email)
    )
    if existing is not None:
        raise AppException("이미 가입된 이메일입니다.", status_code=409)

    company = Company(
        email=data.email,
        hashed_password=hash_password(data.password),
        name=data.name,
        contact_name=data.contact_name,
    )
    session.add(company)
    await session.commit()
    await session.refresh(company)
    return company


async def login(session: AsyncSession, data: LoginRequest) -> tuple[str, Company]:
    company = await session.scalar(
        select(Company).where(Company.email == data.email)
    )
    if company is None or not verify_password(
        data.password, company.hashed_password
    ):
        raise AppException("이메일 또는 비밀번호가 올바르지 않습니다.", status_code=401)

    return create_access_token(subject=company.id), company
