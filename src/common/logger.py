"""
Unified logging configuration for application-wide debugging and diagnostics.
"""

import logging
import sys
from typing import Optional


def setup_logger(
    name: str = "DAPLinkSuite", level: int = logging.INFO
) -> logging.Logger:
    """
    Configures and returns a singleton logger instance with formatted console output.
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.setLevel(level)
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%H:%M:%S",
        )

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


def get_logger(module_name: Optional[str] = None) -> logging.Logger:
    """
    Retrieves a logger instance scoped to the requesting feature module.
    """
    base_name = "DAPLinkSuite"
    if module_name:
        return logging.getLogger(f"{base_name}.{module_name}")
    return logging.getLogger(base_name)
