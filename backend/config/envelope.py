"""The standard API error envelope (CLAUDE.md section 4). Pure Python.

Every error from /api/v1 has the same shape:
    {"error": {"code": "...", "message": "...", "details": {...}, "request_id": "..."}}
`details` and `request_id` appear only when there is something to say.
"""

from typing import Any

STATUS_CODES = {
    400: "bad_request",
    401: "not_authenticated",
    403: "permission_denied",
    404: "not_found",
    405: "method_not_allowed",
    406: "not_acceptable",
    409: "conflict",
    415: "unsupported_media_type",
    429: "throttled",
}


def code_for_status(status: int) -> str:
    if status in STATUS_CODES:
        return STATUS_CODES[status]
    return "server_error" if status >= 500 else "error"


def plain(value: Any) -> Any:
    """Turn nested error data (dicts, lists, string subclasses) into plain JSON types."""
    if isinstance(value, dict):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [plain(item) for item in value]
    if isinstance(value, bool | int | float) or value is None:
        return value
    return str(value)


def build_error(
    code: str,
    message: str,
    *,
    details: Any = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if details:
        error["details"] = plain(details)
    if request_id:
        error["request_id"] = request_id
    return {"error": error}
