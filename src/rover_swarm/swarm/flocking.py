from __future__ import annotations

import math
from dataclasses import dataclass

from rover_swarm.types import Position


@dataclass
class FlockingForce:
    dx: float = 0.0
    dy: float = 0.0
    dz: float = 0.0


class FlockingAlgorithm:
    """Reynolds boids-style flocking for rover swarm movement.

    Three rules: separation, alignment, cohesion.
    """

    def __init__(
        self,
        separation_weight: float = 1.5,
        alignment_weight: float = 1.0,
        cohesion_weight: float = 1.0,
        perception_radius: float = 10.0,
        separation_radius: float = 3.0,
        max_speed: float = 5.0,
    ) -> None:
        self.separation_weight = separation_weight
        self.alignment_weight = alignment_weight
        self.cohesion_weight = cohesion_weight
        self.perception_radius = perception_radius
        self.separation_radius = separation_radius
        self.max_speed = max_speed

    def compute(
        self,
        my_pos: Position,
        my_heading: float,
        neighbors: list[tuple[Position, float]],
    ) -> FlockingForce:
        separation = self._separation(my_pos, neighbors)
        alignment = self._alignment(my_heading, neighbors)
        cohesion = self._cohesion(my_pos, neighbors)
        total = FlockingForce(
            dx=separation.dx * self.separation_weight
            + alignment.dx * self.alignment_weight
            + cohesion.dx * self.cohesion_weight,
            dy=separation.dy * self.separation_weight
            + alignment.dy * self.alignment_weight
            + cohesion.dy * self.cohesion_weight,
        )
        magnitude = math.sqrt(total.dx ** 2 + total.dy ** 2)
        if magnitude > self.max_speed:
            scale = self.max_speed / magnitude
            total.dx *= scale
            total.dy *= scale
        return total

    def _separation(self, my_pos: Position, neighbors: list[tuple[Position, float]]) -> FlockingForce:
        force = FlockingForce()
        for pos, _ in neighbors:
            dx = my_pos.x - pos.x
            dy = my_pos.y - pos.y
            dist = math.sqrt(dx ** 2 + dy ** 2)
            if 0 < dist < self.separation_radius:
                strength = 1.0 / dist
                force.dx += (dx / dist) * strength
                force.dy += (dy / dist) * strength
        return force

    def _alignment(self, my_heading: float, neighbors: list[tuple[Position, float]]) -> FlockingForce:
        force = FlockingForce()
        if not neighbors:
            return force
        avg_heading = sum(h for _, h in neighbors) / len(neighbors)
        force.dx = math.cos(avg_heading) - math.cos(my_heading)
        force.dy = math.sin(avg_heading) - math.sin(my_heading)
        return force

    def _cohesion(self, my_pos: Position, neighbors: list[tuple[Position, float]]) -> FlockingForce:
        force = FlockingForce()
        if not neighbors:
            return force
        avg_x = sum(p.x for p, _ in neighbors) / len(neighbors)
        avg_y = sum(p.y for p, _ in neighbors) / len(neighbors)
        force.dx = avg_x - my_pos.x
        force.dy = avg_y - my_pos.y
        return force
