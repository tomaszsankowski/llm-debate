"""Wspólne błędy dostawców i odczyt czasu ponowienia żądania."""

import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


class ProviderError(Exception):
    def __init__(self, code: str, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_after = retry_after

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "retry_after": self.retry_after}


def retry_delay(headers) -> float | None:
    raw = headers.get("retry-after", "")
    try:
        seconds = float(raw)
        if math.isfinite(seconds):
            return max(0, seconds)
    except ValueError:
        pass
    try:
        deadline = parsedate_to_datetime(raw)
        return max(0, (deadline - datetime.now(timezone.utc)).total_seconds())
    except (ValueError, TypeError, OverflowError):
        return None
