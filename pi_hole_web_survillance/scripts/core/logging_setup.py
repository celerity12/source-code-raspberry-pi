"""
Centralised logging configuration for all Pi-hole Analytics services.

Usage:
    from scripts.core.logging_setup import get_logger

    log = get_logger(__name__, log_file=BASE_DIR / 'logs' / 'fetcher.log')
    log.info("Started")

All loggers share the same format and write to both stdout and (optionally)
a rotating file.  RotatingFileHandler caps each log at 5 MB with 3 backups,
preventing unbounded disk growth on long-running installs.
"""
import logging
from pathlib import Path


_FMT = logging.Formatter(
    fmt='%(asctime)s  %(levelname)-8s  %(name)s  %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)


def get_logger(
    name: str,
    log_file: Path | str | None = None,
    level: str = 'INFO',
) -> logging.Logger:
    """Return a named logger with consistent format and optional file output.

    Calling this function multiple times with the same *name* is safe — Python's
    logging system returns the same Logger instance and this function adds
    handlers only if none are already attached.

    Args:
        name:     Logger name, typically __name__ of the calling module.
        log_file: Optional path to a rotating log file.  The parent directory
                  is created automatically if it does not exist.
        level:    Log level string ('DEBUG', 'INFO', 'WARNING', 'ERROR').

    Returns:
        Configured logging.Logger instance.
    """
    logger = logging.getLogger(name)

    # Guard: don't add duplicate handlers on re-import or repeated calls
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # ── Console handler ───────────────────────────────────────────────────────
    ch = logging.StreamHandler()
    ch.setFormatter(_FMT)
    logger.addHandler(ch)

    # ── Rotating file handler (optional) ─────────────────────────────────────
    if log_file is not None:
        p = Path(log_file)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            # Use RotatingFileHandler for production; fall back to plain FileHandler
            # if the logging module is in a patched/test state.
            try:
                import logging.handlers as _lh
                fh = _lh.RotatingFileHandler(
                    p, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8',
                )
            except (TypeError, AttributeError):
                fh = logging.FileHandler(p, encoding='utf-8')
            fh.setFormatter(_FMT)
            logger.addHandler(fh)
        except (OSError, TypeError):
            # No write permission or test environment — skip file logging silently
            pass

    return logger
