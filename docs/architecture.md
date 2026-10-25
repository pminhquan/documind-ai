# DocuMind AI — Architecture (M0/M1)

Trạng thái hiện tại: **baseline OCR tối giản, CPU-first**, chưa có API/DB/frontend.

## Sơ đồ module

```
documind-ai/
├── src/documind/
│   ├── cli.py              # entry point `documind-ocr` (argparse)
│   └── ocr/
│       ├── validation.py    # kiểm tra input: tồn tại, định dạng, kích thước
│       ├── preprocessing.py # decode ảnh bằng Pillow, chuẩn hoá về RGB
│       ├── engine.py        # wrapper PaddleOCR 3.x (model PP-OCRv5, CPU)
│       └── results.py       # chuẩn hoá kết quả thô → JSON có cấu trúc
├── scripts/
│   └── make_sample_receipt.py  # sinh ảnh hoá đơn mẫu (dữ liệu giả)
└── tests/                   # pytest: unit (mock) + smoke CLI
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

## Nguyên tắc thiết kế

- **Tách lớp**: CLI không chứa logic OCR; module `ocr/` không biết tới
  argparse/exit code. Nhờ đó unit test mock được engine mà không cần
  paddle nặng.
- **Lazy import**: `paddleocr` chỉ được import bên trong
  `PaddleOcrEngine.__init__`, giúp `import documind` và pytest chạy nhanh.
- **CPU-first**: tắt các bước classify/unwarp của PaddleOCR để baseline
  nhẹ; chưa có giả định GPU.

## Ranh giới phạm vi (M0/M1)

Chưa có: trích xuất trường hoá đơn, tái tạo bảng, database, API, frontend,
đánh giá accuracy (cần ground-truth có nhãn). Đây là nội dung của M2+.
