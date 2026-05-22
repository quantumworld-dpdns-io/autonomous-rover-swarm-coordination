from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable

from rover_swarm.types import Position


@dataclass
class Path:
    waypoints: list[Position] = field(default_factory=list)
    cost: float = 0.0

    def length(self) -> float:
        total = 0.0
        for i in range(1, len(self.waypoints)):
            total += self.waypoints[i - 1].distance_to(self.waypoints[i])
        return total


class PathPlanner:
    """Base path planner interface."""

    def plan(self, start: Position, goal: Position) -> Path:
        raise NotImplementedError


class AStarPlanner(PathPlanner):
    """A* path planner on a 2D grid."""

    def __init__(
        self,
        grid_width: int = 100,
        grid_height: int = 100,
        cell_size: float = 1.0,
        obstacle_map: Callable[[float, float], bool] | None = None,
    ) -> None:
        self.grid_width = grid_width
        self.grid_height = grid_height
        self.cell_size = cell_size
        self.obstacle_map = obstacle_map or (lambda x, y: False)

    def _to_grid(self, pos: Position) -> tuple[int, int]:
        return (
            int(pos.x / self.cell_size) + self.grid_width // 2,
            int(pos.y / self.cell_size) + self.grid_height // 2,
        )

    def _to_world(self, gx: int, gy: int) -> Position:
        return Position(
            x=(gx - self.grid_width // 2) * self.cell_size,
            y=(gy - self.grid_height // 2) * self.cell_size,
        )

    def _heuristic(self, a: tuple[int, int], b: tuple[int, int]) -> float:
        return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)

    def plan(self, start: Position, goal: Position) -> Path:
        import heapq
        start_g = self._to_grid(start)
        goal_g = self._to_grid(goal)
        open_set = [(0.0, start_g)]
        came_from: dict = {}
        g_score: dict = {start_g: 0.0}
        f_score: dict = {start_g: self._heuristic(start_g, goal_g)}

        while open_set:
            _, current = heapq.heappop(open_set)
            if current == goal_g:
                path = self._reconstruct(came_from, current)
                return Path(waypoints=[self._to_world(gx, gy) for gx, gy in path])

            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)]:
                neighbor = (current[0] + dx, current[1] + dy)
                wx, wy = self._to_world(*neighbor).x, self._to_world(*neighbor).y
                if self.obstacle_map(wx, wy):
                    continue
                if not (0 <= neighbor[0] < self.grid_width and 0 <= neighbor[1] < self.grid_height):
                    continue
                move_cost = math.sqrt(2) if dx != 0 and dy != 0 else 1.0
                tentative = g_score[current] + move_cost
                if tentative < g_score.get(neighbor, float("inf")):
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative
                    f = tentative + self._heuristic(neighbor, goal_g)
                    f_score[neighbor] = f
                    heapq.heappush(open_set, (f, neighbor))

        return Path(waypoints=[start, goal], cost=float("inf"))

    def _reconstruct(self, came_from: dict, current: tuple[int, int]) -> list[tuple[int, int]]:
        path = [current]
        while current in came_from:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return path


class RRTPlanner(PathPlanner):
    """Rapidly-Exploring Random Tree path planner."""

    def __init__(
        self,
        max_iterations: int = 1000,
        step_size: float = 2.0,
        goal_sample_rate: float = 0.1,
        obstacle_check: Callable[[float, float], bool] | None = None,
    ) -> None:
        self.max_iterations = max_iterations
        self.step_size = step_size
        self.goal_sample_rate = goal_sample_rate
        self.obstacle_check = obstacle_check or (lambda x, y: False)

    def plan(self, start: Position, goal: Position) -> Path:
        nodes = [{"pos": start, "parent": None, "cost": 0.0}]

        for _ in range(self.max_iterations):
            if random.random() < self.goal_sample_rate:
                target = goal
            else:
                target = Position(
                    x=random.uniform(-50, 50),
                    y=random.uniform(-50, 50),
                )

            nearest = min(nodes, key=lambda n: n["pos"].distance_to(target))
            dist = nearest["pos"].distance_to(target)
            step_ratio = min(self.step_size / max(dist, 0.01), 1.0)
            new_pos = Position(
                x=nearest["pos"].x + (target.x - nearest["pos"].x) * step_ratio,
                y=nearest["pos"].y + (target.y - nearest["pos"].y) * step_ratio,
            )

            if self.obstacle_check(new_pos.x, new_pos.y):
                continue

            new_node = {
                "pos": new_pos,
                "parent": len(nodes) - 1,
                "cost": nearest["cost"] + nearest["pos"].distance_to(new_pos),
            }
            nodes.append(new_node)

            if new_pos.distance_to(goal) < self.step_size:
                path: list[Position] = [goal, new_pos]
                idx = new_node["parent"]
                while idx is not None:
                    path.append(nodes[idx]["pos"])
                    idx = nodes[idx]["parent"]
                path.reverse()
                return Path(waypoints=path, cost=new_node["cost"])

        return Path(waypoints=[start, goal], cost=float("inf"))
