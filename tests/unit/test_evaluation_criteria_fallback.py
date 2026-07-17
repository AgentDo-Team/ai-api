"""extract_evaluation_criteria 의 배점표 탐지/대체 템플릿 로직 단위 테스트.

- 규칙 기반 하드필터가 배점표 청크를 찾으면 그 청크 원문으로 세부항목을 추출한다.
- 못 찾으면(임베딩 검색 없이) 표준 평가표 템플릿을 대체 채점표로 사용하고,
  콘솔에 대체 사용 메시지를 출력한다.
"""

from typing import Any

from app.db.models.bid import Chunk
from app.schemas.evaluation import CriteriaExtractionResult, EvalCriterion
from app.services.evaluation_service import (
    _FALLBACK_TEMPLATE_FILENAME,
    EvaluationService,
)


class FakeChunkRepository:
    def __init__(self, chunks: list[Chunk]) -> None:
        self._chunks = chunks

    async def list_by_bid_notice(self, bid_notice_id: int) -> list[Chunk]:
        return self._chunks


class RecordingLLM:
    """complete_structured 에 넘어온 user 텍스트를 기록한다."""

    def __init__(self) -> None:
        self.last_user: str | None = None

    async def complete_structured(
        self, *, system: str, user: str, response_model: type
    ) -> Any:
        self.last_user = user
        return CriteriaExtractionResult(
            criteria=[EvalCriterion(name="기술능력", description=None, max_score=90.0)]
        )


def make_service(chunks: list[Chunk], llm: RecordingLLM) -> EvaluationService:
    return EvaluationService(
        session=None,
        bid_notice_repo=None,
        chunk_repo=FakeChunkRepository(chunks),
        analysis_repo=None,
        search_set_repo=None,
        eval_ref_repo=None,
        llm=llm,
    )


_EVAL_TABLE_CONTENT = (
    "평가항목 배점\n| 평가항목 | 배점 |\n|---|---|\n| 기술능력 | 90점 |\n| 가격 | 10점 |"
)


async def test_uses_matched_chunk_when_hard_filter_hits(capsys):
    """배점표 청크가 규칙 기반으로 걸리면 템플릿을 쓰지 않고 그 청크 원문으로 추출한다."""
    chunks = [Chunk(id=1, bid_notice_id=1, chunk_index=0, content=_EVAL_TABLE_CONTENT)]
    llm = RecordingLLM()
    service = make_service(chunks, llm)

    criteria = await service.extract_evaluation_criteria(bid_notice_id=1)

    assert [c.name for c in criteria] == ["기술능력"]
    assert llm.last_user == _EVAL_TABLE_CONTENT  # 청크 원문 그대로 사용
    assert "대체 채점표를 사용합니다" not in capsys.readouterr().out  # 대체 메시지 없음


async def test_falls_back_to_template_when_no_eval_chunk(capsys):
    """배점표 청크가 없으면 표준 평가표 템플릿을 대체 채점표로 쓰고 콘솔에 알린다."""
    chunks = [
        Chunk(id=1, bid_notice_id=1, chunk_index=0, content="본 사업은 클라우드 전환 사업입니다."),
    ]
    llm = RecordingLLM()
    service = make_service(chunks, llm)

    criteria = await service.extract_evaluation_criteria(bid_notice_id=1)

    assert [c.name for c in criteria] == ["기술능력"]
    # 템플릿 원문이 LLM 입력으로 넘어갔는지 확인
    assert llm.last_user == EvaluationService._load_fallback_template_text()
    assert llm.last_user.strip() != ""

    out = capsys.readouterr().out
    assert "적절한 배점표 청크를 찾지 못해 대체 채점표를 사용합니다" in out
    assert _FALLBACK_TEMPLATE_FILENAME in out
