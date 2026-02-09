import logging
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "bot.log"

def setup_logger():
    logger = logging.getLogger("pattern_bot")
    logger.setLevel(logging.INFO)

    fh = logging.FileHandler(LOG_PATH, mode="a")
    fh.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    fh.setFormatter(formatter)

    logger.addHandler(fh)
    return logger
