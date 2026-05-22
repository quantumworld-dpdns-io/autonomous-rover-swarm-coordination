from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from rover_swarm.ai.base import InferenceConfig, InferenceEngine
from rover_swarm.config import settings


class SglangEngine(InferenceEngine):
    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        self.host = host or settings.ai.sglang_host
        self.port = port or settings.ai.sglang_port
        self._base_url = f"http://{self.host}:{self.port}"
        self._client: httpx.AsyncClient | None = None
        self._current_model: str | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self._base_url, timeout=120.0)
        return self._client

    async def load_model(self, model_name: str) -> None:
        logger.info("Loading model {} via SGLang", model_name)
        self._current_model = model_name

    async def unload_model(self) -> None:
        logger.info("Unloading model {}", self._current_model)
        self._current_model = None

    async def infer(self, prompt: str, config: InferenceConfig | None = None) -> str:
        cfg = config or InferenceConfig()
        client = await self._get_client()

        payload = {
            "model": self._current_model or cfg.model_name,
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
            logger.error("SGLang inference failed: {}", e)
            raise

    async def generate_structured(
        self,
        prompt: str,
        json_schema: dict[str, Any],
        config: InferenceConfig | None = None,
    ) -> dict[str, Any]:
        cfg = config or InferenceConfig()
        client = await self._get_client()

        payload: dict[str, Any] = {
            "model": self._current_model or cfg.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens,
            "top_p": cfg.top_p,
            "response_format": {
                "type": "json_object",
                "schema": json_schema,
            },
        }
        if cfg.stop:
            payload["stop"] = cfg.stop

        try:
            resp = await client.post("/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "{}")
                import json
                return json.loads(content)
            return {}
        except httpx.HTTPError as e:
            logger.error("SGLang structured generation failed: {}", e)
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
            logger.error("SGLang embedding failed: {}", e)
            raise

    async def health(self) -> bool:
        try:
            client = await self._get_client()
            resp = await client.get("/health")
            return resp.status_code == 200
        except httpx.HTTPError as e:
            logger.warning("SGLang health check failed: {}", e)
            return False

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
