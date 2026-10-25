# SafeStride Assist: An AI-Based Safe Walking Assistant Using Real-Time Obstacle Detection and Monocular Depth Estimation

### Abstract

SafeStride Assist is a research and teaching prototype that uses computer vision, monocular depth estimation, spatial reasoning, and speech feedback to support safer walking for people with visual impairment. A camera stream is processed locally using YOLO-based obstacle detection, ByteTrack tracking, and Depth Anything V2. The central contribution is a distance-aware walking-corridor algorithm: it estimates the ground plane, converts relative depth into approximate metres, finds the nearest obstacle or blocker within a three-metre forward corridor, and recommends a clear side when possible.

The system also provides a browser-based live console, directional voice alerts, obstacle tracking, and approach-risk estimation. The ground-plane model converts monocular depth into an approximate metric scale and evaluates a three-metre, one-metre-wide forward corridor. This lets the assistant reason about unknown blockers in addition to known obstacle classes rather than relying only on bounding-box labels.

SafeStride Assist is designed as an educational prototype rather than a certified medical, mobility, or emergency device. Its purpose is to demonstrate how visual perception, spatial analysis, and human-centred audio feedback can be combined in a privacy-conscious local-processing workflow.

### Keywords

Assistive technology, computer vision, YOLO, monocular depth estimation, distance estimation, obstacle detection, blocker detection, voice alerts, safe walking assistance, spatial reasoning.

## 1. Introduction

People with visual impairment may need to combine a white cane, guide dog, personal knowledge, and assistance from other people to interpret obstacles and move through unfamiliar environments. A camera-based assistant cannot replace these safety methods, but it can provide an additional perception channel by describing relevant blockers, estimating distance, and presenting timely audio guidance.

SafeStride Assist addresses this challenge through a modular pipeline. The camera provides the scene, machine-learning models identify visual content, depth estimation approximates the scene geometry, and a deterministic reasoning layer converts those observations into prioritised guidance. The system is intentionally designed to keep video processing on the local machine by default.

Safe movement in an unfamiliar environment depends on understanding the relationship between the user, the ground, and nearby obstacles. A person, pole, door, vehicle, step, or other obstruction may be visible in the camera image but still be irrelevant if it is far to the side. Conversely, an unknown structure may be dangerous even when it is not represented by a detector class. This makes path-aware analysis important: the assistant must identify which visual information is close enough, high enough, and positioned within the user's forward walking corridor to deserve attention.

SafeStride Assist is therefore designed as an additional perception and feedback layer rather than a replacement for a white cane, guide dog, or human support. The system uses a camera stream to estimate the scene, a depth model to approximate distance, and a spatial reasoning module to identify possible blockers in front of the user. Its output is deliberately short and action-oriented, for example reporting that the path is blocked, giving an approximate distance, and suggesting a clearer side. This approach connects computer vision results to a practical decision while keeping the user aware that the measurements are approximate.

## 2. Problem Statement

Many detection demonstrations stop at drawing a bounding box around an obstacle. For safe walking assistance, the important question is whether the obstacle or unknown blocker is relevant to the user's forward path, how far away it is, and what the user should do next. A useful prototype must also avoid overwhelming the user with repeated or low-priority messages.

The problem addressed by this project is the design of a real-time prototype that can:

- detect relevant obstacles and unknown depth-based blockers;
- estimate approximate distance and clock-direction position;
- decide whether the forward walking corridor is blocked;
- provide concise, prioritised, repeatable voice instructions; and
- provide immediate guidance without overwhelming the user with repeated alerts.

## 3. Objectives

1. Build a live camera-processing pipeline for real-time perception.
2. Detect walking-relevant obstacles using YOLO and track them over time with ByteTrack.
3. Estimate approximate obstacle distance using Depth Anything V2 and ground-plane calibration.
4. Analyse a three-metre forward corridor and determine whether it is blocked.
5. Generate complete spoken alerts containing the obstacle, distance, direction, and suggested side.
6. Provide a browser console with live video, captions, diagnostics, and voice controls.
7. Prioritise urgent camera obstructions over ordinary warnings and background announcements.
8. Establish a foundation for custom door-state and stair-direction models.

## 4. Drawbacks of Existing Systems

**Limited Reach of Manual Aids:** Dakopoulos and Bourbakis [7] explain that electronic travel aids are intended to complement, rather than replace, traditional mobility aids. A white cane or guide dog remains essential, but manual aids may provide limited information about distant, overhead, or unfamiliar obstacles.

**Limited Distance Awareness:** Tapu et al. [8] observe that many assistive systems detect obstacles without providing reliable distance information. A visual label or bounding box alone does not indicate how urgently the user must respond.

**No Walking-Corridor Reasoning:** Existing detection systems commonly identify objects in the camera view without deciding whether they lie within the user's forward walking corridor. This can produce warnings for objects that are visible but not directly relevant to the user's path.

**Unknown Blockers May Be Missed:** As discussed by Bhowmick and Hazarika [9], assistive vision systems depend strongly on their sensing and recognition models. Temporary structures, low-contrast hazards, and objects without trained classes may therefore remain undetected.

**Insufficient Stair and Step Awareness:** General obstacle detectors may not reliably distinguish stairs, curbs, and changes in ground level from ordinary scene structure. This limits their ability to provide the specific directional warning required for safe step and stair negotiation.

**Repeated and Low-Value Alerts:** Frequent announcements can increase cognitive load and make urgent information harder to notice. A system must therefore consider persistence, distance, path relevance, and alert priority rather than speaking for every detection.

**Weak Temporal Reasoning:** Frame-by-frame analysis does not establish whether an obstacle is approaching, stationary, or moving across the walking path. Tracking methods such as ByteTrack [2] are needed to provide more stable temporal evidence.

**Additional Hardware and Connectivity Requirements:** Some assistive solutions require dedicated sensors, wearable components, or network services, which can increase cost, maintenance, and dependence on operating conditions.

**Unclear Safety Boundaries:** Ranftl et al. [4] show that monocular depth is useful for scene structure but does not automatically provide guaranteed real-world distance. Experimental systems must communicate uncertainty and must not be treated as replacements for certified mobility support.

## 5. Proposed Methodology

### 4.1 Perception

The system receives frames from an IP webcam, local webcam, uploaded video, or recorded test clip. YOLO identifies relevant obstacles and ByteTrack maintains their identities across frames. The default model is filtered to walking-relevant COCO classes. Custom hazard checkpoints can be loaded separately when required.

### 4.2 Depth and Spatial Reasoning

Depth Anything V2 estimates relative depth. A RANSAC ground-plane estimator uses the lower part of the image and the known approximate camera height to stabilise the depth scale. The spatial analyser projects the depth map into approximate three-dimensional points and evaluates a one-metre-wide corridor extending up to three metres ahead.

The corridor is considered blocked when enough points rise above the ground plane within the configured obstacle-height range. Detected obstacles are also assigned approximate distance, clock direction, lateral position, and an `in_path` status. This allows the system to report both named hazards and unknown blockers.

### 4.3 Risk and Alert Selection

The alert layer ranks detections by relevance, proximity, approach risk, and whether they are inside the walking path. Time-to-collision is estimated for approaching tracked objects. Cooldowns and event identifiers prevent excessive repetition while preserving important repeated guidance.

The priority order is:

1. urgent camera obstruction;
2. local path correction; and
3. background or status information.

Example output: `Stop. Path blocked, 2 meters. Keep left.`

### 4.4 User Interface and Audio

The web console displays the annotated live feed, obstacle count, inference rate, depth status, current priority, path status, and spoken captions. Browser speech synthesis and local Windows audio provide voice feedback. The system supports test-voice controls and keeps processing local by default.

## 5. System Architecture

The system is organised into the following layers:

- **Input layer:** IP webcam, local webcam, uploaded video, or test clip.
- **Perception layer:** YOLO detection, ByteTrack tracking, and Depth Anything V2.
- **Reasoning layer:** ground-plane calibration, corridor analysis, distance estimation, and time-to-collision.
- **Decision layer:** alert ranking, cooldowns, guidance direction, and safety priority.
- **Interaction layer:** browser live console, captions, speech synthesis, and diagnostic status.

## 6. Current Prototype Scope

The current prototype includes live IP-camera streaming, local YOLO and depth inference, ground-plane scale correction, three-metre corridor analysis, distance-aware directional obstacle guidance, browser voice alerts, and a corrected visual corridor overlay. The standard run configuration can disable the experimental custom hazard checkpoint with `--no-hazards`.

Custom door-state classes such as `door_open`, `door_closed`, and `door_semi`, together with stair-direction classes such as `stair_up` and `stair_down`, are suitable next model extensions. Public datasets have been identified, but any downloaded data must be reviewed for license compatibility, relabelled where necessary, and validated on the project's own camera viewpoint before deployment.

## 7. Expected Outcomes

- A functioning real-time safe-walking assistant demonstration.
- A distance algorithm that converts monocular depth into approximate obstacle range.
- Distance-aware and direction-aware spoken obstruction alerts.
- A browser interface for monitoring perception, path status, and alert state.
- A modular codebase that separates perception, spatial reasoning, alert decisions, and speech.
- A reproducible foundation for evaluating custom hazard, door, and stair models.
- Measurable evaluation targets including precision, recall, mAP, false-alert rate, missed-hazard rate, latency, and frames per second.

## 8. Limitations and Safety

Monocular depth provides approximate rather than guaranteed metric distance. The distance algorithm depends on camera height, camera angle, ground visibility, lighting, motion blur, reflections, crowds, and unusual objects. Speech output depends on the operating system and browser. The prototype must not be used as a sole mobility aid, medical device, or emergency system.

Testing should be performed with appropriate supervision and conventional mobility safety methods. No claim is made that the system can detect every obstacle or guarantee a safe path.

## 9. Future Work

Future work includes training and evaluating door open/closed/semi-closed detection, stair-up/stair-down detection, calibration assistance, low-light evaluation, multilingual speech, mobile packaging, emergency-contact support, and a formal benchmark using controlled and real-world test clips.

## 10. Conclusion

SafeStride Assist demonstrates a practical architecture for combining real-time vision, monocular depth, ground-plane distance estimation, spatial reasoning, and speech feedback in an accessible safe-walking prototype. Its central contribution is the translation of visual depth into prioritised, distance-aware, actionable guidance while preserving a clear boundary between a student research prototype and a certified safety device.
