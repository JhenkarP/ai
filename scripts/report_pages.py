"""Export the report to PDF with Microsoft Word and measure the page numbers of the contents tables.

    python scripts/report_pages.py [docx]

Writes docs/report_assets/page_numbers.json (read by docs/create_major_project_report.py) and a PDF next to the
document. Run the builder, then this script, then the builder again so the tables carry the measured pages.
"""

import json
import re
import sys
from pathlib import Path

import comtypes.client
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
sys.path.insert(0, str(DOCS))
import report_content as C  # noqa: E402


def export_pdf(docx: Path, pdf: Path) -> int:
    word = comtypes.client.CreateObject("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        doc = word.Documents.Open(str(docx.resolve()), ReadOnly=True, AddToRecentFiles=False)
        doc.ExportAsFixedFormat(str(pdf.resolve()), 17)
        pages = doc.ComputeStatistics(2)
        doc.Close(False)
    finally:
        word.Quit()
    return pages


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def measure(pdf: Path) -> dict:
    results = json.loads((DOCS / "paper_assets" / "results.json").read_text(encoding="utf-8"))
    blocks = C.build(results)
    doc = pymupdf.open(str(pdf))
    page_lines = [[norm(l) for l in page.get_text().splitlines() if norm(l)] for page in doc]
    start = next(i for i, lines in enumerate(page_lines)
                 if "Chapter 1" in lines and "INTRODUCTION" in lines)

    wanted = []  # (key, matcher)
    for b in blocks:
        kind = b[0]
        if kind == "chapter":
            n, title = b[1], b[2]
            wanted.append((f"ch{n}", lambda lines, n=n: f"Chapter {n}" in lines))
        elif kind == "h2":
            num, title = b[1], b[2]
            wanted.append((f"s{num}", lambda lines, num=num, title=title:
                           any(l.startswith(f"{num} {title[:24]}") for l in lines)))
        elif kind == "fig":
            m = re.match(r"(Fig \d+\.\d+):", b[2])
            if m:
                wanted.append((m.group(1), lambda lines, k=m.group(1): any(l.startswith(k + ":") for l in lines)))
        elif kind == "refs":
            wanted.append(("refs", lambda lines: "REFERENCES" in lines))

    pages, cursor, missing = {}, start, []
    for key, match in wanted:
        for i in range(cursor, len(page_lines)):
            if match(page_lines[i]):
                pages[key] = i - start + 1
                cursor = i
                break
        else:
            missing.append(key)
    pages["_front_pages"] = start
    pages["_total_pages"] = len(page_lines)
    return pages, missing


def main():
    docx = Path(sys.argv[1]) if len(sys.argv) > 1 else DOCS / "SafeStride_Assist_Major_Project_Report.docx"
    pdf = docx.with_suffix(".pdf")
    n = export_pdf(docx, pdf)
    pages, missing = measure(pdf)
    out = DOCS / "report_assets" / "page_numbers.json"
    out.write_text(json.dumps(pages, indent=1), encoding="utf-8")
    print(f"Word reports {n} pages; front matter {pages['_front_pages']} pages; chapters start at page index "
          f"{pages['_front_pages']}")
    print("missing:", missing or "none")
    print({k: v for k, v in pages.items() if k.startswith("ch") or k == "refs"})


if __name__ == "__main__":
    main()
