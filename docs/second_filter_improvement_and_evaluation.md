# 2차 소프트필터 안정화 변경 및 검색 품질 평가 계획

> Notion 정리용 문서  
> 범위: 회사 입력폼 저장·지연 임베딩·하드필터·2차 하이브리드 검색  
> 제외: 팀원 1의 공고 파싱/청킹/임베딩 로직, 팀원 2의 평가표/LLM 분석 로직, 리랭커 구현

## 1. 배경과 목표

현재 서비스의 검색 흐름은 다음과 같다.

1. 로그인한 회사가 회사 프로필과 성공 프로젝트를 작성한다.
2. 입력폼은 우선 RDB에만 저장한다.
3. 사용자가 채팅창에서 정형 공고 필터와 자유형식 메시지를 입력하고 전송한다.
4. 전송 시점에 아직 임베딩되지 않은 회사 프로필·프로젝트를 임베딩한다.
5. 정형 조건으로 하드필터를 수행한다.
6. 하드필터 통과 공고의 `개요`, `요구사항` 청크를 Dense와 BM25로 검색한다.
7. 여러 검색 순위를 RRF로 융합하고 공고별 상위 10개 청크를 팀원 2에게 전달한다.

이번 작업의 목표는 기존 검색 응답과 팀 간 DTO를 유지하면서 다음 문제를 해결하는 것이다.

- 회사 입력폼 수정 후 과거 임베딩을 계속 사용하는 문제
- 같은 검색 요청에서 지연 임베딩 준비 로직이 두 번 실행되는 문제
- 검색 실패 후 상태가 계속 진행 중으로 남는 문제
- 프로필이나 성공 프로젝트가 없는데도 검색이 실행되는 문제
- 위 동작을 보장하는 테스트와 운영 문서 부족

## 2. 변경하지 않은 계약

다음 응답 구조와 필드명은 변경하지 않았다.

- `POST /bid-notices/search`의 `search_set_id`
- `hard_filtered_count`
- `items[]`
- `items[].soft_score`
- `second_filter.search_set_id`
- `second_filter.company_id`
- `second_filter.results[]`
- `ranked_chunks[]`

따라서 팀원 1의 적재 로직과 팀원 2의 입력 DTO는 이번 변경 때문에 수정할 필요가 없다.

상태 조회 API에만 `failure_reason`이라는 nullable 필드가 추가됐다.

## 3. 파일별 변경 내역

### 3.1 `app/services/company_service.py`

#### 수정 위치

- `CompanyService.update_profile()`
- `CompanyService.update_project()`

#### 기존 문제

프로필 또는 프로젝트를 한 번 임베딩한 후 내용을 수정해도 `embedding` 값이 그대로 남았다.
`ensure_company_embedded()`는 `embedding IS NULL`인 데이터만 다시 임베딩하므로 수정 전 정보가
검색에 계속 사용될 수 있었다.

예시:

```text
기존 주력기술: Java, Spring
임베딩 생성 완료
주력기술 수정: Python, FastAPI, RAG
기존 임베딩 유지 → 검색은 Java/Spring 기준으로 계속 수행
```

#### 변경 내용

PATCH 요청으로 전달된 필드 중 실제 값이 바뀐 필드가 있는지 확인한다.

```python
embedding_changed = any(
    getattr(profile, key) != value for key, value in changes.items()
)
```

실제 변경이 있을 때만 임베딩을 무효화한다.

```python
if embedding_changed:
    profile.embedding = None
```

프로젝트에도 동일한 방식을 적용했다.

#### 수정 후 변화와 효과

- 입력폼 수정 직후 API 응답의 `embedded`가 `false`가 된다.
- 다음 검색 전송 시 수정된 내용으로 임베딩이 다시 생성된다.
- 같은 값을 다시 전송한 경우에는 불필요하게 임베딩을 무효화하지 않는다.
- 과거 벡터와 최신 RDB 값이 불일치하는 문제를 방지한다.

#### 설계 고민

모든 PATCH 요청에서 무조건 `embedding=None`으로 만들 수도 있었지만, 값이 실제로 바뀌지 않은
요청까지 재임베딩 비용을 발생시킬 수 있다. 따라서 `exclude_unset=True`로 전달된 필드만 확인하고,
기존 값과 달라진 경우에만 무효화했다.

### 3.2 `app/services/embedding_service.py`

#### 수정 위치

- `_validate_company_inputs()` 추가
- `ensure_company_embedded()` 조회 및 대상 선정 방식 변경

#### 기존 문제

- 회사 프로필이 없어도 검색이 시작될 수 있었다.
- 성공 프로젝트가 0개여도 검색이 실행됐다.
- 비교 타깃이 없으면 모든 공고가 `aggregate_score=0`, `ranked_chunks=[]`로 반환될 수 있었다.
- 기존 쿼리는 미임베딩 행만 조회했기 때문에, 준비 상태 검증과 전체 입력폼 확인에 적합하지 않았다.

#### 변경 내용

검색에 필요한 입력폼을 다음 순서로 검증한다.

1. 회사 프로필 존재 여부
2. 성공 프로젝트 1개 이상 존재 여부
3. 프로필에 임베딩 가능한 텍스트가 존재하는지
4. 프로젝트에 임베딩 가능한 텍스트가 존재하는지

조건 미충족 시 `409 Conflict`로 명확한 사유를 반환한다.

```text
회사 프로필을 먼저 작성해 주세요.
성공 프로젝트를 하나 이상 작성해 주세요.
회사 프로필에 임베딩할 수 있는 내용을 입력해 주세요.
성공 프로젝트에 임베딩할 수 있는 내용을 입력해 주세요.
```

전체 입력폼을 한 번 조회한 뒤 `embedding is None`인 객체만 임베딩 대상으로 선택한다.

#### 수정 후 변화와 효과

- 의미 없는 0점 검색 결과가 생성되는 것을 방지한다.
- 프론트 화면 분기를 우회한 직접 API 호출도 서버에서 차단한다.
- 이미 임베딩된 입력폼은 재사용하고 수정으로 무효화된 입력폼만 다시 임베딩한다.
- 준비 상태 검증과 지연 임베딩 대상 선정을 같은 조회 결과로 처리한다.

#### 설계 고민

폼 준비 검증을 별도의 서비스로 분리하면 코드 역할은 명확해지지만, 프로필과 프로젝트를 검증용으로
조회한 뒤 임베딩 서비스에서 다시 조회할 가능성이 있다. 이번에는 검색 전송 시 반드시 거치는
`ensure_company_embedded()`가 검증과 대상 선정을 함께 담당하도록 해 조회 중복을 줄였다.

### 3.3 `app/services/second_filter_service.py`

#### 수정 위치

- `SecondFilterService.run()`의 `ensure_company_embedded()` 호출 제거

#### 기존 문제

`search_service.search_bid_notices()`에서 지연 임베딩을 수행한 직후
`SecondFilterService.run()`에서도 같은 함수를 호출했다. 두 번째 호출에서 외부 임베딩 API가
항상 다시 호출되는 것은 아니지만, 프로필과 프로젝트 조회 쿼리는 중복 발생했다.

#### 변경 내용

지연 임베딩과 준비 검증의 책임을 상위 오케스트레이션인 `search_service` 한 곳으로 통합했다.
`SecondFilterService`는 이미 준비된 타깃을 로드해 검색하는 역할만 담당한다.

#### 수정 후 변화와 효과

- 검색 요청당 지연 임베딩 준비 호출이 정확히 1회 수행된다.
- 불필요한 프로필·프로젝트 조회가 제거된다.
- 오케스트레이션과 검색 알고리즘의 책임 경계가 명확해진다.

#### 설계 고민

`SecondFilterService` 단독 호출 시 자동 임베딩이 되지 않는다는 트레이드오프가 있다. 현재 운영 흐름은
항상 `search_service`를 통해 실행되므로 중복 제거를 우선했다. 향후 독립 호출이 필요해지면
`prepared=True` 같은 암묵적 플래그보다 명시적인 준비 서비스 호출을 사용하는 편이 안전하다.

### 3.4 `app/core/enums.py`

#### 변경 내용

검색세트 상태를 다음과 같이 확장했다.

| 상태 | 의미 |
|---|---|
| `ongoing_second_filter` | 2차 소프트필터 진행 중 |
| `ongoing_third_filter` | 3차 분석 진행 중 |
| `completed` | 3차 분석까지 완료 |
| `failed` | 2차 소프트필터 실패 |

#### 수정 이유와 효과

2차 처리 중 예외가 발생해도 `ongoing_second_filter`로 계속 남아 실패 여부를 알 수 없었다.
`failed` 상태를 추가해 진행 중인 검색과 실패한 검색을 구분하도록 했다. 별도의 2차 완료 상태는
두지 않으며, 정상 완료 후 팀원 2의 3차 필터가 시작되면 `ongoing_third_filter`로 전환된다.

팀원 2의 3차 실패 처리 방식은 이번 작업 범위에 포함하지 않았다. 따라서 현재 `failed`는
2차 소프트필터 실패에 대해서만 설정된다.

### 3.5 `app/services/search_service.py`

#### 수정 위치

- `search_bid_notices()` 상태 전이와 예외 처리

#### 기존 문제

2차 필터 시작 전에 `ongoing_second_filter`를 커밋했지만 이후 임베딩, Dense 검색 또는 BM25 검색이
실패하면 상태가 계속 진행 중으로 남았다. 사용자는 폴링을 계속해도 실패 여부를 알 수 없었다.

#### 변경 내용

정상 흐름:

```text
검색세트 생성
→ ongoing_second_filter
→ 입력폼 검증 및 지연 임베딩
→ 하드필터
→ Dense + BM25 + RRF
→ 3차 필터 시작 시 ongoing_third_filter
```

실패 흐름:

```text
예외 발생
→ 현재 트랜잭션 rollback
→ 검색세트 재조회
→ failed + failure_reason 저장
→ 원래 예외 재발생
```

예상 가능한 `AppException`은 사용자에게 전달 가능한 메시지를 저장한다. 예상하지 못한 예외의 내부
내용은 DB나 API에 그대로 노출하지 않고 다음 일반 메시지를 저장한다.

```text
2차 소프트필터 처리 중 오류가 발생했습니다.
```

#### 수정 후 변화와 효과

- 실패 시 무한 폴링 문제를 줄인다.
- 내부 예외 정보나 민감한 외부 API 메시지가 사용자에게 노출되는 것을 방지한다.
- 실패 후에도 기존 HTTP 예외 응답 동작은 유지한다.

#### 설계 고민

DB 예외가 발생하면 세션의 트랜잭션이 실패 상태일 수 있어 바로 상태 UPDATE를 실행할 수 없다.
따라서 먼저 `rollback()`한 뒤 이미 커밋된 검색세트를 다시 조회해 실패 상태를 저장했다.

### 3.6 `app/db/models/search.py`

#### 변경 내용

`SearchSet`에 nullable `failure_reason TEXT` 컬럼을 추가했다.

#### 수정 이유와 효과

상태만 `failed`로 저장하면 운영자와 사용자가 실패 원인을 알 수 없다. 안전하게 가공된 실패 사유를
검색세트 단위로 보존해 상태 API에서 확인할 수 있게 했다.

### 3.7 `app/db/init_db.py`

#### 기존 문제

`SQLModel.metadata.create_all()`은 새 테이블은 만들지만 이미 존재하는 테이블에 새 컬럼을 추가하지
않는다. 모델에 `failure_reason`만 추가하면 기존 개발 DB에는 컬럼이 생기지 않아 런타임 오류가
발생할 수 있다.

#### 변경 내용

기존 DB에도 안전하게 적용할 수 있도록 다음 SQL을 추가했다.

```sql
ALTER TABLE search_sets
ADD COLUMN IF NOT EXISTS failure_reason TEXT;
```

#### 수정 후 변화와 효과

- 신규 DB와 기존 DB 모두 같은 스키마를 갖는다.
- 초기화 명령을 여러 번 실행해도 `IF NOT EXISTS` 때문에 실패하지 않는다.

#### 향후 과제

현재 방식은 최소한의 호환 보강이다. 스키마 변경이 늘어나면 Alembic 같은 버전 기반 마이그레이션
도구를 도입해야 적용 순서, 롤백, 운영 이력을 관리할 수 있다.

### 3.8 `app/schemas/search.py`, `app/api/search.py`

#### 변경 내용

상태 조회 응답에 nullable `failure_reason`을 추가했다.

```json
{
  "search_set_id": 13,
  "status": "failed",
  "failure_reason": "성공 프로젝트를 하나 이상 작성해 주세요."
}
```

정상 상태에서는 `failure_reason`이 `null`이다. 메인 검색 응답과 팀원 2 전달 DTO는 변경하지 않았다.

### 3.9 테스트 파일

#### 추가·수정한 테스트

| 파일 | 검증 내용 |
|---|---|
| `tests/unit/test_company_profiles_api.py` | 프로필 수정 후 기존 임베딩이 `None`이 되는지 |
| `tests/unit/test_company_projects_api.py` | 프로젝트 수정 후 기존 임베딩이 `None`이 되는지 |
| `tests/unit/test_embedding_service.py` | 프로필·프로젝트 존재 및 임베딩 가능 텍스트 검증 |
| `tests/unit/test_search_service.py` | 임베딩 준비 호출 1회, 성공/실패 상태 전이 |
| `tests/unit/test_search_set_status_api.py` | 실패 상태와 실패 사유 응답 |
| `tests/unit/test_second_filter_service.py` | 제거된 중복 임베딩 호출 mock 정리 |

#### 검증 결과

```text
84 passed, 4 warnings
```

경고 4개는 Starlette의 기존 `HTTP_422_UNPROCESSABLE_ENTITY` deprecation warning이며 이번 변경의
실패나 회귀는 아니다.

## 4. 트러블슈팅 기록

### 4.1 기존 DB에 새 컬럼이 생성되지 않는 문제

#### 증상

ORM 모델에 `failure_reason`을 추가해도 기존 PostgreSQL 테이블에는 컬럼이 생기지 않는다.

#### 원인

`create_all()`은 기존 테이블의 ALTER 작업을 수행하지 않는다.

#### 해결

`SCHEMA_UPGRADES`에 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`를 추가하고 개발 DB에 적용했다.
`information_schema.columns` 조회로 `failure_reason text`가 실제 생성된 것을 확인했다.

### 4.2 Windows CP949 콘솔에서 DB 초기화 명령이 실패 코드로 종료

#### 증상

스키마 SQL 실행 후 마지막 출력에서 다음 오류가 발생했다.

```text
UnicodeEncodeError: 'cp949' codec can't encode character '\u2705'
```

#### 원인

초기화 완료 메시지의 체크 이모지(`✅`)를 Windows CP949 콘솔이 출력하지 못했다.

#### 해결

완료 메시지를 이모지 없는 `DB 스키마 초기화 완료`로 변경했다. 재실행 결과 exit code 0을 확인했다.

### 4.3 실패한 트랜잭션에서 상태 UPDATE가 불가능할 수 있는 문제

#### 고민

검색 중 DB 오류가 발생하면 같은 세션은 failed transaction 상태일 수 있다. 이 상태에서 바로
`status='failed'`를 커밋하면 또 실패할 수 있다.

#### 해결

예외 처리에서 `rollback()`을 먼저 수행한 뒤 검색세트를 다시 조회해 실패 상태를 저장했다.

### 4.4 실측 성능 확인 과정

Docker 접근은 샌드박스 권한 제한으로 최초 확인이 실패했다. 승인된 읽기 전용 Docker 명령으로
실행 중인 PostgreSQL을 확인한 뒤 `EXPLAIN (ANALYZE, BUFFERS)`를 사용해 Dense와 BM25를 측정했다.

## 5. 현재 하이브리드 검색 방식

### 5.1 처리 흐름

```text
하드필터 통과 공고
  ├─ 회사 프로필 Dense 검색
  ├─ 회사 프로필 BM25 검색
  ├─ 성공 프로젝트별 Dense 검색
  ├─ 성공 프로젝트별 BM25 검색
  └─ 자유형식 메시지 BM25 검색
                ↓
             RRF 융합
                ↓
       공고별 상위 청크 10개
```

현재는 리랭커가 없다. RRF 결과가 곧 최종 청크 순위다.

### 5.2 RRF 계산 방식

코드의 `rank`는 0부터 시작하므로 점수식은 다음과 같다.

```python
score += 1.0 / (RRF_K + rank + 1)
```

순위를 1부터 표현하면 다음과 같다.

```text
RRF(chunk) = Σ 1 / (60 + rank)
```

하나의 청크가 Dense, BM25, 자유형식 메시지 검색에 반복해서 등장하면 각 순위 기여도가 합산된다.

### 5.3 RRF를 선택한 이유

Dense의 코사인 거리와 BM25 점수는 범위와 분포가 다르다. 원점수를 그대로 더하면 점수 범위가 큰
검색 방식이 결과를 지배할 수 있다. RRF는 원점수가 아니라 순위만 이용하므로 별도 점수 정규화 없이
검색 결과를 결합할 수 있다.

`RRF_K=60`일 때의 기여도는 다음과 같다.

```text
1위  = 1/61 ≈ 0.01639
10위 = 1/70 ≈ 0.01429
```

1위와 10위의 차이는 약 13%다. 한 목록에서 몇 위인지보다 여러 검색 목록에서 반복적으로 등장하는
합의 효과를 상대적으로 강하게 반영한다.

단, `60`은 현재 데이터셋으로 최적화한 값이 아니라 일반적으로 쓰이는 휴리스틱이다. 최적값이라고
주장하려면 아래의 오프라인 평가가 필요하다.

### 5.4 현재 데이터와 실측 성능

개발 DB 측정 결과:

| 항목 | 값 |
|---|---:|
| 공고 수 | 209 |
| 전체 청크 수 | 35,213 |
| 공고당 전체 청크 평균 | 190.3 |
| 공고당 개요·요구사항 청크 평균 | 110.8 |
| 개요·요구사항 청크 중앙값 | 102 |
| 90퍼센타일 | 206.6 |
| 최대 | 323 |

대표 실행계획 측정:

| 쿼리 | 실행 시간 | 계획 시간 | 해석 |
|---|---:|---:|---|
| 공고 1건 Dense top-20 | 약 0.255ms | 약 1.153ms | 공고 ID 인덱스로 먼저 좁혀 현재 규모에서는 빠름 |
| 공고 1건 BM25 top-20 | 약 178.7ms | 약 164.1ms | BM25 고정 오버헤드가 큼 |
| 공고 20건 배치 BM25 | 약 53.1ms | 약 172.3ms | 공고별 반복보다 배치 처리가 유리 |

BM25 실행 시간은 캐시, 검색어, 매칭 건수와 DB 상태에 따라 달라질 수 있으므로 절대값보다는 쿼리
구조의 비교 근거로 사용해야 한다.

하드필터 공고 수를 `N`, 프로필+프로젝트 수를 `M`이라고 하면 쿼리 수는 대략 다음과 같다.

```text
Dense ≈ N × M
BM25 배치 ≈ M + 자유형식 메시지 1회
```

따라서 현재 병목 후보는 RRF의 파이썬 덧셈이 아니라 타깃 수에 따라 증가하는 Dense/BM25 검색이다.

### 5.5 `top_k=10`의 현재 의미와 한계

`top_k=10`은 공고를 10개로 줄이는 값이 아니다. 하드필터를 통과한 모든 공고에 대해 각 공고에서
팀원 2에게 전달할 청크를 최대 10개로 제한하는 값이다.

현재 정당화 가능한 이유:

- LLM 입력 토큰 수 제한
- 응답 크기 제한
- 개요와 여러 요구사항 근거를 함께 전달할 수 있는 최소한의 여유
- 검색 품질과 후속 분석 비용 사이의 초기 절충값

현재 정당화할 수 없는 부분:

- 5개보다 10개가 실제 평가 정확도가 높은지
- 10개면 중요한 요구사항을 충분히 포함하는지
- 15개 또는 20개 대비 비용 효율이 가장 좋은지

즉, 10은 합리적인 초기 운영값이지만 검증된 최적값은 아니다.

## 6. 검색 품질 평가지표를 실제로 측정하는 방법

### 6.1 먼저 정답 평가셋을 만든다

자동 지표를 계산하려면 어떤 청크가 중요한지 정답이 필요하다. 최소 30~50개의 검색 시나리오를
선정하고 다음 정보를 저장한다.

```json
{
  "case_id": "case-001",
  "company_id": 2,
  "message": "AI 플랫폼과 데이터 분석 경험을 우선",
  "filters": {
    "domain_code": "81111513"
  },
  "bid_notice_id": 41,
  "relevance": {
    "6587": 3,
    "6588": 2,
    "6601": 1
  }
}
```

관련도 등급 권장 기준:

| 등급 | 의미 |
|---:|---|
| 3 | 회사 적합성이나 평가표 판단에 반드시 필요한 핵심 요구사항 |
| 2 | 판단에 직접 도움이 되는 관련 청크 |
| 1 | 약하게 관련되거나 보조 근거로 사용할 수 있는 청크 |
| 0 | 무관한 청크 |

가능하면 두 명이 독립 라벨링하고 의견이 다른 청크만 합의한다. 한 명의 판단만 사용하면 특정
사람의 해석이 평가 결과에 과도하게 반영될 수 있다.

### 6.2 Recall@K

중요한 정답 청크 중 검색 상위 K개 안에 몇 개가 들어왔는지 측정한다.

```text
Recall@K = 상위 K개에 포함된 정답 청크 수 / 전체 정답 청크 수
```

예시:

```text
정답 청크: {10, 20, 30, 40}
검색 top-10에 포함: {10, 30, 40}
Recall@10 = 3/4 = 0.75
```

리랭커 이전 후보 검색에는 `Recall@30` 또는 `Recall@50`이 중요하다. 후보 단계에서 정답 청크를
놓치면 리랭커가 복구할 수 없기 때문이다.

### 6.3 MRR

첫 번째 정답 청크가 얼마나 빨리 등장하는지 측정한다.

```text
RR = 1 / 첫 번째 정답 청크 순위
MRR = 모든 평가 케이스 RR의 평균
```

예시:

```text
첫 정답 청크가 2위 → RR=0.5
첫 정답 청크가 5위 → RR=0.2
```

MRR은 가장 먼저 제시되는 근거의 품질을 보지만, 두 번째 이후 정답 청크의 품질은 반영하지 않는다.

### 6.4 nDCG@10

여러 관련 청크의 순서와 관련도 등급을 함께 평가한다.

```text
DCG@K = Σ ((2^relevance - 1) / log2(rank + 1))
nDCG@K = 실제 DCG@K / 이상적인 순서의 DCG@K
```

값은 0~1이며 1에 가까울수록 핵심 청크가 위쪽에 배치됐다는 의미다. 현재처럼 관련도 1~3을
구분할 수 있는 평가에서는 MRR보다 nDCG@10이 최종 top-10 품질을 더 잘 설명한다.

### 6.5 검색 지연시간 p50/p95

각 평가 케이스를 동일한 환경에서 여러 번 실행하고 `time.perf_counter()`로 측정한다.

권장 방식:

1. 워밍업 3~5회 결과는 버린다.
2. 각 조건을 최소 30회 실행한다.
3. 전체 시간과 Dense, BM25, RRF 시간을 각각 기록한다.
4. 중앙값 p50과 느린 요청을 나타내는 p95를 계산한다.

```python
p50 = numpy.percentile(latencies_ms, 50)
p95 = numpy.percentile(latencies_ms, 95)
```

평균만 사용하면 일부 매우 느린 요청이 사용자 경험에 미치는 영향을 확인하기 어렵다.

### 6.6 팀원 2에게 전달되는 토큰 수

최종 `ranked_chunks`의 원문과 팀원 2의 프롬프트 고정 문구를 실제 사용하는 토크나이저로 계산한다.

```python
encoding = tiktoken.encoding_for_model(settings.llm_model)
token_count = len(encoding.encode(prompt_text))
```

기록할 값:

- 공고당 청크 본문 토큰 수
- 공고당 전체 프롬프트 토큰 수
- 검색 요청 전체 토큰 수
- top-k 5/10/15별 예상 비용

`preview` 120자만 세면 안 되고 팀원 2가 실제 LLM에 넣는 전체 청크 본문을 기준으로 계산해야 한다.

## 7. 권장 실험 설계

### 7.1 1단계: 현재 검색 방식의 기준선

| 실험 | Dense | BM25 | RRF | 목적 |
|---|---:|---:|---:|---|
| A | O | X | X | 의미 기반 검색 기준선 |
| B | X | O | X | 정확 용어 검색 기준선 |
| C | O | O | K=60 | 현재 방식 |

측정값:

- Recall@10, Recall@20, Recall@50
- MRR
- nDCG@10
- p50/p95
- 공고당 전달 토큰 수

### 7.2 2단계: RRF 파라미터와 top-k

| 변수 | 비교값 |
|---|---|
| RRF K | 20, 60, 100 |
| 검색 후보 수 | 20, 30, 50 |
| 최종 전달 청크 수 | 5, 10, 15 |

한 번에 여러 변수를 바꾸지 않고 하나씩 바꿔야 결과 원인을 설명할 수 있다.

### 7.3 3단계: 리랭커 도입

리랭커를 추가할 때는 기존 `top_k=10`을 바로 후보 수로 사용하지 않는다.

```text
Dense + BM25 + RRF 후보 30~50개
→ 리랭커
→ 최종 10개
```

권장 초기값:

```python
retrieval_candidate_k = 50
final_top_k = 10
```

리랭커 실험에서는 다음 두 조건만 비교하면 기여도를 명확히 볼 수 있다.

```text
현재 RRF top-10
RRF top-50 → reranker top-10
```

### 7.4 초기 합격 기준 예시

다음 값은 확정 기준이 아니라 첫 실험을 위한 출발점이다.

```text
후보 Recall@50 ≥ 0.95
최종 nDCG@10이 현재 RRF 대비 향상
p95 검색 시간 증가 ≤ 30%
공고당 LLM 입력 토큰이 모델 한도의 70% 이하
```

## 8. 평가 실행 결과 저장 형식

### 8.1 구현된 평가 명령

평가 케이스는 회사 프로필·프로젝트·자유형식 메시지를 고정하고, 하드필터를 통과한 여러 공고를
하나의 시나리오로 구성한다. 첫 평가 케이스용 다중 공고 라벨링 CSV를 생성한다.

```text
uv run python -m scripts.evaluation.export_label_candidates --case-id case-001-multi-project --company-id 2 --bid-notice-ids 41,159,75,119,122 --message "AI 플랫폼과 데이터 분석 경험을 우선" --pool-k 20 --output evaluation/labels/case-001-multi-project.csv
```

CSV의 `notice_relevance`에는 회사와 공고 전체의 관련도 0~3을, `chunk_relevance`에는 공고별 후보
청크 관련도 0~3을 입력한다. 같은 공고의 모든 행에는 동일한 `notice_relevance`를 넣은 뒤 JSONL로
변환한다.

```text
uv run python -m scripts.evaluation.build_cases_from_labels --input evaluation/labels/case-001-multi-project.csv --output evaluation/second_filter_cases.jsonl
```

Dense only, BM25 only, 현재 RRF 기준선을 실행한다.

```text
uv run python -m scripts.evaluation.second_filter_benchmark --cases evaluation/second_filter_cases.jsonl --methods dense,bm25,rrf --candidate-k 50 --final-k 10 --warmup 2 --repeat 10 --output-dir evaluation/results
```

현재 구현된 파일:

| 파일 | 역할 |
|---|---|
| `scripts/evaluation/retrieval_metrics.py` | Recall, MRR, nDCG, percentile 계산 |
| `scripts/evaluation/export_label_candidates.py` | DB 청크를 사람 검토용 CSV로 출력 |
| `scripts/evaluation/build_cases_from_labels.py` | 라벨 CSV를 평가 JSONL로 변환 |
| `scripts/evaluation/second_filter_benchmark.py` | Dense/BM25/RRF 실행 및 JSON/CSV 결과 저장 |
| `evaluation/README.md` | 평가 작업 순서와 명령어 |

`evaluation/labels/case-001-multi-project.csv`에는 실제 프로젝트 1개와 평가용 가상 프로젝트
3개를 기준으로 공고 41, 159, 75, 119, 122를 같은 회사·메시지로 검색한 Dense/BM25/RRF 후보
합집합 129개를 내보냈다. 라벨은 의도적으로 비워 두었으며 담당자가
공고 원문과 회사 입력폼을 함께 읽고 입력해야 한다. `pool-k=20`은 첫 라벨링 작업량을 제한하기 위한
값이며, 본 평가에서는 50으로 넓히거나 원문에서 누락된 핵심 청크를 직접 추가해야 한다.

CSV와 함께 생성되는 `case-001-multi-project.context.json`에는 실제 비교에 사용한 프로필·프로젝트 텍스트,
자유형식, 필터, 공고 목록과 임베딩 지문이 저장된다. JSONL 변환 시 이 스냅샷을 평가 케이스에
포함하고 벤치마크 실행 시 현재 DB 입력과 대조한다. 라벨링 이후 회사 입력폼이 변경됐다면 기존
라벨을 다른 입력에 잘못 사용하는 것을 막기 위해 평가를 중단한다.

### 8.2 결과 형식

실험 결과에는 공고 순위와 공고별 청크 순위가 함께 저장된다. 청크 지표는 관련 청크가 있는 공고별
점수를 평균하고, 공고 지표는 하나의 시나리오 안에서 관련 공고가 얼마나 위에 배치됐는지 계산한다.
실험 결과를 CSV로 남기면 조건 간 비교와 그래프 작성이 쉽다.

```csv
case_id,method,notice_count,chunk_recall_at_20,chunk_mrr,chunk_ndcg_at_10,notice_mrr,notice_ndcg_at_10,latency_p95_ms,final_token_count
case-001,rrf,5,0.88,0.72,0.81,1.0,0.91,630,24100
```

실험 환경도 함께 기록한다.

- Git commit
- 데이터 스냅샷 시각
- 임베딩 모델과 차원
- BM25 tokenizer
- RRF K
- 후보 수와 최종 top-k
- PostgreSQL/pgvector/pg_search 버전
- LLM 및 리랭커 모델

## 9. 남은 위험과 후속 과제

- `RRF_K=60`, `top_k=10`은 아직 라벨 평가셋으로 검증하지 않았다.
- 회사 프로젝트 수가 증가하면 Dense 쿼리는 `공고 수 × 타깃 수`로 증가한다.
- BM25는 타깃 텍스트 수만큼 배치 쿼리가 증가한다.
- 현재 `aggregate_score`는 top-k RRF 점수 합이므로 검색 간 절대 점수 비교에는 주의가 필요하다.
- 리랭커를 추가하려면 후보 수와 최종 전달 수를 분리해야 한다.
- 현재 실패 상태 관리는 2차 소프트필터 범위에만 적용했다.
- 최소 스키마 보강 방식은 장기적으로 정식 마이그레이션 도구로 교체해야 한다.

## 10. 최종 요약

이번 변경은 검색 알고리즘의 점수 산식을 바꾸지 않고 입력 데이터 정합성, 검색 준비 검증, 상태 추적,
실패 복구 가능성을 개선했다. 메인 검색 응답과 팀 간 DTO는 유지했다.

현재 Dense+BM25를 RRF로 결합하는 방식은 서로 다른 점수 공간을 순위 기반으로 안정적으로 합친다는
점에서 타당하다. BM25를 공고 전체에 대해 배치 검색하는 선택도 실제 실행계획 측정으로 타당성을
확인했다. 다만 `RRF_K=60`과 `top_k=10`은 아직 경험적 초기값이므로, 리랭커 도입 전에 정답 청크가
표시된 평가셋을 만들고 Recall@K, MRR, nDCG@10, p50/p95, 토큰 수, 최종 평가표 오차를 기준으로
검증해야 한다.
