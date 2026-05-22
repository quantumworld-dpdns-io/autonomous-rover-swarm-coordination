from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from rover_swarm.ai.base import InferenceConfig, InferenceEngine
from rover_swarm.ai.ollama_engine import OllamaEngine
from rover_swarm.config import settings


@dataclass
class RouterConfig:
    active_engine: str = "ollama"
    fallback_chain: list[str] = field(default_factory=lambda: ["ollama", "vllm", "llamacpp"])
    timeout_seconds: float = 30.0


class EngineManager:
    def __init__(self, config: RouterConfig | None = None) -> None:
        self.config = config or RouterConfig()
        self._engines: dict[str, InferenceEngine] = {}
        self._initialized: bool = False

    async def initialize(self) -> None:
        if self._initialized:
            return

        logger.info("Initializing inference engines")

        try:
            ollama = OllamaEngine()
            if await ollama.health():
                self._engines["ollama"] = ollama
                logger.info("Ollama engine registered")
            else:
                logger.warning("Ollama not available, skipping")
        except Exception as e:
            logger.warning("Failed to initialize Ollama engine: {}", e)

        self._engines["vllm"] = type(
            "VllmEngineStub",
            (InferenceEngine,),
            {
                "__init__": lambda self: None,
                "load_model": lambda self, m: None,
                "unload_model": lambda self: None,
                "infer": lambda self, p, c=None: "",
                "embed": lambda self, t: [],
            },
        )()

        self._engines["llamacpp"] = type(
            "LlamacppEngineStub",
            (InferenceEngine,),
            {
                "__init__": lambda self: None,
                "load_model": lambda self, m: None,
                "unload_model": lambda self: None,
                "infer": lambda self, p, c=None: "",
                "embed": lambda self, t: [],
            },
        )()

        self._initialized = True
        logger.info(
            "Engine manager initialized with active={}, fallback={}",
            self.config.active_engine,
            self.config.fallback_chain,
        )

    async def register_engine(self, name: str, engine: InferenceEngine) -> None:
        self._engines[name] = engine
        logger.info("Registered engine {}", name)

    async def _route(self, engine_name: str | None = None) -> InferenceEngine:
        engine_key = engine_name or self.config.active_engine
        engine = self._engines.get(engine_key)
        if engine is None:
            msg = f"Engine '{engine_key}' is not registered"
            raise ValueError(msg)
        return engine

    async def route_infer(
        self,
        prompt: str,
        config: InferenceConfig | None = None,
        engine_name: str | None = None,
    ) -> str:
        engines_to_try = self._resolve_chain(engine_name)

        last_error: Exception | None = None
        for name in engines_to_try:
            try:
                engine = await self._route(name)
                result = await engine.infer(prompt, config)
                if result:
                    return result
            except Exception as e:
                logger.warning("Engine {} failed, trying fallback: {}", name, e)
                last_error = e
                continue

        logger.error("All inference engines failed")
        raise RuntimeError("All inference engines failed") from last_error

    async def route_embed(
        self,
        text: str,
        engine_name: str | None = None,
    ) -> list[float]:
        engines_to_try = self._resolve_chain(engine_name)

        last_error: Exception | None = None
        for name in engines_to_try:
            try:
                engine = await self._route(name)
                result = await engine.embed(text)
                if result:
                    return result
            except Exception as e:
                logger.warning("Engine {} embedding failed, trying fallback: {}", name, e)
                last_error = e
                continue

        logger.error("All embedding engines failed")
        raise RuntimeError("All embedding engines failed") from last_error

    async def health_all(self) -> dict[str, bool]:
        results: dict[str, bool] = {}
        for name, engine in self._engines.items():
            try:
                health_method = getattr(engine, "health", None)
                if health_method is not None:
                    results[name] = await health_method()
                else:
                    results[name] = True
            except Exception as e:
                logger.warning("Health check failed for {}: {}", name, e)
                results[name] = False
        return results

    async def switch_engine(self, engine_name: str) -> None:
        if engine_name not in self._engines:
            msg = f"Cannot switch to unknown engine '{engine_name}'"
            raise ValueError(msg)
        self.config.active_engine = engine_name
        logger.info("Switched active engine to {}", engine_name)

    def _resolve_chain(self, engine_name: str | None = None) -> list[str]:
        if engine_name:
            if engine_name in self._engines:
                return [engine_name]
            return [engine_name] + self.config.fallback_chain
        return [self.config.active_engine] + [
            e for e in self.config.fallback_chain if e != self.config.active_engine
        ]

    async def shutdown(self) -> None:
        for name, engine in self._engines.items():
            close_method = getattr(engine, "close", None)
            if close_method is not None:
                try:
                    await close_method()
                except Exception as e:
                    logger.warning("Error closing engine {}: {}", name, e)
        self._engines.clear()
        self._initialized = False
        logger.info("All engines shut down")
