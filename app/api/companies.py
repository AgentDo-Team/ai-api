"""회사(companies) CRUD 엔드포인트."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status

from app.api.deps import get_company_service
from app.schemas.company import CompanyCreate, CompanyRead, CompanyUpdate
from app.schemas.response import ApiResponse
from app.services.company_service import CompanyService

router = APIRouter(prefix="/api/companies", tags=["companies"])

ServiceDep = Annotated[CompanyService, Depends(get_company_service)]
CompanyIdPath = Annotated[int, Path(description="회사 ID", ge=1)]

NOT_FOUND = {404: {"description": "회사를 찾을 수 없음"}}
CONFLICT = {409: {"description": "이메일이 이미 등록됨"}}


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="회사 생성",
    description="회사를 등록한다. `email`은 전체 회사 중 유일해야 하며, 중복이면 409를 반환한다.",
    response_description="생성된 회사",
    responses=CONFLICT,
)
async def create_company(
    body: CompanyCreate, service: ServiceDep
) -> ApiResponse[CompanyRead]:
    company = await service.create_company(body)
    return ApiResponse.ok(data=CompanyRead.of(company), message="회사가 등록되었습니다.")


@router.get(
    "",
    summary="회사 목록 조회",
    description="등록된 회사를 ID 오름차순으로 페이징 조회한다.",
    response_description="회사 목록",
)
async def list_companies(
    service: ServiceDep,
    limit: Annotated[int, Query(description="한 번에 가져올 개수", ge=1, le=100)] = 20,
    offset: Annotated[int, Query(description="건너뛸 개수", ge=0)] = 0,
) -> ApiResponse[list[CompanyRead]]:
    companies = await service.list_companies(limit=limit, offset=offset)
    return ApiResponse.ok(data=[CompanyRead.of(c) for c in companies])


@router.get(
    "/{company_id}",
    summary="회사 단건 조회",
    description="회사 ID로 회사 한 건을 조회한다.",
    response_description="회사",
    responses=NOT_FOUND,
)
async def get_company(
    company_id: CompanyIdPath, service: ServiceDep
) -> ApiResponse[CompanyRead]:
    company = await service.get_company(company_id)
    return ApiResponse.ok(data=CompanyRead.of(company))


@router.patch(
    "/{company_id}",
    summary="회사 부분 수정",
    description="요청 본문에 담아 보낸 필드만 수정한다.",
    response_description="수정된 회사",
    responses={**NOT_FOUND, **CONFLICT},
)
async def update_company(
    company_id: CompanyIdPath, body: CompanyUpdate, service: ServiceDep
) -> ApiResponse[CompanyRead]:
    company = await service.update_company(company_id, body)
    return ApiResponse.ok(data=CompanyRead.of(company), message="회사 정보가 수정되었습니다.")


@router.delete(
    "/{company_id}",
    summary="회사 삭제",
    description="회사를 삭제한다. 해당 회사의 프로필과 프로젝트도 함께 삭제된다(ON DELETE CASCADE).",
    response_description="삭제 결과",
    responses=NOT_FOUND,
)
async def delete_company(
    company_id: CompanyIdPath, service: ServiceDep
) -> ApiResponse[None]:
    await service.delete_company(company_id)
    return ApiResponse.ok(message="회사가 삭제되었습니다.")
