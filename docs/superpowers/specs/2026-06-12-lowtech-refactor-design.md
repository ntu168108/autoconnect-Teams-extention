# Thiết kế: Refactor + đóng gói 1-click cho người dùng lowtech (Windows & macOS)

Ngày: 2026-06-12 · Trạng thái: ĐÃ DUYỆT

## Mục tiêu

Người dùng không biết kỹ thuật có thể dùng bot mà **không cài Python, không gõ lệnh,
không đọc Terminal**:

1. **Đóng gói 1-click**: tải file từ GitHub Releases, giải nén, double-click là chạy.
2. **Web UI thành bảng theo dõi**: sau khi bấm "Bắt đầu", trang cấu hình chuyển thành
   trang trạng thái (đếm ngược, lịch học, log, nút Dừng).
3. **Refactor** `src/auto_joiner.py` (1127 dòng) thành các module rõ vai trò.
   Logic selector/join giữ nguyên 100% — chỉ di chuyển code.

## 1. Trải nghiệm người dùng cuối

- **Windows**: Releases → `TeamsAutoJoiner-Windows.zip` → giải nén →
  double-click `Teams Auto-Joiner.exe`.
- **macOS**: `TeamsAutoJoiner-macOS.zip` → giải nén → double-click `Chạy bot.command`
  (lần đầu: chuột phải → Open vì app chưa ký — ghi rõ trong README và trên Web UI).
- Sau khi mở: form cấu hình → bấm **Bắt đầu** → cùng cửa sổ chuyển sang `/status`:
  - Trạng thái lớn: "Đang dò lịch…" / "Còn 01:23:45 đến <môn>" / "Đang trong lớp".
  - Buổi kế tiếp + danh sách lịch đã dò.
  - Nhật ký hoạt động tiếng Việt, cuộn được.
  - Nút **Dừng bot**.
- Console vẫn hiện làm kênh dự phòng (nếu trình duyệt không mở được).

## 2. Kiến trúc

- HTTP server (stdlib, 127.0.0.1, port ngẫu nhiên) **sống suốt vòng đời bot**.
  Routes: `GET /` (form), `POST /` (lưu config), `GET /status` (bảng theo dõi),
  `GET /api/status` (JSON), `POST /api/stop` (dừng bot).
- Object `Status` thread-safe duy nhất: bot gọi `status.report(state, **fields)` và
  `status.log(msg)` tại các mốc; web poll `/api/status` mỗi 2 giây.
- Đếm ngược chạy bằng JS phía client từ timestamp đích (không tốn server mỗi giây).
- Dừng bot: `POST /api/stop` set cờ `status.stop_requested`; vòng lặp chính kiểm tra
  cờ ở mỗi điểm chờ và thoát sạch (đóng Chrome).

## 3. Cấu trúc module mới (`src/`)

| Module | Vai trò |
|---|---|
| `main.py` | Entry point: GUI/`--no-gui`, vòng đời, bắt lỗi thân thiện tiếng Việt |
| `config.py` | Load/save config; xử lý đường dẫn khi đóng gói (config.json cạnh file exe — dùng `sys.executable` khi `sys.frozen`, KHÔNG dùng `_MEIPASS`) |
| `selectors.py` | Toàn bộ CSS selector + đoạn JS của Teams/Outlook |
| `browser.py` | Mở Chrome/Edge, login, `wait_until_found`/`wait_present`, `_browser_dead` |
| `scanner.py` | Dò lịch: banner kênh + Lịch Outlook (iframe), parse giờ VI |
| `joiner.py` | Vào lớp: prejoin, tắt cam/mic, lời nhắn vào chat họp, rời họp, đếm người |
| `schedule.py` | Vòng lặp chính: dò → đếm ngược → vào lớp → ở lại → lặp |
| `status.py` | Trạng thái chia sẻ + ring buffer log (cũng tee ra console) |
| `webui.py` | Form cấu hình + trang theo dõi + API (thay `setup_ui.py`) |
| `notify.py` | Discord webhook qua `requests.post` trực tiếp — **bỏ dependency `discord.py`** |

## 4. Build & phát hành

- `.github/workflows/release.yml`: push tag `v*` → 2 job (windows-latest,
  macos-latest) → PyInstaller onefile (console=True) → zip kèm hướng dẫn ngắn →
  đăng GitHub Releases.
- `build.spec` + `build_local.bat` / `build_local.command` để thử build trước khi tag.
- `run.bat` / `run.command` giữ nguyên cho ai chạy từ source.
- `requirements.txt`: bỏ `discord.py`, giữ `selenium`, `requests`.

## 5. Rủi ro & cách xử lý

- **PyInstaller + Selenium Manager**: Selenium 4.6+ tự tải driver lúc chạy — OK
  trong exe; cần mạng lần đầu.
- **Đường dẫn khi frozen**: mọi `open()` tương đối đi qua `config.py:get_root()`.
- **macOS Gatekeeper**: hướng dẫn chuột phải → Open (README + Web UI).
- **Windows SmartScreen**: ghi chú "More info → Run anyway" trong README.
- **Regression selector**: không đổi bất kỳ selector/flow nào đã verify chạy thật.

## 6. Kiểm thử

- Smoke: import sạch từng module; `python src/main.py --no-gui` với config mẫu
  khởi động đến bước mở Chrome.
- Web UI: mở form, submit, kiểm tra `/status` + `/api/status` trả đúng JSON,
  nút Dừng hoạt động.
- Build local Windows: exe chạy được trên chính máy này.
- macOS build verify qua GitHub Actions artifact (user có máy Mac để thử).
