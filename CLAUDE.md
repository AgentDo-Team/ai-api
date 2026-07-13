# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

- 목적: AI 입찰공고 분석 서비스
- 주요 사용자: IT 회사의 입찰공고를 분석하는 부서
- 핵심 기능: RAG로 입찰공고를 읽어서 분석후 추천해주는 기능

## Tech Stack

- Language: Python 3.12
- Framework: fastAPI,
- ORM: SQLmodel
- DataBase: PostgreSQL + pgvector extension, run via Docker Compose (`docker/docker-compose.yml`)
- Package manager: uv
- Test: pytest
- Build: 별도 애플리케이션 빌드 단계 없음 (uv로 실행하는 서비스). 배포용 `docker/Dockerfile`은 현재 비어 있어 이미지 빌드는 아직 준비되지 않음

## Directory Structure
- app/ — FastAPI 앱 진입점. 미들웨어, 라우터, 예외핸들러, lifespan 등록
- app/api/ — HTTP 엔드포인트 계층. 질의/RAG, 문서 색인, 헬스체크 등 라우터 정의
- app/core/ — 앱 전역 설정. Settings(.env), 로깅, DB/MCP 커넥션 startup·shutdown(lifespan)
- app/common/ — 공통 응답/예외 처리. 응답 스키마 래퍼, 커스텀 예외, 전역 예외핸들러, 에러코드 상수
- app/schemas/ — Pydantic DTO 정의. 문서/질의/채팅 등 도메인별 요청·응답 모델
- app/db/ — 영속성 계층. ORM 모델(문서, pgvector 임베딩 청크) + 리포지토리(하이브리드 검색, pre-filtering 쿼리)
- app/rag/ — RAG 파이프라인 구성 요소. 문서 로더(PDF/HWP), 청킹 전략, 임베딩 래퍼, 검색(유사도+필터) 로직
- app/llm/ — Multi-LLM 어댑터 계층. 공통 인터페이스, provider 레지스트리(fallback 포함), OpenAI/Ollama 등 어댑터 구현체
- app/mcp/ — MCP 프로토콜 연동. 클라이언트 초기화, 자체 서버 노출(선택), 연결할 MCP 서버 설정
- app/tools/ — Tool 레지스트리. tool 인터페이스, 등록/디스패치, RAG 검색 등 개별 tool 구현
- app/services/ — 비즈니스 로직/오케스트레이션 계층. 채팅(LLM+tool+RAG 조합), 색인, 검색 파이프라인 조율
- tests/ — 유닛/통합 테스트 및 pytest 공통 fixture
- docker/ — 컨테이너 정의. Dockerfile, app+postgresql(pgvector)+ollama compose 구성

## Common Commands

```text
install: uv sync
dev: docker compose -f docker/docker-compose.yml up -d && uv run python -m app.db.init_db && uv run uvicorn main:app --reload
test: uv run pytest   # DB/Ollama 없이 도는 단위 테스트
build:  (해당 없음 — 위 Tech Stack의 Build 항목 참고)
```

## Working Rules

- 변경 전 관련 파일을 먼저 읽는다.
- 큰 변경은 계획을 먼저 제안한다.
- 테스트 없이 동작을 단정하지 않는다.

## Code Style
- All API response wrap in `ApiResponse`
- API 변경 시 문서와 테스트를 함께 갱신한다.


## Done Criteria

- 관련 테스트를 실행했다.
- 실행하지 못한 검증은 이유를 남겼다.
- 변경 파일과 위험도를 요약했다.
