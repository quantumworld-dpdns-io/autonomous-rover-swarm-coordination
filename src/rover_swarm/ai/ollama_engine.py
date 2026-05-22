from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from rover_swarm.ai.base import InferenceConfig, InferenceEngine
from rover_swarm.config import settings


class OllamaEngine(InferenceEngine):
    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        self.host = host or settings.ai.ollama.host
        self.port = port or settings.ai.ollama.port
        self._base_url = f"http://{self.host}:{self.port}"
        self._client: httpx.AsyncClient | None = None
        self._current_model: str | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self._base_url, timeout=60.0)
        return self._client

    async def health(self) -> bool:
        try:
            client = await self._get_client()
            resp = await client.get("/api/tags")
            return resp.status_code == 200
        except httpx.HTTPError as e:
            logger.warning("Ollama health check failed: {}", e)
            return False

    async def load_model(self, model_name: str) -> None:
        logger.info("Loading model {} via Ollama", model_name)
        self._current_model = model_name

    async def unload_model(self) -> None:
        logger.info("Unloading model {}", self._current_model)
        self._current_model = None

    async def infer(self, prompt: str, config: InferenceConfig | None = None) -> str:
        cfg = config or InferenceConfig()
        model = self._current_model or cfg.model_name
        client = await self._get_client()

        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "options": {
                "temperature": cfg.temperature,
                "num_predict": cfg.max_tokens,
                "top_p": cfg.top_p,
                "frequency_penalty": cfg.frequency_penalty,
                "presence_penalty": cfg.presence_penalty,
                "seed": cfg.seed,
            },
        }
        if cfg.stop:
            payload["options"]["stop"] = cfg.stop

        try:
            resp = await client.post("/api/generate", json=payload)
            resp.raise_for_status()
            lines = resp.text.strip().split("\n")
            result = "".join(
                line for line in lines
            )
            return result
        except httpx.HTTPError as e:
            logger.error("Ollama inference failed: {}", e)
            raise

    async def embed(self, text: str) -> list[float]:
        client = await self._get_client()
        model = self._current_model or "nomic-embed-text"

        payload = {
            "model": model,
            "prompt": text,
        }

        try:
            resp = await client.post("/api/embeddings", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("embedding", [])
        except httpx.HTTPError as e:
            logger.error("Ollama embedding failed: {}", e)
            raise

    async def list_models(self) -> list[dict[str, Any]]:
        client = await self._get_client()
        try:
            resp = await client.get("/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return data.get("models", [])
        except httpx.HTTPError as e:
            logger.error("Failed to list Ollama models: {}", e)
            return []

    async def pull_model(self, model_name: str) -> None:
        client = await self._get_client()
        payload = {"name": model_name}
        try:
            resp = await client.post("/api/pull", json=payload)
            resp.raise_for_status()
            self._current_model = model_name
            logger.info("Pulled model {} via Ollama", model_name)
        except httpx.HTTPError as e:
            logger.error("Failed to pull model {}: {}", model_name, e)
            raise

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
