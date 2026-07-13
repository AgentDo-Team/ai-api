"""인증 관련 보안 유틸.

- 비밀번호 해싱/검증: bcrypt (평문은 절대 저장하지 않는다)
- JWT 액세스 토큰 발급/디코드: PyJWT (HS256, secret_key 서명)
"""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    """평문 비밀번호를 bcrypt 해시 문자열로 변환한다."""
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    """평문 비밀번호가 저장된 해시와 일치하는지 검증한다."""
    return bcrypt.checkpw(
        password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def create_access_token(subject: str | int) -> str:
    """subject(사용자 식별자)를 담은 JWT 액세스 토큰을 발급한다.

    payload:
      - sub: 사용자 id (문자열)
      - exp: 만료 시각 (access_token_expire_minutes 후)
    """
    expire = datetime.now(UTC) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {"sub": str(subject), "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """JWT 토큰을 검증·디코드한다.

    만료/서명 오류 시 jwt.PyJWTError 계열 예외를 그대로 전파한다.
    """
    return jwt.decode(
        token, settings.secret_key, algorithms=[settings.jwt_algorithm]
    )
