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
