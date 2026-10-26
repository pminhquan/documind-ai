# DocuMind local benchmark (real CPU inference)

- Date: 2026-10-25 23:41
- Python: 3.12.10, OS: Windows-11-10.0.26200-SP0
- Input: sample_receipt.png (fixed synthetic receipt)
- Runs per measurement: 3 (median reported)

- OCR engine cold init: **3.66s** (model cached on disk)
- Warm OCR inference: **17.02s** (min 16.80s / max 17.03s)
- Invoice extraction (no inference): **9.1ms**
- Table geometry (no inference): **3.6ms** (no ruled table in the receipt input)
- Unified auto request (1 OCR call reused): **16.87s**

Engine initializations in this run: 1; OCR inference calls for unified: 1 (items reused across workflows).
