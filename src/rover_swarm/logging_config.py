from __future__ import annotations

import logging
import sys
from pathlib import Path

from loguru import logger

from rover_swarm.config import LogLevel, settings


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.Record) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def configure_logging(
    level: LogLevel = settings.log_level,
    json_output: bool = False,
    log_file: Path | None = None,
) -> None:
    logger.remove()

    log_format = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<7} | {name}:{function}:{line} | {message}"
    )
    if json_output:
        log_format = "{extra[serialized]}"

    logger.add(
        sys.stdout,
        format=log_format,
        level=level.value,
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            str(log_file),
            format=log_format,
            level=level.value,
            rotation="100 MB",
            retention="30 days",
            compression="gz",
        )

    logging.basicConfig(handlers=[InterceptHandler()], level=logging.INFO, force=True)
    for lib_logger in ("uvicorn", "fastapi", "httpx", "aiohttp", "grpc"):
        logging.getLogger(lib_logger).handlers = [InterceptHandler()]
        logging.getLogger(lib_logger).propagate = False

    logger.info("Logging configured", level=level.value, json_output=json_output, log_file=log_file)
