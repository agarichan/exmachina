from __future__ import annotations

import logging

try:
    from typing import Literal  # type: ignore
except ImportError:
    from typing_extensions import Literal


def set_verbose(
    logger: logging.Logger | None = None,
    verbose: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None = None,
):
    """exmachinaのログを表示する

    Args:
        verbose (Literal[): 10, 20, 30, 40, 50に相当
    """
    try:
        from rich.logging import RichHandler
    except ModuleNotFoundError:
        raise ImportError("pip install exmachina[rich]")

    if verbose is not None:
        handler = RichHandler(rich_tracebacks=True, enable_link_path=False, level=verbose)
        if logger is None:
            logger = logging.getLogger("exmachina")
        logger.setLevel(verbose)
        if "RichHandler" not in [h.__class__.__name__ for h in logger.handlers]:
            logger.addHandler(handler)
