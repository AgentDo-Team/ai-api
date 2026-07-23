from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.common.exceptions import AppException
from app.db.models.company import CompanyProfile, CompanyProject
from app.services import embedding_client


def _compose(parts: list[tuple[str, str | None]]) -> str:
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


def _validate_company_inputs(
    profile: CompanyProfile | None, projects: list[CompanyProject]
) -> None:
    """검색에 필요한 회사 입력폼이 실제 임베딩 가능한 상태인지 검증한다."""
    if profile is None:
        raise AppException("회사 프로필을 먼저 작성해 주세요.", status_code=409)
    if not projects:
        raise AppException("성공 프로젝트를 하나 이상 작성해 주세요.", status_code=409)
    if not profile_text(profile).strip():
        raise AppException(
            "회사 프로필에 임베딩할 수 있는 내용을 입력해 주세요.", status_code=409
        )
    if not any(project_text(project).strip() for project in projects):
        raise AppException(
            "성공 프로젝트에 임베딩할 수 있는 내용을 입력해 주세요.", status_code=409
        )


def _validate_embedding_vectors(vectors: list[dict], expected_count: int) -> None:
    """외부 임베딩 응답이 입력 항목과 1:1로 대응하는지 확인한다."""
    if len(vectors) != expected_count:
        raise AppException(
            "임베딩 결과 수가 입력 항목 수와 일치하지 않습니다.", status_code=502
        )
    if any(not vector.get("dense") for vector in vectors):
        raise AppException("비어 있는 임베딩 결과가 반환되었습니다.", status_code=502)


async def ensure_company_embedded(session: AsyncSession, company_id: int) -> int:
    
    profile = (
        await session.exec(
            select(CompanyProfile).where(CompanyProfile.company_id == company_id)
        )
    ).first()
    projects = (
        await session.exec(
            select(CompanyProject).where(CompanyProject.company_id == company_id)
        )
    ).all()
    _validate_company_inputs(profile, list(projects))

    targets: list[tuple[CompanyProfile | CompanyProject, str]] = []
    if profile.embedding is None:
        targets.append((profile, profile_text(profile)))
    for project in projects:
        if project.embedding is None:
            targets.append((project, project_text(project)))
    targets = [(obj, text) for obj, text in targets if text.strip()]

    if not targets:
        return 0

    vectors = await embedding_client.embed_texts([text for _, text in targets])
    _validate_embedding_vectors(vectors, len(targets))

    for (obj, _), vector in zip(targets, vectors, strict=True):
        obj.embedding = vector["dense"]
        session.add(obj)

    await session.commit()
    return len(targets)
