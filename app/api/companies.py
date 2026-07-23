from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.api.deps import get_company_service, verify_company_access
from app.schemas.company import CompanyRead, CompanyUpdate
from app.schemas.response import ApiResponse
from app.services.company_service import CompanyService

router = APIRouter(prefix="/api/companies", tags=["companies"])

ServiceDep = Annotated[CompanyService, Depends(get_company_service)]
CompanyIdPath = Annotated[int, Path(description="회사 ID", ge=1)]

AUTH_ERRORS = {
    401: {"description": "인증 정보가 없거나 유효하지 않음"},
    403: {"description": "본인 회사의 리소스가 아님"},
}
NOT_FOUND = {404: {"description": "회사를 찾을 수 없음"}, **AUTH_ERRORS}
CONFLICT = {409: {"description": "이메일이 이미 등록됨"}}


@router.get(
    "/{company_id}",
    summary="회사 단건 조회",
    description="본인 회사 정보를 조회한다. 토큰의 회사 id와 경로가 다르면 403.",
    response_description="회사",
    responses=NOT_FOUND,
    dependencies=[Depends(verify_company_access)],
)
async def get_company(
    company_id: CompanyIdPath, service: ServiceDep
) -> ApiResponse[CompanyRead]:
    company = await service.get_company(company_id)
    return ApiResponse.ok(data=CompanyRead.of(company))


@router.patch(
    "/{company_id}",
    summary="회사 부분 수정",
    description="본인 회사 정보를 수정한다. 요청 본문에 담아 보낸 필드만 수정한다.",
    response_description="수정된 회사",
    responses={**NOT_FOUND, **CONFLICT},
    dependencies=[Depends(verify_company_access)],
)
async def update_company(
    company_id: CompanyIdPath, body: CompanyUpdate, service: ServiceDep
) -> ApiResponse[CompanyRead]:
    company = await service.update_company(company_id, body)
    return ApiResponse.ok(data=CompanyRead.of(company), message="회사 정보가 수정되었습니다.")


@router.delete(
    "/{company_id}",
    summary="회사 삭제 (회원 탈퇴)",
    description="본인 회사(계정)를 삭제한다. 프로필과 프로젝트도 함께 삭제된다(ON DELETE CASCADE).",
    response_description="삭제 결과",
    responses=NOT_FOUND,
    dependencies=[Depends(verify_company_access)],
)
async def delete_company(
    company_id: CompanyIdPath, service: ServiceDep
) -> ApiResponse[None]:
    await service.delete_company(company_id)
    return ApiResponse.ok(message="회사가 삭제되었습니다.")
