"""협업 제안 메일 초안 작성 서비스.

우리 회사/협력사/보완이 필요한 입찰공고 정보를 조회하고, 부족한 부분에 대한 설명을 LLM으로
생성해 메일 양식(수신자/제목/본문)에 채워 넣는다.

LangGraph 파이프라인에서는 메일 작성(compose) → HITL 검수(승인/취소) → 발송
(app.clients.gmail_client.send_email) 순서로 쓰이므로, 이 서비스는 DB 저장이나 발송 없이
초안만 반환한다. 수신자 주소는 협력사(Partner.email)에서 가져온다.
"""

from __future__ import annotations

from app.common.exceptions import AppException
from app.db.repositories.bid_notice_repository import BidNoticeRepository
from app.db.repositories.company_repository import CompanyRepository, PartnerRepository
from app.llm.base import LLMProvider
from app.schemas.collaboration_email import CollaborationEmailDraft, HelpNeededSummary

_HELP_NEEDED_SYSTEM_PROMPT = (
    "너는 입찰공고 공동수급을 제안하는 협업 메일의 한 문단을 작성하는 어시스턴트다. "
    "우리 회사가 특정 입찰공고를 수행하는 데 있어 부족한 부분과, 협업사가 어떤 도움을 줄 수 있는지를 "
    "정중하고 구체적인 한국어 존댓말 1~2문장으로 작성해라. 과장하지 말고, 주어진 정보 범위 안에서만 작성해라."
)

_SUBJECT_TEMPLATE = "[협업 제안] 귀사와 {company_name}의 공동 캠페인 진행을 제안드립니다."

_BODY_TEMPLATE = (
    "안녕하세요, {partner_name}님, {company_name}의 {contact_name}입니다.\n"
    "이번에 좋은 기회로 협업을 제안드리고자 연락드렸습니다.\n\n"
    "저희 {company_name}은 최근 {project_title}를 진행하려고 합니다\n"
    "{help_needed}\n\n"
    "관련하여 보다 상세한 내용과 캠페인 기획안은 차후 다시 연락드리겠습니다."
)


class CollaborationEmailService:
    def __init__(
        self,
        company_repo: CompanyRepository,
        partner_repo: PartnerRepository,
        bid_notice_repo: BidNoticeRepository,
        llm: LLMProvider,
    ) -> None:
        self.company_repo = company_repo
        self.partner_repo = partner_repo
        self.bid_notice_repo = bid_notice_repo
        self.llm = llm

    async def compose(
        self,
        company_id: int,
        partner_id: int,
        bid_notice_id: int,
        gap_description: str,
    ) -> CollaborationEmailDraft:
        company = await self.company_repo.get(company_id)
        if company is None:
            raise AppException("회사를 찾을 수 없습니다.", status_code=404)

        partner = await self.partner_repo.get(partner_id)
        if partner is None:
            raise AppException("협업할 협력사를 찾을 수 없습니다.", status_code=404)
        if not partner.email:
            raise AppException(
                "협력사에 등록된 이메일 주소가 없어 메일을 보낼 수 없습니다.", status_code=422
            )

        bid_notice = await self.bid_notice_repo.get(bid_notice_id)
        if bid_notice is None:
            raise AppException("입찰공고를 찾을 수 없습니다.", status_code=404)

        summary = await self.llm.complete_structured(
            system=_HELP_NEEDED_SYSTEM_PROMPT,
            user=(
                f"[우리 회사] {company.name}\n"
                f"[진행 예정 프로젝트] {bid_notice.title}\n"
                f"[보완이 필요한 부분]\n{gap_description}"
            ),
            response_model=HelpNeededSummary,
        )

        subject = _SUBJECT_TEMPLATE.format(company_name=company.name)
        body = _BODY_TEMPLATE.format(
            partner_name=partner.name,
            company_name=company.name,
            contact_name=company.contact_name or "담당자",
            project_title=bid_notice.title,
            help_needed=summary.help_needed,
        )
        return CollaborationEmailDraft(to=partner.email, subject=subject, body=body)
