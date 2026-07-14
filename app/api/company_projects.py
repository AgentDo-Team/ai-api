"""회사 프로젝트(company_projects) CRUD 엔드포인트. 회사당 N건(1:N)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status

from app.api.deps import get_company_service
from app.schemas.company import (
    CompanyProjectCreate,
    CompanyProjectRead,
    CompanyProjectUpdate,
)
from app.schemas.response import ApiResponse
from app.services.company_service import CompanyService

router = APIRouter(prefix="/api/companies/{company_id}/projects", tags=["company-projects"])

ServiceDep = Annotated[CompanyService, Depends(get_company_service)]
CompanyIdPath = Annotated[int, Path(description="회사 ID", ge=1)]
ProjectIdPath = Annotated[int, Path(description="프로젝트 ID", ge=1)]

NOT_FOUND = {404: {"description": "회사 또는 프로젝트를 찾을 수 없음"}}


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="회사 프로젝트 생성",
    description="회사의 수행 프로젝트(실적)를 등록한다.",
    response_description="생성된 프로젝트",
    responses={404: {"description": "회사를 찾을 수 없음"}},
)
async def create_project(
    company_id: CompanyIdPath, body: CompanyProjectCreate, service: ServiceDep
) -> ApiResponse[CompanyProjectRead]:
    project = await service.create_project(company_id, body)
    return ApiResponse.ok(
        data=CompanyProjectRead.of(project), message="프로젝트가 등록되었습니다."
    )


@router.get(
    "",
    summary="회사 프로젝트 목록 조회",
    description="해당 회사의 프로젝트를 ID 오름차순으로 페이징 조회한다.",
    response_description="프로젝트 목록",
    responses={404: {"description": "회사를 찾을 수 없음"}},
)
async def list_projects(
    company_id: CompanyIdPath,
    service: ServiceDep,
    limit: Annotated[int, Query(description="한 번에 가져올 개수", ge=1, le=100)] = 20,
    offset: Annotated[int, Query(description="건너뛸 개수", ge=0)] = 0,
) -> ApiResponse[list[CompanyProjectRead]]:
    projects = await service.list_projects(company_id, limit=limit, offset=offset)
    return ApiResponse.ok(data=[CompanyProjectRead.of(p) for p in projects])


@router.get(
    "/{project_id}",
    summary="회사 프로젝트 단건 조회",
    description="다른 회사에 속한 프로젝트 ID를 요청하면 404를 반환한다.",
    response_description="프로젝트",
    responses=NOT_FOUND,
)
async def get_project(
    company_id: CompanyIdPath, project_id: ProjectIdPath, service: ServiceDep
) -> ApiResponse[CompanyProjectRead]:
    project = await service.get_project(company_id, project_id)
    return ApiResponse.ok(data=CompanyProjectRead.of(project))


@router.patch(
    "/{project_id}",
    summary="회사 프로젝트 부분 수정",
    description="보낸 필드만 수정한다.",
    response_description="수정된 프로젝트",
    responses=NOT_FOUND,
)
async def update_project(
    company_id: CompanyIdPath,
    project_id: ProjectIdPath,
    body: CompanyProjectUpdate,
    service: ServiceDep,
) -> ApiResponse[CompanyProjectRead]:
    project = await service.update_project(company_id, project_id, body)
    return ApiResponse.ok(
        data=CompanyProjectRead.of(project), message="프로젝트가 수정되었습니다."
    )


@router.delete(
    "/{project_id}",
    summary="회사 프로젝트 삭제",
    description="프로젝트를 삭제한다.",
    response_description="삭제 결과",
    responses=NOT_FOUND,
)
async def delete_project(
    company_id: CompanyIdPath, project_id: ProjectIdPath, service: ServiceDep
) -> ApiResponse[None]:
    await service.delete_project(company_id, project_id)
    return ApiResponse.ok(message="프로젝트가 삭제되었습니다.")
