# DocuMind AI — Setup (Windows)

Hướng dẫn cài đặt môi trường phát triển trên Windows bằng **Python 3.12 (64-bit)**.

## 1. Vì sao Python 3.12?

- **PaddlePaddle 3.x** (backend của PaddleOCR) hiện hỗ trợ Python **3.9–3.13**.
  Python 3.14 (bản mặc định trên máy này) **chưa** có wheel tương thích.
- Python 3.12 là phiên bản ổn định, được hỗ trợ đầy đủ bởi toàn bộ stack
  (paddlepaddle, paddleocr, pillow, pytest), nên được chọn làm interpreter
  chuẩn của dự án.

## 2. Cài Python 3.12 (nếu chưa có)

```powershell
# Kiểm tra các bản Python đã cài
py -0p

# Cài Python 3.12 cho user hiện tại (không cần admin)
winget install --id Python.Python.3.12 --scope user
```

Sau khi cài, xác minh:

```powershell
py -3.12 -V
# Python 3.12.10
```

## 3. Tạo virtual environment

Từ thư mục gốc của dự án:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -V   # phải là 3.12.x và trỏ tới .venv\Scripts\python.exe
```

> Nếu PowerShell chặn script, chạy một lần:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

## 4. Cài dependencies

```powershell
python -m pip install --upgrade pip
pip install -e ".[dev]"        # paddlepaddle (CPU) + paddleocr + pillow + pytest
pip install -e ".[web]"        # FastAPI stack; also required to run the web tests locally
```

`requirements.lock.txt` là ảnh chụp môi trường lịch sử, **không phải**
installer cho checkout hiện tại: nó ghim chính project vào một commit cũ
(`-e git+https://github.com/pminhquan/documind-ai.git@ab62d749...`), trước
cả M5A. Luôn dùng lệnh editable install ở trên để chạy đúng `src/` hiện tại.

## 5. Xác minh cài đặt

```powershell
python -c "import documind; print(documind.__version__)"
documind-ocr --help
pytest
```

## Ghi chú

- Bản cài CPU của PaddlePaddle là mặc định trên Windows; **không** cài bản
  GPU/CUDA trừ khi đã xác nhận có card NVIDIA tương thích.
- Model PP-OCRv6 (detection + recognition, ghim tường minh trong
  `src/documind/ocr/engine.py`) được tải tự động **lần chạy đầu tiên**
  vào cache của user (`~/.paddlex/official_models`), nằm ngoài repository.
