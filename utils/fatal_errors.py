import logging

FATAL_ERROR_MARKERS = (
    "authenticat",
    "unauthorized",
    "invalid api key",
    "invalid api-key",
    "permission denied",
    "403",
    "401",
    "database disk image is malformed",
    "disk i/o error",
    "no space left on device",
)


def is_fatal(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(marker in msg for marker in FATAL_ERROR_MARKERS)


def handle_symbol_error(exc: Exception, label: str) -> None:
    """Log-and-continue for ordinary errors; re-raise fatal ones."""
    if is_fatal(exc):
        logging.critical(f"{label}: FATAL error, stopping bot: {exc}")
        print(f"FATAL {label}: {exc} - bot is stopping, this needs attention")
        raise exc
    logging.error(f"{label}: {exc}")
    print(f"ERROR {label}: {exc}")
