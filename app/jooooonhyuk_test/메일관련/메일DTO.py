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
    """메일 양식에 값을 채운 결과. HITL 검수 후 그대로 gmail_client.send_email 의 subject/body 로 쓴다."""

    subject: str
    body: str
