"""Logging setup for the scheduled entry points.

The bi-daily orchestrator and the Spotify logger run headless under Task Scheduler,
so a bare `print()` vanishes. `setup_logging(name)` attaches a console handler plus
a rotating file handler at `data/logs/<name>.log` (gitignored) so each run leaves a
durable, size-capped trail you can inspect later.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

_FORMAT = "%(asctime)s %(levelname)s %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(name: str = "ttspotslideshow", level: int = logging.INFO,
                  log_dir: Optional[Path] = None) -> logging.Logger:
    """Configure and return a named logger with console + rotating-file output.

    Idempotent: calling it again for the same name won't stack duplicate handlers.
    """
    log_dir = Path(log_dir) if log_dir else (Path("data") / "logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    if any(getattr(h, "_ttspot", False) for h in logger.handlers):
        return logger  # already configured

    fmt = logging.Formatter(_FORMAT, _DATEFMT)
    file_handler = RotatingFileHandler(
        log_dir / f"{name}.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    file_handler._ttspot = True

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console._ttspot = True

    logger.addHandler(file_handler)
    logger.addHandler(console)
    return logger
