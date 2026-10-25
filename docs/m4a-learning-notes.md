# Learning Notes — M4A: Khung đánh giá AI

Ghi chú học tập tiếng Việt cho milestone M4A.

---

## 1. Ground truth (sự thật nền) là gì?

Là **nhãn chuẩn** do con người tạo ra để so sánh với output của hệ
thống. Không có ground truth thì không đo được accuracy — chỉ "nhìn có
vẻ ổn". Trong DocuMind, mỗi task có dạng GT riêng:

| Task | GT | So sánh với |
|---|---|---|
| OCR | `reference_text` (toàn văn chuẩn) | `full_text` của OCR JSON |
| Invoice | `invoice` object (schema trùng extraction) | output `documind-extract` |
| Table | ma trận `rows x columns` các cell | output `documind-table` |

Nguyên tắc đánh giá: **prediction phải lưu sẵn** trước khi eval (eval
không chạy model) → kết quả tái lập được 100%, không phụ thuộc model
version hay nhiễu inference.

## 2. CER vs WER — đo lỗi ở cấp nào?

Cả hai dùng **khoảng cách Levenshtein** (số phép insert/delete/substitute
ít nhất để biến chuỗi A thành chuỗi B):

- **CER** (Character Error Rate) = edits / số ký tự GT. Đo lỗi **chữ cái**
  (`9.57` → `9.S7` là 1 edit).
- **WER** (Word Error Rate) = edits / số từ GT. Đo lỗi **cả từ**
  (`Total` → `T0tal` vẫn là 1 edit / 1 từ).

Vì sao cả hai? CER nhạy với lỗi nhỏ nhưng bị "pha loãng" bởi từ đúng dài;
WER phản ánh trải nghiệm đọc nhưng ít hạt hơn. Số liệu thật của dự án
minh họa rõ: trên hoá đơn mẫu, **CER = 0.242 nhưng WER = 0.046** — hầu
hết edit là **khoảng trắng cột bị OCR gộp/split khác cách in** (mỗi khoảng
trắng sai = 1 ký tự edit nhưng 0 word edit, vì whitespace được collapse
trước khi đếm từ). Bài học: luôn báo cả hai và giải thích *vì sao* chênh.

Công thức chuẩn: `rate = edits / len(reference)`. **GT rỗng** là case đặc
biệt — project quy ước tường minh: GT rỗng + prediction rỗng → 0.0; GT
rỗng + prediction có nội dung → 1.0 (sai hoàn toàn, không phải "vô hạn"
hay crash).

## 3. Precision, Recall, F1 — khi nào dùng?

Với tác vụ **trích xuất** (field extraction), mỗi field là một dự đoán
đúng/sai:

- **Precision** = dự đoán đúng / tổng dự đoán → "bao nhiêu % dự đoán là
  tin được" (phát hiện bịa: `extra`/hallucination làm precision giảm).
- **Recall** = dự đoán đúng / tổng field có trong GT → "bao nhiêu % field
  đã lấy được" (thiếu: `missing` làm recall giảm).
- **F1** = trung bình điều hoà 2/P + 1/R.

M4A hiện báo field accuracy (matched / applicable) + missing/extra/incorrect
riêng biệt — tương đương việc theo dõi precision/recall nhưng tách rõ
nguyên nhân. Khi nào **không** dùng precision/recall? Với CER/WER
(measurement task) — đây là metric khoảng cách, không phải classification.

## 4. Field-level accuracy — bẫy của null

Quy tắc M4A (tường minh, không ngầm định):

| GT | Prediction | Phân loại | Đếm vào accuracy? |
|---|---|---|---|
| giá trị | giá trị đúng | `matched` | ✓ |
| giá trị | giá trị sai | `incorrect` | ✓ |
| giá trị | `null` | `missing` | ✓ (**không bao giờ tính là đúng**) |
| `null` | giá trị | `extra` (bịa) | ✓ |
| `null` | `null` | `true_negative` | ✗ (loại khỏi mẫu số) |

Bẫy kinh điển: nếu cứ "cả hai null = đúng" và giữ trong mẫu số, một
dataset nhiều field trống sẽ cho accuracy 95% dù hệ thống **không trích
được gì**. `true_negative` luôn bị loại — nhưng `missing` thì không.

## 5. Dataset leakage (rò rỉ dữ liệu) là gì?

Là khi dữ liệu ở tập train xuất hiện (trực tiếp hoặc gần-duplicate) ở
tập test → metric test đẹp ảo. Ví dụ trong domain này: cùng một template
hoá đơn chia ở cả train lẫn test — model "nhớ bố cục" thay vì học.

Quy tắc phòng tránh (đã ghi trong annotation guide):
- **Split theo document**, không theo page/cell.
- **Stratify theo template/source** để mỗi split có đủ loại bố cục.
- Freeze split (`split.json` committed) **trước** khi tuning.
- Synthetic và real data **không trộn** trong cùng split.

## 6. Train / dev / test — vai trò từng tập?

- **Train**: huấn luyện / phát triển rule.
- **Dev (validation)**: dùng thoải mái khi iterate — chọn threshold,
  sửa regex. Được "chạm" nhiều lần.
- **Test**: chạm **một lần mỗi milestone**, báo số final. Chạm nhiều =
  test biến thành dev, metric mất ý nghĩa.

Với rule-based system (như DocuMind M2/M3A), train/dev/test vẫn có ý
nghĩa: rule "train" trên dev để tránh overfit regex vào vài mẫu cụ thể,
test giữ lại để đo tổng quát.

## 7. Error analysis — nhìn số, tìm nguyên nhân

Quy trình 4 bước (đã dùng để giải thích CER 0.242):
1. Xem **aggregate** → có vấn đề không? (CER cao bất thường)
2. Xem **per-document** → vấn đề tập trung ở đâu?
3. Xem **error examples** (ops insert/delete/substitute) → nhận ra
   phần lớn là "insert space" → nguyên nhân: khoảng trắng cột.
4. Quyết định: lỗi thật hay artifact của normalization? → ở đây là
   artifact của column alignment; WER mới phản ánh chất lượng thực.

Đây là kỹ năng quan trọng hơn cả việc tính metric: **số không giải thích
thì không có giá trị**.

## 8. Vì sao synthetic accuracy ≠ real-world performance?

- Synthetic input **sạch theo cấu trúc**: font đẹp, lưới kẻ đủ, không
  nghiêng, không noise → mọi bước (threshold, morphology, OCR) đều ở
  điều kiện lý tưởng.
- Real input mang: scan nghiêng, nếp gấp, ánh sáng không đều, font lạ,
  đường kẻ đứt, chữ in đè — từng thứ một là đủ làm gãy rule.
- Vì thế báo cáo phải ghi rõ **điều kiện đo** và không bao giờ dùng chữ
  "accuracy" trơn cho synthetic. M4A ghi `reports/`: "synthetic baseline,
  not real-world accuracy"; real-data evaluation đang **pending** vì
  chưa có dữ liệu thật có license.

## 9. Ba bài tập tự luyện (không cần AI agent)

1. **Tính tay CER/WER**: với GT `TOTAL 13.53` và prediction `T0TAL 13,53`,
   liệt kê từng edit operation (dùng `edit_operations` trong Python để
   kiểm tra), tự tính CER và WER trước, chạy code sau để đối chiếu.
   *Mục tiêu*: hiểu cơ chế Levenshtein, không chỉ gọi hàm.

2. **Thêm precision/recall cho invoice fields**: từ `summary` của
   `invoice_eval` (matched/missing/extra/incorrect), tính precision =
   matched/(matched+extra+incorrect), recall = matched/(matched+missing+incorrect)
   trong một test mới. Chọn một document có missing và extra để thấy hai
   số tách biệt. *Mục tiêu*: nối metric với phân loại lỗi.

3. **Phát hiện leakage bằngnear-duplicate**: viết hàm so sánh 2 document
   bằng CER của `full_text`; dùng nó để gom các document giống nhau
   >90% vào cùng một split. Chạy trên vài fixture. *Mục tiêu*: hiểu vì
   sao split theo document là chưa đủ — cần cả near-duplicate check.
