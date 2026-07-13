"""회원가입·로그인 비즈니스 로직."""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.common.exceptions import AppException
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models.user import User
from app.schemas.auth import LoginRequest, SignupRequest


async def signup(session: AsyncSession, data: SignupRequest) -> User:
    """새 사용자를 등록한다. 이메일이 이미 존재하면 409를 발생시킨다."""
    existing = await session.scalar(select(User).where(User.email == data.email))
    if existing is not None:
        raise AppException("이미 가입된 이메일입니다.", status_code=409)

    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def login(session: AsyncSession, data: LoginRequest) -> str:
    """이메일/비밀번호를 검증하고 액세스 토큰을 반환한다.

    이메일이 없거나 비밀번호가 틀리면 동일하게 401을 발생시킨다
    (어느 쪽이 틀렸는지 노출하지 않기 위함).
    """
    user = await session.scalar(select(User).where(User.email == data.email))
    if user is None or not verify_password(data.password, user.hashed_password):
        raise AppException("이메일 또는 비밀번호가 올바르지 않습니다.", status_code=401)

    return create_access_token(subject=user.id)
