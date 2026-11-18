/*
 * 瀏覽器模式（給 GitHub Pages 用）
 *
 * GitHub Pages 只能放靜態網頁，沒辦法跑 app.py。
 * 所以在 github.io 上（或網址加 ?mode=browser），這支程式會：
 *   1. 用 sql.js（編譯成 WebAssembly 的 SQLite）在瀏覽器裡開一個資料庫
 *   2. 攔截畫面送出的 /api/... 請求，用和 app.py 一樣的規則處理、執行一樣的 SQL
 * 每個人的資料庫都在自己的瀏覽器裡，互不影響；重新整理就會還原。
 * Postman 打不到這個模式（沒有真的伺服器），要用 Postman 請跑 app.py。
 */
(function () {
  const BROWSER_MODE = location.hostname.endsWith('github.io') ||
                       new URLSearchParams(location.search).get('mode') === 'browser';
  if (!BROWSER_MODE) return;
  window.BROWSER_MODE = true;

  const CDN = 'https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.12.0/';
  const realFetch = window.fetch.bind(window);
  let db, schemaText;

  const STATUS_LABEL = { proposal: '洽談中', active: '進行中', review: '待驗收', closed: '已結案', cancelled: '已取消' };
  const ALLOWED = {               // 狀態機：和 app.py 相同
    proposal: ['active', 'cancelled'],
    active: ['review', 'cancelled'],
    review: ['closed', 'active'],
    closed: [],
    cancelled: [],
  };
  const BOOL_COLUMNS = new Set(['is_done', 'is_active']);

  class ApiError extends Error {
    constructor(status, message) { super(message); this.status = status; }
  }

  function loadScript(src) {
    return new Promise((ok, fail) => {
      const s = document.createElement('script');
      s.src = src; s.onload = ok; s.onerror = () => fail(new Error('載入失敗：' + src));
      document.head.appendChild(s);
    });
  }

  async function resetDb() {
    if (!schemaText) schemaText = await (await realFetch('schema.sql')).text();
    db.exec('PRAGMA foreign_keys = ON;');   // SQLite 預設不檢查外鍵，要手動打開
    db.exec(schemaText);
  }

  const ready = (async () => {
    await loadScript(CDN + 'sql-wasm.js');
    const SQL = await window.initSqlJs({ locateFile: f => CDN + f });
    db = new SQL.Database();
    await resetDb();
  })();
  ready.catch(e => console.error(e));

  function showSql(sql, params) {
    for (const p of params) {
      let v;
      if (p === null || p === undefined) v = 'NULL';
      else if (typeof p === 'boolean') v = p ? 'TRUE' : 'FALSE';
      else if (typeof p === 'number') v = String(p);
      else v = "'" + String(p).replace(/'/g, "''") + "'";
      sql = sql.replace('?', v);
    }
    return sql + ';';
  }

  function toObj(row) {
    for (const k in row) if (BOOL_COLUMNS.has(k) && row[k] !== null) row[k] = !!row[k];
    return row;
  }

  // 執行一句 SQL，記到 log 裡，回傳 { rows, n（影響筆數）}
  function run(log, sql, params = []) {
    log.push(showSql(sql, params));
    const bind = params.map(p => typeof p === 'boolean' ? (p ? 1 : 0) : (p === undefined ? null : p));
    let stmt;
    try {
      stmt = db.prepare(sql);
      stmt.bind(bind);
      const rows = [];
      while (stmt.step()) rows.push(toObj(stmt.getAsObject()));
      stmt.free();
      return { rows, n: db.getRowsModified() };
    } catch (e) {
      if (stmt) stmt.free();
      if (/constraint/i.test(e.message)) throw new ApiError(409, '資料庫拒絕了：' + e.message);
      throw e;
    }
  }

  function toInt(s) {
    const n = Number(s);
    if (s === null || s === undefined || s === '' || !Number.isInteger(n)) throw new ApiError(400, `編號要是整數，收到的是 ${JSON.stringify(s)}`);
    return n;
  }

  // ───────────── API 路由（和 app.py 一樣） ─────────────
  function api(method, parts, q, body, log) {
    const is = (m, ...p) => method === m && parts.length === p.length && p.every((x, i) => x === '*' || x === parts[i]);

    if (is('GET', 'projects')) {
      const { rows } = run(log, 'SELECT id, name, status, budget, due_date FROM projects ORDER BY due_date');
      return [200, rows, `查到 ${rows.length} 筆`];
    }

    if (is('GET', 'projects', '*')) {
      const { rows } = run(log, 'SELECT * FROM projects WHERE id = ?', [toInt(parts[1])]);
      if (!rows.length) throw new ApiError(404, '找不到這個案件（SELECT 查到 0 筆）');
      return [200, rows[0], '查到 1 筆'];
    }

    if (is('GET', 'tasks')) {
      const join = q.with === 'project';
      let sql, t;
      if (join) {
        sql = 'SELECT tasks.id, tasks.title, tasks.assignee, tasks.due_date, tasks.is_done,' +
              ' projects.name AS project_name\nFROM tasks\nJOIN projects ON tasks.project_id = projects.id';
        t = 'tasks.';
      } else { sql = 'SELECT * FROM tasks'; t = ''; }
      const conds = [], params = [];
      if (q.assignee) { conds.push(`${t}assignee = ?`); params.push(q.assignee); }
      if (q.done === 'true' || q.done === 'false') { conds.push(`${t}is_done = ?`); params.push(q.done === 'true'); }
      if (conds.length) sql += '\nWHERE ' + conds.join(' AND ');
      sql += `\nORDER BY ${t}due_date`;
      const { rows } = run(log, sql, params);
      return [200, rows, `查到 ${rows.length} 筆`];
    }

    if (is('GET', 'customers')) {
      const sql = q.with === 'projects'
        ? 'SELECT customers.name, projects.name AS project_name, projects.status\nFROM customers\n' +
          'LEFT JOIN projects ON projects.customer_id = customers.id\nORDER BY customers.id'
        : 'SELECT * FROM customers';
      const { rows } = run(log, sql);
      return [200, rows, `查到 ${rows.length} 筆`];
    }

    if (is('POST', 'tasks')) {
      const title = (body.title || '').trim();
      if (!title) throw new ApiError(400, '任務名稱是必填（後端檢查，還沒碰到資料庫）');
      run(log, 'INSERT INTO tasks (project_id, title, assignee, due_date, is_done) VALUES (?, ?, ?, ?, ?)',
          [toInt(body.project_id), title, body.assignee || null, body.due_date || null, false]);
      const newId = db.exec('SELECT last_insert_rowid()')[0].values[0][0];
      const { rows } = run(log, 'SELECT * FROM tasks WHERE id = ?', [newId]);
      return [201, rows[0], `新增成功，新任務的編號是 ${newId}`];
    }

    if (is('PATCH', 'tasks', '*')) {
      const tid = toInt(parts[1]);
      const { n } = run(log, 'UPDATE tasks SET is_done = ? WHERE id = ?', [body.is_done === undefined ? true : !!body.is_done, tid]);
      if (n === 0) throw new ApiError(404, 'UPDATE 改到 0 筆：沒有這個任務');
      const { rows } = run(log, 'SELECT * FROM tasks WHERE id = ?', [tid]);
      return [200, rows[0], `UPDATE 改到 ${n} 筆`];
    }

    if (is('PATCH', 'projects', '*', 'status')) {
      const pid = toInt(parts[1]), next = body.status;

      if (body.unsafe) {   // 「外包廠商版」：不檢查規則，直接改
        const { n } = run(log, 'UPDATE projects SET status = ? WHERE id = ?', [next, pid]);
        if (n === 0) throw new ApiError(404, 'UPDATE 改到 0 筆：沒有這個案件');
        let msg = '改好了，但後端完全沒檢查規則！';
        if (next === 'closed') {
          const left = run(log, 'SELECT COUNT(*) AS n FROM tasks WHERE project_id = ? AND is_done = ?', [pid, false]).rows[0].n;
          if (left) msg += ` 這個案件還有 ${left} 個任務沒完成，會計已經收到開尾款發票的通知了。`;
        }
        const { rows } = run(log, 'SELECT id, name, status FROM projects WHERE id = ?', [pid]);
        return [200, rows[0], msg];
      }

      const found = run(log, 'SELECT status FROM projects WHERE id = ?', [pid]).rows;
      if (!found.length) throw new ApiError(404, '找不到這個案件');
      const cur = found[0].status;
      if (!(ALLOWED[cur] || []).includes(next)) {
        const ok = ALLOWED[cur].map(s => STATUS_LABEL[s]).join('、') || '（沒有，這是終點）';
        throw new ApiError(409, `不能從「${STATUS_LABEL[cur]}」改成「${STATUS_LABEL[next] || next}」。合法的下一步：${ok}`);
      }
      // 把「目前的狀態」也寫進 WHERE：就算兩個人同時改，也只有一個會成功
      const { n } = run(log, 'UPDATE projects SET status = ? WHERE id = ? AND status = ?', [next, pid, cur]);
      if (n === 0) throw new ApiError(409, 'UPDATE 改到 0 筆：狀態剛剛被別人改過了，請重新整理');
      const { rows } = run(log, 'SELECT id, name, status FROM projects WHERE id = ?', [pid]);
      return [200, rows[0], `「${STATUS_LABEL[cur]}」→「${STATUS_LABEL[next]}」，UPDATE 改到 ${n} 筆`];
    }

    if (is('DELETE', 'customers', '*')) {
      let n;
      try {
        n = run(log, 'DELETE FROM customers WHERE id = ?', [toInt(parts[1])]).n;
      } catch (e) {
        if (e instanceof ApiError && e.status === 409)
          throw new ApiError(409, e.message + '（還有案件指向這位客戶，外鍵擋下來了。實務上應該改成停用 is_active = FALSE）');
        throw e;
      }
      if (n === 0) throw new ApiError(404, 'DELETE 刪到 0 筆：沒有這位客戶');
      return [200, null, `DELETE 刪掉 ${n} 筆`];
    }

    throw new ApiError(404, `沒有這個 API：${method} /api/${parts.join('/')}`);
  }

  // 攔截 /api/... 的請求，交給上面的 api() 處理
  window.fetch = async function (input, init = {}) {
    const url = typeof input === 'string' ? input : input.url;
    if (!url.startsWith('/api/')) return realFetch(input, init);
    await ready;

    const u = new URL(url, location.origin);
    const method = (init.method || 'GET').toUpperCase();
    const parts = u.pathname.replace(/^\/api\/?/, '').split('/').filter(Boolean);
    const q = Object.fromEntries(u.searchParams);
    const log = [];
    let status, payload;
    try {
      const body = init.body ? JSON.parse(init.body) : {};
      let result;
      if (method === 'POST' && parts.length === 1 && parts[0] === 'reset') {
        await resetDb();
        log.push('-- 重新執行 schema.sql：刪表、建表、放回練習資料');
        result = [200, null, '資料已還原成講義的練習資料'];
      } else {
        result = api(method, parts, q, body, log);
      }
      status = result[0];
      payload = { ok: true, message: result[2], data: result[1], sql: log };
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(500, '程式錯誤：' + e.message);
      status = err.status;
      payload = { ok: false, message: err.message, sql: log };
    }

    // 和 app.py 在終端機印的一樣，印在瀏覽器的 Console（F12 打開）
    console.log(`%c${method} ${decodeURIComponent(u.pathname + u.search)} → ${status}`, 'font-weight:bold');
    log.forEach(s => console.log('   SQL │ ' + s.replace(/\n/g, '\n       │ ')));

    await new Promise(r => setTimeout(r, 120));   // 模擬網路延遲
    return new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } });
  };

  document.addEventListener('DOMContentLoaded', () => {
    const p = document.querySelector('header p');
    if (p) p.insertAdjacentHTML('beforeend',
      '<br><b>瀏覽器模式：</b>資料庫跑在你自己的瀏覽器裡（SQLite），每個人一份、互不影響，重新整理就還原。按 F12 打開 Console 可以看到執行的 SQL。');
  });
})();
