"""Typed errors for provider failures, so callers (API layer, CLI) can map
each to a distinct, clean message instead of a raw provider exception.
"""


class LLMAuthError(RuntimeError):
    pass


class LLMRateLimitError(RuntimeError):
    pass


class LLMConnectionError(RuntimeError):
    pass
