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
STATE_FILE = "stock.json"

PRICE_LIMIT = int(os.environ.get("PRICE_LIMIT", "118000"))
MIN_WAIT = int(os.environ.get("MIN_WAIT_SECONDS", "5"))
MAX_WAIT = int(os.environ.get("MAX_WAIT_SECONDS", "10"))
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
    # Ghi ra file tạm rồi đổi tên, tránh làm hỏng file nếu bị ngắt giữa chừng
    tmp_path = STATE_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, STATE_FILE)


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

    for tier in data.get("tiers", []):
        price = tier.get("price_per_1000")
        rate = tier.get("rate")
        stock = tier.get("stock")

        if price is None or rate is None:
            continue

        # Dùng "rate" làm khóa định danh cho từng gói (KHÔNG dùng stock,
        # vì stock đổi liên tục và sẽ làm bot gửi tin spam)
        tier_key = str(rate)
        prev = tiers_state.get(tier_key, {"last_price": None, "notified_below": False})

        is_below = price <= PRICE_LIMIT
        was_below = prev.get("notified_below", False)

        # Chỉ gửi tin khi giá VỪA chuyển xuống dưới ngưỡng
        # (nếu giá vẫn ở dưới ngưỡng từ lần trước thì không gửi lại)
        if is_below and not was_below:
            stock_str = f"{stock:,}" if isinstance(stock, (int, float)) else str(stock)
            msg = (
                "🚨 ROBUX GIÁ SIÊU RẺ - DƯỚI 118K!\n\n"
                f"💰 Giá: {price:,}đ / 1000 R$\n"
                f"📈 Rate: ${rate}\n"
                f"📦 Stock: {stock_str} R$\n"
                f"🔗 Mua ngay: {BUY_LINK}\n"
                f"⏰ {updated_at}"
            )

            if send_telegram(msg):
                print(f"Đã gửi Telegram cho rate ${rate} (giá {price:,}đ)")
            else:
                print(f"Gửi Telegram THẤT BẠI cho rate ${rate}, sẽ thử lại lần sau")
                # Không đánh dấu đã gửi nếu gửi thất bại, để lần check sau thử lại
                tiers_state[tier_key] = {"last_price": price, "notified_below": False}
                continue

        tiers_state[tier_key] = {"last_price": price, "notified_below": is_below}

    state["tiers"] = tiers_state
    state["last_checked"] = datetime.now().isoformat(timespec="seconds")
    save_state(state)


def main():
    if RUN_ONCE:
        # Chế độ chạy 1 lần rồi thoát (dùng cho GitHub Actions backup)
        print("Chạy kiểm tra một lần (RUN_ONCE=true)...")
        check_stock()
        return

    print("Bot theo dõi giá Robux đã khởi động (chế độ chạy liên tục)...")
    while True:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Đang kiểm tra...")
        try:
            check_stock()
        except Exception as e:
            # Bắt mọi lỗi bất ngờ để vòng lặp không bị chết hẳn
            print("Lỗi không mong muốn:", e)

        wait = random.randint(MIN_WAIT, MAX_WAIT)
        time.sleep(wait)


if __name__ == "__main__":
    main()
