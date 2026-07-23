from __future__ import annotations

from pydantic import BaseModel, Field


class HelpNeededSummary(BaseModel):
    help_needed: str = Field(
        description="협업사에게 어떤 도움이 필요한지 정중하고 구체적으로 설명하는 1~2문장"
    )


class CollaborationEmailDraft(BaseModel):
    to: str = Field(description="수신자 이메일 주소 (협력사 담당자)")
    subject: str
    body: str
