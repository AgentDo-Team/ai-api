"""회사 입력폼 검색 준비 검증 단위 테스트."""

import pytest

from app.common.exceptions import AppException
from app.db.models.company import CompanyProfile, CompanyProject
from app.services.embedding_service import (
    _validate_company_inputs,
    _validate_embedding_vectors,
)


def test_validate_company_inputs_requires_profile():
    with pytest.raises(AppException, match="회사 프로필"):
        _validate_company_inputs(None, [CompanyProject(id=1, company_id=1, title="P")])


def test_validate_company_inputs_requires_project():
    profile = CompanyProfile(id=1, company_id=1, target_techs="AI")

    with pytest.raises(AppException, match="성공 프로젝트"):
        _validate_company_inputs(profile, [])


def test_validate_company_inputs_requires_profile_text():
    profile = CompanyProfile(
        id=1,
        company_id=1,
        company_scale=None,
        credit_rating=None,
        sp_grade=None,
    )
    projects = [CompanyProject(id=1, company_id=1, title="P")]

    with pytest.raises(AppException, match="임베딩할 수 있는 내용"):
        _validate_company_inputs(profile, projects)


def test_validate_company_inputs_accepts_ready_company():
    profile = CompanyProfile(id=1, company_id=1, target_techs="AI, RAG")
    projects = [CompanyProject(id=1, company_id=1, title="공공 RAG 구축")]

    _validate_company_inputs(profile, projects)


def test_validate_embedding_vectors_rejects_missing_result():
    with pytest.raises(AppException, match="결과 수"):
        _validate_embedding_vectors([{"dense": [1.0]}], expected_count=2)


def test_validate_embedding_vectors_rejects_empty_vector():
    with pytest.raises(AppException, match="비어 있는"):
        _validate_embedding_vectors([{"dense": []}], expected_count=1)
