"""3차 필터 엔드포인트.

2차 필터 결과(하드필터 통과 공고 + 공고별 매칭 청크)를 받아 배점표 채점과
적합/부적합 검증을 수행하고, 최종점수 상위 5개 공고를 반환한다.

동기 API: 공고 수 × LLM 호출량에 따라 수십 초 이상 걸릴 수 있으므로
클라이언트 타임아웃을 2~3분으로 넉넉히 잡아야 한다.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_third_filter_service
from app.schemas.response import ApiResponse
from app.schemas.third_filter import ThirdFilterRequest, ThirdFilterResponse
from app.services.third_filter_service import ThirdFilterService

router = APIRouter(prefix="/api/third-filter", tags=["third-filter"])

ServiceDep = Annotated[ThirdFilterService, Depends(get_third_filter_service)]


@router.post(
    "",
    summary="3차 필터: 배점표 채점 + 상위 5건 적합성 검증/요약",
    description=(
        "입력된 모든 공고를 평가기준표 기반으로 채점한 뒤, "
        "최종점수(aggregate_score + soft_score) 상위 5개 공고에 대해 "
        "적합/부적합 LLM 검증과 100자 요약을 수행해 반환한다. "
        "판정/요약 결과는 analysis_results 에도 저장된다."
    ),
    response_description="최종점수 상위 5개 공고의 분석 결과",
)
async def run_third_filter(
    body: ThirdFilterRequest, service: ServiceDep
) -> ApiResponse[ThirdFilterResponse]:
    result = await service.run(body)
    return ApiResponse.ok(data=result, message="3차 필터 분석이 완료되었습니다.")
