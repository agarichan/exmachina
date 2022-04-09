import logging

import pytest

from exmachina.core.helper import set_verbose


@pytest.mark.parametrize(
    "verbose, level", [("DEBUG", 10), ("INFO", 20), ("WARNING", 30), ("ERROR", 40), ("CRITICAL", 50)]
)
def test_set_verbose(verbose: str, level: int):
    set_verbose(verbose)

    exmachina = logging.getLogger("exmachina")

    assert exmachina.level == level
