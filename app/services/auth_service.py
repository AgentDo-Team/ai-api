"""회원가입·로그인 비즈니스 로직 (계정 = 회사)."""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.common.exceptions import AppException
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models.company import Company
from app.schemas.auth import LoginRequest, SignupRequest


async def signup(session: AsyncSession, data: SignupRequest) -> Company:
    """새 회사 계정을 등록한다. 이메일이 이미 존재하면 409를 발생시킨다."""
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
    """이메일/비밀번호를 검증하고 (액세스 토큰, 계정)을 반환한다.

    이메일이 없거나 비밀번호가 틀리면 동일하게 401을 발생시킨다
    (어느 쪽이 틀렸는지 노출하지 않기 위함).
    """
    company = await session.scalar(
        select(Company).where(Company.email == data.email)
    )
    if company is None or not verify_password(
        data.password, company.hashed_password
    ):
        raise AppException("이메일 또는 비밀번호가 올바르지 않습니다.", status_code=401)

    return create_access_token(subject=company.id), company
