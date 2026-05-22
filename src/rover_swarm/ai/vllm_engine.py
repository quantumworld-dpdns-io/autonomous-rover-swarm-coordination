from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from rover_swarm.ai.base import InferenceConfig, InferenceEngine
from rover_swarm.config import settings


class VllmEngine(InferenceEngine):
    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        self.host = host or settings.ai.vllm.host
        self.port = port or settings.ai.vllm.port
        self._base_url = f"http://{self.host}:{self.port}"
        self._client: httpx.AsyncClient | None = None
        self._current_model: str | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self._base_url, timeout=120.0)
        return self._client

    async def load_model(self, model_name: str) -> None:
        logger.info("Loading model {} via vLLM", model_name)
        self._current_model = model_name

    async def unload_model(self) -> None:
        logger.info("Unloading model {}", self._current_model)
        self._current_model = None

    async def health(self) -> bool:
        try:
            client = await self._get_client()
            resp = await client.get("/health")
            return resp.status_code == 200
        except httpx.HTTPError as e:
            logger.warning("vLLM health check failed: {}", e)
            return False

    async def stats(self) -> dict[str, Any]:
        try:
            client = await self._get_client()
            resp = await client.get("/stats")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("Failed to get vLLM stats: {}", e)
            return {}

    async def infer(self, prompt: str, config: InferenceConfig | None = None) -> str:
        cfg = config or InferenceConfig()
        model = self._current_model or cfg.model_name
        client = await self._get_client()

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens,
            "top_p": cfg.top_p,
            "frequency_penalty": cfg.frequency_penalty,
            "presence_penalty": cfg.presence_penalty,
            "seed": cfg.seed,
        }
        if cfg.stop:
            payload["stop"] = cfg.stop

        try:
            resp = await client.post("/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return ""
        except httpx.HTTPError as e:
            logger.error("vLLM inference failed: {}", e)
            raise

    async def embed(self, text: str) -> list[float]:
        client = await self._get_client()
        model = self._current_model or ""

        payload = {
            "model": model,
            "input": text,
        }

        try:
            resp = await client.post("/v1/embeddings", json=payload)
            resp.raise_for_status()
            data = resp.json()
            emb_data = data.get("data", [])
            if emb_data:
                return emb_data[0].get("embedding", [])
            return []
        except httpx.HTTPError as e:
            logger.error("vLLM embedding failed: {}", e)
            raise

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
