from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import numpy as np


class ObstacleType(str, Enum):
    ROCK = "rock"
    CRATER = "crater"
    WATER = "water"
    SAND = "sand"
    VEGETATION = "vegetation"
    STRUCTURE = "structure"


@dataclass
class Obstacle:
    position: tuple[float, float]
    radius: float
    obstacle_type: ObstacleType = ObstacleType.ROCK
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TerrainMap:
    elevation: np.ndarray
    traversability: np.ndarray
    resolution: float
    origin_x: float = 0.0
    origin_y: float = 0.0
    obstacles: list[Obstacle] = field(default_factory=list)

    def grid_coords(self, x: float, y: float) -> tuple[int, int]:
        gx = int((x - self.origin_x) / self.resolution)
        gy = int((y - self.origin_y) / self.resolution)
        gx = max(0, min(gx, self.elevation.shape[1] - 1))
        gy = max(0, min(gy, self.elevation.shape[0] - 1))
        return gx, gy

    def elevation_at(self, x: float, y: float) -> float:
        gx, gy = self.grid_coords(x, y)
        return float(self.elevation[gy, gx])

    def traversability_at(self, x: float, y: float) -> float:
        gx, gy = self.grid_coords(x, y)
        return float(self.traversability[gy, gx])

    def path_cost(self, waypoints: list[tuple[float, float]]) -> float:
        if len(waypoints) < 2:
            return 0.0
        total = 0.0
        for i in range(len(waypoints) - 1):
            x1, y1 = waypoints[i]
            x2, y2 = waypoints[i + 1]
            dist = math.hypot(x2 - x1, y2 - y1)
            mid_x, mid_y = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            trav = self.traversability_at(mid_x, mid_y)
            total += dist * (2.0 - trav)
        return total


def _generate_perlin_noise(
    shape: tuple[int, int],
    scale: float = 20.0,
    octaves: int = 4,
    persistence: float = 0.5,
    lacunarity: float = 2.0,
    seed: int | None = None,
) -> np.ndarray:
    try:
        from scipy.interpolate import interpn
    except ImportError:
        interpn = None

    if seed is not None:
        np.random.seed(seed)

    rows, cols = shape
    noise = np.zeros((rows, cols))
    amplitude = 1.0
    frequency = 1.0
    max_value = 0.0

    for _ in range(octaves):
        c = int(cols * frequency / scale)
        r = int(rows * frequency / scale)
        c = max(c, 2)
        r = max(r, 2)
        grid = np.random.rand(r, c) * 2.0 - 1.0

        if interpn is not None:
            xi = np.linspace(0, r - 1, rows)
            yi = np.linspace(0, c - 1, cols)
            xi_grid, yi_grid = np.meshgrid(xi, yi, indexing="ij")
            points = np.column_stack((xi_grid.ravel(), yi_grid.ravel()))
            sampled = interpn(
                (np.arange(r), np.arange(c)),
                grid,
                points,
                method="linear",
                bounds_error=False,
                fill_value=0.0,
            ).reshape((rows, cols))
        else:
            sampled = np.zeros((rows, cols))
            for i in range(rows):
                for j in range(cols):
                    fi = i / rows * (r - 1)
                    fj = j / cols * (c - 1)
                    ir, jr = int(fi), int(fj)
                    ifr, jfr = fi - ir, fj - jr
                    ir = min(ir, r - 2)
                    jr = min(jr, c - 2)
                    v00 = grid[ir, jr]
                    v10 = grid[ir + 1, jr]
                    v01 = grid[ir, jr + 1]
                    v11 = grid[ir + 1, jr + 1]
                    v0 = v00 + (v10 - v00) * ifr
                    v1 = v01 + (v11 - v01) * ifr
                    sampled[i, j] = v0 + (v1 - v0) * jfr

        noise += amplitude * sampled
        max_value += amplitude
        amplitude *= persistence
        frequency *= lacunarity

    noise /= max_value
    noise = (noise + 1.0) / 2.0
    return np.clip(noise, 0.0, 1.0)


def generate_random_terrain(
    width: float = 100.0,
    height: float = 100.0,
    resolution: float = 1.0,
    seed: int | None = None,
    num_obstacles: int = 10,
    **kwargs: Any,
) -> TerrainMap:
    cols = max(2, int(width / resolution))
    rows = max(2, int(height / resolution))
    shape = (rows, cols)

    elevation = _generate_perlin_noise(shape, seed=seed, **kwargs)
    traversability = 1.0 - elevation
    traversability = np.clip(traversability, 0.0, 1.0)

    if seed is not None:
        rng = random.Random(seed)
    else:
        rng = random.Random()

    obstacles: list[Obstacle] = []
    for _ in range(num_obstacles):
        ox = rng.uniform(0.0, width)
        oy = rng.uniform(0.0, height)
        gx, gy = int(ox / resolution), int(oy / resolution)
        gx = min(gx, cols - 1)
        gy = min(gy, rows - 1)
        obs_type = rng.choice(list(ObstacleType))
        radius = rng.uniform(1.0, 4.0)
        obstacles.append(
            Obstacle(
                position=(ox, oy),
                radius=radius,
                obstacle_type=obs_type,
                metadata={"grid_x": gx, "grid_y": gy},
            )
        )
        trav_radius = max(1, int(radius / resolution))
        for di in range(-trav_radius, trav_radius + 1):
            for dj in range(-trav_radius, trav_radius + 1):
                ni, nj = gy + di, gx + dj
                if 0 <= ni < rows and 0 <= nj < cols:
                    dist = math.hypot(di, dj)
                    if dist <= trav_radius:
                        traversability[ni, nj] = max(0.0, traversability[ni, nj] - 0.5 * (1.0 - dist / trav_radius))

    return TerrainMap(
        elevation=elevation,
        traversability=traversability,
        resolution=resolution,
        origin_x=0.0,
        origin_y=0.0,
        obstacles=obstacles,
    )
