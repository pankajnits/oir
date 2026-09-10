"""Errors for the app-side layer."""

__all__ = ["LeakError"]


class LeakError(RuntimeError):
    """A watched name string would have appeared in the packed payload."""

    def __init__(self, names: list[str]):
        self.names = names
        super().__init__(f"refusing to send watched plaintext to the LLM: {names}")
