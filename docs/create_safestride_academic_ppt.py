from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt

ROOT = Path(__file__).parents[1]
OUT = ROOT / "docs" / "SafeStride_Assist_Presentation.pptx"
ALT_OUT = ROOT / "docs" / "SafeStride_B15_Presentation.pptx"
ICON = ROOT / "mobile" / "assets" / "icon.png"

NAVY = RGBColor(20, 42, 63)
BLUE = RGBColor(39, 105, 154)
TEAL = RGBColor(37, 151, 145)
PALE = RGBColor(237, 247, 248)
PALE_BLUE = RGBColor(235, 243, 250)
INK = RGBColor(29, 43, 54)
GRAY = RGBColor(91, 108, 119)
LIGHT = RGBColor(226, 234, 237)
WHITE = RGBColor(255, 255, 255)
ORANGE = RGBColor(224, 135, 57)
RED = RGBColor(190, 67, 67)

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]


def shape(slide, x, y, w, h, fill=WHITE, line=LIGHT, rounded=False):
    item = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE,
        Inches(x), Inches(y), Inches(w), Inches(h),
    )
    item.fill.solid()
    item.fill.fore_color.rgb = fill
    item.line.color.rgb = line
    item.line.width = Pt(1)
    if rounded:
        item.adjustments[0] = 0.06
    return item


def text(slide, value, x, y, w, h, size=18, color=INK, bold=False,
         font="Aptos", align=PP_ALIGN.LEFT, valign=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = Inches(0.05)
    frame.margin_right = Inches(0.05)
    frame.margin_top = Inches(0.02)
    frame.margin_bottom = Inches(0.02)
    frame.vertical_anchor = valign
    p = frame.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = value
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    return box


def bullets(slide, items, x, y, w, h, size=17, color=INK, gap=7):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = Inches(0.04)
    frame.margin_right = Inches(0.04)
    for i, item in enumerate(items):
        p = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        p.text = "• " + item
        p.font.name = "Aptos"
        p.font.size = Pt(size)
        p.font.color.rgb = color
        p.space_after = Pt(gap)
    return box


def line(slide, x1, y1, x2, y2, color=BLUE, width=2, arrow=False):
    item = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    item.line.color.rgb = color
    item.line.width = Pt(width)
    if arrow:
        item.line.end_arrowhead = True
    return item


def header(title, section, number):
    slide = prs.slides.add_slide(BLANK)
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = WHITE
    shape(slide, 0, 0, 13.333, 0.22, fill=NAVY, line=NAVY)
    text(slide, "SAFESTRIDE ASSIST", 0.65, 0.38, 3.2, 0.22, size=10, color=TEAL, bold=True, font="Aptos Mono")
    text(slide, section.upper(), 10.1, 0.38, 2.55, 0.22, size=10, color=GRAY, bold=True, font="Aptos Mono", align=PP_ALIGN.RIGHT)
    text(slide, title, 0.65, 0.75, 11.6, 0.5, size=28, color=NAVY, bold=True)
    shape(slide, 0.65, 1.38, 12.0, 0.02, fill=LIGHT, line=LIGHT)
    text(slide, f"B15  |  {number:02d}", 11.55, 7.08, 1.05, 0.18, size=9, color=GRAY, font="Aptos Mono", align=PP_ALIGN.RIGHT)
    return slide


def tag(slide, value, x, y, w, fill=PALE_BLUE, color=BLUE):
    shape(slide, x, y, w, 0.32, fill=fill, line=fill, rounded=True)
    text(slide, value, x, y + 0.055, w, 0.18, size=10, color=color, bold=True, align=PP_ALIGN.CENTER)


def diagram_node(slide, title, body, x, y, w, h, fill=PALE_BLUE, accent=BLUE):
    shape(slide, x, y, w, h, fill=fill, line=accent, rounded=True)
    shape(slide, x, y, 0.08, h, fill=accent, line=accent)
    text(slide, title, x + 0.22, y + 0.18, w - 0.35, 0.28, size=16, color=NAVY, bold=True)
    text(slide, body, x + 0.22, y + 0.58, w - 0.35, h - 0.7, size=13, color=GRAY)


def camera_visual(slide, x, y, w, h):
    shape(slide, x, y, w, h, fill=RGBColor(28, 47, 57), line=NAVY, rounded=True)
    # Ground and horizon.
    shape(slide, x + 0.12, y + 0.12, w - 0.24, h * 0.42, fill=RGBColor(76, 105, 112), line=RGBColor(76, 105, 112))
    shape(slide, x + 0.12, y + h * 0.54, w - 0.24, h * 0.34, fill=RGBColor(92, 113, 101), line=RGBColor(92, 113, 101))
    line(slide, x + 0.12, y + h * 0.54, x + w - 0.12, y + h * 0.54, color=WHITE, width=1)
    # Forward corridor.
    corridor = slide.shapes.add_shape(MSO_SHAPE.ISOSCELES_TRIANGLE, Inches(x + w * 0.35), Inches(y + h * 0.5), Inches(w * 0.3), Inches(h * 0.34))
    corridor.rotation = 180
    corridor.fill.solid()
    corridor.fill.fore_color.rgb = RGBColor(88, 194, 180)
    corridor.fill.transparency = 55
    corridor.line.color.rgb = TEAL
    # Obstacle.
    shape(slide, x + w * 0.56, y + h * 0.43, w * 0.13, h * 0.22, fill=ORANGE, line=ORANGE, rounded=True)
    text(slide, "2.0 m", x + w * 0.69, y + h * 0.44, w * 0.22, 0.22, size=11, color=WHITE, bold=True)
    text(slide, "FORWARD CORRIDOR", x + 0.25, y + h - 0.48, w - 0.5, 0.22, size=11, color=WHITE, bold=True, font="Aptos Mono", align=PP_ALIGN.CENTER)
    tag(slide, "PATH BLOCKED", x + 0.25, y + 0.25, 1.45, fill=RGBColor(255, 236, 218), color=RED)


def code_panel(slide, title, code, x, y, w, h):
    shape(slide, x, y, w, h, fill=RGBColor(247, 250, 251), line=LIGHT, rounded=True)
    text(slide, title.upper(), x + 0.2, y + 0.18, w - 0.4, 0.2, size=10, color=TEAL, bold=True, font="Aptos Mono")
    text(slide, code, x + 0.2, y + 0.56, w - 0.4, h - 0.7, size=12, color=INK, font="Cascadia Mono")


def formula_panel(slide, title, formulas, x, y, w, h, accent=TEAL):
    shape(slide, x, y, w, h, fill=RGBColor(247, 250, 251), line=accent, rounded=True)
    text(slide, title.upper(), x + 0.2, y + 0.18, w - 0.4, 0.2, size=10, color=accent, bold=True, font="Aptos Mono")
    text(slide, formulas, x + 0.25, y + 0.62, w - 0.5, h - 0.85, size=19, color=NAVY, font="Cambria Math", align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)


# 1. Starting slide
slide = prs.slides.add_slide(BLANK)
slide.background.fill.solid()
slide.background.fill.fore_color.rgb = PALE
shape(slide, 0, 0, 13.333, 0.3, fill=NAVY, line=NAVY)
shape(slide, 0, 0.3, 0.3, 7.2, fill=TEAL, line=TEAL)
if ICON.exists():
    slide.shapes.add_picture(str(ICON), Inches(10.65), Inches(0.75), width=Inches(1.45), height=Inches(1.45))
text(slide, "THE NATIONAL INSTITUTE OF ENGINEERING", 0.85, 0.75, 8.5, 0.3, size=14, color=NAVY, bold=True)
text(slide, "DEPARTMENT OF COMPUTER SCIENCE & ENGINEERING", 0.85, 1.12, 8.5, 0.28, size=12, color=GRAY)
text(slide, "PROJECT SYNOPSIS", 0.85, 1.9, 3.2, 0.25, size=12, color=TEAL, bold=True, font="Aptos Mono")
text(slide, "SafeStride Assist", 0.85, 2.35, 7.7, 0.65, size=40, color=NAVY, bold=True)
text(slide, "An AI-Based Safe Walking Assistant Using Monocular Depth Estimation", 0.88, 3.15, 7.6, 0.65, size=22, color=BLUE, bold=True)
text(slide, "Real-time perception  |  spatial reasoning  |  voice feedback", 0.88, 4.12, 7.2, 0.3, size=16, color=GRAY)
shape(slide, 8.6, 2.2, 3.1, 2.9, fill=WHITE, line=LIGHT, rounded=True)
text(slide, "CAMERA", 9.0, 2.65, 2.3, 0.25, size=17, color=BLUE, bold=True, align=PP_ALIGN.CENTER)
line(slide, 10.15, 3.0, 10.15, 3.38, color=TEAL, width=2, arrow=True)
text(slide, "DEPTH + PATH", 9.0, 3.45, 2.3, 0.25, size=17, color=TEAL, bold=True, align=PP_ALIGN.CENTER)
line(slide, 10.15, 3.8, 10.15, 4.18, color=TEAL, width=2, arrow=True)
text(slide, "VOICE ALERT", 9.0, 4.25, 2.3, 0.25, size=17, color=ORANGE, bold=True, align=PP_ALIGN.CENTER)
text(slide, "Batch B15  |  Major Project", 0.88, 6.62, 4.5, 0.25, size=14, color=GRAY)

# 2. Abstract
slide = header("Abstract", "Overview", 2)
shape(slide, 0.85, 1.75, 7.05, 4.85, fill=PALE_BLUE, line=PALE_BLUE, rounded=True)
text(slide, "SafeStride Assist is a research and teaching prototype for safer walking assistance.", 1.2, 2.1, 6.35, 0.7, size=24, color=NAVY, bold=True)
text(slide, "It combines YOLO-based detection, ByteTrack tracking, Depth Anything V2, ground-plane calibration, and speech feedback. The central method evaluates a three-metre forward walking corridor instead of reporting every object in the camera view.", 1.2, 3.1, 6.3, 1.1, size=18, color=INK)
text(slide, "The output is a concise action such as: Stop. Path blocked, 2 meters. Keep left. Processing is local by default, and the system is explicitly an educational prototype rather than a certified mobility or emergency device.", 1.2, 4.65, 6.3, 1.1, size=17, color=GRAY)
for i, (head, body, color) in enumerate([("PERCEIVE", "camera + models", BLUE), ("REASON", "depth + corridor", TEAL), ("GUIDE", "voice + captions", ORANGE)]):
    x = 8.45 + (i % 1) * 0.0
    y = 1.85 + i * 1.45
    shape(slide, x, y, 3.85, 0.95, fill=WHITE, line=color, rounded=True)
    text(slide, head, x + 0.2, y + 0.16, 1.25, 0.25, size=14, color=color, bold=True)
    text(slide, body, x + 1.55, y + 0.16, 2.0, 0.25, size=17, color=NAVY, bold=True)

# 3. Index
slide = header("Index", "Presentation roadmap", 3)
index_items = [
    "Introduction and motivation", "Problem statement", "Literature review", "System architecture",
    "System design and data flow", "Algorithm code snippets", "Implementation and evaluation",
    "Novelty and contribution", "Limitations and safety", "Conclusion and references",
]
for i, item in enumerate(index_items):
    x = 1.0 + (i // 5) * 6.0
    y = 1.75 + (i % 5) * 0.87
    shape(slide, x, y, 0.55, 0.38, fill=TEAL if i < 5 else BLUE, line=TEAL if i < 5 else BLUE, rounded=True)
    text(slide, f"{i + 1:02d}", x, y + 0.07, 0.55, 0.2, size=11, color=WHITE, bold=True, font="Aptos Mono", align=PP_ALIGN.CENTER)
    text(slide, item, x + 0.82, y + 0.02, 4.7, 0.3, size=19, color=NAVY, bold=True)
    shape(slide, x + 0.82, y + 0.52, 4.75, 0.02, fill=LIGHT, line=LIGHT)

# 4. Introduction
slide = header("Introduction", "Motivation", 4)
text(slide, "Assistive technology should reduce uncertainty without removing the user's control.", 0.9, 1.75, 7.25, 0.65, size=26, color=NAVY, bold=True)
bullets(slide, [
    "Traditional mobility aids remain essential for safe navigation.",
    "A camera can provide an additional perception channel in unfamiliar environments.",
    "The useful question is not only what is visible, but what is relevant to the forward path.",
    "Feedback must be short, prioritised, and understandable under time pressure.",
], 0.95, 2.75, 6.55, 2.55, size=18, gap=12)
camera_visual(slide, 8.25, 1.8, 3.8, 4.55)
text(slide, "Illustrative camera view with a walking corridor and distance-aware blocker", 8.25, 6.48, 3.8, 0.3, size=11, color=GRAY, align=PP_ALIGN.CENTER)

# 5. Problem statement
slide = header("Problem statement", "Need", 5)
shape(slide, 0.9, 1.75, 5.55, 4.95, fill=RGBColor(254, 245, 242), line=RGBColor(244, 211, 199), rounded=True)
text(slide, "Detection alone is insufficient", 1.3, 2.1, 4.7, 0.45, size=25, color=RED, bold=True)
bullets(slide, [
    "A bounding box does not indicate path relevance.",
    "A class label does not provide distance or urgency.",
    "Unknown blockers may not belong to a trained class.",
    "Frame-by-frame alerts can overwhelm the user.",
], 1.3, 2.95, 4.5, 2.3, size=18, gap=11)
shape(slide, 6.9, 1.75, 5.55, 4.95, fill=PALE, line=RGBColor(180, 226, 221), rounded=True)
text(slide, "SafeStride must decide", 7.3, 2.1, 4.7, 0.45, size=25, color=TEAL, bold=True)
for i, item in enumerate(["Is the path blocked?", "How far away is it?", "Which side is clearer?", "Should the system speak now?"]):
    y = 2.95 + i * 0.7
    shape(slide, 7.35, y, 0.35, 0.35, fill=TEAL, line=TEAL, rounded=True)
    text(slide, str(i + 1), 7.35, y + 0.07, 0.35, 0.18, size=11, color=WHITE, bold=True, align=PP_ALIGN.CENTER)
    text(slide, item, 7.95, y + 0.02, 3.9, 0.28, size=19, color=NAVY, bold=True)

# 6. Literature review
slide = header("Literature review", "Research foundation", 6)
rows = [
    ("Real-time detection", "YOLO [1]", "Fast visual object detection", BLUE),
    ("Temporal tracking", "ByteTrack [2]", "Stable identities across frames", TEAL),
    ("Monocular depth", "Depth Anything V2 [3]", "Relative scene-depth estimation", ORANGE),
    ("Assistive navigation", "Khan, Xu, Eltaher [7, 8, 10]", "Navigation and obstacle-avoidance reviews", BLUE),
    ("Multimodal feedback", "Katzschmann, Johannesson, Shull [9, 11, 12]", "Haptic and audio guidance", TEAL),
    ("User-centred control", "Ranganeni, Zhang [13, 14]", "Agency and accessible route assistance", ORANGE),
]
for i, (topic, citation, finding, color) in enumerate(rows):
    y = 1.65 + i * 0.78
    shape(slide, 0.95, y, 2.35, 0.55, fill=color, line=color, rounded=True)
    text(slide, topic, 1.05, y + 0.15, 2.15, 0.22, size=14, color=WHITE, bold=True, align=PP_ALIGN.CENTER)
    text(slide, citation, 3.65, y + 0.08, 2.6, 0.3, size=16, color=NAVY, bold=True)
    text(slide, finding, 6.65, y + 0.08, 5.3, 0.3, size=16, color=GRAY)
shape(slide, 1.0, 6.45, 11.7, 0.45, fill=PALE, line=PALE, rounded=True)
text(slide, "Gap addressed: integrate perception, geometry, temporal evidence, risk, and human-centred feedback in one local workflow.", 1.25, 6.57, 11.2, 0.2, size=15, color=NAVY, bold=True, align=PP_ALIGN.CENTER)

# 7. System architecture
slide = header("System architecture", "Proposed system", 7)
text(slide, "The architecture separates sensing, spatial reasoning, decisions, and interaction.", 0.9, 1.63, 11.3, 0.35, size=19, color=GRAY)
architecture = [
    ("INPUT", "IP webcam\nUSB webcam\nvideo clip", 0.9, 2.35, 2.05, 1.25, PALE_BLUE, BLUE),
    ("PERCEPTION", "YOLO detection\nByteTrack\nDepth Anything V2", 3.45, 2.35, 2.35, 1.25, PALE, TEAL),
    ("SPATIAL REASONING", "Ground plane\n3D projection\n3 m corridor", 6.25, 2.35, 2.35, 1.25, RGBColor(255, 247, 232), ORANGE),
    ("DECISION", "Risk + TTC\npriority\ncooldown", 9.05, 2.35, 1.9, 1.25, RGBColor(254, 245, 242), RED),
    ("USER OUTPUT", "Browser console\nvoice\ncaptions", 11.4, 2.35, 1.25, 1.25, PALE_BLUE, BLUE),
]
for title, body, x, y, w, h, fill, accent in architecture:
    diagram_node(slide, title, body, x, y, w, h, fill=fill, accent=accent)
for x in [2.95, 5.85, 8.65, 10.98]:
    line(slide, x, 2.98, x + 0.38, 2.98, color=NAVY, width=2, arrow=True)
shape(slide, 1.35, 4.5, 10.7, 1.15, fill=PALE_BLUE, line=BLUE, rounded=True)
text(slide, "Safety priority", 1.7, 4.78, 1.6, 0.25, size=15, color=BLUE, bold=True)
text(slide, "urgent camera obstruction  >  local path correction  >  background route/status information", 3.45, 4.75, 8.0, 0.3, size=18, color=NAVY, bold=True, align=PP_ALIGN.CENTER)
text(slide, "Local processing keeps the core perception loop independent of remote cloud services.", 1.35, 6.2, 10.7, 0.28, size=15, color=GRAY, align=PP_ALIGN.CENTER)

# 8. System design and data flow
slide = header("System design and data flow", "How the prototype works", 8)
steps = [("1", "Capture", "frame"), ("2", "Detect + track", "objects"), ("3", "Estimate depth", "geometry"), ("4", "Evaluate corridor", "path status"), ("5", "Rank alert", "urgency"), ("6", "Speak", "guidance")]
for i, (num, title, body) in enumerate(steps):
    x = 0.85 + i * 2.05
    shape(slide, x, 2.0, 1.65, 1.25, fill=PALE_BLUE if i % 2 == 0 else PALE, line=BLUE if i % 2 == 0 else TEAL, rounded=True)
    text(slide, num, x + 0.12, 2.18, 0.35, 0.28, size=14, color=ORANGE, bold=True, font="Aptos Mono")
    text(slide, title, x + 0.12, 2.55, 1.4, 0.3, size=16, color=NAVY, bold=True, align=PP_ALIGN.CENTER)
    text(slide, body, x + 0.12, 2.92, 1.4, 0.2, size=12, color=GRAY, align=PP_ALIGN.CENTER)
    if i < len(steps) - 1:
        line(slide, x + 1.68, 2.62, x + 1.95, 2.62, color=NAVY, width=2, arrow=True)
camera_visual(slide, 0.9, 4.05, 4.0, 2.2)
shape(slide, 5.25, 4.05, 3.0, 2.2, fill=RGBColor(247, 250, 251), line=LIGHT, rounded=True)
text(slide, "STATE", 5.55, 4.35, 2.35, 0.22, size=11, color=TEAL, bold=True, font="Aptos Mono", align=PP_ALIGN.CENTER)
text(slide, "Path: BLOCKED\nNearest: 2.0 m\nDirection: right\nAdvice: KEEP LEFT", 5.55, 4.85, 2.35, 1.0, size=17, color=NAVY, bold=True, align=PP_ALIGN.CENTER)
shape(slide, 8.6, 4.05, 3.8, 2.2, fill=RGBColor(254, 245, 242), line=RGBColor(244, 211, 199), rounded=True)
text(slide, "VOICE OUTPUT", 8.95, 4.35, 3.1, 0.22, size=11, color=RED, bold=True, font="Aptos Mono", align=PP_ALIGN.CENTER)
text(slide, "Stop. Path blocked,\n2 meters. Keep left.", 8.95, 4.95, 3.1, 0.75, size=20, color=NAVY, bold=True, align=PP_ALIGN.CENTER)

# 9. Geometry and corridor
slide = header("Spatial reasoning", "System design detail", 9)
text(slide, "The key design decision is to evaluate the user's forward corridor, not every detected object.", 0.9, 1.62, 11.4, 0.35, size=19, color=GRAY)
camera_visual(slide, 0.9, 2.05, 5.15, 3.95)
shape(slide, 6.6, 2.05, 5.5, 3.95, fill=PALE, line=RGBColor(180, 226, 221), rounded=True)
text(slide, "Corridor reasoning", 7.0, 2.42, 4.7, 0.35, size=23, color=TEAL, bold=True)
bullets(slide, [
    "Estimate relative depth with Depth Anything V2.",
    "Fit a ground plane using the lower image region.",
    "Project depth into approximate 3D points.",
    "Evaluate a one-metre-wide corridor up to three metres ahead.",
    "Mark named or unknown blockers as in_path when geometry supports it.",
], 7.0, 3.12, 4.5, 2.3, size=16, gap=9)

# 10. Algorithm formulas
slide = header("Mathematical formulation", "Algorithm design", 10)
text(slide, "The implementation combines learned estimates with deterministic geometric and risk rules.", 0.9, 1.62, 11.4, 0.35, size=19, color=GRAY)
formula_panel(slide, "Depth to approximate distance", "Z ~= (f * H) / h\n\nX = (u - c_x) Z / f_x\nY = (v - c_y) Z / f_y", 0.85, 2.0, 3.75, 3.85, accent=BLUE)
formula_panel(slide, "Ground plane and corridor", "pi: aX + bY + cZ + d = 0\n\nC = {p : |X| <= 0.5,\n0.8 <= Z <= 3.0}\n\nblocked = 1 if |C_blocked| >= tau", 4.8, 2.0, 3.75, 3.85, accent=TEAL)
formula_panel(slide, "Risk and alert priority", "TTC = d / max(v_app, eps)\n\nR = w_p P + w_d / (d + eps)\n    + w_t / (TTC + eps)\n    + w_s S\n\nalert = argmax(R)", 8.75, 2.0, 3.75, 3.85, accent=ORANGE)
text(slide, "Z: estimated distance  |  f: focal length  |  H: camera height  |  h: image height  |  tau: blocker threshold", 1.0, 6.25, 11.2, 0.25, size=13, color=GRAY, align=PP_ALIGN.CENTER)

# 11. Implementation and evaluation
slide = header("Implementation and evaluation", "Prototype scope", 11)
shape(slide, 0.9, 1.75, 5.65, 4.75, fill=PALE_BLUE, line=PALE_BLUE, rounded=True)
text(slide, "Implemented stack", 1.3, 2.1, 3.4, 0.35, size=24, color=NAVY, bold=True)
bullets(slide, [
    "Python 3.10+ and PyTorch",
    "OpenCV and Ultralytics YOLO11s",
    "ByteTrack and Depth Anything V2",
    "Browser live console with captions and speech",
    "IP webcam, USB webcam, uploaded video, or test clip",
], 1.3, 2.85, 4.65, 2.45, size=17, gap=10)
shape(slide, 6.95, 1.75, 5.45, 4.75, fill=RGBColor(255, 247, 232), line=RGBColor(246, 220, 178), rounded=True)
text(slide, "Evaluation measures", 7.35, 2.1, 3.8, 0.35, size=24, color=ORANGE, bold=True)
bullets(slide, [
    "Precision, recall, and mAP",
    "Path-blocking accuracy",
    "Distance-estimation error",
    "False-alert and missed-hazard rate",
    "Latency and frames per second",
], 7.35, 2.85, 4.35, 2.45, size=17, gap=10)

# 12. Novelty
slide = header("Novelty and contribution", "What is different", 12)
contributions = [
    ("01", "Path-aware perception", "Moves beyond object labels by deciding whether the forward walking corridor is blocked."),
    ("02", "Known and unknown hazards", "Combines detector outputs with depth geometry to identify unlabelled blockers."),
    ("03", "Actionable distance", "Turns approximate monocular depth into distance, direction, and side guidance."),
    ("04", "Safety-first speech", "Uses persistence, time-to-collision, priority, and cooldowns to control announcements."),
]
for i, (num, title, body) in enumerate(contributions):
    y = 1.75 + i * 1.15
    shape(slide, 0.95, y, 0.6, 0.42, fill=TEAL if i % 2 == 0 else BLUE, line=TEAL if i % 2 == 0 else BLUE, rounded=True)
    text(slide, num, 0.95, y + 0.1, 0.6, 0.2, size=12, color=WHITE, bold=True, font="Aptos Mono", align=PP_ALIGN.CENTER)
    text(slide, title, 1.85, y - 0.01, 3.6, 0.3, size=20, color=NAVY, bold=True)
    text(slide, body, 5.65, y, 6.35, 0.42, size=17, color=GRAY)
    shape(slide, 1.85, y + 0.62, 10.15, 0.02, fill=LIGHT, line=LIGHT)

# 13. Limitations and safety
slide = header("Limitations and safety boundary", "Responsible use", 13)
shape(slide, 0.9, 1.75, 5.65, 4.75, fill=RGBColor(254, 245, 242), line=RGBColor(244, 211, 199), rounded=True)
text(slide, "Known limitations", 1.3, 2.1, 3.3, 0.35, size=24, color=RED, bold=True)
bullets(slide, [
    "Monocular depth is approximate, not guaranteed metric distance.",
    "Results depend on camera height, pitch, lighting, blur, reflections, crowds, and ground visibility.",
    "Speech behaviour depends on browser and operating-system audio support.",
], 1.3, 2.85, 4.7, 2.25, size=17, gap=12)
shape(slide, 6.95, 1.75, 5.45, 4.75, fill=PALE, line=RGBColor(180, 226, 221), rounded=True)
text(slide, "Safety boundary", 7.35, 2.1, 3.3, 0.35, size=24, color=TEAL, bold=True)
bullets(slide, [
    "Educational research prototype only.",
    "Not a certified mobility aid, medical device, or emergency system.",
    "Must not replace a white cane, guide dog, or human assistance.",
    "Testing requires supervision and conventional mobility safety methods.",
], 7.35, 2.85, 4.4, 2.25, size=17, gap=12)

# 14. Conclusion
slide = header("Conclusion", "Summary", 14)
text(slide, "SafeStride Assist demonstrates how perception can become guidance when placed in context.", 1.0, 1.85, 11.3, 0.6, size=28, color=NAVY, bold=True, align=PP_ALIGN.CENTER)
for i, (label, body, color) in enumerate([
    ("SEE", "detect and track", BLUE),
    ("MEASURE", "estimate depth and distance", TEAL),
    ("DECIDE", "evaluate path and urgency", ORANGE),
    ("SPEAK", "give concise guidance", RED),
]):
    x = 0.95 + i * 3.05
    shape(slide, x, 3.0, 2.45, 1.6, fill=PALE_BLUE if i % 2 == 0 else PALE, line=color, rounded=True)
    text(slide, label, x + 0.15, 3.38, 2.15, 0.3, size=20, color=color, bold=True, align=PP_ALIGN.CENTER)
    text(slide, body, x + 0.18, 4.0, 2.1, 0.3, size=14, color=GRAY, align=PP_ALIGN.CENTER)
    if i < 3:
        line(slide, x + 2.5, 3.8, x + 2.85, 3.8, color=NAVY, width=2, arrow=True)
text(slide, "The project provides a modular foundation for future evaluation, calibration, custom hazard models, and accessible navigation research.", 1.4, 5.65, 10.5, 0.5, size=18, color=GRAY, align=PP_ALIGN.CENTER)

# 15. References
slide = header("References", "Selected sources", 15)
refs = [
    "[1] Redmon et al., You Only Look Once, CVPR, 2016.",
    "[2] Zhang et al., ByteTrack, ECCV, 2022.",
    "[3] Yang et al., Depth Anything V2, NeurIPS, 2024.",
    "[4] Ranftl et al., Vision Transformers for Dense Prediction, ICCV, 2021.",
    "[5] Ultralytics, Ultralytics YOLO Documentation.",
    "[6] World Health Organization, World Report on Vision, 2019.",
    "[7] Khan et al., Navigation Assistants Systematic Review, IEEE Access, 2021.",
    "[8] Xu et al., Wearable Obstacle Avoidance Travel Aids, IEEE Access, 2023.",
    "[9] Katzschmann et al., Safe Local Navigation with ToF and Haptic Feedback, IEEE TNSRE, 2018.",
    "[10] Eltaher et al., Urban Navigation Systems Review, Sensors, 2021.",
    "[11] Johannesson et al., The Sound of Vision, Brain Sciences, 2016.",
    "[12] Shull and Damian, Haptic Wearables Review, JNER, 2015.",
    "[13] Ranganeni et al., Levels of Control for Blind Travelers, HRI, 2023.",
    "[14] Zhang et al., ARCore User-Centric Assistive Navigation, Applied Sciences, 2019.",
]
for i, ref in enumerate(refs):
    x = 0.95 + (i // 7) * 6.0
    y = 1.7 + (i % 7) * 0.63
    text(slide, ref, x, y, 5.55, 0.42, size=13, color=INK)
text(slide, "Full DOI links and formatted entries are retained in the written synopsis.", 1.0, 6.52, 11.3, 0.25, size=14, color=GRAY, align=PP_ALIGN.CENTER)

prs.save(OUT)
prs.save(ALT_OUT)
print(OUT)
