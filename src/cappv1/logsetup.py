"""Run logging: a colored console view and a per-run log file."""

import logging
import sys
import time
from pathlib import Path

logger = logging.getLogger("pptx_alt_text")

_RESET, _BOLD, _DIM = "\033[0m", "\033[1m", "\033[2m"
_RED, _GREEN, _YELLOW, _CYAN, _GRAY = (
    "\033[31m",
    "\033[32m",
    "\033[33m",
    "\033[36m",
    "\033[90m",
)
_LEVEL_COLOR = {logging.INFO: _CYAN, logging.WARNING: _YELLOW, logging.ERROR: _RED}


class ColorFormatter(logging.Formatter):
    """Colorizes by log level, with a couple of message-aware overrides so
    completions and skips stand out at a glance."""

    def __init__(self, fmt: str, datefmt: str, use_color: bool) -> None:
        super().__init__(fmt, datefmt)
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        if not self.use_color:
            return line
        msg = record.getMessage().lower()
        if "saved to" in msg:
            return f"{_BOLD}{_GREEN}✓ {line}{_RESET}"
        if "already complete, skipping" in msg or "nothing to process" in msg:
            return f"{_GRAY}{line}{_RESET}"
        color = _LEVEL_COLOR.get(record.levelno, "")
        return f"{color}{line}{_RESET}" if color else line


def setup_logging(logs_dir: Path, console: bool = True) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"run-{time.strftime('%Y%m%d-%H%M%S')}.log"
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = not console  # with its own console handler, the root logger would print every line twice

    fmt = "%(asctime)s %(levelname)s %(message)s"
    datefmt = "%H:%M:%S"

    # stdout is colored only when it's a real terminal - stays plain when
    # captured by nohup so the fallback launcher log has no escape codes.
    if console:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(ColorFormatter(fmt, datefmt, use_color=sys.stdout.isatty()))
        logger.addHandler(stream_handler)

    # the persisted per-run log is always colored - it's meant to be tailed
    # live in a terminal, not opened in a plain-text editor.
    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(ColorFormatter(fmt, datefmt, use_color=True))
    logger.addHandler(file_handler)
