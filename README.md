<div align="center">

# Teams Auto-Joiner

**Tự động vào họp Microsoft Teams — Cập nhật hoàn toàn cho New Teams 2026**

[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![Selenium](https://img.shields.io/badge/Selenium-4.x-43B02A?logo=selenium&logoColor=white)](https://selenium.dev)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS-0078D4?logo=windows&logoColor=white)](.)
[![GitHub Stars](https://img.shields.io/github/stars/ntu168108/autoconnect-Teams-extention?style=flat&color=gold&logo=github)](https://github.com/ntu168108/autoconnect-Teams-extention/stargazers)
[![Last Commit](https://img.shields.io/github/last-commit/ntu168108/autoconnect-Teams-extention?color=brightgreen)](https://github.com/ntu168108/autoconnect-Teams-extention/commits)
[![Release](https://img.shields.io/github/v/release/ntu168108/autoconnect-Teams-extention?color=blue)](https://github.com/ntu168108/autoconnect-Teams-extention/releases)

<br/>

*Lấy cảm hứng từ [TobiasPankner/Teams-Auto-Joiner](https://github.com/TobiasPankner/Teams-Auto-Joiner) — viết lại hoàn toàn để hoạt động với giao diện Teams mới nhất, kèm Web UI cấu hình.*

</div>

---

## Mục lục

- [Tính năng](#tính-năng)
- [Yêu cầu](#yêu-cầu)
- [Cài đặt & chạy](#cài-đặt--chạy)
- [Các tùy chọn cấu hình](#các-tùy-chọn-cấu-hình)
- [Cách hoạt động](#cách-hoạt-động)
- [Khắc phục sự cố](#khắc-phục-sự-cố)
- [Dành cho người phát triển](#dành-cho-người-phát-triển)
- [Star History](#star-history)
- [Ghi nhận](#ghi-nhận)

---

## Tính năng

- Tự đăng nhập, tự tìm cuộc họp trong **Lịch (Calendar)** hoặc **kênh (Channel)**
- **Đếm ngược tới buổi học kế tiếp** trên Terminal, **tự vào lớp sớm N phút** (tự chọn; `0` = đúng giờ)
  - Đọc giờ từ **banner cuộc họp trong kênh** *và* **sự kiện trên Lịch Outlook**, chọn buổi gần nhất
- Tự vào họp với **camera & mic đã tắt sẵn**
- *(Tùy chọn)* Tự **gửi lời nhắn** vào **chat phòng họp** khi vào
- *(Tùy chọn)* Tự **rời họp** sau X phút
- **Giao diện cấu hình bằng web**, có chế độ **Sáng / Tối** — không cần sửa file tay
- Hỗ trợ **Teams giao diện tiếng Việt** (nhận diện nút theo ID cố định + nhãn tiếng Việt)

---

## Yêu cầu

| Phần mềm | Phiên bản | Ghi chú |
|---|---|---|
| **Python** | 3.8+ | [python.org/downloads](https://www.python.org/downloads/) — tick **"Add Python to PATH"** khi cài (Windows) |
| **Trình duyệt** | Chrome hoặc Edge | Hầu hết máy đã có sẵn |
| **Tài khoản** | Microsoft Teams | Tài khoản tổ chức hoặc cá nhân |

---

## Cài đặt & chạy

### Windows

```bash
# Bước 1 — Cài thư viện (chỉ làm một lần)
pip install -r requirements.txt
```

Sau đó **double-click `run.bat`** để khởi động.

---

### macOS

```bash
# Bước 1 — Cài thư viện (chỉ làm một lần)
pip3 install -r requirements.txt
```

Sau đó **double-click `run.command`** trong Finder.

> **Lần đầu chạy bị chặn?** Vào **System Settings → Privacy & Security → Open Anyway**.

---

**Các bước tiếp theo (cả 2 hệ điều hành):**

3. Cửa sổ **cấu hình Web UI** hiện ra trong trình duyệt → điền **Email / Mật khẩu**, chọn **Nguồn tìm cuộc họp**, bấm **▶ Bắt đầu**
4. Bot mở Chrome, đăng nhập và bắt đầu tự tìm + vào họp

> **Đừng bấm gì vào cửa sổ Chrome đó** trong khi bot đang chạy.
> Nếu hiện yêu cầu xác thực **(MFA / OTP)**, bạn tự hoàn tất trong cửa sổ đó — bot sẽ chờ.

---

## Các tùy chọn cấu hình

| Tùy chọn | Ý nghĩa |
|---|---|
| **Email / Mật khẩu** | Tài khoản Teams. Để trống → tự đăng nhập tay trong trình duyệt. |
| **Nguồn tìm cuộc họp** | `Chỉ Lịch` (nhanh) · `Chỉ Kênh` · `Cả hai` (đầy đủ nhất) |
| **Vào lớp sớm (phút)** | `0` = đúng giờ. Bot đếm ngược rồi tự vào. |
| **Chạy ẩn (headless)** | Chạy ngầm, không hiện cửa sổ trình duyệt. |
| **Tắt loa trình duyệt** | Tắt âm thanh phát ra từ trình duyệt (không ảnh hưởng mic của bạn). |
| **Tự rời họp sau (phút)** | `-1` = không tự rời, ở lại tới khi có họp mới. |
| **Khoảng quét lại (giây)** | Tần suất kiểm tra cuộc họp mới. |
| **Lời nhắn khi vào họp** | Tin tự gửi vào chat phòng họp (để trống = không gửi). |
| **Discord webhook** | *(Tùy chọn)* Gửi thông báo trạng thái qua Discord. |

Các tùy chọn nâng cao (blacklist kênh, lọc regex tên họp, đa tổ chức…) chỉnh trực tiếp trong `config.json` — xem `config.json.example`.

> **Bảo mật:** `config.json` chứa mật khẩu của bạn. **KHÔNG chia sẻ, KHÔNG đẩy lên GitHub.** File đã được `.gitignore` loại trừ sẵn.

---

## Cách hoạt động

```
┌─────────────────────────────────────────────────────┐
│  1. Selenium mở Chrome → teams.microsoft.com         │
│              ↓                                       │
│  2. Dò lịch học: Kênh + Lịch Outlook                │
│     → chọn buổi gần nhất                            │
│              ↓                                       │
│  3. Đếm ngược tới (giờ bắt đầu − phút vào sớm)      │
│              ↓                                       │
│  4. Vào lớp → tắt camera & mic → bấm Tham gia       │
│              ↓                                       │
│  5. Gửi lời nhắn (nếu đặt)                          │
│     → Tự rời (nếu đặt) → Lặp lại từ bước 2          │
└─────────────────────────────────────────────────────┘
```

> **Lưu ý:** Bot chỉ vào được lớp khi lớp **thực sự đang/đến giờ diễn ra**. Buổi học phải có mặt trong **kênh lớp** hoặc trên **Lịch Outlook** để bot dò ra.

---

## Khắc phục sự cố

<details>
<summary><b>"Không tìm thấy Python"</b></summary>

Cài Python và tick **Add Python to PATH** (Windows) hoặc chạy `brew install python` (macOS), sau đó chạy lại.
</details>

<details>
<summary><b>macOS: "run.command không thể mở vì không xác định được nhà phát triển"</b></summary>

Vào **System Settings → Privacy & Security → Open Anyway**.
</details>

<details>
<summary><b>macOS: "Package chưa được cài"</b></summary>

Mở Terminal trong thư mục dự án, chạy:
```bash
pip3 install -r requirements.txt
```
</details>

<details>
<summary><b>Kẹt ở màn hình đăng nhập / MFA</b></summary>

Tự hoàn tất xác thực trong cửa sổ Chrome — bot chờ tối đa ~2.5 phút.
</details>

<details>
<summary><b>Không tìm thấy cuộc họp trong Lịch</b></summary>

Cuộc họp chỉ tham gia được khi **đang/đến giờ diễn ra**. Kiểm tra đúng tài khoản và đây là *Cuộc họp Microsoft Teams* (không phải sự kiện thường).
</details>

<details>
<summary><b>Nút bấm bị lỗi sau khi Teams cập nhật</b></summary>

Microsoft thường xuyên đổi UI — xem mục **Dành cho người phát triển** bên dưới để cập nhật selector.
</details>

---

## Dành cho người phát triển

Microsoft thường xuyên đổi giao diện Teams → có thể làm hỏng các *selector*. Dùng công cụ debug kèm theo:

```bash
python inspect_teams.py
```

Đăng nhập, điều hướng đến màn hình cần, gõ **Enter** để lưu **HTML + screenshot + danh sách nút bấm** vào `dumps/`, rồi cập nhật selector trong `auto_joiner.py`.

| File | Vai trò |
|---|---|
| `auto_joiner.py` | Bot chính (đăng nhập, tìm họp, vào họp, gửi lời nhắn) |
| `setup_ui.py` | Giao diện web cấu hình |
| `inspect_teams.py` | Công cụ debug & chụp DOM |
| `run.bat` | Trình khởi động **Windows** |
| `run.command` | Trình khởi động **macOS** (tự kiểm tra yêu cầu hệ thống) |
| `config.json.example` | Mẫu cấu hình đầy đủ tất cả tùy chọn |

---

## Star History

<a href="https://www.star-history.com/?repos=ntu168108%2Fautoconnect-Teams-extention&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=ntu168108/autoconnect-Teams-extention&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=ntu168108/autoconnect-Teams-extention&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=ntu168108/autoconnect-Teams-extention&type=date&legend=top-left" />
 </picture>
</a>

---

## Ghi nhận

Dựa trên ý tưởng và mã nguồn ban đầu của **[TobiasPankner/Teams-Auto-Joiner](https://github.com/TobiasPankner/Teams-Auto-Joiner)**.  
Bản này viết lại toàn bộ selector cho New Teams và bổ sung giao diện cấu hình Web UI.
