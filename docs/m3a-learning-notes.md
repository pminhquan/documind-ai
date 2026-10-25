# Learning Notes — M3A: Nhận dạng cấu trúc bảng có kẻ ô

Ghi chú học tập tiếng Việt cho milestone M3A.

---

## 1. Image thresholding (phân ngưỡng ảnh) là gì?

Là biến ảnh xám thành ảnh **nhị phân** đen/trắng bằng một ngưỡng:
pixel < ngưỡng → đen, ngược lại → trắng. Trong M3A dùng
**Otsu threshold** (`cv2.THRESH_OTSU`): thuật toán tự chọn ngưỡng tối ưu
bằng cách cực tiểu hóa phương saiWithin-class của 2 nhóm pixel — hữu ích
khi không biết trước độ sáng của scan. Kèm `THRESH_BINARY_INV` (đảo) để
**nét đen (đường kẻ + chữ) thành màu trắng (=255)** vì các thao tác
morphology của OpenCV mặc định thao tác trên vùng trắng.

Mẹo ghi nhớ: `imread` của OpenCV đọc ảnh màu là BGR (không phải RGB) —
bug kinh điển khi hiển thị/xử lý.

## 2. Morphological operations (phép hình thái học) là gì?

Là các phép biến đổi ảnh nhị phân dựa trên **structuring element**
(kernel) — một cửa sổ nhỏ định hình "hình dạng" cần xử lý:

- **Erosion** (xói mòn): pixel giữ giá trị trắng chỉ khi **toàn bộ** cửa
  sổ nằm trong vùng trắng. Kernel `(40, 1)` ngang → chỉ giữ run trắng
  dài ≥ 40px **nằm ngang liên tục**.
- **Dilation** (giãn nở): pixel thành trắng nếu **bất kỳ** phần cửa sổ
  chạm vùng trắng — phục hồi độ dày đường kẻ sau erosion.

Cặp erosion → dilation gọi là **opening**: loại bỏ các đối tượng nhỏ hơn
kernel, giữ nguyên hình dạng đối tượng lớn. Đây chính là cách tách
**đường kẻ** khỏi **chữ**: nét chữ cao ~14px < kernel dọc 20px → biến
mất; đường kẻ dọc cao ~150px → sống sót.

## 3. Phát hiện đường ngang/dọc hoạt động thế nào?

Sau opening, dùng **projection profile** — cộng số pixel trắng theo mỗi
hàng (đường ngang) hoặc mỗi cột (đường dọc):

```
h_mask.sum(axis=1)  → mảng counts theo y → hàng nào có ≥ 60% bề rộng
                      vùng bảng là trắng → đó là vị trí đường kẻ ngang
v_mask.sum(axis=0)  → tương tự theo x cho đường kẻ dọc
```

Các pixel hàng liền kề (đường kẻ dày 2-3px) được **cluster** về một tâm
line. Danh sách tâm line = **các cạnh lưới** (row_edges / col_edges).
Vùng bảng được tìm bằng connected component trên phép OR của 2 mask —
mỗi bảng một component, sắp theo y để hỗ trợ nhiều bảng trong một ảnh.

## 4. Bounding-box intersection (giao hình chữ nhật)

Hai hình chữ nhật giao nhau khi **cả hai chiều** chồng lên:

```python
overlap_w = min(a.x2, b.x2) - max(a.x, b.x)   # > 0 mới có giao
overlap_h = min(a.y2, b.y2) - max(a.y, b.y)
area = max(0, overlap_w) * max(0, overlap_h)
```

Trong M3A, intersection area dùng làm **fallback khi center-point miss**:
nếu tâm box OCR rơi ngoài mọi cell (box hơi tràn qua nét kẻ), chọn cell
có diện tích giao lớn nhất. Đây là kỹ thuật chung cho mọi bài toán gán
vùng (object detection, layout matching) — hãy nhớ thứ tự ưu tiên:
**center-point trước (rõ nghĩa), max-overlap sau (an toàn)**.

## 5. Cell assignment (gán OCR vào ô)

Mỗi OCR region được gán theo bước:
1. Tính **tâm** box (trung bình 4 đỉnh).
2. Tìm cell chứa tâm — các cell rời rạc nên tối đa 1 cell thỏa.
3. Miss → dùng max-overlap (mục 4). Vẫn miss → ghi vào `warnings`
   (region ngoài lưới, vd. tiêu đề phía trên bảng) — **không ép gán**.
4. Nhiều region trong cùng cell → nối bằng space theo thứ tự đọc
   (y rồi x); confidence = **trung bình** các region.

Nguyên tắc xuyên suốt project: **không bịa dữ liệu** — cell trống giữ
`text: ""`, `confidence: null`.

## 6. Ruled vs borderless tables — khác biệt cốt lõi

| | **Ruled** (M3A) | **Borderless** (M3B) |
|---|---|---|
| Đường kẻ | Có, đầy đủ, thẳng | Không có hoặc chỉ gạch chân hàng |
| Cách tách | Hình thái học tách line → giao điểm | Phải học vị trí text (model, ví dụ SLANet/TableMaster) hoặc cluster khoảng cách giữa các region |
| Độ khó | Thấp, deterministic, test được không cần OCR | Cao, cần dữ liệu train |
| Ứng dụng thực | Scan biểu mẫu, báo cáo in | Ảnh chụp web, PDF xuất từ HTML |

Chiến lược ngành: luôn thử **rule baseline cho ruled table trước** — rẻ,
chính xác tuyệt đối khi input đúng dạng; model chỉ cần cho phần borderless.

## 7. Ba bài tập tự luyện (không cần AI agent)

1. **Đổi kernel, quan sát**: trong `src/documind/tables/geometry.py`,
   đổi `MIN_KERNEL` từ 20 → 10 và chạy lại `documind-table` trên
   `table_gaps.png`. Giải thích vì sao kết quả vẫn/không còn đúng
   (gợi ý: chữ cao bao nhiêu px so với kernel?). *Mục tiêu*: cảm nhận
   vai trò của kernel size trong opening.

2. **Thêm warning "cell quá lớn"**: cell có diện tích gấp 10 lần trung
   bình thường là dấu hiệu lưới bị miss một cạnh. Viết test trước trong
   `tests/test_tables_assign.py`, rồi implement warning trong
   `pipeline.py`. *Mục tiêu*: thực hành heuristic chất lượng + TDD.

3. **Đo giao box 2 chiều**: viết hàm thuần
   `iou(box_a, box_b) -> float` (intersection over union) cho box 4 điểm,
   kèm 4 test (không giao, chạm cạnh, chứa nhau, giao một phần).
   So sánh kết quả với `Rect.intersection_area`. *Mục tiêu*: chuẩn hóa
   kỹ thuật đo giao — dùng nhiều trong object detection.
