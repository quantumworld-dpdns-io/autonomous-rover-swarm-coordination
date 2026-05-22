from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from rover_swarm.types import Orientation, Position


@dataclass
class FusedPosition:
    """Fused position estimate with uncertainty."""

    position: Position
    covariance: list[list[float]]
    velocity: tuple[float, float, float] = (0.0, 0.0, 0.0)
    orientation: Orientation | None = None

    @property
    def uncertainty(self) -> float:
        return (self.covariance[0][0] + self.covariance[1][1] + self.covariance[2][2]) ** 0.5


class SensorFusion:
    """Kalman filter-based fusion of GPS and IMU data."""

    def __init__(
        self,
        dt: float = 0.1,
        process_noise: float = 0.1,
        gps_noise: float = 1.0,
        imu_noise: float = 0.01,
    ) -> None:
        self._dt = dt
        self._process_noise = process_noise
        self._gps_noise = gps_noise
        self._imu_noise = imu_noise

        self._x: list[float] = [0.0, 0.0, 0.0]
        self._v: list[float] = [0.0, 0.0, 0.0]
        self._P: list[list[float]] = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
        self._initialized = False
        self._update_count = 0
        self._orientation: Orientation | None = None

        logger.debug(
            "SensorFusion initialized",
            dt=dt,
            process_noise=process_noise,
            gps_noise=gps_noise,
            imu_noise=imu_noise,
        )

    def _predict(self) -> None:
        dt = self._dt
        self._x = [
            self._x[0] + self._v[0] * dt,
            self._x[1] + self._v[1] * dt,
            self._x[2] + self._v[2] * dt,
        ]

        q = self._process_noise * dt
        for i in range(3):
            self._P[i][i] += q

    def _update_gps(self, position: Position) -> None:
        z = [position.x, position.y, position.z]
        r = self._gps_noise

        for i in range(3):
            k = self._P[i][i] / (self._P[i][i] + r)
            self._x[i] += k * (z[i] - self._x[i])
            self._P[i][i] = (1.0 - k) * self._P[i][i]

    def _update_imu(self, orientation: Orientation, rates: Any) -> None:
        self._orientation = orientation
        r = self._imu_noise

        if hasattr(rates, "roll_rate"):
            self._v[0] += rates.roll_rate * self._dt
            self._v[1] += rates.pitch_rate * self._dt
            self._v[2] += rates.yaw_rate * self._dt

        for i in range(3):
            k = 0.1
            self._P[i][i] = (1.0 - k) * self._P[i][i] + k * r

    def update(
        self,
        position: Position | None = None,
        orientation: Orientation | None = None,
        angular_rates: Any | None = None,
    ) -> FusedPosition:
        """Update the filter with new sensor measurements."""
        self._predict()

        if position is not None:
            self._update_gps(position)
            self._initialized = True

        if orientation is not None and angular_rates is not None:
            self._update_imu(orientation, angular_rates)
            self._initialized = True

        self._update_count += 1

        fused = FusedPosition(
            position=Position(x=self._x[0], y=self._x[1], z=self._x[2]),
            covariance=[row[:] for row in self._P],
            velocity=(self._v[0], self._v[1], self._v[2]),
            orientation=self._orientation,
        )

        logger.trace(
            "Fusion update",
            count=self._update_count,
            uncertainty=fused.uncertainty,
        )

        return fused

    def predict(self, steps: int = 1) -> FusedPosition:
        """Predict future state without measurement updates."""
        for _ in range(steps):
            self._predict()

        return FusedPosition(
            position=Position(x=self._x[0], y=self._x[1], z=self._x[2]),
            covariance=[row[:] for row in self._P],
            velocity=(self._v[0], self._v[1], self._v[2]),
            orientation=self._orientation,
        )

    def get_position(self) -> FusedPosition | None:
        """Get the current fused position estimate."""
        if not self._initialized:
            return None

        return FusedPosition(
            position=Position(x=self._x[0], y=self._x[1], z=self._x[2]),
            covariance=[row[:] for row in self._P],
            velocity=(self._v[0], self._v[1], self._v[2]),
            orientation=self._orientation,
        )

    def reset(self) -> None:
        """Reset the filter to initial state."""
        self._x = [0.0, 0.0, 0.0]
        self._v = [0.0, 0.0, 0.0]
        self._P = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
        self._initialized = False
        self._update_count = 0
        self._orientation = None
        logger.info("SensorFusion reset")
