from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from rover_swarm.types import Position, RoverId


@dataclass
class EnvironmentConfig:
    world_bounds: tuple[float, float, float, float] = (0.0, 0.0, 100.0, 100.0)
    obstacles: list[tuple[float, float, float]] = field(default_factory=list)
    terrain_difficulty: float = 0.0


@dataclass
class SimulatedRover:
    rover_id: RoverId
    position: Position
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(2, dtype=np.float64))
    heading: float = 0.0
    battery: float = 100.0
    speed: float = 0.0
    sensor_noise_std: float = 0.1
    active: bool = True
    path_history: list[Position] = field(default_factory=list)
    sensor_readings: dict[str, Any] = field(default_factory=dict)

    def noisy_sensor(self, true_value: float) -> float:
        return true_value + np.random.normal(0.0, self.sensor_noise_std)


@dataclass
class SimulationMetrics:
    total_steps: int = 0
    total_collisions: int = 0
    total_distance_traveled: float = 0.0
    average_battery: float = 100.0
    active_rovers: int = 0
    events: list[str] = field(default_factory=list)

    def snapshot(self) -> dict[str, Any]:
        return {
            "total_steps": self.total_steps,
            "total_collisions": self.total_collisions,
            "total_distance_traveled": round(self.total_distance_traveled, 2),
            "average_battery": round(self.average_battery, 2),
            "active_rovers": self.active_rovers,
        }


class SwarmSimulator:
    def __init__(self, config: EnvironmentConfig | None = None) -> None:
        self.config = config or EnvironmentConfig()
        self._rovers: dict[RoverId, SimulatedRover] = {}
        self._metrics = SimulationMetrics()
        self._dt: float = 0.1

    def add_rover(
        self,
        rover_id: RoverId,
        x: float = 0.0,
        y: float = 0.0,
        heading: float = 0.0,
        battery: float = 100.0,
    ) -> SimulatedRover:
        rover = SimulatedRover(
            rover_id=rover_id,
            position=Position(x=x, y=y),
            heading=heading,
            battery=battery,
        )
        self._rovers[rover_id] = rover
        return rover

    def get_rover(self, rover_id: RoverId) -> SimulatedRover:
        return self._rovers[rover_id]

    def rover_positions(self) -> dict[RoverId, Position]:
        return {rid: r.position for rid, r in self._rovers.items()}

    def set_environment(self, config: EnvironmentConfig) -> None:
        self.config = config

    def step(self, dt: float | None = None) -> None:
        if dt is not None:
            self._dt = dt
        self._metrics.total_steps += 1

        for rover in list(self._rovers.values()):
            if not rover.active:
                continue

            dx = rover.velocity[0] * self._dt
            dy = rover.velocity[1] * self._dt

            if dx != 0.0 or dy != 0.0:
                rover.heading = math.atan2(dy, dx)

            rover.position.x += dx
            rover.position.y += dy

            x_min, y_min, x_max, y_max = self.config.world_bounds
            clamped = False
            if rover.position.x < x_min:
                rover.position.x = x_min
                rover.velocity[0] *= -0.5
                clamped = True
            elif rover.position.x > x_max:
                rover.position.x = x_max
                rover.velocity[0] *= -0.5
                clamped = True
            if rover.position.y < y_min:
                rover.position.y = y_min
                rover.velocity[1] *= -0.5
                clamped = True
            elif rover.position.y > y_max:
                rover.position.y = y_max
                rover.velocity[1] *= -0.5
                clamped = True
            if clamped:
                self._metrics.total_collisions += 1

            for ox, oy, radius in self.config.obstacles:
                dist = math.hypot(rover.position.x - ox, rover.position.y - oy)
                if dist < radius:
                    overlap = radius - dist
                    if dist > 1e-8:
                        nx = (rover.position.x - ox) / dist
                        ny = (rover.position.y - oy) / dist
                    else:
                        nx, ny = 1.0, 0.0
                    rover.position.x += nx * overlap
                    rover.position.y += ny * overlap
                    rover.velocity -= 0.5 * np.array([nx, ny], dtype=np.float64)
                    self._metrics.total_collisions += 1

            speed = float(np.linalg.norm(rover.velocity))
            self._metrics.total_distance_traveled += speed * self._dt
            rover.speed = speed

            discharge = 0.01 * speed * self._dt + 0.001 * self._dt
            rover.battery = max(0.0, rover.battery - discharge)
            if rover.battery <= 0.0:
                rover.active = False

            rover.path_history.append(Position(x=rover.position.x, y=rover.position.y))

        active = sum(1 for r in self._rovers.values() if r.active)
        self._metrics.active_rovers = active
        if active:
            self._metrics.average_battery = (
                sum(r.battery for r in self._rovers.values() if r.active) / active
            )

    def reset(self) -> None:
        self._rovers.clear()
        self._metrics = SimulationMetrics()

    @property
    def metrics(self) -> SimulationMetrics:
        return self._metrics

    @property
    def rovers(self) -> dict[RoverId, SimulatedRover]:
        return dict(self._rovers)
