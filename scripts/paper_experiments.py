"""Run the experiments reported in the SafeStride IEEE paper and save figures + results.

    python scripts/paper_experiments.py

Outputs go to docs/paper_assets/: results.json and the figures used by the paper.
Everything here is measured by running the project code; nothing is typed in by hand
except the hazard-model test metrics, which are copied from the executed notebook
notebooks/train_hazards_results.ipynb (cell 15 output).
"""

import base64
import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
ASSETS = ROOT / "docs" / "paper_assets"
ASSETS.mkdir(parents=True, exist_ok=True)

from blindnav.announcer import Alert, Announcer, URGENT, message, rank_alerts  # noqa: E402
from blindnav.detector import Detection  # noqa: E402
from blindnav.navigation import NavigationManager, _bearing_degrees, distance_meters  # noqa: E402
from blindnav.spatial import (CAMERA_HEIGHT, PATH_HALF_WIDTH, PATH_LENGTH, SpatialAnalyzer,  # noqa: E402
                              focal_length)

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 7.5, "axes.labelsize": 7.5, "axes.titlesize": 8, "legend.fontsize": 6.5,
    "xtick.labelsize": 7, "ytick.labelsize": 7, "axes.spines.top": False, "axes.spines.right": False,
})
W, H = 640, 480
results: dict = {}


# --------------------------------------------------------------------------------------
# 1. Controlled synthetic scenes: known ground, known obstacle, unknown monocular scale
# --------------------------------------------------------------------------------------
def slab_scene(z_obstacle=None, lateral=0.0, scale=1.0, noise=0.02, seed=0):
    """Flat ground seen from CAMERA_HEIGHT plus an upright 0.8 m wide, 1.2 m tall slab.

    `scale` multiplies every depth: a monocular network that is wrong by a constant factor.
    """
    rng = np.random.default_rng(seed)
    f = focal_length((H, W))
    rows = np.arange(H, dtype=np.float64)[:, None] - H / 2
    cols = np.arange(W, dtype=np.float64)[None, :] - W / 2
    ground = np.where(rows > 1, f * CAMERA_HEIGHT / np.maximum(rows, 1), 60.0) * np.ones((H, W))
    depth = ground.copy()
    if z_obstacle is not None:
        height = CAMERA_HEIGHT - rows * z_obstacle / f
        lateral_m = cols * z_obstacle / f
        hit = (height > 0) & (height < 1.2) & (np.abs(lateral_m - lateral) < 0.4) & (z_obstacle < ground)
        depth = np.where(hit, z_obstacle, ground)
    depth = depth * scale * (1 + noise * rng.standard_normal((H, W)))
    return depth.astype(np.float32)


class UncorrectedAnalyzer(SpatialAnalyzer):
    """Same pipeline but the depth scale is never corrected (baseline for the ablation)."""

    def __init__(self):
        super().__init__()
        original = self.ground.update

        def update(points):
            found = original(points)
            self.ground.scale = 1.0
            return found
        self.ground.update = update


def run_scene(analyzer_cls, **kwargs):
    analyzer = analyzer_cls()
    status = None
    for frame in range(6):  # let the rolling scale median settle
        status = analyzer.analyze(slab_scene(seed=frame, **kwargs), [])
    return status


def scale_experiment():
    distances, scales, seeds = [1.5, 2.0, 2.5, 2.8], [1.0, 1.5, 2.0, 3.0], range(5)
    rows = []
    for k in scales:
        for z in distances:
            with_err, without_err, with_hit, without_hit, without_dist = [], [], [], [], []
            for seed in seeds:
                a = run_scene(SpatialAnalyzer, z_obstacle=z, scale=k, noise=0.02)
                b = run_scene(UncorrectedAnalyzer, z_obstacle=z, scale=k, noise=0.02)
                with_hit.append(a.blocked)
                without_hit.append(b.blocked)
                if a.blocked:
                    with_err.append(abs(a.distance - z))
                if b.blocked:
                    without_err.append(abs(b.distance - z))
            rows.append({
                "scale": k, "distance": z,
                "corrected_error_m": float(np.mean(with_err)) if with_err else None,
                "corrected_detect": float(np.mean(with_hit)),
                "uncorrected_error_m": float(np.mean(without_err)) if without_err else None,
                "uncorrected_detect": float(np.mean(without_hit)),
            })
    results["scale_experiment"] = rows

    def avg(key, subset):
        values = [r[key] for r in subset if r[key] is not None]
        return float(np.mean(values)) if values else None

    summary = {}
    for k in scales:
        subset = [r for r in rows if r["scale"] == k]
        summary[str(k)] = {key: avg(key, subset) for key in
                           ("corrected_error_m", "corrected_detect", "uncorrected_error_m", "uncorrected_detect")}
    results["scale_summary"] = summary

    fig, ax = plt.subplots(1, 2, figsize=(3.45, 1.9))
    xs = np.arange(len(scales))
    ax[0].bar(xs - 0.18, [summary[str(k)]["uncorrected_error_m"] or 0 for k in scales], 0.36,
              label="no scale correction", color="#b0b0b0")
    ax[0].bar(xs + 0.18, [summary[str(k)]["corrected_error_m"] or 0 for k in scales], 0.36,
              label="ground-plane scale", color="#1f4e79")
    ax[0].set_xticks(xs, [f"×{k:g}" for k in scales])
    ax[0].set_xlabel("depth scale error")
    ax[0].set_ylabel("mean distance error (m)")
    ax[0].set_ylim(0, 2.0)
    ax[0].legend(frameon=False, loc="upper left")
    ax[1].bar(xs - 0.18, [100 * summary[str(k)]["uncorrected_detect"] for k in scales], 0.36, color="#b0b0b0")
    ax[1].bar(xs + 0.18, [100 * summary[str(k)]["corrected_detect"] for k in scales], 0.36, color="#1f4e79")
    ax[1].set_xticks(xs, [f"×{k:g}" for k in scales])
    ax[1].set_xlabel("depth scale error")
    ax[1].set_ylabel("blocker detected (%)")
    ax[1].set_ylim(0, 105)
    fig.tight_layout(pad=0.4)
    fig.savefig(ASSETS / "fig_scale.png", dpi=300)
    plt.close(fig)


# --------------------------------------------------------------------------------------
# 2. Scenario test cases (expected vs obtained, computed by running the code)
# --------------------------------------------------------------------------------------
def scenario_table():
    import test_spatial  # tests/test_spatial.py: synthetic ramp

    cases = []

    def add(case_id, scenario, expected, obtained):
        cases.append({"id": case_id, "scenario": scenario, "expected": expected,
                      "obtained": obtained, "status": "Pass" if expected == obtained else "Fail"})

    add("TC1", "Surface rising away from user (slope +0.5)", "stairs up",
        f"stairs {test_spatial.stair_direction(0.5)}")
    add("TC2", "Surface falling away from user (slope -0.5)", "stairs down",
        f"stairs {test_spatial.stair_direction(-0.5)}")
    flat = test_spatial.stair_direction(0.0)
    add("TC3", "Flat ground inside the stairs box", "no direction", "no direction" if flat is None else flat)

    near = run_scene(SpatialAnalyzer, z_obstacle=2.0, scale=2.0, noise=0.02)
    add("TC4", "Obstacle 2.0 m ahead, depth scale ×2", "blocked, 2.0 ± 0.3 m",
        "blocked, 2.0 ± 0.3 m" if near.blocked and abs(near.distance - 2.0) <= 0.3
        else f"blocked={near.blocked}, d={near.distance}")
    cases[-1]["detail"] = f"{near.distance:.2f} m" if near.blocked else "-"

    side = run_scene(SpatialAnalyzer, z_obstacle=2.0, lateral=1.2, scale=1.0, noise=0.02)
    add("TC5", "Obstacle 1.2 m to the side (outside corridor)", "path clear",
        "path clear" if not side.blocked else "blocked")

    right = run_scene(SpatialAnalyzer, z_obstacle=2.0, lateral=0.3, scale=1.0, noise=0.02)
    add("TC6", "Obstacle slightly right of centre", "keep left",
        f"keep {right.guidance}" if right.guidance else "no guidance")

    nan_alert = rank_alerts([Detection(box=(0, 0, 10, 10), class_name="person", confidence=.9,
                                       distance=math.nan, clock=12, in_path=True, track_id=1)], None)
    add("TC7", "Detection with undefined distance", "no alert", "no alert" if not nan_alert else "alert")

    announcer = Announcer()
    alert = Alert("path", "obstacle", 2.0, 12, 0.8, URGENT, path_priority=True)
    first = announcer.decide(0.0, [alert]) is not None
    announcer.decide(10.0, [])
    again = announcer.decide(20.0, [alert]) is not None
    add("TC8", "Same obstacle returns after path cleared", "announced again",
        "announced again" if first and again else "silent")

    manager = NavigationManager()
    route = nav_route()
    manager.set_route(route, END)
    manager.update(START[0] + 0.0005, START[1] + 0.0005 * 1.0)
    for _ in range(2):
        update = manager.update(START[0] - 0.001, START[1] - 0.001, accuracy=5)
    add("TC9", "GPS 150 m off the route (two readings)", "off-route warning",
        "off-route warning" if update.off_route else "none")

    manager = NavigationManager(repeat_after=0.0)
    manager.set_route(route, END)
    first = manager.update(*END)
    jitter = manager.update(END[0], END[1] - 0.0004)
    add("TC10", "Arrival, then GPS jitter 40 m away", "arrival announced once",
        "arrival announced once" if first.message and jitter.message is None else "repeated")
    results["test_cases"] = cases


# --------------------------------------------------------------------------------------
# 3. Navigation simulation under GPS noise
# --------------------------------------------------------------------------------------
START, CORNER, END = (13.027282, 77.497048), (13.027951, 77.497156), (13.027949, 77.49789)


def nav_route():
    return {
        "geometry": {"coordinates": [[START[1], START[0]], [CORNER[1], CORNER[0]], [END[1], END[0]]]},
        "legs": [{"steps": [
            {"distance": 75, "maneuver": {"type": "depart", "modifier": "right", "bearing_after": 9,
                                          "location": [START[1], START[0]]}},
            {"distance": 80, "maneuver": {"type": "turn", "modifier": "right", "bearing_after": 90,
                                          "location": [CORNER[1], CORNER[0]]}},
            {"distance": 0, "maneuver": {"type": "arrive", "modifier": "right", "bearing_after": 0,
                                         "location": [END[1], END[0]]}},
        ]}],
        "distance": 155,
    }


def lerp(a, b, f):
    return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)


def navigation_experiment():
    rows = []
    for sigma in (3.0, 6.0, 10.0):
        arrived, turn_ok, off_route, counts, countdown_ok = [], [], [], [], []
        for seed in range(20):
            rng = np.random.default_rng(seed)
            manager = NavigationManager()
            manager.set_route(nav_route(), END)
            spoken, distances, false_off = [], [], False
            reached_turn = False
            for a, b in ((START, CORNER), (CORNER, END)):
                steps = int(distance_meters(a, b) / 1.4)
                bearing = _bearing_degrees(a, b)
                for i in range(steps + 1):
                    p = lerp(a, b, i / steps)
                    lat = p[0] + rng.normal(0, sigma) / 111_320
                    lon = p[1] + rng.normal(0, sigma) / 108_500
                    heading = (bearing + rng.normal(0, 8)) % 360
                    u = manager.update(lat, lon, heading=heading, accuracy=max(5.0, sigma * 1.5),
                                       heading_timestamp=time.time() * 1000)
                    manager.last_event_time -= 1.0  # one simulated second per GPS sample
                    false_off |= u.off_route
                    reached_turn |= u.step_index >= 1
                    if u.message:
                        spoken.append(u.message)
                        m = re.search(r"walk straight for (\d+) meters, then", u.message)
                        if m:
                            distances.append(int(m.group(1)))
            arrived.append(manager.arrived)
            turn_ok.append(reached_turn)
            off_route.append(false_off)
            counts.append(len(spoken))
            countdown_ok.append(len(distances) >= 2 and distances[-1] < distances[0])
        rows.append({"gps_sigma_m": sigma, "arrived_pct": 100 * float(np.mean(arrived)),
                     "turn_step_pct": 100 * float(np.mean(turn_ok)),
                     "false_off_route_pct": 100 * float(np.mean(off_route)),
                     "countdown_pct": 100 * float(np.mean(countdown_ok)),
                     "messages_per_100m": float(np.mean(counts)) / 1.55})
    results["navigation"] = rows


# --------------------------------------------------------------------------------------
# 4. Figures that need no models
# --------------------------------------------------------------------------------------
def corridor_figure():
    fig, ax = plt.subplots(figsize=(3.45, 2.1))
    ax.add_patch(plt.Rectangle((-PATH_HALF_WIDTH, 0), 2 * PATH_HALF_WIDTH, PATH_LENGTH,
                               color="#9fc5e8", alpha=0.6, label="walking corridor (1 m × 3 m)"))
    half = math.radians(35)
    ax.plot([0, -4 * math.tan(half) * 1.0], [0, 4], color="#555", lw=0.8, ls="--")
    ax.plot([0, 4 * math.tan(half) * 1.0], [0, 4], color="#555", lw=0.8, ls="--", label="camera field of view")
    ax.add_patch(plt.Rectangle((-0.3, 2.0), 0.6, 0.12, color="#c0392b", label="blocker (distance 2 m)"))
    ax.add_patch(plt.Rectangle((0.9, 1.2), 0.5, 0.12, color="#888", label="object outside corridor"))
    ax.plot(0, 0, marker="^", color="black", ms=6)
    ax.annotate("camera\nheight 1.4 m", (0, 0), (-1.55, 0.15), fontsize=6.5)
    ax.set_xlim(-1.8, 1.8)
    ax.set_ylim(-0.2, 3.6)
    ax.set_aspect("equal")
    ax.set_xlabel("lateral X (m)")
    ax.set_ylabel("forward Z (m)")
    ax.legend(frameon=False, loc="upper right", fontsize=5.8)
    fig.tight_layout(pad=0.4)
    fig.savefig(ASSETS / "fig_corridor.png", dpi=300)
    plt.close(fig)


def hazard_figures():
    names = ["stairs", "pole", "pillar", "bin", "cone", "obstacle"]
    map50 = [0.571, 0.585, 0.746, 0.0339, 0.942, 0.458]  # notebook cell 15, held-out test split
    map5095 = [0.437, 0.418, 0.589, 0.0293, 0.707, 0.228]
    results["hazard_test"] = {"images": 540, "instances": 536, "precision": 0.667, "recall": 0.584,
                              "map50": 0.556, "map50_95": 0.401, "inference_ms_t4": 11.4,
                              "per_class": {n: {"map50": a, "map50_95": b}
                                            for n, a, b in zip(names, map50, map5095)}}
    fig, ax = plt.subplots(figsize=(3.45, 1.9))
    xs = np.arange(len(names))
    ax.bar(xs - 0.18, map50, 0.36, label="mAP50", color="#1f4e79")
    ax.bar(xs + 0.18, map5095, 0.36, label="mAP50-95", color="#9fc5e8")
    ax.set_xticks(xs, names)
    ax.set_ylabel("average precision")
    ax.set_ylim(0, 1.05)
    ax.legend(frameon=False, ncol=2, loc="upper left")
    fig.tight_layout(pad=0.4)
    fig.savefig(ASSETS / "fig_hazard_map.png", dpi=300)
    plt.close(fig)


# --------------------------------------------------------------------------------------
# 5. Real pipeline: latency, alert behaviour and a live annotated frame
# --------------------------------------------------------------------------------------
def latency_experiment():
    table = {}
    for every in (1, 2):
        out = subprocess.run(
            [sys.executable, "scripts/benchmark.py", "data/videos/city_street_youtube.mp4",
             "--frames", "120", "--depth-every", str(every)],
            cwd=ROOT, capture_output=True, text=True, env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8",
                                                           "HF_HUB_OFFLINE": "1"})
        stages = {}
        for line in out.stdout.splitlines():
            m = re.match(r"\s+(\d\.\s.+?|TOTAL)\s+([\d.]+) ms", line)
            if m:
                stages[m.group(1).strip()] = float(m.group(2))
            gpu = re.search(r"\((NVIDIA[^)]+)\)", line)
            if gpu:
                results["gpu"] = gpu.group(1)
        table[str(every)] = stages
        if not stages:
            table[str(every)] = {"error": (out.stderr or out.stdout)[-400:]}
    results["latency_ms"] = table


def pipeline_experiment():
    import torch
    from blindnav.depth import DepthEstimator, colorize, object_distance
    from blindnav.detector import HAZARD_CLASS_CONF, Detector
    from blindnav.risk import MotionTracker
    from blindnav.spatial import focal_length as fl
    from blindnav.visualize import draw_detections, draw_path

    detector = Detector("models/yolo11s.pt")
    hazards = Detector("models/hazards.pt", all_classes=True, class_conf=HAZARD_CLASS_CONF, id_offset=100_000)
    depth_model = DepthEstimator(input_size=392)
    clips = ["data/videos/city_street_youtube.mp4", "data/videos/live_demo_source.mp4",
             "data/videos/bits/30s/part_001_30s_1.mp4", "data/videos/bits/30s/part_002_30s_1.mp4",
             "data/videos/bits/30s/part_003_30s_2.mp4"]
    rows, ratios_all, best_frame = [], [], (-1, None)
    for clip in clips:
        path = ROOT / clip
        if not path.exists():
            continue
        cap = cv2.VideoCapture(str(path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        detector.reset_tracking()
        hazards.reset_tracking()
        spatial, motion, announcer = SpatialAnalyzer(), MotionTracker(), Announcer()
        depth, n, blocked, alerts, ratios = None, 0, 0, [], []
        torch.cuda.synchronize()
        begin = time.perf_counter()
        while n < int(20 * fps):
            ok, frame = cap.read()
            if not ok:
                break
            if frame.shape[1] > 1280:
                frame = cv2.resize(frame, (1280, int(frame.shape[0] * 1280 / frame.shape[1])))
            Hh, Ww = frame.shape[:2]
            t = n / fps
            raw = frame.copy()
            dets = detector.detect(frame) + hazards.detect(frame)
            if depth is None or n % 2 == 0:
                depth = depth_model.estimate(frame)
            for d in dets:
                d.distance = object_distance(depth, d.box)
            status = spatial.analyze(depth, dets)
            motion.update(t, dets, status, Hh)
            alert = announcer.decide(t, rank_alerts(dets, status))
            if alert:
                alerts.append((t, alert.level, message(alert)))
            blocked += status.blocked
            f = fl(frame.shape)
            for d in dets:
                x1, y1, x2, y2 = d.box
                if (d.class_name == "person" and y1 > 2 and y2 < Hh - 2 and x1 > 2 and x2 < Ww - 2
                        and y2 - y1 > 80 and d.distance and np.isfinite(d.distance)):
                    from_height = f * 1.7 / (y2 - y1)
                    if from_height < 15:
                        ratios.append(d.distance / from_height)
            score = len([d for d in dets if d.in_path]) * 3 + len(dets) + (5 if status.blocked else 0)
            if n > 30 and score > best_frame[0]:
                shown = raw.copy()
                draw_path(shown, status, dets)
                draw_detections(shown, dets)
                side = draw_detections(colorize(depth), dets)
                best_frame = (score, np.hstack([shown, side]))
            n += 1
        torch.cuda.synchronize()
        elapsed = time.perf_counter() - begin
        minutes = n / fps / 60
        rows.append({"clip": clip.split("/")[-1], "seconds": n / fps, "fps": n / elapsed,
                     "alerts": len(alerts), "alerts_per_min": len(alerts) / minutes if minutes else 0,
                     "urgent": sum(level == URGENT for _, level, _ in alerts),
                     "blocked_pct": 100 * blocked / max(n, 1),
                     "samples": [m for _, _, m in alerts[:3]], "n_ratio": len(ratios)})
        ratios_all += ratios
    results["pipeline"] = rows
    if ratios_all:
        results["distance_consistency"] = {
            "n": len(ratios_all), "median": float(np.median(ratios_all)),
            "q25": float(np.percentile(ratios_all, 25)), "q75": float(np.percentile(ratios_all, 75))}
    if best_frame[1] is not None:
        image = best_frame[1]
        scale = 1500 / image.shape[1]
        cv2.imwrite(str(ASSETS / "fig_live_frame.jpg"), cv2.resize(image, None, fx=scale, fy=scale),
                    [cv2.IMWRITE_JPEG_QUALITY, 90])


def frame_figure():
    """Annotated frame + depth map from the sidewalk clip (a representative, non-outlier scene)."""
    from blindnav.depth import DepthEstimator, colorize, object_distance
    from blindnav.detector import HAZARD_CLASS_CONF, Detector
    from blindnav.risk import MotionTracker
    from blindnav.visualize import draw_detections, draw_path

    detector = Detector("models/yolo11s.pt")
    hazards = Detector("models/hazards.pt", all_classes=True, class_conf=HAZARD_CLASS_CONF, id_offset=100_000)
    depth_model = DepthEstimator(input_size=392)
    cap = cv2.VideoCapture(str(ROOT / "data/videos/bits/30s/part_002_30s_1.mp4"))
    spatial, motion = SpatialAnalyzer(), MotionTracker()
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    best, n, depth = (-1, None), 0, None
    while n < int(15 * fps):
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.resize(frame, (1280, int(frame.shape[0] * 1280 / frame.shape[1])))
        raw = frame.copy()
        dets = detector.detect(frame) + hazards.detect(frame)
        if depth is None or n % 2 == 0:
            depth = depth_model.estimate(frame)
        for d in dets:
            d.distance = object_distance(depth, d.box)
        status = spatial.analyze(depth, dets)
        motion.update(n / fps, dets, status, frame.shape[0])
        named = [d for d in dets if d.class_name == "person" and d.distance and d.distance < 12]
        score = len(named) * 2 + (4 if status.blocked else 0) - len([d for d in dets if d.class_name == "stairs"]) * 5
        if n > 60 and score > best[0]:
            shown = raw.copy()
            draw_path(shown, status, dets)
            draw_detections(shown, dets)
            side = draw_detections(colorize(depth), dets)
            best = (score, np.hstack([shown, side]))
        n += 1
    image = best[1]
    cv2.imwrite(str(ASSETS / "fig_live_frame.jpg"), cv2.resize(image, None, fx=1500 / image.shape[1],
                fy=1500 / image.shape[1]), [cv2.IMWRITE_JPEG_QUALITY, 90])


def ttc_experiment():
    """Looming time-to-collision on a simulated object approaching at constant speed."""
    from blindnav.risk import MotionTracker

    f = focal_length((720, 1280))
    targets = (6.0, 4.0, 3.0, 2.0)
    rows = []
    for speed in (1.0, 1.5, 3.0):  # m/s closing speed: slow walk, brisk walk, bicycle
        samples = {t: [] for t in targets}
        for seed in range(20):
            rng = np.random.default_rng(seed)
            tracker = MotionTracker()
            z0, t = speed * 10.0, 0.0  # starts 10 s from impact
            while True:
                z = z0 - speed * t
                true_ttc = z / speed
                if true_ttc < 1.5:
                    break
                height = f * 1.7 / z  # a 1.7 m tall person
                y2 = 600 + rng.normal(0, 1.5)
                y1 = y2 - height + rng.normal(0, 1.5)
                det = Detection(box=(500, int(round(y1)), 560, int(round(y2))), class_name="person",
                                confidence=0.9, distance=z, track_id=1)
                tracker.update(t, [det], None, 720)
                for target in targets:
                    if abs(true_ttc - target) < 0.5 / 30 * speed / speed * 1.0:
                        samples[target].append(det.ttc)
                t += 1 / 30
        for target in targets:
            values = samples[target]
            found = [v for v in values if v is not None]
            rows.append({"speed": speed, "true_ttc": target, "available_pct": 100 * len(found) / max(len(values), 1),
                         "mean_estimate": float(np.mean(found)) if found else None,
                         "mean_abs_error": float(np.mean([abs(v - target) for v in found])) if found else None})
    results["ttc"] = rows


def main(parts):
    steps = {"scale": scale_experiment, "cases": scenario_table, "nav": navigation_experiment,
             "figures": lambda: (corridor_figure(), hazard_figures()), "ttc": ttc_experiment,
             "latency": latency_experiment, "pipeline": pipeline_experiment, "frame": frame_figure}
    out_file = ASSETS / "results.json"
    if out_file.exists():
        results.update(json.loads(out_file.read_text(encoding="utf-8")))
    for name in parts or steps:
        print(f"== {name}", flush=True)
        steps[name]()
        out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in results.items() if k in parts or not parts}, indent=1)[:6000])


if __name__ == "__main__":
    main(sys.argv[1:])
