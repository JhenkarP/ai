from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).parents[1]
DOCS = ROOT / "docs"
OUT = DOCS / "SafeStride_Assist_Research_Paper.docx"
FIGURE = DOCS / "safestride_architecture_figure.png"

FONT = "Times New Roman"
NAVY = (24, 55, 82)
TEAL = (37, 135, 137)
GRAY = (90, 100, 108)
LIGHT = (235, 243, 246)
WHITE = (255, 255, 255)


def set_cell_shading(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_border(cell, color="D5DDE1", size="4"):
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = "w:" + edge
        element = borders.find(qn(tag))
        if element is None:
            element = OxmlElement(tag)
            borders.append(element)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), size)
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), color)


def set_run(run, size=9, bold=False, italic=False, color=(0, 0, 0), font=FONT):
    run.font.name = font
    run._element.rPr.rFonts.set(qn("w:eastAsia"), font)
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = RGBColor(*color)


def set_paragraph(paragraph, size=9, align=None, before=0, after=2, line=1.0):
    if align is not None:
        paragraph.alignment = align
    fmt = paragraph.paragraph_format
    fmt.space_before = Pt(before)
    fmt.space_after = Pt(after)
    fmt.line_spacing = line
    for run in paragraph.runs:
        set_run(run, size=size)


def add_text(doc, value, size=9, bold=False, italic=False, align=None, before=0, after=2, line=1.0, color=(0, 0, 0)):
    p = doc.add_paragraph()
    if align is not None:
        p.alignment = align
    run = p.add_run(value)
    set_run(run, size=size, bold=bold, italic=italic, color=color)
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.line_spacing = line
    return p


def add_rich_paragraph(doc, parts, size=9, after=2, first_line=0.16):
    p = doc.add_paragraph()
    p.paragraph_format.first_line_indent = Inches(first_line)
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.line_spacing = 1.0
    for value, bold, italic in parts:
        run = p.add_run(value)
        set_run(run, size=size, bold=bold, italic=italic)
    return p


def heading(doc, label, title):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_with_next = True
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    r = p.add_run(label + " ")
    set_run(r, size=10, bold=True, color=NAVY)
    r = p.add_run(title.upper())
    set_run(r, size=10, bold=True, color=NAVY)
    return p


def caption(doc, value):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(4)
    r = p.add_run(value)
    set_run(r, size=8, italic=True, color=GRAY)
    return p


def add_formula(doc, value):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run(value)
    set_run(r, size=9, italic=True, font="Cambria Math")
    return p


def configure_columns(section):
    sect_pr = section._sectPr
    cols = sect_pr.find(qn("w:cols"))
    if cols is None:
        cols = OxmlElement("w:cols")
        sect_pr.append(cols)
    cols.set(qn("w:num"), "2")
    cols.set(qn("w:space"), "360")


def add_page_number(section):
    footer = section.footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    set_run(run, size=8, color=GRAY)
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(end)


def make_architecture_figure():
    width, height = 1500, 500
    image = Image.new("RGB", (width, height), WHITE)
    draw = ImageDraw.Draw(image)
    try:
        font_head = ImageFont.truetype("arial.ttf", 28)
        font_body = ImageFont.truetype("arial.ttf", 21)
        font_small = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        font_head = font_body = font_small = ImageFont.load_default()
    nodes = [
        ("INPUT", "camera / video", NAVY),
        ("PERCEPTION", "YOLO + ByteTrack\nDepth Anything V2", TEAL),
        ("REASONING", "ground plane\n3 m corridor", (220, 135, 57)),
        ("DECISION", "risk + priority\nTTC + cooldown", (190, 67, 67)),
        ("OUTPUT", "browser + voice\ncaptions", NAVY),
    ]
    box_w, box_h, gap = 245, 180, 55
    start_x = 35
    y = 150
    for i, (head, body, color) in enumerate(nodes):
        x = start_x + i * (box_w + gap)
        draw.rounded_rectangle((x, y, x + box_w, y + box_h), radius=20, fill=(247, 250, 251), outline=color, width=5)
        draw.rectangle((x, y, x + 12, y + box_h), fill=color)
        draw.text((x + 25, y + 28), head, fill=NAVY, font=font_head)
        draw.multiline_text((x + 25, y + 82), body, fill=GRAY, font=font_body, spacing=8)
        if i < len(nodes) - 1:
            x1 = x + box_w + 8
            x2 = x + box_w + gap - 8
            ym = y + box_h // 2
            draw.line((x1, ym, x2, ym), fill=NAVY, width=5)
            draw.polygon(((x2, ym), (x2 - 15, ym - 10), (x2 - 15, ym + 10)), fill=NAVY)
    draw.text((35, 40), "SafeStride Assist: local perception-to-guidance pipeline", fill=NAVY, font=font_head)
    draw.text((35, 415), "Safety priority: urgent camera obstruction > path correction > background navigation/status", fill=GRAY, font=font_small)
    image.save(FIGURE, dpi=(220, 220))


def build_document():
    make_architecture_figure()
    doc = Document()
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(0.7)
    section.bottom_margin = Inches(0.65)
    section.left_margin = Inches(0.7)
    section.right_margin = Inches(0.7)
    configure_columns(section)
    add_page_number(section)

    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = FONT
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    normal.font.size = Pt(9)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_after = Pt(6)
    r = title.add_run("SafeStride Assist: A Local AI-Based Safe Walking Assistant Using Monocular Depth Estimation")
    set_run(r, size=20, bold=True, color=NAVY)

    authors = doc.add_paragraph()
    authors.alignment = WD_ALIGN_PARAGRAPH.CENTER
    authors.paragraph_format.space_after = Pt(2)
    r = authors.add_run("Jhenkar P, Department of Computer Science and Engineering")
    set_run(r, size=10, bold=True)
    aff = doc.add_paragraph()
    aff.alignment = WD_ALIGN_PARAGRAPH.CENTER
    aff.paragraph_format.space_after = Pt(8)
    r = aff.add_run("The National Institute of Engineering, Mysuru, India")
    set_run(r, size=9, italic=True, color=GRAY)

    abstract = doc.add_paragraph()
    abstract.paragraph_format.space_after = Pt(3)
    abstract.paragraph_format.line_spacing = 1.0
    r = abstract.add_run("Abstract—")
    set_run(r, size=9, bold=True)
    r = abstract.add_run("SafeStride Assist is a research and teaching prototype that combines real-time object detection, temporal tracking, monocular depth estimation, ground-plane reasoning, and speech feedback to support safer walking assistance. The system processes camera or video frames locally using an Ultralytics YOLO model, ByteTrack, and Depth Anything V2. A spatial reasoning layer projects depth into approximate three-dimensional points, estimates a ground plane, and evaluates a one-metre-wide forward corridor extending up to three metres. Named detections and unknown depth-based blockers are assigned approximate distance, direction, path membership, and risk. An alert layer uses persistence, approach speed, time-to-collision, priority, and cooldown rules to produce concise guidance such as “Stop. Path blocked, 2 meters. Keep left.” The prototype exposes its state through a browser console with captions, diagnostics, and speech controls. SafeStride Assist is intended for educational research and must not be treated as a certified mobility aid, medical device, or emergency system.")
    set_run(r, size=9)

    terms = doc.add_paragraph()
    terms.paragraph_format.space_after = Pt(7)
    r = terms.add_run("Index Terms—")
    set_run(r, size=9, bold=True)
    r = terms.add_run("assistive technology, computer vision, YOLO, ByteTrack, monocular depth estimation, ground-plane estimation, spatial reasoning, obstacle detection, voice guidance.")
    set_run(r, size=9, italic=True)

    heading(doc, "I.", "Introduction")
    add_rich_paragraph(doc, [("People with visual impairment often combine traditional mobility aids, environmental knowledge, and human assistance when navigating unfamiliar environments. A camera-based assistant cannot replace these methods, but it can provide an additional perception channel by describing nearby blockers, estimating approximate distance, and presenting timely feedback. The practical challenge is not simply to identify objects. The system must determine which visual evidence is relevant to the user's forward path and decide when a short spoken message is useful.", False, False)])
    add_rich_paragraph(doc, [("SafeStride Assist addresses this challenge as a local processing pipeline. A camera supplies frames, machine-learning models identify visual content, a depth model estimates scene structure, and a deterministic reasoning layer converts observations into prioritised guidance. Keeping the core loop local reduces dependence on remote services and makes the prototype easier to inspect during research and teaching.", False, False)])
    add_rich_paragraph(doc, [("The main contribution is a distance-aware walking-corridor method. It combines named object detections with depth points that rise above an estimated ground plane, allowing the system to reason about unknown blockers as well as known classes. The output is deliberately action-oriented: the assistant should remain quiet when the path is clear and speak when the evidence supports an immediate decision.", False, False)])

    heading(doc, "II.", "Related Work")
    add_rich_paragraph(doc, [("Redmon et al. introduced YOLO as a one-stage detector capable of high-speed visual inference [1]. SafeStride uses a current Ultralytics YOLO checkpoint and filters detections to walking-relevant classes. ByteTrack associates high- and low-confidence detections across frames, improving temporal identity and supporting persistence analysis [2].", False, False)])
    add_rich_paragraph(doc, [("Depth Anything V2 provides dense monocular depth estimation from a single image [3]. Monocular depth captures scene structure but does not automatically provide guaranteed metric distance. Dense prediction research similarly demonstrates the value of depth for scene understanding while motivating explicit calibration and uncertainty boundaries [4].", False, False)])
    add_rich_paragraph(doc, [("Assistive-navigation reviews identify recurring challenges involving distance awareness, route guidance, obstacle avoidance, sensing conditions, and user workload [7], [8], [10]. Work on time-of-flight and haptic feedback demonstrates the value of local navigation cues [9], while Sound of Vision and haptic-wearable research motivate multimodal feedback design [11], [12]. User-control studies further emphasise that assistance should preserve user agency rather than silently replace user decisions [13].", False, False)])
    add_rich_paragraph(doc, [("SafeStride builds on these directions by combining real-time detection, tracking, monocular depth, path-aware geometry, risk ranking, and speech in a single educational prototype.", False, False)])

    heading(doc, "III.", "System Overview")
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(1)
    p.add_run().add_picture(str(FIGURE), width=Inches(6.75))
    caption(doc, "Fig. 1. SafeStride Assist local perception-to-guidance architecture.")
    add_rich_paragraph(doc, [("The input layer accepts an IP webcam, USB webcam, uploaded video, or recorded test clip. The perception layer performs YOLO detection, ByteTrack association, and Depth Anything V2 inference. The spatial reasoning layer estimates the ground plane, corrects the depth scale, projects points into approximate 3D coordinates, and evaluates the forward corridor. The decision layer combines path membership, distance, temporal persistence, and approach risk. Finally, the interaction layer presents the annotated feed, captions, diagnostics, and speech output in a browser console.", False, False)])
    add_rich_paragraph(doc, [("The architecture separates learned perception from deterministic safety reasoning. This separation makes the system easier to test: detector quality can be measured independently from corridor decisions and alert selection.", False, False)])

    heading(doc, "IV.", "Methodology")
    add_rich_paragraph(doc, [("A. Perception and Tracking—", True, False), ("For each input frame, YOLO returns candidate bounding boxes, class labels, and confidence values. ByteTrack associates detections with existing tracks, allowing the system to observe persistence and distance changes rather than reacting to one frame only.", False, False)])
    add_rich_paragraph(doc, [("B. Depth and 3D Projection—", True, False), ("Depth Anything V2 supplies a relative depth field D(u,v). For each sampled pixel, the implementation uses the intrinsic matrix K and homogeneous image coordinate q = [u, v, 1]ᵀ to obtain a camera-frame point:", False, False)])
    add_formula(doc, "P(u,v) = Z(u,v) K⁻¹q,     K = [[fₓ, 0, cₓ], [0, fᵧ, cᵧ], [0, 0, 1]]")
    add_rich_paragraph(doc, [("Equivalently, for the implementation's square-focal-length approximation, X = (u − W/2)Z/f and Y = (v − H/2)Z/f. This projection does not create metric truth by itself; it creates a spatial coordinate system whose scale is corrected by the ground estimator.", False, False)])
    add_rich_paragraph(doc, [("C. Robust Ground-Plane and Scale Estimation—", True, False), ("Let S be the lower-image point set used as a ground candidate. RANSAC selects the plane π̂ that maximises geometric consensus:", False, False)])
    add_formula(doc, "π̂ = arg maxπ  Σp∈S  𝟙(|nᵀp + d| < τ),     π : nᵀp + d = 0,     ||n||₂ = 1")
    add_rich_paragraph(doc, [("The inlier tolerance is distance-adaptive, τ = 0.03 median({Zp : p ∈ S}), and candidate planes are rejected when their normal is not sufficiently aligned with the vertical ground direction. If nᵧ is the vertical component of the accepted normal and Hc is the assumed camera height, each frame produces:", False, False)])
    add_formula(doc, "sₜ = Hc / (−nᵧ,ₜ),     ŝₜ = median{sⱼ : j ∈ [t − k, t]}")
    add_rich_paragraph(doc, [("The rolling median ŝₜ suppresses unstable frame-level estimates. Metric coordinates are then approximated by P̄ₜ = ŝₜPₜ, and height above the fitted ground is computed as:", False, False)])
    add_formula(doc, "hₜ(P) = −ŝₜ(nᵀP + d)")
    add_rich_paragraph(doc, [("D. Set-Based Walking-Corridor Analysis—", True, False), ("The forward corridor is defined as a subset of the corrected 3D space:", False, False)])
    add_formula(doc, "C = {P : |X| < 0.5,  0 < Z < 3.0,  0.25 < h(P) < 2.0}")
    add_rich_paragraph(doc, [("The binary obstacle mask is M(P) = 𝟙(P ∈ C). A path obstruction is declared only when the number of supporting samples exceeds the noise-rejection threshold:", False, False)])
    add_formula(doc, "blocked = 𝟙(ΣP  M(P) ≥ Nmin),     Dpath = Q₀.₀₅({Z(P) : M(P)=1})")
    add_rich_paragraph(doc, [("Here Q₀.₀₅ is the fifth percentile, which provides a robust near-face distance without selecting a single noisy minimum. The guidance side is inferred from the lateral distribution of the nearest front-face samples.", False, False)])
    add_rich_paragraph(doc, [("E. Temporal Motion and Time-to-Collision—", True, False), ("For a path obstacle, distance history is fitted by least squares over a one-second window. With Dᵢ observed at time tᵢ, the closing-rate estimate is:", False, False)])
    add_formula(doc, "β̂ = Σᵢ(tᵢ−t̄)(Dᵢ−D̄) / Σᵢ(tᵢ−t̄)²,     vapproach = −β̂")
    add_formula(doc, "TTCpath = Dpath / vapproach,     vapproach > 0")
    add_rich_paragraph(doc, [("For tracked bounding boxes, the implementation also uses a scale-invariant looming cue. If bₜ is the box height, the time-to-contact estimate is:", False, False)])
    add_formula(doc, "TTCloom = [d ln(bₜ)/dt]⁻¹")
    add_rich_paragraph(doc, [("F. Bounded Alert Utility—", True, False), ("The alert layer converts proximity and approach into a bounded urgency rather than using an unscaled distance threshold. For an in-path object:", False, False)])
    add_formula(doc, "u = w · max(clip₀¹(1 − D/Rp), clip₀¹(1 − TTC/Rt))")
    add_rich_paragraph(doc, [("where clip₀¹(x)=min(1,max(0,x))), w is the class or hazard weight, Rp is the proximity range, and Rt is the TTC range. Off-path approach risk is attenuated, persistence must exceed a minimum duration, and an alert is repeated only when the cooldown or meaningful-distance-change condition is satisfied. This formulation reflects the implemented decision policy rather than claiming that a learned model alone determines safety.", False, False)])

    heading(doc, "V.", "Implementation")
    add_rich_paragraph(doc, [("The prototype is implemented in Python 3.10+ using PyTorch, OpenCV, NumPy, Ultralytics YOLO, ByteTrack, and Depth Anything V2. The browser console displays the annotated video stream, object count, inference rate, depth state, corridor status, current alert, and spoken caption. Browser speech synthesis and local Windows audio provide feedback. The implementation separates detector, depth, spatial, risk, announcer, navigation, speech, and visualisation modules.", False, False)])
    add_rich_paragraph(doc, [("A frame is processed by detection and optional hazard models, followed by depth estimation at the configured interval. Each detection may receive an approximate distance. The spatial analyser returns a path status, distance, clock direction, and guidance side. Motion tracking updates temporal state, after which active alerts are ranked. The highest-priority message is sent to the speech layer subject to persistence and cooldown rules.", False, False)])

    heading(doc, "VI.", "Experimental Evaluation")
    add_rich_paragraph(doc, [("The current project documentation defines an evaluation protocol rather than claiming completed benchmark values. Evaluation should be performed on controlled and real-world clips containing people, vehicles, poles, doors, crowds, low-light scenes, and unknown temporary blockers. Ground-truth annotations should identify object class, bounding region, corridor membership, approximate distance, and whether an alert was warranted.", False, False)])
    add_rich_paragraph(doc, [("The proposed measures are detection precision, recall, and mAP; path-blocking accuracy; distance-estimation error; false-alert rate; missed-hazard rate; alert latency; and frames per second. A useful ablation compares detector-only alerts against detector-plus-depth corridor reasoning and then against the full temporal risk and cooldown layer.", False, False)])
    table = doc.add_table(rows=1, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    table.columns[0].width = Inches(1.7)
    table.columns[1].width = Inches(4.7)
    for cell, value in zip(table.rows[0].cells, ["Measure", "Purpose"]):
        set_cell_shading(cell, "183752")
        set_cell_border(cell, "183752")
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(value)
        set_run(r, size=8, bold=True, color=(255, 255, 255))
    rows = [
        ("Detection", "Precision, recall, mAP50"),
        ("Spatial", "Distance error and corridor classification"),
        ("Safety", "False alerts and missed hazards"),
        ("Runtime", "Latency and frames per second"),
    ]
    for left, right in rows:
        cells = table.add_row().cells
        for cell, value in zip(cells, [left, right]):
            set_cell_border(cell)
            p = cell.paragraphs[0]
            r = p.add_run(value)
            set_run(r, size=8)
    caption(doc, "TABLE I. PROPOSED EVALUATION MEASURES")

    heading(doc, "VII.", "Results and Discussion")
    add_rich_paragraph(doc, [("The implemented prototype demonstrates the complete perception-to-guidance path: live or recorded input, object detection, temporal tracking, monocular depth, ground-plane correction, forward-corridor analysis, prioritised alert selection, and browser speech output. Its main practical advantage is that it links visual evidence to path relevance. A detected object outside the corridor is less urgent than an unknown structure that rises from the ground directly ahead.", False, False)])
    add_rich_paragraph(doc, [("The results should be interpreted as prototype behaviour rather than clinical or safety certification. Monocular depth can change with camera pitch, camera height, lighting, reflections, motion blur, crowds, and weak ground visibility. Consequently, the system reports approximate distance and keeps an explicit safety boundary in both the user interface and project documentation.", False, False)])

    heading(doc, "VIII.", "Limitations")
    add_rich_paragraph(doc, [("The system depends on a visible ground region and a reasonably stable camera viewpoint. Relative depth is not guaranteed metric depth. Detection quality depends on model coverage, image quality, and scene conditions. Speech output depends on browser and operating-system audio support. Unknown blockers can be missed when their geometry is ambiguous or the ground-plane estimate is unstable. The prototype must not replace a white cane, guide dog, human assistance, certified mobility aid, medical device, or emergency system.", False, False)])

    heading(doc, "IX.", "Future Work")
    add_rich_paragraph(doc, [("Future work includes collecting project-specific camera data, benchmarking distance and path accuracy, adding calibration assistance, testing low-light and crowded scenes, evaluating multilingual speech, and packaging the console for mobile hardware. Door-state and stair-direction models may be added as secondary extensions after their datasets, labels, and safety behaviour are validated on the project's camera viewpoint.", False, False)])

    heading(doc, "X.", "Conclusion")
    add_rich_paragraph(doc, [("SafeStride Assist presents a local, modular architecture for combining real-time vision, monocular depth, ground-plane estimation, spatial corridor reasoning, temporal risk analysis, and speech feedback. Its central contribution is the translation of approximate visual depth into a path-aware and prioritised guidance message. The project demonstrates a credible research foundation for assistive-navigation experimentation while maintaining a clear distinction between an educational prototype and a certified safety device.", False, False)])

    heading(doc, "References", "")
    references = [
        "[1] J. Redmon, S. Divvala, R. Girshick, and A. Farhadi, \"You Only Look Once: Unified, Real-Time Object Detection,\" in Proc. CVPR, 2016.",
        "[2] Y. Zhang et al., \"ByteTrack: Multi-Object Tracking by Associating Every Detection Box,\" in Proc. ECCV, 2022.",
        "[3] L. Yang et al., \"Depth Anything V2,\" in Proc. NeurIPS, 2024, arXiv:2406.09414.",
        "[4] R. Ranftl, A. Bochkovskiy, and D. Cremers, \"Vision Transformers for Dense Prediction,\" in Proc. ICCV, 2021.",
        "[5] Ultralytics, \"Ultralytics YOLO Documentation,\" online documentation.",
        "[6] World Health Organization, World Report on Vision, Geneva, Switzerland, 2019.",
        "[7] M. Khan, A. Nazir, and M. Khan, \"Navigation Assistants for People with Visual Impairment: A Systematic Review,\" IEEE Access, 2021, doi: 10.1109/ACCESS.2021.3052415.",
        "[8] X. Xu et al., \"Wearable Obstacle Avoidance Electronic Travel Aids: A Systematic Review,\" IEEE Access, 2023, doi: 10.1109/ACCESS.2023.3285396.",
        "[9] T. J. Katzschmann, B. Araki, and D. Rus, \"Safe Local Navigation with Time-of-Flight and Haptic Feedback,\" IEEE TNSRE, 2018, doi: 10.1109/TNSRE.2018.2800665.",
        "[10] A. Eltaher et al., \"Urban Navigation Systems for People with Visual Impairment: A Review,\" Sensors, 2021, doi: 10.3390/s21093103.",
        "[11] J. Johannesson et al., \"The Sound of Vision Project,\" Brain Sciences, 2016, doi: 10.3390/brainsci6030020.",
        "[12] M. M. Shull and M. Damian, \"Haptic Wearables as Sensory Substitution and Augmentation Devices: A Review,\" JNER, 2015, doi: 10.1186/s12984-015-0055-z.",
        "[13] S. Ranganeni et al., \"Levels of Control for Blind Travelers Using Navigation Assistance,\" in Proc. ACM/IEEE HRI, 2023, doi: 10.1145/3568162.3578630.",
        "[14] Z. Zhang et al., \"User-Centric Assistive Navigation Using ARCore,\" Applied Sciences, 2019, doi: 10.3390/app9050989.",
    ]
    for ref in references:
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Inches(0.22)
        p.paragraph_format.first_line_indent = Inches(-0.22)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = 1.0
        r = p.add_run(ref)
        set_run(r, size=8)

    doc.save(OUT)
    print(OUT)


if __name__ == "__main__":
    build_document()
