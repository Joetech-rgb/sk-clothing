"""Logging filters: stamp the request ID and mask phone numbers. Standard library only."""

import logging

from .redaction import redact
from .request_ids import get_request_id


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except (TypeError, ValueError):  # a malformed log call must not break the request
            message = str(record.msg)
        record.msg = redact(message)
        record.args = ()
        return True
