# 3차 필터 API 동작 흐름

## 개요

`POST /api/third-filter` 는 2차 필터(하이브리드 검색)를 통과한 공고 목록을 받아,

1. **모든 공고**를 평가기준표(배점표) 기반으로 채점하고 (`EvaluationService`)
2. 최종점수(`final_score`, 배점표 채점 점수) 기준 **상위 5개 공고에만** 적합/부적합 LLM 검증과 100자 요약을 수행한 뒤
3. 그 결과를 응답으로 반환하면서 `analysis_results` 테이블에도 저장한다.

`aggregate_score`(2차 필터가 산출한 매칭도)는 이미 2차 필터 단계의 하드필터 통과 여부에 반영된 값이라, 3차 필터의 최종점수 산정에는 **쓰지 않는다**. 응답에는 참고용으로만 그대로 노출된다. `final_score` 는 DB 상으로는 `analysis_results.soft_score` 컬럼에 저장되지만, 응답 DTO 에는 `soft_score` 라는 별도 필드로 중복 노출하지 않고 `final_score` 하나로만 내려준다.

**동기 API**다. 공고 간 병렬(동시 3건) + 공고 내 세부항목 병렬(동시 5개) 채점으로, 공고 1건당 약 10초 안팎 — 공고 10건 기준 대략 **40~60초**가 걸린다. 프론트/프록시의 HTTP 타임아웃은 여유 있게 **2~3분**으로 잡는 것을 권장한다(세부항목이 많은 RFP, LLM rate limit 등 변수가 있다).

## 요청 예시

```json
{
  "search_set_id": 1,
  "company_id": 1,
  "results": [
    {
      "bid_notice_id": 12,
      "aggregate_score": 0.65,
      "ranked_chunks": [
        {
          "chunk_id": 4821,
          "rank": 1,
          "score": 0.91,
          "matched_source": "project",
          "matched_id": 5
        }
      ]
    }
  ]
}
```

| 필드 | 의미 |
|---|---|
| `search_set_id` | 검색세트 ID (분석 결과 저장 키) |
| `company_id` | 회사 ID (프로필/프로젝트 조회에 사용) |
| `results[].bid_notice_id` | 하드필터 통과 공고 ID |
| `results[].aggregate_score` | 공고 전체 매칭도 (2차 필터의 청크 점수 집계). 응답에 참고용으로 그대로 노출되며 최종점수 산정에는 쓰이지 않는다 |
| `ranked_chunks[].chunk_id` | 매칭된 공고 청크 ID (원문 조회에 사용) |
| `ranked_chunks[].matched_source` | 매칭 근거가 `profile`(회사 프로필)인지 `project`(과거 프로젝트)인지 |
| `ranked_chunks[].matched_id` | 매칭된 프로필/프로젝트 ID (추천이유 근거) |

## 응답 예시

```json
{
  "success": true,
  "message": "3차 필터 분석이 완료되었습니다.",
  "data": {
    "results": [
      {
        "bid_notice_id": 12,
        "final_score": 90,
        "aggregate_score": 0.65,
        "recommend_reason": [
          {
            "chunk_id": 4821,
            "reason": "요구 기술과 동일 도메인 수행 실적이 확인됨.",
            "cited_source": "project",
            "cited_id": 5,
            "cited_field": "performance"
          }
        ],
        "weaknesses": [
          {
            "chunk_id": 4830,
            "reason": "보안관제 자격요건을 뒷받침하는 항목이 없음.",
            "cited_source": "none",
            "cited_id": null,
            "cited_field": null
          }
        ],
        "summary": "○○공단 노후 전산시스템의 클라우드 전환 사업. 예산 15억, 8개월.",
        "title": "○○공단 클라우드 전환 사업 제안요청",
        "demand_org": "○○공단"
      }
    ],
    "skipped": []
  }
}
```

`results` 는 최종점수 내림차순 **최대 5건**. `skipped` 는 처리 중 예상 못한 오류로 제외된 공고 목록이다.

`final_score` 는 배점표 채점 점수 그 자체다. `aggregate_score` 는 응답에 참고 정보로만 포함되며 최종점수/정렬에는 반영되지 않는다.

`recommend_reason`/`weaknesses` 는 판정 이유를 하나의 문자열로 이어붙이지 않고, **판정 1건당 1개 객체**로 구성된 리스트다. `ranked_chunks` 가 여러 개면 청크마다 적합/부적합 판정이 나오므로 리스트 길이도 그만큼 늘어난다(둘 다 없으면 빈 배열 `[]`). 각 객체의 `cited_source`/`cited_id`/`cited_field` 는 어떤 프로필/프로젝트의 어떤 필드가 근거였는지를 가리킨다(근거 없음이면 `cited_source: "none"`). 배점표 채점 자체가 실패한 경우에는 `chunk_id: null` 인 사유 1건이 `weaknesses` 에 들어간다.

## 처리 흐름

```
POST /api/third-filter
        │
        ▼
[1단계] 모든 공고 배점표 채점 ── 공고 간 병렬 (Semaphore=3, 공고별 독립 DB 세션)
        │   EvaluationService.evaluate() — 공고 1건당:
        │     ① 청크에서 평가기준표 탐지 (정규식 하드필터 → 실패 시 참조코퍼스 유사도 소프트필터)
        │     ② LLM 으로 세부평가 항목 분리 (항목명/설명/배점)
        │     ③~⑤ 세부항목 채점 — 항목 간 병렬 (동시 5개, 항목별 독립 DB 세션):
        │         하이브리드(dense+BM25) 검색으로 관련 청크 수집
        │         → 청크 + 회사 프로필/프로젝트를 LLM 에 주고 채점 (출처 인용 강제)
        │         → 근거 없으면 0점 (없는 근거로 점수 생성 방지)
        │     ⑥ 항목당 채점 1회 (EVAL_K=1. 2 이상으로 올리면 반복 후 평균/다수결 집계)
        │        → 항목 점수 합산 = soft_score
        │   실패 정책:
        │     · 평가기준표 없음 등(AppException) → soft_score=0 으로 랭킹 유지
        │     · 그 외 예외 → skipped 로 제외 (요청 전체는 계속 진행)
        ▼
[2단계] final_score(= soft_score) 내림차순 정렬 → 상위 5개 선별
        │   (aggregate_score 는 최종점수 산정에 쓰지 않는다. 2차 필터가 이미
        │    반영한 값이므로 3차 필터는 배점표 채점 결과만으로 순위를 매긴다)
        ▼
[3단계] 상위 5개만 검증 + 요약 ── 공고 간 병렬 (공고별 독립 DB 세션)
        │   (a) 적합/부적합 검증: ranked_chunks 의 청크 원문 ↔ 매칭된 프로필/프로젝트를
        │       few-shot 프롬프트로 LLM 일괄 판정. fit 판정에는 출처 인용
        │       (cited_source/cited_id/cited_field) 을 강제하고, 인용 없는 fit 은
        │       코드에서 unfit 으로 보정.
        │       → fit 판정들 = recommend_reason 리스트, unfit 판정들 = weaknesses 리스트
        │       (청크별 판정 1건 = FitReason 객체 1개, 문자열로 합치지 않음)
        │   (b) 요약: 공고 청크 본문 앞부분(~6,000자)을 LLM 으로 100자 이내 요약 → summary
        │   (c) analysis_results 에 upsert:
        │       recommend_reason / weaknesses / summary 갱신
        │       (같은 search_set_id + bid_notice_id 재실행 시에도 중복 오류 없음)
        ▼
[4단계] ThirdFilterResponse 조립 → ApiResponse 로 감싸 반환
```

## 실패 처리 정책

| 상황 | 처리 |
|---|---|
| 평가기준표를 찾을 수 없음 (404) | 부적격이 아니라 "배점표 가점 없음"으로 간주. `final_score=0` 으로 랭킹에는 남고, 상위 5에 들면 `weaknesses` 에 사유 표기 |
| 공고/검색세트 없음 등 `AppException` | 위와 동일 (`final_score=0`) |
| 채점/검증 중 예상 못한 예외 | 해당 공고만 `skipped` 로 제외, 나머지는 정상 반환 |
| LLM 이 근거 없이 fit 판정 | 코드에서 unfit 으로 강제 보정 |
| 요약이 100자 초과 | 코드에서 100자로 절단 |

## 동시성 노트

- SQLAlchemy `AsyncSession` 은 **동시 쿼리를 허용하지 않는다**. 그래서 병렬 구간은 전부 `async_session_factory()` 로 독립 세션을 열어 수행한다:
  - **공고 간 병렬**: `ThirdFilterService.MAX_CONCURRENT_NOTICES = 3` — 공고마다 새 세션.
  - **공고 내 세부항목 병렬**: `EvaluationService.MAX_CONCURRENT_CRITERIA = 5` — 항목마다 새 세션에서 DB 를 읽고, 느린 LLM 호출 **전에** 세션을 닫아 커넥션을 풀에 반납한다.
- 최악의 경우 동시 세션 수는 공고 3 × 항목 5 = **15개**까지 열리지만, 각 세션이 커넥션을 잡는 시간은 짧다(검색 쿼리 몇 개). 커넥션 풀 고갈이 보이면 `MAX_CONCURRENT_CRITERIA` 를 먼저 낮춘다.
- 항목당 반복 채점 횟수는 `EvaluationService.EVAL_K = 1`. 채점 편차가 문제가 되면 2 이상으로 올려 평균/다수결 집계를 되살릴 수 있다 (LLM 호출량이 K배가 된다).

## 예상 소요 시간

LLM 1회 호출 ≈ 2~5초(gpt-4o-mini 구조화 출력), 공고당 호출 수 = 항목 추출 1회 + 세부항목 수 × EVAL_K(=1)회.

| 입력 공고 수 | 총 LLM 호출(항목 5개 가정) | 예상 응답 시간 |
|---|---|---|
| 5건 | ~40회 | ~25초 |
| 10건 | ~70회 | ~45–60초 |
| 20건 | ~130회 | ~1.5–2분 |

공고 1건 ≈ 항목 추출(3–5초) + 병렬 항목 채점 1배치(3–5초, 항목 5개 초과 시 배치 추가). 상위 5건 검증+요약(공고당 LLM 2회)이 마지막에 ~15초 붙는다.

## 관련 파일

| 파일 | 역할 |
|---|---|
| `app/api/third_filter.py` | 라우터 (`POST /api/third-filter`) |
| `app/schemas/third_filter.py` | 요청/응답 DTO + LLM structured output DTO |
| `app/services/third_filter_service.py` | 오케스트레이션 (채점 병렬화, 검증/요약, 저장) |
| `app/services/evaluation_service.py` | 배점표 기반 채점 파이프라인 (soft_score 산출, upsert 저장) |
| `app/rag/retrievers/hybrid_search.py` | dense+BM25 하이브리드 검색, 참조코퍼스 소프트 필터 |
| `app/rag/chunking/table_filter.py` | 평가기준표 청크 정규식 하드 필터 |
| `app/db/models/analysis.py` | `analysis_results` 모델 (soft_score, recommend_reason/weaknesses: JSONB 리스트, summary) |
| `app/api/deps.py` | `get_third_filter_service` 의존성 조립 |