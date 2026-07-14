"""임베딩용 텍스트 조립 순수 함수 테스트."""

from app.db.models.company import CompanyProfile, CompanyProject
from app.rag.embeddings.text import (
    build_profile_embedding_text,
    build_project_embedding_text,
)


def test_profile_text_labels_and_orders_fields():
    profile = CompanyProfile(
        company_id=1,
        company_scale="중소기업",
        target_techs="AI, RAG",
        offered_solutions="분석 SaaS",
        strengths_diff="국방 경험",
        credit_rating="A+",
    )

    text = build_profile_embedding_text(profile)

    assert text == (
        "기업규모: 중소기업\n"
        "주력기술: AI, RAG\n"
        "보유솔루션: 분석 SaaS\n"
        "강점및차별점: 국방 경험"
    )
    assert "A+" not in text  # 신용평가등급은 임베딩 대상이 아니다


def test_profile_text_skips_none_and_blank_fields():
    profile = CompanyProfile(
        company_id=1, target_techs="AI", offered_solutions="   ", strengths_diff=None
    )

    assert build_profile_embedding_text(profile) == "주력기술: AI"


def test_profile_text_is_none_when_nothing_embeddable():
    profile = CompanyProfile(company_id=1, credit_rating="A+", sp_grade="1등급")

    assert build_profile_embedding_text(profile) is None


def test_project_text_includes_all_embeddable_fields():
    project = CompanyProject(
        company_id=1,
        title="물자관리 고도화",
        client="국방부",
        domain="국방",
        tech_stack="FastAPI",
        develop_features="재고 예측",
        content="상세 내용",
        performance="40% 개선",
    )

    text = build_project_embedding_text(project)

    assert text == (
        "프로젝트명: 물자관리 고도화\n"
        "고객사: 국방부\n"
        "도메인: 국방\n"
        "기술스택: FastAPI\n"
        "주요기능: 재고 예측\n"
        "내용: 상세 내용\n"
        "실적: 40% 개선"
    )


def test_project_text_with_only_title():
    project = CompanyProject(company_id=1, title="제목만")

    assert build_project_embedding_text(project) == "프로젝트명: 제목만"
