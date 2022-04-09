from __future__ import annotations

import logging

try:
    from typing import Literal  # type: ignore
except ImportError:
    from typing_extensions import Literal

try:
    from rich.logging import RichHandler
except ImportError:
    raise ImportError("pip install exmachina[rich]")


def set_verbose(verbose: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None):
    """exmachinaのログを表示する

    Args:
        verbose (Literal[): 10, 20, 30, 40, 50に相当
    """
    if verbose is not None:
        handler = RichHandler(rich_tracebacks=True, enable_link_path=False, level=verbose)
        logger = logging.getLogger("exmachina")
        logger.setLevel(verbose)
        if "RichHandler" not in [h.__class__.__name__ for h in logger.handlers]:
            logger.addHandler(handler)