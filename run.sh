#!/data/data/com.termux/files/usr/bin/bash
# Chạy bot liên tục trên Termux, tự khởi động lại nếu bị crash

termux-wake-lock

cd "$(dirname "$0")" || exit 1

while true; do
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Khởi động bot..."
    python3 check.py
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Bot dừng/lỗi, khởi động lại sau 5 giây..."
    sleep 5
done
