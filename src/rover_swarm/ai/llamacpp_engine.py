from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from rover_swarm.ai.base import InferenceConfig, InferenceEngine
from rover_swarm.config import settings


class LlamacppEngine(InferenceEngine):
    def __init__(self, model_path: str | Path | None = None) -> None:
        self.model_path = Path(model_path or settings.ai.llamacpp.model_path)
        self._model: Any = None
        self._current_model: str | None = None

    async def load_model(self, model_name: str) -> None:
        path = self.model_path / model_name if self.model_path.is_dir() else self.model_path
        logger.info("Loading GGUF model from {}", path)

        try:
            from llama_cpp import Llama
        except ImportError:
            logger.error("llama-cpp-python is not installed")
            raise ImportError(
                "llama-cpp-python is required for LlamacppEngine. "
                "Install with: pip install llama-cpp-python"
            )

        self._model = Llama(
            model_path=str(path),
            n_ctx=4096,
            n_threads=4,
            verbose=False,
        )
        self._current_model = str(path)
        logger.info("GGUF model loaded from {}", path)

    async def unload_model(self) -> None:
        logger.info("Unloading GGUF model {}", self._current_model)
        if self._model is not None:
            self._model.close()
            self._model = None
        self._current_model = None

    async def infer(self, prompt: str, config: InferenceConfig | None = None) -> str:
        if self._model is None:
            msg = "No model loaded; call load_model() first"
            raise RuntimeError(msg)

        cfg = config or InferenceConfig()

        try:
            response = self._model(
                prompt=prompt,
                max_tokens=cfg.max_tokens,
                temperature=cfg.temperature,
                top_p=cfg.top_p,
                frequency_penalty=cfg.frequency_penalty,
                presence_penalty=cfg.presence_penalty,
                stop=cfg.stop or [],
                seed=cfg.seed,
            )
            choices = response.get("choices", [])
            if choices:
                return choices[0].get("text", "")
            return ""
        except Exception as e:
            logger.error("llama.cpp inference failed: {}", e)
            raise

    async def embed(self, text: str) -> list[float]:
        if self._model is None:
            msg = "No model loaded; call load_model() first"
            raise RuntimeError(msg)

        try:
            embeddings = self._model.embed(text)
            if isinstance(embeddings, list) and len(embeddings) > 0:
                if isinstance(embeddings[0], list):
                    return embeddings[0]
                return embeddings
            return []
        except Exception as e:
            logger.error("llama.cpp embedding failed: {}", e)
            raise

    async def close(self) -> None:
        await self.unload_model()
