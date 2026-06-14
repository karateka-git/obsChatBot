from __future__ import annotations

import logging
from pathlib import Path

from . import __version__


DATA_DIR = Path("data")


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> int:
    configure_logging()
    logger = logging.getLogger("obs_chat_bot")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Starting obsChatBot %s", __version__)
    logger.info("Data directory: %s", DATA_DIR.resolve())
    logger.info("Minimal Python project structure is ready")

    return 0

