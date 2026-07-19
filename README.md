# Atlantis Robux Stock Bot — Setup Guide

## 0. Việc cần làm ngay (bảo mật)

Repo `srobx` của bạn đang **public**, và token/API key cũ đã bị lộ. Trước khi làm gì khác:

1. Vào Telegram, chat với **@BotFather** → `/mybots` → chọn bot → **API Token** → **Revoke current token**, lấy token mới.
2. Liên hệ atlantiscmnt.com xin cấp lại API key mới, hủy key cũ (`4e4ad49e-...`).
3. Không bao giờ dán key/token thẳng vào code nữa — dùng biến môi trường (đã sửa trong bản này).

## 1. Tại sao bot cũ "không chạy 24/7"

Thư mục workflow của bạn trên GitHub là `.github/workflow/` (thiếu chữ **s**). GitHub Actions **chỉ** nhận diện workflow trong `.github/workflows/` — nên khả năng cao là job cron của bạn chưa từng chạy lần nào. Bản này đã sửa đúng thành `.github/workflows/stock.yml`.

Ngoài ra, ngay cả khi sửa đúng tên thư mục, GitHub Actions **không đảm bảo** chạy đúng giờ — lịch `cron` có thể bị trễ vài phút đến hơn chục phút khi hệ thống GitHub đông tải. Vì vậy Actions chỉ nên là lớp **dự phòng**, không phải nguồn thông báo chính.

## 2. Kiến trúc mới

- **Bot chính**: chạy liên tục trên điện thoại qua Termux, check mỗi 5–10 giây → gần như tức thời.
- **Bot dự phòng**: GitHub Actions chạy mỗi 5 phút, phòng khi điện thoại tắt/mất mạng.
- **Đã sửa lỗi spam**: bản cũ dùng `rate-price-stock` làm khóa, mà `stock` đổi liên tục nên gần như lần check nào cũng gửi tin. Bản mới chỉ gửi khi giá **vừa** giảm xuống dưới 118.000đ, không gửi lặp lại khi giá vẫn đang ở dưới ngưỡng đó.
- **Tin nhắn giờ có link** mua hàng kèm theo.

## 3. Thiết lập trên Termux (điện thoại)

```bash
pkg update && pkg upgrade -y
pkg install python git tmux termux-api -y
pip install -r requirements.txt

# Tạo file .env thật (không commit file này)
cp .env.example .env
nano .env   # điền API key, bot token, chat id mới vào đây
```

Cấp quyền wake-lock và tắt tối ưu pin cho Termux:
- Cài app **Termux:API** (khác với package `termux-api` ở trên, cần cả app lẫn package) từ F-Droid.
- Vào **Cài đặt điện thoại → Pin → Termux** → chọn "Không giới hạn" / "No restrictions".
- Nếu máy Xiaomi/Oppo/Samsung: thêm Termux vào danh sách **tự khởi động** (Autostart) và **khóa app** trong màn hình đa nhiệm (vuốt lên card Termux, bấm biểu tượng khóa) để hệ thống không kill nó.

Chạy bot trong phiên `tmux` để nó sống cả khi bạn tắt màn hình Termux:

```bash
chmod +x run.sh
tmux new -s robux
./run.sh
```

Nhấn `Ctrl+B` rồi `D` để thoát khỏi tmux mà không dừng bot. Để xem lại log: `tmux attach -t robux`.

## 4. Tự khởi động lại khi restart điện thoại

Cài app **Termux:Boot** (F-Droid, không có trên Play Store) để Termux tự chạy script khi khởi động máy:

```bash
mkdir -p ~/.termux/boot
```

Tạo file `~/.termux/boot/start-robux.sh`:

```bash
#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock
cd ~/srobx
tmux new-session -d -s robux './run.sh'
```

```bash
chmod +x ~/.termux/boot/start-robux.sh
```

Mở app Termux:Boot ít nhất một lần để Android cấp quyền chạy khi boot.

## 5. Thiết lập GitHub Actions (lớp dự phòng)

Trên GitHub: repo → **Settings → Secrets and variables → Actions → New repository secret**, thêm 3 secret:

- `ATLANTIS_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Đẩy code lên (từ Termux, dùng git):

```bash
git add .
git commit -m "Fix workflow path, remove hardcoded secrets, fix spam bug"
git push
```

Vì bot chính đã chạy trên điện thoại, Actions và Termux dùng **hai file `stock.json` độc lập** — không cần đồng bộ giữa chúng, việc trùng thông báo đôi lúc (một từ điện thoại, một từ Actions) là bình thường và không đáng lo.

## 6. Kiểm tra nhanh

Chạy thử một lần thủ công để chắc chắn config đúng trước khi để chạy nền:

```bash
RUN_ONCE=true python3 check.py
```

Nếu thấy dòng báo lỗi "Thiếu biến môi trường..." nghĩa là file `.env` chưa được điền/đọc đúng.
