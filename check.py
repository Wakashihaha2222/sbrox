import requests
import json
import os
import time
import random
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional; on GitHub Actions the env vars come from Secrets directly

# ====== CẤU HÌNH (đọc từ biến môi trường, KHÔNG hardcode) ======
API_KEY = os.environ.get("ATLANTIS_API_KEY", "")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

API_URL = "https://atlantiscmnt.com/api/robux/stock"
BUY_LINK = "https://atlantiscmnt.com/robux-120h"

# Termux (bot chính) và GitHub Actions (bot dự phòng) là HAI TIẾN TRÌNH ĐỘC LẬP,
# mỗi bên dùng một file state riêng để không bị lẫn trạng thái qua git pull/push.
STATE_FILE = os.environ.get("STATE_FILE", "stock_local.json")
LOG_FILE = os.environ.get("LOG_FILE", "price_log.txt")

PRICE_LIMIT = int(os.environ.get("PRICE_LIMIT", "135000"))
STOCK_LOW_THRESHOLD = int(os.environ.get("STOCK_LOW_THRESHOLD", "300"))
MIN_WAIT = int(os.environ.get("MIN_WAIT_SECONDS", "2"))
MAX_WAIT = int(os.environ.get("MAX_WAIT_SECONDS", "4"))
RUN_ONCE = os.environ.get("RUN_ONCE", "false").lower() == "true"

if not API_KEY or not BOT_TOKEN or not CHAT_ID:
    raise SystemExit(
        "Thiếu biến môi trường ATLANTIS_API_KEY / TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID.\n"
        "Xem file .env.example để biết cách thiết lập."
    )

session = requests.Session()
session.headers.update({"x-api-key": API_KEY})


def send_telegram(message, retries=3):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for attempt in range(retries):
        try:
            r = session.get(url, params={"chat_id": CHAT_ID, "text": message}, timeout=10)
            if r.status_code == 200:
                return True
            print(f"Telegram lỗi (status {r.status_code}): {r.text[:200]}")
        except requests.RequestException as e:
            print(f"Telegram lỗi kết nối (lần {attempt + 1}/{retries}): {e}")
        time.sleep(2)
    return False


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            print("File state bị lỗi, tạo state mới.")
    return {"tiers": {}}


def save_state(state):
    tmp_path = STATE_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, STATE_FILE)


def log_prices(timestamp, tiers):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            for tier in tiers:
                rate = tier.get("rate")
                price = tier.get("price_per_1000")
                stock = tier.get("stock")
                f.write(f"{timestamp} | rate={rate} | price={price} | stock={stock}\n")
    except OSError as e:
        print("Không ghi được price_log.txt:", e)


def check_stock():
    state = load_state()
    tiers_state = state.get("tiers", {})

    try:
        r = session.get(API_URL, timeout=15)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError) as e:
        print("Lỗi khi gọi API:", e)
        return

    updated_at = data.get("updated_at", datetime.now().isoformat(timespec="seconds"))
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    tiers_list = data.get("tiers", [])
    log_prices(now_str, tiers_list)

    # Gom TẤT CẢ thay đổi trong lần check này lại, rồi gửi MỖI LOẠI một tin
    # nhắn Telegram DUY NHẤT (thay vì gửi riêng cho từng rate). Nhờ vậy nếu
    # 2-3 rate cùng đạt ngưỡng trong 1 lần check, bạn nhận được 1 tin gộp đủ
    # thông tin, thay vì nhiều tin nhắn liên tiếp dễ bị Telegram giới hạn tốc độ.
    price_hits = []
    restock_hits = []
    low_stock_hits = []

    for tier in tiers_list:
        price = tier.get("price_per_1000")
        rate = tier.get("rate")
        stock = tier.get("stock")

        if price is None or rate is None:
            continue

        tier_key = str(rate)
        prev = tiers_state.get(tier_key, {"last_price": None, "last_stock": None})

        prev_price = prev.get("last_price")
        prev_stock = prev.get("last_stock")

        stock_str = f"{stock:,}" if isinstance(stock, (int, float)) else str(stock)

        # ---------- 1) Giá giảm dưới ngưỡng ----------
        is_below = price <= PRICE_LIMIT
        was_below = prev_price is not None and prev_price <= PRICE_LIMIT
        if is_below and not was_below:
            price_hits.append(f"• Rate ${rate}: {price:,}đ (stock: {stock_str} R$)")

        # ---------- 2) RESTOCK: từ hết hàng -> có hàng lại ----------
        is_out_now = isinstance(stock, (int, float)) and stock <= 0
        was_out = isinstance(prev_stock, (int, float)) and prev_stock <= 0
        if was_out and not is_out_now:
            restock_hits.append(f"• Rate ${rate}: {price:,}đ (stock: {stock_str} R$)")

        # ---------- 3) SẮP HẾT HÀNG ----------
        is_low_now = isinstance(stock, (int, float)) and 0 < stock <= STOCK_LOW_THRESHOLD
        was_low = isinstance(prev_stock, (int, float)) and 0 < prev_stock <= STOCK_LOW_THRESHOLD
        if is_low_now and not was_low:
            low_stock_hits.append(f"• Rate ${rate}: {price:,}đ (còn {stock_str} R$)")

        tiers_state[tier_key] = {
            "last_price": price,
            "last_stock": stock,
        }

    # ---------- Gửi các tin nhắn gộp (mỗi loại 1 tin, nếu có) ----------
    if price_hits:
        msg = (
            "🚨 ROBUX GIÁ SIÊU RẺ! (ngưỡng: {:,}đ)\n\n".format(PRICE_LIMIT)
            + "\n".join(price_hits)
            + f"\n\n🔗 Mua ngay: {BUY_LINK}\n⏰ {updated_at}"
        )
        if send_telegram(msg):
            print(f"Đã gửi Telegram (giá rẻ) - {len(price_hits)} rate")
        else:
            print(f"Gửi Telegram THẤT BẠI (giá rẻ) - {len(price_hits)} rate, sẽ thử lại lần sau")
        time.sleep(1.2)

    if restock_hits:
        msg = (
            "✅ ROBUX ĐÃ CÓ HÀNG LẠI!\n\n"
            + "\n".join(restock_hits)
            + f"\n\n🔗 Mua ngay: {BUY_LINK}\n⏰ {updated_at}"
        )
        if send_telegram(msg):
            print(f"Đã gửi Telegram (restock) - {len(restock_hits)} rate")
        else:
            print(f"Gửi Telegram THẤT BẠI (restock) - {len(restock_hits)} rate, sẽ thử lại lần sau")
        time.sleep(1.2)

    if low_stock_hits:
        msg = (
            "⚠️ ROBUX SẮP HẾT HÀNG! (ngưỡng: {:,} R$)\n\n".format(STOCK_LOW_THRESHOLD)
            + "\n".join(low_stock_hits)
            + f"\n\n🔗 Mua ngay: {BUY_LINK}\n⏰ {updated_at}"
        )
        if send_telegram(msg):
            print(f"Đã gửi Telegram (sắp hết hàng) - {len(low_stock_hits)} rate")
        else:
            print(f"Gửi Telegram THẤT BẠI (sắp hết hàng) - {len(low_stock_hits)} rate, sẽ thử lại lần sau")
        time.sleep(1.2)

    state["tiers"] = tiers_state
    state["last_checked"] = datetime.now().isoformat(timespec="seconds")
    save_state(state)


def main():
    if RUN_ONCE:
        print("Chạy kiểm tra một lần (RUN_ONCE=true)...")
        check_stock()
        return

    print("Bot theo dõi giá & tồn kho Robux đã khởi động (chế độ chạy liên tục)...")
    print(f"Dùng state file: {STATE_FILE}")
    while True:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Đang kiểm tra...")
        try:
            check_stock()
        except Exception as e:
            print("Lỗi không mong muốn:", e)

        wait = random.randint(MIN_WAIT, MAX_WAIT)
        time.sleep(wait)


if __name__ == "__main__":
    main()
