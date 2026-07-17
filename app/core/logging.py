"""앱 전역 로깅 설정.

설정 시점: uvicorn 은 자체 로깅을 구성(Config.configure_logging)한 **뒤에** main 모듈을
import 하므로, main.py 에서 setup_logging() 을 호출하면 uvicorn 설정을 덮어쓰지 않고
그 위에 얹힌다. uvicorn 로거(uvicorn / uvicorn.access)는 propagate=False 라 자기 포맷을
그대로 유지하고, 우리 앱 로그만 아래 포맷으로 나간다.

레벨 정책: 루트는 WARNING 으로 두어 서드파티(openai/httpx/sqlalchemy 등)를 조용히 시키고,
"app" 로거만 settings.log_level 로 연다. 3차 필터처럼 수십 초 도는 파이프라인의 진행
상황을 INFO 로 남기기 위해서다.
"""

from __future__ import annotations

import logging
import re
import sys

from app.core.config import settings

# 프론트가 3초 주기(ChatSessionPage.jsx POLL_INTERVAL_MS)로 때리는 상태 조회 엔드포인트.
# 3차 필터가 1분 돌면 access log 20줄이 쌓여 진행 로그를 덮어버리므로 이 요청만 걸러낸다.
_POLLING_ACCESS_LOG_RE = re.compile(r"GET /bid-notices/search-sets/\d+/status")

_LOG_FORMAT = "%(asctime)s %(levelname)-7s %(message)s"
_DATE_FORMAT = "%H:%M:%S"


class ExcludePollingAccessLog(logging.Filter):
    """상태 폴링 요청의 access log 만 버린다. 다른 요청의 access log 는 그대로 남는다."""

    def filter(self, record: logging.LogRecord) -> bool:
        return _POLLING_ACCESS_LOG_RE.search(record.getMessage()) is None


def setup_logging(level: str | None = None) -> None:
    """루트 핸들러를 붙이고, 앱 로거 레벨과 폴링 access log 필터를 설정한다(멱등)."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))

    root = logging.getLogger()
    root.handlers = [handler]  # reload 시 핸들러 중복 부착 방지
    root.setLevel(logging.WARNING)

    logging.getLogger("app").setLevel(level or settings.log_level)

    # uvicorn 이 이미 구성해둔 로거에 필터만 얹는다. 중복 부착을 피해 한 번만 단다.
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, ExcludePollingAccessLog) for f in access_logger.filters):
        access_logger.addFilter(ExcludePollingAccessLog())
