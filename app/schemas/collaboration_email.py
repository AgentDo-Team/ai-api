"""협업 제안 메일 초안 DTO.

HelpNeededSummary 는 LLM structured output 타겟으로 쓰인다
(OpenAIProvider.complete_structured(response_model=HelpNeededSummary)).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class HelpNeededSummary(BaseModel):
    help_needed: str = Field(
        description="협업사에게 어떤 도움이 필요한지 정중하고 구체적으로 설명하는 1~2문장"
    )


class CollaborationEmailDraft(BaseModel):
    """메일 양식에 값을 채운 결과.

    HITL 검수(승인/취소) 후 그대로 gmail_client.send_email 의 to/subject/body 로 쓴다.
    """

    to: str = Field(description="수신자 이메일 주소 (협력사 담당자)")
    subject: str
    body: str
