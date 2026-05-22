from __future__ import annotations

import math
from typing import Any

from rover_swarm.constants import COLLISION_AVOIDANCE_RADIUS
from rover_swarm.types import Position


class CollisionAvoidance:
    """Velocity obstacle-based collision avoidance for rovers."""

    def __init__(self, radius: float = COLLISION_AVOIDANCE_RADIUS) -> None:
        self._radius = radius
        self._avoidance_forces: dict[str, tuple[float, float]] = {}

    def compute_avoidance(
        self,
        my_pos: Position,
        my_velocity: tuple[float, float],
        obstacles: list[tuple[Position, tuple[float, float], float]],
    ) -> tuple[float, float]:
        fx, fy = 0.0, 0.0
        for obs_pos, obs_vel, obs_radius in obstacles:
            dx = my_pos.x - obs_pos.x
            dy = my_pos.y - obs_pos.y
            dist = math.sqrt(dx * dx + dy * dy)
            combined = self._radius + obs_radius
            if dist < combined and dist > 0.01:
                strength = (combined - dist) / combined
                fx += (dx / dist) * strength * 2.0
                fy += (dy / dist) * strength * 2.0
            rel_vx = my_velocity[0] - obs_vel[0]
            rel_vy = my_velocity[1] - obs_vel[1]
            if dist > 0.01:
                tc = (dx * rel_vx + dy * rel_vy) / (dist * dist)
                if tc > 0:
                    closest_x = my_pos.x + rel_vx * tc
                    closest_y = my_pos.y + rel_vy * tc
                    cdx = closest_x - obs_pos.x
                    cdy = closest_y - obs_pos.y
                    cd = math.sqrt(cdx * cdx + cdy * cdy)
                    if cd < combined:
                        fx += cdx / max(cd, 0.01) * 0.5
                        fy += cdy / max(cd, 0.01) * 0.5
        return fx, fy

    def set_radius(self, radius: float) -> None:
        self._radius = radius
