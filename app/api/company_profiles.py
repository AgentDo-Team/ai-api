"""회사 프로필(company_profiles) CRUD 엔드포인트. 회사당 1건(1:1)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.api.deps import get_company_service, verify_company_access
from app.schemas.company import (
    CompanyProfileCreate,
    CompanyProfileRead,
    CompanyProfileUpdate,
)
from app.schemas.response import ApiResponse
from app.services.company_service import CompanyService

# JWT 인증 필수. 경로의 company_id가 토큰의 계정(=회사) id와 다르면 403.
router = APIRouter(
    prefix="/api/companies/{company_id}/profile",
    tags=["company-profiles"],
    dependencies=[Depends(verify_company_access)],
)

ServiceDep = Annotated[CompanyService, Depends(get_company_service)]
CompanyIdPath = Annotated[int, Path(description="회사 ID", ge=1)]

AUTH_ERRORS = {
    401: {"description": "인증 정보가 없거나 유효하지 않음"},
    403: {"description": "본인 회사의 리소스가 아님"},
}
NOT_FOUND = {404: {"description": "회사 또는 프로필을 찾을 수 없음"}, **AUTH_ERRORS}


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="회사 프로필 생성",
    description="회사당 프로필은 1건만 존재할 수 있다. 이미 있으면 409.",
    response_description="생성된 프로필",
    responses={
        404: {"description": "회사를 찾을 수 없음"},
        409: {"description": "이미 프로필이 존재함"},
        **AUTH_ERRORS,
    },
)
async def create_profile(
    company_id: CompanyIdPath, body: CompanyProfileCreate, service: ServiceDep
) -> ApiResponse[CompanyProfileRead]:
    profile = await service.create_profile(company_id, body)
    return ApiResponse.ok(
        data=CompanyProfileRead.of(profile), message="회사 프로필이 등록되었습니다."
    )


@router.get(
    "",
    summary="회사 프로필 조회",
    description="회사의 프로필을 조회한다.",
    response_description="프로필",
    responses=NOT_FOUND,
)
async def get_profile(
    company_id: CompanyIdPath, service: ServiceDep
) -> ApiResponse[CompanyProfileRead]:
    profile = await service.get_profile(company_id)
    return ApiResponse.ok(data=CompanyProfileRead.of(profile))


@router.patch(
    "",
    summary="회사 프로필 부분 수정",
    description="보낸 필드만 수정한다.",
    response_description="수정된 프로필",
    responses=NOT_FOUND,
)
async def update_profile(
    company_id: CompanyIdPath, body: CompanyProfileUpdate, service: ServiceDep
) -> ApiResponse[CompanyProfileRead]:
    profile = await service.update_profile(company_id, body)
    return ApiResponse.ok(
        data=CompanyProfileRead.of(profile), message="회사 프로필이 수정되었습니다."
    )


@router.delete(
    "",
    summary="회사 프로필 삭제",
    description="회사의 프로필을 삭제한다. 회사 자체는 삭제되지 않는다.",
    response_description="삭제 결과",
    responses=NOT_FOUND,
)
async def delete_profile(
    company_id: CompanyIdPath, service: ServiceDep
) -> ApiResponse[None]:
    await service.delete_profile(company_id)
    return ApiResponse.ok(message="회사 프로필이 삭제되었습니다.")
