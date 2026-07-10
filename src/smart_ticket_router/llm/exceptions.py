class LLMAuthError(RuntimeError):
    pass


class LLMRateLimitError(RuntimeError):
    pass


class LLMConnectionError(RuntimeError):
    pass
