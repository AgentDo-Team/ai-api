# 2차 소프트필터 오프라인 평가

평가 단위는 공고 하나가 아니라 다음 입력을 고정한 **검색 시나리오 하나**다.

- 회사 프로필 1개
- 성공 프로젝트 1개 이상
- 공고 필터와 자유형식 메시지
- 하드필터를 통과한 여러 공고
- 각 공고의 `개요`, `요구사항` 청크

## 1. 다중 공고 후보 풀 생성

아래 명령은 같은 회사·메시지로 공고 5개를 Dense, BM25, RRF로 검색한 뒤 후보 합집합을 CSV로 만든다.

```text
uv run python -m scripts.evaluation.export_label_candidates --case-id case-001-multi-project --company-id 2 --bid-notice-ids 41,159,75,119,122 --message "AI 플랫폼과 데이터 분석 경험을 우선" --filters "{}" --pool-k 20 --output evaluation/labels/case-001-multi-project.csv
```

현재 `case-001-multi-project.csv`는 실제 프로젝트 1개와 평가용 가상 프로젝트 3개를 기준으로
조회한 5개 공고, 129개 후보 청크를 담고 있다. 한 청크가 여러 방식에
검색되므로 `dense_rank`, `bm25_rank`, `rrf_rank`, `retrieved_by`를 함께 기록한다.

명령을 실행하면 `evaluation/labels/case-001-multi-project.context.json`도 함께 생성된다. 여기에는 프로필과
프로젝트별 실제 임베딩 입력 텍스트, 자유형식, 필터, 공고 목록, 임베딩 SHA-256 지문이 들어 있다.
라벨 작성자는 CSV와 context JSON을 함께 열어 비교 기준을 확인하며, context 파일은 수정하지 않는다.

## 2. 사람 라벨 입력

CSV에서 다음 두 열을 모두 채운다.

- `notice_relevance`: 회사 역량과 공고 전체의 적합도 0~3. 같은 공고의 모든 행에 같은 값을 입력한다.
- `chunk_relevance`: 실제 판단에 필요한 청크 관련도 0~3. 후보 풀의 모든 행에 입력한다.

관련도 기준:

- 3: 판단에 반드시 필요한 핵심 근거
- 2: 직접적으로 유용한 근거
- 1: 보조 근거
- 0: 무관

후보 풀 방식은 어떤 검색법도 찾지 못한 청크를 라벨링하지 못할 수 있다. 중요한 청크가 빠졌다면
원문에서 직접 추가하거나 `--pool-k 50`으로 후보 풀을 넓힌다.

전체 문서 Recall을 측정하려면 `개요`, `요구사항` 전체 청크를 내보낸다. 기존 129개 라벨은
`--existing-labels`로 재사용되며 새 청크만 비어 있는 상태로 생성된다.

```text
uv run python -m scripts.evaluation.export_label_candidates --case-id case-001-full --company-id 2 --bid-notice-ids 41,159,75,119,122 --message "AI 플랫폼과 데이터 분석 경험을 우선" --filters "{}" --pool-k 50 --all-domain-chunks --existing-labels C:\Users\user\Downloads\case-001-multi-project.csv --output evaluation/labels/case-001-full.csv
```

리랭커 전후 비교용 약 1,000개 평가셋은 하드필터 후보 9개 공고의 전체 청크 1,039개로 구성한다.

```text
uv run python -m scripts.evaluation.export_label_candidates --case-id case-001-1000 --company-id 2 --bid-notice-ids 41,159,75,119,122,18,16,113,35 --message "AI 플랫폼과 데이터 분석 경험을 우선" --filters "{}" --pool-k 50 --all-domain-chunks --existing-labels C:\Users\user\Downloads\case-001-multi-project.csv --output evaluation/labels/case-001-1000.csv
```

이 파일은 기존 129개 청크 라벨과 기존 공고 5개의 `notice_relevance`를 재사용한다. 추가 공고 4개의
`notice_relevance`와 아직 비어 있는 `chunk_relevance` 910개를 작성한 뒤 평가 JSONL로 변환한다.

완료된 전체 라벨 기준선은 다음 경로에 저장한다.

```text
evaluation/second_filter_cases_1000.jsonl
evaluation/results/full-1000/<run_id>.json
evaluation/results/full-1000/<run_id>.csv
```

2026-07-17 기준 RRF 전체 문서 결과는 Recall@50 `0.782`, MRR `0.800`, nDCG@10 `0.396`,
p95 `11,128.893ms`다. 기존 129개 후보 풀 결과는 Pooled Recall 참고값으로만 사용한다.

## 3. 평가 JSONL 생성

```text
uv run python -m scripts.evaluation.build_cases_from_labels --input evaluation/labels/case-001-multi-project.csv --output evaluation/second_filter_cases.jsonl
```

빈 라벨, 0~3 범위를 벗어난 라벨, 공고 안에서 서로 다른 `notice_relevance`가 있으면 변환이 실패한다.
CSV 옆에 같은 이름의 `.context.json`이 없어도 변환이 실패한다.
단, 다운로드 폴더의 CSV를 직접 입력하면 프로젝트의 `evaluation/labels`에서 같은 이름의 context를
자동으로 찾는다.

## 4. 기준선 실행

```text
uv run python -m scripts.evaluation.second_filter_benchmark --cases evaluation/second_filter_cases.jsonl --methods dense,bm25,rrf --candidate-k 50 --final-k 10 --warmup 2 --repeat 10 --output-dir evaluation/results
```

측정값:

- 공고별 청크 Recall@10/20/50, MRR, nDCG@10의 시나리오 평균
- 관련도 2 이상 Recall@10
- 관련도 3 기준 Recall@10/20/50, 후보 Recall, Hit Rate@10, MRR
- 여러 공고의 Recall@5/10, MRR, nDCG@10
- 전체 시나리오 검색시간 p50/p95
- 모든 공고의 최종 top-k 청크 토큰 합계

`candidate-k`보다 큰 Recall@K는 `null`이다. 검색시간은 공고 하나가 아니라 시나리오에 포함된 모든
공고를 처리하는 시간이다. `filters`는 재현용 메타데이터이며 실제 공고 목록은 `bid_notice_ids`에
하드필터 결과를 고정해 넣는다.

벤치마크는 현재 DB의 프로필·프로젝트 텍스트와 임베딩 지문을 라벨링 당시 스냅샷과 비교한다.
입력폼이 수정됐다면 평가를 중단하므로 후보 CSV를 다시 생성하고 다시 라벨링해야 한다.

## 5. 현재 운영 기준

CPU BGE ONNX 리랭커는 실제 케이스에서 지연시간이 크게 증가하고 MRR·nDCG가
개선되지 않아 제거했다. 현재 운영·평가 대상은 Dense, BM25, RRF이며 최종 전달 수는
공고별 10개로 유지한다.

```text
Dense + BM25 + 자유형식 BM25 → RRF 후보 50개 → 최종 10개
```

API 응답 DTO와 팀원 2에게 전달되는 최종 청크 형식은 변경하지 않는다.
