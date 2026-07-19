"""챗봇 채팅 세션 / 메시지 요청·응답 DTO.

세션은 기존 SearchSet(=검색 세션/채팅방)을 재사용하고, 메시지는 기존 ChatMessage
테이블에 role(user/assistant)/content 로 쌓는다. 별도 챗봇 테이블은 만들지 않는다.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.analysis import ChatMessage
from app.db.models.search import SearchSet

# --------------------------------------------------------------------------- #
# ChatSession (= SearchSet)
# --------------------------------------------------------------------------- #


class ChatSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="채팅 세션 ID")
    title: str = Field(description="채팅 세션 제목")
    status: str | None = Field(default=None, description="분석 상태(없으면 순수 채팅 세션)")
    created_at: datetime | None = Field(default=None, description="생성 시각")

    @classmethod
    def of(cls, session: SearchSet) -> "ChatSessionRead":
        return cls.model_validate(session)


# --------------------------------------------------------------------------- #
# ChatMessage
# --------------------------------------------------------------------------- #


class ChatRequest(BaseModel):
    question: str = Field(
        min_length=1,
        description="사용자 질문",
        examples=["이 공고의 주요 과업은 뭐야?"],
    )
    bid_notice_id: int | None = Field(
        default=None,
        ge=1,
        description="근거로 삼을 입찰공고 ID. 있으면 해당 공고 청크를 벡터검색해 답변하고, "
        "없으면 회사 컨텍스트만으로 답변한다.",
    )


class ChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="메시지 ID")
    role: str = Field(description="발화 주체 (user / assistant)")
    content: str | None = Field(default=None, description="메시지 내용")
    created_at: datetime | None = Field(default=None, description="생성 시각")

    @classmethod
    def of(cls, message: ChatMessage) -> "ChatMessageRead":
        return cls.model_validate(message)
