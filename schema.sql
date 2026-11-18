-- 和講義一樣的練習資料（青禾行銷，全部虛構）
DROP TABLE IF EXISTS contacts;
DROP TABLE IF EXISTS tasks;
DROP TABLE IF EXISTS projects;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
  id INTEGER PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  tax_id VARCHAR(8) UNIQUE,
  is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE projects (
  id INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL,
  name VARCHAR(100) NOT NULL,
  budget INTEGER NOT NULL CHECK (budget >= 0),
  status VARCHAR(20) NOT NULL DEFAULT 'proposal'
    CHECK (status IN ('proposal', 'active', 'review', 'closed', 'cancelled')),
  due_date DATE,
  FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE tasks (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL,
  title VARCHAR(100) NOT NULL,
  assignee VARCHAR(50),
  due_date DATE,
  is_done BOOLEAN NOT NULL DEFAULT FALSE,
  FOREIGN KEY (project_id) REFERENCES projects(id)
);

INSERT INTO customers (id, name, tax_id, is_active) VALUES
  (1, '山嵐咖啡', '24536802', TRUE),
  (2, '好日子烘焙', '53917204', TRUE),
  (3, '藍鯨單車', '80462913', TRUE),
  (4, '松果文具', '61028435', TRUE);

INSERT INTO projects (id, customer_id, name, budget, status, due_date) VALUES
  (1, 1, '秋季新品上市活動', 180000, 'active', '2026-11-30'),
  (2, 1, '門市開幕快閃活動', 60000, 'closed', '2026-09-15'),
  (3, 2, '聖誕禮盒預購', 120000, 'proposal', '2026-12-10'),
  (4, 3, '官網改版', 350000, 'review', '2026-11-20'),
  (5, 3, '年度品牌影片', 280000, 'cancelled', '2026-10-31');

INSERT INTO tasks (id, project_id, title, assignee, due_date, is_done) VALUES
  (1, 1, '拍攝新品照片', '阿哲', '2026-11-05', TRUE),
  (2, 1, '撰寫社群貼文', '美玲', '2026-11-12', FALSE),
  (3, 1, '設定廣告投放', '小林', '2026-11-20', FALSE),
  (4, 2, '快閃活動場地布置', '阿哲', '2026-09-10', TRUE),
  (5, 3, '禮盒包裝設計', '阿哲', '2026-11-25', FALSE),
  (6, 4, '首頁設計稿', '阿哲', '2026-10-30', TRUE),
  (7, 4, '修正客戶回饋', '美玲', '2026-11-08', FALSE),
  (8, 4, '客戶驗收會議', '小林', '2026-11-18', FALSE);
