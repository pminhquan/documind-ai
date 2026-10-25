# Learning Notes — DocuMind M0/M1

Ghi chú học tập bằng tiếng Việt, tóm tắt các khái niệm nền tảng của
milestone này. Viết ngắn gọn để ôn tập nhanh.

---

## 1. Virtual environment (`.venv`) là gì?

Một **môi trường ảo Python** là một thư mục chứa bản sao riêng của
interpreter Python cùng các thư viện đã cài cho riêng dự án.

- **Vấn đề**: các dự án khác nhau cần các phiên bản thư viện khác nhau.
  Nếu cài thẳng vào Python toàn cục (global), dễ xảy ra xung đột phiên bản
  và khó tái lập lại môi trường.
- **Giải pháp**: `py -3.12 -m venv .venv` tạo thư mục `.venv` chứa
  Python 3.12 riêng. Khi kích hoạt, lệnh `python`/`pip` trỏ vào `.venv`
  thay vì Python toàn cục — mọi cài đặt chỉ ảnh hưởng bên trong dự án.
- Trong dự án này, máy có Python 3.14 toàn cục nhưng `.venv` dùng
  Python 3.12.10 x64; hai môi trường tồn tại độc lập, không can thiệp nhau.

## 2. Pipeline OCR hoạt động như thế nào?

OCR (Optical Character Recognition) — nhận dạng ký tự quang học — biến
ảnh chữ thành text máy đọc được. Pipeline của DocuMind (dùng
**PaddleOCR 3.x**, model **PP-OCRv5** trên CPU) gồm các bước:

1. **Validation** — kiểm tra file tồn tại, đúng định dạng ảnh, không rỗng,
   không quá lớn. Fail sớm → thông báo lỗi rõ ràng, tiết kiệm tính toán.
2. **Preprocessing** — decode ảnh bằng Pillow, chuẩn hoá về RGB
   (ảnh xám/palette/CMYK được chuyển đổi), tránh lỗi cho bước sau.
3. **Text detection** — mạng neural tìm ra *vị trí* các vùng có chữ
   trong ảnh (xuất ra đa giác 4 điểm cho mỗi dòng chữ).
4. **Text recognition** — với từng vùng chữ, mạng neural thứ hai
   *đọc* nội dung, trả về chuỗi ký tự và điểm tin cậy (confidence).
5. **Normalization** — gộp kết quả thô thành JSON có cấu trúc:
   `text`, `confidence`, `box` cho từng dòng.

Điểm quan trọng: detection và recognition là **hai model riêng biệt**
chạy nối tiếp (pipeline two-stage), không phải một mạng duy nhất.

## 3. Bounding box là gì?

**Bounding box** là hình chữ nhật (hoặc đa giác 4 điểm) **bao quanh một
đối tượng** trong ảnh — ở đây là một dòng chữ được phát hiện.

Trong kết quả của DocuMind, mỗi dòng có `box` gồm 4 điểm toạ độ pixel:

```json
"box": [[10, 5], [300, 5], [300, 40], [10, 40]]
```

- `[10, 5]` = điểm trái-trên (x=10, y=5); các điểm còn lại lần lượt là
  phải-trên, phải-dưới, trái-dưới.
- Vì sao cần box? Vì chỉ có text là chưa đủ: **vị trí** cho biết dòng nào
  ở trên/dưới (thứ tự đọc), dòng nào là "TOTAL" (thường phía dưới, bên
  phải), và là nền tảng để M2 trích xuất trường theo bố cục (layout).
- PaddleOCR trả đa giác 4 điểm (có thể xoay nghiêng) chứ không nhất
  thiết là hình chữ nhật thẳng — chữ trong ảnh chụp nghiêng vẫn được
  bao đúng.

## 4. Vì sao chọn Python 3.12?

- PaddlePaddle 3.x (backend của PaddleOCR) phát hành wheel cho
  **Python 3.9–3.13**; Python 3.14 (đang là mặc định của máy) **chưa
  được hỗ trợ** → dùng 3.14 sẽ không cài được paddlepaddle.
- Python 3.12 đủ mới (hiểu cú pháp hiện đại như `X | Y` type union)
  và đủ ổn định, mọi thư viện trong stack đều có wheel bản ổn định.
- Khoá phiên bản trong `pyproject.toml` bằng `requires-python = ">=3.12,<3.13"`
  để mọi người setup ra môi trường giống nhau → tái lập kết quả (reproducibility).

## 5. Core AI logic nằm ở file nào?

| File | Vai trò |
|---|---|
| `src/documind/ocr/engine.py` | **Chạy model**: khởi tạo PaddleOCR 3.x (PP-OCRv5 CPU), gọi `predict()`, bọc lỗi thành `OcrEngineError`. Đây là file "gần AI" nhất. |
| `src/documind/ocr/results.py` | **Chuẩn hoá kết quả** model → `TextBox` (text, confidence, box) và JSON. Xử lý output của AI nhưng không chạy AI. |
| `src/documind/ocr/preprocessing.py` | Chuẩn bị dữ liệu vào cho model (decode + RGB). |
| `src/documind/cli.py` | Giao diện dòng lệnh — **không chứa logic AI**, chỉ wiring. |

Nguyên tắc: logic AI tách khỏi CLI để có thể unit-test bằng **mock**
(không cần tải model thật) — xem `tests/test_cli.py`.

## 6. Ba bài tập tự luyện

1. **Vẽ bounding box lên ảnh**: viết script dùng Pillow đọc
   `outputs/sample_receipt.ocr.json`, vẽ các `box` (hình chữ nhật đỏ)
   lên ảnh gốc và lưu thành `annotated.png`. Gợi ý: `ImageDraw.rectangle`.
   *Mục tiêu*: hiểu toạ độ pixel và cấu trúc JSON output.

2. **Thêm trường `aspect_ratio` vào `TextBox`**: mở
   `src/documind/ocr/results.py`, tính tỉ lệ width/height của box khi
   normalize (dựa vào 2 điểm đối diện), viết thêm 1–2 unit test trong
   `tests/test_results.py`. *Mục tiêu*: thực hành dataclass + TDD nhỏ.

3. **Quan sát preprocessing bằng thực nghiệm**: tạo ảnh grayscale
   (mode `"L"`) và ảnh palette (mode `"P"`) bằng Pillow, chạy
   `documind-ocr` trên chúng, dùng logging/print để chứng minh ảnh đi
   qua nhánh chuyển đổi RGB trong `preprocessing.py`. *Mục tiêu*: hiểu
   context manager và vì sao output JSON vẫn đúng định dạng.
