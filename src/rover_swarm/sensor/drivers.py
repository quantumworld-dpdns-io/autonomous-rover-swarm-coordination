from __future__ import annotations

import math
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from rover_swarm.exceptions import SensorReadError
from rover_swarm.sensor.base import CalibrationResult, Sensor
from rover_swarm.types import (
    Metadata,
    Orientation,
    Position,
    RoverId,
    SensorReading,
    SensorType,
)


@dataclass
class AngularRates:
    roll_rate: float = 0.0
    pitch_rate: float = 0.0
    yaw_rate: float = 0.0


@dataclass
class ImuReading:
    orientation: Orientation
    rates: AngularRates
    acceleration: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass
class LidarReading:
    distances: list[float]
    angles: list[float]
    min_range: float = 0.0
    max_range: float = 0.0


@dataclass
class CameraMetadata:
    width: int
    height: int
    format: str
    focal_length: float
    exposure: float
    iso: int


@dataclass
class TemperatureReading:
    celsius: float
    humidity: float | None = None


@dataclass
class BatteryReading:
    voltage: float
    current: float
    capacity_remaining: float
    capacity_total: float
    temperature_celsius: float | None = None


_FAILURE_ENV_VAR = "ROVER_SENSOR_FAILURE_RATE"


def _should_fail(sensor_name: str) -> bool:
    rate = float(os.environ.get(_FAILURE_ENV_VAR, "0.0"))
    if rate > 0 and random.random() < rate:
        logger.warning("Simulated sensor failure", name=sensor_name)
        return True
    return False


def _add_noise(value: float, noise_std: float) -> float:
    return value + random.gauss(0, noise_std)


class GpsSensor(Sensor):
    """GPS sensor returning position with simulated noise."""

    def __init__(
        self,
        rover_id: RoverId,
        name: str = "gps",
        frequency: float = 10.0,
        noise_std: float = 1.0,
        origin: Position | None = None,
        drift: tuple[float, float, float] = (0.1, 0.1, 0.0),
    ) -> None:
        super().__init__(name, SensorType.GPS, rover_id, frequency)
        self._noise_std = noise_std
        self._origin = origin or Position()
        self._drift = drift
        self._step = 0
        self._last_reading = self._origin

    def read(self) -> SensorReading:
        if _should_fail(self._name):
            raise SensorReadError(f"Sensor {self._name} failed")

        self._step += 1
        t = self._step * (1.0 / self._frequency)

        x = self._origin.x + self._drift[0] * t + _add_noise(0, self._noise_std)
        y = self._origin.y + self._drift[1] * t + _add_noise(0, self._noise_std)
        z = self._origin.z + self._drift[2] * t + _add_noise(0, self._noise_std * 0.5)

        position = Position(x=x, y=y, z=z)
        self._last_reading = position

        return SensorReading(
            sensor_type=SensorType.GPS,
            rover_id=self._rover_id,
            value=position,
            metadata={"noise_std": self._noise_std, "step": self._step},
        )

    def _do_calibrate(self) -> CalibrationResult:
        samples = [random.gauss(0, self._noise_std) for _ in range(100)]
        bias = sum(samples) / len(samples)
        return CalibrationResult(
            success=True,
            offset=bias,
            scale=1.0,
            details={"samples": 100, "measured_bias": bias},
        )


class ImuSensor(Sensor):
    """IMU sensor returning orientation with angular rates."""

    def __init__(
        self,
        rover_id: RoverId,
        name: str = "imu",
        frequency: float = 100.0,
        noise_std: float = 0.01,
        bias: Orientation | None = None,
    ) -> None:
        super().__init__(name, SensorType.IMU, rover_id, frequency)
        self._noise_std = noise_std
        self._bias = bias or Orientation()
        self._step = 0

    def read(self) -> SensorReading:
        if _should_fail(self._name):
            raise SensorReadError(f"Sensor {self._name} failed")

        self._step += 1
        t = self._step * (1.0 / self._frequency)

        roll = _add_noise(math.sin(t * 0.5) * 0.1 + self._bias.roll, self._noise_std)
        pitch = _add_noise(math.cos(t * 0.3) * 0.05 + self._bias.pitch, self._noise_std)
        yaw = _add_noise(t * 0.02 + self._bias.yaw, self._noise_std)

        orientation = Orientation(roll=roll, pitch=pitch, yaw=yaw)

        rates = AngularRates(
            roll_rate=_add_noise(math.cos(t * 0.5) * 0.1, self._noise_std * 0.5),
            pitch_rate=_add_noise(-math.sin(t * 0.3) * 0.05, self._noise_std * 0.5),
            yaw_rate=_add_noise(0.02, self._noise_std * 0.5),
        )

        accel = (
            _add_noise(0, self._noise_std * 2),
            _add_noise(0, self._noise_std * 2),
            _add_noise(-9.81, self._noise_std * 2),
        )

        imu_reading = ImuReading(orientation=orientation, rates=rates, acceleration=accel)

        return SensorReading(
            sensor_type=SensorType.IMU,
            rover_id=self._rover_id,
            value=imu_reading,
            metadata={"step": self._step},
        )


class LidarSensor(Sensor):
    """LIDAR sensor returning mock distance readings."""

    def __init__(
        self,
        rover_id: RoverId,
        name: str = "lidar",
        frequency: float = 20.0,
        noise_std: float = 0.05,
        num_rays: int = 360,
        max_range: float = 30.0,
        min_range: float = 0.1,
    ) -> None:
        super().__init__(name, SensorType.LIDAR, rover_id, frequency)
        self._noise_std = noise_std
        self._num_rays = num_rays
        self._max_range = max_range
        self._min_range = min_range
        self._step = 0

    def read(self) -> SensorReading:
        if _should_fail(self._name):
            raise SensorReadError(f"Sensor {self._name} failed")

        self._step += 1
        angles = [i * 360.0 / self._num_rays for i in range(self._num_rays)]
        distances = [
            abs(_add_noise(self._max_range * 0.5, self._noise_std * self._max_range))
            for _ in range(self._num_rays)
        ]

        lidar_reading = LidarReading(
            distances=distances,
            angles=angles,
            min_range=self._min_range,
            max_range=self._max_range,
        )

        return SensorReading(
            sensor_type=SensorType.LIDAR,
            rover_id=self._rover_id,
            value=lidar_reading,
            metadata={"num_rays": self._num_rays, "step": self._step},
        )

    def _do_calibrate(self) -> CalibrationResult:
        samples = [abs(random.gauss(1.0, self._noise_std)) for _ in range(50)]
        avg_error = sum(samples) / len(samples) - 1.0
        return CalibrationResult(
            success=avg_error < 0.5,
            offset=avg_error,
            scale=1.0 / (1.0 + avg_error) if abs(avg_error) > 0.01 else 1.0,
            details={"mean_error": avg_error, "samples": 50},
        )


class CameraSensor(Sensor):
    """Camera sensor returning mock image metadata."""

    def __init__(
        self,
        rover_id: RoverId,
        name: str = "camera",
        frequency: float = 30.0,
        width: int = 1280,
        height: int = 720,
        image_format: str = "jpeg",
        focal_length: float = 4.0,
    ) -> None:
        super().__init__(name, SensorType.CAMERA, rover_id, frequency)
        self._width = width
        self._height = height
        self._format = image_format
        self._focal_length = focal_length
        self._step = 0

    def read(self) -> SensorReading:
        if _should_fail(self._name):
            raise SensorReadError(f"Sensor {self._name} failed")

        self._step += 1
        exposure = _add_noise(0.01, 0.001)
        iso = int(random.choice([100, 200, 400, 800]))

        metadata = CameraMetadata(
            width=self._width,
            height=self._height,
            format=self._format,
            focal_length=self._focal_length,
            exposure=exposure,
            iso=iso,
        )

        return SensorReading(
            sensor_type=SensorType.CAMERA,
            rover_id=self._rover_id,
            value=metadata,
            metadata={
                "step": self._step,
                "frame_id": f"frame_{self._step:06d}",
            },
        )


class TemperatureSensor(Sensor):
    """Temperature sensor returning ambient temperature."""

    def __init__(
        self,
        rover_id: RoverId,
        name: str = "temperature",
        frequency: float = 1.0,
        noise_std: float = 0.5,
        ambient_celsius: float = 25.0,
    ) -> None:
        super().__init__(name, SensorType.TEMPERATURE, rover_id, frequency)
        self._noise_std = noise_std
        self._ambient = ambient_celsius
        self._step = 0

    def read(self) -> SensorReading:
        if _should_fail(self._name):
            raise SensorReadError(f"Sensor {self._name} failed")

        self._step += 1
        t = self._step * (1.0 / self._frequency)
        diurnal = math.sin(t * 0.01) * 5.0
        celsius = _add_noise(self._ambient + diurnal, self._noise_std)
        humidity = _add_noise(50.0, 5.0)
        humidity = max(0.0, min(100.0, humidity))

        reading = TemperatureReading(celsius=celsius, humidity=humidity)

        return SensorReading(
            sensor_type=SensorType.TEMPERATURE,
            rover_id=self._rover_id,
            value=reading,
            metadata={"step": self._step, "humidity": humidity},
        )


class BatteryMonitor(Sensor):
    """Battery monitor returning voltage, current, and capacity."""

    def __init__(
        self,
        rover_id: RoverId,
        name: str = "battery",
        frequency: float = 1.0,
        noise_std: float = 0.05,
        capacity_total: float = 100.0,
        nominal_voltage: float = 12.0,
        discharge_rate: float = 0.01,
    ) -> None:
        super().__init__(name, SensorType.BATTERY, rover_id, frequency)
        self._noise_std = noise_std
        self._capacity_total = capacity_total
        self._nominal_voltage = nominal_voltage
        self._discharge_rate = discharge_rate
        self._step = 0

    def read(self) -> SensorReading:
        if _should_fail(self._name):
            raise SensorReadError(f"Sensor {self._name} failed")

        self._step += 1
        elapsed = self._step * (1.0 / self._frequency)
        capacity_used = min(elapsed * self._discharge_rate, self._capacity_total * 0.95)
        capacity_remaining = self._capacity_total - capacity_used

        voltage = _add_noise(
            self._nominal_voltage * (capacity_remaining / self._capacity_total) * 1.1,
            self._noise_std,
        )
        current = _add_noise(self._discharge_rate * 10, self._noise_std * 0.1)
        temperature = _add_noise(30.0, 2.0)

        reading = BatteryReading(
            voltage=voltage,
            current=current,
            capacity_remaining=capacity_remaining,
            capacity_total=self._capacity_total,
            temperature_celsius=temperature,
        )

        return SensorReading(
            sensor_type=SensorType.BATTERY,
            rover_id=self._rover_id,
            value=reading,
            metadata={
                "step": self._step,
                "state_of_charge": capacity_remaining / self._capacity_total,
                "elapsed_seconds": elapsed,
            },
        )
