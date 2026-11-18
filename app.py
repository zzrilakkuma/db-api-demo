#!/usr/bin/env python3
"""
青禾行銷・迷你案件系統（教學用）

  瀏覽器按按鈕 ──HTTP──► 這支程式（API／後端）──SQL──► SQLite 資料庫

執行：python3 app.py          → 打開 http://localhost:8765
     python3 app.py --lan    → 同一個 Wi-Fi 的學員也能連（用 Postman 打你的 IP）

只用 Python 內建套件，不用安裝任何東西。
注意：為了教學，API 會把執行的 SQL 一起回傳。真實系統絕對不會這樣做。
"""
import json
import socket
import sqlite3
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).parent
PORT = 8765

db = sqlite3.connect(HERE / "demo.db", check_same_thread=False)
db.row_factory = sqlite3.Row
db.execute("PRAGMA foreign_keys = ON")  # SQLite 預設不檢查外鍵，要手動打開
lock = threading.Lock()

BOOL_COLUMNS = {"is_done", "is_active"}
STATUS_LABEL = {"proposal": "洽談中", "active": "進行中", "review": "待驗收",
                "closed": "已結案", "cancelled": "已取消"}
# 狀態機：每個狀態「可以」改成哪些狀態
ALLOWED = {
    "proposal": ["active", "cancelled"],
    "active": ["review", "cancelled"],
    "review": ["closed", "active"],   # 驗收被退回 → 回到進行中
    "closed": [],
    "cancelled": [],
}


class ApiError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def reset_db():
    with lock:
        db.executescript((HERE / "schema.sql").read_text(encoding="utf-8"))


def show_sql(sql, params):
    """把 ? 換成實際的值，方便上課看（真正執行時用參數，避免 SQL injection）"""
    for p in params:
        if p is None:
            v = "NULL"
        elif isinstance(p, bool):
            v = "TRUE" if p else "FALSE"
        elif isinstance(p, (int, float)):
            v = str(p)
        else:
            v = "'" + str(p).replace("'", "''") + "'"
        sql = sql.replace("?", v, 1)
    return sql + ";"


def to_dict(row):
    d = dict(row)
    for k in d:
        if k in BOOL_COLUMNS and d[k] is not None:
            d[k] = bool(d[k])
    return d


def run(log, sql, params=()):
    """執行一句 SQL，記到 log 裡，回傳 (資料列, 影響筆數, 新資料的 id)"""
    log.append(show_sql(sql, params))
    with lock:
        try:
            cur = db.execute(sql, params)
            rows = [to_dict(r) for r in cur.fetchall()]
            db.commit()
            return rows, cur.rowcount, cur.lastrowid
        except sqlite3.IntegrityError as e:
            db.rollback()
            raise ApiError(409, f"資料庫拒絕了：{e}")


def to_int(s):
    try:
        return int(s)
    except (TypeError, ValueError):
        raise ApiError(400, f"編號要是整數，收到的是 {s!r}")


# ───────────────────────── API 路由 ─────────────────────────

def api(method, parts, q, body, log):
    # GET /api/projects ─ 全部案件
    if method == "GET" and parts == ["projects"]:
        rows, _, _ = run(log, "SELECT id, name, status, budget, due_date FROM projects ORDER BY due_date")
        return 200, rows, f"查到 {len(rows)} 筆"

    # GET /api/projects/4 ─ 一個案件
    if method == "GET" and len(parts) == 2 and parts[0] == "projects":
        rows, _, _ = run(log, "SELECT * FROM projects WHERE id = ?", (to_int(parts[1]),))
        if not rows:
            raise ApiError(404, "找不到這個案件（SELECT 查到 0 筆）")
        return 200, rows[0], "查到 1 筆"

    # GET /api/tasks?assignee=阿哲&done=false&with=project
    if method == "GET" and parts == ["tasks"]:
        join = q.get("with") == "project"
        if join:
            sql = ("SELECT tasks.id, tasks.title, tasks.assignee, tasks.due_date, tasks.is_done,"
                   " projects.name AS project_name\nFROM tasks\nJOIN projects ON tasks.project_id = projects.id")
            t = "tasks."
        else:
            sql, t = "SELECT * FROM tasks", ""
        conds, params = [], []
        if q.get("assignee"):
            conds.append(f"{t}assignee = ?")
            params.append(q["assignee"])
        if q.get("done") in ("true", "false"):
            conds.append(f"{t}is_done = ?")
            params.append(q["done"] == "true")
        if conds:
            sql += "\nWHERE " + " AND ".join(conds)
        sql += f"\nORDER BY {t}due_date"
        rows, _, _ = run(log, sql, params)
        return 200, rows, f"查到 {len(rows)} 筆"

    # GET /api/customers?with=projects ─ LEFT JOIN
    if method == "GET" and parts == ["customers"]:
        if q.get("with") == "projects":
            sql = ("SELECT customers.name, projects.name AS project_name, projects.status\n"
                   "FROM customers\nLEFT JOIN projects ON projects.customer_id = customers.id\n"
                   "ORDER BY customers.id")
        else:
            sql = "SELECT * FROM customers"
        rows, _, _ = run(log, sql)
        return 200, rows, f"查到 {len(rows)} 筆"

    # POST /api/tasks ─ 新增任務
    if method == "POST" and parts == ["tasks"]:
        title = (body.get("title") or "").strip()
        if not title:
            raise ApiError(400, "任務名稱是必填（後端檢查，還沒碰到資料庫）")
        _, _, new_id = run(
            log,
            "INSERT INTO tasks (project_id, title, assignee, due_date, is_done) VALUES (?, ?, ?, ?, ?)",
            (to_int(body.get("project_id")), title, body.get("assignee") or None,
             body.get("due_date") or None, False))
        rows, _, _ = run(log, "SELECT * FROM tasks WHERE id = ?", (new_id,))
        return 201, rows[0], f"新增成功，新任務的編號是 {new_id}"

    # PATCH /api/tasks/2 ─ 修改任務（例如標記完成）
    if method == "PATCH" and len(parts) == 2 and parts[0] == "tasks":
        tid = to_int(parts[1])
        _, n, _ = run(log, "UPDATE tasks SET is_done = ? WHERE id = ?", (bool(body.get("is_done", True)), tid))
        if n == 0:
            raise ApiError(404, "UPDATE 改到 0 筆：沒有這個任務")
        rows, _, _ = run(log, "SELECT * FROM tasks WHERE id = ?", (tid,))
        return 200, rows[0], f"UPDATE 改到 {n} 筆"

    # PATCH /api/projects/3/status ─ 改案件狀態（狀態機）
    if method == "PATCH" and len(parts) == 3 and parts[0] == "projects" and parts[2] == "status":
        pid, new = to_int(parts[1]), body.get("status")

        if body.get("unsafe"):  # 「外包廠商版」：不檢查規則，直接改
            _, n, _ = run(log, "UPDATE projects SET status = ? WHERE id = ?", (new, pid))
            if n == 0:
                raise ApiError(404, "UPDATE 改到 0 筆：沒有這個案件")
            msg = f"改好了，但後端完全沒檢查規則！"
            if new == "closed":
                left, _, _ = run(log, "SELECT COUNT(*) AS n FROM tasks WHERE project_id = ? AND is_done = ?", (pid, False))
                if left[0]["n"]:
                    msg += f" 這個案件還有 {left[0]['n']} 個任務沒完成，會計已經收到開尾款發票的通知了。"
            rows, _, _ = run(log, "SELECT id, name, status FROM projects WHERE id = ?", (pid,))
            return 200, rows[0], msg

        rows, _, _ = run(log, "SELECT status FROM projects WHERE id = ?", (pid,))
        if not rows:
            raise ApiError(404, "找不到這個案件")
        cur = rows[0]["status"]
        if new not in ALLOWED.get(cur, []):
            ok = "、".join(STATUS_LABEL[s] for s in ALLOWED[cur]) or "（沒有，這是終點）"
            raise ApiError(409, f"不能從「{STATUS_LABEL[cur]}」改成「{STATUS_LABEL.get(new, new)}」。合法的下一步：{ok}")
        # 把「目前的狀態」也寫進 WHERE：就算兩個人同時改，也只有一個會成功
        _, n, _ = run(log, "UPDATE projects SET status = ? WHERE id = ? AND status = ?", (new, pid, cur))
        if n == 0:
            raise ApiError(409, "UPDATE 改到 0 筆：狀態剛剛被別人改過了，請重新整理")
        rows, _, _ = run(log, "SELECT id, name, status FROM projects WHERE id = ?", (pid,))
        return 200, rows[0], f"「{STATUS_LABEL[cur]}」→「{STATUS_LABEL[new]}」，UPDATE 改到 {n} 筆"

    # DELETE /api/customers/1 ─ 刪除客戶（外鍵會擋）
    if method == "DELETE" and len(parts) == 2 and parts[0] == "customers":
        try:
            _, n, _ = run(log, "DELETE FROM customers WHERE id = ?", (to_int(parts[1]),))
        except ApiError as e:
            raise ApiError(409, e.message + "（還有案件指向這位客戶，外鍵擋下來了。實務上應該改成停用 is_active = FALSE）")
        if n == 0:
            raise ApiError(404, "DELETE 刪到 0 筆：沒有這位客戶")
        return 200, None, f"DELETE 刪掉 {n} 筆"

    # POST /api/reset ─ 資料還原
    if method == "POST" and parts == ["reset"]:
        reset_db()
        log.append("-- 重新執行 schema.sql：刪表、建表、放回練習資料")
        return 200, None, "資料已還原成講義的練習資料"

    raise ApiError(404, f"沒有這個 API：{method} /api/{'/'.join(parts)}")


# ───────────────────────── HTTP 伺服器 ─────────────────────────

class Handler(BaseHTTPRequestHandler):
    def _send(self, status, payload, ctype="application/json; charset=utf-8"):
        data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle(self, method):
        url = urlparse(self.path)
        if method == "GET" and url.path in ("/", "/index.html"):
            return self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        if not url.path.startswith("/api/"):
            return self._send(404, {"ok": False, "message": "找不到"})

        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        body = {}
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return self._send(400, {"ok": False, "message": "Body 不是合法的 JSON"})

        log = []
        try:
            status, data, message = api(method, url.path.strip("/").split("/")[1:], q, body, log)
            payload = {"ok": True, "message": message, "data": data, "sql": log}
        except ApiError as e:
            status, payload = e.status, {"ok": False, "message": e.message, "sql": log}

        print(f"\n{method} {self.path} → {status}")
        for s in log:
            print("   SQL │ " + s.replace("\n", "\n       │ "))
        self._send(status, payload)

    def do_GET(self): self._handle("GET")
    def do_POST(self): self._handle("POST")
    def do_PATCH(self): self._handle("PATCH")
    def do_DELETE(self): self._handle("DELETE")
    def log_message(self, *args): pass  # 用上面自己印的格式就好


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "你的電腦 IP"


if __name__ == "__main__":
    lan = "--lan" in sys.argv
    reset_db()
    host = "0.0.0.0" if lan else "127.0.0.1"
    print(f"網站：http://localhost:{PORT}")
    if lan:
        print(f"同網路的學員用 Postman 打：http://{lan_ip()}:{PORT}/api/projects")
    print("按 Ctrl+C 停止。每次啟動都會把資料還原成講義的練習資料。")
    ThreadingHTTPServer((host, PORT), Handler).serve_forever()
