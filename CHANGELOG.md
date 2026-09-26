# Nhật ký thay đổi

Mỗi mục `## vX.Y.Z` bên dưới được dùng làm ghi chú cho bản phát hành cùng tên
trên trang [Releases](https://github.com/ntu168108/autoconnect-Teams-extention/releases).
Các bản trước v1.2.0: xem trang Releases.

## v1.2.0 — 2026-09-26

Bản này sửa các lỗi logic **sau khi đã vào lớp**, và lỗi của tính năng **tự rời
lớp khi lớp vắng**.

### Sửa lỗi

- **Tự rời lớp ngay sau khi vào.** Bot vào sớm lúc lớp mới có một hai người,
  thấy ít hơn *Số người tối thiểu* là rời, rồi không bao giờ vào lại buổi đó —
  mất trọn buổi học. Giờ bot chỉ xét rời lớp **sau khi lớp đã từng đông** tới
  mức tối thiểu.
- **Một lần đếm sai là rời lớp.** Chỉ một lần đọc nhầm số người (Teams đang vẽ
  lại, mạng chập chờn) đủ để bot bỏ một lớp đang đông. Giờ bot phải thấy lớp
  vắng ở **3 lần đếm liên tiếp** mới rời (`leave_confirm_checks`).
- **Kẹt ở lớp cũ, lỡ buổi kế tiếp.** Giảng viên rời đi mà không bấm "Kết thúc
  cuộc họp" thì bot ngồi mãi ở lớp cũ. Giờ tới giờ buổi kế tiếp, bot tự rời lớp
  cũ và chuyển sang.
- **Bấm Rời không được vẫn báo đã rời.** Khi đó bot bỏ qua luôn buổi kế tiếp mà
  không vào. Giờ bot chỉ coi là đã rời khi rời thật, và tiếp tục thử lại.
- **Đếm nhầm số người trong lớp.** Không còn cộng cả người *được mời nhưng chưa
  vào* hay người *trong phòng chờ*, và không đọc nhầm số trong phím tắt thành
  số người.

### Tính năng mới

- **Tự vào lại khi bị rớt giữa buổi** (mạng rớt, bị mời ra…), nếu buổi học
  chưa hết giờ theo Lịch. Tối đa 2 lần mỗi buổi (`max_rejoins`, `0` = tắt).
- **Nút "Rời lớp"** trên bảng theo dõi khi đang trong lớp.
- **"Vào ngay" khi đang trong lớp khác**: bot rời lớp hiện tại rồi chuyển sang
  buổi bạn chọn.

### Cho người phát triển

- `tools/inspect_teams.py` chạy lại được (trước đó lỗi import), và in ra số
  người bot đọc được mỗi lần chụp để so với Teams.
- Thêm 42 test cho các tình huống trong lớp (tổng 117).
