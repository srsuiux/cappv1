class ServiceError(Exception):
    """A failure with a plain-language message and, where there is one, the fix."""

    def __init__(self, code: str, message: str, fix: str = "") -> None:
        super().__init__(message)
        self.code, self.message, self.fix = code, message, fix

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "fix": self.fix}
