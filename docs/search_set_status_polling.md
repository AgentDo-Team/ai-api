# 검색세트(SearchSet) 상태 폴링

`POST /bid-notices/search`(1차 하드필터 + 2차 소프트필터)와 `POST /api/third-filter`(3차 필터)는
모두 동기 API라 응답을 받을 때까지 기다려야 한다. 특히 3차 필터는 공고 수에 따라 수십 초~수 분이
걸릴 수 있어, 프론트가 별도로 진행 상태를 확인할 수 있도록 `search_sets.status` 를 단계별로
갱신하고 이를 폴링하는 엔드포인트를 제공한다.

## 상태 값 (`SearchSetStatus`, `app/core/enums.py`)

| 값 | 의미 | 갱신 시점 |
|---|---|---|
| `null` | 아직 2차 필터가 시작되지 않음 | 검색세트 생성 직후(기본값) |
| `ongoing_second_filter` | 2차 소프트필터(청크 유사도 랭킹) 진행 중 | `search_service.search_bid_notices` 가 하드필터 이후, 2차 필터 시작 직전에 설정 |
| `ongoing_third_filter` | 3차 필터(배점표 채점 + 상위 5건 검증/요약) 진행 중 | `ThirdFilterService.run` 시작 시 설정 |
| `completed` | 3차 필터까지 완료 | `ThirdFilterService.run` 정상 종료 시 설정 |

`POST /bid-notices/search` 는 동기 응답이라 호출이 끝나는 시점엔 이미 2차 필터가 끝나 있다.
따라서 `ongoing_second_filter` 상태는 그 요청이 서버에서 처리되는 짧은 구간에만 관측될 수 있다.
반면 3차 필터는 별도 API 호출이라, 그 호출이 진행되는 동안 폴링으로 `ongoing_third_filter` →
`completed` 전이를 볼 수 있다.

실패(예외) 시에는 상태를 별도로 갱신하지 않는다 — `ongoing_third_filter` 에 머문 채 API 호출이
에러 응답으로 끝난다.

## 폴링 API

```
GET /bid-notices/search-sets/{search_set_id}/status
Authorization: Bearer <JWT>
```

- JWT 필수. 토큰의 회사(계정) id와 `search_sets.company_id` 가 다르면 403.
- 존재하지 않는 `search_set_id` 는 404.

응답:

```json
{
  "success": true,
  "message": "요청이 성공적으로 처리되었습니다.",
  "data": {
    "search_set_id": 1,
    "status": "ongoing_third_filter"
  }
}
```

## 관련 파일

| 파일 | 역할 |
|---|---|
| `app/core/enums.py` | `SearchSetStatus` enum |
| `app/db/repositories/search_set_repository.py` | `set_status()` — 상태 갱신 + 커밋 |
| `app/services/search_service.py` | 2차 필터 시작 시 `ongoing_second_filter` 설정 |
| `app/services/third_filter_service.py` | 3차 필터 시작/완료 시 `ongoing_third_filter`/`completed` 설정 |
| `app/api/search.py` | `GET /bid-notices/search-sets/{id}/status` 라우터 |
| `app/schemas/search.py` | `SearchSetStatusResponse` |
