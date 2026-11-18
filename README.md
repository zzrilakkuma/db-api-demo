# 青禾行銷 迷你案件系統（教學用）

按按鈕 → API → SQL → 資料庫 → 回傳 JSON，一步一步顯示在畫面上。只用 Python 內建套件。

## 啟動
```
cd ~/db-api-demo
python3 app.py           # 打開 http://localhost:8765
python3 app.py --lan     # 同一個 Wi-Fi 的學員可以用 Postman 打你的 IP
```
每次啟動都會把資料還原成講義的練習資料。終端機會印出每個請求執行的 SQL。

## API（Postman 可以直接打）
| Method | 路徑 | SQL |
|---|---|---|
| GET | /api/projects | SELECT 全部案件 |
| GET | /api/projects/4 | SELECT 一個案件（15 → 404） |
| GET | /api/tasks?assignee=阿哲&done=false | SELECT … WHERE |
| GET | /api/tasks?with=project&done=false | JOIN |
| GET | /api/customers?with=projects | LEFT JOIN |
| POST | /api/tasks  `{"project_id":3,"title":"提案簡報","assignee":"小林","due_date":"2026-11-16"}` | INSERT（案件 99 → 外鍵擋） |
| PATCH | /api/tasks/2  `{"is_done":true}` | UPDATE |
| PATCH | /api/projects/3/status  `{"status":"active"}` | 狀態機＋UPDATE … WHERE status = 目前狀態 |
| PATCH | /api/projects/1/status  `{"status":"closed","unsafe":true}` | 外包廠商版：不檢查規則 |
| DELETE | /api/customers/1 | DELETE（客戶 1 被外鍵擋、客戶 4 刪得掉） |
| POST | /api/reset | 還原資料 |

## 檔案
- `app.py`：API／後端，約 280 行，每個 API 都有中文註解
- `index.html`：前端畫面
- `schema.sql`：和講義相同的建表與練習資料

## 公開給學員連（Cloudflare 臨時通道）
需要先安裝 cloudflared：`brew install cloudflared`
```
./start-public.sh
```
等 5–10 秒，終端機會印出 `https://xxxx.trycloudflare.com`，那就是公開網址。按 Ctrl+C 會把網站和通道一起關掉。

- 電腦要一直開著，網址每次啟動都會變。
- 拿到網址的人都能改資料（只有練習資料），所有人共用同一份資料。
