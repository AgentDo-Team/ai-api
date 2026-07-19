# SQLModel로 company_context 조회하기 (company_id 기준)

RAG가 "이 회사가 이 공고에 적합한가"를 판단하려면, LLM 프롬프트에 넣을 `company_context`
텍스트가 필요하다. 이 문서는 `company_id` 하나로 `company_profiles`(회사 프로필, 1건)와
`company_projects`(회사 실적, N건)를 조회해서 그 텍스트를 만드는 방법을 SQLModel 쿼리
기준으로 설명한다.

## 1. 테이블 관계부터 이해하기

`app/db/models/company.py`에 세 테이블이 정의되어 있다.

```python
class Company(SQLModel, table=True):
    __tablename__ = "companies"
    id: int | None = Field(sa_column=Column(BigInteger, primary_key=True, ...))
    email: str
    ...

class CompanyProfile(SQLModel, table=True):
    __tablename__ = "company_profiles"
    id: int | None = ...
    company_id: int = Field(
        sa_column=Column(BigInteger, ForeignKey("companies.id"), nullable=False, unique=True)
    )
    company_scale: CompanyScale
    target_techs: str | None
    offered_solutions: str | None
    strengths_diff: str | None
    credit_rating: CreditRating
    sp_grade: SpGrade
    embedding: list[float] | None
    ...

class CompanyProject(SQLModel, table=True):
    __tablename__ = "company_projects"
    id: int | None = ...
    company_id: int = Field(
        sa_column=Column(BigInteger, ForeignKey("companies.id"), nullable=False)
    )
    title: str
    client: str | None
    domain: str | None
    tech_stack: str | None
    develop_features: str | None
    content: str | None
    performance: str | None
    embedding: list[float] | None
    ...
```

핵심 포인트 2가지:

- **`CompanyProfile.company_id`에 `unique=True`**가 걸려 있다 → 회사당 프로필은 **정확히 0개
  또는 1개**. 따라서 조회 결과도 "1건 또는 None"으로 다뤄야 한다.
- **`CompanyProject.company_id`는 unique가 아니다** → 회사당 실적은 **여러 건**. 조회 결과는
  리스트다.

두 테이블 모두 `Relationship()`으로 ORM 레벨 연결을 걸어두지 않았다. 즉 `company.profile`
처럼 접근할 수 없고, **각 테이블을 `company_id`로 직접 필터링**해서 가져와야 한다. 이 프로젝트
스타일에서는 그게 오히려 명시적이라 의도된 설계다.

## 2. 기본 쿼리 패턴: `select().where()`

SQLModel의 비동기 쿼리는 항상 이 3단계다.

1. `select(모델)`로 쿼리 객체 생성
2. `.where(조건)`으로 필터
3. `await session.exec(쿼리)`로 실행 → 결과에서 `.first()` / `.all()`로 값 추출

### 2-1. 프로필 1건 조회 (`get_by_company_id`)

```python
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.db.models.company import CompanyProfile

async def get_profile_by_company_id(
    session: AsyncSession, company_id: int
) -> CompanyProfile | None:
    result = await session.exec(
        select(CompanyProfile).where(CompanyProfile.company_id == company_id)
    )
    return result.first()
```

- `unique=True` 컬럼으로 필터링하는 거라 결과가 많아야 1건이다. 그래서 `.first()`를 쓴다
  (`.one()`을 써도 되지만, 프로필이 없는 회사도 정상 상태이므로 예외를 던지는 `.one()`보다
  `None`을 자연스럽게 돌려주는 `.first()`가 이 도메인에 맞는다).
- 실제 구현은 `app/db/repositories/company_repository.py`의
  `CompanyProfileRepository.get_by_company_id`에 있다.

### 2-2. 프로젝트 여러 건 조회 (`list_by_company`)

```python
async def list_projects_by_company(
    session: AsyncSession, company_id: int, limit: int = 20, offset: int = 0
) -> list[CompanyProject]:
    result = await session.exec(
        select(CompanyProject)
        .where(CompanyProject.company_id == company_id)
        .order_by(CompanyProject.id)
        .offset(offset)
        .limit(limit)
    )
    return list(result.all())
```

- `.all()`은 여러 건을 리스트로 돌려준다. `result.all()`은 SQLAlchemy `Sequence` 타입이라
  타입 힌트를 명확히 하려면 `list(...)`로 감싼다.
- `order_by` + `limit`/`offset`은 실적이 너무 많을 때 LLM 프롬프트가 무한정 길어지는 걸
  막기 위한 안전장치다. 실제 코드(`third_filter_service.py`)에서는
  `limit=_FIT_ANALYSIS_MAX_PROJECTS`처럼 상수로 상한을 건다.
- 실제 구현은 `CompanyProjectRepository.list_by_company`에 있다.

## 3. 레포지토리 계층에서 조립하기

이 프로젝트는 "DB 접근은 레포지토리, 텍스트 조립/비즈니스 판단은 서비스"로 계층을
나눈다 (`CLAUDE.md` 참고). 그래서 쿼리 자체는 위 두 메서드가 전부고, `company_context`를
만드는 조립 로직은 서비스 계층에 있다. 실제로 이 조합(두 레포지토리를 같이 호출해서
LLM 프롬프트용 컨텍스트를 만드는 패턴)은 `app/services/evaluation_service.py`의
`_build_criterion_prompt`에서 그대로 쓰인다.

```python
async def build_company_context(session: AsyncSession, company_id: int) -> str:
    profile = await CompanyProfileRepository(session).get_by_company_id(company_id)
    projects = await CompanyProjectRepository(session).list_by_company(
        company_id, limit=20
    )
    ...
```

텍스트 포맷팅까지 직접 f-string으로 짤 필요는 없다. `app/services/embedding_service.py`에
이미 재사용 가능한 포맷터가 있다.

```python
from app.services.embedding_service import profile_text, project_text

async def build_company_context(session: AsyncSession, company_id: int) -> str:
    profile_repo = CompanyProfileRepository(session)
    project_repo = CompanyProjectRepository(session)

    # 1) 프로필 조회 (없을 수 있음)
    profile = await profile_repo.get_by_company_id(company_id)
    profile_str = profile_text(profile) if profile else "(등록된 프로필 없음)"

    # 2) 프로젝트 목록 조회 (0건일 수 있음)
    projects = await project_repo.list_by_company(company_id, limit=20)
    projects_str = (
        "\n".join(project_text(p) for p in projects) or "(등록된 실적 없음)"
    )

    return f"{profile_str}\n\n{projects_str}"
```

`profile_text` / `project_text`는 `(라벨, 값)` 쌍을 내부 `_compose`로 조립하는 함수라,
필드가 늘어나도 이 두 함수만 고치면 되고 컨텍스트를 만드는 모든 호출부(2차 필터, 3차 필터,
평가 서비스)가 같은 포맷을 공유한다. 새로 짜는 코드에서 프로필/프로젝트를 텍스트로 바꿀
일이 있으면, f-string을 새로 만들기 전에 이 두 함수를 먼저 재사용할 수 있는지 확인한다.

## 4. 흔한 실수

- **`profile`이 `None`일 수 있다는 걸 잊고 `profile.target_techs`처럼 바로 접근** →
  `AttributeError`. 반드시 `if profile else ...` 분기를 넣는다.
- **프로필을 `.all()`로, 프로젝트를 `.first()`로 헷갈려서 조회** → 프로필은 1건(`.first()`),
  프로젝트는 여러 건(`.all()`)이라는 스키마상의 unique 제약을 기준으로 구분한다.
- **`limit` 없이 프로젝트 전체를 가져와 프롬프트에 다 욱여넣기** → 회사 실적이 많으면
  토큰 낭비/컨텍스트 초과로 이어진다. 상한을 두고 정렬 기준(최근 등록순 등)을 명시한다.
- **N+1 쿼리**: 여러 회사의 컨텍스트를 한 번에 만들어야 한다면, `company_id`별로
  `get_by_company_id`/`list_by_company`를 반복 호출하지 말고
  `.where(CompanyProfile.company_id.in_(company_ids))`처럼 `in_()`으로 한 번에 가져온 뒤
  파이썬에서 `company_id`로 그룹핑하는 걸 검토한다.

## 5. 참고 파일

| 파일 | 역할 |
|---|---|
| `app/db/models/company.py` | `Company`, `CompanyProfile`, `CompanyProject` 모델 정의 |
| `app/db/repositories/company_repository.py` | `get_by_company_id`, `list_by_company` 등 쿼리 메서드 |
| `app/services/embedding_service.py` | `profile_text`, `project_text` 재사용 가능한 텍스트 포맷터 |
| `app/services/evaluation_service.py` | `_build_criterion_prompt`: 두 레포지토리를 함께 써서 LLM 프롬프트용 컨텍스트를 조립하는 실제 예 |
| `app/services/third_filter_service.py` | 임베딩 없는 경우까지 포함한 컨텍스트 조립 예 |
