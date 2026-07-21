class InvalidModelOutputError(RuntimeError):
    """Raised after the one allowed structured-output repair also fails."""

    code = "INVALID_MODEL_OUTPUT"
