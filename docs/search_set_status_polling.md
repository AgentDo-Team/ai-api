# 검색세트(SearchSet) 상태 스트리밍(SSE)

`POST /bid-notices/search`(1차 하드필터 + 2차 소프트필터)와 `POST /api/third-filter`(3차 필터)는
모두 동기 API라 응답을 받을 때까지 기다려야 한다. 특히 3차 필터는 공고 수에 따라 수십 초~수 분이
걸릴 수 있어, 프론트가 별도로 진행 상태를 확인할 수 있도록 `search_sets.status` 를 단계별로
갱신하고 이를 **SSE(Server-Sent Events)로 스트리밍하는** 엔드포인트를 제공한다.
(이전에는 프론트가 3초 간격으로 폴링했으나, 상태 변경을 서버가 push 하는 SSE 로 전환했다.)

## 상태 값 (`SearchSetStatus`, `app/core/enums.py`)

| 값 | 의미 | 갱신 시점 |
|---|---|---|
| `null` | 아직 2차 필터가 시작되지 않음 | 검색세트 생성 직후(기본값) |
| `ongoing_second_filter` | 2차 소프트필터(청크 유사도 랭킹) 진행 중 | `search_service.search_bid_notices` 가 2차 필터 시작 직전에 설정 |
| `ongoing_third_filter` | 3차 필터(배점표 채점 + 상위 5건 검증/요약) 진행 중 | `ThirdFilterService.run` 시작 시 설정 |
| `completed` | 3차 필터까지 완료 | `ThirdFilterService.run` 정상 종료 시 설정 |
| `failed` | 2차 소프트필터 처리 실패 | 2차 필터 예외 처리 시 설정하고 `failure_reason` 저장 |

`POST /bid-notices/search` 는 동기 응답이라 호출이 끝나는 시점엔 이미 2차 필터가 끝나 있다.
따라서 `ongoing_second_filter` 상태는 그 요청이 서버에서 처리되는 짧은 구간에만 관측될 수 있다.
반면 3차 필터는 별도 API 호출이라, 그 호출이 진행되는 동안 폴링으로 `ongoing_third_filter` →
`completed` 전이를 볼 수 있다.

2차 필터 실패 시에는 `failed` 와 안전한 `failure_reason` 을 저장한다. 3차 필터의 실패 상태 처리는
팀원 2의 로직 범위이므로 이번 변경에 포함하지 않았으며, 3차 실패 시에는 기존처럼
`ongoing_third_filter` 에 머물 수 있다.

## 상태 스트림 API (SSE)

```
GET /bid-notices/search-sets/{search_set_id}/status/stream
Authorization: Bearer <JWT>
Accept: text/event-stream
```

- JWT 필수. 토큰의 회사(계정) id와 `search_sets.company_id` 가 다르면 403.
- 존재하지 않는 `search_set_id` 는 404.
- 소유권 검증은 스트림이 열리기 **전**에 수행되므로, 실패 시 SSE 가 아니라 일반 JSON 오류로 끝난다.

서버는 `STATUS_POLL_INTERVAL_SECONDS`(기본 2초)마다 DB 상태를 다시 읽어 **바뀐 경우에만**
이벤트를 push 한다. status 가 `completed` 가 되면 이벤트를 한 번 더 보내고 스트림을 닫는다.
3차 필터가 멈춰 응답이 없으면 `STATUS_STREAM_MAX_SECONDS`(기본 600초) 후 error 이벤트로 종료한다.

이벤트(각 이벤트는 `data: {json}\n\n` 한 블록):

응답:

```json
{
  "success": true,
  "message": "요청이 성공적으로 처리되었습니다.",
  "data": {
    "search_set_id": 1,
    "status": "ongoing_second_filter",
    "failure_reason": null
  }
}
```

2차 실패 예시:

```json
{
  "success": true,
  "message": "요청이 성공적으로 처리되었습니다.",
  "data": {
    "search_set_id": 2,
    "status": "failed",
    "failure_reason": "성공 프로젝트를 하나 이상 작성해 주세요."
  }
}
```
data: {"type": "status", "search_set_id": 1, "status": "ongoing_second_filter", "progress_current": null, "progress_total": null}

data: {"type": "status", "search_set_id": 1, "status": "ongoing_third_filter", "progress_current": 3, "progress_total": 10}

data: {"type": "status", "search_set_id": 1, "status": "completed", "progress_current": 10, "progress_total": 10}
```

- `type: "status"` — 상태/진행률 변경분. 3차 필터 중에는 `progress_current/progress_total` 이 채워진다.
- `type: "error"` — 세트 소멸/시간 초과 등. `{"type": "error", "message": <사유>}`.

프론트는 `EventSource`(헤더 주입 불가) 대신 `fetch` + `ReadableStream` 으로 읽어 Authorization 을 싣는다
(`src/api/search.js` 의 `streamSearchSetStatus`).

## 관련 파일

| 파일 | 역할 |
|---|---|
| `app/core/enums.py` | `SearchSetStatus` enum |
| `app/db/repositories/search_set_repository.py` | `set_status()` — 상태 갱신 + 커밋 |
| `app/db/models/search.py` | 실패 사유를 저장하는 `failure_reason` 컬럼 |
| `app/services/search_service.py` | 2차 필터 시작/완료/실패 상태와 실패 사유 관리 |
| `app/services/third_filter_service.py` | 3차 필터 시작/완료 시 `ongoing_third_filter`/`completed` 설정 |
| `app/api/search.py` | `GET /bid-notices/search-sets/{id}/status/stream` SSE 라우터 (`_status_event_source`) |
| `app/schemas/search.py` | `SearchSetStatusResponse` |
