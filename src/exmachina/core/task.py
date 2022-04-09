from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class TaskManager:
    emit_tasks: dict[str, asyncio.Task] = field(default_factory=dict)
