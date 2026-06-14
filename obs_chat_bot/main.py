from __future__ import annotations

import logging

from . import __version__
from .config import ConfigError, load_config


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> int:
    configure_logging()
    logger = logging.getLogger("obs_chat_bot")

    logger.info("Starting obsChatBot %s", __version__)

    try:
        config = load_config()
    except ConfigError as error:
        logger.error("Configuration error: %s", error)
        return 2

    config.data_dir.mkdir(parents=True, exist_ok=True)

    for key, value in config.safe_summary().items():
        logger.info("Config %s: %s", key, value)

    logger.info("Data directory: %s", config.data_dir.resolve())
    logger.info("Configuration is ready")

    return 0
