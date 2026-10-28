from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

OUT = Path(__file__).with_name("SafeStride_Synopsis.docx")
FONT = "Book Antiqua"


def set_cell_shading(cell, fill="D9EAD3"):
    properties = cell._tc.get_or_add_tcPr()
    shading = properties.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        properties.append(shading)
    shading.set(qn("w:fill"), fill)


def remove_cell_shading(cell):
    properties = cell._tc.get_or_add_tcPr()
    shading = properties.find(qn("w:shd"))
    if shading is not None:
        properties.remove(shading)


def set_table_borders(table):
    properties = table._tbl.tblPr
    borders = properties.first_child_found_in("w:tblBorders")
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        properties.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = borders.find(qn("w:" + edge))
        if element is None:
            element = OxmlElement("w:" + edge)
            borders.append(element)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), "4")
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), "auto")


def set_cell_text(cell, value, bold=False, align=WD_ALIGN_PARAGRAPH.LEFT, size=10):
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.alignment = align
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = 1.0
    run = paragraph.add_run(value)
    run.bold = bold
    run.font.name = FONT
    run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    run.font.size = Pt(size)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def set_run_font(run, size=11, bold=False, italic=False):
    run.font.name = FONT
    run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic


def add_paragraph(doc, value, align=WD_ALIGN_PARAGRAPH.JUSTIFY, first_line=True, space_after=0):
    paragraph = doc.add_paragraph()
    paragraph.alignment = align
    paragraph.paragraph_format.line_spacing = 1.0
    paragraph.paragraph_format.space_after = Pt(space_after)
    if first_line and align == WD_ALIGN_PARAGRAPH.JUSTIFY:
        paragraph.paragraph_format.first_line_indent = Inches(0.25)
    run = paragraph.add_run(value)
    set_run_font(run)
    return paragraph


def add_heading(doc, value):
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.keep_with_next = True
    run = paragraph.add_run(value)
    set_run_font(run, size=11, bold=True)
    return paragraph


def add_bullet(doc, value, number=None):
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    paragraph.paragraph_format.left_indent = Inches(0.35)
    paragraph.paragraph_format.first_line_indent = Inches(-0.2)
    paragraph.paragraph_format.line_spacing = 1.0
    paragraph.paragraph_format.space_after = Pt(0)
    prefix = f"{number}. " if number is not None else "- "
    run = paragraph.add_run(prefix + value)
    set_run_font(run)
    return paragraph


def add_reference(doc, number, value):
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    paragraph.paragraph_format.left_indent = Inches(0.25)
    paragraph.paragraph_format.first_line_indent = Inches(-0.25)
    paragraph.paragraph_format.line_spacing = 1.0
    paragraph.paragraph_format.space_after = Pt(0)
    run = paragraph.add_run(f"{number}. {value}")
    set_run_font(run, size=10)
    return paragraph


def add_page_number(paragraph):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    set_run_font(run, size=9)
    field_begin = OxmlElement("w:fldChar")
    field_begin.set(qn("w:fldCharType"), "begin")
    instruction = OxmlElement("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = "PAGE"
    field_end = OxmlElement("w:fldChar")
    field_end.set(qn("w:fldCharType"), "end")
    run._r.append(field_begin)
    run._r.append(instruction)
    run._r.append(field_end)


def add_requirements_table(doc, headers, rows, widths):
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = "Table Grid"
    set_table_borders(table)
    for index, header in enumerate(headers):
        set_cell_text(table.rows[0].cells[index], header, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
        remove_cell_shading(table.rows[0].cells[index])
    for row in rows:
        cells = table.add_row().cells
        for index, value in enumerate(row):
            set_cell_text(cells[index], value, size=10)
    for row in table.rows:
        for index, width in enumerate(widths):
            row.cells[index].width = Inches(width)
    doc.add_paragraph().paragraph_format.space_after = Pt(0)
    return table


def build_document():
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(0.2638888889)
    section.bottom_margin = Inches(0.1944444444)
    section.left_margin = Inches(0.25)
    section.right_margin = Inches(0.25)

    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    normal.font.size = Pt(11)
    normal.paragraph_format.line_spacing = 1.0
    normal.paragraph_format.space_after = Pt(0)

    footer = section.footer.paragraphs[0]
    add_page_number(footer)

    for value, size, bold in [
        ("DEPARTMENT OF COMPUTER SCIENCE & ENGINEERING", 12, True),
        ("THE NATIONAL INSTITUTE OF ENGINEERING", 12, True),
        ("(An Autonomous Institution)", 10, False),
        ("Project Synopsis", 14, True),
    ]:
        paragraph = doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_after = Pt(0)
        run = paragraph.add_run(value)
        set_run_font(run, size=size, bold=bold)

    metadata = doc.add_table(rows=2, cols=4)
    metadata.alignment = WD_TABLE_ALIGNMENT.CENTER
    metadata.style = "Table Grid"
    set_table_borders(metadata)
    values = [
        ("Batch No:", "B15", "Date:", "16/07/2026"),
        ("USN", "1", "Name", "Jhenkar P"),
    ]
    for row_index, row_values in enumerate(values):
        for col_index, value in enumerate(row_values):
            set_cell_text(metadata.rows[row_index].cells[col_index], value, bold=col_index % 2 == 0, size=10)
            remove_cell_shading(metadata.rows[row_index].cells[col_index])
    metadata.add_row()
    last = metadata.rows[-1].cells
    set_cell_text(last[0], "Email-ID", bold=True, size=10)
    set_cell_text(last[1], "2023cs_JHENKARP_b@nie.ac.in", size=10)
    set_cell_text(last[2], "Mobile Number", bold=True, size=10)
    set_cell_text(last[3], "6363108117", size=10)
    doc.add_paragraph().paragraph_format.space_after = Pt(0)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_before = Pt(0)
    title.paragraph_format.space_after = Pt(0)
    run = title.add_run("Project Title: SafeStride Assist - An AI-Based Safe Walking Assistant Using Monocular Depth Estimation")
    set_run_font(run, size=11, bold=True)

    add_heading(doc, "Abstract:")
    add_paragraph(doc, "SafeStride Assist is a research and teaching prototype that uses computer vision, monocular depth estimation, spatial reasoning, and speech feedback to support safer walking for people with visual impairment. A camera stream is processed locally using YOLO-based obstacle detection, ByteTrack tracking, and Depth Anything V2. The central contribution is a distance-aware walking-corridor algorithm that estimates the ground plane, converts relative depth into approximate metres, identifies the nearest obstacle or unknown blocker within a three-metre forward corridor, and recommends a clear side when possible. The system provides a browser-based live console, directional voice alerts, obstacle tracking, approach-risk estimation, and a visual path overlay. By combining named obstacle detection with depth-based blocker analysis, the prototype can provide actionable feedback instead of displaying detection boxes alone. SafeStride Assist is intended as an educational research prototype and not as a certified mobility, medical, or emergency device.")
    add_paragraph(doc, "Keywords: Safe Walking Assistant, Computer Vision, YOLO, Monocular Depth Estimation, Distance Estimation, Obstacle Detection, Blocker Detection, Voice Alerts, Spatial Reasoning.", first_line=False)

    add_heading(doc, "Introduction:")
    add_paragraph(doc, "People with visual impairment may need to combine a white cane, guide dog, personal knowledge, and assistance from other people to interpret obstacles and move through unfamiliar environments. A camera-based assistant cannot replace these safety methods, but it can provide an additional perception channel by describing relevant blockers, estimating distance, and presenting timely audio guidance.")
    add_paragraph(doc, "Many computer vision demonstrations stop at detecting an object and drawing a bounding box. For safe walking assistance, the more important questions are whether a blocker lies in the user's forward path, how far away it is, whether it is approaching, and what action should be taken. SafeStride Assist addresses these questions using a modular local-processing pipeline that combines visual detection, depth estimation, geometric reasoning, risk scoring, and concise speech feedback.")
    add_paragraph(doc, "Safe movement in an unfamiliar environment depends on understanding the relationship between the user, the ground, and nearby obstacles. A person, pole, door, vehicle, step, or other obstruction may be visible in the camera image but still be irrelevant if it is far to the side. Conversely, an unknown structure may be dangerous even when it is not represented by a detector class. This makes path-aware analysis important: the assistant must identify which visual information is close enough, high enough, and positioned within the user's forward walking corridor to deserve attention.")
    add_paragraph(doc, "SafeStride Assist is therefore designed as an additional perception and feedback layer rather than a replacement for a white cane, guide dog, or human support. The system uses a camera stream to estimate the scene, a depth model to approximate distance, and a spatial reasoning module to identify possible blockers in front of the user. Its output is deliberately short and action-oriented, for example reporting that the path is blocked, giving an approximate distance, and suggesting a clearer side. This approach connects computer vision results to a practical decision while keeping the user aware that the measurements are approximate.")
    add_paragraph(doc, "The project is designed around a simple human-centred principle: the assistant should remain quiet when the path is clear and speak only when the information can help the user make a safer immediate decision. This requires more than high model confidence. It requires temporal persistence, distance filtering, path membership, alert cooldowns, and a clear distinction between a warning and an urgent stop message. These design decisions connect the machine-learning output to a practical walking experience.")

    add_heading(doc, "Problem Statement:")
    add_paragraph(doc, "A visually impaired user needs timely information about obstacles in the walking path, but a standard object detector does not directly provide reliable distance, path relevance, or a recommended action. Unknown blockers may also be missed when the detector does not have a class for them. Repeated alerts can overload the user, while delayed or incomplete alerts reduce their practical value. Therefore, there is a need for an assistive safe-walking prototype that combines known obstacle detection with depth-based corridor analysis, approximate distance estimation, approach-risk assessment, and prioritised voice guidance.")

    add_heading(doc, "Literature Survey:")
    add_paragraph(doc, "Redmon et al. [1] introduced the YOLO family of one-stage object detectors, demonstrating that visual detection can be performed at high speed by processing the complete image in a single network. This supports the real-time detection component of SafeStride Assist, although the project uses a current Ultralytics YOLO checkpoint and filters the output to walking-relevant classes.")
    add_paragraph(doc, "Zhang et al. [2] proposed ByteTrack, a multi-object tracking method that associates high- and low-confidence detections to preserve object identities across frames. Temporal tracking is important for SafeStride Assist because persistence and approach speed help reduce one-frame false alerts and support time-to-collision reasoning.")
    add_paragraph(doc, "Yang et al. [3] introduced Depth Anything V2 for monocular depth estimation. The model supplies relative scene depth from a single camera frame. SafeStride Assist extends this capability with a ground-plane estimator and camera-height assumption to obtain a stable approximate metric scale for nearby walking hazards.")
    add_paragraph(doc, "Ranftl et al. [4] demonstrated the usefulness of monocular depth models for dense scene understanding. Their work highlights that relative depth captures scene structure but does not automatically provide a guaranteed real-world distance. This motivates the ground-plane scale correction and explicit safety limitations used in the proposed prototype.")
    add_paragraph(doc, "World Health Organization [5] reports the importance of accessible support for people with vision impairment. Assistive systems should therefore communicate only relevant information, use understandable feedback, and avoid presenting experimental computer vision as a replacement for established mobility aids. These principles guide SafeStride Assist's prioritised alerting and prototype safety boundary.")
    add_paragraph(doc, "Research on assistive computer vision also shows that perception quality and interaction design must be evaluated together. A detector may achieve good image-level accuracy but still be unsuitable if it speaks too frequently, gives an incorrect side instruction, or reports a distant object that does not affect the walking path. SafeStride Assist therefore treats distance, path relevance, and alert timing as first-class parts of the system rather than as optional display features.")
    add_paragraph(doc, "Khan et al. [7] systematically reviewed navigation assistants for blind and visually impaired people and identified continuing gaps in independent, reliable, and context-aware navigation. This supports SafeStride Assist's combination of perception, route guidance, and safety feedback rather than treating obstacle detection as an isolated task.")
    add_paragraph(doc, "Xu et al. [8] reviewed wearable electronic travel aids for obstacle avoidance. Their findings support combining camera-based perception with distance estimation and multimodal feedback, while also reinforcing that such systems should complement conventional mobility aids.")
    add_paragraph(doc, "Katzschmann et al. [9] demonstrated local navigation using time-of-flight sensing and haptic feedback. This provides direct support for distance-aware local hazard warnings and for offering feedback channels that do not depend only on speech.")
    add_paragraph(doc, "Eltaher et al. [10] reviewed urban navigation systems for visually impaired people, including route guidance and location-aware assistance. Their work supports SafeStride Assist's destination search, route instructions, heading alignment, off-route detection, and arrival state.")
    add_paragraph(doc, "Johannesson et al. [11] presented the Sound of Vision project, which explored converting visual scene information into auditory representations. This supports the use of concise directional voice feedback and spatial audio as a non-visual interface, while SafeStride Assist keeps its output intentionally shorter and action-oriented.")
    add_paragraph(doc, "Shull and Damian [12] reviewed haptic wearables as sensory replacement and sensory augmentation. Their analysis supports the future addition of haptic cues and the use of multimodal feedback when speech alone may be insufficient or distracting.")
    add_paragraph(doc, "Ranganeni et al. [13] studied different levels of control in a navigation assistant for blind travelers. Their results indicate that user preferences vary by situation, supporting SafeStride Assist's role as an assistive layer that provides guidance while preserving user agency rather than claiming full autonomous control.")
    add_paragraph(doc, "Zhang et al. [14] proposed an ARCore-based user-centric assistive navigation system for visually impaired people. This supports the feasibility of combining smartphone cameras, computer vision, positioning, and user-directed guidance in a portable application context.")
    add_paragraph(doc, "The literature further indicates that monocular depth should be treated as an estimate with scene-dependent uncertainty. Camera height, pitch, ground visibility, lighting, motion blur, and reflective surfaces affect the result. The proposed system addresses this by fitting a ground plane from lower-image points, smoothing scale estimates over recent frames, using a bounded forward corridor, and communicating the prototype's limitations instead of presenting distance as a guaranteed measurement.")

    add_heading(doc, "Existing System & its Drawback:")
    add_paragraph(doc, "Existing assistive systems include traditional mobility aids, low-cost electronic travel aids, GPS navigation applications, remote-assistance services, and camera-based computer-vision demonstrations. These systems provide valuable support, but they generally address only one part of the walking problem. A basic ultrasonic or Raspberry Pi prototype may report that an object is nearby, a GPS application may provide route instructions without describing local obstacles, and a camera detector may draw a label without deciding whether the object blocks the user's path. This creates a need for a system that combines perception, distance estimation, temporal reasoning, path analysis, and prioritised feedback.")
    add_heading(doc, "Drawbacks of Existing Systems:")
    drawbacks = [
        "Limited Reach of Manual Aids: Khan et al. [7] explain that electronic travel aids should complement, rather than replace, a white cane, guide dog, or human assistance. Manual aids remain essential but may provide limited information about distant, overhead, moving, or unfamiliar obstacles.",
        "Simple Fixed-Range Warnings: Low-cost ultrasonic, Arduino, or Raspberry Pi systems often report only that an object is within a predefined range. They may not identify the obstacle, estimate its direction, determine whether it blocks the path, or recommend an appropriate action.",
        "Limited Processing on Low-Cost Hardware: Camera-based prototypes running on embedded computers may experience reduced frame rates or delayed alerts when object detection, tracking, and depth estimation are performed together. This can reduce usefulness in rapidly changing scenes.",
        "GPS Does Not Describe Nearby Hazards: GPS navigation applications can provide route and destination guidance, but they generally cannot identify a sudden obstacle, blocked corridor, indoor hazard, or object entering the user's immediate path.",
        "No Walking-Corridor Reasoning: Many camera demonstrations detect objects in the image without deciding whether they lie within the user's forward walking corridor. This can produce warnings for objects that are visible but not directly relevant to the user's path.",
        "Unknown Blockers May Be Missed: Assistive vision systems depend on their sensing and recognition models. Temporary structures, low-contrast hazards, transparent objects, and objects without trained classes may therefore remain undetected.",
        "Limited Ground-Change Awareness: General obstacle detectors may not reliably distinguish every curb, step, or change in ground level from ordinary scene structure. This remains a secondary extension area for SafeStride Assist rather than the main focus of the current prototype.",
        "Repeated and Low-Value Alerts: Frequent announcements can increase cognitive load and make urgent information harder to notice. A system must consider persistence, distance, path relevance, and alert priority rather than speaking for every detection.",
        "Weak Temporal Reasoning: Frame-by-frame analysis does not establish whether an obstacle is approaching, stationary, or moving across the walking path. Tracking methods such as ByteTrack [2] are needed to provide more stable temporal evidence.",
        "Dependence on Connectivity or Remote Assistance: Remote-assistance services can provide useful human scene interpretation, but they depend on network availability, service response time, privacy conditions, and operator availability.",
        "Unclear Safety Boundaries: Ranftl et al. [4] show that monocular depth is useful for scene structure but does not automatically provide guaranteed real-world distance. Experimental systems must communicate uncertainty and must not be treated as replacements for certified mobility support."
    ]
    for item in drawbacks:
        heading, explanation = item.split(": ", 1)
        paragraph = doc.add_paragraph(style="List Bullet")
        paragraph.paragraph_format.space_after = Pt(3)
        paragraph.paragraph_format.line_spacing = 1.0
        bold_run = paragraph.add_run(heading + ": ")
        set_run_font(bold_run, size=11, bold=True)
        body_run = paragraph.add_run(explanation)
        set_run_font(body_run, size=11)

    add_heading(doc, "Proposed Methodology:")
    add_paragraph(doc, "The proposed SafeStride Assist system is a local, AI-based safe-walking assistant that processes camera frames and generates concise voice guidance. It combines YOLO obstacle detection, ByteTrack temporal tracking, Depth Anything V2 monocular depth estimation, RANSAC ground-plane fitting, a three-dimensional walking-corridor model, approach-risk estimation, and prioritised speech feedback. The system can detect known obstacles and can also identify unknown blockers from depth points that rise above the estimated ground plane within the forward corridor.")
    add_paragraph(doc, "The distance algorithm begins by converting the depth map into three-dimensional points using a pinhole-camera model and an estimated focal length. A RANSAC procedure searches the lower image for a stable horizontal ground plane while rejecting points belonging to people, walls, vehicles, and other outliers. The known approximate camera height is then used to estimate a scale factor. Recent valid scale estimates are retained in a short history and combined using a median, reducing sudden distance changes caused by individual noisy frames.")
    add_paragraph(doc, "After scale correction, the spatial analyser tests each point against a one-metre-wide corridor extending from approximately 0.8 metres to three metres in front of the camera. Points that rise above the ground plane within the configured obstacle-height range are treated as possible blockers. If enough valid points are present, the nearest robust depth percentile is selected as the obstacle distance. The distribution of front-facing points is then used to estimate clock direction and whether a left or right side appears clearer.")
    add_paragraph(doc, "The alert decision layer combines corridor status with named obstacle detections, tracking persistence, estimated approach speed, and time-to-collision. A nearby path blocker receives higher priority than a distant obstacle outside the corridor. The announcer waits briefly for persistence to remove one-frame false positives, prevents messages from interrupting each other unnecessarily, and repeats an alert only after a cooldown or meaningful reduction in distance. This produces short messages such as 'Stop. Path blocked, 2 meters. Keep left.'")
    add_paragraph(doc, "The key features of the proposed system include:")
    features = [
        "Real-Time Obstacle Detection: Uses YOLO to identify walking-relevant obstacles from webcam or video frames.",
        "Temporal Obstacle Tracking: Uses ByteTrack to maintain obstacle identity and support persistence and approach analysis.",
        "Monocular Distance Estimation: Uses Depth Anything V2 and ground-plane scale correction to estimate approximate distance in metres.",
        "Walking-Corridor Analysis: Evaluates a one-metre-wide corridor up to three metres ahead of the camera.",
        "Unknown Blocker Detection: Detects depth points that rise from the ground even when no named obstacle class is available.",
        "Actionable Voice Alerts: Produces messages containing obstacle type, distance, direction, urgency, and recommended side.",
        "Local Browser Console: Displays the annotated feed, path state, depth status, alert priority, captions, and diagnostics.",
        "Safety-Oriented Alerting: Uses persistence, cooldowns, urgency, and path priority so that the most relevant warning is spoken first."
    ]
    for index, item in enumerate(features, start=1):
        add_bullet(doc, item, number=index)

    add_heading(doc, "Objectives:")
    add_paragraph(doc, "The primary objectives of the proposed system are:", first_line=False)
    objectives = [
        "To develop a real-time computer vision pipeline for safe-walking assistance using a camera stream.",
        "To detect walking-relevant obstacles using YOLO and track them over time with ByteTrack.",
        "To estimate approximate obstacle distance using monocular depth and ground-plane calibration.",
        "To analyse a three-metre forward corridor and determine whether it is blocked.",
        "To detect unknown depth-based blockers that do not have a recognised obstacle label.",
        "To generate concise voice alerts containing obstacle distance, direction, urgency, and guidance.",
        "To reduce false and repeated alerts using persistence checks, cooldowns, and priority ranking.",
        "To provide a browser console for monitoring the live feed, path status, and alert state.",
        "To establish a foundation for future custom hazard and environmental-state models."
    ]
    for item in objectives:
        add_bullet(doc, item)

    add_heading(doc, "Proposed System Advantages:")
    advantages = [
        "Distance-Aware Assistance: Converts relative monocular depth into an approximate distance that can be included in speech feedback.",
        "Known and Unknown Blocker Reasoning: Combines named YOLO obstacles with depth-based corridor analysis for hazards without a trained class.",
        "Walking-Path Relevance: Estimates whether an obstacle lies inside the forward corridor instead of treating every detected region equally.",
        "Actionable Feedback: Provides a recommended clear side when the geometry supports a left or right correction.",
        "Reduced Alert Overload: Uses persistence, urgency, cooldowns, and priority ranking to keep speech concise and meaningful.",
        "Real-Time Demonstration: Supports webcam and recorded-video processing with an annotated browser console.",
        "Modular and Extensible Design: Separates detection, depth, spatial reasoning, risk analysis, and speech so future hazard models can be evaluated independently.",
        "Clear Safety Boundary: Reports the system as an educational prototype with approximate distance rather than a certified mobility device."
    ]
    for item in advantages:
        add_bullet(doc, item)

    add_heading(doc, "Implementation Scope and Safety Considerations:")
    add_paragraph(doc, "The current implementation supports IP-camera and recorded-video inputs, local inference, an annotated browser console, depth status, path overlays, obstacle captions, and Windows/browser speech output. The system can operate in a detection-only configuration when experimental custom hazard weights are disabled. The current standard model is intended for a demonstration and should be evaluated on representative clips before any change in camera position, camera height, lighting, or operating environment.")
    add_paragraph(doc, "The distance result is approximate and should be interpreted as an assistance cue rather than a certified measurement. A poor ground-plane fit, a tilted camera, a hidden floor, a moving camera, heavy crowding, or a reflective surface can affect the estimate. The system may miss small, transparent, overhead, or unusual hazards, and it may incorrectly classify visual structures as blockers. Testing should be performed with appropriate supervision and conventional mobility safety methods. No claim is made that the assistant detects every obstacle or guarantees a safe path.")
    add_paragraph(doc, "Evaluation should include both model metrics and end-to-end interaction metrics. Useful measurements include obstacle precision and recall, false-alert rate, missed-blocker rate, distance-estimation error, path-blocking accuracy, alert latency, frames per second, and the time required for an alert to become stable. Test groups should include clear paths, pedestrians, vehicles, poles, stairs, doors, crowded scenes, low-light scenes, motion blur, and clips containing unknown blockers. These measurements will guide future calibration and custom hazard-model training.")

    add_heading(doc, "Software Requirements:")
    add_requirements_table(doc, ["SOFTWARE", "SPECIFICATION"], [
        ("OPERATING SYSTEM", "Windows 11 / Ubuntu 22.04 LTS"),
        ("PROGRAMMING LANGUAGE", "Python 3.10 or higher"),
        ("COMPUTER VISION LIBRARY", "OpenCV"),
        ("OBJECT DETECTION MODEL", "YOLO11s using Ultralytics"),
        ("OBJECT TRACKING", "ByteTrack"),
        ("DEPTH ESTIMATION MODEL", "Depth Anything V2"),
        ("DEEP LEARNING FRAMEWORK", "PyTorch"),
        ("WEB INTERFACE", "HTML, CSS, JavaScript, and browser speech synthesis"),
        ("INPUT SUPPORT", "IP webcam, USB webcam, uploaded video, or recorded test clip")
    ], [2.5, 4.8])

    add_heading(doc, "Hardware Requirements:")
    add_requirements_table(doc, ["HARDWARE", "UNIT", "SPECIFICATION"], [
        ("PROCESSOR", "1", "Intel Core i5 / i7 or equivalent"),
        ("GRAPHICS PROCESSING UNIT", "1", "NVIDIA GPU with CUDA support recommended"),
        ("RAM", "1", "8 GB minimum; 16 GB recommended"),
        ("STORAGE", "1", "256 GB SSD or higher"),
        ("CAMERA", "1", "IP webcam, USB webcam, or digital camera with video output"),
        ("AUDIO OUTPUT", "1", "Speaker or headphones for voice alerts")
    ], [2.5, 0.8, 4.0])

    add_heading(doc, "References:")
    references = [
        "Redmon, J., Divvala, S., Girshick, R., Farhadi, A.: You Only Look Once: Unified, Real-Time Object Detection. Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition (CVPR), 2016.",
        "Zhang, Y., Sun, P., Jiang, Y., et al.: ByteTrack: Multi-Object Tracking by Associating Every Detection Box. European Conference on Computer Vision (ECCV), 2022.",
        "Yang, L., Kang, B., Huang, Z., et al.: Depth Anything V2. Advances in Neural Information Processing Systems, 2024. https://arxiv.org/abs/2406.09414.",
        "Ranftl, R., Bochkovskiy, A., and Koltun, V.: Vision Transformers for Dense Prediction. Proceedings of the IEEE International Conference on Computer Vision (ICCV), 2021.",
        "Ultralytics: Ultralytics YOLO Documentation. https://docs.ultralytics.com/.",
        "World Health Organization: World Report on Vision. World Health Organization, 2019. https://www.who.int/publications/i/item/9789241516570.",
        "Khan, S., Nazir, S., and Khan, H. U.: Analysis of Navigation Assistants for Blind and Visually Impaired People: A Systematic Review. IEEE Access, 9, 26712-26734, 2021. https://doi.org/10.1109/ACCESS.2021.3052415.",
        "Xu, J., et al.: Wearable Obstacle Avoidance Electronic Travel Aids for Blind and Visually Impaired Individuals: A Systematic Review. IEEE Access, 2023. https://doi.org/10.1109/ACCESS.2023.3285396.",
        "Katzschmann, R. K., Araki, B., and Rus, D.: Safe Local Navigation for Visually Impaired Users With a Time-of-Flight and Haptic Feedback Device. IEEE Transactions on Neural Systems and Rehabilitation Engineering, 26(3), 583-593, 2018. https://doi.org/10.1109/TNSRE.2018.2800665.",
        "Eltaher, M., et al.: A Systematic Review of Urban Navigation Systems for Visually Impaired People. Sensors, 21(9), 3103, 2021. https://doi.org/10.3390/s21093103.",
        "Johannesson, O. I., et al.: The Sound of Vision Project: The Concept and First Results. Brain Sciences, 6(3), 20, 2016. https://doi.org/10.3390/brainsci6030020.",
        "Shull, P. B., and Damian, D. D.: Haptic Wearables as Sensory Replacement, Sensory Augmentation and Trainer: A Review. Journal of NeuroEngineering and Rehabilitation, 12, 59, 2015. https://doi.org/10.1186/s12984-015-0055-z.",
        "Ranganeni, V., Sinclair, M., Ofek, E., Miller, A., Campbell, J., Kolobov, A., and Cutrell, E.: Exploring Levels of Control for a Navigation Assistant for Blind Travelers. Proceedings of the ACM/IEEE International Conference on Human-Robot Interaction, 4-12, 2023. https://doi.org/10.1145/3568162.3578630.",
        "Zhang, C., et al.: An ARCore Based User Centric Assistive Navigation System for Visually Impaired People. Applied Sciences, 9(5), 989, 2019. https://doi.org/10.3390/app9050989."
    ]
    for index, reference in enumerate(references, start=1):
        add_reference(doc, index, reference)

    add_heading(doc, "Guide Details:")
    guide = doc.add_table(rows=3, cols=2)
    guide.alignment = WD_TABLE_ALIGNMENT.LEFT
    guide.style = "Table Grid"
    set_table_borders(guide)
    for row, (label, value) in enumerate([
        ("Guide Name", "____________________________________________"),
        ("Designation", "____________________________________________"),
        ("Signature", "____________________________________________"),
    ]):
        set_cell_text(guide.rows[row].cells[0], label, bold=True, size=10)
        set_cell_text(guide.rows[row].cells[1], value, size=10)
        remove_cell_shading(guide.rows[row].cells[0])

    doc.save(OUT)
    print(OUT)


if __name__ == "__main__":
    build_document()
