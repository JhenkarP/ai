"""Decision-making: out of everything the system perceives, what deserves to be said, and when.

Perception (phases 1-4) says WHAT is there. This module decides what MATTERS right now.
A blind user can only process one short message every ~2 seconds, so silence is the
default and every word must be worth it.
"""

import math
from dataclasses import dataclass

from blindnav.detector import Detection
from blindnav.spatial import PathStatus, path_hazard

WARNING, URGENT = 1, 2
WARNING_THRESHOLD = 0.3   # urgency needed to say something
URGENT_THRESHOLD = 0.6    # urgency needed to interrupt with "Stop!"
PROXIMITY_RANGE = 4.0     # m: in the path, urgency grows from 0 (at 4 m) to 1 (at 0 m)
HAZARD_PROXIMITY_RANGE = 6.0  # m: give fixed street hazards more warning distance
TTC_RANGE = 6.0           # s: urgency grows from 0 (impact in 6 s) to 1 (impact now)
MAX_DISTANCE = 20.0       # m: farther detections are ignored (mostly false positives)
MAX_APPROACH_DISTANCE = 12.0  # m: beyond this, distances are unreliable -> no "approaching" alert

# How bad a collision would be. A car hurts more than a person or a bench.
CLASS_WEIGHT = {
    "car": 1.0, "bus": 1.0, "truck": 1.0, "train": 1.0, "motorcycle": 1.0,
    "bicycle": 0.9, "person": 0.7, "dog": 0.6,
    # Street hazards (our phase 6 model). Stairs: a fall is among the worst accidents.
    "stairs": 1.0, "stairs_up": 1.0, "stairs_down": 1.0,
    "pole": 0.8, "pillar": 0.8, "obstacle": 0.7, "cone": 0.6,
    "door_closed": 1.0, "door_open": 0.4,
}
HAZARD_CLASSES = {"stairs", "pole", "pillar", "obstacle", "cone", "bin", "door_closed"}
DEFAULT_WEIGHT = 0.6      # static objects: bench, chair, potted plant, hydrant...
OBSTACLE_WEIGHT = 0.8     # unknown obstacle found by the 3D corridor
HEAD_LEVEL_WEIGHT = 1.0   # a cane can't detect it: treat it as seriously as a car

MIN_PERSISTENCE = 0.2     # s an alert must exist before being spoken (kills 1-frame false positives)
MIN_GAP = 0.1             # s between two messages, so priority changes are announced quickly
REPEAT_AFTER = 5.0        # s before repeating an alert about the same thing...
REPEAT_IF_CLOSER = 1.0    # ...and only if it got at least this much closer
FORGET_AFTER = 3.0        # s an alert must be gone before it counts as a new event when it returns


@dataclass
class Alert:
    key: int | str        # what the alert is about: a track id, or "path"
    label: str            # COCO class name, or "obstacle"
    distance: float
    clock: int
    urgency: float        # 0..1, used to rank alerts
    level: int            # WARNING or URGENT
    approaching: bool = False
    head_level: bool = False
    guidance: str | None = None
    path_priority: bool = False


def clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def urgency(distance: float, ttc: float | None, in_path: bool, weight: float,
            proximity_range: float = PROXIMITY_RANGE) -> float:
    """Combine two independent reasons to worry, and keep the strongest one.

    - proximity: something very close IN MY PATH (even if it doesn't move: a pole)
    - time: something that will reach me soon (even if it is still far: a fast car)
    """
    proximity = clip01(1 - distance / proximity_range) if in_path else 0.0
    time = clip01(1 - ttc / TTC_RANGE) if ttc is not None and distance < MAX_APPROACH_DISTANCE else 0.0
    if not in_path:
        time *= 0.6  # approaching but beside my path: I'll probably walk past it
    return weight * max(proximity, time)


def rank_alerts(detections: list[Detection], path: PathStatus | None) -> list[Alert]:
    """Turn raw perception into a list of alerts, most urgent first."""
    alerts = []
    detection_alerts: dict[int, Alert] = {}
    for det in detections:
        if det.class_name in {"door_open", "door_closed"} and (
            det.distance is None or det.distance >= 3.0 or not det.in_path):
            continue
        if det.distance is None or not math.isfinite(det.distance) or (
                det.distance > MAX_DISTANCE and not det.in_path):
            continue  # no usable distance, or too far to trust
        label = det.class_name
        if det.class_name == "stairs" and det.direction in {"up", "down"}:
            label = f"stairs_{det.direction}"
        if det.track_id is None:
            if not det.in_path and label not in {"stairs_up", "stairs_down"}:
                continue  # ordinary detections still require tracker confirmation
            alert_key = f"{label}_{det.clock or 12}"
        else:
            alert_key = det.track_id
        weight = CLASS_WEIGHT.get(label, DEFAULT_WEIGHT)
        proximity_range = HAZARD_PROXIMITY_RANGE if det.class_name in HAZARD_CLASSES else PROXIMITY_RANGE
        u = urgency(det.distance, det.ttc, det.in_path, weight, proximity_range)
        alert = Alert(alert_key, label, det.distance, det.clock or 12, u,
                      level=0, approaching=det.ttc is not None,
                      path_priority=det.in_path)
        alerts.append(alert)
        detection_alerts[id(det)] = alert

    if path is not None and path.blocked:
        # If YOLO already knows what blocks the path, its name is more useful than "obstacle".
        # That only holds when the named object really produced an alert of its own.
        named = path_hazard(detections, path)
        named_alert = detection_alerts.get(id(named)) if named is not None else None
        if named_alert is not None:
            named_alert.guidance = path.guidance
        if named_alert is None or path.head_level:
            weight = HEAD_LEVEL_WEIGHT if path.head_level else OBSTACLE_WEIGHT
            u = urgency(path.distance, path.ttc, True, weight)
            alerts.append(Alert("path", "obstacle", path.distance, path.clock or 12, u, level=0,
                                approaching=path.ttc is not None, head_level=path.head_level,
                                guidance=path.guidance, path_priority=True))

    for a in alerts:
        # A red box means the object is in the walking path. That is an immediate
        # safety event, independent of distance, TTC, or persistence scoring.
        a.level = URGENT if a.path_priority or a.urgency >= URGENT_THRESHOLD else (
            WARNING if a.urgency >= WARNING_THRESHOLD else 0)
        if a.path_priority and a.level == 0:
            a.level = WARNING
    if path is not None and path.guidance:
        in_path_keys = {det.track_id for det in detections if det.in_path}
        for alert in alerts:
            if alert.key == "path" or alert.key in in_path_keys:
                alert.guidance = path.guidance
    def priority(a: Alert) -> tuple[int, int, int, int, float]:
        # Stop-level danger first, then anything shown in red, then the user's
        # requested 11 o'clock direction, and finally numeric urgency.
        stair_priority = a.label in {"stairs_up", "stairs_down"} and a.path_priority
        return (a.level == URGENT, stair_priority, a.path_priority, a.clock == 11, a.urgency)

    return sorted([a for a in alerts if a.level], key=priority, reverse=True)


class Announcer:
    """Decides WHEN to speak. Remembers what was said to avoid repeating itself."""

    def __init__(self):
        self.first_seen: dict = {}  # key -> time the alert first appeared (persistence check)
        self.spoken: dict = {}      # key -> (time, level, distance) of the last message about it
        self.last_present: dict = {}  # key -> last time the alert was still active
        self.last_message_time = -math.inf

    def decide(self, t: float, alerts: list[Alert]) -> Alert | None:
        """Return the one alert to speak now, or None (silence)."""
        present = {a.key for a in alerts}
        self.first_seen = {k: v for k, v in self.first_seen.items() if k in present}
        for a in alerts:
            self.first_seen.setdefault(a.key, t)
            self.last_present[a.key] = t
        # Something that disappeared for a while and comes back is a new event: without this,
        # keys like "path" would stay muted forever after the first announcement.
        for key in [k for k, seen in self.last_present.items()
                    if k not in present and t - seen > FORGET_AFTER]:
            del self.last_present[key]
            self.spoken.pop(key, None)

        for a in alerts:  # already sorted: most urgent first
            if self._should_say(t, a):
                self.spoken[a.key] = (t, a.level, a.distance)
                self.last_message_time = t
                return a
        return None

    def _should_say(self, t: float, a: Alert) -> bool:
        if not a.path_priority and t - self.first_seen[a.key] < MIN_PERSISTENCE:
            return False  # might be a 1-frame false positive (remember the hydrant)
        if not a.path_priority and a.level < URGENT and t - self.last_message_time < MIN_GAP:
            return False  # only an URGENT alert may cut in right after another message

        previous = self.spoken.get(a.key)
        if previous is None:
            return True   # never talked about this one
        when, level, distance = previous
        if a.level > level:
            return True   # escalation: it became more dangerous since we last said it
        # Same danger still there: remind only after a while, and only if it got closer.
        return t - when > REPEAT_AFTER and distance - a.distance > REPEAT_IF_CLOSER


# ----- Message wording -----------------------------------------------------------------

LABELS = {
    "en": {"door_open": "door open", "door_closed": "door closed",
           "stairs_up": "stairs going up", "stairs_down": "stairs going down"},
    "fr": {"person": "personne", "bicycle": "vélo", "car": "voiture", "motorcycle": "moto",
           "bus": "bus", "truck": "camion", "train": "train", "traffic light": "feu",
           "stop sign": "panneau stop", "fire hydrant": "borne incendie",
           "parking meter": "horodateur", "bench": "banc", "chair": "chaise",
           "potted plant": "plante", "dog": "chien", "cat": "chat", "suitcase": "valise",
           "obstacle": "obstacle", "stairs": "escalier", "pole": "poteau", "pillar": "pilier",
           "cone": "cône", "bin": "poubelle", "stairs_up": "escalier montant",
           "stairs_down": "escalier descendant", "door_open": "porte ouverte",
           "door_closed": "porte fermée"},
}
TEMPLATES = {
    "en": {"ahead": "ahead", "clock": "at {h} o'clock", "near": "very close",
           "meters": "{n} meter", "meters_plural": "{n} meters", "stop": "Stop! ",
        "careful": "Careful, ",
           "approaching": "{label} approaching", "head": "Watch your head! ",
           "keep": "Keep {side}"},
    "fr": {"ahead": "devant", "clock": "à {h} heures", "near": "tout près",
           "meters": "{n} mètre", "meters_plural": "{n} mètres", "stop": "Stop ! ",
        "careful": "Attention, ",
           "approaching": "{label} qui approche", "head": "Attention à la tête ! ",
           "keep": "Gardez la {side}"},
}


def message(alert: Alert, lang: str = "en") -> str:
    """Short, always the same structure: [Stop!] <what> <where>, <how far>."""
    T = TEMPLATES[lang]
    label = LABELS.get(lang, {}).get(alert.label, alert.label)
    what = T["approaching"].format(label=label) if alert.approaching else label
    where = T["ahead"] if alert.clock == 12 else T["clock"].format(h=alert.clock)
    n = round(alert.distance)
    far = T["near"] if alert.distance < 1 else T["meters" if n == 1 else "meters_plural"].format(n=n)

    prefix = T["head"] if alert.head_level else (T["stop"] if alert.level == URGENT else "")
    if alert.label in {"stairs_up", "stairs_down"}:
        text = f"{T['careful']}{label} {where}, {far}"
        if alert.guidance:
            side = alert.guidance.capitalize() if lang == "en" else ("gauche" if alert.guidance == "left" else "droite")
            text += f". {T['keep'].format(side=side)}."
    elif alert.guidance:
        text = f"{prefix}Path blocked, {far}"
        side = alert.guidance.capitalize() if lang == "en" else ("gauche" if alert.guidance == "left" else "droite")
        text += f". {T['keep'].format(side=side)}."
    else:
        text = f"{prefix}{what} {where}, {far}"
    return text[0].upper() + text[1:]
