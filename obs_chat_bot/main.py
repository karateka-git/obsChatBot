from __future__ import annotations

import argparse
import logging
import tempfile
from pathlib import Path

from . import __version__
from .config import ConfigError, load_config


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="obs-chat-bot")
    parser.add_argument(
        "--healthcheck",
        action="store_true",
        help="Validate configuration and writable data directory, then exit.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging()
    logger = logging.getLogger("obs_chat_bot")

    logger.info("Starting obsChatBot %s", __version__)

    try:
        config = load_config()
    except ConfigError as error:
        logger.error("Configuration error: %s", error)
        return 2

    config.data_dir.mkdir(parents=True, exist_ok=True)

    if args.healthcheck:
        return run_healthcheck(config.data_dir, logger)

    for key, value in config.safe_summary().items():
        logger.info("Config %s: %s", key, value)

    logger.info("Data directory: %s", config.data_dir.resolve())
    logger.info("Configuration is ready")

    return 0


def run_healthcheck(data_dir: Path, logger: logging.Logger) -> int:
    try:
        with tempfile.NamedTemporaryFile(dir=data_dir, prefix="health-", delete=True):
            pass
    except OSError as error:
        logger.error("Health check failed: data directory is not writable: %s", error)
        return 1

    logger.info("Health check passed")
    return 0
