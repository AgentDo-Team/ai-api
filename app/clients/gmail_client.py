"""
Gmail API를 이용한 이메일 발송 클라이언트.

- gmail_token.json (access/refresh token)을 읽어 인증하며, 만료 시 refresh token으로
  자동 갱신한다. 최초 발급(브라우저 OAuth 동의)은 app/clients/gmail_auth.py 를
  1회 실행해서 미리 만들어두어야 한다.
- send_email()은 DB 저장 없이 단독으로 호출 가능한 순수 함수로, LangGraph 노드에서
  그대로 재사용한다 (app/agents/collaboration_email 의 send_email 노드).

단독 실행 검증:
    uv run python -m app.clients.gmail_client --to joonlife0901@naver.com
"""

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
    """
    gmail_token.json 을 읽어 인증 정보를 반환한다. 만료된 경우 refresh token으로 갱신한다.
    토큰 파일이 없거나 refresh token마저 만료/폐기된 경우, 재인증이 필요하다는 안내와 함께
    예외를 던진다 (재인증은 app.clients.gmail_auth 를 실행해서 수행한다).
    """
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
    """Gmail API 서비스 객체를 생성한다."""
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
    """
    Gmail API로 이메일을 발송한다. DB 저장 없이 결과(dict, Gmail message id 포함)를 그대로 반환하므로
    LangGraph 노드 함수 안에서 그대로 호출해 쓸 수 있다.
    """
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


if __name__ == "__main__":  # 이 파일이 직접 실행됐을 때만 이 코드를 돌려라
    _main()
