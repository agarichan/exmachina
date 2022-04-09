from __future__ import annotations

from typing import Any, Callable

from . import params


def Depends(dependency: Callable[..., Any], *, use_cache: bool = True) -> Any:  # noqa: N802
    return params.Depends(dependency=dependency, use_cache=use_cache)
