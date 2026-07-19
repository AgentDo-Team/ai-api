"""
Gmail OAuth 최초 인증 스크립트.

client_secret.json (Google Cloud Console에서 발급받은 OAuth 클라이언트 시크릿)으로 브라우저
동의 화면을 띄워 인증한 뒤, gmail_token.json (access/refresh token)을 생성한다.
서비스 실행 중 반복 호출되는 코드가 아니라 최초 설정 시 1회만 실행하면 되므로
app/clients/gmail_client.py 와 분리해두었다.

실행:
    uv run python -m app.clients.gmail_auth
"""

from __future__ import annotations

from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from app.core.config import settings

# gmail.send 스코프만 요청한다 (메일함 조회/삭제 등은 불필요, 최소 권한 원칙).
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def generate_token(
    client_secret_file: str | Path | None = None,
    token_file: str | Path | None = None,
) -> Path:
    """client_secret.json 으로 브라우저 OAuth 동의를 받고 gmail_token.json 을 생성한다."""
    client_secret_path = Path(client_secret_file or settings.gmail_client_secret_file)
    token_path = Path(token_file or settings.gmail_token_file)

    if not client_secret_path.exists():
        raise FileNotFoundError(
            f"Gmail client secret 파일을 찾을 수 없습니다: {client_secret_path}. "
            "Google Cloud Console > API 및 서비스 > 사용자 인증 정보에서 "
            "OAuth 클라이언트(데스크톱 앱) json을 발급받아 해당 경로에 두세요."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
    creds = flow.run_local_server(port=0)
    token_path.write_text(creds.to_json())
    return token_path


def _main() -> None:
    token_path = generate_token()
    print(f"인증 완료. 토큰 저장 위치: {token_path.resolve()}")


if __name__ == "__main__":
    _main()
