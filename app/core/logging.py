from __future__ import annotations

import logging
import re
import sys

from app.core.config import settings

_POLLING_ACCESS_LOG_RE = re.compile(r"GET /bid-notices/search-sets/\d+/status")

_LOG_FORMAT = "%(asctime)s %(levelname)-7s %(message)s"
_DATE_FORMAT = "%H:%M:%S"


class ExcludePollingAccessLog(logging.Filter):

    def filter(self, record: logging.LogRecord) -> bool:
        return _POLLING_ACCESS_LOG_RE.search(record.getMessage()) is None


def setup_logging(level: str | None = None) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))

    root = logging.getLogger()
    root.handlers = [handler] 
    root.setLevel(logging.WARNING)

    logging.getLogger("app").setLevel(level or settings.log_level)

    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, ExcludePollingAccessLog) for f in access_logger.filters):
        access_logger.addFilter(ExcludePollingAccessLog())
