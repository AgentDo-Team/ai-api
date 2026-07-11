# ai-api

## 시작하기

### 1. uv 설치 (최초 1회)
brew는 맥 전용이라 윈도우 사용자는 참고 부탁합니다
```bash
brew install uv
```

### 2. 의존성 설치

`pyproject.toml`에 정의된 의존성을 그대로 설치하게 됩니다

```bash
uv sync
```

### 3. 환경변수 설정

`.env.example`을 복사해서 `.env`를 만듭니다. (DB 접속 정보는 기본값 그대로 쓰면 됩니다)

```bash
cp .env.example .env
```

### 4. 데이터베이스 실행 + 스키마 생성

PostgreSQL(+pgvector)을 도커로 띄웁니다. Docker Desktop이 켜져 있어야 합니다.

```bash
docker compose -f docker/docker-compose.yml up -d
```

컨테이너가 뜨면 테이블과 벡터 인덱스를 생성합니다. (`app/db/models` 의 SQLModel 정의 기준)

```bash
uv run python -m app.db.init_db
```

`✅ DB 스키마 초기화 완료` 가 출력되면 성공입니다. 아래 명령어로 테이블 목록을 확인할 수 있습니다.

```bash
docker exec ai-api-postgres psql -U edu -d edudb -c "\dt"
```

### 5. 서버 실행

```bash
uv run uvicorn main:app --reload
```

실행 후 아래 주소에서 확인할 수 있습니다.

- API: http://127.0.0.1:8000
- Swagger 문서: http://127.0.0.1:8000/docs

## 데이터베이스 관리

```bash
docker compose -f docker/docker-compose.yml up -d    # DB 시작
docker compose -f docker/docker-compose.yml down     # DB 중지 (데이터는 유지됨)
docker compose -f docker/docker-compose.yml down -v  # DB 중지 + 데이터 전체 삭제
```

### 모델(스키마)이 바뀌었을 때 ⚠️

`init_db`는 내부적으로 `create_all`을 쓰기 때문에 **이미 존재하는 테이블은 건드리지 않습니다.**
즉 누군가 `app/db/models` 에 컬럼을 추가/삭제해도, 내 DB에 그 테이블이 이미 있으면
`uv run python -m app.db.init_db` 를 다시 돌려도 아무 일도 일어나지 않습니다. (에러도 안 남)

아직 마이그레이션 도구(Alembic)를 안 쓰고 있으므로, 스키마가 바뀌면 DB를 갈아엎는 게 가장 확실합니다.
개발 중이라 데이터가 없다는 전제입니다 — **데이터가 날아가니 주의하세요.**

```bash
docker compose -f docker/docker-compose.yml down -v  # 볼륨까지 삭제
docker compose -f docker/docker-compose.yml up -d
uv run python -m app.db.init_db                       # 새 스키마로 재생성
```

특정 테이블만 다시 만들고 싶다면 해당 테이블만 드롭한 뒤 `init_db`를 다시 실행하면 됩니다.

```bash
docker exec ai-api-postgres psql -U edu -d edudb -c "DROP TABLE chunks;"
uv run python -m app.db.init_db
```

## 의존성 추가/삭제

```bash
uv add <패키지명>        # 의존성 추가
uv add <패키지명> --dev  # 개발용 의존성 추가 (테스트, 린트 등)
uv remove <패키지명>     # 의존성 삭제
```

패키지를 추가/삭제하면 `pyproject.toml`과 `uv.lock`이 자동으로 갱신됩니다. 두 파일 모두 커밋해서 깃허브에 올려야 우리 팀원들이 사용할 수 있음!!!

## 참고

- `uv run <파일명>`: 가상환경(`.venv`) 활성화 없이 바로 실행
- `uv sync`: `uv.lock` 기준으로 내 환경을 동기화 (다른 사람이 의존성을 추가/변경했을 때 실행)

## uv run 관련 부연설명
uv run은 명령을 실행하기 직전에 내부적으로 .venv를 찾아서 그 환경의 파이썬/패키지를 사용해 실행하므로
conda activate 같은 명령어 실행 단계를 건너뛸 수 있습니다
여러분이 conda 환경에서 실행했다고 해도 uv run 으로 실행하면 그걸 무시하고 pyproject.toml기반 환경에서 실행됩니다
