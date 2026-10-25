"""Route state and walking guidance independent of camera perception."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class NavigationUpdate:
    message: str | None = None
    event_id: int = 0
    active: bool = False
    off_route: bool = False
    arrived: bool = False
    distance_remaining: float | None = None
    step_index: int = 0


def distance_meters(first: tuple[float, float], second: tuple[float, float]) -> float:
    """Return the great-circle distance between (latitude, longitude) pairs."""
    radius = 6_371_000.0
    first_lat, first_lon = map(math.radians, first)
    second_lat, second_lon = map(math.radians, second)
    d_lat = second_lat - first_lat
    d_lon = second_lon - first_lon
    a = math.sin(d_lat / 2) ** 2 + math.cos(first_lat) * math.cos(second_lat) * math.sin(d_lon / 2) ** 2
    return radius * 2 * math.asin(math.sqrt(a))


def _format_distance(distance: float) -> str:
    if distance < 100:
        return f"{round(distance / 5) * 5} meters"
    return f"{round(distance / 10) * 10} meters"


def _bearing_degrees(first: tuple[float, float], second: tuple[float, float]) -> float:
    first_lat = math.radians(first[0])
    delta_lon = math.radians(second[1] - first[1])
    second_lat = math.radians(second[0])
    y = math.sin(delta_lon) * math.cos(second_lat)
    x = math.cos(first_lat) * math.sin(second_lat) - math.sin(first_lat) * math.cos(second_lat) * math.cos(delta_lon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _heading_delta(current: float, target: float) -> float:
    return (target - current + 540) % 360 - 180


class NavigationManager:
    """Track a walking route and emit a new voice event only when guidance changes."""

    def __init__(self, deviation_meters: float = 50.0, arrival_meters: float = 25.0,
                 repeat_after: float = 8.0):
        self.deviation_meters = deviation_meters
        self.arrival_meters = arrival_meters
        self.repeat_after = repeat_after
        self.route: dict[str, Any] | None = None
        self.steps: list[dict[str, Any]] = []
        self.geometry: list[tuple[float, float]] = []
        self.destination: tuple[float, float] | None = None
        self.step_index = 0
        self.event_id = 0
        self.last_message: str | None = None
        self.last_event_time = -float("inf")
        self.last_position: tuple[float, float] | None = None
        self.distance_remaining: float | None = None
        self.heading: float | None = None
        self.aligned_to_route = False
        self.arrived = False

    def set_route(self, route: dict[str, Any], destination: tuple[float, float]) -> NavigationUpdate:
        self.route = route
        self.destination = destination
        self.steps = [step for step in route.get("legs", [{}])[0].get("steps", []) if step.get("maneuver")]
        self.geometry = [
            (point[1], point[0])
            for point in route.get("geometry", {}).get("coordinates", [])
            if len(point) >= 2
        ]
        self.step_index = 0
        self.arrived = False
        self.last_message = None
        self.last_event_time = -float("inf")
        self.event_id += 1
        self.distance_remaining = route.get("distance")
        self.heading = None
        self.aligned_to_route = False
        return NavigationUpdate(active=True, event_id=self.event_id, step_index=0,
                                distance_remaining=route.get("distance"))

    def clear(self) -> None:
        self.route = None
        self.steps = []
        self.geometry = []
        self.destination = None
        self.step_index = 0
        self.distance_remaining = None
        self.heading = None
        self.aligned_to_route = False
        self.arrived = False
        self.last_message = None

    def update(self, latitude: float, longitude: float, heading: float | None = None) -> NavigationUpdate:
        position = (latitude, longitude)
        self.last_position = position
        if heading is not None and 0 <= heading < 360:
            self.heading = heading
        if self.route is None or self.destination is None:
            return NavigationUpdate()

        remaining = distance_meters(position, self.destination)
        self.distance_remaining = remaining
        if remaining <= self.arrival_meters:
            self.arrived = True
            return self._event("You have arrived at your destination.", remaining, arrived=True)

        deviation = self._distance_to_geometry(position)
        if deviation > self.deviation_meters:
            return self._event("You are off route. Please stop while the route is recalculated.", remaining,
                               off_route=True)

        route_point = self._next_route_point(position)
        if self.heading is not None and route_point is not None:
            delta = _heading_delta(self.heading, _bearing_degrees(position, route_point))
            if abs(delta) > 30:
                self.aligned_to_route = False
                direction = "right" if delta > 0 else "left"
                return self._event(f"Turn {direction} to face the road, then walk straight.", remaining)
            self.aligned_to_route = True

        while self.step_index < len(self.steps) - 1:
            maneuver = self.steps[self.step_index].get("maneuver", {})
            point = maneuver.get("location", [])
            if len(point) < 2:
                break
            maneuver_position = (point[1], point[0])
            if distance_meters(position, maneuver_position) <= 12:
                self.step_index += 1
            else:
                break

        if not self.steps:
            return NavigationUpdate(active=True, distance_remaining=remaining, step_index=0)

        step = self.steps[min(self.step_index, len(self.steps) - 1)]
        maneuver = step.get("maneuver", {})
        instruction = self._instruction(maneuver)
        distance = float(step.get("distance", remaining))
        message = f"{instruction} in {_format_distance(distance)}."
        return self._event(message, remaining, step_index=self.step_index)

    def _event(self, message: str, remaining: float, **kwargs: Any) -> NavigationUpdate:
        now = time.monotonic()
        changed = message != self.last_message
        repeat = now - self.last_event_time >= self.repeat_after
        if changed or repeat:
            self.last_message = message
            self.last_event_time = now
            self.event_id += 1
        step_index = kwargs.pop("step_index", self.step_index)
        return NavigationUpdate(message=message if changed or repeat else None, event_id=self.event_id,
                                active=True, distance_remaining=remaining,
                                step_index=step_index, **kwargs)

    def _distance_to_geometry(self, position: tuple[float, float]) -> float:
        if not self.geometry:
            return 0.0
        return min(distance_meters(position, point) for point in self.geometry)

    def _next_route_point(self, position: tuple[float, float]) -> tuple[float, float] | None:
        if not self.geometry:
            return None
        nearest_index = min(range(len(self.geometry)), key=lambda index: distance_meters(position, self.geometry[index]))
        if nearest_index + 1 < len(self.geometry):
            return self.geometry[nearest_index + 1]
        return self.geometry[nearest_index]

    @staticmethod
    def _instruction(maneuver: dict[str, Any]) -> str:
        maneuver_type = maneuver.get("type", "continue")
        modifier = maneuver.get("modifier", "straight")
        if maneuver_type == "arrive":
            return "Continue"
        if maneuver_type == "depart":
            return "Start walking"
        if maneuver_type == "roundabout":
            exit_number = maneuver.get("exit")
            return f"Take exit {exit_number} at the roundabout" if exit_number else "Enter the roundabout"
        if modifier in {"left", "right", "slight left", "slight right", "sharp left", "sharp right"}:
            return f"Turn {modifier}"
        return "Continue straight"

    def snapshot(self) -> dict[str, Any]:
        return {
            "active": self.route is not None,
            "arrived": self.arrived,
            "step_index": self.step_index,
            "event_id": self.event_id,
            "destination": self.destination,
            "distance_remaining": self.distance_remaining,
            "heading": self.heading,
            "aligned_to_route": self.aligned_to_route,
            "guidance": self.last_message,
        }
