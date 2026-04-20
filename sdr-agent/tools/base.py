"""Shared utilities for all tool wrappers."""
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

log = structlog.get_logger()


class ToolError(Exception):
    """Raised when an external tool call fails unrecoverably."""
    pass


def is_retryable(exc: Exception) -> bool:
    """Retry on rate limits and server errors only."""
    import httpx
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503, 504)
    return isinstance(exc, httpx.TimeoutException)


retry_policy = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception(is_retryable),
    reraise=True,
)
