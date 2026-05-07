class AntiBotError(Exception):
    """Raised when an OTH response shows anti-bot signals.

    Triggers: HTTP 403 / 429, or a sentinel string (Cloudflare/Imperva
    challenge text) detected in the response body. Coordination modules
    catch this and call `ScrapeSession.rotate()` to recycle the browser.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        sentinel: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.sentinel = sentinel
