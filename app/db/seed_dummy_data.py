"""평가 파이프라인 수동 검증용 더미데이터 생성/정리 스크립트.

모든 더미 행은 아래 마커로 식별 가능하다:
  - BidNotice.notice_no  == DUMMY_NOTICE_NO ("DUMMY-EVAL-TEST")
  - Company.email        == DUMMY_COMPANY_EMAIL ("dummy-eval-test@bidpick.local")

cleanup() 은 이 마커로 더미 BidNotice/Company/SearchSet 을 찾아 삭제한다.
FK ON DELETE CASCADE 로 Chunk/CompanyProfile/CompanyProject 등 하위 행은 함께 삭제된다.

사용법:
  uv run python -m app.db.seed_dummy_data seed
  uv run python -m app.db.seed_dummy_data cleanup
"""

from __future__ import annotations

import argparse
import asyncio

from sqlmodel import select

# 모든 모델을 import 하여 SQLModel.metadata 에 테이블을 등록한다.
import app.db.models  # noqa: F401
from app.core.config import settings
from app.db.models.bid import BidNotice, Chunk
from app.db.models.company import Company, CompanyProfile, CompanyProject
from app.db.models.search import SearchSet
from app.db.session import async_session_factory
from app.llm.openai_provider import OpenAIProvider

DUMMY_NOTICE_NO = "DUMMY-EVAL-TEST"
DUMMY_COMPANY_EMAIL = "dummy-eval-test@bidpick.local"

_DUMMY_CHUNKS = [
    # 0: 일반 산문 (사업 개요) - 평가표 아님
    "본 사업은 ○○공단의 노후 전산시스템을 클라우드 기반으로 전환하는 것을 목적으로 한다. "
    "사업 기간은 계약체결일로부터 8개월이며, 사업 예산은 15억원이다.",
    # 1: 요구사항 총괄표 (distractor) - 배점 없는 요구사항 표라 배제되어야 함
    "## 요구사항 총괄표\n"
    "| 고유번호 | 요구사항명 | 요구사항 분류 |\n"
    "|---|---|---|\n"
    "| SFR-001 | 사용자 인증 | 기능 |\n"
    "| PFR-002 | 응답시간 3초 이내 | 성능 |",
    # 2: 평가기준표 (핵심 타겟 청크)
    "## 평가 항목 및 배점\n"
    "제안서 평가는 정성적 평가와 정량적 평가로 구분하며 총 100점 만점으로 한다.\n"
    "| 평가 항목 | 배점 |\n"
    "|---|---|\n"
    "| 기술능력 평가 (유사 사업 수행실적 및 기술 이해도) | 40점 |\n"
    "| 사업수행계획 평가 (인력 구성 및 투입 계획의 적절성) | 30점 |\n"
    "| 가격 평가 | 30점 |\n"
    "합계: 100점",
    # 3: 평가기준 보충설명 (기술능력 평가 세부 맥락)
    "기술능력 평가는 입찰자가 최근 3년 이내 수행한 유사 규모(10억원 이상)의 공공기관 "
    "클라우드 전환 사업 실적을 정성적으로 평가하며, 투입 인력의 관련 자격증 보유 현황도 함께 본다.",
    # 4: 평가기준 보충설명 (사업수행계획 세부 맥락)
    "사업수행계획 평가는 프로젝트관리(PM) 경력 5년 이상 인력의 투입 여부와, "
    "단계별 일정 계획의 현실성, 위험관리 방안의 구체성을 기준으로 한다.",
    # 5: 일반 산문 (계약 조건) - 평가표 아님
    "계약 체결 후 30일 이내에 착수계를 제출하여야 하며, 하도급은 발주기관의 사전 승인을 받아야 한다.",
]


async def seed() -> None:
    llm = OpenAIProvider() if settings.openai_api_key else None
    if llm is None:
        print("⚠️  OPENAI_API_KEY 미설정: 청크 임베딩을 건너뜁니다(dense 검색은 결과가 비게 됩니다).")

    async with async_session_factory() as session:
        bid_notice = BidNotice(
            notice_no=DUMMY_NOTICE_NO,
            title="[더미] ○○공단 클라우드 전환 사업",
            demand_org="○○공단",
            budget_krw=1_500_000_000,
            parse_status="PARSED",
        )
        session.add(bid_notice)
        await session.flush()

        for idx, content in enumerate(_DUMMY_CHUNKS):
            embedding = await llm.embed(content) if llm else None
            session.add(
                Chunk(
                    bid_notice_id=bid_notice.id,
                    chunk_index=idx,
                    page_no=idx // 2 + 1,
                    content=content,
                    embedding=embedding,
                )
            )

        company = Company(
            email=DUMMY_COMPANY_EMAIL,
            hashed_password="dummy-not-a-real-hash",
            name="[더미] 에이전트두",
            contact_name="김테스트",
        )
        session.add(company)
        await session.flush()

        session.add(
            CompanyProfile(
                company_id=company.id,
                company_scale="중소기업",
                target_techs="클라우드 전환, AI/RAG",
                offered_solutions="공공기관 클라우드 마이그레이션 솔루션",
                strengths_diff="공공기관 클라우드 전환 실적 다수 보유",
                credit_rating="A+",
                sp_grade="1등급",
            )
        )

        session.add(
            CompanyProject(
                company_id=company.id,
                title="□□부 전산시스템 클라우드 전환 사업",
                client="□□부",
                domain="공공행정",
                tech_stack="AWS, Kubernetes, Python",
                develop_features="레거시 시스템 클라우드 이관, CI/CD 파이프라인 구축",
                content="12억원 규모의 공공기관 클라우드 전환 사업을 수행하며 PM 경력 8년 인력을 투입했다.",
                performance="시스템 가용성 99.9% 달성, 운영비 25% 절감",
            )
        )
        session.add(
            CompanyProject(
                company_id=company.id,
                title="△△청 데이터 분석 플랫폼 구축",
                client="△△청",
                domain="공공행정",
                tech_stack="Python, PostgreSQL, FastAPI",
                develop_features="데이터 파이프라인, 대시보드",
                content="5억원 규모 데이터 분석 플랫폼 구축 사업.",
                performance="분석 처리 시간 40% 단축",
            )
        )

        search_set = SearchSet(company_id=company.id, title="[더미] 검색세트", status="PENDING")
        session.add(search_set)
        await session.flush()

        await session.commit()
        print(
            f"✅ 더미데이터 생성 완료: bid_notice_id={bid_notice.id}, "
            f"company_id={company.id}, search_set_id={search_set.id}"
        )


async def cleanup() -> None:
    """bid_notices 는 analysis_results 에서 ON DELETE RESTRICT 로 참조되므로,
    evaluate() 실행으로 생긴 analysis_results 를 먼저 지우기 위해 search_set 을
    bid_notice 보다 먼저 삭제한다(search_set 삭제 시 analysis_results 는 CASCADE).
    """
    async with async_session_factory() as session:
        companies = (
            await session.exec(select(Company).where(Company.email == DUMMY_COMPANY_EMAIL))
        ).all()
        for company in companies:
            search_sets = (
                await session.exec(select(SearchSet).where(SearchSet.company_id == company.id))
            ).all()
            for search_set in search_sets:
                await session.delete(search_set)
            await session.delete(company)
        await session.flush()

        bid_notices = (
            await session.exec(select(BidNotice).where(BidNotice.notice_no == DUMMY_NOTICE_NO))
        ).all()
        for bid_notice in bid_notices:
            await session.delete(bid_notice)

        await session.commit()
        print(f"✅ 더미데이터 정리 완료: bid_notice {len(bid_notices)}건, company {len(companies)}건 삭제")


def main() -> None:
    parser = argparse.ArgumentParser(description="평가 파이프라인 더미데이터 관리")
    parser.add_argument("action", choices=["seed", "cleanup"])
    args = parser.parse_args()

    if args.action == "seed":
        asyncio.run(seed())
    else:
        asyncio.run(cleanup())


if __name__ == "__main__":
    main()
