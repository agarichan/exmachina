from __future__ import annotations

import logging

try:
    from typing import Literal  # type: ignore
except ImportError:
    from typing_extensions import Literal

from rich.logging import RichHandler


def set_verbose(verbose: Literal["NOTEST", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None):
    """exmachinaのログを表示する

    Args:
        verbose (Literal[): 0, 10, 20, 30, 40, 50に相当
    """
    if verbose is not None:
        logging.basicConfig(level=verbose)
        handler = RichHandler(rich_tracebacks=True, enable_link_path=False, level=verbose)
        logger = logging.getLogger("exmachina")
        if "RichHandler" not in [h.__class__.__name__ for h in logger.handlers]:
            logger.addHandler(handler)
