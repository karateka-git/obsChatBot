"""Валидируемая политика размеров универсального chunk assembler."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


@dataclass(frozen=True, slots=True)
class ChunkingPolicy:
    """Задаёт мягкие и жёсткие границы размера chunks в символах."""

    minimum_size_chars: int = 300
    target_size_chars: int = 3000
    maximum_size_chars: int = 6000

    def __post_init__(self) -> None:
        if self.minimum_size_chars <= 0:
            raise ValueError("minimum_size_chars must be positive")
        if self.target_size_chars < self.minimum_size_chars:
            raise ValueError(
                "target_size_chars must not be less than minimum_size_chars"
            )
        if self.maximum_size_chars < self.target_size_chars:
            raise ValueError(
                "maximum_size_chars must not be less than target_size_chars"
            )

    @property
    def signature(self) -> str:
        """Возвращает стабильный hash фактических параметров policy."""
        payload = json.dumps(
            {
                "maximum_size_chars": self.maximum_size_chars,
                "minimum_size_chars": self.minimum_size_chars,
                "target_size_chars": self.target_size_chars,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(payload.encode("utf-8")).hexdigest()
