from __future__ import annotations

from typing import Any, Callable


class Depends:
    def __init__(self, dependency: Callable[..., Any], *, use_cache: bool = True):
        self.dependency = dependency
        self.use_cache = use_cache

    def __repr__(self) -> str:
        attr = getattr(self.dependency, "__name__", type(self.dependency).__name__)
        cache = "" if self.use_cache else ", use_cache=False"
        return f"{self.__class__.__name__}({attr}{cache})"
