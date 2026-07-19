"""CollaborationEmailService.compose 단위 테스트 (DB/LLM 없이).

리포지토리와 LLM 을 가짜로 갈아끼우고 초안 생성 로직만 검증한다.
"""

from types import SimpleNamespace

import pytest

from app.common.exceptions import AppException
from app.schemas.collaboration_email import CollaborationEmailDraft, HelpNeededSummary
from app.services.collaboration_email_service import CollaborationEmailService


class FakeRepo:
    """id → 엔티티 dict 로 .get 만 흉내낸다."""

    def __init__(self, rows: dict | None = None) -> None:
        self.rows = rows or {}

    async def get(self, entity_id: int):
        return self.rows.get(entity_id)


class FakeLLM:
    async def complete_structured(self, *, system, user, response_model, model=None):
        assert response_model is HelpNeededSummary
        return HelpNeededSummary(help_needed="AI 챗봇 구축 경험을 지원해 주시면 감사하겠습니다.")

    async def complete_structured_batch(self, *, requests, response_model, model=None):  # pragma: no cover
        raise NotImplementedError

    async def embed(self, text):  # pragma: no cover
        raise NotImplementedError


def _service(company=None, partner=None, bid_notice=None) -> CollaborationEmailService:
    return CollaborationEmailService(
        company_repo=FakeRepo({1: company} if company else {}),
        partner_repo=FakeRepo({2: partner} if partner else {}),
        bid_notice_repo=FakeRepo({3: bid_notice} if bid_notice else {}),
        llm=FakeLLM(),
    )


async def test_compose_fills_draft():
    company = SimpleNamespace(name="에이전트두", contact_name="김준혁")
    partner = SimpleNamespace(name="협력보안", email="contact@partner.io")
    bid_notice = SimpleNamespace(title="공공 클라우드 전환 사업")
    service = _service(company, partner, bid_notice)

    draft = await service.compose(
        company_id=1, partner_id=2, bid_notice_id=3, gap_description="클라우드 실적 부족"
    )

    assert isinstance(draft, CollaborationEmailDraft)
    assert draft.to == "contact@partner.io"
    assert "에이전트두" in draft.subject
    assert "협력보안" in draft.body
    assert "김준혁" in draft.body
    assert "공공 클라우드 전환 사업" in draft.body
    assert "AI 챗봇 구축 경험" in draft.body


async def test_compose_uses_default_contact_when_missing():
    company = SimpleNamespace(name="에이전트두", contact_name=None)
    partner = SimpleNamespace(name="협력보안", email="contact@partner.io")
    bid_notice = SimpleNamespace(title="공고")
    draft = await _service(company, partner, bid_notice).compose(
        company_id=1, partner_id=2, bid_notice_id=3, gap_description="x"
    )
    assert "담당자" in draft.body


async def test_compose_missing_company_raises_404():
    partner = SimpleNamespace(name="협력보안", email="c@partner.io")
    bid_notice = SimpleNamespace(title="공고")
    with pytest.raises(AppException) as exc:
        await _service(None, partner, bid_notice).compose(
            company_id=1, partner_id=2, bid_notice_id=3, gap_description="x"
        )
    assert exc.value.status_code == 404


async def test_compose_missing_partner_raises_404():
    company = SimpleNamespace(name="에이전트두", contact_name="김준혁")
    bid_notice = SimpleNamespace(title="공고")
    with pytest.raises(AppException) as exc:
        await _service(company, None, bid_notice).compose(
            company_id=1, partner_id=2, bid_notice_id=3, gap_description="x"
        )
    assert exc.value.status_code == 404


async def test_compose_partner_without_email_raises_422():
    company = SimpleNamespace(name="에이전트두", contact_name="김준혁")
    partner = SimpleNamespace(name="협력보안", email=None)
    bid_notice = SimpleNamespace(title="공고")
    with pytest.raises(AppException) as exc:
        await _service(company, partner, bid_notice).compose(
            company_id=1, partner_id=2, bid_notice_id=3, gap_description="x"
        )
    assert exc.value.status_code == 422


async def test_compose_missing_bid_notice_raises_404():
    company = SimpleNamespace(name="에이전트두", contact_name="김준혁")
    partner = SimpleNamespace(name="협력보안", email="c@partner.io")
    with pytest.raises(AppException) as exc:
        await _service(company, partner, None).compose(
            company_id=1, partner_id=2, bid_notice_id=3, gap_description="x"
        )
    assert exc.value.status_code == 404
