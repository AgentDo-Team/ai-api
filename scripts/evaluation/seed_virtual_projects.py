from __future__ import annotations

import argparse
import asyncio

from sqlmodel import select

from app.db.models.company import Company, CompanyProject
from app.db.session import async_session_factory, engine
from app.schemas.company import CompanyProjectCreate
from app.services import embedding_client, embedding_service


VIRTUAL_PROJECTS = [
    CompanyProjectCreate(
        title="[평가용 가상] 국방 정비문서 RAG 지식검색 플랫폼",
        client="평가용 국방기관",
        domain="국방/공공",
        tech_stack="Python, FastAPI, PostgreSQL, pgvector, OpenAI",
        develop_features="정비교범 파싱·청킹, Dense+BM25 하이브리드 검색, 근거 인용형 질의응답, 문서 접근권한 관리",
        content="국방 정비교범과 기술문서를 구조화하고 RAG 기반으로 검색·질의응답하는 내부 지식 플랫폼을 구축한 가상 평가 프로젝트",
        performance="문서 검색 소요시간 65% 단축, 답변 근거 인용률 95% 달성(가상 평가값)",
    ),
    CompanyProjectCreate(
        title="[평가용 가상] 공공입찰 공고 분석 및 제안지원 SaaS",
        client="평가용 공공조달기관",
        domain="공공조달/문서분석",
        tech_stack="Python, FastAPI, PostgreSQL, pgvector, LLM",
        develop_features="공고 API 수집, RFP 파싱, 요구사항 추출, 하이브리드 유사도 검색, 제안 적합도 분석",
        content="입찰공고와 제안요청서를 자동 수집·분석하고 회사 실적과 요구사항의 유사도를 계산해 추천 근거를 제공하는 가상 SaaS 프로젝트",
        performance="공고 검토시간 70% 단축, 핵심 요구사항 탐색 재현율 92% 달성(가상 평가값)",
    ),
    CompanyProjectCreate(
        title="[평가용 가상] 스마트도시 데이터 분석 AI 플랫폼",
        client="평가용 지방자치단체",
        domain="스마트시티/공공데이터",
        tech_stack="Python, FastAPI, PostgreSQL, Kafka, MLflow",
        develop_features="도시 데이터 수집·정제, 이상징후 탐지, 수요 예측, 운영 대시보드, 외부 시스템 API 연계",
        content="교통·안전·환경 데이터를 통합하고 AI 분석 결과를 도시 운영 담당자에게 제공하는 가상 데이터 플랫폼 구축 프로젝트",
        performance="이상징후 탐지시간 50% 단축, 데이터 처리량 40% 향상(가상 평가값)",
    ),
]


async def seed(company_id: int) -> tuple[list[int], int]:
    async with async_session_factory() as session:
        if await session.get(Company, company_id) is None:
            raise ValueError(f"company {company_id} does not exist")

        existing = list(
            (
                await session.exec(
                    select(CompanyProject).where(
                        CompanyProject.company_id == company_id,
                        CompanyProject.title.in_([item.title for item in VIRTUAL_PROJECTS]),
                    )
                )
            ).all()
        )
        by_title = {project.title: project for project in existing}
        created: list[CompanyProject] = []
        for data in VIRTUAL_PROJECTS:
            if data.title not in by_title:
                project = CompanyProject(company_id=company_id, **data.model_dump())
                session.add(project)
                created.append(project)
        await session.flush()

        to_embed = [project for project in [*existing, *created] if project.embedding is None]
        if to_embed:
            vectors = await embedding_client.embed_texts(
                [embedding_service.project_text(project) for project in to_embed]
            )
            for project, vector in zip(to_embed, vectors):
                project.embedding = vector["dense"]
                session.add(project)
        await session.commit()
        return [project.id for project in created], len(to_embed)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--company-id", type=int, default=2)
    args = parser.parse_args()
    created_ids, embedded_count = await seed(args.company_id)
    print(f"created project IDs: {created_ids}")
    print(f"embedded projects: {embedded_count}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
