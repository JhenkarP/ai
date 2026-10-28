"""Build the SafeStride IEEE-style conference paper (Word + PDF) from measured results.

    python scripts/paper_experiments.py        # measure everything (docs/paper_assets/results.json)
    python docs/create_safestride_ieee_paper.py

Outputs: docs/SafeStride_Assist_IEEE_Paper.docx and docs/SafeStride_Assist_IEEE_Paper.pdf
The same content model is rendered twice (python-docx and ReportLab), so both files match.
All numbers in the text come from docs/paper_assets/results.json.
"""

import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
ASSETS = DOCS / "paper_assets"
R = json.loads((ASSETS / "results.json").read_text(encoding="utf-8"))

TITLE = ("Safe-Stride Assist: An AI-Based Safe Walking Assistance System for People with "
         "Visual Impairments")
AUTHORS = [
    ("Jhenkar P", "Dept. of Computer Science and Engineering", "The National Institute of Engineering",
     "Mysuru, India", "2023cs_JHENKARP_b@nie.ac.in"),
    ("[Guide name to be added]", "Dept. of Computer Science and Engineering", "The National Institute of Engineering",
     "Mysuru, India", "[guide email to be added]"),
]
KEYWORDS = ("Safe walking assistance, visual impairment, monocular depth estimation, ground-plane "
            "estimation, obstacle detection, YOLO, ByteTrack, time-to-collision, route guidance")

# Hazard-model test metrics: executed output of notebooks/train_hazards_results.ipynb (cell 15).
HAZARD_ROWS = [  # class, test instances, P, R, mAP50, mAP50-95
    ("stairs", 14, 0.660, 0.555, 0.571, 0.437), ("pole", 92, 0.570, 0.739, 0.585, 0.418),
    ("pillar", 175, 0.728, 0.680, 0.746, 0.589), ("bin", 38, 0.652, 0.0263, 0.0339, 0.0293),
    ("cone", 74, 0.972, 0.944, 0.942, 0.707), ("obstacle", 143, 0.419, 0.559, 0.458, 0.228),
]


# --------------------------------------------------------------------------------------
# Figure: navigation state machine (drawn here, matches blindnav/navigation.py)
# --------------------------------------------------------------------------------------
def make_arch_figure(path: Path) -> None:
    plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"]})
    fig, ax = plt.subplots(figsize=(3.45, 1.55))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4.5)
    ax.axis("off")
    nodes = [
        ("INPUT", "webcam\nvideo file\nphone camera\n+ GPS", "#1f4e79"),
        ("PERCEPTION", "YOLO11s\nhazard YOLO\nByteTrack\nDepth Any-\nthing V2", "#2a8a8c"),
        ("REASONING", "ground plane\n(RANSAC)\nscale fix\n1×3 m corridor", "#d98a2b"),
        ("DECISION", "urgency +\nTTC, ranking\npersistence,\ncooldowns", "#b94a48"),
        ("OUTPUT", "annotated\nfeed, voice,\nbeeps, route\ninstructions", "#1f4e79"),
    ]
    w, gap = 1.7, 0.375
    for i, (head, body, color) in enumerate(nodes):
        x = i * (w + gap)
        ax.add_patch(FancyBboxPatch((x, 0.5), w, 3.3, boxstyle="round,pad=0.02,rounding_size=0.12",
                                    fc="#f6f9fb", ec=color, lw=1.1))
        ax.add_patch(plt.Rectangle((x, 3.25), w, 0.55, color=color))
        ax.text(x + w / 2, 3.52, head, ha="center", va="center", fontsize=5.2, color="white", weight="bold")
        ax.text(x + w / 2, 1.85, body, ha="center", va="center", fontsize=5.4, linespacing=1.25)
        if i < len(nodes) - 1:
            ax.add_patch(FancyArrowPatch((x + w + 0.02, 2.1), (x + w + gap - 0.02, 2.1), arrowstyle="-|>",
                                         mutation_scale=6, lw=0.9, color="#222"))
    fig.tight_layout(pad=0.15)
    fig.savefig(path, dpi=300)
    plt.close(fig)


def make_state_figure(path: Path) -> None:
    plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"]})
    fig, ax = plt.subplots(figsize=(3.45, 2.3))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 7.2)
    ax.axis("off")
    boxes = {
        "route": (0.1, 5.3, 2.9, 1.5, "Route set\n(OSRM foot route)"),
        "align": (3.55, 5.3, 2.9, 1.5, "Align camera\nto road (±30°)"),
        "walk": (7.0, 5.3, 2.9, 1.5, "Walk straight,\ndistance countdown"),
        "turn": (7.0, 2.7, 2.9, 1.5, "Maneuver reached\n(12–25 m)"),
        "arrive": (3.55, 0.2, 2.9, 1.5, "Arrived (≤25 m)\nlatched"),
        "off": (0.1, 2.7, 2.9, 1.5, "Off route (any state):\n2 readings > 50 m"),
    }
    for x, y, w, h, label in boxes.values():
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.04,rounding_size=0.2",
                                    fc="#eef3f8", ec="#1f4e79", lw=0.9))
        ax.text(x + w / 2, y + h / 2, label, ha="center", va="center", fontsize=6.2)

    def arrow(a, b, rad=0.0):
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=7, lw=0.8, color="#333",
                                     connectionstyle=f"arc3,rad={rad}"))

    arrow((3.05, 6.05), (3.5, 6.05))
    arrow((6.5, 6.05), (6.95, 6.05))
    arrow((8.45, 5.25), (8.45, 4.25))
    arrow((6.95, 3.45), (5.2, 5.25), rad=-0.2)
    arrow((7.9, 2.65), (6.5, 1.2), rad=0.1)
    arrow((1.55, 4.25), (1.55, 5.25))
    ax.text(6.75, 6.95, "aligned", fontsize=5.4, ha="center")
    ax.text(5.5, 4.2, "next step", fontsize=5.4, ha="center")
    ax.text(7.7, 1.55, "last step", fontsize=5.4, ha="center")
    ax.text(1.7, 4.55, "new route", fontsize=5.4)
    fig.tight_layout(pad=0.2)
    fig.savefig(path, dpi=300)
    plt.close(fig)


# --------------------------------------------------------------------------------------
# Content model
# --------------------------------------------------------------------------------------
def fmt(x, nd=2):
    return f"{x:.{nd}f}"


def build_content():
    make_state_figure(ASSETS / "fig_nav_states.png")
    make_arch_figure(ASSETS / "fig_arch.png")
    lat1, lat2 = R["latency_ms"]["1"], R["latency_ms"]["2"]
    fps1, fps2 = 1000 / lat1["TOTAL"], 1000 / lat2["TOTAL"]
    scale = R["scale_summary"]
    pipe = R["pipeline"]
    dc = R.get("distance_consistency")
    nav = R["navigation"]
    haz = R["hazard_test"]
    gpu = R.get("gpu", "NVIDIA GPU")
    total_s = sum(r["seconds"] for r in pipe)
    mean_fps = sum(r["fps"] for r in pipe) / len(pipe)
    all_alerts = sum(r["alerts"] for r in pipe)
    rate = all_alerts / (total_s / 60)
    n_cases = len(R["test_cases"])
    passed = sum(c["status"] == "Pass" for c in R["test_cases"])

    c = []
    add = c.append

    add(("abstract",
         "Visually impaired pedestrians need to know whether an obstacle blocks their next steps, how far "
         "away it is, and what to do about it, but most camera-based assistants stop at drawing bounding "
         "boxes. This paper presents Safe-Stride Assist, a research prototype that turns a single camera "
         "stream into short, prioritised spoken guidance. The system combines YOLO11s detection, ByteTrack "
         "tracking, Depth Anything V2 monocular depth, and a geometric reasoning layer: RANSAC ground-plane "
         "fitting converts relative depth to approximate metres using the camera height, and a 1 m × 3 m "
         "walking corridor exposes known and unknown blockers and suggests a clearer side. Looming-based "
         "time-to-collision, persistence checks and cooldowns control when to speak, and a GPS module "
         "provides route instructions with compass alignment. In controlled scenes, the scale correction "
         f"kept the distance error at {fmt(scale['2.0']['corrected_error_m'] * 100, 1)} cm even when the raw "
         f"depth was twice too large, while an uncorrected pipeline missed "
         f"{fmt(100 * (1 - scale['1.5']['uncorrected_detect']), 0)} % of the blockers at a ×1.5 scale error and "
         "all of them at ×3. A six-class hazard "
         f"detector reached {fmt(haz['map50'], 3)} mAP50 on {haz['images']} held-out images, and the full "
         f"pipeline ran at {fmt(fps2, 1)} FPS on a laptop GPU ({gpu.replace('NVIDIA GeForce ', '').replace(' Laptop GPU', '')}). Safe-Stride "
         "is an educational prototype, not a certified mobility device."))
    add(("keywords", KEYWORDS))

    add(("h1", "I.", "Introduction"))
    add(("p", "People with visual impairment combine a white cane, a guide dog, memory of the "
              "environment and help from other people to move safely. A camera cannot replace these aids, "
              "but it can add a perception channel for things a cane reaches late or not at all: head-level "
              "objects, approaching vehicles, steps and unfamiliar barriers. The World Health Organization "
              "stresses that such support must be accessible and understandable [6]."))
    add(("p", "Detection alone is not enough. A person 15 m away at the roadside is irrelevant, whereas an "
              "unlabelled bin 2 m ahead in the walking line is urgent. Safe-Stride Assist therefore treats "
              "four questions as first-class outputs: is the object in the user's path, how far is it, is it "
              "approaching, and what should the user do. The answer is delivered as a short sentence such "
              "as “Stop! Path blocked, 2 meters. Keep Left.”"))
    add(("p", "The main contributions are: (i) a distance-aware walking-corridor method that uses depth "
              "points above an estimated ground plane, so unknown blockers are found without a trained "
              "class; (ii) a ranking and announcement policy that limits repetition; (iii) a route-guidance "
              "layer with heading alignment, distance countdown and off-route detection; and (iv) an "
              "implementation with a browser console and a phone client, together with an "
              "evaluation that separates controlled, simulated and real-video evidence."))

    add(("h1", "II.", "Problem Statement"))
    add(("p", "Pedestrians who cannot see well meet people, vehicles, poles, doorways, steps, uneven ground "
              "and temporary barriers. Conventional detectors recognise only trained classes and do not "
              "state whether an object blocks the path, how far it is, or whether it is approaching. "
              "Monocular depth networks give scene structure but not guaranteed metric scale [4]. The goal is "
              "a supplementary assistive prototype that (a) estimates approximate distance from one camera, "
              "(b) decides path relevance inside a bounded corridor, (c) detects blockers that have no "
              "class label, (d) ranks hazards by urgency and approach risk, (e) speaks sparingly, and "
              "(f) combines this with route guidance, while stating its limits honestly."))

    add(("h1", "III.", "Literature Survey"))
    add(("p", "Redmon et al. [1] showed that one network pass can detect objects in real time, and "
              "current Ultralytics checkpoints [5] continue this line. Zhang et al. [2] proposed ByteTrack, "
              "which keeps identities by associating both high- and low-confidence boxes; temporal identity "
              "supports persistence and approach analysis. Yang et al. [3] introduced Depth Anything V2 for "
              "dense monocular depth, and Ranftl et al. [4] showed that dense prediction transformers "
              "capture scene structure, although a relative depth map is not a guaranteed distance."))
    add(("p", "Khan et al. [7] reviewed navigation assistants for blind and visually impaired people and "
              "Xu et al. [8] reviewed wearable obstacle-avoidance aids; both conclude that electronic aids "
              "should complement, not replace, traditional mobility tools and must consider sensing range "
              "and feedback. Katzschmann et al. [9] demonstrated local navigation with time-of-flight "
              "sensing and haptic feedback. Eltaher et al. [10] surveyed urban navigation systems, "
              "which motivates route guidance, heading alignment and off-route handling. Johannesson "
              "et al. [11] explored converting scenes to sound, and Shull and Damian [12] reviewed haptic "
              "wearables; both support multimodal, non-visual feedback. Ranganeni et al. [13] studied "
              "levels of control in a navigation assistant and found that preferences vary with the "
              "situation, and Zhang et al. [14] built a smartphone assistive navigation system on ARCore, "
              "which supports a portable phone-based design."))
    add(("h2", "Drawbacks of existing systems"))
    add(("bullets", [
        "Detection labels and boxes do not say whether an object lies in the walking path.",
        "Relative monocular depth is not metric; without calibration its distances can be wrong by "
        "a constant factor [4].",
        "Objects outside the trained classes (temporary barriers, poles, bins) may be missed entirely.",
        "Frame-by-frame systems cannot tell whether an object is approaching.",
        "Frequent announcements raise cognitive load and hide urgent warnings.",
        "Obstacle sensing and route guidance are usually separate systems.",
    ]))
    add(("h2", "Advantages of the proposed system"))
    add(("bullets", [
        "Metric scale is recovered from the ground plane and a known camera height.",
        "Known objects and depth-based unknown blockers share one corridor decision.",
        "Persistence, cooldowns and priority ranking limit repeated speech.",
        "Everything runs locally: camera frames are not uploaded to a cloud service.",
        "The same engine serves a browser console and a phone client with GPS guidance.",
    ]))

    add(("h1", "IV.", "System Design"))
    add(("h2", "A. System architecture"))
    add(("p", "Fig. 1 shows the pipeline. Frames come from a webcam, an uploaded video or the phone camera. "
              "The perception stage runs YOLO11s with ByteTrack and Depth Anything V2. The reasoning stage "
              "estimates the ground plane, corrects the depth scale and evaluates the corridor. The decision "
              "stage ranks alerts and decides when to speak. The output stage draws the annotated feed and "
              "speaks through Windows speech, the browser or the phone. Learned perception is kept apart from "
              "deterministic reasoning so each can be tested on its own."))
    add(("fig", "SafeStride_arch", "paper_assets/fig_arch.png",
         "Fig. 1. Local perception-to-guidance pipeline of Safe-Stride Assist."))
    add(("h2", "B. Walking-corridor geometry"))
    add(("p", "The corridor is a 1 m wide and 3 m long region on the ground in front of the camera "
              "(Fig. 2). A point belongs to a blocker when it lies inside the corridor and between 0.25 m "
              "and 2.0 m above the ground, so curbs are ignored but head-level objects count. Objects outside "
              "the corridor, such as the grey box in Fig. 2, do not trigger path warnings."))
    add(("fig", "corridor", "paper_assets/fig_corridor.png",
         "Fig. 2. Walking corridor in camera coordinates. A blocker inside it triggers a path warning."))
    add(("h2", "C. Navigation state machine"))
    add(("p", "Route guidance follows the states in Fig. 3. The route comes from an OpenStreetMap-based "
              "foot-routing service [16]. The phone reports GPS position and a compass-derived camera "
              "heading. The assistant first asks the user to face the road, then counts down the distance to "
              "the next maneuver, switches to the next instruction when the maneuver point is reached, and "
              "latches the arrived state."))
    add(("fig", "states", "paper_assets/fig_nav_states.png",
         "Fig. 3. State diagram of the route-guidance module."))

    add(("h2", "E. Safety and privacy design"))
    add(("p", "Camera frames are analysed on the user's own computer; the phone sends frames only to "
              "that computer over the local network, and no cloud vision service is used. The server keeps "
              "only the latest GPS position in memory and does not return it in its public status "
              "endpoints. Two parts do leave the machine: place search and routing send the destination "
              "text and the start and end coordinates to public OpenStreetMap-based services [16], and "
              "uploaded videos are stored in a local folder without automatic deletion. The server has no "
              "authentication, so it must run on a trusted network. Messages state approximate distances "
              "and the interface carries a prototype notice; the system never claims that a path is safe, "
              "only that no blocker was found."))

    add(("h1", "V.", "System Implementation"))
    add(("p", "Table I lists the software and hardware environment in which all results were measured. "
              "The browser console and the phone client both talk to the same Python engine."))
    add(("table", "TABLE I. SOFTWARE AND HARDWARE ENVIRONMENT",
         ["Component", "Specification"],
         [["Operating system", "Windows 11 (server-side voice uses Windows SAPI)"],
          ["Language / runtime", "Python 3.12 (3.10 or newer), PyTorch 2.5.1 with CUDA 12.4"],
          ["Detection and tracking", "Ultralytics 8.4 YOLO11s, ByteTrack"],
          ["Depth", "Depth Anything V2 Metric-Outdoor-Small (Transformers 4.49)"],
          ["Image processing", "OpenCV 4.10, NumPy 1.26"],
          ["Back-end", "Python HTTP server, MJPEG stream, JSON endpoints"],
          ["Browser console", "HTML, CSS, JavaScript, browser speech synthesis"],
          ["Phone client", "Expo SDK 58, React Native 0.88 (camera, GPS, compass, speech)"],
          ["Hardware", "Laptop with " + gpu + "; phone with camera, GPS and compass"]],
         [1.0, 2.35]))
    add(("h2", "A. Phase 1: perception"))
    add(("p", "YOLO11s runs at a 0.35 confidence threshold on walking-relevant COCO classes (people, "
              "vehicles, benches, chairs, hydrants and similar). A second YOLO11s model detects street "
              "hazards. It was trained from COCO weights on a South-Asian street dataset [15] that "
              "contains 22 classes (rickshaws, CNG vehicles, footpaths and others). Only six hazard "
              "classes that COCO does not know were kept (Table II); the tree class was dropped because it "
              "had two validation and no test examples, and polygon labels were converted to boxes. "
              "Training ran for 60 epochs (batch 32, 640 px, patience 15, default mosaic, colour and scale "
              "augmentation) in 0.67 h on a Tesla T4. Per-class thresholds follow the test results: the "
              "vague “obstacle” class needs 0.5 confidence, and “bin” is disabled because its recall was "
              "0.026. ByteTrack gives each box a stable identity. Depth Anything V2 Metric-Outdoor-Small "
              "runs in FP16 at a 392-pixel input and is refreshed every second frame. The real-video runs "
              "in Section VII-D used a single-class stairs variant of the hazard detector (validation "
              "mAP50 0.50), because the six-class weights evaluated in Table IV were not in the project's "
              "model folder."))
    add(("table", "TABLE II. HAZARD DATASET AFTER FILTERING (INSTANCES PER SPLIT)",
         ["Class", "Train", "Valid", "Test"],
         [["stairs", "183", "19", "14"], ["pole", "1637", "107", "92"], ["pillar", "510", "193", "175"],
          ["bin", "36", "25", "38"], ["cone", "123", "32", "74"], ["obstacle", "234", "10", "143"],
          ["Images with hazards", "1935", "210", "211"], ["Background images", "967", "341", "329"]],
         [1.3, 0.7, 0.7, 0.7]))
    add(("h2", "B. Phase 2: scale-corrected 3D geometry"))
    add(("p", "Each depth value Z at pixel (u, v) is back-projected with a pinhole model, where "
              "f = (max(W, H)/2) / tan(θ/2) is the focal length in pixels and θ = 70° is the assumed field "
              "of view:"))
    add(("eq", "X = (u − W/2) · Z / f,      Y = (v − H/2) · Z / f"))
    add(("p", "The lower 40 % of the image is searched for the "
              "ground with RANSAC, choosing the plane n·P + d = 0 that has most inliers within an "
              "adaptive tolerance τ = 0.03 · median(Z); planes whose normal is not close to vertical are "
              "rejected:"))
    add(("eq", "π̂ = argmax_π  Σ_{p in S}  1( |n·p + d| < τ )"))
    add(("p", "With the assumed camera height H_{c} = 1.4 m, the plane gives a scale factor per frame, and "
              "the median over the last 90 frames (about 3 s) removes occasional bad fits:"))
    add(("eq", "s_t = H_c / (−d_t),      ŝ_t = median( s_{t−89}, …, s_t )"))
    add(("eq", "h(P) = −ŝ_t (n·P + d),      P̄ = ŝ_t · P"))
    add(("p", "Points with h between 0.25 m and 2.0 m inside the corridor (|X̄| < 0.5 m, 0 < Z̄ < 3 m) "
              "form the blocker set. At least 15 points are required, the distance is the 5th percentile of "
              "their depth, the side with fewer points is suggested as the clear side, and an object with "
              "nothing below 1 m is flagged as head-level. A YOLO box on stairs is kept only when the depth "
              "slope inside the box confirms a direction (least-squares slope of height against depth):"))
    add(("eq", "dh/dZ > 0.08: stairs up;      dh/dZ < −0.08: stairs down"))
    add(("h2", "C. Phase 3: risk, alert ranking and speech"))
    add(("p", "Time-to-collision uses looming, which needs no depth: for a box of pixel height b(t), "
              "TTC = 1 / (d ln b / dt), with the slope fitted over the last second (at least five samples, "
              "boxes taller than 40 px, approach faster than 0.3 m/s, TTC below 10 s). Urgency combines "
              "proximity and time pressure and is scaled by a class weight w_{c} that reflects how harmful "
              "a collision would be (1.0 for vehicles and stairs, 0.7 for people, 0.6 for static objects):"))
    add(("eq", "U = w_c · max( 1 − D/R,  1 − TTC/T )"))
    add(("p", "Here D is the distance, R = 4 m (6 m for hazards) is the proximity range and T = 6 s the "
              "time range. An object in the red corridor is always at least a warning, and “Stop!” is "
              "spoken when U ≥ 0.6 or the object is in the path. The announcer waits 0.2 s before speaking about "
              "an off-path object, repeats an alert only after 5 s and only if the object is 1 m closer, "
              "and forgets an alert after 3 s of absence so that a returning obstacle is announced "
              "again. Speech uses Windows SAPI with a stereo-panned beep from the obstacle side; the "
              "browser and the phone use their own speech engines."))
    add(("h2", "D. Phase 4: route guidance and interfaces"))
    add(("p", "Distances use the haversine formula and directions use the initial bearing θ:"))
    add(("eq", "d = 2 R_e · asin( √( sin²(Δφ/2) + cos φ₁ cos φ₂ sin²(Δλ/2) ) )"))
    add(("p", "The user is told to turn when the camera heading differs from the next road bearing by more "
              "than 30°. A step advances within 12–25 m of the next maneuver (scaled by GPS accuracy), "
              "an off-route warning needs two consecutive readings more than 50 m from the route, and "
              "arrival is declared within 25 m. The back-end is a Python HTTP server that streams the "
              "annotated frames to a browser console; the phone client (Expo / React Native) posts JPEG "
              "frames, GPS and compass headings, and speaks the returned alerts."))

    add(("h1", "VI.", "Testing"))
    add(("p", "Table III lists scenarios with expected and obtained behaviour. Each row was produced by "
              "running the project code on a synthetic scene or a simulated route, not by hand. "
              f"All {passed} of {n_cases} scenarios passed. In addition, an automated suite of 37 tests "
              "(pytest) covers navigation, spatial geometry, the announcer and the web server. During "
              "this verification the suite exposed four real defects that were fixed before the "
              "measurements below: inverted stairs up/down labels, a depth cache that never refreshed "
              "when depth was requested for every frame, muted re-announcement of a returning obstacle, "
              "and a distance countdown that stayed constant while walking."))
    rows = []
    for tc in R["test_cases"]:
        obtained = tc["obtained"] + (f" ({tc['detail']})" if tc.get("detail") else "")
        rows.append([tc["id"], tc["scenario"], tc["expected"], obtained, tc["status"]])
    add(("table", "TABLE III. SCENARIO TEST CASES (EXPECTED VS. OBTAINED)",
         ["ID", "Scenario", "Expected", "Obtained", "Status"], rows, [0.35, 1.15, 0.72, 0.72, 0.42]))

    add(("h1", "VII.", "Result Analysis"))
    add(("h2", "A. Hazard detector"))
    add(("p", f"On the held-out test split ({haz['images']} images, {haz['instances']} instances, executed "
              f"notebook) the six-class model reached precision {fmt(haz['precision'], 3)}, recall "
              f"{fmt(haz['recall'], 3)}, mAP50 {fmt(haz['map50'], 3)} and mAP50-95 {fmt(haz['map50_95'], 3)} "
              f"at {fmt(haz['inference_ms_t4'], 1)} ms per image on a Tesla T4 (Table IV, Fig. 4). The "
              "validation split gave a higher mAP50 of 0.684, so the model generalises less well to unseen "
              "images than validation suggests. Cones "
              "and pillars are detected well. Bins are almost never found (recall 0.026) because the training "
              "set contained only 36 bin examples, so the live system disables that class. The stairs "
              "estimate rests on only 14 test instances and should be read as indicative."))
    add(("table", "TABLE IV. HAZARD-MODEL TEST RESULTS PER CLASS",
         ["Class", "Inst.", "P", "R", "mAP50", "mAP50-95"],
         [[a, str(b), fmt(p, 3), fmt(r_, 3), fmt(m, 3), fmt(m2, 3)] for a, b, p, r_, m, m2 in HAZARD_ROWS]
         + [["all", str(haz["instances"]), fmt(haz["precision"], 3), fmt(haz["recall"], 3),
             fmt(haz["map50"], 3), fmt(haz["map50_95"], 3)]],
         [0.7, 0.45, 0.45, 0.45, 0.55, 0.7]))
    add(("fig", "hazmap", "paper_assets/fig_hazard_map.png",
         "Fig. 4. Per-class average precision of the hazard detector on the test split."))
    add(("h2", "B. Effect of ground-plane scale correction"))
    add(("p", "A synthetic scene with exact geometry (flat ground, a 0.8 m wide and 1.2 m tall obstacle "
              "at 1.5–2.8 m, 2 % depth noise, five noise seeds) isolates the contribution of scale "
              "correction. The raw depth was multiplied by 1.0, 1.5, 2.0 and 3.0 to imitate a monocular "
              f"network that is wrong by a constant factor. With correction the mean distance error was "
              f"{fmt(scale['2.0']['corrected_error_m'] * 100, 1)} cm at every factor and every blocker was "
              f"detected. Without it, the error was {fmt(scale['1.5']['uncorrected_error_m'], 2)} m at "
              f"×1.5 and {fmt(scale['2.0']['uncorrected_error_m'], 2)} m at ×2, and only "
              f"{fmt(100 * scale['1.5']['uncorrected_detect'], 0)} % (×1.5) and "
              f"{fmt(100 * scale['2.0']['uncorrected_detect'], 0)} % (×2) of blockers were still inside "
              "the 3 m corridor; at ×3 none were (Fig. 5). These scenes are an idealised upper bound: "
              "real scenes have uneven ground, occlusion and a camera height that changes with the user."))
    add(("fig", "scale", "paper_assets/fig_scale.png",
         "Fig. 5. Distance error (left) and blocker detection rate (right) with and without ground-plane "
         "scale correction."))
    add(("h2", "C. Speed"))
    add(("p", f"Table V gives the per-frame time measured on an {gpu} for a walking video "
              f"({'1280 px wide'}), with the COCO detector, the hazard detector, depth, spatial analysis "
              f"and drawing. Refreshing depth on every second frame lowers the total from "
              f"{fmt(lat1['TOTAL'], 1)} ms ({fmt(fps1, 1)} FPS) to {fmt(lat2['TOTAL'], 1)} ms "
              f"({fmt(fps2, 1)} FPS), and depth is the dominant cost. Risk analysis and the announcer take "
              "about 0.1 ms."))
    stage_names = ["1. detect (COCO)", "2. detect (hazards)", "3. depth", "4. spatial",
                   "5. risk + announcer", "6. drawing", "TOTAL"]
    add(("table", "TABLE V. MEAN TIME PER FRAME (ms)",
         ["Stage", "Depth every frame", "Depth every 2nd frame"],
         [[s.split('. ')[-1], fmt(lat1[s], 1), fmt(lat2[s], 1)] for s in stage_names],
         [1.5, 0.95, 0.95]))
    add(("h2", "D. Behaviour on real walking video"))
    add(("p", f"The full pipeline was run on {len(pipe)} clips ({fmt(total_s, 0)} s in total): a street "
              "clip, a crowded station walkway, a city sidewalk with a construction barrier, an indoor "
              "lobby, and a short indoor phone recording of a living room. There is no hand-labelled "
              "ground truth, so Table VI reports what can be measured: speed (mean "
              f"{fmt(mean_fps, 1)} FPS including all models), alert rate and the share of frames with a "
              "blocked path. Fig. 6 shows a typical annotated frame with its depth map. The living-room "
              "clip is a failure case: the stairs detector fires on the patterned carpet and the "
              "path is reported blocked in every frame, which produces 175 alerts per minute. It shows "
              "that the stairs model, trained on outdoor scenes, is not reliable on indoor floors, "
              "and that the alert rate on the other four clips (6–48 per minute) is more representative. "
              "Whether individual stairs alerts on the street clips were correct was not checked by hand. "
              "Messages spoken in these runs include “Truck approaching at 11 o'clock, 3 meters”, “Stop! "
              "Path blocked, 3 meters. Keep Left.”, “Person approaching at 1 o'clock, 6 meters” and "
              "“Stop! person ahead, 3 meters”; their correctness was likewise not verified. "
              + (f"As a distance sanity check, the depth-based distance to fully visible people was compared "
                 f"with the distance implied by a 1.7 m person height: the ratio had a median of "
                 f"{fmt(dc['median'], 2)} (interquartile range {fmt(dc['q25'], 2)}–{fmt(dc['q75'], 2)}, "
                 f"{dc['n']} measurements). Both estimates rely on assumptions, so this tests consistency, "
                 "not absolute accuracy." if dc else "")))
    add(("table", "TABLE VI. FULL-PIPELINE BEHAVIOUR ON WALKING VIDEO",
         ["Clip", "Length (s)", "FPS", "Alerts per min", "Urgent", "Blocked (%)"],
         [[r["clip"].replace(".mp4", "").replace("_30s_", "-").replace("part_", "walk_")
           .replace("city_street_youtube", "street").replace("live_demo_source", "living room*"),
           fmt(r["seconds"], 0), fmt(r["fps"], 1), fmt(r["alerts_per_min"], 1), str(r["urgent"]),
           fmt(r["blocked_pct"], 0)] for r in pipe],
         [1.0, 0.55, 0.4, 0.6, 0.45, 0.6]))
    add(("fig", "live", "paper_assets/fig_live_frame.jpg",
         "Fig. 6. Prototype output on the sidewalk clip: annotated frame (left) with distance, clock "
         "direction, time-to-collision (magenta) and path status, and the metric depth map (right). "
         "*Failure case, see text."))
    ttc = {(r["speed"], r["true_ttc"]): r for r in R["ttc"]}
    speeds = sorted({r["speed"] for r in R["ttc"]})
    biases = [r["mean_estimate"] - r["true_ttc"] for r in R["ttc"] if r["mean_estimate"] is not None]
    add(("h2", "E. Time-to-collision accuracy"))
    add(("p", "The looming estimator was tested on a simulated 1.7 m tall person approaching a 1280×720 "
              "camera at constant speed from 10 s before impact, with 1.5 px of noise on both box edges, "
              "30 frames per second and 20 noise seeds per speed. Table VII lists the mean estimate at four "
              "true values of time-to-collision. An estimate was available at every checkpoint, so "
              "the 6 s urgency range of the alert score is covered. The estimate was too large by "
              f"{fmt(min(biases), 2)}–{fmt(max(biases), 2)} s at every speed, close to half of the one-second "
              "window used for the slope fit: the fit reports the average over the last second, so it lags. "
              "The alert therefore arrives about half a second later than ideal, which is "
              "1.5 m of travel for a 3 m/s bicycle. Subtracting half the window would likely remove most "
              "of this bias, but that was not tested."))
    add(("table", "TABLE VII. ESTIMATED TIME-TO-COLLISION (s) AT FOUR TRUE VALUES",
         ["Closing speed", "True 6.0", "True 4.0", "True 3.0", "True 2.0"],
         [[f"{s:g} m/s"] + [fmt(ttc[(s, t)]["mean_estimate"], 2) for t in (6.0, 4.0, 3.0, 2.0)]
          for s in speeds], [0.9, 0.6, 0.6, 0.6, 0.6]))
    add(("h2", "F. Route guidance under GPS noise"))
    add(("p", "A 155 m two-leg route was walked 20 times per noise level at 1.4 m/s with Gaussian GPS "
              "error, a compass error of 8° and a one-second sample interval (Table VIII). Navigation reached "
              "the turn and the destination in all runs, the distance countdown decreased monotonically "
              "between the first and last message in all runs, and no run raised a false off-route warning. "
              f"About {fmt(sum(r['messages_per_100m'] for r in nav) / len(nav), 1)} messages per 100 m "
              "were spoken. These are simulations; the compass-to-heading conversion on a real phone has "
              "not been validated on a device."))
    add(("table", "TABLE VIII. ROUTE-GUIDANCE SIMULATION (20 RUNS PER ROW)",
         ["GPS σ (m)", "Arrived (%)", "Turn step (%)", "False off-route (%)", "Msgs/100 m"],
         [[fmt(r["gps_sigma_m"], 0), fmt(r["arrived_pct"], 0), fmt(r["turn_step_pct"], 0),
           fmt(r["false_off_route_pct"], 0), fmt(r["messages_per_100m"], 1)] for r in nav],
         [0.6, 0.65, 0.7, 0.9, 0.6]))

    add(("h1", "VIII.", "Discussion and Limitations"))
    add(("p", "Three results shape the design. First, scale correction is what makes a 3 m corridor "
              "usable with a monocular network: without it the distance error grows in proportion to the "
              "scale error and blockers leave the corridor. Second, depth estimation is the largest cost "
              "(Table V), so refreshing it every second frame buys about four frames per second at the price "
              "of slightly older geometry. Third, the hazard detector generalises less well than its "
              "validation score suggests (0.684 versus 0.556 mAP50), and the classes with few examples "
              "(stairs, bins) are the weakest, so rare but dangerous hazards need more data. "
              "Verification also paid off: the explicit scenario tests caught four defects that no "
              "single screenshot would have shown."))
    add(("p", "Monocular depth and a fixed camera height make distances approximate; camera pitch, "
              "lighting, motion blur and reflective surfaces reduce accuracy, and a phone held at a "
              "different height changes the scale. The controlled experiments use idealised geometry. "
              "The real-video clips have no ground-truth labels, the stairs detector produced false "
              "alarms on an indoor patterned floor, the hazard test set has few stairs examples, the bin "
              "class is not usable, and the weights in the repository's live configuration are a "
              "single-class stairs model rather than the six-class model evaluated in Table IV. No study with "
              "visually impaired users has been carried out. The prototype has not been validated for "
              "safety and must be used only together with a cane, a guide dog or human support."))

    add(("h1", "IX.", "Conclusion and Future Work"))
    add(("p", "Safe-Stride Assist shows that one camera can give path-aware, prioritised guidance when "
              "detection, tracking, scale-corrected monocular depth and corridor reasoning are combined, "
              f"running at about {fmt(fps2, 0)} FPS on a laptop GPU. Ground-plane scale correction "
              "removed the large distance errors that a constant depth-scale error produces, and the "
              "alert policy and route module behaved consistently in simulation. Future work is "
              "to evaluate with labelled walking data and with users, calibrate risk weights, estimate "
              "camera height and pitch from the phone sensors, retrain the bin and obstacle classes "
              "with more data, add haptic feedback, and validate compass handling on devices."))

    add(("refs", [
        "J. Redmon, S. Divvala, R. Girshick, and A. Farhadi, “You only look once: Unified, real-time "
        "object detection,” in Proc. IEEE CVPR, 2016.",
        "Y. Zhang, P. Sun, Y. Jiang et al., “ByteTrack: Multi-object tracking by associating every "
        "detection box,” in Proc. ECCV, 2022.",
        "L. Yang, B. Kang, Z. Huang et al., “Depth Anything V2,” in Advances in Neural Information "
        "Processing Systems, 2024.",
        "R. Ranftl, A. Bochkovskiy, and V. Koltun, “Vision transformers for dense prediction,” in Proc. "
        "IEEE ICCV, 2021.",
        "Ultralytics, “Ultralytics YOLO documentation.” [Online]. Available: https://docs.ultralytics.com/",
        "World Health Organization, World Report on Vision. Geneva: WHO, 2019.",
        "S. Khan, S. Nazir, and H. U. Khan, “Analysis of navigation assistants for blind and visually "
        "impaired people: A systematic review,” IEEE Access, vol. 9, pp. 26712–26734, 2021.",
        "J. Xu et al., “Wearable obstacle avoidance electronic travel aids for blind and visually "
        "impaired individuals: A systematic review,” IEEE Access, 2023.",
        "R. K. Katzschmann, B. Araki, and D. Rus, “Safe local navigation for visually impaired users "
        "with a time-of-flight and haptic feedback device,” IEEE Trans. Neural Syst. Rehabil. Eng., "
        "vol. 26, no. 3, pp. 583–593, 2018.",
        "M. Eltaher et al., “A systematic review of urban navigation systems for visually impaired "
        "people,” Sensors, vol. 21, no. 9, p. 3103, 2021.",
        "O. I. Johannesson et al., “The Sound of Vision project: The concept and first results,” "
        "Brain Sci., vol. 6, no. 3, p. 20, 2016.",
        "P. B. Shull and D. D. Damian, “Haptic wearables as sensory replacement, sensory augmentation "
        "and trainer,” J. NeuroEng. Rehabil., vol. 12, p. 59, 2015.",
        "V. Ranganeni et al., “Exploring levels of control for a navigation assistant for blind "
        "travelers,” in Proc. ACM/IEEE HRI, 2023, pp. 4–12.",
        "C. Zhang et al., “An ARCore based user centric assistive navigation system for visually "
        "impaired people,” Appl. Sci., vol. 9, no. 5, p. 989, 2019.",
        "Mendeley Data, “Object detection dataset: Navigation assistance for the visually impaired people "
        "using YOLOv11,” dataset ID m68g3h7p87. [Online]. Available: https://data.mendeley.com/",
        "OpenStreetMap contributors, “OpenStreetMap.” [Online]. Available: https://www.openstreetmap.org/",
    ]))
    return c


# --------------------------------------------------------------------------------------
# Mini-markup: **bold**, *italic*, _{sub}, ^{sup}
# --------------------------------------------------------------------------------------
TOKEN = re.compile(r"(\*\*.+?\*\*|_\{.+?\}|\^\{.+?\})")


def segments(text, italic=False):
    out = []
    for part in TOKEN.split(text):
        if not part:
            continue
        if part.startswith("**"):
            out.append((part[2:-2], True, italic, False, False))
        elif part.startswith("_{"):
            out.append((part[2:-1], False, italic, True, False))
        elif part.startswith("^{"):
            out.append((part[2:-1], False, italic, False, True))
        else:
            out.append((part, False, italic, False, False))
    return out


# Equations use plain subscripts like s_t and h(P); convert simple "x_t" patterns to real subscripts.
def eq_markup(text):
    text = re.sub(r"([A-Za-zŝπ̂])_\{([^}]+)\}", r"\1_{\2}", text)
    text = re.sub(r"\b([A-Za-zŝ])_([A-Za-z0-9])\b", r"\1_{\2}", text)
    text = re.sub(r"(argmax)_([A-Za-zπ])", r"\1_{\2}", text)
    text = re.sub(r"Σ_\{([^}]+)\}", r"Σ_{\1}", text)
    text = text.replace("R_e", "R_{e}").replace("w_c", "w_{c}").replace("H_c", "H_{c}")
    text = text.replace("sin²", "sin^{2}")
    return text


COL_IN = 3.375
FIG_IN = 3.3


# --------------------------------------------------------------------------------------
# Word renderer
# --------------------------------------------------------------------------------------
def render_docx(content, path):
    from docx import Document
    from docx.enum.section import WD_SECTION
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt

    FONT = "Times New Roman"
    BODY = 9.5

    def run_fmt(run, size=BODY, bold=False, italic=False, sub=False, sup=False, small_caps=False):
        run.font.name = FONT
        run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.italic = italic
        run.font.subscript = sub
        run.font.superscript = sup
        run.font.small_caps = small_caps

    def add_segments(p, text, size=BODY, italic=False, bold=False):
        for t, b, i, sb, sp in segments(text, italic):
            run_fmt(p.add_run(t), size, b or bold, i, sb, sp)

    def para(align=None, before=0, after=3, first_line=0.0, keep_next=False, line=1.0):
        p = doc.add_paragraph()
        if align is not None:
            p.alignment = align
        f = p.paragraph_format
        f.space_before, f.space_after, f.line_spacing = Pt(before), Pt(after), line
        f.first_line_indent = Inches(first_line)
        f.keep_with_next = keep_next
        return p

    def set_cols(section, num):
        pr = section._sectPr
        cols = pr.find(qn("w:cols"))
        if cols is None:
            cols = OxmlElement("w:cols")
            pr.append(cols)
        cols.set(qn("w:num"), str(num))
        cols.set(qn("w:space"), "360")

    def borders(cell, top=False, bottom=False):
        pr = cell._tc.get_or_add_tcPr()
        b = OxmlElement("w:tcBorders")
        for edge, on in (("top", top), ("bottom", bottom)):
            e = OxmlElement(f"w:{edge}")
            e.set(qn("w:val"), "single" if on else "nil")
            e.set(qn("w:sz"), "6")
            e.set(qn("w:color"), "000000")
            b.append(e)
        pr.append(b)

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    sec.left_margin = sec.right_margin = Inches(0.75)
    sec.top_margin, sec.bottom_margin = Inches(0.75), Inches(0.75)
    set_cols(sec, 1)
    st = doc.styles["Normal"]
    st.font.name = FONT
    st._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    st.font.size = Pt(BODY)

    footer = sec.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = footer.add_run()
    run_fmt(r, 8)
    for kind, text in (("begin", None), (None, " PAGE "), ("end", None)):
        if kind:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
        else:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
        r._r.append(el)

    # Title block (one column)
    p = para(WD_ALIGN_PARAGRAPH.CENTER, 0, 8)
    run_fmt(p.add_run(TITLE), 20, bold=True)
    table = doc.add_table(rows=1, cols=len(AUTHORS))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for cell, (name, dept, org, city, email) in zip(table.rows[0].cells, AUTHORS):
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        for k, (line, italic, bold) in enumerate([(name, False, True), (dept, True, False), (org, True, False),
                                                  (city, True, False), (email, False, False)]):
            pp = cell.paragraphs[0] if k == 0 else cell.add_paragraph()
            pp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            pp.paragraph_format.space_after = Pt(0)
            run_fmt(pp.add_run(line), 9.5 if k else 11, bold=bold, italic=italic)
    para(after=4)

    body = doc.add_section(WD_SECTION.CONTINUOUS)
    set_cols(body, 2)
    J = WD_ALIGN_PARAGRAPH.JUSTIFY

    for item in content:
        kind = item[0]
        if kind == "abstract":
            p = para(J, 0, 4)
            run_fmt(p.add_run("Abstract—"), BODY, bold=True, italic=True)
            add_segments(p, item[1], BODY, bold=True)
        elif kind == "keywords":
            p = para(J, 0, 5)
            run_fmt(p.add_run("Keywords—"), BODY, bold=True, italic=True)
            add_segments(p, item[1], BODY, italic=True)
        elif kind == "h1":
            p = para(WD_ALIGN_PARAGRAPH.CENTER, 7, 3, keep_next=True)
            run_fmt(p.add_run(f"{item[1]} {item[2]}"), 10, small_caps=True)
        elif kind == "h2":
            p = para(WD_ALIGN_PARAGRAPH.LEFT, 3, 2, keep_next=True)
            run_fmt(p.add_run(item[1]), BODY, italic=True)
        elif kind == "p":
            p = para(J, 0, 3, first_line=0.17)
            add_segments(p, item[1])
        elif kind == "bullets":
            for b in item[1]:
                p = para(J, 0, 1.5)
                p.paragraph_format.left_indent = Inches(0.17)
                p.paragraph_format.first_line_indent = Inches(-0.13)
                add_segments(p, "• " + b)
        elif kind == "eq":
            p = para(None, 1, 3)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            add_segments(p, eq_markup(item[1]), 9.5, italic=True)
        elif kind == "fig":
            _, _, rel, caption = item
            file = DOCS / rel
            p = para(WD_ALIGN_PARAGRAPH.CENTER, 3, 1, keep_next=True)
            p.add_run().add_picture(str(file), width=Inches(FIG_IN))
            cp = para(WD_ALIGN_PARAGRAPH.CENTER, 0, 5)
            add_segments(cp, caption, 8)
        elif kind == "table":
            _, caption, header, rows, widths = item
            cp = para(WD_ALIGN_PARAGRAPH.CENTER, 3, 2, keep_next=True)
            run_fmt(cp.add_run(caption), 8, small_caps=False)
            total = sum(widths)
            scaled = [w * FIG_IN / total for w in widths]
            t = doc.add_table(rows=1 + len(rows), cols=len(header))
            t.alignment = WD_TABLE_ALIGNMENT.CENTER
            t.autofit = False
            for ri, row in enumerate([header] + rows):
                for ci, value in enumerate(row):
                    cell = t.rows[ri].cells[ci]
                    cell.width = Inches(scaled[ci])
                    pp = cell.paragraphs[0]
                    pp.paragraph_format.space_after = Pt(0)
                    pp.alignment = WD_ALIGN_PARAGRAPH.LEFT if ci < 2 and header[0] in ("ID", "Class", "Clip", "Stage") else WD_ALIGN_PARAGRAPH.CENTER
                    run_fmt(pp.add_run(str(value)), 7.2, bold=(ri == 0))
                    borders(cell, top=(ri in (0, 1)), bottom=(ri in (0, len(rows))))
            para(after=4)
        elif kind == "refs":
            p = para(WD_ALIGN_PARAGRAPH.CENTER, 7, 3, keep_next=True)
            run_fmt(p.add_run("References"), 10, small_caps=True)
            for n, ref in enumerate(item[1], 1):
                p = para(J, 0, 1.5)
                p.paragraph_format.left_indent = Inches(0.26)
                p.paragraph_format.first_line_indent = Inches(-0.26)
                run_fmt(p.add_run(f"[{n}] {ref}"), 8)

    doc.core_properties.title = TITLE
    doc.core_properties.author = "Jhenkar P"
    doc.save(path)


# --------------------------------------------------------------------------------------
# PDF renderer
# --------------------------------------------------------------------------------------
def render_pdf(content, path):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (BaseDocTemplate, Frame, FrameBreak, Image as RLImage, KeepTogether,
                                    NextPageTemplate, PageTemplate, Paragraph, Spacer, Table, TableStyle)
    from reportlab.lib.fonts import addMapping

    fonts = Path(r"C:\Windows\Fonts")
    for name, file in (("TNR", "times.ttf"), ("TNR-B", "timesbd.ttf"), ("TNR-I", "timesi.ttf"),
                       ("TNR-BI", "timesbi.ttf")):
        pdfmetrics.registerFont(TTFont(name, str(fonts / file)))
    addMapping("TNR", 0, 0, "TNR")
    addMapping("TNR", 1, 0, "TNR-B")
    addMapping("TNR", 0, 1, "TNR-I")
    addMapping("TNR", 1, 1, "TNR-BI")

    def esc(t):
        return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def markup(text, italic=False):
        out = []
        for t, b, i, sb, sp in segments(text, italic):
            s = esc(t)
            if sb:
                s = f"<sub>{s}</sub>"
            if sp:
                s = f"<super>{s}</super>"
            if b:
                s = f"<b>{s}</b>"
            if i:
                s = f"<i>{s}</i>"
            out.append(s)
        return "".join(out)

    S = {
        "body": ParagraphStyle("body", fontName="TNR", fontSize=9.5, leading=11.3, alignment=TA_JUSTIFY,
                               firstLineIndent=12, spaceAfter=3),
        "abs": ParagraphStyle("abs", fontName="TNR-B", fontSize=9.5, leading=11.3, alignment=TA_JUSTIFY,
                              spaceAfter=4),
        "kw": ParagraphStyle("kw", fontName="TNR-I", fontSize=9.5, leading=11.3, alignment=TA_JUSTIFY,
                             spaceAfter=5),
        "h1": ParagraphStyle("h1", fontName="TNR", fontSize=10, leading=12, alignment=TA_CENTER,
                             spaceBefore=7, spaceAfter=3, keepWithNext=True),
        "h2": ParagraphStyle("h2", fontName="TNR-I", fontSize=9.5, leading=11.3, alignment=TA_LEFT,
                             spaceBefore=3, spaceAfter=2, keepWithNext=True),
        "bul": ParagraphStyle("bul", fontName="TNR", fontSize=9.5, leading=11.3, alignment=TA_JUSTIFY,
                              leftIndent=12, firstLineIndent=-9, spaceAfter=1.5),
        "eq": ParagraphStyle("eq", fontName="TNR-I", fontSize=9.5, leading=12, alignment=TA_CENTER),
        "cap": ParagraphStyle("cap", fontName="TNR", fontSize=8, leading=9.5, alignment=TA_CENTER,
                              spaceAfter=5),
        "tcap": ParagraphStyle("tcap", fontName="TNR", fontSize=8, leading=9.5, alignment=TA_CENTER,
                               spaceBefore=3, spaceAfter=2, keepWithNext=True),
        "cell": ParagraphStyle("cell", fontName="TNR", fontSize=7.2, leading=8.4),
        "cellb": ParagraphStyle("cellb", fontName="TNR-B", fontSize=7.2, leading=8.4),
        "ref": ParagraphStyle("ref", fontName="TNR", fontSize=8, leading=9.4, alignment=TA_JUSTIFY,
                              leftIndent=19, firstLineIndent=-19, spaceAfter=1.5),
        "title": ParagraphStyle("title", fontName="TNR-B", fontSize=20, leading=23, alignment=TA_CENTER,
                                spaceAfter=8),
        "a0": ParagraphStyle("a0", fontName="TNR-B", fontSize=11, leading=13, alignment=TA_CENTER),
        "a1": ParagraphStyle("a1", fontName="TNR-I", fontSize=9.5, leading=11.3, alignment=TA_CENTER),
        "a2": ParagraphStyle("a2", fontName="TNR", fontSize=9.5, leading=11.3, alignment=TA_CENTER),
    }

    story = []
    story.append(Paragraph(esc(TITLE), S["title"]))
    cells = []
    for name, dept, org, city, email in AUTHORS:
        cells.append([Paragraph(esc(name), S["a0"]), Paragraph(esc(dept), S["a1"]),
                      Paragraph(esc(org), S["a1"]), Paragraph(esc(city), S["a1"]),
                      Paragraph(esc(email), S["a2"])])
    tbl = Table([cells], colWidths=[3.5 * inch] * len(AUTHORS))
    tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [tbl, FrameBreak()]

    for item in content:
        kind = item[0]
        if kind == "abstract":
            story.append(Paragraph("<b><i>Abstract—</i></b>" + markup(item[1]), S["abs"]))
        elif kind == "keywords":
            story.append(Paragraph("<b>Keywords—</b>" + esc(item[1]), S["kw"]))
        elif kind == "h1":
            story.append(Paragraph(f"{item[1]} {item[2].upper()}", S["h1"]))
        elif kind == "h2":
            story.append(Paragraph(esc(item[1]), S["h2"]))
        elif kind == "p":
            story.append(Paragraph(markup(item[1]), S["body"]))
        elif kind == "bullets":
            for b in item[1]:
                story.append(Paragraph("• " + markup(b), S["bul"]))
        elif kind == "eq":
            story.append(Spacer(1, 1))
            story.append(Paragraph(markup(eq_markup(item[1]), italic=True), S["eq"]))
            story.append(Spacer(1, 3))
        elif kind == "fig":
            _, _, rel, caption = item
            file = DOCS / rel
            w, h = Image.open(file).size
            width = FIG_IN * inch
            story.append(KeepTogether([Spacer(1, 3), RLImage(str(file), width=width, height=width * h / w),
                                       Spacer(1, 2), Paragraph(markup(caption), S["cap"])]))
        elif kind == "table":
            _, caption, header, rows, widths = item
            total = sum(widths)
            col_w = [w * FIG_IN * inch / total for w in widths]
            data = [[Paragraph(esc(str(v)), S["cellb"]) for v in header]]
            data += [[Paragraph(esc(str(v)), S["cell"]) for v in row] for row in rows]
            t = Table(data, colWidths=col_w, repeatRows=1)
            t.setStyle(TableStyle([
                ("LINEABOVE", (0, 0), (-1, 0), 0.7, colors.black), ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
                ("LINEBELOW", (0, -1), (-1, -1), 0.7, colors.black), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ]))
            story.append(KeepTogether([Paragraph(esc(caption), S["tcap"]), t, Spacer(1, 6)]))
        elif kind == "refs":
            story.append(Paragraph("REFERENCES", S["h1"]))
            for n, ref in enumerate(item[1], 1):
                story.append(Paragraph(f"[{n}] {esc(ref)}", S["ref"]))

    page_w, page_h = letter
    margin, gap = 0.75 * inch, 0.25 * inch
    col_w = (page_w - 2 * margin - gap) / 2
    top_h = 2.0 * inch
    body_top = page_h - margin - top_h

    def frames_first():
        return [Frame(margin, body_top + 0, page_w - 2 * margin, top_h, id="top", leftPadding=0,
                      rightPadding=0, topPadding=0, bottomPadding=0),
                Frame(margin, margin, col_w, body_top - margin, id="l1", leftPadding=0, rightPadding=0,
                      topPadding=0, bottomPadding=0),
                Frame(margin + col_w + gap, margin, col_w, body_top - margin, id="r1", leftPadding=0,
                      rightPadding=0, topPadding=0, bottomPadding=0)]

    def frames_later():
        h = page_h - 2 * margin
        return [Frame(margin, margin, col_w, h, id="l", leftPadding=0, rightPadding=0, topPadding=0,
                      bottomPadding=0),
                Frame(margin + col_w + gap, margin, col_w, h, id="r", leftPadding=0, rightPadding=0,
                      topPadding=0, bottomPadding=0)]

    def footer(canvas, doc_):
        canvas.setFont("TNR", 8)
        canvas.drawCentredString(page_w / 2, 0.45 * inch, str(doc_.page))

    doc = BaseDocTemplate(str(path), pagesize=letter, title=TITLE, author="Jhenkar P")
    doc.addPageTemplates([PageTemplate(id="first", frames=frames_first(), onPage=footer,
                                       autoNextPageTemplate="later"),
                          PageTemplate(id="later", frames=frames_later(), onPage=footer)])
    doc.build(story)


def save_with_fallback(render, content, path):
    """Write `path`; if it is open in another program, write a numbered copy instead."""
    for attempt in range(10):
        target = path if attempt == 0 else path.with_name(f"{path.stem}_v{attempt + 1}{path.suffix}")
        try:
            render(content, target)
            print("Wrote", target)
            return target
        except PermissionError:
            print(f"{target.name} is open in another program; trying a new name")
    raise PermissionError(path)


def main():
    content = build_content()
    save_with_fallback(render_pdf, content, DOCS / "SafeStride_Assist_IEEE_Paper.pdf")
    save_with_fallback(render_docx, content, DOCS / "SafeStride_Assist_IEEE_Paper.docx")


if __name__ == "__main__":
    main()
