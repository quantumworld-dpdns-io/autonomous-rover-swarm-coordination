from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger

try:
    import weave

    _WEAVE_AVAILABLE = True
except ImportError:
    _WEAVE_AVAILABLE = False


@dataclass
class EvaluationResult:
    """Dataclass for evaluation scores."""

    scores: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    target: str = ""
    prediction: str = ""

    def avg_score(self) -> float:
        if not self.scores:
            return 0.0
        return sum(self.scores.values()) / len(self.scores)


class WeaveEvaluator:
    """W&B Weave integration for LLM/swarm evaluation."""

    def __init__(self, project_name: str = "rover-swarm-eval") -> None:
        self._project = project_name
        self._initialized = False

        if _WEAVE_AVAILABLE:
            try:
                weave.init(project_name)
                self._initialized = True
                logger.info("Weave initialised for project {}", project_name)
            except Exception:
                logger.exception("Failed to initialise Weave")
        else:
            logger.warning("weave not installed; evaluation logging disabled")

    def log_prompt(
        self,
        prompt: str,
        model: str = "",
        temperature: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        if not self._initialized or not _WEAVE_AVAILABLE:
            return None

        try:
            call = weave.trace_call(
                "prompt",
                inputs={
                    "prompt": prompt,
                    "model": model,
                    "temperature": temperature,
                    **(metadata or {}),
                },
            )
            logger.debug("Logged prompt to Weave", prompt=prompt[:50])
            return call.id if hasattr(call, "id") else None
        except Exception:
            logger.exception("Failed to log prompt to Weave")
            return None

    def log_response(
        self,
        response: str,
        prompt_id: str | None = None,
        latency_ms: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        if not self._initialized or not _WEAVE_AVAILABLE:
            return None

        try:
            call = weave.trace_call(
                "response",
                inputs={
                    "response": response,
                    "prompt_id": prompt_id or "",
                    "latency_ms": latency_ms,
                    **(metadata or {}),
                },
            )
            logger.debug("Logged response to Weave", response_len=len(response))
            return call.id if hasattr(call, "id") else None
        except Exception:
            logger.exception("Failed to log response to Weave")
            return None

    def create_dataset(
        self,
        name: str,
        rows: list[dict[str, Any]],
    ) -> bool:
        if not self._initialized or not _WEAVE_AVAILABLE:
            return False

        try:
            dataset = weave.Dataset(name=name, rows=rows)
            weave.publish(dataset)
            logger.info("Published Weave dataset '{}' with {} rows", name, len(rows))
            return True
        except Exception:
            logger.exception("Failed to create Weave dataset '{}'", name)
            return False

    def run_evaluation(
        self,
        evaluator_name: str,
        dataset_name: str,
        scoring_fn: Any = None,
        model_output_fn: Any = None,
    ) -> EvaluationResult:
        """Run an evaluation using a Weave dataset and optional scoring function."""
        if not self._initialized or not _WEAVE_AVAILABLE:
            return EvaluationResult(metadata={"error": "Weave not initialised"})

        try:
            dataset = weave.ref(dataset_name).get()
        except Exception:
            logger.exception("Failed to load dataset '{}'", dataset_name)
            return EvaluationResult(metadata={"error": f"Dataset '{dataset_name}' not found"})

        scores: dict[str, float] = {}
        total = len(dataset.rows) if hasattr(dataset, "rows") else 0
        correct = 0

        for i, row in enumerate(dataset.rows if hasattr(dataset, "rows") else []):
            target = row.get("target", "")
            if scoring_fn:
                try:
                    prediction = model_output_fn(row) if model_output_fn else row.get("prediction", "")
                    score = scoring_fn(target=target, prediction=prediction)
                    if isinstance(score, dict):
                        for k, v in score.items():
                            scores[f"row_{i}_{k}"] = float(v)
                    else:
                        scores[f"row_{i}"] = float(score)
                    if isinstance(score, (int, float)) and score > 0.5:
                        correct += 1
                except Exception:
                    logger.exception("Scoring failed for row {}", i)

        accuracy = correct / total if total > 0 else 0.0
        result = EvaluationResult(
            scores={"accuracy": accuracy, **scores},
            metadata={
                "evaluator": evaluator_name,
                "dataset": dataset_name,
                "total_rows": total,
            },
        )
        logger.info(
            "Evaluation '{}' complete: accuracy={:.3f}",
            evaluator_name,
            accuracy,
        )
        return result

    def shutdown(self) -> None:
        if _WEAVE_AVAILABLE and self._initialized:
            try:
                weave.finish()
                logger.info("Weave finished")
            except Exception:
                logger.exception("Error shutting down Weave")
