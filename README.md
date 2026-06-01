# Teams Auto-Joiner — bản cập nhật cho Microsoft Teams mới

> **Lấy cảm hứng từ dự án gốc của TobiasPankner:**
> **https://github.com/TobiasPankner/Teams-Auto-Joiner**
>
> Bản gốc không còn chạy được vì Microsoft đã thay đổi **hoàn toàn** giao diện Teams (sang "new Teams"). Dự án này viết lại để hoạt động trở lại với **Microsoft Teams phiên bản mới (2026)**, đồng thời thêm giao diện cấu hình bằng web. Xin cảm ơn tác giả **TobiasPankner** cho ý tưởng và nền tảng ban đầu.

Script Python tự động **tham gia cuộc họp Microsoft Teams** giúp bạn — tự **tắt camera & micro** trước khi vào, có thể tự gửi lời nhắn và tự rời họp theo điều kiện.

---

## Tính năng
- Tự đăng nhập, tự tìm cuộc họp trong **Lịch (Calendar)** hoặc **kênh (Channel)**.
- **Đếm ngược tới buổi học kế tiếp** ngay trên Terminal, **tự vào lớp sớm N phút** (bạn tự chọn; `0` = đúng giờ).
  - Đọc **giờ** từ **banner cuộc họp trong kênh** *và* **sự kiện trên Lịch Outlook**, chọn buổi gần nhất.
- Tự vào họp với **camera & mic đã tắt sẵn**.
- (Tùy chọn) Tự **gửi lời nhắn** vào **chat phòng họp** khi vào.
- (Tùy chọn) Tự **rời họp** sau X phút.
- **Giao diện cấu hình bằng web**, có chế độ **Sáng / Tối** — không cần sửa file tay.
- Hỗ trợ **Teams giao diện tiếng Việt** (nhận diện nút theo ID cố định + nhãn tiếng Việt).

## Yêu cầu
- **Python 3.8+**
  - Windows: tải tại https://www.python.org/downloads/ — nhớ tick **"Add Python to PATH"** khi cài.
  - macOS: tải tại https://www.python.org/downloads/ hoặc chạy `brew install python`.
- **Google Chrome** hoặc **Microsoft Edge** (hầu hết máy đã có sẵn).
- Một tài khoản **Microsoft Teams**.

## Cài đặt & chạy

### Windows
1. **Cài thư viện** (chỉ làm một lần). Mở PowerShell trong thư mục này rồi gõ:
   ```
   pip install -r requirements.txt
   ```
2. **Double-click `run.bat`** để khởi động.
3. Một **cửa sổ cấu hình** hiện ra trong trình duyệt → điền **Email / Mật khẩu**, chọn **Nguồn tìm cuộc họp**, bấm **▶ Bắt đầu**.
4. Bot mở Chrome, đăng nhập và bắt đầu tự tìm + vào họp.

### macOS
1. **Cài thư viện** (chỉ làm một lần). Mở Terminal trong thư mục này rồi gõ:
   ```
   pip3 install -r requirements.txt
   ```
2. **Double-click `run.command`** trong Finder để khởi động.
   - Script sẽ **tự kiểm tra** Python, các thư viện và trình duyệt trước khi chạy — nếu thiếu gì sẽ hiện hướng dẫn cụ thể.
   - **Lần đầu chạy:** macOS có thể chặn vì file tải từ internet. Vào **System Settings → Privacy & Security**, kéo xuống tìm thông báo bị chặn và nhấn **"Open Anyway"**.
3. Một **cửa sổ cấu hình** hiện ra trong trình duyệt → điền **Email / Mật khẩu**, chọn **Nguồn tìm cuộc họp**, bấm **▶ Bắt đầu**.
4. Bot mở Chrome, đăng nhập và bắt đầu tự tìm + vào họp.

> **Đừng bấm gì vào cửa sổ Chrome đó** trong khi bot đang chạy.
> Nếu hiện yêu cầu xác thực (MFA / OTP), bạn tự hoàn tất trong cửa sổ đó — bot sẽ chờ.

## Các tùy chọn cấu hình
| Tùy chọn | Ý nghĩa |
|---|---|
| **Email / Mật khẩu** | Tài khoản Teams. Để trống thì bạn tự đăng nhập tay trong trình duyệt. |
| **Nguồn tìm cuộc họp** | `Chỉ Lịch` (nhanh — đọc giờ trên Lịch Outlook) · `Chỉ Kênh` (đọc banner trong kênh) · `Cả hai` (đầy đủ nhất). Chế độ nào cũng đếm ngược + tự vào lớp. |
| **Vào lớp sớm (phút)** | Tự vào lớp trước giờ bắt đầu mấy phút (`0` = đúng giờ). Bot đếm ngược rồi vào. |
| **Chạy ẩn (headless)** | Chạy ngầm, không hiện cửa sổ trình duyệt. |
| **Tắt loa trình duyệt** | Tắt âm thanh phát ra từ trình duyệt (không ảnh hưởng micro của bạn). |
| **Tự rời họp sau (phút)** | `-1` = không tự rời (ở lại tới khi có họp mới). |
| **Khoảng quét lại (giây)** | Bao lâu kiểm tra cuộc họp mới một lần. |
| **Lời nhắn khi vào họp** | Tin tự gửi vào **chat phòng họp** (để trống = không gửi). |
| **Discord webhook** | (Tùy chọn) gửi thông báo trạng thái qua Discord. |

Các tùy chọn nâng cao khác (blacklist kênh, lọc theo regex tên họp, đa tổ chức…) có thể chỉnh trực tiếp trong `config.json` — xem `config.json.example` để biết đầy đủ.

> Cấu hình được lưu vào **`config.json`** (tạo tự động khi bạn bấm Bắt đầu).
> **File này chứa mật khẩu của bạn — KHÔNG chia sẻ, KHÔNG đẩy lên GitHub.** Đã được `.gitignore` loại trừ sẵn.

## Cách hoạt động (tóm tắt)
1. Mở Chrome qua **Selenium** → vào `teams.microsoft.com` → đăng nhập.
2. **Dò lịch học**: đọc **giờ bắt đầu** từ banner cuộc họp trong **kênh** và sự kiện trên **Lịch Outlook**, gộp lại và chọn **buổi gần nhất**.
3. **Đếm ngược** trên Terminal tới mốc *(giờ bắt đầu − số phút "vào sớm")*.
4. Tới mốc đó → vào lớp; nếu giảng viên chưa mở thì **thử lại** tới khi vào được → mở màn hình chờ → **tắt camera & micro** → bấm **Tham gia**.
5. (Nếu đặt) gửi **lời nhắn** vào **chat phòng họp**; tự rời theo điều kiện bạn cấu hình; xong thì quay lại đếm ngược buổi tiếp theo.

> **Lưu ý:** Bot chỉ vào được lớp khi lớp **thực sự đang/đến giờ diễn ra**. Buổi học của bạn nên có mặt trong **kênh lớp** (hoặc bạn ghi giờ lên **Lịch Outlook**) để bot dò ra.

## Khắc phục sự cố
- **"Không tìm thấy Python"** → cài Python và tick *Add Python to PATH* (Windows) hoặc `brew install python` (macOS), rồi chạy lại.
- **macOS: "run.command không thể mở vì không xác định được nhà phát triển"** → vào **System Settings → Privacy & Security → Open Anyway**.
- **macOS: "Package chưa được cài"** → mở Terminal, chạy `pip3 install -r requirements.txt` trong thư mục này.
- **Kẹt ở màn hình đăng nhập / MFA** → tự hoàn tất trong cửa sổ Chrome; bot chờ tối đa ~2,5 phút.
- **Không tìm thấy cuộc họp trong Lịch** → cuộc họp chỉ tham gia được khi **đang/đến giờ**. Kiểm tra đúng tài khoản và cuộc họp là *Cuộc họp Microsoft Teams*.
- **Nút bấm bị lỗi sau khi Teams cập nhật** → xem mục *Dành cho người phát triển* bên dưới.

## Dành cho người phát triển
Microsoft thường xuyên đổi giao diện Teams → có thể làm hỏng các *selector*. Khi đó dùng công cụ kèm theo để chụp lại cấu trúc DOM mới:
```
python inspect_teams.py
```
Đăng nhập, bấm tới màn hình cần, gõ **Enter** để lưu **HTML + ảnh chụp + danh sách nút bấm** (vào thư mục `dumps/`), rồi cập nhật selector trong `auto_joiner.py`.

| File | Vai trò |
|---|---|
| `auto_joiner.py` | Bot chính (đăng nhập, tìm họp, vào họp, gửi lời nhắn). |
| `setup_ui.py` | Giao diện web để cấu hình. |
| `inspect_teams.py` | Công cụ chụp DOM (dùng khi Teams đổi giao diện). |
| `run.bat` | Trình khởi động cho **Windows** (double-click là chạy). |
| `run.command` | Trình khởi động cho **macOS** (double-click là chạy, tự kiểm tra yêu cầu hệ thống). |
| `config.json.example` | Mẫu cấu hình đầy đủ các tùy chọn. |

## Ghi nhận
Dựa trên ý tưởng và mã nguồn ban đầu của **[TobiasPankner/Teams-Auto-Joiner](https://github.com/TobiasPankner/Teams-Auto-Joiner)**. Bản này cập nhật toàn bộ selector cho new Teams và bổ sung giao diện cấu hình.
