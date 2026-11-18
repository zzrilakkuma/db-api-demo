#!/bin/bash
# 啟動網站，並用 Cloudflare 臨時通道公開。按 Ctrl+C 會兩個一起關掉。
cd "$(dirname "$0")"
python3 app.py &
APP=$!
trap 'kill $APP 2>/dev/null' EXIT
sleep 1
echo "等 Cloudflare 給公開網址（約 5–10 秒），出現 https://xxxx.trycloudflare.com 那行就是了："
cloudflared tunnel --url http://localhost:8765 2>&1 | grep --line-buffered -o 'https://[a-z0-9-]*\.trycloudflare\.com'
