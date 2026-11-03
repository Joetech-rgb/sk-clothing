"""Request IDs. Pure Python (stdlib only).

Every request gets an ID that appears in the response header, in every log line for that request,
in error bodies and in Sentry, so one failed checkout can be traced end to end. An ID sent by the
caller is kept only if it is a plain token, so nobody can inject odd characters into the logs.
"""

import re
import uuid
from contextvars import ContextVar, Token

NO_REQUEST = "-"
_VALID = re.compile(r"[A-Za-z0-9._-]{8,64}")
_current: ContextVar[str] = ContextVar("request_id", default=NO_REQUEST)


def new_request_id() -> str:
    return uuid.uuid4().hex


def resolve_request_id(incoming: str | None) -> str:
    """The caller's ID if it is a safe token, otherwise a new one."""
    if incoming and _VALID.fullmatch(incoming):
        return incoming
    return new_request_id()


def set_request_id(value: str) -> Token[str]:
    return _current.set(value)


def reset_request_id(token: Token[str]) -> None:
    _current.reset(token)


def get_request_id() -> str:
    return _current.get()
