class ParseError(Exception):
    """Raised when an OTH response cannot be parsed into typed objects.

    Coordination modules should treat ParseError as a dead-letter signal — the
    payload shape changed, retrying won't help, a human needs to look.
    """
