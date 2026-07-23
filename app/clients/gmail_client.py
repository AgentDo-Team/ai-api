from __future__ import annotations

import argparse
import base64
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.clients.gmail_auth import SCOPES
from app.core.config import settings


def get_credentials(token_file: str | Path | None = None) -> Credentials:
    token_path = Path(token_file or settings.gmail_token_file)

    if not token_path.exists():
        raise FileNotFoundError(
            f"Gmail token 파일을 찾을 수 없습니다: {token_path}. "
            "먼저 `uv run python -m app.clients.gmail_auth` 를 실행해 최초 인증을 완료하세요."
        )

    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds.valid:
        return creds

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token_path.write_text(creds.to_json())
            return creds
        except RefreshError as exc:
            raise RuntimeError(
                "Gmail refresh token이 만료/폐기되었습니다. "
                "`uv run python -m app.clients.gmail_auth` 를 다시 실행해 재인증하세요."
            ) from exc

    raise RuntimeError(
        "유효한 Gmail 인증 정보가 없습니다. "
        "`uv run python -m app.clients.gmail_auth` 를 실행해 재인증하세요."
    )


def get_gmail_service(credentials: Credentials | None = None):
    return build("gmail", "v1", credentials=credentials or get_credentials())


def _build_raw_message(sender: str | None, to: str, subject: str, body: str) -> dict:
    message = MIMEText(body, "plain", "utf-8")
    message["to"] = to
    message["subject"] = subject
    if sender:
        message["from"] = sender
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    return {"raw": raw}


def send_email(
    to: str,
    subject: str,
    body: str,
    sender: str | None = None,
    service=None,
) -> dict:
    
    gmail_service = service or get_gmail_service()
    raw_message = _build_raw_message(sender or settings.gmail_sender_email, to, subject, body)

    try:
        sent = gmail_service.users().messages().send(userId="me", body=raw_message).execute()
    except HttpError as exc:
        raise RuntimeError(f"Gmail 발송 실패: {exc}") from exc

    return sent


def _main() -> None:
    parser = argparse.ArgumentParser(description="Gmail API 발송 테스트")
    parser.add_argument("--to", required=True, help="수신자 이메일 주소")
    parser.add_argument("--subject", default="[bidpick] Gmail API 발송 테스트")
    parser.add_argument("--body", default="app/clients/gmail_client.py 단독 실행 검증 메일입니다.")
    args = parser.parse_args()

    result = send_email(to=args.to, subject=args.subject, body=args.body)
    print(f"발송 완료. Gmail message id: {result.get('id')}")


if __name__ == "__main__": 
    _main()
