"""Reproducible local benchmark for the DocuMind pipelines.

Measures (real CPU inference, models pre-cached in ~/.paddlex):
- OCR engine cold initialization
- Warm OCR inference (3 runs) on a fixed synthetic receipt
- Invoice extraction + table geometry latency (no inference)

Usage: python scripts/benchmark.py [--runs N]
Writes a Markdown report to reports/ and prints it.
Never run in CI: it downloads/loads real models.
"""

import argparse
import platform
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

RECEIPT = REPO / "assets/samples/sample_receipt.png"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    import cv2

    from documind.tables.geometry import detect_table_grids
    from documind.web import service

    lines = [
        "# DocuMind local benchmark (real CPU inference)",
        "",
        f"- Date: {time.strftime('%Y-%m-%d %H:%M')}",
        f"- Python: {sys.version.split()[0]}, OS: {platform.platform()}",
        f"- Input: {RECEIPT.name} (fixed synthetic receipt)",
        f"- Runs per measurement: {args.runs} (median reported)",
        "",
    ]

    service.reset_engine()
    t0 = time.perf_counter()
    service._get_engine()
    cold = time.perf_counter() - t0
    lines.append(f"- OCR engine cold init: **{cold:.2f}s** (model cached on disk)")

    warm = []
    for _ in range(args.runs):
        t0 = time.perf_counter()
        service.ocr_document(RECEIPT)
        warm.append(time.perf_counter() - t0)
    lines.append(f"- Warm OCR inference: **{statistics.median(warm):.2f}s** "
                 f"(min {min(warm):.2f}s / max {max(warm):.2f}s)")

    ocr_result = service.ocr_document(RECEIPT)
    t0 = time.perf_counter()
    for _ in range(args.runs):
        service.extract_invoice(ocr_result)
    extract = (time.perf_counter() - t0) / args.runs
    lines.append(f"- Invoice extraction (no inference): **{extract * 1000:.1f}ms**")

    image = cv2.imread(str(RECEIPT))
    t0 = time.perf_counter()
    for _ in range(args.runs):
        detect_table_grids(image)
    geometry = (time.perf_counter() - t0) / args.runs
    lines.append(f"- Table geometry (no inference): **{geometry * 1000:.1f}ms** "
                 "(no ruled table in the receipt input)")

    t0 = time.perf_counter()
    service.process_unified(RECEIPT, ["ocr", "invoice", "table"])
    unified = time.perf_counter() - t0
    lines.append(f"- Unified auto request (1 OCR call reused): **{unified:.2f}s**")
    lines += [
        "",
        ("Engine initializations in this run: 1; OCR inference calls "
         "for unified: 1 (items reused across workflows)."),
        "",
    ]

    report = "\n".join(lines)
    print(report)
    out = REPO / "reports" / "benchmark-local.md"
    out.write_text(report, encoding="utf-8")
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
