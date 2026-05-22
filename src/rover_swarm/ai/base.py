from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class InferenceConfig:
    model_name: str = "default"
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 0.9
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stop: list[str] | None = None
    seed: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class InferenceEngine(ABC):
    @abstractmethod
    async def load_model(self, model_name: str) -> None:
        ...

    @abstractmethod
    async def unload_model(self) -> None:
        ...

    @abstractmethod
    async def infer(self, prompt: str, config: InferenceConfig | None = None) -> str:
        ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        ...
