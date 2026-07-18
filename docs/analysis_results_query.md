# 분석 결과(AnalysisResult) 조회

`POST /api/third-filter`(3차 필터)가 산출한 공고별 분석 결과는 `analysis_results` 테이블에
저장된다. 프론트는 3차 필터가 완료된(`search_sets.status = completed`) 뒤, 아래 엔드포인트로
검색세트 단위의 분석 결과 목록을 조회한다.

## 엔드포인트

`GET /bid-notices/search-sets/{search_set_id}/analysis-results`

- **인증**: JWT 필수. 토큰의 계정(=회사)이 소유한 검색세트만 조회 가능.
- **정렬/개수**: `final_score`(= `analysis_results.soft_score`) 내림차순 **상위 5건**. 점수가 없는(NULL) 공고는 마지막.

### 응답 필드 (`AnalysisResultRead`)

| API 필드 | 출처 컬럼 |
|---|---|
| `final_score` | `analysis_results.soft_score` |
| `recommend_reason` | `analysis_results.recommend_reason` |
| `weaknesses` | `analysis_results.weaknesses` |
| `summary` | `analysis_results.summary` |
| `title` | `bid_notices.title` (조인) |
| `demand_org` | `bid_notices.demand_org` (조인) |

`recommend_reason` / `weaknesses` 는 3차 필터의 `FitReason` 리스트와 동일한 형태다
(`chunk_id`, `reason`, `cited_source`, `cited_id`, `cited_field`).

### 상태 코드

| 코드 | 상황 |
|---|---|
| 200 | 정상. 결과가 없으면 `results: []` |
| 401 | 토큰 없음/무효 |
| 403 | 남의 회사 검색세트 |
| 404 | 존재하지 않는 검색세트 |

## 응답 예시

```json
{
  "success": true,
  "message": "요청이 성공적으로 처리되었습니다.",
  "data": {
    "search_set_id": 1,
    "results": [
      {
        "bid_notice_id": 10,
        "final_score": 88,
        "recommend_reason": [
          {
            "chunk_id": 5,
            "reason": "클라우드 구축 경험 일치",
            "cited_source": "project",
            "cited_id": 3,
            "cited_field": "performance"
          }
        ],
        "weaknesses": [],
        "summary": "공공 클라우드 전환 사업",
        "title": "클라우드 전환",
        "demand_org": "행정안전부"
      }
    ]
  }
}
```
