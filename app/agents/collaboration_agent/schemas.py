from __future__ import annotations

from pydantic import BaseModel, Field


class PartnerJudgment(BaseModel):
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
