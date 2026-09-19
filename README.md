<div align="center">

# Teams Auto-Joiner

**Tự động vào họp Microsoft Teams — Cập nhật hoàn toàn cho New Teams 2026**

[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![Selenium](https://img.shields.io/badge/Selenium-4.x-43B02A?logo=selenium&logoColor=white)](https://selenium.dev)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-0078D4?logo=windows&logoColor=white)](.)
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
- [Bảng theo dõi](#bảng-theo-dõi)
- [Cách hoạt động](#cách-hoạt-động)
- [Khắc phục sự cố](#khắc-phục-sự-cố)
- [Dành cho người phát triển](#dành-cho-người-phát-triển)
- [Star History](#star-history)

---

## Tính năng

- Tự đăng nhập, tự tìm cuộc họp trong **Lịch (Calendar)** hoặc **kênh (Channel)**
- **Đếm ngược tới buổi học kế tiếp** trên Terminal, **tự vào lớp sớm N phút** (tự chọn; `0` = đúng giờ)
  - Đọc giờ từ **banner cuộc họp trong kênh** *và* **sự kiện trên Lịch Outlook**, chọn buổi gần nhất
  - Lịch được đọc thẳng qua **API JSON của Outlook** — lấy được cả **nhiều tuần** trong ~1 giây, không phụ thuộc ngôn ngữ hiển thị. Nếu API lỗi, bot tự quay về cách đọc giao diện như cũ.
- Tự vào họp với **camera & mic đã tắt sẵn**
- **Nút "Vào ngay"** trên bảng theo dõi: bấm là vào thẳng buổi đó, không cần chờ đếm ngược
- *(Tùy chọn)* Tự **rời lớp khi lớp vắng** (dưới số người tối thiểu bạn đặt) rồi **tự chờ buổi kế tiếp**
- *(Tùy chọn)* Tự **gửi lời nhắn** vào **chat phòng họp** khi vào
- *(Tùy chọn)* Tự **rời họp** sau X phút
- **Giao diện cấu hình bằng web**, có chế độ **Sáng / Tối** — không cần sửa file tay
- Hỗ trợ **Teams giao diện tiếng Việt** (nhận diện nút theo ID cố định + nhãn tiếng Việt)

---

## Yêu cầu

| Phần mềm | Phiên bản | Ghi chú |
|---|---|---|
| **Python** | 3.8+ | [python.org/downloads](https://www.python.org/downloads/) — tick **"Add Python to PATH"** khi cài (Windows) · Linux: `sudo apt install python3 python3-pip` |
| **Trình duyệt** | Chrome, Edge hoặc Chromium | Hầu hết máy đã có sẵn · Linux: `sudo apt install chromium-browser` |
| **Tài khoản** | Microsoft Teams | Tài khoản tổ chức hoặc cá nhân |

---

## Cài đặt & chạy

### Cách 1 — Tải bản dựng sẵn (KHUYÊN DÙNG, không cần cài gì)

1. Vào trang **[Releases](https://github.com/ntu168108/autoconnect-Teams-extention/releases)** → tải file cho máy bạn:
   - Windows: `TeamsAutoJoiner-Windows.zip`
   - macOS: `TeamsAutoJoiner-macOS.zip`
   - Linux: `TeamsAutoJoiner-Linux.zip`
2. **Giải nén** ra một thư mục bất kỳ.
3. Chạy:
   - Windows: double-click `TeamsAutoJoiner.exe` — nếu hiện cảnh báo xanh, bấm **More info → Run anyway**.
   - macOS: double-click `Chạy bot.command` — lần đầu bị chặn thì **chuột phải → Open → Open**.
   - Linux: mở Terminal trong thư mục đó rồi chạy `./chay-bot.sh`.
4. Form cấu hình hiện ra → điền **Email / Mật khẩu** → bấm **▶ Bắt đầu**.
5. Trang chuyển thành **Bảng theo dõi**: đếm ngược, lịch học, nhật ký, nút **Dừng bot**. Để cửa sổ này mở.

> Máy cần có **Google Chrome** hoặc **Microsoft Edge** (hầu hết máy có sẵn).
>
> **Đừng bấm gì vào cửa sổ Chrome mà bot mở.** Nếu hiện yêu cầu xác thực
> **(MFA / OTP)**, bạn tự hoàn tất trong cửa sổ đó — bot sẽ chờ.

### Cách 2 — Chạy từ mã nguồn (cần Python 3.8+)

```bash
pip install -r requirements.txt
```

Rồi chạy:

| Hệ điều hành | Cách chạy |
|---|---|
| Windows | double-click `run.bat` |
| macOS | double-click `run.command` |
| Linux | `./run.sh` trong Terminal |

Script sẽ tự kiểm tra Python, thư viện và trình duyệt trước khi khởi động, và báo đúng lệnh cài đặt cho hệ điều hành của bạn nếu thiếu.

> **macOS lần đầu chạy bị chặn?** Vào **System Settings → Privacy & Security → Open Anyway**.
>
> **Linux chạy trên máy chủ / qua SSH (không có màn hình)?** Đặt `"headless": true`
> trong `config.json` — script sẽ nhắc bạn nếu phát hiện không có màn hình đồ hoạ.

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
| **Tự rời khi lớp vắng** | Bật để bot theo dõi số người trong lớp. |
| **Số người tối thiểu** | Rời lớp khi còn ít hơn số này (`0` = tắt). Rời xong bot tự chờ buổi kế tiếp. |
| **Discord webhook** | *(Tùy chọn)* Gửi thông báo trạng thái qua Discord. |

Các tùy chọn nâng cao (bỏ qua kênh, đa tổ chức, múi giờ…) chỉnh trực tiếp trong `config.json` — xem `config.json.example`.

> **Bảo mật:** `config.json` chứa mật khẩu của bạn. **KHÔNG chia sẻ, KHÔNG đẩy lên GitHub.** File đã được `.gitignore` loại trừ sẵn.

---

## Bảng theo dõi

Sau khi bấm **Bắt đầu**, cửa sổ cấu hình chuyển thành bảng theo dõi. Cứ để nó mở:

| Khu vực | Dùng để làm gì |
|---|---|
| **Đồng hồ đếm ngược** | Còn bao lâu tới lúc bot tự vào lớp |
| **Lịch đã dò được** | Các buổi học bot tìm thấy. Buổi đã tan bị làm mờ. |
| **Nút "Vào ngay"** | Vào thẳng buổi đó, không cần chờ đếm ngược |
| **Nhật ký hoạt động** | Bot đang làm gì — xem đây trước tiên khi có gì đó lạ |
| **Nút "Dừng bot"** | Rời lớp, đóng Chrome, rồi tự đóng luôn cửa sổ này |

Bot mở 2 cửa sổ nằm **cạnh nhau**: bảng theo dõi bên trái, cửa sổ Teams bot điều khiển bên phải.
**Đừng bấm gì vào cửa sổ Teams bên phải** — bot đang thao tác trong đó.

---

## Cách hoạt động

```
┌──────────────────────────────────────────────────────────┐
│  1. Mở Chrome → đăng nhập Teams                          │
│              ↓                                            │
│  2. Đọc lịch học                                          │
│     • Đường nhanh: API JSON của Outlook (~1 giây,         │
│       lấy được nhiều tuần, không phụ thuộc ngôn ngữ)     │
│     • Hỏng thì tự quay về đọc giao diện như cũ            │
│              ↓                                            │
│  3. Chọn buổi: đang diễn ra trước, rồi tới buổi gần nhất │
│              ↓                                            │
│  4. Đếm ngược tới (giờ bắt đầu − phút vào sớm)           │
│              ↓                                            │
│  5. Vào lớp → tắt camera & mic → gửi lời nhắn (nếu đặt)  │
│              ↓                                            │
│  6. Ở trong lớp; nếu bật, rời khi lớp vắng dần            │
│              ↓                                            │
│  7. Rời xong → quay lại bước 2 tìm buổi kế tiếp           │
└──────────────────────────────────────────────────────────┘
```

**Bot vào lớp bằng 2 đường, tự chuyển nếu đường đầu không được:**

1. **Link riêng của buổi học** — chính xác, vào được cả lớp không nằm trong tuần đang hiển thị
2. **Click sự kiện trên Lịch** — dùng khi đường 1 không mở được màn hình vào lớp

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
<summary><b>Nhật ký báo "API Lịch trả lỗi … chuyển sang đọc giao diện"</b></summary>

**Không sao cả, bot vẫn chạy bình thường.** Bot có 2 cách đọc lịch: gọi API của
Outlook (nhanh, thấy được nhiều tuần) và đọc giao diện (chậm hơn, chỉ thấy tuần
đang hiển thị). Dòng này nghĩa là cách nhanh không dùng được nên bot đã tự
chuyển sang cách kia. Bạn không phải làm gì.

Nếu muốn dùng được cách nhanh: để bot chạy qua một vòng quét nữa — nó cần thấy
Teams gọi máy chủ một lần thì mới lấy được thông tin xác thực.
</details>

<details>
<summary><b>Bot đếm ngược tới buổi tuần sau, trong khi đang có lớp diễn ra</b></summary>

Bot ưu tiên lớp **đang diễn ra** trước. Nếu nó bỏ qua lớp hiện tại, kiểm tra
danh sách "Lịch đã dò được" trên bảng theo dõi xem lớp đó có trong đó không:

- **Không có trong danh sách** → buổi học chưa nằm trên Lịch Outlook, hoặc không
  phải *Cuộc họp Microsoft Teams*.
- **Có nhưng bị làm mờ** → bot cho rằng buổi đó đã tan. Nếu lớp kéo dài hơn giờ
  ghi trên Lịch, tăng `stale_after_hours` trong `config.json`.
</details>

<details>
<summary><b>Bot dò lịch rất lâu, cứ bấm qua từng nhóm/kênh</b></summary>

Bạn đang để **Nguồn tìm cuộc họp** là `Chỉ Kênh` hoặc `Cả hai`. Hai chế độ này
phải bấm qua từng kênh của từng nhóm nên rất chậm. Nếu buổi học có trên Lịch
Outlook, chọn **`Chỉ Lịch`** — nhanh hơn rất nhiều.
</details>

<details>
<summary><b>Nút bấm bị lỗi sau khi Teams cập nhật</b></summary>

Microsoft thường xuyên đổi UI — xem mục **Dành cho người phát triển** bên dưới để cập nhật selector.
</details>

---

## Dành cho người phát triển

Microsoft thường xuyên đổi giao diện Teams → có thể làm hỏng các *selector*. Dùng công cụ debug kèm theo:

```bash
python tools/inspect_teams.py
```

Đăng nhập, điều hướng đến màn hình cần, gõ **Enter** để lưu **HTML + screenshot + danh sách nút bấm** vào `dumps/`, rồi cập nhật selector trong `src/selectors_teams.py`.

| File | Vai trò |
|---|---|
| `src/main.py` | Entry point: vòng đời bot, bắt lỗi thân thiện |
| `src/schedule.py` | Vòng lặp chính: dò lịch → đếm ngược → vào lớp |
| `src/scanner.py` | Dò lịch học từ kênh + Lịch Outlook |
| `src/teams_api.py` | Đọc lịch nhanh qua API JSON của Outlook (có fallback) |
| `src/joiner.py` | Vào lớp, tắt cam/mic, gửi lời nhắn, rời họp |
| `src/browser.py` | Mở Chrome/Edge, đăng nhập, wait helpers |
| `src/selectors_teams.py` | **Toàn bộ selector + JS của Teams** (sửa ở đây khi MS đổi UI) |
| `src/webui.py` | Form cấu hình + bảng theo dõi (web) |
| `src/status.py` | Trạng thái chia sẻ + log cho bảng theo dõi |
| `src/config.py` | Đọc/ghi config.json (hỗ trợ cả khi đóng gói exe) |
| `src/notify.py` | Thông báo Discord webhook |
| `src/models.py` / `src/runtime.py` | Data classes / trạng thái dùng chung |
| `tools/inspect_teams.py` | Công cụ debug & chụp DOM |
| `run.bat` / `run.sh` | Khởi động từ mã nguồn (`run.command` gọi vào `run.sh`) |
| `build_local.bat` / `build_local.sh` | Build file chạy 1-click bằng PyInstaller |
| `tests/` | 74 test — chạy bằng `python3 -m pytest tests/` |
| `.github/workflows/release.yml` | Tự build & đăng Releases khi push tag `v*` |
| `config.json.example` | Mẫu cấu hình đầy đủ tất cả tùy chọn |

**Phát hành bản mới:** sửa code → commit → `git tag v1.x.x` → `git push origin main --tags` — GitHub Actions tự build cả 2 nền tảng và đăng lên Releases.

---

## Star History

<a href="https://www.star-history.com/?repos=ntu168108%2Fautoconnect-Teams-extention&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=ntu168108/autoconnect-Teams-extention&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=ntu168108/autoconnect-Teams-extention&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=ntu168108/autoconnect-Teams-extention&type=date&legend=top-left" />
 </picture>
</a>