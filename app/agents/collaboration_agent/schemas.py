"""회사 약점 해결 에이전트의 LLM 구조화 출력(response_model) 스키마."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PartnerJudgment(BaseModel):
    """협력사가 공고 약점을 해소할 수 있는지에 대한 판단.

    LLM 이 partner_id 를 직접 만들어내면 환각 위험이 있어, 조회한 협력사 리스트의
    0-base 인덱스(partner_index)로 지목하게 하고 노드에서 실제 id 로 매핑한다.
    """

    can_resolve: bool = Field(
        description="보유 협력사 중 하나로 공고의 약점을 실질적으로 보완할 수 있으면 true"
    )
    partner_index: int | None = Field(
        default=None,
        description="약점을 해소할 수 있는 협력사의 인덱스(조회된 협력사 목록의 0-base 순번). "
        "can_resolve 가 false 면 null.",
    )
    gap_description: str = Field(
        description="협력사가 보완해줄 수 있는 부족한 부분(약점)에 대한 1~2문장 설명. "
        "이후 협업 제안 메일 작성에 그대로 쓰인다.",
    )
    reason: str = Field(description="판단 근거(한국어 1~2문장)")
