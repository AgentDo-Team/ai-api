"""지연 임베딩(lazy embedding) 서비스.

입력폼 저장 시점이 아니라 '전송' 시점에, 아직 임베딩되지 않은
(embedding IS NULL) 자사 프로필/프로젝트를 임베딩 서버로 보내
dense 벡터를 채운다. 한 번 채우면 다음 검색부터는 재사용한다.
(렉시컬 매칭은 chunks.content BM25 인덱스가 담당하므로 희소벡터는 저장하지 않는다.)
"""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models.company import CompanyProfile, CompanyProject
from app.services import embedding_client


def _compose(parts: list[tuple[str, str | None]]) -> str:
    """(라벨, 값) 목록에서 값이 있는 항목만 'label: value' 줄로 이어붙인다."""
    return "\n".join(f"{label}: {value}" for label, value in parts if value)


def profile_text(profile: CompanyProfile) -> str:
    return _compose(
        [
            ("기업규모", profile.company_scale),
            ("주력기술", profile.target_techs),
            ("보유솔루션", profile.offered_solutions),
            ("강점/차별점", profile.strengths_diff),
            ("신용등급", profile.credit_rating),
            ("SP등급", profile.sp_grade),
        ]
    )


def project_text(project: CompanyProject) -> str:
    return _compose(
        [
            ("프로젝트명", project.title),
            ("고객사", project.client),
            ("도메인", project.domain),
            ("기술스택", project.tech_stack),
            ("주요기능", project.develop_features),
            ("내용", project.content),
            ("실적", project.performance),
        ]
    )


async def ensure_company_embedded(session: AsyncSession, company_id: int) -> int:
    """회사의 미임베딩 프로필/프로젝트를 임베딩해 컬럼을 채운다.

    이미 임베딩된(embedding IS NOT NULL) 항목은 건너뛴다.
    임베딩한 항목 수를 반환한다.
    """
    # 1. 아직 임베딩 안 된 프로필/프로젝트 조회
    profile = (
        await session.exec(
            select(CompanyProfile).where(
                CompanyProfile.company_id == company_id,
                CompanyProfile.embedding.is_(None),
            )
        )
    ).first()
    projects = (
        await session.exec(
            select(CompanyProject).where(
                CompanyProject.company_id == company_id,
                CompanyProject.embedding.is_(None),
            )
        )
    ).all()

    # 2. (대상 객체, 임베딩할 텍스트) 목록 구성. 텍스트가 빈 항목은 제외.
    targets: list[tuple[CompanyProfile | CompanyProject, str]] = []
    if profile:
        targets.append((profile, profile_text(profile)))
    for project in projects:
        targets.append((project, project_text(project)))
    targets = [(obj, text) for obj, text in targets if text.strip()]

    if not targets:
        return 0

    # 3. 임베딩 서버 호출 (입력 순서 = 출력 순서)
    vectors = await embedding_client.embed_texts([text for _, text in targets])

    # 4. 결과를 각 객체의 dense 컬럼에 채워 저장 (렉시컬은 BM25가 담당)
    for (obj, _), vector in zip(targets, vectors):
        obj.embedding = vector["dense"]
        session.add(obj)

    await session.commit()
    return len(targets)
