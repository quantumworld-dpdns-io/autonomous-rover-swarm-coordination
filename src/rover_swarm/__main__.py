from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from typing import NoReturn

from loguru import logger

from rover_swarm import __version__
from rover_swarm.config import settings
from rover_swarm.ground_station import GroundStation
from rover_swarm.logging_config import configure_logging
from rover_swarm.node import RoverNode


def _print_version() -> None:
    print(f"rover-swarm v{__version__}")
    sys.exit(0)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rover-swarm",
        description="Autonomous rover swarm coordination platform",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print version and exit",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    start_parser = subparsers.add_parser("start", help="Start a rover node")
    start_parser.add_argument(
        "--node-id",
        default=settings.node_id,
        help="Unique node identifier",
    )

    gs_parser = subparsers.add_parser("ground-station", help="Start the ground station")
    gs_parser.add_argument(
        "--port",
        type=int,
        default=settings.api.port,
        help="API server port",
    )

    sim_parser = subparsers.add_parser("simulate", help="Start the swarm simulator")
    sim_parser.add_argument(
        "--count",
        type=int,
        default=5,
        help="Number of simulated rovers",
    )
    sim_parser.add_argument(
        "--steps",
        type=int,
        default=100,
        help="Number of simulation steps",
    )

    subparsers.add_parser("discover", help="Run rover discovery mode")

    return parser


async def _run_rover_node(node_id: str) -> None:
    logger.info("Starting rover node: {}", node_id)
    node = RoverNode(node_id=node_id)
    try:
        await node.start()
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)
        await stop_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        await node.stop()
        logger.info("Rover node stopped: {}", node_id)


async def _run_ground_station(port: int) -> None:
    logger.info("Starting ground station on port {}", port)
    station = GroundStation(port=port)
    try:
        await station.start()
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)
        await stop_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        await station.stop()
        logger.info("Ground station stopped")


async def _run_simulator(count: int, steps: int) -> None:
    from rover_swarm.simulation import SwarmSimulator

    logger.info("Starting swarm simulator with {} rovers ({} steps)", count, steps)
    sim = SwarmSimulator()
    for i in range(count):
        sim.add_rover(rover_id=f"rover-{i:03d}", x=float(i * 10), y=float(i * 5))

    for step in range(steps):
        sim.step()
        if step % 10 == 0:
            metrics = sim.metrics.snapshot()
            logger.info("Step {}/{}: {}", step, steps, metrics)
        await asyncio.sleep(0.01)

    logger.info("Simulation complete: {}", sim.metrics.snapshot())


async def _run_discovery() -> None:
    from rover_swarm.communication import RoverDiscovery

    logger.info("Starting rover discovery mode")
    discovery = RoverDiscovery(node_id=settings.node_id)

    def on_discover(rover: object) -> None:
        logger.info("Found rover: {}", rover)

    discovery.on_discover(on_discover)
    try:
        await discovery.start()
        advertise_task = asyncio.create_task(discovery.advertise())
        listen_task = asyncio.create_task(discovery.listen())
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)
        await stop_event.wait()
        advertise_task.cancel()
        listen_task.cancel()
    except asyncio.CancelledError:
        pass
    finally:
        await discovery.stop()
        logger.info("Discovery stopped")


COMMAND_MAP = {
    "start": lambda args: _run_rover_node(args.node_id),
    "ground-station": lambda args: _run_ground_station(args.port),
    "simulate": lambda args: _run_simulator(args.count, args.steps),
    "discover": lambda args: _run_discovery(),
}


def main() -> None:
    configure_logging()
    parser = _build_parser()
    args = parser.parse_args()

    if args.version:
        _print_version()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    logger.info(
        "rover-swarm v{} starting (command={}, node_id={})",
        __version__,
        args.command,
        settings.node_id,
    )

    handler = COMMAND_MAP.get(args.command)
    if handler is None:
        logger.error("Unknown command: {}", args.command)
        sys.exit(1)

    try:
        asyncio.run(handler(args))
    except KeyboardInterrupt:
        logger.info("Shutdown by user")
    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)


if __name__ == "__main__":
    main()
