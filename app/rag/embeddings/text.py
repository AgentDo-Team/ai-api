"""DB 레코드 → 임베딩용 텍스트 조립.

임베딩 대상 필드만 라벨을 붙여 이어붙인다. 라벨을 붙이는 이유는 나중에 공고 텍스트와
유사도를 비교할 때 "무엇에 대한 값인지"까지 벡터에 담기게 하기 위함이다.
"""

from app.db.models.company import CompanyProfile, CompanyProject

# 값이 바뀌면 재임베딩이 필요한 필드들 (서비스의 재임베딩 판단에도 사용된다)
PROFILE_EMBEDDING_FIELDS = (
    ("company_scale", "기업규모"),
    ("target_techs", "주력기술"),
    ("offered_solutions", "보유솔루션"),
    ("strengths_diff", "강점및차별점"),
)

PROJECT_EMBEDDING_FIELDS = (
    ("title", "프로젝트명"),
    ("client", "고객사"),
    ("domain", "도메인"),
    ("tech_stack", "기술스택"),
    ("develop_features", "주요기능"),
    ("content", "내용"),
    ("performance", "실적"),
)


def _build(source: object, fields: tuple[tuple[str, str], ...]) -> str | None:
    lines = []
    for attr, label in fields:
        value = getattr(source, attr, None)
        if value is None:
            continue
        value = str(value).strip()
        if value:
            lines.append(f"{label}: {value}")
    return "\n".join(lines) if lines else None


def build_profile_embedding_text(profile: CompanyProfile) -> str | None:
    """임베딩할 내용이 하나도 없으면 None (→ 호출자가 임베딩을 건너뛴다)."""
    return _build(profile, PROFILE_EMBEDDING_FIELDS)


def build_project_embedding_text(project: CompanyProject) -> str | None:
    return _build(project, PROJECT_EMBEDDING_FIELDS)
