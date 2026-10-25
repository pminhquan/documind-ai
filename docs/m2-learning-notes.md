# Learning Notes — M2: Trích xuất thông tin hoá đơn

Ghi chú học tập tiếng Việt cho milestone M2. Đối tượng: bạn — sinh viên
CNTT năm 3 đang học AI Engineering.

---

## 1. Regex (biểu thức chính quy) là gì?

Regex là **ngôn ngữ mô tả mẫu chuỗi** (pattern). Ví dụ trong M2:

| Mẫu | Ý nghĩa |
|---|---|
| `\d{1,3}(?:[.,]\d{3})*[.,]\d{2}` | Số tiền: 1–3 chữ số, rồi các nhóm 3 chữ số, kết thúc 2 chữ số thập phân (`1,234.56`, `9.57`) |
| `(\d+(?:[.,]\d+)?)\s*[xX×*]\s*(\d+(?:[.,]\d+)?)` | Cặp `số lượng x đơn giá` (`2 x 2.50`) |
| `(?i)\bcurrency\b\s*[:.]?\s*([A-Za-z]{3})\b` | Dòng `Currency: USD` — `(?i)` = không phân biệt hoa thường, `\b` = biên từ |

Ba điều cần nhớ:
1. **Greedy vs lazy** — `.*` ăn nhiều nhất có thể; trong trích xuất hãy
   giới hạn bằng class cụ thể (`[A-Za-z0-9]`, `\d`) thay vì `.*`.
2. **Capture group** `(...)` — phần được "bắt" ra để dùng;
   `(?:...)` là group không bắt.
3. Regex phù hợp cho **mẫu có quy tắc** (số tiền, ngày, mã số). Với văn
   bản tự do (tên cửa hàng), kết hợp regex + heuristic bố cục tốt hơn.

## 2. Information extraction (trích xuất thông tin) là gì?

Là biến văn bản thô thành **dữ liệu có cấu trúc** (schema có kiểu).
Pipeline M2:

```
OCR JSON (text + box)
  → chuẩn hoá text (NFKC)
  → gom dòng theo hình học (bounding box)
  → regex/heuristic cho từng trường (supplier, date, số tiền...)
  → validate số học
  → JSON có cấu trúc + provenance
```

Khác với classification (trả 1 nhãn), extraction phải xử lý **nhiều
trường, nhiều kiểu dữ liệu**, và quan trọng nhất: **biết khi nào không
có dữ liệu** — trả `null` thay vì bịa. Đó là lý do schema M2 cho phép
mọi trường optional và có `validation_status`.

## 3. OCR layout & bounding box dùng để làm gì trong M2?

M1 chỉ *đọc* text; M2 cần *hiểu bố cục*. Bounding box cho 3 việc:

1. **Gom dòng thật**: OCR trả từng vùng rời rạc (`"SOAP"`, `"2 x 2.50"`,
   `"5.00"` là 3 item riêng). Hai vùng cùng hàng khi **đè lên nhau theo
   chiều dọc ≥ 50% chiều cao của vùng thấp hơn** (`layout.py:_same_row`).
2. **Thứ tự đọc trong hàng**: sắp theo `x0` (trái → phải) → mô tả đứng
   trước số tiền.
3. **"Số tiền phải nhất"**: trên hàng `TAX 10% | 1.23`, số tiền là token
   phải nhất — ông `10%` là *thuế suất*, không phải số tiền.

Provenance (traceability) cũng nhờ box: mỗi trường trích xuất được ghi
kèm `ocr_index` + `box` để lần ngược về vùng chữ gốc — bắt buộc khi
debug "sao nó hiểu sai?".

## 4. Rule-based baseline vs trained models

| | Rule-based (M2) | Trained model (tương lai) |
|---|---|---|
| Cách làm | Regex + hình học, viết tay | Học từ dữ liệu có nhãn |
| Ưu điểm | Không cần dữ liệu train, giải thích được từng quyết định, chạy < 1 ms | Tổng quát với template lạ, tự xử lý nhiễu |
| Nhược điểm | Gãy với layout/nonce mới ngoài từ điển | Cần hàng trăm–nghìn hoá đơn có nhãn, khó debug |
| Khi nào dùng | Baseline, template cố định (hoá đơn của 1 đối tác) | Đa dạng template, phức tạp tăng |

Nguyên tắc ngành: **luôn xây rule baseline trước** để (a) có số liệu so sánh,
(b) hiểu dữ liệu, (c) có fallback tất-yển. Model chỉ đáng thêm khi baseline
đã đo được giới hạn. M2 cố tình không dùng LLM/API.

## 5. Vì sao dùng `Decimal` cho tiền?

`float` là nhị phân base-2 — không biểu diễn được 0.1 chính xác:

```python
>>> 0.1 + 0.2
0.30000000000000004
>>> Decimal("0.10") + Decimal("0.20")
Decimal('0.30')
```

Với validate `5.00 + 2.50 + 1.20 == 8.70`, float có thể sai lệch 1e-16
và phép so sánh `==` gãy. `Decimal` là base-10, giữ nguyên **scale**
(`Decimal("8.70")` nhớ mình có 2 chữ số thập phân) — dữ liệu in trên
hoá đơn là base-10 nên khớp tuyệt đối. Trong code: parse bằng
`Decimal(text)` (không bao giờ `Decimal(float)`), serialize bằng
`str(Decimal)` để giữ `"9.57"` trong JSON. Đây cũng là chuẩn trong hệ
thống tài chính (Python `decimal`, Java `BigDecimal`).

## 6. Cách xem lỗi extraction (debug workflow)

1. **Chạy CLI xem status**: `documind-extract outputs/sample_receipt.json -o out.json`
   — dòng `status=` và danh sách `validation_errors` in ra terminal.
2. **Đọc `validation_errors`**: tiền tố cho biết loại lỗi —
   `ambiguous:` = input mơ hồ (cần review), còn lại = sai số arithmetic
   (input OCR hoặc rule đọc sai).
3. **Truy provenance**: mở JSON output, tìm trường nghi vấn trong
   `"provenance"` → lấy `ocr_index` + `text` + `box` → so với OCR JSON gốc
   cùng index → xác định OCR đọc sai hay rule hiểu sai.
4. **Reproduce bằng fixture**: copy đoạn OCR JSON gây lỗi thành fixture
   nhỏ trong `tests/fixtures/ocr/`, viết test tái hiện, rồi sửa rule.
   Đó chính là workflow TDD dùng trong M2.

## 7. Ba bài tập tự luyện (không cần AI agent)

1. **Thêm từ điển tiếng Việt**: mở
   `src/documind/extraction/extractor.py`, thêm pattern cho
   `TỔNG CỘNG` (total), `TIỀN HÀNG` (subtotal), `THUẾ` (tax) vào
   `SUMMARY_FIELDS`. Viết 1 fixture mới + test trước khi sửa code.
   *Mục tiêu*: hiểu cách mở rộng lexicon theo TDD.

2. **Validator mới — "total bằng tổng line items khi không có subtotal"**:
   khi `subtotal` là `null` nhưng có line items và `total`, kiểm tra
   `sum(line_totals) == total`. Viết test case (đủ/null/khớp/lệch)
   trong `tests/test_extraction.py` trước, rồi sửa
   `src/documind/extraction/validator.py`. *Mục tiêu*: tư duy
   validate theo điều kiện có dữ liệu.

3. **Đo "độ đầy" của extraction**: viết script nhỏ đếm tỉ lệ trường
   non-null trong invoice JSON output (`python -c` hoặc file trong
   `scripts/`). Chạy trên 2–3 fixture và giải thích vì sao fixture
   `missing_fields.json` "đầy" thấp nhưng vẫn `status=ok`.
   *Mục tiêu*: phân biệt "thiếu dữ liệu" với "dữ liệu sai" — hai khái
   niệm khác nhau trong đánh giá extraction.
