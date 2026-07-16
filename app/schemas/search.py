from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.enums import ProcurementCategory


class HardFilterCondition(BaseModel):
    """채팅창에서 입력한 정형 필터 조건 (하드 필터링용).

    임베딩하지 않고 SQL WHERE 절로만 사용한다. 도메인 분류코드는 프론트에서
    코드값(예: '81111513')으로 입력받아 ProcurementCategory 로 검증한다.
    """

    # 예산은 원(KRW) 단위. 프론트의 '가격(억)' 입력은 프론트에서 원으로 변환해 전달.
    domain_code: str | None = Field(
        default=None,
        description="도메인 분류코드 (예: '81111513'). ProcurementCategory 에 등록된 코드만 허용.",
    )
    joint_venture: bool | None = Field(
        default=None, description="공동수급 여부. None이면 전체(조건 미적용)"
    )
    budget_min_krw: int | None = Field(
        default=None, ge=0, description="최소 예산 금액(원)"
    )
    budget_max_krw: int | None = Field(
        default=None, ge=0, description="최대 예산 금액(원)"
    )
    deadline: datetime | None = Field(
        default=None, description="이 일시 이전에 마감되는 공고만 (마감일 상한)"
    )

    @field_validator("domain_code")
    @classmethod
    def check_domain_code(cls, value: str | None) -> str | None:
        if value is not None and value not in ProcurementCategory.__members__:
            raise ValueError(f"알 수 없는 도메인 분류코드입니다: {value}")
        return value

    @model_validator(mode="after")
    def check_budget_range(self) -> "HardFilterCondition":
        if (
            self.budget_min_krw is not None
            and self.budget_max_krw is not None
            and self.budget_min_krw > self.budget_max_krw
        ):
            raise ValueError("budget_min_krw는 budget_max_krw보다 클 수 없습니다.")
        return self


class BidSearchRequest(BaseModel):
    """채팅창 공고 검색 요청.

    정형 필터 조건 + 자연어 메시지로 구성된다. 검색 주체 회사는 요청 본문이 아니라
    JWT 토큰의 계정(=회사)에서 가져온다 (본인 프로필/프로젝트만 조회 가능하도록).
    - filters: 정형 조건 → 1차 하드 필터링 (SQL WHERE)
    - message: 자연어 강조 메시지 → 자사 프로필/프로젝트와 결합해 즉석 임베딩(쿼리 벡터).
      저장하지 않는 일회성 쿼리로, 2차 소프트 필터링에 사용한다.
    """

    filters: HardFilterCondition = Field(default_factory=HardFilterCondition)
    message: str | None = Field(
        default=None,
        max_length=2000,
        description="추가 강조 자연어 메시지 (없으면 정형 조건만으로 검색)",
    )


class BidSearchResultItem(BaseModel):
    """필터링된 공고 1건."""

    bid_notice_id: int
    notice_no: str
    title: str
    demand_org: str | None = None
    budget_krw: int | None = None
    bid_deadline: datetime | None = None
    domain_name: str | None = Field(
        default=None, description="도메인 분류명 (ProcurementCategory 기준 한글명)"
    )
    soft_score: float | None = Field(
        default=None, description="소프트 필터링(2차) 유사도 점수. 하드 필터만 적용 시 None"
    )

    model_config = {"from_attributes": True}


class BidSearchResponse(BaseModel):
    """공고 검색 결과. ApiResponse.data 에 담아 반환한다."""

    search_set_id: int = Field(description="이번 검색으로 생성된 검색 세트(채팅방) ID")
    hard_filtered_count: int = Field(description="1차 하드 필터링 통과 공고 수")
    items: list[BidSearchResultItem] = Field(
        default_factory=list, description="최종(소프트 필터링까지 반영) 공고 목록"
    )
