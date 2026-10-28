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
        self.last_key: str | None = None
        self.last_event_time = -float("inf")
        self.last_position: tuple[float, float] | None = None
        self.distance_remaining: float | None = None
        self.heading: float | None = None
        self.target_bearing: float | None = None
        self.aligned_to_route = False
        self.off_route_count = 0
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
        self.last_key = None
        self.last_event_time = -float("inf")
        self.event_id += 1
        self.distance_remaining = route.get("distance")
        self.heading = None
        self.target_bearing = None
        self.aligned_to_route = False
        self.off_route_count = 0
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
        self.target_bearing = None
        self.aligned_to_route = False
        self.off_route_count = 0
        self.arrived = False
        self.last_message = None
        self.last_key = None

    def update(self, latitude: float, longitude: float, heading: float | None = None,
               accuracy: float | None = None,
               heading_timestamp: float | None = None) -> NavigationUpdate:
        position = (latitude, longitude)
        self.last_position = position
        heading_is_fresh = (heading_timestamp is not None and
                            0 <= time.time() * 1000 - heading_timestamp <= 5000)
        if heading is not None and 0 <= heading < 360 and heading_is_fresh:
            self.heading = heading
        else:
            self.heading = None
        if self.route is None or self.destination is None:
            return NavigationUpdate()

        direct_remaining = distance_meters(position, self.destination)
        deviation, remaining = self._route_metrics(position)
        self.distance_remaining = remaining
        if direct_remaining <= self.arrival_meters or self.arrived:
            # Arrival is latched: GPS jitter must not turn "arrived" back into walking guidance.
            already_arrived = self.arrived
            self.arrived = True
            self.distance_remaining = direct_remaining
            if already_arrived:  # announced once; do not nag while the user stands there
                return NavigationUpdate(active=True, arrived=True, event_id=self.event_id,
                                        distance_remaining=direct_remaining,
                                        step_index=self.step_index)
            return self._event("You have arrived at your destination.", direct_remaining, arrived=True)

        accuracy_tolerance = min(100.0, max(0.0, accuracy * 1.5)) if accuracy is not None else 0.0
        deviation_tolerance = max(self.deviation_meters, accuracy_tolerance)
        if deviation > deviation_tolerance:
            self.off_route_count += 1
            if self.off_route_count < 2:
                return NavigationUpdate(active=True, distance_remaining=remaining,
                                        step_index=self.step_index)
            return self._event("You are off the planned route. Stop and request a new route.", remaining,
                               off_route=True)
        self.off_route_count = 0

        while self.step_index < len(self.steps) - 1:
            maneuver = self.steps[self.step_index].get("maneuver", {})
            next_maneuver = self.steps[self.step_index + 1].get("maneuver", {})
            if next_maneuver.get("type") == "arrive":
                break
            if not self._maneuver_reached(position, maneuver, next_maneuver, accuracy):
                break
            self.step_index += 1

        if not self.steps:
            return NavigationUpdate(active=True, distance_remaining=remaining, step_index=0)

        step = self.steps[min(self.step_index, len(self.steps) - 1)]
        maneuver = step.get("maneuver", {})
        target_bearing = maneuver.get("bearing_after")
        if target_bearing is None:
            route_point = self._next_route_point(position)
            target_bearing = _bearing_degrees(position, route_point) if route_point else None
        self.target_bearing = float(target_bearing) % 360 if target_bearing is not None else None

        if self.heading is None or self.target_bearing is None:
            self.aligned_to_route = False
            return self._event("Camera direction unavailable. Stop until the camera direction can be checked.",
                               remaining, step_index=self.step_index)

        delta = _heading_delta(self.heading, self.target_bearing)
        if abs(delta) > 30:
            self.aligned_to_route = False
            if abs(delta) >= 150:
                return self._event("Turn around to face the road. Stop when aligned.", remaining,
                                   step_index=self.step_index)
            direction = "right" if delta > 0 else "left"
            target = "the road" if maneuver.get("type") == "depart" else "the next road"
            return self._event(f"Turn {direction} to face {target}. Stop when aligned.", remaining,
                               step_index=self.step_index)

        self.aligned_to_route = True
        if maneuver.get("type") == "depart":
            prefix = "You are facing the mapped road. Once safely on it, "
        else:
            prefix = "Aligned. "
        next_maneuver = (self.steps[self.step_index + 1].get("maneuver", {})
                         if self.step_index + 1 < len(self.steps) else {})
        if not next_maneuver or next_maneuver.get("type") == "arrive":
            message = f"{prefix}walk straight for {_format_distance(remaining)} to the destination."
            phase = "destination"
        else:
            # Distance left to the next turn, not the whole step length: the number must
            # count down while the user walks, or the voice sounds stuck on one command.
            next_point = next_maneuver.get("location", [])
            if len(next_point) >= 2:
                distance = distance_meters(position, (next_point[1], next_point[0]))
            else:
                distance = float(step.get("distance", remaining))
            next_instruction = self._instruction(next_maneuver).lower()
            message = (f"{prefix}walk straight for {_format_distance(distance)}, "
                       f"then {next_instruction}.")
            phase = next_instruction
        # A shrinking distance alone is not a new instruction: it is only re-spoken on the timer.
        return self._event(message, remaining, key=f"walk:{self.step_index}:{prefix}:{phase}",
                           step_index=self.step_index)

    def _event(self, message: str, remaining: float, key: str | None = None,
               **kwargs: Any) -> NavigationUpdate:
        now = time.monotonic()
        key = key or message
        changed = key != self.last_key
        repeat = now - self.last_event_time >= self.repeat_after
        if changed or repeat:
            self.last_message = message
            self.last_key = key
            self.last_event_time = now
            self.event_id += 1
        step_index = kwargs.pop("step_index", self.step_index)
        return NavigationUpdate(message=message if changed or repeat else None, event_id=self.event_id,
                                active=True, distance_remaining=remaining,
                                step_index=step_index, **kwargs)

    def _distance_to_geometry(self, position: tuple[float, float]) -> float:
        return self._route_metrics(position)[0]

    @staticmethod
    def _maneuver_reached(position: tuple[float, float], start: dict[str, Any],
                          target: dict[str, Any], accuracy: float | None) -> bool:
        target_point = target.get("location", [])
        start_point = start.get("location", [])
        if len(target_point) < 2:
            return False
        target_position = (target_point[1], target_point[0])
        radius = max(12.0, min(25.0, accuracy * 1.5)) if accuracy is not None else 12.0
        if distance_meters(position, target_position) <= radius:
            return True
        if len(start_point) < 2:
            return False

        start_latitude, start_longitude = start_point[1], start_point[0]
        latitude_scale = 111_320.0
        longitude_scale = latitude_scale * math.cos(math.radians(start_latitude))
        route_x = (target_position[1] - start_longitude) * longitude_scale
        route_y = (target_position[0] - start_latitude) * latitude_scale
        route_length = math.hypot(route_x, route_y)
        if route_length < 1.0:
            return False

        position_x = (position[1] - start_longitude) * longitude_scale
        position_y = (position[0] - start_latitude) * latitude_scale
        along_route = (position_x * route_x + position_y * route_y) / route_length
        cross_track = abs(route_x * position_y - route_y * position_x) / route_length
        corridor = max(15.0, min(30.0, accuracy * 1.5)) if accuracy is not None else 15.0
        return along_route >= route_length and cross_track <= corridor

    def _route_metrics(self, position: tuple[float, float]) -> tuple[float, float]:
        if len(self.geometry) < 2:
            if self.geometry:
                distance = distance_meters(position, self.geometry[0])
                if self.destination is not None:
                    return distance, distance + distance_meters(self.geometry[0], self.destination)
                return distance, distance
            direct = distance_meters(position, self.destination) if self.destination else 0.0
            return 0.0, direct

        latitude_scale = 111_320.0
        longitude_scale = latitude_scale * math.cos(math.radians(position[0]))
        best_deviation = float("inf")
        best_remaining = distance_meters(position, self.destination) if self.destination else 0.0
        for index, (first, second) in enumerate(zip(self.geometry, self.geometry[1:])):
            first_x = (first[1] - position[1]) * longitude_scale
            first_y = (first[0] - position[0]) * latitude_scale
            second_x = (second[1] - position[1]) * longitude_scale
            second_y = (second[0] - position[0]) * latitude_scale
            segment_x = second_x - first_x
            segment_y = second_y - first_y
            segment_squared = segment_x * segment_x + segment_y * segment_y
            fraction = 0.0 if segment_squared == 0 else max(
                0.0, min(1.0, -(first_x * segment_x + first_y * segment_y) / segment_squared)
            )
            projected_x = first_x + fraction * segment_x
            projected_y = first_y + fraction * segment_y
            deviation = math.hypot(projected_x, projected_y)
            if deviation >= best_deviation:
                continue

            segment_length = distance_meters(first, second)
            remaining = segment_length * (1 - fraction)
            remaining += sum(distance_meters(start, end)
                             for start, end in zip(self.geometry[index + 1:], self.geometry[index + 2:]))
            best_deviation = deviation
            best_remaining = remaining
        return best_deviation, best_remaining

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
        map_geometry = self.geometry
        max_map_points = 120
        if len(map_geometry) > max_map_points:
            stride = math.ceil((len(map_geometry) - 1) / (max_map_points - 1))
            map_geometry = map_geometry[::stride]
            if map_geometry[-1] != self.geometry[-1]:
                map_geometry.append(self.geometry[-1])
        return {
            "active": self.route is not None,
            "arrived": self.arrived,
            "step_index": self.step_index,
            "event_id": self.event_id,
            "destination": self.destination,
            "route_geometry": map_geometry,
            "distance_remaining": self.distance_remaining,
            "heading": self.heading,
            "target_bearing": self.target_bearing,
            "aligned_to_route": self.aligned_to_route,
            "guidance": self.last_message,
        }
