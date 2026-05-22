from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rover_swarm.types import Position, RoverId


@dataclass
class VisualizerConfig:
    width: int = 1024
    height: int = 768
    bg_color: tuple[int, int, int] = (30, 30, 40)
    rover_color: tuple[int, int, int] = (0, 200, 255)
    path_color: tuple[int, int, int] = (100, 200, 255)
    comm_link_color: tuple[int, int, int] = (80, 255, 80)
    obstacle_color: tuple[int, int, int] = (255, 80, 80)
    update_rate: float = 30.0
    show_paths: bool = True
    show_communication_links: bool = True
    show_rover_labels: bool = True
    world_bounds: tuple[float, float, float, float] = (0.0, 0.0, 100.0, 100.0)
    extra: dict[str, Any] = field(default_factory=dict)


class SwarmVisualizer:
    def __init__(self, config: VisualizerConfig | None = None) -> None:
        self.config = config or VisualizerConfig()
        self._pygame: Any = None
        self._screen: Any = None
        self._clock: Any = None
        self._fig: Any = None
        self._ax: Any = None
        self._backend: str = "pygame"

    def _init_pygame(self) -> bool:
        try:
            import pygame

            self._pygame = pygame
            pygame.init()
            self._screen = pygame.display.set_mode((self.config.width, self.config.height))
            pygame.display.set_caption("Rover Swarm Simulation")
            self._clock = pygame.time.Clock()
            return True
        except ImportError:
            return False

    def _init_matplotlib(self) -> bool:
        try:
            import matplotlib
            import matplotlib.pyplot as plt

            matplotlib.use("TkAgg")
            self._plt = plt
            w, h = self.config.width / 100, self.config.height / 100
            self._fig, self._ax = plt.subplots(figsize=(w, h))
            self._ax.set_xlim(self.config.world_bounds[0], self.config.world_bounds[2])
            self._ax.set_ylim(self.config.world_bounds[1], self.config.world_bounds[3])
            self._ax.set_aspect("equal")
            self._ax.grid(True, alpha=0.3)
            plt.ion()
            return True
        except ImportError:
            return False

    def setup(self, backend: str = "pygame") -> bool:
        self._backend = backend
        if backend == "pygame":
            return self._init_pygame()
        return self._init_matplotlib()

    def render(
        self,
        positions: dict[RoverId, Position],
        paths: dict[RoverId, list[Position]] | None = None,
        communication_links: list[tuple[RoverId, RoverId]] | None = None,
        obstacles: list[tuple[float, float, float]] | None = None,
        _metadata: dict[RoverId, dict[str, Any]] | None = None,
    ) -> bool:
        if self._backend == "pygame":
            return self._render_pygame(positions, paths, communication_links, obstacles)
        return self._render_matplotlib(positions, paths, communication_links, obstacles)

    def _render_pygame(
        self,
        positions: dict[RoverId, Position],
        paths: dict[RoverId, list[Position]] | None,
        communication_links: list[tuple[RoverId, RoverId]] | None,
        obstacles: list[tuple[float, float, float]] | None,
    ) -> bool:
        if self._pygame is None or self._screen is None:
            return False

        for event in self._pygame.event.get():
            if event.type == self._pygame.QUIT:
                return False

        self._screen.fill(self.config.bg_color)
        w, h = self.config.width, self.config.height
        bx0, by0, bx1, by1 = self.config.world_bounds

        def _world_to_screen(px: float, py: float) -> tuple[float, float]:
            sx = (px - bx0) / (bx1 - bx0) * w
            sy = h - (py - by0) / (by1 - by0) * h
            return sx, sy

        if obstacles:
            for ox, oy, radius in obstacles:
                sx, sy = _world_to_screen(ox, oy)
                sr = radius / (bx1 - bx0) * w
                c = self.config.obstacle_color
                self._pygame.draw.circle(self._screen, c, (int(sx), int(sy)), int(sr))

        if communication_links and self.config.show_communication_links:
            for rid_a, rid_b in communication_links:
                if rid_a in positions and rid_b in positions:
                    a = _world_to_screen(positions[rid_a].x, positions[rid_a].y)
                    b = _world_to_screen(positions[rid_b].x, positions[rid_b].y)
                    self._pygame.draw.line(self._screen, self.config.comm_link_color, a, b, 1)

        for rid, pos in positions.items():
            sx, sy = _world_to_screen(pos.x, pos.y)
            self._pygame.draw.circle(self._screen, self.config.rover_color, (int(sx), int(sy)), 6)
            if self.config.show_rover_labels:
                font = self._pygame.font.Font(None, 18)
                label = font.render(rid, True, (255, 255, 255))
                self._screen.blit(label, (int(sx) + 8, int(sy) - 8))

        if paths and self.config.show_paths:
            for _, trail in paths.items():
                if len(trail) < 2:
                    continue
                pts = [_world_to_screen(p.x, p.y) for p in trail]
                if len(pts) > 1:
                    self._pygame.draw.lines(self._screen, self.config.path_color, False, pts, 1)

        self._pygame.display.flip()
        if self._clock:
            self._clock.tick(self.config.update_rate)
        return True

    def _render_matplotlib(
        self,
        positions: dict[RoverId, Position],
        paths: dict[RoverId, list[Position]] | None,
        communication_links: list[tuple[RoverId, RoverId]] | None,
        obstacles: list[tuple[float, float, float]] | None,
    ) -> bool:
        if self._ax is None:
            return False
        self._ax.clear()
        self._ax.set_xlim(self.config.world_bounds[0], self.config.world_bounds[2])
        self._ax.set_ylim(self.config.world_bounds[1], self.config.world_bounds[3])
        self._ax.set_aspect("equal")
        self._ax.grid(True, alpha=0.3)

        if obstacles:
            for ox, oy, radius in obstacles:
                rgb = [c / 255 for c in self.config.obstacle_color]
                circle = self._plt.Circle((ox, oy), radius, color=(*rgb, 0.5))
                self._ax.add_patch(circle)

        if communication_links and self.config.show_communication_links:
            for rid_a, rid_b in communication_links:
                if rid_a in positions and rid_b in positions:
                    pa = (positions[rid_a].x, positions[rid_a].y)
                    pb = (positions[rid_b].x, positions[rid_b].y)
                    self._ax.plot(
                        [pa[0], pb[0]],
                        [pa[1], pb[1]],
                        color=(*[c / 255 for c in self.config.comm_link_color], 0.4),
                        linewidth=0.5,
                    )

        if paths and self.config.show_paths:
            pc = self.config.path_color
            path_rgb = [c / 255 for c in pc]
            for _, trail in paths.items():
                xs = [p.x for p in trail]
                ys = [p.y for p in trail]
                self._ax.plot(xs, ys, color=(*path_rgb, 0.6), linewidth=0.8)

        for rid, pos in positions.items():
            rc = [c / 255 for c in self.config.rover_color]
            self._ax.plot(pos.x, pos.y, "o", color=(*rc, 1.0), markersize=6)
            if self.config.show_rover_labels:
                self._ax.annotate(
                    rid,
                    (pos.x, pos.y),
                    xytext=(5, 5),
                    textcoords="offset points",
                    fontsize=8,
                    color="white",
                )

        self._plt.pause(1.0 / self.config.update_rate)
        return True

    def close(self) -> None:
        if self._backend == "pygame" and self._pygame is not None:
            self._pygame.quit()
        elif self._backend == "matplotlib" and hasattr(self, "_plt"):
            self._plt.ioff()
            self._plt.close(self._fig)
