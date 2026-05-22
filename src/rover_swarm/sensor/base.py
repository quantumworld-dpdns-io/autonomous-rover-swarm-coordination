from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from rover_swarm.exceptions import SensorCalibrationError, SensorReadError
from rover_swarm.types import Metadata, RoverId, SensorReading, SensorType


@dataclass
class CalibrationResult:
    success: bool
    offset: float = 0.0
    scale: float = 1.0
    details: Metadata = field(default_factory=dict)


class Sensor(ABC):
    """Abstract base for all sensor types."""

    def __init__(
        self,
        name: str,
        sensor_type: SensorType,
        rover_id: RoverId,
        frequency: float = 10.0,
    ) -> None:
        self._name = name
        self._sensor_type = sensor_type
        self._rover_id = rover_id
        self._frequency = frequency
        self._calibrated = False
        self._calibration: CalibrationResult | None = None
        logger.debug(
            "Sensor initialized",
            name=name,
            sensor_type=sensor_type.value,
            rover_id=rover_id,
            frequency=frequency,
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def sensor_type(self) -> SensorType:
        return self._sensor_type

    @property
    def frequency(self) -> float:
        return self._frequency

    @frequency.setter
    def frequency(self, value: float) -> None:
        if value <= 0:
            raise ValueError(f"Frequency must be positive, got {value}")
        self._frequency = value

    @property
    def is_calibrated(self) -> bool:
        return self._calibrated

    @abstractmethod
    def read(self) -> SensorReading:
        """Take a single sensor reading."""

    def calibrate(self) -> CalibrationResult:
        """Run sensor calibration routine."""
        logger.info("Calibrating sensor", name=self._name)
        try:
            result = self._do_calibrate()
            self._calibrated = result.success
            self._calibration = result
            if result.success:
                logger.info(
                    "Calibration successful",
                    name=self._name,
                    offset=result.offset,
                    scale=result.scale,
                )
            else:
                logger.warning("Calibration failed", name=self._name)
            return result
        except Exception as exc:
            raise SensorCalibrationError(
                f"Calibration failed for {self._name}: {exc}"
            ) from exc

    def _do_calibrate(self) -> CalibrationResult:
        """Override in subclasses for custom calibration logic."""
        return CalibrationResult(success=True)

    def health_check(self) -> bool:
        """Check if the sensor is operational."""
        try:
            self.read()
            return True
        except SensorReadError:
            return False
        except Exception:
            logger.exception("Unexpected health check failure", name=self._name)
            return False
