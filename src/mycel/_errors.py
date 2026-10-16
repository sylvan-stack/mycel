"""The closed command failure vocabulary."""

from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_INPUT = "invalid_input"
    IO = "io"
    SETTINGS = "settings"
    UNKNOWN_REPOSITORY = "unknown_repository"
    STORE_UNAVAILABLE = "store_unavailable"
    STORE_FORMAT = "store_format"
    BUSY = "busy"
    REFUSED = "refused"
    INTERNAL = "internal"


class MycelError(Exception):
    def __init__(self, code: ErrorCode | str, message: str):
        self.code = ErrorCode(code)
        self.message = message
        super().__init__(message)

    def to_dict(self) -> dict:
        return {"error": {"code": self.code.value, "message": self.message}}
