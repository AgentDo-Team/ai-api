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

### 3. 서버 실행

```bash
uv run uvicorn main:app --reload
```

실행 후 아래 주소에서 확인할 수 있습니다.

- API: http://127.0.0.1:8000
- Swagger 문서: http://127.0.0.1:8000/docs

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
