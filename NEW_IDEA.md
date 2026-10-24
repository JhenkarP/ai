# SafeStride Assist: Feature Roadmap

## Project Vision

SafeStride Assist is an educational assistive-navigation project that teaches students how computer vision, depth estimation, spatial reasoning, and speech feedback can support safer mobility for visually impaired users.

This project is a research and teaching prototype. It must not be treated as a certified medical, mobility, or emergency device.

## Current Foundation

- YOLO object detection
- ByteTrack object tracking
- Depth Anything V2 monocular depth estimation
- 3D ground-plane and walking-corridor analysis
- Estimated object distance
- Direction and clock-position guidance
- Time-to-collision and approach-risk estimation
- Ranked voice alerts and cooldowns
- Directional warning beeps
- Windows speech output
- Video processing with synchronized alert audio
- GPU acceleration with CUDA
- Webcam and recorded-video modes

## Planned Features

### 1. Custom Hazard and Stair Detection

Train a custom `hazards.pt` model with classes such as:

- `stairs_up`
- `stairs_down`
- `curb`
- `pothole`
- `bollard`
- `pole`
- `construction_barrier`
- `road_block`
- `open_drain`
- `uneven_surface`
- `vehicle_rickshaw`

Example alerts:

- "Stairs ascending ahead."
- "Stairs descending ahead."
- "Stop. Obstacle very close."
- "Bollard at 1 o'clock, 2 meters."

The system should report model confidence and avoid claiming stair direction when the camera orientation is uncertain.

### 2. Real-Time Webcam Interface

- Live camera preview
- Detection boxes and labels
- Depth-map panel
- Walking-path status
- FPS and latency display
- Start and stop controls
- Camera selection
- Fullscreen accessibility mode
- Live alert captions
- Audio-test control

### 3. Reliable Audio Feedback

- Startup sound test
- Spoken test alert
- Separate warning and urgent tones
- Left/right spatial beeps
- Adjustable volume
- Adjustable speech rate
- Alert cooldowns
- Alert priority queue
- Alert history log
- Offline speech fallback
- Clear indication when a video contains no alerts

### 4. GPS and Route Navigation

- Current location
- Destination search
- Walking route calculation
- Turn-by-turn voice instructions
- Crossing and intersection warnings
- Route deviation detection
- Combination of route guidance and local obstacle analysis
- Offline route cache for previously used areas

### 5. Natural-Language Voice Commands

Example commands:

- "Start navigation."
- "Stop navigation."
- "Where am I?"
- "Repeat the last warning."
- "Increase speech speed."
- "Use Hindi."
- "What is ahead?"
- "Call my emergency contact."

### 6. Emergency and Family Support

- SOS button
- Emergency contact configuration
- Share current location
- Send an emergency message
- Optional fall or sudden-motion detection
- Family status notifications
- Low-battery warning
- Offline emergency mode
- Cancel-alert countdown to prevent accidental calls

### 7. Camera and Distance Calibration

- Phone-height setup
- Camera-angle setup
- Camera orientation detection
- Indoor and outdoor profiles
- Automatic ground-plane calibration
- Manual distance correction
- Distance confidence score
- Warning when scene geometry is unreliable

### 8. Accessibility and Localization

- English speech
- Kannada speech
- Hindi speech
- French speech
- Adjustable speech rate
- Adjustable speech volume
- Headphone and speaker modes
- Vibration feedback for mobile devices
- High-contrast interface
- Large controls
- Keyboard navigation
- Screen-reader-friendly controls
- Left/right stereo guidance

### 9. Student Teaching and Demonstration Tools

- Detection-only mode
- Depth-only mode
- Tracking-only mode
- Risk-analysis mode
- Alert-decision explanation
- Step-by-step pipeline visualization
- Dataset inspection tool
- Annotation viewer
- Model confidence viewer
- Latency breakdown
- FPS benchmark dashboard
- Guided laboratory exercises
- Reproducible demo videos
- Student experiment templates

Suggested learning modules:

1. Object detection fundamentals
2. Tracking objects over time
3. Monocular depth estimation
4. Camera geometry and ground planes
5. Time-to-collision estimation
6. Alert ranking and human factors
7. Audio spatialization
8. Model evaluation and safety limits

### 10. Evaluation and Reporting

Measure and report:

- Precision and recall
- mAP50 and mAP50-95
- Distance-estimation error
- Stair-detection accuracy
- False-alert rate
- Missed-hazard rate
- Alert response time
- End-to-end latency
- Frames per second
- GPU memory use
- Audio alert timing
- Performance in daylight, low light, indoor, and outdoor scenes

Create separate test groups for:

- People
- Cars and motorcycles
- Chairs and furniture
- Bollards and poles
- Stairs
- Curbs
- Potholes
- Crowded scenes
- Empty scenes
- Low-light scenes

### 11. Web and Mobile Deployment

- Browser-based dashboard
- Mobile camera support
- REST API for frame analysis
- WebSocket live alerts
- Local-only privacy mode
- Docker deployment
- Device health status
- Model download manager
- Configurable processing quality
- Lightweight mobile model

### 12. Privacy and Safety Controls

- Process camera frames locally by default
- Do not upload video without consent
- Automatic deletion of temporary frames
- No storage of location unless enabled
- Visible recording indicator
- Clear confidence and limitation messages
- Emergency feature confirmation
- No medical diagnosis claims
- No guarantee of obstacle detection
- Human testing only with appropriate supervision

## Recommended Implementation Order

1. Add audio test mode and alert logging.
2. Build a stable live webcam interface.
3. Prepare and train the custom hazard dataset.
4. Add stair, curb, bollard, and pothole classes.
5. Add calibration and confidence reporting.
6. Add a student benchmark and evaluation dashboard.
7. Add GPS route navigation.
8. Add voice commands and settings.
9. Add SOS and family support.
10. Package the system for web and mobile use.

## Hazard Model Training Plan

1. Collect or license representative street and stair images.
2. Annotate bounding boxes using a consistent class list.
3. Split data into training, validation, and test sets.
4. Train a YOLO model with a documented configuration.
5. Evaluate per-class precision, recall, and mAP.
6. Test on clips that were not used for training.
7. Check false alerts and missed hazards manually.
8. Export the best checkpoint as `models/hazards.pt`.
9. Run the full SafeStride pipeline with the custom checkpoint.
10. Record limitations and known failure cases.

## Educational Attribution

SafeStride Assist should document the upstream project, third-party models, datasets, and licenses. Student contributions should be recorded separately through commits, experiment notes, benchmarks, and feature documentation.
