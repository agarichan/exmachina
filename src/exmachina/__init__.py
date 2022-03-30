__version__ = "0.0.0"

import logging

logging.getLogger(__name__).addHandler(logging.NullHandler())
logging.getLogger(__name__).propagate = False

# from .core.machina import Event, Machina  # noqa
from .core.params_function import Depends  # noqa
