# DocuMind AI — Core Pipeline Architecture (M0–M2)

> **Scope note:** this document describes the original OCR/extraction core
> (M0–M2) and is kept for its design rationale. The current product also
> includes ruled tables (M3A), evaluation (M4A), dataset onboarding (M4B
> Phase 1), the local web app (M5A/M5B, including D-18), Vietnamese
> extraction rules (M5C), and performance benchmarking (M5D). For current
> status, architecture, and commands, see [HANDOFF.md](../HANDOFF.md).
> The API and frontend **exist**; a database does **not**.

## Sơ đồ module

```
documind-ai/
├── src/documind/
│   ├── cli.py              # entry point `documind-ocr` (argparse)
│   ├── extract_cli.py      # entry point `documind-extract` (M2)
│   ├── ocr/
│   │   ├── validation.py    # kiểm tra input: tồn tại, định dạng, kích thước
│   │   ├── preprocessing.py # decode ảnh bằng Pillow, chuẩn hoá về RGB
│   │   ├── engine.py        # wrapper PaddleOCR 3.x (PP-OCRv6, CPU)
│   │   └── results.py       # chuẩn hoá kết quả thô → JSON có cấu trúc
│   └── extraction/          # M2: OCR JSON → invoice JSON (deterministic)
│       ├── models.py         # Invoice/LineItem/Provenance (Decimal, dataclass)
│       ├── parsing.py        # normalize, parse_amount, parse_date (regex)
│       ├── layout.py         # gom dòng theo bounding box
│       ├── extractor.py      # pipeline trích xuất + rule tables
│       └── validator.py      # kiểm tra số học (subtotal/total/change)
├── scripts/
│   └── make_sample_receipt.py  # sinh ảnh hoá đơn mẫu (dữ liệu giả)
└── tests/                   # pytest: unit (mock) + smoke CLI + fixtures
```

## Luồng xử lý (data flow)

```
input path
   │
   ▼
validation.validate_image()      → ValidationError (exit code 2)
   │
   ▼
preprocessing.prepare_image()    → PreprocessingError (exit code 1)
   │  (context manager: tạo PNG tạm nếu ảnh không phải RGB)
   ▼
engine.PaddleOcrEngine.predict() → OcrEngineError (exit code 1)
   │  (det + rec: PP-OCRv6, ghim tường minh trong engine; lần đầu tự tải model)
   ▼
results.normalize_result()       → OcrResult(TextBox[text, confidence, box])
   │
   ▼
json.dumps → file output (mặc định: outputs/<tên-ảnh>.json)
```

### Luồng M2 (documind-extract, hoạt động trên OCR JSON đã lưu)

```
OCR JSON
   │
   ▼
extractor.load_ocr_document()    → OcrInputError (exit code 2)
   │
   ▼
layout.group_lines()             # gom dòng theo bounding box
   │
   ▼
extractor: supplier → number → date → currency → line_items → summary
   │  (regex + heuristic bố cục, chi tiết: docs/extraction-spec.md)
   ▼
validator.apply_validation()     # số học → validation_status
   │
   ▼
ExtractionResult.to_json() → outputs/<tên-ảnh>.invoice.json
```

Extraction **không import** module OCR engine và không chạy model —
hoàn toàn deterministic.

## Nguyên tắc thiết kế

- **Tách lớp**: CLI không chứa logic OCR; module `ocr/` không biết tới
  argparse/exit code. Nhờ đó unit test mock được engine mà không cần
  paddle nặng.
- **Lazy import**: `paddleocr` chỉ được import bên trong
  `PaddleOcrEngine.__init__`, giúp `import documind` và pytest chạy nhanh.
- **CPU-first**: tắt các bước classify/unwarp của PaddleOCR để baseline
  nhẹ; chưa có giả định GPU.

## Ranh giới phạm vi lịch sử (M0–M2)

Tại thời điểm tài liệu này được viết: đã có OCR baseline và trích xuất
hoá đơn deterministic (M2); chưa có tái tạo bảng (M3), evaluation (M4),
API hay frontend. Hiện tại M3A/M4A/M4B Phase 1/M5A/M5B (gồm D-18) đã
hoàn thành; M5C (quy tắc trích xuất tiếng Việt) và M5D (benchmark hiệu
năng) cũng đã xong. Database vẫn chưa có và real-document accuracy vẫn
đang chờ dữ liệu gán nhãn (M4B Phase 2).
