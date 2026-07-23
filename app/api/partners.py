from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status

from app.api.deps import get_company_service, verify_company_access
from app.schemas.partner import PartnerCreate, PartnerRead, PartnerUpdate
from app.schemas.response import ApiResponse
from app.services.company_service import CompanyService

router = APIRouter(
    prefix="/api/companies/{company_id}/partners",
    tags=["partners"],
    dependencies=[Depends(verify_company_access)],
)

ServiceDep = Annotated[CompanyService, Depends(get_company_service)]
CompanyIdPath = Annotated[int, Path(description="회사 ID", ge=1)]
PartnerIdPath = Annotated[int, Path(description="협력사 ID", ge=1)]

AUTH_ERRORS = {
    401: {"description": "인증 정보가 없거나 유효하지 않음"},
    403: {"description": "본인 회사의 리소스가 아님"},
}
NOT_FOUND = {404: {"description": "회사 또는 협력사를 찾을 수 없음"}, **AUTH_ERRORS}


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="협력사 생성",
    description="회사가 보유한 협력사를 등록한다.",
    response_description="생성된 협력사",
    responses={404: {"description": "회사를 찾을 수 없음"}, **AUTH_ERRORS},
)
async def create_partner(
    company_id: CompanyIdPath, body: PartnerCreate, service: ServiceDep
) -> ApiResponse[PartnerRead]:
    partner = await service.create_partner(company_id, body)
    return ApiResponse.ok(
        data=PartnerRead.of(partner), message="협력사가 등록되었습니다."
    )


@router.get(
    "",
    summary="협력사 목록 조회",
    description="해당 회사의 협력사를 ID 오름차순으로 페이징 조회한다.",
    response_description="협력사 목록",
    responses={404: {"description": "회사를 찾을 수 없음"}, **AUTH_ERRORS},
)
async def list_partners(
    company_id: CompanyIdPath,
    service: ServiceDep,
    limit: Annotated[int, Query(description="한 번에 가져올 개수", ge=1, le=100)] = 20,
    offset: Annotated[int, Query(description="건너뛸 개수", ge=0)] = 0,
) -> ApiResponse[list[PartnerRead]]:
    partners = await service.list_partners(company_id, limit=limit, offset=offset)
    return ApiResponse.ok(data=[PartnerRead.of(p) for p in partners])


@router.get(
    "/{partner_id}",
    summary="협력사 단건 조회",
    description="다른 회사에 속한 협력사 ID를 요청하면 404를 반환한다.",
    response_description="협력사",
    responses=NOT_FOUND,
)
async def get_partner(
    company_id: CompanyIdPath, partner_id: PartnerIdPath, service: ServiceDep
) -> ApiResponse[PartnerRead]:
    partner = await service.get_partner(company_id, partner_id)
    return ApiResponse.ok(data=PartnerRead.of(partner))


@router.patch(
    "/{partner_id}",
    summary="협력사 부분 수정",
    description="보낸 필드만 수정한다.",
    response_description="수정된 협력사",
    responses=NOT_FOUND,
)
async def update_partner(
    company_id: CompanyIdPath,
    partner_id: PartnerIdPath,
    body: PartnerUpdate,
    service: ServiceDep,
) -> ApiResponse[PartnerRead]:
    partner = await service.update_partner(company_id, partner_id, body)
    return ApiResponse.ok(
        data=PartnerRead.of(partner), message="협력사가 수정되었습니다."
    )


@router.delete(
    "/{partner_id}",
    summary="협력사 삭제",
    description="협력사를 삭제한다.",
    response_description="삭제 결과",
    responses=NOT_FOUND,
)
async def delete_partner(
    company_id: CompanyIdPath, partner_id: PartnerIdPath, service: ServiceDep
) -> ApiResponse[None]:
    await service.delete_partner(company_id, partner_id)
    return ApiResponse.ok(message="협력사가 삭제되었습니다.")
