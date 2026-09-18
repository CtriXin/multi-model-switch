class WebError(Exception):
    """A deliberately public, secret-free error suitable for the local UI."""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
