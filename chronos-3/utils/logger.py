"""Console logging configuration.

Every meaningful event (session start/end, AFK prompts and timeouts,
Pomodoro phase changes, level-ups, reconciliation on startup, and
errors) is logged here with timestamps so you can follow exactly what
the bot is doing from the console alone.
"""
from __future__ import annotations

import logging
import sys

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-16s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class _ColorFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: "\x1b[38;20m",
        logging.INFO: "\x1b[36;20m",
        logging.WARNING: "\x1b[33;20m",
        logging.ERROR: "\x1b[31;20m",
        logging.CRITICAL: "\x1b[31;1m",
    }
    RESET = "\x1b[0m"

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        if not sys.stdout.isatty():
            return formatted
        color = self.COLORS.get(record.levelno, "")
        return f"{color}{formatted}{self.RESET}"


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_ColorFormatter(LOG_FORMAT, DATE_FORMAT))

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    # discord.py's own loggers are chatty at INFO; keep them at WARNING+
    # so the bot's own event log (session starts/ends, etc.) stays readable.
    logging.getLogger("discord.gateway").setLevel(logging.WARNING)
    logging.getLogger("discord.client").setLevel(logging.WARNING)
    logging.getLogger("discord.http").setLevel(logging.WARNING)
